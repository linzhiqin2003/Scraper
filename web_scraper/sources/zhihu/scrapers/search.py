"""Zhihu search scraper with multi-strategy extraction.

Strategy chain: API direct → API intercept → DOM extraction.
"""

import logging
import re
from typing import List, Optional
from urllib.parse import quote

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from ..anti_detect import BlockDetector, BlockStatus, BlockType
from ..browser import open_zhihu_page, wait_for_unblock
from ..config import BASE_URL, SEARCH_TYPES, SEARCH_URL, STRATEGY_AUTO, STRATEGY_PURE_API, Selectors, Timeouts
from ..models import SearchResult, SearchResponse
from ..proxy import ProxyPool
from ..rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


def _parse_number(text: str) -> Optional[int]:
    """Parse display numbers like '1.2 万' -> 12000, '234' -> 234."""
    if not text:
        return None
    text = text.strip().replace(",", "")
    match = re.search(r"([\d.]+)\s*万", text)
    if match:
        return int(float(match.group(1)) * 10000)
    match = re.search(r"(\d+)", text)
    if match:
        return int(match.group(1))
    return None


def _extract_results_from_page(page: Page) -> List[SearchResult]:
    """Extract search results from the current page DOM."""
    results = []

    cards = page.query_selector_all(Selectors.RESULT_CARD)
    if not cards:
        cards = page.query_selector_all(Selectors.RESULT_CARD_FALLBACK)
    if not cards:
        return results

    for card in cards:
        try:
            result = _parse_card(card)
            if result:
                results.append(result)
        except Exception as e:
            logger.debug("Failed to parse card: %s", e)
            continue

    return results


def _parse_card(card) -> Optional[SearchResult]:
    """Parse a single search result card element."""
    title_el = card.query_selector("h2 a, h2 span a, [class*='ContentItem-title'] a")
    if not title_el:
        title_el = card.query_selector("h2")
        if not title_el:
            return None

    title = title_el.inner_text().strip()
    if not title:
        return None

    url = title_el.get_attribute("href") or ""
    if url.startswith("//"):
        url = "https:" + url
    elif url.startswith("/"):
        url = BASE_URL + url

    content_type = "answer"
    if "zhuanlan" in url or "/p/" in url:
        content_type = "article"
    elif "/question/" in url and "/answer/" not in url:
        content_type = "question"
    elif "/zvideo/" in url:
        content_type = "video"

    excerpt = ""
    excerpt_el = card.query_selector(
        ".RichContent-inner, .CopyrightRichTextContainer, "
        "[class*='RichText'], .Highlight"
    )
    if excerpt_el:
        excerpt = excerpt_el.inner_text().strip()[:500]

    author = None
    author_url = None
    author_el = card.query_selector(
        ".AuthorInfo .UserLink-link, [class*='AuthorInfo'] a[href*='/people/']"
    )
    if author_el:
        author = author_el.inner_text().strip()
        author_url = author_el.get_attribute("href") or None
        if author_url and author_url.startswith("/"):
            author_url = BASE_URL + author_url

    upvotes = None
    vote_el = card.query_selector(
        "button[class*='VoteButton--up'], [class*='VoteButton'] :first-child"
    )
    if vote_el:
        upvotes = _parse_number(vote_el.inner_text())

    comments = None
    comment_el = card.query_selector(
        "button:has-text('条评论'), a:has-text('条评论')"
    )
    if comment_el:
        comments = _parse_number(comment_el.inner_text())

    return SearchResult(
        title=title,
        url=url,
        content_type=content_type,
        excerpt=excerpt,
        author=author,
        author_url=author_url,
        upvotes=upvotes,
        comments=comments,
        data_source="dom",
    )


class SearchScraper:
    """Zhihu search scraper with multi-strategy extraction.

    Strategy chain (auto mode):
    1. API direct (Phase 2) - fastest, requires signature oracle
    2. API intercept (Phase 1) - intercept XHR responses during page load
    3. DOM extraction (original) - fallback, parse HTML elements
    """

    def __init__(
        self,
        cdp_port: int = 9222,
        rate_limiter: Optional[RateLimiter] = None,
        proxy_pool: Optional[ProxyPool] = None,
        strategy: str = STRATEGY_AUTO,
    ):
        self.cdp_port = cdp_port
        self.rate_limiter = rate_limiter
        self.proxy_pool = proxy_pool
        self.strategy = strategy
        self._detector = BlockDetector()

    def search(
        self,
        query: str,
        search_type: str = "content",
        limit: int = 20,
        offset: int = 0,
    ) -> SearchResponse:
        """Search Zhihu with multi-strategy extraction.

        Args:
            query: Search keywords.
            search_type: Search type (content, people, scholar, column, topic, zvideo).
            limit: Maximum results to return.
            offset: Result offset for pagination.

        Returns:
            SearchResponse with results.
        """
        # Rate limiting
        if self.rate_limiter:
            self.rate_limiter.wait()

        # Strategy 0: Pure API (no browser needed)
        if self.strategy in (STRATEGY_AUTO, STRATEGY_PURE_API):
            results = self._try_pure_api(query, search_type, limit, offset)
            if results is not None:
                self._record_success()
                return SearchResponse(
                    query=query,
                    search_type=search_type,
                    results=results[:limit],
                    total=len(results),
                )
            if self.strategy == STRATEGY_PURE_API:
                return SearchResponse(query=query, search_type=search_type)

        url = f"{SEARCH_URL}?type={search_type}&q={quote(query)}"

        with open_zhihu_page(cdp_port=self.cdp_port) as page:
            # Strategy 1: Try API direct via browser SignatureOracle
            if self.strategy in (STRATEGY_AUTO, "api"):
                results = self._try_api_direct(page, query, search_type, limit, offset)
                if results is not None:
                    self._record_success()
                    return SearchResponse(
                        query=query,
                        search_type=search_type,
                        results=results[:limit],
                        total=len(results),
                    )

            # Strategy 2: Try API intercept
            if self.strategy in (STRATEGY_AUTO, "intercept"):
                results = self._try_api_intercept(page, url, limit)
                if results is not None:
                    self._record_success()
                    return SearchResponse(
                        query=query,
                        search_type=search_type,
                        results=results[:limit],
                        total=len(results),
                    )

            # Strategy 3: DOM extraction (original logic)
            if self.strategy in (STRATEGY_AUTO, "dom"):
                return self._dom_extract(page, url, query, search_type, limit)

            return SearchResponse(query=query, search_type=search_type)

    def search_multi_pages(
        self,
        query: str,
        search_type: str = "content",
        max_results: int = 20,
    ) -> List[SearchResult]:
        """Search with scrolling pagination."""
        response = self.search(
            query=query,
            search_type=search_type,
            limit=max_results,
        )
        return response.results

    def _try_pure_api(
        self,
        query: str,
        search_type: str,
        limit: int,
        offset: int,
    ) -> Optional[List[SearchResult]]:
        """Attempt pure API search (no browser required)."""
        try:
            from ..api_client import PureAPIClient

            proxy_url = None
            if self.proxy_pool:
                proxy = self.proxy_pool.get_best()
                if proxy:
                    proxy_url = proxy.url

            client = PureAPIClient(proxy_url=proxy_url)
            if not client.initialize():
                logger.debug("PureAPIClient init failed (no cookies?)")
                return None

            try:
                results = client.search(
                    query=query,
                    search_type="general" if search_type == "content" else search_type,
                    limit=limit,
                    offset=offset,
                )
                if results:
                    for r in results:
                        r.data_source = "pure_api"
                    logger.info("Pure API search returned %d results", len(results))
                    return results
            finally:
                client.close()

        except Exception as e:
            logger.debug("Pure API search failed: %s", e)

        return None

    def _try_api_direct(
        self,
        page: Page,
        query: str,
        search_type: str,
        limit: int,
        offset: int,
    ) -> Optional[List[SearchResult]]:
        """Attempt API direct search via SignatureOracle."""
        try:
            from ..api_client import ZhihuAPIClient

            proxy_url = None
            if self.proxy_pool:
                proxy = self.proxy_pool.get_best()
                if proxy:
                    proxy_url = proxy.url

            client = ZhihuAPIClient(page, proxy_url=proxy_url)
            if not client.initialize():
                return None

            try:
                results = client.search(
                    query=query,
                    search_type="general" if search_type == "content" else search_type,
                    limit=limit,
                    offset=offset,
                )
                if results:
                    for r in results:
                        r.data_source = "api_direct"
                    logger.info("API direct search returned %d results", len(results))
                    return results
            finally:
                client.close()

        except Exception as e:
            logger.debug("API direct search failed: %s", e)

        return None

    def _try_api_intercept(
        self,
        page: Page,
        search_url: str,
        limit: int,
    ) -> Optional[List[SearchResult]]:
        """Attempt API intercept search via ResponseInterceptor."""
        try:
            from .interceptor import ResponseInterceptor, parse_api_search_results

            interceptor = ResponseInterceptor()
            interceptor.start(page, ["search"])

            try:
                page.goto(search_url, wait_until="domcontentloaded", timeout=Timeouts.NAVIGATION)
                page.wait_for_timeout(3000)

                # Check for blocks
                block_status = self._detector.check_page(page)
                if block_status.is_blocked:
                    self._handle_block(block_status, page)
                    if block_status.block_type in (BlockType.CAPTCHA, BlockType.SESSION_EXPIRED):
                        return None

                captures = interceptor.stop()
            except Exception:
                interceptor.stop()
                raise

            # Parse captured search responses
            for cap in captures:
                if cap.pattern_name == "search" and cap.body:
                    results = parse_api_search_results(cap.body)
                    if results:
                        for r in results:
                            r.data_source = "api_intercept"
                        logger.info("API intercept returned %d results", len(results))
                        return results

        except Exception as e:
            logger.debug("API intercept search failed: %s", e)

        return None

    def _dom_extract(
        self,
        page: Page,
        url: str,
        query: str,
        search_type: str,
        limit: int,
    ) -> SearchResponse:
        """Original DOM-based extraction (fallback)."""
        # Navigate if not already on the page
        current = page.url
        if "search" not in current or query not in current:
            page.goto(url, wait_until="domcontentloaded", timeout=Timeouts.NAVIGATION)
            page.wait_for_timeout(3000)

        # Handle blocking
        if not wait_for_unblock(page, timeout_ms=60_000):
            raise RuntimeError("Blocked by Zhihu security verification")

        if "signin" in page.url:
            raise RuntimeError(
                "Not logged in. Log in to Chrome first, or run 'scraper zhihu login'"
            )

        # Wait for results to load
        try:
            page.wait_for_selector(
                f"{Selectors.RESULT_CARD}, {Selectors.RESULT_CARD_FALLBACK}, {Selectors.NO_RESULT}",
                timeout=Timeouts.RESULT_LOAD,
            )
        except PlaywrightTimeout:
            pass

        # Check no results
        no_result = page.query_selector(Selectors.NO_RESULT)
        if no_result:
            return SearchResponse(query=query, search_type=search_type)

        # Extract initial results
        all_results = _extract_results_from_page(page)

        # Scroll to load more if needed
        scroll_attempts = 0
        max_scrolls = max(0, (limit - len(all_results)) // 10 + 1)
        while len(all_results) < limit and scroll_attempts < max_scrolls:
            prev_count = len(all_results)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(Timeouts.SCROLL_WAIT)

            new_results = _extract_results_from_page(page)
            seen_urls = {r.url for r in all_results}
            for r in new_results:
                if r.url not in seen_urls:
                    all_results.append(r)
                    seen_urls.add(r.url)

            if len(all_results) == prev_count:
                break
            scroll_attempts += 1

        self._record_success()
        results = all_results[:limit]
        return SearchResponse(
            query=query,
            search_type=search_type,
            results=results,
            total=len(results),
        )

    def _handle_block(self, status: BlockStatus, page: Page) -> None:
        """Handle a detected block condition."""
        logger.warning("Block detected: %s", status.message)

        if status.should_rotate_proxy and self.proxy_pool:
            logger.info("Rotating proxy due to block")
            if self.rate_limiter:
                self.rate_limiter.record_block()

        if status.should_wait and status.wait_seconds > 0:
            import time
            logger.info("Waiting %.0fs due to block", status.wait_seconds)
            time.sleep(status.wait_seconds)

        if status.block_type == BlockType.CAPTCHA:
            wait_for_unblock(page, timeout_ms=60_000)

    def _record_success(self) -> None:
        """Record success to rate limiter."""
        if self.rate_limiter:
            self.rate_limiter.record_success()
