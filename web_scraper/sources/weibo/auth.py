"""Authentication helpers for Weibo login/session handling."""

import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Iterator, Optional
from urllib.parse import urlparse

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout, sync_playwright

from ...core.browser import get_state_path
from .config import (
    SOURCE_NAME,
    SEARCH_URL,
    LOGIN_URL,
    Selectors,
    Timeouts,
)


class LoginStatus(Enum):
    """Login status enumeration."""

    LOGGED_IN = "logged_in"
    LOGGED_OUT = "logged_out"
    SESSION_EXPIRED = "session_expired"
    UNKNOWN = "unknown"


@dataclass
class AuthStatus:
    """Authentication status payload."""

    status: LoginStatus
    checked_at: Optional[datetime] = None
    message: Optional[str] = None
    current_url: Optional[str] = None


def _classify_url(url: str) -> LoginStatus:
    """Infer login state from URL patterns."""
    try:
        parsed = urlparse(url or "")
    except Exception:
        return LoginStatus.UNKNOWN

    host = (parsed.hostname or "").lower()
    path = parsed.path or "/"

    if not host:
        return LoginStatus.UNKNOWN

    # Login/visitor flows on passport subdomain are not authenticated.
    if host == "passport.weibo.com":
        if path.startswith("/sso/signin") or path.startswith("/visitor/"):
            return LoginStatus.LOGGED_OUT
        return LoginStatus.UNKNOWN

    # WeChat OAuth handoff page - still pending user action.
    if host == "open.weixin.qq.com":
        return LoginStatus.UNKNOWN

    # Search domain is the most reliable authenticated target.
    if host == "s.weibo.com":
        return LoginStatus.LOGGED_IN

    # Any non-passport Weibo host generally means we are inside logged-in Web.
    if host == "weibo.com" or host.endswith(".weibo.com"):
        return LoginStatus.LOGGED_IN

    return LoginStatus.UNKNOWN


def _looks_like_login_form(page: Page) -> bool:
    """Check whether login form inputs are currently visible."""
    try:
        fields = page.query_selector_all(Selectors.LOGIN_FORM_INPUT)
        return any(field.is_visible() for field in fields)
    except Exception:
        return False


def _save_storage_state(page: Page) -> None:
    """Persist browser storage state for later sessions."""
    state_file = get_state_path(SOURCE_NAME)
    state_file.parent.mkdir(parents=True, exist_ok=True)
    page.context.storage_state(path=str(state_file))


def _launch_strategies(headless: bool) -> list[tuple[str, dict]]:
    """Launch configurations ordered from most stable to fallback."""
    base_args = ["--disable-gpu", "--disable-blink-features=AutomationControlled"]
    return [
        (
            "chrome",
            {
                "headless": headless,
                "channel": "chrome",
                "args": base_args,
            },
        ),
        (
            "chromium",
            {
                "headless": headless,
                "args": base_args,
            },
        ),
    ]


@contextmanager
def _open_weibo_page(
    *,
    headless: bool,
    use_storage_state: bool,
) -> Iterator[Page]:
    """Create browser page with strategy fallback and clean shutdown."""
    state_file = get_state_path(SOURCE_NAME)
    storage_state = str(state_file) if use_storage_state and state_file.exists() else None

    last_error: Optional[Exception] = None
    with sync_playwright() as playwright:
        for _strategy_name, launch_kwargs in _launch_strategies(headless):
            browser = None
            context = None
            try:
                browser = playwright.chromium.launch(**launch_kwargs)

                context_options = {
                    "viewport": {"width": 1440, "height": 1024},
                    "locale": "zh-CN",
                }
                if storage_state:
                    context_options["storage_state"] = storage_state

                context = browser.new_context(**context_options)
                context.add_init_script(
                    "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
                )
                page = context.new_page()
                try:
                    yield page
                finally:
                    try:
                        context.close()
                    finally:
                        browser.close()
                return
            except Exception as exc:
                last_error = exc
                if context is not None:
                    try:
                        context.close()
                    except Exception:
                        pass
                if browser is not None:
                    try:
                        browser.close()
                    except Exception:
                        pass
                continue

    message = f"Browser launch failed for all strategies. Last error: {last_error}"
    raise RuntimeError(message)


def _friendly_browser_error(exc: Exception) -> str:
    """Map launch errors to actionable guidance."""
    msg = str(exc)
    if "Target page, context or browser has been closed" in msg:
        return (
            "Browser crashed at startup. Please retry login. "
            "If it keeps happening, run 'playwright install --force chromium'."
        )
    if "Executable doesn't exist" in msg:
        return "Playwright browser is missing. Run: playwright install chromium"
    return f"Browser startup failed: {msg}"


def check_login_status(page: Page) -> AuthStatus:
    """Check whether current session is logged in."""
    try:
        page.goto(SEARCH_URL, wait_until="domcontentloaded", timeout=Timeouts.NAVIGATION)
        page.wait_for_timeout(2000)

        status = _classify_url(page.url)
        if status == LoginStatus.LOGGED_OUT:
            if _looks_like_login_form(page):
                message = "Not logged in - redirected to Weibo login page"
            else:
                message = "Not logged in - redirected to Weibo visitor flow"
            return AuthStatus(
                status=LoginStatus.LOGGED_OUT,
                checked_at=datetime.now(),
                message=message,
                current_url=page.url,
            )

        if status == LoginStatus.LOGGED_IN:
            return AuthStatus(
                status=LoginStatus.LOGGED_IN,
                checked_at=datetime.now(),
                message="Logged in - search page is accessible",
                current_url=page.url,
            )

        return AuthStatus(
            status=LoginStatus.UNKNOWN,
            checked_at=datetime.now(),
            message="Could not confirm login status from URL",
            current_url=page.url,
        )

    except PlaywrightTimeout:
        return AuthStatus(
            status=LoginStatus.UNKNOWN,
            checked_at=datetime.now(),
            message="Timeout while checking Weibo session status",
            current_url=page.url if page else None,
        )
    except Exception as exc:
        return AuthStatus(
            status=LoginStatus.UNKNOWN,
            checked_at=datetime.now(),
            message=f"Status check failed: {exc}",
            current_url=page.url if page else None,
        )


def interactive_login(
    headless: bool = False,
    timeout_seconds: int = Timeouts.LOGIN_MANUAL // 1000,
) -> AuthStatus:
    """Open Weibo login page and wait for user to complete login manually."""
    page: Optional[Page] = None
    try:
        with _open_weibo_page(headless=headless, use_storage_state=False) as opened_page:
            page = opened_page
            page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=Timeouts.NAVIGATION)
            page.wait_for_timeout(1500)

            start_time = time.time()
            while time.time() - start_time < timeout_seconds:
                status = _classify_url(page.url)
                if status == LoginStatus.LOGGED_IN:
                    # Verify by opening search URL before persisting state.
                    verified = check_login_status(page)
                    if verified.status == LoginStatus.LOGGED_IN:
                        _save_storage_state(page)
                        return AuthStatus(
                            status=LoginStatus.LOGGED_IN,
                            checked_at=datetime.now(),
                            message="Login successful, session saved",
                            current_url=verified.current_url or page.url,
                        )
                page.wait_for_timeout(1000)

            return AuthStatus(
                status=LoginStatus.LOGGED_OUT,
                checked_at=datetime.now(),
                message="Login timeout - session not established",
                current_url=page.url,
            )
    except PlaywrightTimeout:
        return AuthStatus(
            status=LoginStatus.UNKNOWN,
            checked_at=datetime.now(),
            message="Timeout while opening login page",
            current_url=page.url if page else None,
        )
    except Exception as exc:
        return AuthStatus(
            status=LoginStatus.UNKNOWN,
            checked_at=datetime.now(),
            message=_friendly_browser_error(exc),
            current_url=page.url if page else None,
        )


def check_saved_session(headless: bool = True) -> AuthStatus:
    """Validate saved storage state by opening Weibo search page."""
    state_file = get_state_path(SOURCE_NAME)
    if not state_file.exists():
        return AuthStatus(
            status=LoginStatus.LOGGED_OUT,
            checked_at=datetime.now(),
            message="No saved session found. Run 'scraper weibo login' first.",
            current_url=None,
        )

    page: Optional[Page] = None
    try:
        with _open_weibo_page(headless=headless, use_storage_state=True) as opened_page:
            page = opened_page
            return check_login_status(page)
    except Exception as exc:
        return AuthStatus(
            status=LoginStatus.UNKNOWN,
            checked_at=datetime.now(),
            message=_friendly_browser_error(exc),
            current_url=page.url if page else None,
        )


def clear_session() -> bool:
    """Delete saved session state file."""
    state_file = get_state_path(SOURCE_NAME)
    if state_file.exists():
        state_file.unlink()
        return True
    return False
