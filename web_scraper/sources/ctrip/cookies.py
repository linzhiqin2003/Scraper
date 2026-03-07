"""Cookie handling for Ctrip authentication."""
import urllib.parse
from pathlib import Path
from typing import Dict, Tuple

import httpx

from ...core.browser import get_data_dir
from .config import SOURCE_NAME, AUTH_COOKIES


def get_cookies_path() -> Path:
    """Get default cookies.txt path for Ctrip."""
    return get_data_dir(SOURCE_NAME) / "cookies.txt"


def parse_netscape_cookies(cookies_file: Path) -> httpx.Cookies:
    """
    Parse Netscape cookies.txt format into httpx.Cookies.

    Format: domain  flag  path  secure  expiration  name  value
    Lines starting with # are comments.
    """
    cookies = httpx.Cookies()

    if not cookies_file.exists():
        raise FileNotFoundError(f"Cookies 文件不存在: {cookies_file}")

    with open(cookies_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 7:
                continue
            domain, _, path, _, _, name, value = parts[:7]
            cookies.set(name, value, domain=domain, path=path)

    return cookies


def load_cookies(cookies_path: Path | None = None) -> httpx.Cookies:
    """Load cookies, defaulting to ~/.web_scraper/ctrip/cookies.txt."""
    if cookies_path is None:
        cookies_path = get_cookies_path()
    return parse_netscape_cookies(cookies_path)


def get_cookie_dict(cookies: httpx.Cookies) -> Dict[str, str]:
    """Convert httpx.Cookies to plain dict."""
    return {c.name: c.value for c in cookies.jar}


def get_guid(cookies: httpx.Cookies) -> str:
    """Extract GUID from cookies for SOA2 request params."""
    cookie_dict = get_cookie_dict(cookies)
    return cookie_dict.get("GUID", "")


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
        # Format: UserName=袁科&Grade=10&...
        params = dict(p.split("=", 1) for p in decoded.split("&") if "=" in p)
        return params.get("UserName", "")
    except Exception:
        return ""


def load_playwright_cookies(cookies_path: Path | None = None) -> list[dict]:
    """Parse Netscape cookies.txt into Playwright-compatible cookie dicts.

    Playwright format: {name, value, domain, path, expires, httpOnly, secure, sameSite}
    """
    path = cookies_path or get_cookies_path()
    if not path or not path.exists():
        return []

    result: list[dict] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 7:
                continue
            domain, _, cookie_path, secure_str, expiry_str, name, value = parts[:7]
            try:
                expires = float(expiry_str) if expiry_str and expiry_str != "0" else -1
            except ValueError:
                expires = -1
            # Playwright requires domain without leading dot for exact match,
            # but .ctrip.com (with dot) works for subdomain matching
            result.append({
                "name": name,
                "value": value,
                "domain": domain,
                "path": cookie_path,
                "expires": expires,
                "httpOnly": False,
                "secure": secure_str.upper() == "TRUE",
                "sameSite": "Lax",
            })
    return result


def check_cookies_valid(cookies: httpx.Cookies) -> Tuple[bool, str]:
    """
    Verify cookies by calling getMemberSummaryInfo.

    Returns (is_valid, message).
    """
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
