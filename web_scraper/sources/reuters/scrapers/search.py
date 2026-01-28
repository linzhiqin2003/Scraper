"""Search scraper for Reuters."""

import re
import time
from typing import List, Optional
from urllib.parse import urlencode

from playwright.sync_api import Page, ElementHandle

from ....core.base import BaseScraper
from ....core.exceptions import CaptchaError
from ..config import SOURCE_NAME, BASE_URL, SEARCH_URL, ScraperSelectors
from ..models import SearchResult


class SearchScraper(BaseScraper):
    """Scraper for Reuters search functionality."""

    SOURCE_NAME = SOURCE_NAME
    BASE_URL = BASE_URL
    RATE_LIMIT_PATTERN = ScraperSelectors.RATE_LIMIT_TEXT

    def get_total_count(
        self,
        query: str,
        section: Optional[str] = None,
        date_range: Optional[str] = None,
        page: Optional[Page] = None,
    ) -> int:
        """Get total count of search results without fetching articles.

        Args:
            query: Search query string.
            section: Filter by section.
            date_range: Filter by date range.
            page: Optional existing Page instance to use.

        Returns:
            Total number of matching articles.
        """
        if page is not None:
            return self._do_get_count(page, query, section, date_range)

        with self.get_page() as p:
            return self._do_get_count(p, query, section, date_range)

    def _do_get_count(
        self,
        page: Page,
        query: str,
        section: Optional[str],
        date_range: Optional[str],
    ) -> int:
        """Perform the actual count operation."""
        params = {"query": query}
        if section:
            params["section"] = section
        if date_range:
            params["date"] = date_range

        url = f"{SEARCH_URL}?{urlencode(params)}"
        page.goto(url)
        time.sleep(2)

        if self._check_captcha(page):
            if self.headless:
                raise CaptchaError(
                    "CAPTCHA verification required. "
                    "Run without --headless flag to complete verification manually."
                )
            print("Please complete the CAPTCHA verification in the browser...")
            self.wait_for_element(page, ScraperSelectors.SEARCH_RESULT_ITEM, timeout=60)

        try:
            pagination_text = page.evaluate("""
                () => {
                    const body = document.body.innerText;
                    const match = body.match(/\\d+\\s+to\\s+\\d+\\s+of\\s+([\\d,]+)/i);
                    return match ? match[1] : null;
                }
            """)
            if pagination_text:
                return int(pagination_text.replace(",", ""))
        except Exception:
            pass

        items = page.query_selector_all(ScraperSelectors.SEARCH_RESULT_ITEM)
        return len(items)

    def _check_captcha(self, page: Page) -> bool:
        """Check if page shows visible CAPTCHA verification."""
        captcha_selectors = [
            'iframe[src*="captcha"]',
            'iframe[src*="recaptcha"]',
            'iframe[src*="hcaptcha"]',
            '[class*="captcha"]:visible',
            '#captcha-container',
            '[data-testid*="captcha"]',
            '.verification-required',
            '[class*="challenge"]',
        ]

        for selector in captcha_selectors:
            try:
                el = page.query_selector(selector)
                if el and el.is_visible():
                    return True
            except Exception:
                continue

        visible_text = page.evaluate("() => document.body.innerText")
        text_indicators = [
            "Verification Required",
            "verify you are human",
            "Slide right to secure",
            "Please complete the security check",
        ]
        return any(indicator.lower() in visible_text.lower() for indicator in text_indicators)

    def search(
        self,
        query: str,
        max_results: int = 10,
        section: Optional[str] = None,
        date_range: Optional[str] = None,
        sort_by: str = "relevance",
        page: Optional[Page] = None,
    ) -> List[SearchResult]:
        """Search Reuters for articles.

        Args:
            query: Search query string.
            max_results: Maximum number of results to return.
            section: Filter by section.
            date_range: Filter by date.
            sort_by: Sort order ("relevance" or "date").
            page: Optional existing Page instance to use.

        Returns:
            List of SearchResult objects.

        Raises:
            CaptchaError: If CAPTCHA verification is required.
        """
        if page is not None:
            return self._do_search(page, query, max_results, section, date_range, sort_by)

        with self.get_page() as p:
            return self._do_search(p, query, max_results, section, date_range, sort_by)

    def _do_search(
        self,
        page: Page,
        query: str,
        max_results: int,
        section: Optional[str],
        date_range: Optional[str],
        sort_by: str,
    ) -> List[SearchResult]:
        """Perform the actual search operation using offset-based pagination."""
        all_results: List[SearchResult] = []
        offset = 0
        page_size = 20

        while len(all_results) < max_results:
            params = {"query": query, "offset": offset}
            if section:
                params["section"] = section
            if date_range:
                params["date"] = date_range
            if sort_by == "date":
                params["sort"] = "newest"

            url = f"{SEARCH_URL}?{urlencode(params)}"
            page.goto(url)
            time.sleep(2)

            if offset == 0 and self._check_captcha(page):
                if self.headless:
                    raise CaptchaError(
                        "CAPTCHA verification required. "
                        "Run without --headless flag to complete verification manually."
                    )
                print("Please complete the CAPTCHA verification in the browser...")
                self.wait_for_element(page, ScraperSelectors.SEARCH_RESULT_ITEM, timeout=60)

            if self.check_rate_limit(page):
                self.handle_rate_limit(page)

            try:
                self.wait_for_element(page, ScraperSelectors.SEARCH_RESULT_ITEM, timeout=10)
            except Exception:
                break

            page_results = self._parse_results(page, page_size)

            if not page_results:
                break

            all_results.extend(page_results)
            offset += page_size

            if len(all_results) >= max_results:
                break

        return all_results[:max_results]

    def _parse_results(self, page: Page, max_results: int) -> List[SearchResult]:
        """Parse search result items from page."""
        results: List[SearchResult] = []

        items = page.query_selector_all(ScraperSelectors.SEARCH_RESULT_ITEM)

        if not items:
            items = page.query_selector_all("article, [data-testid*='story']")

        for item in items[:max_results]:
            try:
                result = self._parse_single_result(item)
                if result:
                    results.append(result)
            except Exception:
                continue

        return results

    def _parse_single_result(self, item: ElementHandle) -> Optional[SearchResult]:
        """Parse a single search result item."""
        title = None
        url = None

        try:
            links = item.query_selector_all('a[href*="/"]')
            for link in links:
                href = link.get_attribute("href") or ""
                if re.search(r'-20\d{2}-\d{2}-\d{2}', href):
                    link_text = (link.text_content() or "").strip()
                    if link_text and len(link_text) > 10:
                        title = link_text
                        url = href
                        break
        except Exception:
            return None

        if not title or not url:
            return None

        summary = self.safe_get_text(item, ScraperSelectors.SEARCH_RESULT_SUMMARY)
        published_at = self.safe_get_text(item, ScraperSelectors.SEARCH_RESULT_TIME)
        if not published_at:
            published_at = self.safe_get_attribute(
                item, ScraperSelectors.SEARCH_RESULT_TIME, "datetime"
            )

        category = None
        if url:
            path = url.replace("https://www.reuters.com/", "").strip("/")
            parts = path.split("/")
            if len(parts) > 0:
                category = parts[0]

        return SearchResult(
            title=title,
            summary=summary.strip() if summary else None,
            url=url,
            published_at=published_at.strip() if published_at else None,
            category=category,
        )

    def scrape(self, *args, **kwargs):
        """Main scraping method - alias for search."""
        return self.search(*args, **kwargs)
