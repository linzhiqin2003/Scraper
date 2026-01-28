"""Unified browser management with Playwright."""

import asyncio
import json
import random
from contextlib import contextmanager, asynccontextmanager
from pathlib import Path
from typing import Iterator, Optional, AsyncIterator

from playwright.sync_api import sync_playwright, Browser, Page, Playwright
from playwright.async_api import (
    async_playwright,
    Browser as AsyncBrowser,
    BrowserContext as AsyncBrowserContext,
    Page as AsyncPage,
    Playwright as AsyncPlaywright,
)


# Default data directory
DEFAULT_DATA_DIR = Path.home() / ".web_scraper"

# User agents pool
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
]


def get_random_user_agent() -> str:
    """Get a random user agent string."""
    return random.choice(USER_AGENTS)


def get_data_dir(source: str) -> Path:
    """Get data directory for a specific source."""
    return DEFAULT_DATA_DIR / source


def get_cookies_path(source: str) -> Path:
    """Get cookies file path for a specific source."""
    return get_data_dir(source) / "cookies.json"


def get_state_path(source: str) -> Path:
    """Get state file path for a specific source."""
    return get_data_dir(source) / "browser_state.json"


# Anti-detection script (merged from both projects)
STEALTH_SCRIPT = """
// Hide webdriver property
Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined
});

// Override plugins to look like a real browser
Object.defineProperty(navigator, 'plugins', {
    get: () => [
        { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
        { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
        { name: 'Native Client', filename: 'internal-nacl-plugin' }
    ]
});

// Override languages
Object.defineProperty(navigator, 'languages', {
    get: () => ['en-US', 'en', 'zh-CN', 'zh']
});

// Override platform
Object.defineProperty(navigator, 'platform', {
    get: () => 'MacIntel'
});

// Hide automation indicators in chrome object
window.chrome = {
    runtime: {},
    loadTimes: function() {},
    csi: function() {},
    app: {}
};

// Override permissions query
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications' ?
        Promise.resolve({ state: Notification.permission }) :
        originalQuery(parameters)
);
"""


# ==================== Synchronous Browser Management ====================

@contextmanager
def create_browser(
    headless: bool = True,
    source: str = "default",
    use_chrome: bool = True,
) -> Iterator[Page]:
    """Create and manage browser lifecycle with Playwright (sync).

    Args:
        headless: Run browser in headless mode.
        source: Source name for data isolation.
        use_chrome: Use real Chrome browser (better anti-detection).

    Yields:
        Playwright Page instance.
    """
    with sync_playwright() as p:
        launch_args = [
            "--disable-gpu",
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-accelerated-2d-canvas",
            "--disable-infobars",
            "--window-size=1920,1080",
        ]

        browser = p.chromium.launch(
            headless=headless,
            channel="chrome" if use_chrome else None,
            args=launch_args,
        )

        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=get_random_user_agent(),
            locale="en-US",
            timezone_id="America/New_York",
            permissions=["geolocation"],
        )

        page = context.new_page()
        page.add_init_script(STEALTH_SCRIPT)

        try:
            yield page
        finally:
            browser.close()


def load_cookies_sync(page: Page, source: str) -> bool:
    """Load cookies from saved state file (sync).

    Args:
        page: Playwright Page instance.
        source: Source name for data isolation.

    Returns:
        True if cookies were loaded successfully.
    """
    state_file = get_state_path(source)
    if not state_file.exists():
        return False

    try:
        state = json.loads(state_file.read_text())
        cookies = state.get("cookies", [])

        if cookies:
            pw_cookies = []
            for c in cookies:
                pw_cookie = {
                    "name": c["name"],
                    "value": c["value"],
                    "domain": c.get("domain", ""),
                    "path": c.get("path", "/"),
                }
                if c.get("expires") and c["expires"] > 0:
                    pw_cookie["expires"] = c["expires"]
                if c.get("httpOnly"):
                    pw_cookie["httpOnly"] = c["httpOnly"]
                if c.get("secure"):
                    pw_cookie["secure"] = c["secure"]
                if c.get("sameSite"):
                    pw_cookie["sameSite"] = c["sameSite"]
                pw_cookies.append(pw_cookie)

            page.context.add_cookies(pw_cookies)

        # Load localStorage
        for origin in state.get("origins", []):
            for item in origin.get("localStorage", []):
                try:
                    page.evaluate(
                        "([key, value]) => localStorage.setItem(key, value)",
                        [item["name"], item["value"]]
                    )
                except Exception:
                    continue

        return True
    except Exception:
        return False


def save_cookies_sync(page: Page, source: str, base_url: str = "") -> None:
    """Save cookies and localStorage to state file (sync).

    Args:
        page: Playwright Page instance.
        source: Source name for data isolation.
        base_url: Base URL for localStorage origin.
    """
    data_dir = get_data_dir(source)
    data_dir.mkdir(parents=True, exist_ok=True)

    cookies = page.context.cookies()

    try:
        local_storage = page.evaluate("""
            () => {
                const items = {};
                for (let i = 0; i < localStorage.length; i++) {
                    const key = localStorage.key(i);
                    items[key] = localStorage.getItem(key);
                }
                return items;
            }
        """)
    except Exception:
        local_storage = {}

    state = {
        "cookies": [
            {
                "name": c["name"],
                "value": c["value"],
                "domain": c.get("domain", ""),
                "path": c.get("path", "/"),
                "expires": c.get("expires", -1),
                "httpOnly": c.get("httpOnly", False),
                "secure": c.get("secure", False),
                "sameSite": c.get("sameSite", "Lax"),
            }
            for c in cookies
        ],
        "origins": [
            {
                "origin": base_url,
                "localStorage": [
                    {"name": k, "value": v}
                    for k, v in local_storage.items()
                ]
            }
        ] if local_storage and base_url else []
    }

    state_file = get_state_path(source)
    state_file.write_text(json.dumps(state, indent=2))


# ==================== Asynchronous Browser Management ====================

class BrowserManager:
    """Async browser manager with cookie persistence."""

    def __init__(self, source: str, headless: bool = True):
        """Initialize browser manager.

        Args:
            source: Source name for data isolation.
            headless: Run browser in headless mode.
        """
        self.source = source
        self.headless = headless
        self._playwright: Optional[AsyncPlaywright] = None
        self._browser: Optional[AsyncBrowser] = None
        self._context: Optional[AsyncBrowserContext] = None

    @property
    def data_dir(self) -> Path:
        """Get data directory for this source."""
        return get_data_dir(self.source)

    @property
    def cookies_path(self) -> Path:
        """Get cookies file path."""
        return get_cookies_path(self.source)

    async def start(self) -> None:
        """Start browser instance."""
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
        )

        self._context = await self._browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=get_random_user_agent(),
        )

        await self._apply_stealth()
        await self._load_cookies()

    async def _apply_stealth(self) -> None:
        """Apply anti-detection measures."""
        if self._context:
            await self._context.add_init_script(STEALTH_SCRIPT)

    async def _load_cookies(self) -> bool:
        """Load cookies from file."""
        if self._context is None or not self.cookies_path.exists():
            return False

        try:
            cookies = json.loads(self.cookies_path.read_text())
            await self._context.add_cookies(cookies)
            return True
        except Exception:
            return False

    async def save_cookies(self) -> None:
        """Save cookies to file."""
        if self._context is None:
            return

        try:
            cookies = await self._context.cookies()
            self.cookies_path.write_text(
                json.dumps(cookies, ensure_ascii=False, indent=2)
            )
        except Exception:
            pass

    async def new_page(self) -> AsyncPage:
        """Create a new page."""
        if self._context is None:
            raise RuntimeError("Browser not started. Call start() first.")
        return await self._context.new_page()

    async def stop(self) -> None:
        """Stop browser and cleanup."""
        if self._context:
            await self._context.close()
            self._context = None

        if self._browser:
            await self._browser.close()
            self._browser = None

        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    @property
    def context(self) -> Optional[AsyncBrowserContext]:
        """Get browser context."""
        return self._context

    @property
    def is_started(self) -> bool:
        """Check if browser is started."""
        return self._browser is not None

    async def switch_to_headed(self, current_url: str = "") -> AsyncPage:
        """Switch from headless to headed mode."""
        if not self.headless:
            page = await self.new_page()
            if current_url:
                await page.goto(current_url, wait_until="domcontentloaded", timeout=30000)
            return page

        await self.save_cookies()
        await self.stop()

        self.headless = False
        await self.start()

        page = await self.new_page()
        if current_url:
            await page.goto(current_url, wait_until="domcontentloaded", timeout=30000)
        return page


@asynccontextmanager
async def get_browser(source: str, headless: bool = True) -> AsyncIterator[BrowserManager]:
    """Context manager for async browser instance.

    Args:
        source: Source name for data isolation.
        headless: Run browser in headless mode.

    Yields:
        BrowserManager instance.
    """
    manager = BrowserManager(source=source, headless=headless)
    try:
        await manager.start()
        yield manager
    finally:
        await manager.stop()


async def random_delay(min_delay: float = 1.0, max_delay: float = 3.0) -> None:
    """Wait for a random delay."""
    delay = random.uniform(min_delay, max_delay)
    await asyncio.sleep(delay)
