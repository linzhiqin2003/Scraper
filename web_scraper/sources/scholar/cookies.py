"""Cookie management for Google Scholar (optional).

Google Scholar does not require login, but providing Google cookies
can reduce CAPTCHA frequency.
"""
from pathlib import Path
from typing import Tuple

import httpx

from ...core.cookies import (
    get_cookies_path as _get_cookies_path,
    import_cookies as _import_cookies,
    load_cookies_httpx,
)
from .config import SOURCE_NAME, DEFAULT_HEADERS, BASE_URL


def get_cookies_path() -> Path:
    """Get default cookies.txt path for Scholar."""
    return _get_cookies_path(SOURCE_NAME)


def load_cookies(cookies_path: Path | None = None) -> httpx.Cookies:
    """Load cookies from file. Returns empty cookies if file doesn't exist."""
    return load_cookies_httpx(SOURCE_NAME, cookies_path)


def import_cookies(source: Path) -> Path:
    """Import cookies.txt to the standard location."""
    return _import_cookies(source, SOURCE_NAME)


def check_cookies_valid_sync(cookies: httpx.Cookies) -> Tuple[bool, str]:
    """Verify cookies work by testing a Scholar request."""
    test_url = f"{BASE_URL}/scholar?q=test"

    with httpx.Client(cookies=cookies, follow_redirects=True) as client:
        try:
            resp = client.get(test_url, headers=DEFAULT_HEADERS)

            if resp.status_code == 200:
                content = resp.text
                if "/sorry/" in resp.url.path or "captcha" in content.lower():
                    return False, "CAPTCHA detected - cookies may not be effective"
                if "gs_r" in content:
                    return True, "Cookies are working (search results returned)"
                return True, "Request succeeded (cookies loaded)"
            elif resp.status_code == 429:
                return False, "Rate limited (429) - wait and try again"
            else:
                return False, f"Unexpected status code: {resp.status_code}"

        except httpx.RequestError as e:
            return False, f"Request error: {e}"
