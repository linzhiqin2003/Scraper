"""Cookies handling for WSJ authentication."""
from pathlib import Path
from typing import Tuple

import httpx

from ...core.browser import get_data_dir
from .config import SOURCE_NAME, DEFAULT_HEADERS


def get_cookies_path() -> Path:
    """Get default cookies.txt path for WSJ."""
    return get_data_dir(SOURCE_NAME) / "cookies.txt"


def parse_netscape_cookies(cookies_file: Path) -> httpx.Cookies:
    """
    Parse Netscape cookies.txt format into httpx.Cookies.

    Format: domain  flag  path  secure  expiration  name  value
    Lines starting with # are comments.
    """
    cookies = httpx.Cookies()

    if not cookies_file.exists():
        raise FileNotFoundError(f"Cookies file not found: {cookies_file}")

    with open(cookies_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            parts = line.split("\t")
            if len(parts) < 7:
                continue

            domain, _, path, secure, _, name, value = parts[:7]
            cookies.set(name, value, domain=domain, path=path)

    return cookies


def load_cookies(cookies_path: Path | None = None) -> httpx.Cookies:
    """Load cookies from file, defaulting to ~/.web_scraper/wsj/cookies.txt."""
    if cookies_path is None:
        cookies_path = get_cookies_path()
    return parse_netscape_cookies(cookies_path)


def validate_cookies(cookies: httpx.Cookies) -> bool:
    """Check if cookies contain necessary WSJ authentication tokens."""
    cookie_names = {cookie.name for cookie in cookies.jar}

    # WSJ typically uses these cookies for authentication
    required_patterns = ["DJSESSION", "wsjregion", "usr_bkt"]
    found = sum(
        1
        for pattern in required_patterns
        if any(pattern in name for name in cookie_names)
    )

    return found >= 1


async def check_cookies_valid_async(cookies: httpx.Cookies) -> Tuple[bool, str]:
    """
    Verify cookies work by checking WSJ homepage for login status (async).

    Returns (is_valid, message).
    """
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
    """
    Verify cookies work by checking WSJ homepage for login status (sync).

    Returns (is_valid, message).
    """
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
