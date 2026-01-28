"""Synchronous base scraper class."""

import re
import time
from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import Iterator, List, Optional, Any

from playwright.sync_api import Page, ElementHandle, TimeoutError as PlaywrightTimeout

from .browser import create_browser, load_cookies_sync, get_state_path
from .exceptions import NotLoggedInError, RateLimitedError


class BaseScraper(ABC):
    """Base class for synchronous scrapers."""

    # Subclasses should set this
    SOURCE_NAME: str = "default"
    BASE_URL: str = ""
    RATE_LIMIT_PATTERN: str = r"rate limit|too many requests"

    def __init__(self, headless: bool = True, page: Optional[Page] = None):
        """Initialize scraper.

        Args:
            headless: Run browser in headless mode.
            page: Optional shared Playwright Page instance.
        """
        self.headless = headless
        self._shared_page = page

    @contextmanager
    def get_page(self) -> Iterator[Page]:
        """Get a Playwright Page with authenticated session.

        If a shared page was provided, use it without closing.
        Otherwise create a new browser session.

        Raises:
            NotLoggedInError: If session file doesn't exist.

        Yields:
            Playwright Page instance.
        """
        if self._shared_page is not None:
            yield self._shared_page
            return

        state_file = get_state_path(self.SOURCE_NAME)
        if not state_file.exists():
            raise NotLoggedInError(
                f"Not logged in. Run 'scraper {self.SOURCE_NAME} login' first."
            )

        # storage_state is loaded automatically in create_browser
        with create_browser(headless=self.headless, source=self.SOURCE_NAME) as page:
            yield page

    def check_rate_limit(self, page: Page) -> bool:
        """Check if page shows rate limit warning.

        Args:
            page: Playwright Page instance.

        Returns:
            True if rate limited, False otherwise.
        """
        content = page.content()
        return bool(re.search(self.RATE_LIMIT_PATTERN, content, re.IGNORECASE))

    def wait_for_element(
        self,
        page: Page,
        selector: str,
        timeout: int = 10,
    ) -> Optional[ElementHandle]:
        """Wait for element to appear on page.

        Args:
            page: Playwright Page instance.
            selector: CSS selector.
            timeout: Timeout in seconds.

        Returns:
            ElementHandle if found, None if timeout.
        """
        try:
            page.wait_for_selector(selector, timeout=timeout * 1000)
            return page.query_selector(selector)
        except PlaywrightTimeout:
            return None

    def wait_for_elements(
        self,
        page: Page,
        selector: str,
        timeout: int = 10,
    ) -> List[ElementHandle]:
        """Wait for elements to appear on page.

        Args:
            page: Playwright Page instance.
            selector: CSS selector.
            timeout: Timeout in seconds.

        Returns:
            List of ElementHandles, empty if timeout.
        """
        try:
            page.wait_for_selector(selector, timeout=timeout * 1000)
            return page.query_selector_all(selector)
        except PlaywrightTimeout:
            return []

    def safe_get_text(
        self,
        element: ElementHandle,
        selector: str,
        default: Optional[str] = None,
    ) -> Optional[str]:
        """Safely get text content from child element.

        Args:
            element: Parent ElementHandle.
            selector: CSS selector for child.
            default: Default value if not found.

        Returns:
            Text content or default.
        """
        try:
            child = element.query_selector(selector)
            if child:
                return child.text_content()
        except Exception:
            pass
        return default

    def safe_get_attribute(
        self,
        element: ElementHandle,
        selector: str,
        attribute: str,
        default: Optional[str] = None,
    ) -> Optional[str]:
        """Safely get attribute from child element.

        Args:
            element: Parent ElementHandle.
            selector: CSS selector for child.
            attribute: Attribute name.
            default: Default value if not found.

        Returns:
            Attribute value or default.
        """
        try:
            child = element.query_selector(selector)
            if child:
                return child.get_attribute(attribute)
        except Exception:
            pass
        return default

    def normalize_url(self, url: str) -> str:
        """Normalize URL to absolute form.

        Args:
            url: Relative or absolute URL.

        Returns:
            Absolute URL.
        """
        if not url:
            return ""
        if url.startswith("http"):
            return url
        if url.startswith("/"):
            return f"{self.BASE_URL}{url}"
        return f"{self.BASE_URL}/{url}"

    def scroll_to_load(
        self,
        page: Page,
        item_selector: str,
        max_items: int,
        max_scrolls: int = 10,
        scroll_delay: float = 1.5,
    ) -> int:
        """Scroll page to load more items.

        Args:
            page: Playwright Page instance.
            item_selector: Selector for items to count.
            max_items: Stop when this many items loaded.
            max_scrolls: Maximum scroll attempts.
            scroll_delay: Delay between scrolls in seconds.

        Returns:
            Number of items loaded.
        """
        prev_count = 0
        no_new_count = 0

        for _ in range(max_scrolls):
            items = page.query_selector_all(item_selector)
            current_count = len(items)

            if current_count >= max_items:
                break

            if current_count == prev_count:
                no_new_count += 1
                if no_new_count >= 3:
                    break
            else:
                no_new_count = 0

            prev_count = current_count
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(scroll_delay)

        items = page.query_selector_all(item_selector)
        return len(items)

    def handle_rate_limit(
        self,
        page: Page,
        base_delay: float = 5.0,
        max_retries: int = 3,
    ) -> bool:
        """Handle rate limiting with exponential backoff.

        Args:
            page: Playwright Page instance.
            base_delay: Base delay in seconds.
            max_retries: Maximum retry attempts.

        Returns:
            True if recovered, False if max retries exceeded.

        Raises:
            RateLimitedError: If max retries exceeded.
        """
        for attempt in range(max_retries):
            if not self.check_rate_limit(page):
                return True

            wait_time = base_delay * (2 ** attempt)
            time.sleep(wait_time)
            page.reload()

        raise RateLimitedError(
            f"Rate limited after {max_retries} retries. "
            "Please wait and try again later."
        )

    @abstractmethod
    def scrape(self, *args, **kwargs) -> Any:
        """Main scraping method to be implemented by subclasses."""
        pass
