"""Tests for Ctrip cookie handling."""

import tempfile
from pathlib import Path

import httpx

from web_scraper.sources.ctrip.cookies import (
    get_cookie_dict,
    get_guid,
    get_username_from_cookie,
    load_playwright_cookies,
    parse_netscape_cookies,
    validate_cookies,
)


SAMPLE_COOKIES = """\
# Netscape HTTP Cookie File
.ctrip.com\tTRUE\t/\tFALSE\t0\tcticket\tabc123
.ctrip.com\tTRUE\t/\tFALSE\t0\tlogin_uid\tuser456
.ctrip.com\tTRUE\t/\tFALSE\t0\t_udl\tudl789
.ctrip.com\tTRUE\t/\tFALSE\t0\tGUID\tguid-001
"""


def _write_cookies(content: str) -> Path:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8")
    f.write(content)
    f.close()
    return Path(f.name)


def test_parse_netscape_cookies() -> None:
    path = _write_cookies(SAMPLE_COOKIES)
    cookies = parse_netscape_cookies(path)
    d = get_cookie_dict(cookies)
    assert d["cticket"] == "abc123"
    assert d["login_uid"] == "user456"
    assert d["_udl"] == "udl789"
    assert d["GUID"] == "guid-001"


def test_parse_skips_comments_and_empty() -> None:
    content = "# comment\n\n.ctrip.com\tTRUE\t/\tFALSE\t0\tkey\tval\n"
    path = _write_cookies(content)
    cookies = parse_netscape_cookies(path)
    d = get_cookie_dict(cookies)
    assert d == {"key": "val"}


def test_parse_skips_short_lines() -> None:
    content = "too\tfew\tfields\n.ctrip.com\tTRUE\t/\tFALSE\t0\tname\tvalue\n"
    path = _write_cookies(content)
    cookies = parse_netscape_cookies(path)
    assert len(get_cookie_dict(cookies)) == 1


def test_validate_cookies_valid() -> None:
    path = _write_cookies(SAMPLE_COOKIES)
    cookies = parse_netscape_cookies(path)
    assert validate_cookies(cookies) is True


def test_validate_cookies_missing_key() -> None:
    content = ".ctrip.com\tTRUE\t/\tFALSE\t0\tcticket\tabc\n"
    path = _write_cookies(content)
    cookies = parse_netscape_cookies(path)
    assert validate_cookies(cookies) is False


def test_get_guid() -> None:
    path = _write_cookies(SAMPLE_COOKIES)
    cookies = parse_netscape_cookies(path)
    assert get_guid(cookies) == "guid-001"


def test_get_guid_missing() -> None:
    content = ".ctrip.com\tTRUE\t/\tFALSE\t0\tother\tval\n"
    path = _write_cookies(content)
    cookies = parse_netscape_cookies(path)
    assert get_guid(cookies) == ""


def test_get_username_from_cookie() -> None:
    import urllib.parse

    raw = urllib.parse.quote("UserName=测试用户&Grade=3&Foo=bar")
    content = f".ctrip.com\tTRUE\t/\tFALSE\t0\tAHeadUserInfo\t{raw}\n"
    path = _write_cookies(content)
    cookies = parse_netscape_cookies(path)
    assert get_username_from_cookie(cookies) == "测试用户"


def test_get_username_missing() -> None:
    cookies = httpx.Cookies()
    assert get_username_from_cookie(cookies) == ""


def test_load_playwright_cookies() -> None:
    path = _write_cookies(SAMPLE_COOKIES)
    pw = load_playwright_cookies(path)
    assert len(pw) == 4
    names = {c["name"] for c in pw}
    assert "cticket" in names
    assert "GUID" in names
    # Check structure
    first = pw[0]
    assert "name" in first
    assert "value" in first
    assert "domain" in first
    assert "sameSite" in first


def test_load_playwright_cookies_missing_file() -> None:
    result = load_playwright_cookies(Path("/nonexistent/path.txt"))
    assert result == []
