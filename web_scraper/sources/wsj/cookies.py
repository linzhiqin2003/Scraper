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
    return _has_auth_cookie_names({cookie.name for cookie in cookies.jar})


def _has_auth_cookie_names(cookie_names: set[str]) -> bool:
    """Detect both legacy and current WSJ auth cookies."""
    lowered = {name.lower() for name in cookie_names}
    markers = {"connect.sid", "djsession", "wsjregion", "usr_bkt", "sso", "csrf"}
    return any(marker in name for name in lowered for marker in markers)


def _interpret_validation_response(
    status_code: int,
    content: str,
    cookies: httpx.Cookies,
) -> Tuple[bool, str]:
    """Interpret WSJ validation responses using body markers and auth cookies."""
    if status_code != 200:
        return False, f"Unexpected status code: {status_code}"

    if (
        "Sign Out" in content
        or "My Account" in content
        or "data-logged-in" in content
    ):
        return True, "Cookies are valid (logged in)"

    if _has_auth_cookie_names({c.name for c in cookies.jar}):
        return True, "Cookies loaded (auth cookies present)"

    return False, "Cookies may be expired (no login detected)"


async def check_cookies_valid_async(cookies: httpx.Cookies) -> Tuple[bool, str]:
    """Verify cookies work by checking WSJ homepage for login status (async)."""
    test_url = "https://www.wsj.com/"

    async with httpx.AsyncClient(cookies=cookies, follow_redirects=True) as client:
        try:
            resp = await client.get(test_url, headers=DEFAULT_HEADERS)
            return _interpret_validation_response(resp.status_code, resp.text, cookies)

        except httpx.RequestError as e:
            return False, f"Request error: {e}"


def check_cookies_valid_sync(cookies: httpx.Cookies) -> Tuple[bool, str]:
    """Verify cookies work by checking WSJ homepage for login status (sync)."""
    test_url = "https://www.wsj.com/"
    fallback_message = "Cookies may be expired (browser validation failed)"

    with httpx.Client(cookies=cookies, follow_redirects=True) as client:
        try:
            resp = client.get(test_url, headers=DEFAULT_HEADERS)
            is_valid, message = _interpret_validation_response(resp.status_code, resp.text, cookies)
            if is_valid:
                return is_valid, message
            fallback_message = message

        except httpx.RequestError as e:
            fallback_message = f"Request error: {e}"

    try:
        from .browser_fetch import fetch_html

        html = fetch_html(test_url)
        return _interpret_validation_response(200, html, cookies)
    except Exception:
        return False, fallback_message
