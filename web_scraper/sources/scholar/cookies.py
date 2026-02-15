"""Cookie management for Google Scholar (optional).

Google Scholar does not require login, but providing Google cookies
can reduce CAPTCHA frequency.
"""
import shutil
from pathlib import Path
from typing import Tuple

import httpx

from ...core.browser import get_data_dir
from .config import SOURCE_NAME, DEFAULT_HEADERS, BASE_URL


def get_cookies_path() -> Path:
    """Get default cookies.txt path for Scholar."""
    return get_data_dir(SOURCE_NAME) / "cookies.txt"


def parse_netscape_cookies(cookies_file: Path) -> httpx.Cookies:
    """Parse Netscape cookies.txt format into httpx.Cookies.

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
    """Load cookies from file. Returns empty cookies if file doesn't exist.

    Unlike WSJ, Scholar doesn't require cookies to function.
    Cookies are optional and only help reduce CAPTCHA frequency.
    """
    if cookies_path is None:
        cookies_path = get_cookies_path()

    if not cookies_path.exists():
        return httpx.Cookies()

    return parse_netscape_cookies(cookies_path)


def import_cookies(source: Path) -> Path:
    """Import cookies.txt to the standard location.

    Returns:
        Path to the saved cookies file.
    """
    if not source.exists():
        raise FileNotFoundError(f"File not found: {source}")

    dest = get_cookies_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(source, dest)
    return dest


def check_cookies_valid_sync(cookies: httpx.Cookies) -> Tuple[bool, str]:
    """Verify cookies work by testing a Scholar request.

    Returns (is_valid, message).
    """
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
