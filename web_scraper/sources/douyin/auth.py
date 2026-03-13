"""Authentication helpers for Douyin login/session handling."""

import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Iterator, Optional

from patchright.sync_api import Page, TimeoutError as PlaywrightTimeout, sync_playwright

from ...core.browser import get_state_path, STEALTH_SCRIPT
from .config import SOURCE_NAME, BASE_URL, LOGIN_URL, Timeouts


class LoginStatus(Enum):
    LOGGED_IN = "logged_in"
    LOGGED_OUT = "logged_out"
    UNKNOWN = "unknown"


@dataclass
class AuthStatus:
    status: LoginStatus
    checked_at: Optional[datetime] = None
    message: Optional[str] = None
    current_url: Optional[str] = None


def _check_login_state(page: Page) -> LoginStatus:
    """Infer login state from current page URL and DOM."""
    url = page.url or ""
    if "/login" in url:
        return LoginStatus.LOGGED_OUT

    try:
        # Logged-in indicator: user profile/avatar visible
        # Logged-out indicator: "登录" button visible in header
        result = page.evaluate("""
        () => {
            const loginBtn = document.querySelector(
                'button[class*="login"], [class*="loginBtn"], ' +
                '[class*="login-btn"], [data-e2e="top-login-button"]'
            );
            if (loginBtn && loginBtn.offsetParent !== null) {
                return 'logged_out';
            }
            const avatar = document.querySelector(
                '[class*="avatar"], [class*="Avatar"], ' +
                '[class*="userAvatar"], [data-e2e="user-avatar"]'
            );
            if (avatar && avatar.offsetParent !== null) {
                return 'logged_in';
            }
            return 'unknown';
        }
        """)
        if result == "logged_out":
            return LoginStatus.LOGGED_OUT
        if result == "logged_in":
            return LoginStatus.LOGGED_IN
        return LoginStatus.UNKNOWN
    except Exception:
        return LoginStatus.UNKNOWN


@contextmanager
def _open_douyin_page(
    *,
    headless: bool,
    use_storage_state: bool,
) -> Iterator[Page]:
    """Create browser page with storage state and stealth script."""
    state_file = get_state_path(SOURCE_NAME)
    storage_state = str(state_file) if use_storage_state and state_file.exists() else None

    with sync_playwright() as playwright:
        browser = None
        context = None
        try:
            browser = playwright.chromium.launch(
                headless=headless,
                channel="chrome",
                args=["--disable-blink-features=AutomationControlled"],
            )
            context_kwargs: dict = {
                "viewport": {"width": 1440, "height": 1024},
                "locale": "zh-CN",
            }
            if storage_state:
                context_kwargs["storage_state"] = storage_state

            context = browser.new_context(**context_kwargs)
            context.add_init_script(STEALTH_SCRIPT)
            page = context.new_page()
            try:
                yield page
            finally:
                try:
                    context.close()
                finally:
                    browser.close()
        except Exception:
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
            raise


def _save_storage_state(page: Page) -> None:
    state_file = get_state_path(SOURCE_NAME)
    state_file.parent.mkdir(parents=True, exist_ok=True)
    page.context.storage_state(path=str(state_file))


def interactive_login(
    headless: bool = False,
    timeout_seconds: int = 300,
) -> AuthStatus:
    """Open Douyin login page and wait for user to complete login manually."""
    page: Optional[Page] = None
    try:
        with _open_douyin_page(headless=headless, use_storage_state=False) as opened_page:
            page = opened_page
            page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=Timeouts.NAVIGATION)
            page.wait_for_timeout(1500)

            start_time = time.time()
            while time.time() - start_time < timeout_seconds:
                status = _check_login_state(page)
                if status == LoginStatus.LOGGED_IN:
                    _save_storage_state(page)
                    return AuthStatus(
                        status=LoginStatus.LOGGED_IN,
                        checked_at=datetime.now(),
                        message="Login successful, session saved",
                        current_url=page.url,
                    )
                if "/login" not in page.url and "douyin.com" in page.url:
                    # URL left the login page — verify once more before saving
                    page.wait_for_timeout(2000)
                    if _check_login_state(page) == LoginStatus.LOGGED_IN:
                        _save_storage_state(page)
                        return AuthStatus(
                            status=LoginStatus.LOGGED_IN,
                            checked_at=datetime.now(),
                            message="Login successful, session saved",
                            current_url=page.url,
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
            message=f"Browser error: {exc}",
            current_url=page.url if page else None,
        )


def check_saved_session(headless: bool = True) -> AuthStatus:
    """Validate saved storage state by opening Douyin home page."""
    state_file = get_state_path(SOURCE_NAME)
    if not state_file.exists():
        return AuthStatus(
            status=LoginStatus.LOGGED_OUT,
            checked_at=datetime.now(),
            message="No saved session found. Run 'scraper douyin login' or 'scraper douyin import-cookies'.",
        )

    page: Optional[Page] = None
    try:
        with _open_douyin_page(headless=headless, use_storage_state=True) as opened_page:
            page = opened_page
            page.goto(BASE_URL, wait_until="domcontentloaded", timeout=Timeouts.NAVIGATION)
            page.wait_for_timeout(3000)

            status = _check_login_state(page)
            if status == LoginStatus.LOGGED_IN:
                return AuthStatus(
                    status=LoginStatus.LOGGED_IN,
                    checked_at=datetime.now(),
                    message="Session is valid",
                    current_url=page.url,
                )
            if status == LoginStatus.LOGGED_OUT:
                return AuthStatus(
                    status=LoginStatus.LOGGED_OUT,
                    checked_at=datetime.now(),
                    message="Session expired or not logged in",
                    current_url=page.url,
                )
            return AuthStatus(
                status=LoginStatus.UNKNOWN,
                checked_at=datetime.now(),
                message="Could not confirm login status",
                current_url=page.url,
            )
    except Exception as exc:
        return AuthStatus(
            status=LoginStatus.UNKNOWN,
            checked_at=datetime.now(),
            message=f"Status check failed: {exc}",
            current_url=page.url if page else None,
        )


def clear_session() -> bool:
    """Delete saved session state file."""
    state_file = get_state_path(SOURCE_NAME)
    if state_file.exists():
        state_file.unlink()
        return True
    return False
