"""Cookie handling for Ctrip authentication."""
import urllib.parse
from pathlib import Path
from typing import Dict, Tuple

import httpx

from ...core.cookies import (
    get_cookies_path as _get_cookies_path,
    load_cookies_httpx,
    load_cookies_playwright as _load_pw,
)
from .config import SOURCE_NAME, AUTH_COOKIES


def get_cookies_path() -> Path:
    """Get default cookies.txt path for Ctrip."""
    return _get_cookies_path(SOURCE_NAME)


def load_cookies(cookies_path: Path | None = None) -> httpx.Cookies:
    """Load cookies, defaulting to ~/.web_scraper/ctrip/cookies.txt."""
    return load_cookies_httpx(SOURCE_NAME, cookies_path)


def load_playwright_cookies(cookies_path: Path | None = None) -> list[dict]:
    """Parse Netscape cookies.txt into Playwright-compatible cookie dicts."""
    return _load_pw(SOURCE_NAME, cookies_path)


def get_cookie_dict(cookies: httpx.Cookies) -> Dict[str, str]:
    """Convert httpx.Cookies to plain dict."""
    return {c.name: c.value for c in cookies.jar}


def get_guid(cookies: httpx.Cookies) -> str:
    """Extract GUID from cookies for SOA2 request params."""
    return get_cookie_dict(cookies).get("GUID", "")


def validate_cookies(cookies: httpx.Cookies) -> bool:
    """Check if cookies contain required Ctrip auth tokens."""
    cookie_names = {c.name for c in cookies.jar}
    return all(name in cookie_names for name in AUTH_COOKIES)


def get_username_from_cookie(cookies: httpx.Cookies) -> str:
    """Extract username from AHeadUserInfo cookie (URL-encoded JSON)."""
    cookie_dict = get_cookie_dict(cookies)
    raw = cookie_dict.get("AHeadUserInfo", "")
    if not raw:
        return ""
    try:
        decoded = urllib.parse.unquote(raw)
        params = dict(p.split("=", 1) for p in decoded.split("&") if "=" in p)
        return params.get("UserName", "")
    except Exception:
        return ""


def check_cookies_valid(cookies: httpx.Cookies) -> Tuple[bool, str]:
    """Verify cookies by calling getMemberSummaryInfo."""
    from .config import MEMBER_SUMMARY_URL, DEFAULT_HEADERS, soa2_head

    guid = get_guid(cookies)
    params = {"_fxpcqlniredt": guid} if guid else {}
    payload = {"channel": "Online", "clientVersion": "99.99", "head": soa2_head(guid)}

    try:
        with httpx.Client(cookies=cookies, follow_redirects=True, timeout=10) as client:
            resp = client.post(
                MEMBER_SUMMARY_URL,
                json=payload,
                headers=DEFAULT_HEADERS,
                params=params,
            )
            data = resp.json()
            ack = data.get("ResponseStatus", {}).get("Ack", "")
            if ack == "Success" and data.get("userName"):
                return True, f"已登录：{data['userName']}"
            errors = data.get("ResponseStatus", {}).get("Errors", [])
            msg = errors[0].get("Message", "未知错误") if errors else "登录状态验证失败"
            return False, msg
    except Exception as e:
        return False, f"请求失败：{e}"
