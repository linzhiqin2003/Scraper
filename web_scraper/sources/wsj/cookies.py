"""Cookies handling for WSJ authentication."""
from pathlib import Path
from typing import Tuple

import httpx

from ...core.cookies import (
    get_cookies_path as _get_cookies_path,
    load_cookies_httpx,
)
from .config import SOURCE_NAME, DEFAULT_HEADERS


def get_cookies_path() -> Path:
    """Get default cookies.txt path for WSJ."""
    return _get_cookies_path(SOURCE_NAME)


def load_cookies(cookies_path: Path | None = None) -> httpx.Cookies:
    """Load cookies from file, defaulting to ~/.web_scraper/wsj/cookies.txt."""
    return load_cookies_httpx(SOURCE_NAME, cookies_path)


def validate_cookies(cookies: httpx.Cookies) -> bool:
    """Check if cookies contain necessary WSJ authentication tokens."""
    cookie_names = {cookie.name for cookie in cookies.jar}

    # connect.sid is the Express session cookie set by the new WSJ SSO flow
    # DJSESSION/wsjregion/usr_bkt are legacy cookies that may or may not appear
    auth_patterns = ["connect.sid", "DJSESSION", "wsjregion", "usr_bkt"]
    return any(
        any(pattern in name for name in cookie_names)
        for pattern in auth_patterns
    )


async def check_cookies_valid_async(cookies: httpx.Cookies) -> Tuple[bool, str]:
    """Verify cookies work by checking WSJ homepage for login status (async)."""
    test_url = "https://www.wsj.com/"

    async with httpx.AsyncClient(cookies=cookies, follow_redirects=True) as client:
        try:
            resp = await client.get(test_url, headers=DEFAULT_HEADERS)

            if resp.status_code == 200:
                content = resp.text
                if (
                    "Sign Out" in content
                    or "My Account" in content
                    or "data-logged-in" in content
                ):
                    return True, "Cookies are valid (logged in)"
                cookie_names = {c.name for c in cookies.jar}
                if any(
                    "usr" in n.lower() or "session" in n.lower() for n in cookie_names
                ):
                    return True, "Cookies loaded (auth cookies present)"
                return False, "Cookies may be expired (no login detected)"
            else:
                return False, f"Unexpected status code: {resp.status_code}"

        except httpx.RequestError as e:
            return False, f"Request error: {e}"


def check_cookies_valid_sync(cookies: httpx.Cookies) -> Tuple[bool, str]:
    """Verify cookies work by checking WSJ homepage for login status (sync)."""
    test_url = "https://www.wsj.com/"

    with httpx.Client(cookies=cookies, follow_redirects=True) as client:
        try:
            resp = client.get(test_url, headers=DEFAULT_HEADERS)

            if resp.status_code == 200:
                content = resp.text
                if (
                    "Sign Out" in content
                    or "My Account" in content
                    or "data-logged-in" in content
                ):
                    return True, "Cookies are valid (logged in)"
                cookie_names = {c.name for c in cookies.jar}
                if any(
                    "usr" in n.lower() or "session" in n.lower() for n in cookie_names
                ):
                    return True, "Cookies loaded (auth cookies present)"
                return False, "Cookies may be expired (no login detected)"
            else:
                return False, f"Unexpected status code: {resp.status_code}"

        except httpx.RequestError as e:
            return False, f"Request error: {e}"
