"""Anti-detection: block detection, session health monitoring, and recovery.

Detects various forms of blocking (CAPTCHA, rate limiting, IP bans, session expiry)
from both page-level and API-level signals, with recovery recommendations.
"""

import logging
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

from playwright.sync_api import Page

logger = logging.getLogger(__name__)


class BlockType(Enum):
    """Types of blocking detected."""

    NONE = "none"
    CAPTCHA = "captcha"
    RATE_LIMITED = "rate_limited"
    IP_BANNED = "ip_banned"
    SESSION_EXPIRED = "session_expired"
    UNKNOWN = "unknown"


@dataclass
class BlockStatus:
    """Detection result with recovery suggestions."""

    block_type: BlockType = BlockType.NONE
    message: str = ""
    should_rotate_proxy: bool = False
    should_wait: bool = False
    wait_seconds: float = 0.0
    should_notify_user: bool = False

    @property
    def is_blocked(self) -> bool:
        return self.block_type != BlockType.NONE


# Page-level detection patterns
_CAPTCHA_URL_PATTERNS = ("unhuman", "captcha", "/account/unhuman")
_CAPTCHA_TEXT_PATTERNS = ("验证码", "请完成验证", "安全验证")
_RATE_LIMIT_TEXT_PATTERNS = ("操作太频繁", "请求太多", "请稍后再试", "频率过高")
_BAN_TEXT_PATTERNS = ("访问受限", "IP 被封", "禁止访问", "403 Forbidden")
_LOGIN_URL_PATTERNS = ("/signin", "/signup", "passport.zhihu.com")


class BlockDetector:
    """Detects page-level and API-level blocks.

    Usage:
        detector = BlockDetector()

        # Page-level check
        status = detector.check_page(page)
        if status.is_blocked:
            handle_block(status)

        # API-level check
        status = detector.check_api_response(429, {"error": {"message": "rate limit"}})
    """

    def check_page(self, page: Page) -> BlockStatus:
        """Check a Playwright page for block signals.

        Inspects URL and page content for captcha, rate limits, bans, and login redirects.
        """
        url = page.url

        # 1. CAPTCHA detection (URL)
        for pattern in _CAPTCHA_URL_PATTERNS:
            if pattern in url:
                return BlockStatus(
                    block_type=BlockType.CAPTCHA,
                    message=f"CAPTCHA detected in URL: {url}",
                    should_notify_user=True,
                    should_wait=True,
                    wait_seconds=0,  # user must solve manually
                )

        # 2. Session expired (login redirect)
        for pattern in _LOGIN_URL_PATTERNS:
            if pattern in url:
                return BlockStatus(
                    block_type=BlockType.SESSION_EXPIRED,
                    message="Redirected to login page, session expired",
                    should_notify_user=True,
                )

        # 3. Text-based detection on page body
        try:
            body_text = page.evaluate("() => document.body?.innerText?.substring(0, 2000) || ''")
        except Exception:
            body_text = ""

        for pattern in _CAPTCHA_TEXT_PATTERNS:
            if pattern in body_text:
                return BlockStatus(
                    block_type=BlockType.CAPTCHA,
                    message=f"CAPTCHA text detected: {pattern}",
                    should_notify_user=True,
                    should_wait=True,
                )

        for pattern in _RATE_LIMIT_TEXT_PATTERNS:
            if pattern in body_text:
                return BlockStatus(
                    block_type=BlockType.RATE_LIMITED,
                    message=f"Rate limit text detected: {pattern}",
                    should_rotate_proxy=True,
                    should_wait=True,
                    wait_seconds=30.0,
                )

        for pattern in _BAN_TEXT_PATTERNS:
            if pattern in body_text:
                return BlockStatus(
                    block_type=BlockType.IP_BANNED,
                    message=f"IP ban text detected: {pattern}",
                    should_rotate_proxy=True,
                    should_wait=True,
                    wait_seconds=120.0,
                )

        return BlockStatus()

    def check_api_response(
        self,
        status_code: int,
        body: Optional[Dict[str, Any]] = None,
    ) -> BlockStatus:
        """Check an API response for block signals.

        Args:
            status_code: HTTP status code.
            body: Parsed JSON response body.
        """
        if status_code == 429:
            return BlockStatus(
                block_type=BlockType.RATE_LIMITED,
                message="HTTP 429 Too Many Requests",
                should_rotate_proxy=True,
                should_wait=True,
                wait_seconds=30.0,
            )

        if status_code == 403:
            error_msg = ""
            if body and isinstance(body, dict):
                error_msg = str(body.get("error", {}).get("message", ""))

            if "banned" in error_msg.lower() or "forbidden" in error_msg.lower():
                return BlockStatus(
                    block_type=BlockType.IP_BANNED,
                    message=f"HTTP 403 Forbidden: {error_msg}",
                    should_rotate_proxy=True,
                    should_wait=True,
                    wait_seconds=120.0,
                )

            return BlockStatus(
                block_type=BlockType.IP_BANNED,
                message="HTTP 403 Forbidden",
                should_rotate_proxy=True,
                should_wait=True,
                wait_seconds=60.0,
            )

        if status_code == 401:
            return BlockStatus(
                block_type=BlockType.SESSION_EXPIRED,
                message="HTTP 401 Unauthorized",
                should_notify_user=True,
            )

        # Check body for error patterns
        if body and isinstance(body, dict):
            error = body.get("error", {})
            if isinstance(error, dict):
                code = error.get("code", 0)
                msg = str(error.get("message", ""))
                if code == 40354 or "UnAuthorized" in msg:
                    return BlockStatus(
                        block_type=BlockType.SESSION_EXPIRED,
                        message=f"API auth error: {msg}",
                        should_notify_user=True,
                    )

        return BlockStatus()


class SessionHealthMonitor:
    """Monitors session cookie health.

    Checks if the d_c0 cookie (Zhihu's session token) is present and valid.
    """

    def __init__(self) -> None:
        self._last_check: float = 0.0
        self._is_healthy: bool = False

    def check(self, page: Page) -> bool:
        """Check if the d_c0 session cookie is present.

        Args:
            page: Playwright page connected to Zhihu.

        Returns:
            True if session appears healthy.
        """
        try:
            cookies = page.context.cookies(["https://www.zhihu.com"])
            d_c0 = None
            for cookie in cookies:
                if cookie.get("name") == "d_c0":
                    d_c0 = cookie
                    break

            if not d_c0:
                logger.warning("d_c0 cookie not found, session may be expired")
                self._is_healthy = False
                return False

            # Check expiry
            expires = d_c0.get("expires", -1)
            if isinstance(expires, (int, float)) and expires > 0:
                if expires < time.time():
                    logger.warning("d_c0 cookie expired")
                    self._is_healthy = False
                    return False

            self._is_healthy = True
            self._last_check = time.monotonic()
            return True

        except Exception as e:
            logger.debug("Session health check failed: %s", e)
            self._is_healthy = False
            return False

    def get_d_c0(self, page: Page) -> Optional[str]:
        """Extract the d_c0 cookie value from the page context.

        Args:
            page: Playwright page connected to Zhihu.

        Returns:
            d_c0 cookie value or None.
        """
        try:
            cookies = page.context.cookies(["https://www.zhihu.com"])
            for cookie in cookies:
                if cookie.get("name") == "d_c0":
                    return cookie.get("value")
        except Exception:
            pass
        return None

    @property
    def is_healthy(self) -> bool:
        return self._is_healthy
