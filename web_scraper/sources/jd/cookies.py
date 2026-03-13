"""Cookies handling for JD (京东) authentication."""
import json
import logging
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.parse import unquote

import httpx

from ...core.cookies import (
    get_cookies_path as _get_cookies_path,
    load_cookies_httpx,
    load_cookies_playwright as _load_pw,
    parse_netscape_cookies as _parse_raw,
    to_header_string,
)
from .config import SOURCE_NAME, REQUIRED_COOKIES, AUTH_COOKIES, DEFAULT_HEADERS

logger = logging.getLogger(__name__)


def get_cookies_path() -> Path:
    """Get default cookies.txt path for JD."""
    return _get_cookies_path(SOURCE_NAME)


def load_cookies(cookies_path: Path | None = None) -> httpx.Cookies:
    """Load cookies from file, defaulting to ~/.web_scraper/jd/cookies.txt."""
    return load_cookies_httpx(SOURCE_NAME, cookies_path)


def netscape_to_playwright(cookies_file: Path) -> List[Dict]:
    """Parse Netscape cookies.txt into Playwright cookie format."""
    return _load_pw(SOURCE_NAME, cookies_file)


def load_cookies_raw(cookies_path: Path | None = None) -> str:
    """Load cookies as a raw 'name=value; ...' string for HTTP headers.

    Used by Node.js h5st signing service which needs cookies as a string.
    """
    path = cookies_path or get_cookies_path()
    if not path.exists():
        raise FileNotFoundError(f"Cookies file not found: {path}")
    return to_header_string(_parse_raw(path))


def validate_cookies(cookies: httpx.Cookies) -> bool:
    """Check if cookies contain necessary JD authentication tokens."""
    cookie_names = {cookie.name for cookie in cookies.jar}
    return all(name in cookie_names for name in REQUIRED_COOKIES)


def get_username_from_cookies(cookies: httpx.Cookies) -> str | None:
    """Extract username (pin) from _pst cookie."""
    for cookie in cookies.jar:
        if cookie.name == "_pst":
            return unquote(cookie.value)
    return None


def get_area_from_cookies(cookies: httpx.Cookies) -> str | None:
    """Extract area code from ipLoc-djd cookie (format: province_city_county_town)."""
    for cookie in cookies.jar:
        if cookie.name == "ipLoc-djd":
            return cookie.value.replace("-", "_")
    return None


def get_eid_token(cookies: httpx.Cookies) -> str | None:
    """Extract EID token from 3AB9D23F7A4B3CSS cookie."""
    for cookie in cookies.jar:
        if cookie.name == "3AB9D23F7A4B3CSS":
            return cookie.value
    return None


def check_cookies_valid_sync(cookies: httpx.Cookies) -> Tuple[bool, str]:
    """Verify cookies by calling a lightweight JD API."""
    test_url = "https://api.m.jd.com/api"
    params = {
        "appid": "item-v3",
        "functionId": "pctradesoa_queryPlusInfo",
        "client": "pc",
        "clientVersion": "1.0.0",
        "body": json.dumps({"pageId": "JD_SXmain"}),
    }

    with httpx.Client(
        cookies=cookies,
        follow_redirects=True,
        timeout=15.0,
    ) as client:
        try:
            resp = client.get(test_url, params=params, headers=DEFAULT_HEADERS)

            if resp.status_code != 200:
                return False, f"HTTP {resp.status_code}"

            data = resp.json()
            if isinstance(data, dict):
                user_data = data.get("data", {})
                if isinstance(user_data, dict) and user_data.get("isLogin"):
                    username = get_username_from_cookies(cookies)
                    return True, f"Logged in as {username}" if username else "Logged in"

            return False, "Cookies may be expired (isLogin=false)"

        except httpx.RequestError as e:
            return False, f"Request error: {e}"
        except (json.JSONDecodeError, KeyError):
            return False, "Invalid response from JD API"
