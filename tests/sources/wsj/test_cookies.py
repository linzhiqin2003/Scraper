"""Tests for WSJ cookie validation."""

import httpx

from web_scraper.sources.wsj.cookies import (
    _interpret_validation_response,
    validate_cookies,
)


def _cookies(*names: str) -> httpx.Cookies:
    cookies = httpx.Cookies()
    for name in names:
        cookies.set(name, "value", domain=".wsj.com", path="/")
    return cookies


def test_validate_cookies_accepts_current_sso_cookie_names() -> None:
    assert validate_cookies(_cookies("connect.sid", "sso")) is True


def test_interpret_validation_response_accepts_auth_cookies_without_body_markers() -> None:
    cookies = _cookies("connect.sid", "csrf")
    is_valid, message = _interpret_validation_response(200, "<html>home</html>", cookies)

    assert is_valid is True
    assert message == "Cookies loaded (auth cookies present)"


def test_interpret_validation_response_rejects_missing_auth_markers() -> None:
    cookies = _cookies("other_cookie")
    is_valid, message = _interpret_validation_response(200, "<html>home</html>", cookies)

    assert is_valid is False
    assert message == "Cookies may be expired (no login detected)"
