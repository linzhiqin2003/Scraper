"""Asynchronous base scraper class."""

import asyncio
from abc import ABC, abstractmethod
from typing import Any, Optional, List
from urllib.parse import parse_qs, urlparse

from playwright.async_api import Page

from .browser import BrowserManager, random_delay
from .exceptions import RateLimitedError, NotLoggedInError


class AsyncBaseScraper(ABC):
    """Base class for asynchronous scrapers."""

    # Subclasses should set this
    SOURCE_NAME: str = "default"
    BASE_URL: str = ""

    # Common login selectors (override in subclass if needed)
    LOGIN_SELECTORS: List[str] = []
    RATE_LIMIT_SELECTORS: List[str] = []
    CAPTCHA_SELECTORS: List[str] = []

    def __init__(self, browser: BrowserManager):
        """Initialize scraper.

        Args:
            browser: BrowserManager instance.
        """
        self.browser = browser

    async def _wait_for_element(
        self,
        page: Page,
        selector: str,
        timeout: int = 10000,
        state: str = "visible",
    ) -> bool:
        """Wait for an element to appear.

        Args:
            page: Playwright page.
            selector: CSS selector.
            timeout: Timeout in milliseconds.
            state: Element state to wait for.

        Returns:
            True if element found, False otherwise.
        """
        try:
            await page.wait_for_selector(selector, timeout=timeout, state=state)
            return True
        except Exception:
            return False

    async def _scroll_page(self, page: Page, scroll_count: int = 1, delay: float = 1.5) -> None:
        """Scroll page down.

        Args:
            page: Playwright page.
            scroll_count: Number of times to scroll.
            delay: Delay after each scroll.
        """
        for _ in range(scroll_count):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(delay)

    async def _scroll_and_load(
        self,
        page: Page,
        item_selector: str,
        max_items: int,
        max_scrolls: int = 50,
        scroll_delay: float = 1.5,
    ) -> List[Any]:
        """Scroll page and collect items until reaching max_items.

        Args:
            page: Playwright page.
            item_selector: CSS selector for items to collect.
            max_items: Maximum number of items to collect.
            max_scrolls: Maximum number of scroll attempts.
            scroll_delay: Delay after each scroll.

        Returns:
            List of collected items (as element handles).
        """
        seen_count = 0
        scroll_count = 0
        no_new_items_count = 0

        while scroll_count < max_scrolls:
            items = await page.query_selector_all(item_selector)
            current_count = len(items)

            if current_count >= max_items:
                break

            if current_count == seen_count:
                no_new_items_count += 1
                if no_new_items_count >= 3:
                    break
            else:
                no_new_items_count = 0
                seen_count = current_count

            await self._scroll_page(page, delay=scroll_delay)
            scroll_count += 1

        return await page.query_selector_all(item_selector)

    async def _retry_operation(
        self,
        operation,
        max_retries: int = 3,
        retry_delay: float = 5.0,
    ) -> Any:
        """Retry an async operation with exponential backoff.

        Args:
            operation: Async callable to execute.
            max_retries: Maximum retry attempts.
            retry_delay: Base delay between retries.

        Returns:
            Result of the operation.

        Raises:
            Last exception if all retries fail.
        """
        last_exception = None
        for attempt in range(max_retries):
            try:
                return await operation()
            except Exception as e:
                last_exception = e
                if attempt < max_retries - 1:
                    wait_time = retry_delay * (2 ** attempt)
                    await asyncio.sleep(wait_time)

        raise last_exception

    async def _check_login_required(self, page: Page) -> bool:
        """Check if page shows login prompt.

        Args:
            page: Playwright page.

        Returns:
            True if login is required.
        """
        for selector in self.LOGIN_SELECTORS:
            try:
                el = await page.query_selector(selector)
                if el:
                    return True
            except Exception:
                pass
        return False

    async def _check_rate_limit(self, page: Page) -> bool:
        """Check if page shows rate limit warning.

        Args:
            page: Playwright page.

        Returns:
            True if rate limited.
        """
        for selector in self.RATE_LIMIT_SELECTORS:
            try:
                el = await page.query_selector(selector)
                if el:
                    return True
            except Exception:
                pass
        return False

    async def _check_captcha(self, page: Page) -> bool:
        """Check if page shows CAPTCHA.

        Args:
            page: Playwright page.

        Returns:
            True if CAPTCHA detected.
        """
        for selector in self.CAPTCHA_SELECTORS:
            try:
                el = await page.query_selector(selector)
                if el:
                    return True
            except Exception:
                pass
        return False

    async def _handle_rate_limit(
        self,
        page: Page,
        wait_time: float = 60.0,
        silent: bool = False,
    ) -> None:
        """Handle rate limit by waiting.

        Args:
            page: Playwright page.
            wait_time: Time to wait in seconds.
            silent: Suppress console output.
        """
        from rich.console import Console
        console = Console()

        if not silent:
            console.print(
                f"[yellow]Rate limit detected. Waiting {wait_time} seconds...[/yellow]"
            )

        await asyncio.sleep(wait_time)

    async def _close_login_modal(self, page: Page) -> None:
        """Try to close login modal if it appears.

        Args:
            page: Playwright page.
        """
        # Default implementation - subclasses can override
        try:
            close_btn = await page.query_selector('[aria-label="Close"], [aria-label="关闭"]')
            if close_btn:
                await close_btn.click()
                await random_delay(0.3, 0.5)
        except Exception:
            pass

    def _extract_param_from_url(self, url: str, param: str) -> str:
        """Extract a query parameter from URL.

        Args:
            url: URL containing the parameter.
            param: Parameter name to extract.

        Returns:
            Parameter value or empty string.
        """
        try:
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            return params.get(param, [""])[0]
        except Exception:
            return ""

    def _extract_path_segment(self, url: str, index: int) -> str:
        """Extract a path segment from URL.

        Args:
            url: URL to parse.
            index: Index of path segment (0-based).

        Returns:
            Path segment or empty string.
        """
        try:
            parsed = urlparse(url)
            parts = parsed.path.strip("/").split("/")
            if index < len(parts):
                return parts[index]
            return ""
        except Exception:
            return ""

    @abstractmethod
    async def scrape(self, *args, **kwargs) -> Any:
        """Main scraping method to be implemented by subclasses."""
        pass
