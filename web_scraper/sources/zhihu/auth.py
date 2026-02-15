"""Authentication helpers for Zhihu login/session handling."""

import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Iterator, Optional
from urllib.parse import urlparse

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout, sync_playwright

from ...core.browser import get_state_path
from .config import LOGIN_URL, SEARCH_URL, SOURCE_NAME, Selectors, Timeouts


class LoginStatus(Enum):
    """Login status enumeration."""

    LOGGED_IN = "logged_in"
    LOGGED_OUT = "logged_out"
    BLOCKED = "blocked"
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

    if "zhihu.com" not in host:
        return LoginStatus.UNKNOWN

    if path.startswith("/signin") or path.startswith("/signup"):
        return LoginStatus.LOGGED_OUT

    if path.startswith("/account/unhuman") or "captcha" in path:
        return LoginStatus.BLOCKED

    return LoginStatus.UNKNOWN


def _looks_logged_in(page: Page) -> bool:
    """Check whether logged-in user indicators are visible."""
    try:
        selectors = Selectors.USER_AVATAR.split(",")
        return any(
            (el := page.query_selector(selector.strip())) is not None and el.is_visible()
            for selector in selectors
        )
    except Exception:
        return False


def _looks_logged_out(page: Page) -> bool:
    """Check whether logged-out indicators are visible."""
    try:
        selectors = (Selectors.LOGIN_ENTRY + ", " + Selectors.LOGIN_MODAL_HINT).split(",")
        for selector in selectors:
            element = page.query_selector(selector.strip())
            if element and element.is_visible():
                return True
    except Exception:
        return False
    return False


def _save_storage_state(page: Page) -> None:
    """Persist browser storage state for later sessions."""
    state_file = get_state_path(SOURCE_NAME)
    state_file.parent.mkdir(parents=True, exist_ok=True)
    page.context.storage_state(path=str(state_file))


def _launch_strategies(headless: bool) -> list[tuple[str, dict]]:
    """Launch configurations ordered from most stable to fallback."""
    base_args = [
        "--disable-gpu",
        "--disable-blink-features=AutomationControlled",
    ]
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
def _open_zhihu_page(
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
            "Browser crashed at startup. Please retry. "
            "If it keeps happening, run 'playwright install --force chromium'."
        )
    if "Executable doesn't exist" in msg:
        return "Playwright browser is missing. Run: playwright install chromium"
    return f"Browser startup failed: {msg}"


def _classify_current_page(page: Page) -> AuthStatus:
    """Classify login status from current page without navigation."""
    status = _classify_url(page.url)
    if status == LoginStatus.BLOCKED:
        return AuthStatus(
            status=LoginStatus.BLOCKED,
            checked_at=datetime.now(),
            message="Blocked by Zhihu security verification (unhuman/captcha)",
            current_url=page.url,
        )
    if status == LoginStatus.LOGGED_OUT:
        return AuthStatus(
            status=LoginStatus.LOGGED_OUT,
            checked_at=datetime.now(),
            message="Not logged in - redirected to Zhihu signin page",
            current_url=page.url,
        )

    if _looks_logged_in(page):
        return AuthStatus(
            status=LoginStatus.LOGGED_IN,
            checked_at=datetime.now(),
            message="Logged in - user menu/avatar detected",
            current_url=page.url,
        )

    if _looks_logged_out(page):
        return AuthStatus(
            status=LoginStatus.LOGGED_OUT,
            checked_at=datetime.now(),
            message="Not logged in - login entry/modal is visible",
            current_url=page.url,
        )

    return AuthStatus(
        status=LoginStatus.UNKNOWN,
        checked_at=datetime.now(),
        message="Could not confirm login status",
        current_url=page.url,
    )


def check_login_status(page: Page, navigate: bool = True) -> AuthStatus:
    """Check whether current session is logged in.

    Args:
        page: Playwright page instance.
        navigate: When True, first navigate to Zhihu search page for verification.
    """
    try:
        if navigate:
            page.goto(SEARCH_URL, wait_until="domcontentloaded", timeout=Timeouts.NAVIGATION)
            page.wait_for_timeout(2000)

        return _classify_current_page(page)
    except PlaywrightTimeout:
        return AuthStatus(
            status=LoginStatus.UNKNOWN,
            checked_at=datetime.now(),
            message="Timeout while checking Zhihu session status",
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
    """Open Zhihu login page and wait for user to complete login manually."""
    page: Optional[Page] = None
    try:
        with _open_zhihu_page(headless=headless, use_storage_state=False) as opened_page:
            page = opened_page
            page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=Timeouts.NAVIGATION)
            page.wait_for_timeout(1500)

            start_time = time.time()
            last_observed = LoginStatus.UNKNOWN
            while time.time() - start_time < timeout_seconds:
                # During manual login, do NOT force navigation.
                # Especially on /account/unhuman we must wait for user verification.
                current = check_login_status(page, navigate=False)
                last_observed = current.status

                if current.status == LoginStatus.LOGGED_IN:
                    # Double-check via target page to avoid false positives.
                    verified = check_login_status(page, navigate=True)
                    if verified.status == LoginStatus.LOGGED_IN:
                        _save_storage_state(page)
                        return AuthStatus(
                            status=LoginStatus.LOGGED_IN,
                            checked_at=datetime.now(),
                            message="Login successful, session saved",
                            current_url=verified.current_url or page.url,
                        )

                page.wait_for_timeout(1500)

            if last_observed == LoginStatus.BLOCKED:
                timeout_message = (
                    "Login timeout - still blocked by Zhihu security verification "
                    "(unhuman/captcha not completed)"
                )
            else:
                timeout_message = "Login timeout - session not established"

            return AuthStatus(
                status=LoginStatus.LOGGED_OUT,
                checked_at=datetime.now(),
                message=timeout_message,
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
    """Validate saved storage state by opening Zhihu search page."""
    state_file = get_state_path(SOURCE_NAME)
    if not state_file.exists():
        return AuthStatus(
            status=LoginStatus.LOGGED_OUT,
            checked_at=datetime.now(),
            message="No saved session found. Run 'scraper zhihu login' first.",
            current_url=None,
        )

    page: Optional[Page] = None
    try:
        with _open_zhihu_page(headless=headless, use_storage_state=True) as opened_page:
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
