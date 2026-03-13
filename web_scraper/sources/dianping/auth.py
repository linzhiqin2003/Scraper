"""Browser session helpers for Dianping search flows."""

import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from patchright.sync_api import Page, TimeoutError as PlaywrightTimeout

from ...core.browser import create_browser, get_state_path
from .config import (
    SOURCE_NAME,
    DEFAULT_CITY_ID,
    LOGIN_TIMEOUT_SECONDS,
    build_search_url,
)
from .cookies import get_cookies_path, load_playwright_cookies

RESULT_SELECTOR = ".shop-all-list li .tit h4"


class LoginStatus(Enum):
    """Login/session status for Dianping browser flows."""

    LOGGED_IN = "logged_in"
    LOGGED_OUT = "logged_out"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"


@dataclass
class AuthStatus:
    """Status payload for Dianping browser session checks."""

    status: LoginStatus
    checked_at: Optional[datetime] = None
    message: Optional[str] = None
    current_url: Optional[str] = None


def _is_verify_page(page: Page) -> bool:
    """Return True when current page is a Meituan verification page."""
    try:
        host = (urlparse(page.url).hostname or "").lower()
        if "verify.meituan.com" in host:
            return True
        return page.query_selector("text=验证") is not None
    except Exception:
        return False


def _looks_like_results_page(page: Page) -> bool:
    """Check whether search results are visible."""
    try:
        node = page.query_selector(RESULT_SELECTOR)
        return node is not None and node.is_visible()
    except Exception:
        return False


def _save_storage_state(page: Page) -> Path:
    """Persist browser storage state for later searches."""
    state_file = get_state_path(SOURCE_NAME)
    state_file.parent.mkdir(parents=True, exist_ok=True)
    page.context.storage_state(path=str(state_file))
    return state_file


def _hydrate_context_from_cookies(page: Page) -> None:
    """Seed browser context with imported cookies when no saved state exists."""
    cookies_path = get_cookies_path()
    if not cookies_path.exists():
        return
    cookies = load_playwright_cookies(cookies_path)
    if cookies:
        page.context.add_cookies(cookies)


def interactive_login(
    *,
    headless: bool = False,
    timeout_seconds: int = LOGIN_TIMEOUT_SECONDS,
    query: str = "瑞幸",
    city_id: int = DEFAULT_CITY_ID,
    channel: int = 0,
) -> AuthStatus:
    """Open Dianping search page and save browser session after manual verification."""
    search_url = build_search_url(query=query, city_id=city_id, channel=channel, page=1)

    try:
        with create_browser(
            headless=headless,
            source=SOURCE_NAME,
            use_storage_state=False,
        ) as page:
            _hydrate_context_from_cookies(page)
            page.goto(search_url, wait_until="domcontentloaded", timeout=60000)

            start_time = time.time()
            while time.time() - start_time < timeout_seconds:
                if _looks_like_results_page(page):
                    _save_storage_state(page)
                    return AuthStatus(
                        status=LoginStatus.LOGGED_IN,
                        checked_at=datetime.now(),
                        message="浏览器会话已保存，可复用搜索态",
                        current_url=page.url,
                    )
                page.wait_for_timeout(1000)

            return AuthStatus(
                status=LoginStatus.BLOCKED if _is_verify_page(page) else LoginStatus.UNKNOWN,
                checked_at=datetime.now(),
                message="等待手动完成验证超时，未保存会话",
                current_url=page.url,
            )
    except PlaywrightTimeout:
        return AuthStatus(
            status=LoginStatus.UNKNOWN,
            checked_at=datetime.now(),
            message="打开大众点评页面超时",
            current_url=search_url,
        )
    except Exception as exc:
        return AuthStatus(
            status=LoginStatus.UNKNOWN,
            checked_at=datetime.now(),
            message=f"浏览器登录失败：{exc}",
            current_url=search_url,
        )


def check_saved_session(
    *,
    headless: bool = True,
    query: str = "瑞幸",
    city_id: int = DEFAULT_CITY_ID,
    channel: int = 0,
) -> AuthStatus:
    """Check whether saved browser state can still access the search page."""
    state_file = get_state_path(SOURCE_NAME)
    if not state_file.exists():
        return AuthStatus(
            status=LoginStatus.LOGGED_OUT,
            checked_at=datetime.now(),
            message="未找到浏览器会话，请运行 'scraper dianping login'",
            current_url=None,
        )

    search_url = build_search_url(query=query, city_id=city_id, channel=channel, page=1)
    try:
        with create_browser(
            headless=headless,
            source=SOURCE_NAME,
            use_storage_state=True,
        ) as page:
            page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(1500)

            if _looks_like_results_page(page):
                _save_storage_state(page)
                return AuthStatus(
                    status=LoginStatus.LOGGED_IN,
                    checked_at=datetime.now(),
                    message="浏览器会话有效，可直接访问搜索结果页",
                    current_url=page.url,
                )
            if _is_verify_page(page):
                return AuthStatus(
                    status=LoginStatus.BLOCKED,
                    checked_at=datetime.now(),
                    message="浏览器会话仍会触发验证，请重新运行 'scraper dianping login'",
                    current_url=page.url,
                )
            return AuthStatus(
                status=LoginStatus.UNKNOWN,
                checked_at=datetime.now(),
                message="无法确认浏览器会话状态",
                current_url=page.url,
            )
    except Exception as exc:
        return AuthStatus(
            status=LoginStatus.UNKNOWN,
            checked_at=datetime.now(),
            message=f"浏览器会话检查失败：{exc}",
            current_url=search_url,
        )


def clear_session() -> bool:
    """Clear saved browser state."""
    state_file = get_state_path(SOURCE_NAME)
    if state_file.exists():
        state_file.unlink()
        return True
    return False
