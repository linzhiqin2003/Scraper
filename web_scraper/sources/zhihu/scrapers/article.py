"""Zhihu article/answer scraper with multi-strategy extraction.

Strategy chain: API direct → API intercept → DOM extraction.
"""

import logging
import re
from datetime import datetime
from typing import List, Optional

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from ..anti_detect import BlockDetector, BlockStatus, BlockType
from ..browser import open_zhihu_page, wait_for_unblock
from ..config import BASE_URL, STRATEGY_AUTO, STRATEGY_PURE_API, Selectors, Timeouts
from ..models import ArticleDetail
from ..proxy import ProxyPool
from ..rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


def _extract_article(page: Page, url: str) -> ArticleDetail:
    """Extract article/answer content from the current page DOM."""
    # Title
    title = ""
    for sel in Selectors.ARTICLE_TITLE.split(", "):
        el = page.query_selector(sel)
        if el:
            title = el.inner_text().strip()
            if title:
                break

    # Content type and question title
    content_type = "article"
    question_title = None
    if "/answer/" in url or "/question/" in url:
        content_type = "answer"
        q_el = page.query_selector("h1[class*='QuestionHeader-title']")
        if q_el:
            question_title = q_el.inner_text().strip()
            if not title:
                title = question_title

    # Content
    content = ""
    content_el = page.query_selector(Selectors.ARTICLE_CONTENT)
    if content_el:
        content = content_el.inner_text().strip()

    # Author
    author = None
    author_url = None
    author_el = page.query_selector(Selectors.ARTICLE_AUTHOR)
    if author_el:
        author = author_el.inner_text().strip()
        href = author_el.get_attribute("href")
        if href:
            author_url = href if href.startswith("http") else BASE_URL + href

    # Upvotes
    upvotes = None
    vote_el = page.query_selector("button[class*='VoteButton--up']")
    if vote_el:
        text = vote_el.inner_text().strip()
        match = re.search(r"([\d,.]+)\s*万?", text)
        if match:
            num = match.group(1).replace(",", "")
            if "万" in text:
                upvotes = int(float(num) * 10000)
            else:
                try:
                    upvotes = int(num)
                except ValueError:
                    pass

    # Comments
    comments = None
    comment_el = page.query_selector("button:has-text('条评论'), a:has-text('条评论')")
    if comment_el:
        match = re.search(r"(\d+)", comment_el.inner_text())
        if match:
            comments = int(match.group(1))

    # Time
    created_at = None
    updated_at = None
    time_el = page.query_selector("time")
    if time_el:
        dt = time_el.get_attribute("datetime")
        if dt:
            created_at = dt
        else:
            created_at = time_el.inner_text().strip()

    edit_el = page.query_selector(":text('编辑于'), :text('修改于')")
    if edit_el:
        text = edit_el.inner_text()
        match = re.search(r"(\d{4}-\d{2}-\d{2})", text)
        if match:
            updated_at = match.group(1)

    # Tags
    tags = []
    tag_els = page.query_selector_all(Selectors.ARTICLE_TAGS)
    for tag_el in tag_els:
        tag = tag_el.inner_text().strip()
        if tag:
            tags.append(tag)

    # Images
    images = []
    img_els = page.query_selector_all(
        ".Post-RichTextContainer img, .RichContent-inner img"
    )
    for img_el in img_els:
        src = img_el.get_attribute("src") or img_el.get_attribute("data-original")
        if src and not src.startswith("data:"):
            if src.startswith("//"):
                src = "https:" + src
            images.append(src)

    return ArticleDetail(
        url=url,
        title=title,
        content=content,
        author=author,
        author_url=author_url,
        upvotes=upvotes,
        comments=comments,
        created_at=created_at,
        updated_at=updated_at,
        tags=tags,
        images=images,
        content_type=content_type,
        question_title=question_title,
        scraped_at=datetime.now(),
        data_source="dom",
    )


def _parse_content_ids(url: str) -> tuple:
    """Extract answer_id or article_id from URL.

    Returns:
        (content_type, content_id) where content_type is "answer" or "article".
    """
    # https://www.zhihu.com/question/123/answer/456
    match = re.search(r"/answer/(\d+)", url)
    if match:
        return ("answer", match.group(1))

    # https://zhuanlan.zhihu.com/p/789
    match = re.search(r"/p/(\d+)", url)
    if match:
        return ("article", match.group(1))

    return (None, None)


class ArticleScraper:
    """Zhihu article/answer scraper with multi-strategy extraction.

    Strategy chain (auto mode):
    1. API direct - fastest, requires signature oracle
    2. API intercept - intercept XHR responses during page load
    3. DOM extraction - fallback, parse HTML elements
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

    def scrape(self, url: str) -> ArticleDetail:
        """Scrape a single article or answer with multi-strategy extraction.

        Args:
            url: Article or answer URL.

        Returns:
            ArticleDetail with full content.
        """
        # Rate limiting
        if self.rate_limiter:
            self.rate_limiter.wait()

        content_type, content_id = _parse_content_ids(url)

        # Strategy 0: Pure API (no browser needed)
        if self.strategy in (STRATEGY_AUTO, STRATEGY_PURE_API) and content_id:
            result = self._try_pure_api(url, content_type, content_id)
            if result:
                self._record_success()
                return result
            if self.strategy == STRATEGY_PURE_API:
                raise RuntimeError(
                    f"Pure API fetch failed for {url}. "
                    "Check cookies: scraper zhihu import-cookies"
                )

        with open_zhihu_page(cdp_port=self.cdp_port) as page:
            # Strategy 1: Try API direct via browser SignatureOracle
            if self.strategy in (STRATEGY_AUTO, "api") and content_id:
                result = self._try_api_direct(page, url, content_type, content_id)
                if result:
                    self._record_success()
                    return result

            # Strategy 2: Try API intercept
            if self.strategy in (STRATEGY_AUTO, "intercept"):
                result = self._try_api_intercept(page, url, content_type, content_id)
                if result:
                    self._record_success()
                    return result

            # Strategy 3: DOM extraction (original)
            if self.strategy in (STRATEGY_AUTO, "dom"):
                return self._dom_extract(page, url)

            raise RuntimeError(f"All extraction strategies failed for {url}")

    def _try_pure_api(
        self,
        url: str,
        content_type: Optional[str],
        content_id: Optional[str],
    ) -> Optional[ArticleDetail]:
        """Attempt pure API fetch (no browser required)."""
        if not content_id:
            return None

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
                if content_type == "answer":
                    result = client.fetch_answer(content_id)
                elif content_type == "article":
                    result = client.fetch_article(content_id)
                else:
                    return None

                if result:
                    result.data_source = "pure_api"
                    logger.info("Pure API fetch successful for %s", url)
                    return result
            finally:
                client.close()

        except Exception as e:
            logger.debug("Pure API fetch failed: %s", e)

        return None

    def _try_api_direct(
        self,
        page: Page,
        url: str,
        content_type: Optional[str],
        content_id: Optional[str],
    ) -> Optional[ArticleDetail]:
        """Attempt API direct fetch via SignatureOracle."""
        if not content_id:
            return None

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
                if content_type == "answer":
                    result = client.fetch_answer(content_id)
                elif content_type == "article":
                    result = client.fetch_article(content_id)
                else:
                    return None

                if result:
                    result.data_source = "api_direct"
                    logger.info("API direct fetch successful for %s", url)
                    return result
            finally:
                client.close()

        except Exception as e:
            logger.debug("API direct fetch failed: %s", e)

        return None

    def _try_api_intercept(
        self,
        page: Page,
        url: str,
        content_type: Optional[str],
        content_id: Optional[str],
    ) -> Optional[ArticleDetail]:
        """Attempt API intercept during page navigation."""
        try:
            from .interceptor import ResponseInterceptor, parse_api_article

            # Determine which patterns to listen for
            patterns = []
            if content_type == "answer":
                patterns = ["answer"]
            elif content_type == "article":
                patterns = ["article"]
            else:
                patterns = ["answer", "article"]

            interceptor = ResponseInterceptor()
            interceptor.start(page, patterns)

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=Timeouts.NAVIGATION)
                page.wait_for_timeout(3000)

                # Check for blocks
                block_status = self._detector.check_page(page)
                if block_status.is_blocked:
                    self._handle_block(block_status, page)
                    if block_status.block_type in (BlockType.CAPTCHA, BlockType.SESSION_EXPIRED):
                        interceptor.stop()
                        return None

                captures = interceptor.stop()
            except Exception:
                interceptor.stop()
                raise

            # Parse captured responses
            for cap in captures:
                if cap.body and cap.pattern_name in ("answer", "article"):
                    result = parse_api_article(cap.body, url)
                    if result and result.content:
                        result.data_source = "api_intercept"
                        logger.info("API intercept fetch successful for %s", url)
                        return result

        except Exception as e:
            logger.debug("API intercept fetch failed: %s", e)

        return None

    def _dom_extract(self, page: Page, url: str) -> ArticleDetail:
        """Original DOM-based extraction (fallback)."""
        # Navigate if not already on the page
        current = page.url
        if url not in current:
            page.goto(url, wait_until="domcontentloaded", timeout=Timeouts.NAVIGATION)
            page.wait_for_timeout(3000)

        if not wait_for_unblock(page, timeout_ms=60_000):
            raise RuntimeError("Blocked by Zhihu security verification")

        if "signin" in page.url:
            raise RuntimeError(
                "Not logged in. Log in to Chrome first, or run 'scraper zhihu login'"
            )

        # Wait for content to load
        try:
            page.wait_for_selector(
                Selectors.ARTICLE_CONTENT,
                timeout=Timeouts.RESULT_LOAD,
            )
        except PlaywrightTimeout:
            logger.warning("Content selector not found, extracting what's available")

        # Expand truncated content
        expand_btn = page.query_selector(
            "button:has-text('展开阅读全文'), button:has-text('阅读全文')"
        )
        if expand_btn:
            try:
                expand_btn.click()
                page.wait_for_timeout(1000)
            except Exception:
                pass

        self._record_success()
        return _extract_article(page, url)

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
