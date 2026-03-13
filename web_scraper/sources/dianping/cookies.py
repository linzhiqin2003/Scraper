"""Cookie handling for Dianping authentication."""
from pathlib import Path
from typing import Dict, Tuple

import httpx

from ...core.cookies import (
    get_cookies_path as _get_cookies_path,
    load_cookies_httpx,
    load_cookies_playwright as _load_pw,
)
from .config import (
    SOURCE_NAME,
    AUTH_COOKIE_NAMES,
    GROWTH_USER_INFO_URL,
    JSON_HEADERS,
    DP_HOME_URL,
)


def get_cookies_path() -> Path:
    """Get default cookies.txt path for Dianping."""
    return _get_cookies_path(SOURCE_NAME)


def load_cookies(cookies_path: Path | None = None) -> httpx.Cookies:
    """Load cookies, defaulting to ~/.web_scraper/dianping/cookies.txt."""
    return load_cookies_httpx(SOURCE_NAME, cookies_path)


def load_playwright_cookies(cookies_path: Path | None = None) -> list[dict]:
    """Load Netscape cookies into Playwright cookie objects."""
    return _load_pw(SOURCE_NAME, cookies_path)


def get_cookie_dict(cookies: httpx.Cookies) -> Dict[str, str]:
    """Convert httpx cookies to a plain dictionary."""
    return {c.name: c.value for c in cookies.jar}


def get_lx_cuid(cookies: httpx.Cookies) -> str:
    """Extract _lxsdk_cuid from cookies."""
    return get_cookie_dict(cookies).get("_lxsdk_cuid", "")


def validate_cookies(cookies: httpx.Cookies) -> bool:
    """Check whether auth-related cookies are present."""
    cookie_names = {c.name for c in cookies.jar}
    return bool(cookie_names & AUTH_COOKIE_NAMES)


def check_cookies_valid(cookies: httpx.Cookies) -> Tuple[bool, str]:
    """Validate login state by calling the growthuserinfo endpoint."""
    headers = dict(JSON_HEADERS)
    headers["Origin"] = "https://m.dianping.com"
    headers["Referer"] = DP_HOME_URL

    try:
        with httpx.Client(
            cookies=cookies,
            headers=headers,
            follow_redirects=True,
            timeout=10,
            http2=True,
        ) as client:
            resp = client.post(GROWTH_USER_INFO_URL, json={})
            if "verify.meituan.com" in str(resp.url):
                return False, "触发大众点评验证页"

            data = resp.json()
            user = data.get("result", {})
            if data.get("code") == 200 and user.get("userId"):
                nickname = user.get("userNickName") or user.get("userId")
                return True, f"已登录：{nickname}"
            return False, data.get("msg") or "登录态无效"
    except Exception as e:
        return False, f"请求失败：{e}"
