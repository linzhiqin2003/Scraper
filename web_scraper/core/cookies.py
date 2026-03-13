"""Unified cookie handling for all sources.

All sources use Netscape-format cookies.txt exported from browser extensions
(EditThisCookie, Cookie-Editor, etc.). This module provides shared parsing,
loading, importing, and format conversion utilities.

Usage:
    from web_scraper.core.cookies import load_cookies, import_cookies

    # Load as plain dict (for curl-cffi / HttpClient)
    cookies = load_cookies("x")  # from ~/.web_scraper/x/cookies.txt

    # Load as httpx.Cookies (for httpx clients, preserves domain/path)
    hx_cookies = load_cookies_httpx("wsj")

    # Load as Playwright format (for browser automation)
    pw_cookies = load_cookies_playwright("jd")

    # Import from user-provided file
    import_cookies("/path/to/exported.txt", "x")
"""
import shutil
from pathlib import Path
from typing import Optional

from .browser import get_data_dir


def get_cookies_path(source: str) -> Path:
    """Get the standard cookies.txt path for a source.

    Args:
        source: Source name (e.g. "x", "wsj", "jd").

    Returns:
        Path to ~/.web_scraper/{source}/cookies.txt
    """
    return get_data_dir(source) / "cookies.txt"


def parse_netscape_cookies(cookies_file: Path) -> list[dict]:
    """Parse Netscape-format cookies.txt into a list of cookie dicts.

    Each dict contains: name, value, domain, path, secure, expires.
    This is the canonical parsed representation from which all other
    formats (dict, httpx, playwright) are derived.

    Args:
        cookies_file: Path to Netscape cookies.txt file.

    Returns:
        List of cookie dicts.

    Raises:
        FileNotFoundError: If file doesn't exist.
    """
    if not cookies_file.exists():
        raise FileNotFoundError(f"Cookies file not found: {cookies_file}")

    cookies = []
    for line in cookies_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue

        domain, _, path, secure, expires, name, value = parts[:7]
        try:
            exp = int(expires)
        except ValueError:
            exp = 0

        cookies.append({
            "name": name,
            "value": value,
            "domain": domain,
            "path": path,
            "secure": secure.upper() == "TRUE",
            "expires": exp,
        })

    return cookies


# ── Output formats ──────────────────────────────────────────────────────────


def to_dict(cookies: list[dict]) -> dict[str, str]:
    """Convert parsed cookies to a plain {name: value} dict.

    Suitable for curl-cffi, HttpClient, and simple header construction.
    Note: loses domain/path info; last-wins on duplicate names.
    """
    return {c["name"]: c["value"] for c in cookies}


def to_httpx(cookies: list[dict]) -> "httpx.Cookies":
    """Convert parsed cookies to httpx.Cookies (preserves domain/path)."""
    import httpx
    result = httpx.Cookies()
    for c in cookies:
        result.set(c["name"], c["value"], domain=c["domain"], path=c["path"])
    return result


def to_playwright(cookies: list[dict]) -> list[dict]:
    """Convert parsed cookies to Playwright-compatible cookie dicts."""
    result = []
    for c in cookies:
        pw = {
            "name": c["name"],
            "value": c["value"],
            "domain": c["domain"],
            "path": c["path"] or "/",
            "secure": c["secure"],
            "httpOnly": False,
        }
        if c["expires"] > 0:
            pw["expires"] = c["expires"]
        result.append(pw)
    return result


def to_header_string(cookies: list[dict]) -> str:
    """Convert parsed cookies to a raw 'name=value; ...' header string."""
    return "; ".join(f'{c["name"]}={c["value"]}' for c in cookies)


# ── High-level convenience functions ────────────────────────────────────────


def load_cookies(
    source: str,
    cookies_path: Optional[Path] = None,
) -> dict[str, str]:
    """Load cookies as a plain dict. Returns empty dict if file doesn't exist.

    Args:
        source: Source name for default path lookup.
        cookies_path: Override path (skips default lookup).

    Returns:
        Dict of {cookie_name: cookie_value}.
    """
    path = cookies_path or get_cookies_path(source)
    if not path.exists():
        return {}
    return to_dict(parse_netscape_cookies(path))


def load_cookies_httpx(
    source: str,
    cookies_path: Optional[Path] = None,
) -> "httpx.Cookies":
    """Load cookies as httpx.Cookies. Returns empty Cookies if file doesn't exist.

    Args:
        source: Source name for default path lookup.
        cookies_path: Override path.

    Returns:
        httpx.Cookies instance.
    """
    import httpx
    path = cookies_path or get_cookies_path(source)
    if not path.exists():
        return httpx.Cookies()
    return to_httpx(parse_netscape_cookies(path))


def load_cookies_playwright(
    source: str,
    cookies_path: Optional[Path] = None,
) -> list[dict]:
    """Load cookies as Playwright-format dicts. Returns empty list if file doesn't exist.

    Args:
        source: Source name for default path lookup.
        cookies_path: Override path.

    Returns:
        List of Playwright cookie dicts.
    """
    path = cookies_path or get_cookies_path(source)
    if not path.exists():
        return []
    return to_playwright(parse_netscape_cookies(path))


def import_cookies(
    source_file: str | Path,
    source: str,
) -> Path:
    """Import a cookies.txt file to the standard location for a source.

    Args:
        source_file: Path to the user-provided cookies.txt.
        source: Source name (determines destination directory).

    Returns:
        Path to the saved cookies file.

    Raises:
        FileNotFoundError: If source_file doesn't exist.
    """
    src = Path(source_file)
    if not src.exists():
        raise FileNotFoundError(f"File not found: {src}")

    dest = get_cookies_path(source)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return dest
