"""Browser connection management for Zhihu scraper.

Zhihu has aggressive anti-bot detection that blocks Playwright-launched browsers.
The primary strategy is connecting to the user's real Chrome via CDP (Chrome DevTools Protocol).
Fallback: launch Playwright with storage_state (may get blocked).
"""

import logging
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    sync_playwright,
    TimeoutError as PlaywrightTimeout,
)

from ...core.browser import STEALTH_SCRIPT, get_state_path
from .config import DEFAULT_CDP_PORT, SOURCE_NAME, Timeouts

logger = logging.getLogger(__name__)


def find_chrome_path() -> Optional[str]:
    """Find Chrome executable path on the system."""
    import shutil

    candidates = [
        # macOS
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        # Linux
        "google-chrome",
        "google-chrome-stable",
        "chromium-browser",
        "chromium",
    ]
    for candidate in candidates:
        if "/" in candidate:
            if Path(candidate).exists():
                return candidate
        else:
            found = shutil.which(candidate)
            if found:
                return found
    return None


def is_cdp_available(port: int = DEFAULT_CDP_PORT) -> bool:
    """Check if Chrome DevTools Protocol is available on the given port."""
    import httpx

    try:
        resp = httpx.get(f"http://127.0.0.1:{port}/json/version", timeout=2.0)
        return resp.status_code == 200
    except Exception:
        return False


def launch_chrome_with_cdp(port: int = DEFAULT_CDP_PORT) -> Optional[subprocess.Popen]:
    """Launch Chrome with remote debugging enabled.

    Returns the subprocess handle, or None if Chrome couldn't be found.
    """
    chrome_path = find_chrome_path()
    if not chrome_path:
        return None

    proc = subprocess.Popen(
        [
            chrome_path,
            f"--remote-debugging-port={port}",
            "--no-first-run",
            "--no-default-browser-check",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Wait for CDP to become available
    for _ in range(20):
        time.sleep(0.5)
        if is_cdp_available(port):
            return proc

    proc.terminate()
    return None


@contextmanager
def open_zhihu_page(
    *,
    cdp_port: int = DEFAULT_CDP_PORT,
    headless: bool = False,
    auto_launch_chrome: bool = True,
) -> Iterator[Page]:
    """Open a Zhihu page with the best available browser strategy.

    Strategy order:
    1. Connect to existing Chrome via CDP (most reliable, avoids all detection)
    2. Auto-launch Chrome with CDP if not running
    3. Fallback: launch Playwright with storage_state (may get blocked)

    Args:
        cdp_port: CDP port to connect to.
        headless: Headless mode for fallback Playwright launch.
        auto_launch_chrome: Whether to auto-launch Chrome if CDP is not available.

    Yields:
        Playwright Page instance connected to Zhihu.
    """
    chrome_proc = None

    with sync_playwright() as pw:
        # Strategy 1: Connect to existing Chrome via CDP
        if is_cdp_available(cdp_port):
            logger.info("Connecting to existing Chrome via CDP on port %d", cdp_port)
            yield from _connect_cdp(pw, cdp_port)
            return

        # Strategy 2: Auto-launch Chrome with CDP
        if auto_launch_chrome:
            logger.info("Launching Chrome with CDP on port %d", cdp_port)
            chrome_proc = launch_chrome_with_cdp(cdp_port)
            if chrome_proc and is_cdp_available(cdp_port):
                try:
                    yield from _connect_cdp(pw, cdp_port)
                    return
                finally:
                    chrome_proc.terminate()
                    chrome_proc.wait(timeout=5)

        # Strategy 3: Fallback to Playwright launch with storage_state
        logger.warning("CDP not available, falling back to Playwright launch (may get blocked)")
        yield from _launch_playwright(pw, headless)


def _connect_cdp(pw: Playwright, port: int) -> Iterator[Page]:
    """Connect to Chrome via CDP and yield a new page."""
    browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
    try:
        # Use existing context if available, otherwise create new
        if browser.contexts:
            context = browser.contexts[0]
        else:
            context = browser.new_context(
                viewport={"width": 1440, "height": 1024},
                locale="zh-CN",
            )

        page = context.new_page()
        try:
            yield page
        finally:
            page.close()
    finally:
        browser.close()


def _launch_playwright(pw: Playwright, headless: bool) -> Iterator[Page]:
    """Launch Playwright browser with storage_state fallback."""
    state_file = get_state_path(SOURCE_NAME)
    storage_state = str(state_file) if state_file.exists() else None

    launch_args = [
        "--disable-gpu",
        "--disable-blink-features=AutomationControlled",
    ]

    # Try Chrome first, fallback to Chromium
    browser = None
    for channel in ("chrome", None):
        try:
            browser = pw.chromium.launch(
                headless=headless,
                channel=channel,
                args=launch_args,
            )
            break
        except Exception:
            continue

    if browser is None:
        raise RuntimeError("Failed to launch browser. Run: playwright install chromium")

    context_opts = {
        "viewport": {"width": 1440, "height": 1024},
        "locale": "zh-CN",
    }
    if storage_state:
        context_opts["storage_state"] = storage_state

    context = browser.new_context(**context_opts)
    context.add_init_script(STEALTH_SCRIPT)
    page = context.new_page()

    try:
        yield page
    finally:
        try:
            context.close()
        finally:
            browser.close()


def wait_for_unblock(page: Page, timeout_ms: int = Timeouts.LOGIN_MANUAL) -> bool:
    """If page is blocked (unhuman/captcha), wait for user to solve it.

    Uses BlockDetector for comprehensive detection, with URL fallback.

    Returns True if unblocked, False if timed out.
    """
    from .anti_detect import BlockDetector, BlockType

    detector = BlockDetector()
    status = detector.check_page(page)

    if not status.is_blocked:
        # Legacy URL check as extra safety
        url = page.url
        if "unhuman" not in url and "captcha" not in url:
            return True

    if status.block_type not in (BlockType.CAPTCHA, BlockType.NONE):
        # For non-CAPTCHA blocks, we can't wait for user interaction
        logger.warning("Non-CAPTCHA block detected: %s", status.message)
        return False

    print(
        "[知乎] 检测到安全验证，请在浏览器中完成验证...",
        file=sys.stderr,
    )

    start = time.time()
    while time.time() - start < timeout_ms / 1000:
        page.wait_for_timeout(1500)
        new_status = detector.check_page(page)
        if not new_status.is_blocked:
            return True

    return False
