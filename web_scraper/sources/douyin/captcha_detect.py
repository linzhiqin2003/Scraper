"""Douyin CAPTCHA detection and manual resolution support.

Detects ByteDance slider CAPTCHA (verify.zijieapi.com) via:
  1. DOM selectors — CAPTCHA overlay elements
  2. Page text patterns — "验证码", "滑动滑块", etc.
  3. URL interception — requests to verify.zijieapi.com

When detected:
  - Headless mode: raises CaptchaError with instructions to use --no-headless
  - Non-headless mode: prints prompt and polls until CAPTCHA disappears or timeout
"""

from __future__ import annotations

import logging
from typing import Optional

from patchright.sync_api import Page

from ...core.exceptions import CaptchaError
from .config import (
    CAPTCHA_DOM_SELECTORS,
    CAPTCHA_TEXT_PATTERNS,
    Timeouts,
)

logger = logging.getLogger(__name__)

# JS that checks all CAPTCHA selectors at once (returns first match or null)
_DETECT_CAPTCHA_JS = """
() => {{
    const selectors = {selectors_json};
    for (const sel of selectors) {{
        try {{
            const el = document.querySelector(sel);
            if (el && el.offsetParent !== null) return sel;
        }} catch (e) {{}}
    }}
    return null;
}}
"""

# JS to check page text for CAPTCHA keywords
_DETECT_CAPTCHA_TEXT_JS = """
() => {{
    const text = document.body ? document.body.innerText : '';
    const patterns = {patterns_json};
    for (const p of patterns) {{
        if (text.includes(p)) return p;
    }}
    return null;
}}
"""


def _build_detect_js() -> str:
    """Build the JS detection snippet with current config selectors."""
    import json
    return _DETECT_CAPTCHA_JS.format(selectors_json=json.dumps(CAPTCHA_DOM_SELECTORS))


def _build_text_detect_js() -> str:
    import json
    return _DETECT_CAPTCHA_TEXT_JS.format(patterns_json=json.dumps(CAPTCHA_TEXT_PATTERNS))


def check_captcha(page: Page) -> Optional[str]:
    """Check if a CAPTCHA is currently visible on the page.

    Returns a description string if detected, None otherwise.
    """
    # Check DOM selectors
    try:
        matched_selector = page.evaluate(_build_detect_js())
        if matched_selector:
            return f"CAPTCHA element detected: {matched_selector}"
    except Exception:
        pass

    # Check text patterns
    try:
        matched_text = page.evaluate(_build_text_detect_js())
        if matched_text:
            return f"CAPTCHA text detected: '{matched_text}'"
    except Exception:
        pass

    return None


def handle_captcha(
    page: Page,
    headless: bool,
    timeout_ms: int = Timeouts.CAPTCHA_MANUAL,
    check_interval_ms: int = Timeouts.CAPTCHA_CHECK_INTERVAL,
) -> bool:
    """Detect and handle CAPTCHA on the current page.

    Args:
        page: Playwright page instance.
        headless: Whether browser is running headless.
        timeout_ms: Max time to wait for manual solve (ms).
        check_interval_ms: Polling interval (ms).

    Returns:
        True if CAPTCHA was detected and resolved.
        False if no CAPTCHA was detected.

    Raises:
        CaptchaError: If CAPTCHA detected in headless mode, or manual solve timed out.
    """
    detection = check_captcha(page)
    if not detection:
        return False

    logger.warning("CAPTCHA detected: %s", detection)

    if headless:
        raise CaptchaError(
            f"Slider CAPTCHA detected ({detection}). "
            "Run with --no-headless flag to complete verification manually."
        )

    # Non-headless: wait for user to solve manually
    logger.info("Waiting for manual CAPTCHA resolution (timeout: %ds)...", timeout_ms // 1000)
    elapsed = 0
    while elapsed < timeout_ms:
        page.wait_for_timeout(check_interval_ms)
        elapsed += check_interval_ms

        if not check_captcha(page):
            logger.info("CAPTCHA resolved after ~%ds.", elapsed // 1000)
            # Small extra wait for page to settle after CAPTCHA
            page.wait_for_timeout(1000)
            return True

    raise CaptchaError(
        f"Manual CAPTCHA resolution timed out after {timeout_ms // 1000}s. "
        "Please try again."
    )
