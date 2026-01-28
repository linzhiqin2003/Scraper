"""Authentication module for Reuters login."""

import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from ...core.browser import (
    create_browser,
    load_cookies_sync,
    save_cookies_sync,
    get_state_path,
)
from .config import SOURCE_NAME, BASE_URL, SIGN_IN_URL, Selectors


class LoginStatus(Enum):
    """Login status enumeration."""

    LOGGED_IN = "logged_in"
    LOGGED_OUT = "logged_out"
    SESSION_EXPIRED = "session_expired"
    UNKNOWN = "unknown"


@dataclass
class AuthStatus:
    """Authentication status information."""

    status: LoginStatus
    email: Optional[str] = None
    checked_at: Optional[datetime] = None
    message: Optional[str] = None


def _dismiss_cookie_dialog(page: Page) -> None:
    """Dismiss cookie consent dialog if present."""
    try:
        # Try common cookie consent button selectors
        selectors = [
            '#onetrust-accept-btn-handler',  # OneTrust cookie banner (Reuters uses this)
            'button#onetrust-accept-btn-handler',
            'button:has-text("Accept All Cookies")',
            'button:has-text("Accept All")',
            'button:has-text("Accept all")',
            'button:has-text("I Accept")',
            'button:has-text("Accept")',
            'button[id*="accept"]',
            'button[class*="accept"]',
        ]
        for selector in selectors:
            try:
                btn = page.query_selector(selector)
                if btn and btn.is_visible():
                    btn.click()
                    time.sleep(1)
                    return
            except Exception:
                continue

        # If no button found, try to close the banner by clicking outside or pressing Escape
        try:
            page.keyboard.press("Escape")
            time.sleep(0.5)
        except Exception:
            pass
    except Exception:
        pass


def check_login_status(page: Page) -> AuthStatus:
    """Check if user is logged in by visiting homepage.

    Args:
        page: Playwright Page instance.

    Returns:
        AuthStatus with current login state.
    """
    try:
        page.goto(BASE_URL)
        time.sleep(3)

        try:
            sign_in_link = page.query_selector(Selectors.SIGN_IN_LINK)
            if sign_in_link:
                sign_in_text = sign_in_link.text_content() or ""
                if "Sign In" in sign_in_text:
                    return AuthStatus(
                        status=LoginStatus.LOGGED_OUT,
                        checked_at=datetime.now(),
                        message="Not logged in - Sign In link visible",
                    )
        except Exception:
            pass

        return AuthStatus(
            status=LoginStatus.LOGGED_IN,
            checked_at=datetime.now(),
            message="Logged in - Sign In link not visible",
        )

    except PlaywrightTimeout:
        return AuthStatus(
            status=LoginStatus.UNKNOWN,
            checked_at=datetime.now(),
            message="Timeout while checking login status",
        )
    except Exception as e:
        return AuthStatus(
            status=LoginStatus.UNKNOWN,
            checked_at=datetime.now(),
            message=f"Error checking status: {e}",
        )


def perform_login(
    email: str,
    password: str,
    headless: bool = False,
) -> AuthStatus:
    """Perform login to Reuters.

    Args:
        email: User email address.
        password: User password.
        headless: Whether to run in headless mode.

    Returns:
        AuthStatus indicating login result.
    """
    # Don't load old storage state when logging in fresh
    with create_browser(headless=headless, source=SOURCE_NAME, use_storage_state=False) as page:
        try:
            page.goto(SIGN_IN_URL)
            time.sleep(2)

            # Handle cookie consent dialog if present
            _dismiss_cookie_dialog(page)

            # Step 1: Enter email
            page.wait_for_selector(Selectors.EMAIL_INPUT, timeout=30000)
            page.fill(Selectors.EMAIL_INPUT, email)
            page.click('button:has-text("Next")')

            # Step 2: Enter password
            page.wait_for_selector(Selectors.PASSWORD_INPUT, timeout=30000)
            page.fill(Selectors.PASSWORD_INPUT, password)
            page.click('button:has-text("Sign in")')

            time.sleep(5)

            if "/sign-in" not in page.url:
                status = check_login_status(page)

                if status.status == LoginStatus.LOGGED_IN:
                    save_cookies_sync(page, SOURCE_NAME, BASE_URL)
                    return AuthStatus(
                        status=LoginStatus.LOGGED_IN,
                        email=email,
                        checked_at=datetime.now(),
                        message="Login successful, session saved",
                    )

            try:
                error_elem = page.query_selector('[class*="error"], [role="alert"]')
                if error_elem:
                    error_text = error_elem.text_content() or "Unknown error"
                    return AuthStatus(
                        status=LoginStatus.LOGGED_OUT,
                        email=email,
                        checked_at=datetime.now(),
                        message=f"Login failed: {error_text}",
                    )
            except Exception:
                pass

            return AuthStatus(
                status=LoginStatus.LOGGED_OUT,
                email=email,
                checked_at=datetime.now(),
                message="Login failed: still on sign-in page",
            )

        except PlaywrightTimeout as e:
            return AuthStatus(
                status=LoginStatus.UNKNOWN,
                email=email,
                checked_at=datetime.now(),
                message=f"Timeout during login: {e}",
            )
        except Exception as e:
            return AuthStatus(
                status=LoginStatus.UNKNOWN,
                email=email,
                checked_at=datetime.now(),
                message=f"Login error: {e}",
            )


def interactive_login(headless: bool = False) -> AuthStatus:
    """Interactive login - opens browser for manual login.

    Useful when CAPTCHA or 2FA is required.

    Args:
        headless: Whether to run in headless mode (should be False).

    Returns:
        AuthStatus indicating login result.
    """
    # Don't load old storage state when logging in fresh
    with create_browser(headless=headless, source=SOURCE_NAME, use_storage_state=False) as page:
        try:
            page.goto(SIGN_IN_URL)
            time.sleep(2)

            # Handle cookie consent dialog if present
            _dismiss_cookie_dialog(page)

            print("Please complete login in the browser window...")
            print("Waiting for login to complete (timeout: 5 minutes)...")
            print("Note: If CAPTCHA appears, please complete it manually.")

            timeout = 300
            start_time = time.time()

            while time.time() - start_time < timeout:
                try:
                    current_url = page.url

                    # Check URL first (safer than content)
                    not_sign_in = "/sign-in" not in current_url and "/account/" not in current_url
                    on_reuters = "reuters.com" in current_url

                    # Only check content if URL looks good
                    if not_sign_in and on_reuters:
                        try:
                            page_content = page.content().lower()
                            not_captcha = "captcha" not in current_url and "captcha-delivery" not in page_content
                            if not_captcha:
                                break
                        except Exception:
                            # Page still navigating, wait
                            pass
                except Exception:
                    # Page navigating, ignore
                    pass

                time.sleep(1)
            else:
                return AuthStatus(
                    status=LoginStatus.LOGGED_OUT,
                    checked_at=datetime.now(),
                    message="Login timeout - user did not complete login",
                )

            save_cookies_sync(page, SOURCE_NAME, BASE_URL)
            status = check_login_status(page)

            if status.status == LoginStatus.LOGGED_IN:
                return AuthStatus(
                    status=LoginStatus.LOGGED_IN,
                    checked_at=datetime.now(),
                    message="Interactive login successful, session saved",
                )

            return AuthStatus(
                status=LoginStatus.LOGGED_IN,
                checked_at=datetime.now(),
                message="Login completed, session saved (status check skipped)",
            )

        except Exception as e:
            return AuthStatus(
                status=LoginStatus.UNKNOWN,
                checked_at=datetime.now(),
                message=f"Interactive login error: {e}",
            )
