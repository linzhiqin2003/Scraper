"""Article scraper for Reuters."""

import time
from typing import List, Optional

from playwright.sync_api import Page

from ....core.base import BaseScraper
from ....core.exceptions import ContentNotFoundError, PaywallError, CaptchaError
from ....converters.markdown import html_to_markdown
from ..config import SOURCE_NAME, BASE_URL, ScraperSelectors
from ..models import Article, ArticleImage


class ArticleScraper(BaseScraper):
    """Scraper for Reuters article pages."""

    SOURCE_NAME = SOURCE_NAME
    BASE_URL = BASE_URL
    RATE_LIMIT_PATTERN = ScraperSelectors.RATE_LIMIT_TEXT

    def fetch(self, url: str, page: Optional[Page] = None) -> Article:
        """Fetch and parse a full article.

        Args:
            url: Article URL (absolute or relative).
            page: Optional existing Page instance to use.

        Returns:
            Article object with full content.

        Raises:
            ContentNotFoundError: If article not found.
            PaywallError: If article is behind paywall.
        """
        full_url = self.normalize_url(url)

        if page is not None:
            return self._do_fetch(page, full_url, url)

        with self.get_page() as p:
            return self._do_fetch(p, full_url, url)

    def _do_fetch(self, page: Page, full_url: str, original_url: str) -> Article:
        """Perform the actual fetch operation."""
        page.goto(full_url, wait_until="domcontentloaded", timeout=30000)

        try:
            page.wait_for_selector("h1, article, main", timeout=10000)
        except Exception:
            pass

        time.sleep(2)

        if "Page Not Found" in page.title() or "404 Error" in page.title():
            raise ContentNotFoundError(f"Article not found: {original_url}")

        if self._check_captcha(page):
            if self.headless:
                raise CaptchaError(
                    "CAPTCHA verification required. "
                    "Run without --headless flag to complete verification manually."
                )
            print("Please complete the CAPTCHA verification in the browser...")
            self.wait_for_element(page, "h1", timeout=120)
            time.sleep(2)

        if self.check_rate_limit(page):
            self.handle_rate_limit(page)

        if self._check_paywall(page):
            raise PaywallError(f"Article is behind paywall: {original_url}")

        self.wait_for_element(page, ScraperSelectors.ARTICLE_BODY, timeout=30)

        return self._parse_article(page, full_url)

    def _check_captcha(self, page: Page) -> bool:
        """Check if page shows CAPTCHA verification."""
        content = page.content()
        captcha_indicators = [
            "Verification Required",
            "verify you are human",
            "captcha",
            "Slide right to secure",
        ]
        return any(indicator.lower() in content.lower() for indicator in captcha_indicators)

    def _check_paywall(self, page: Page) -> bool:
        """Check if article is behind paywall."""
        try:
            el = page.query_selector(ScraperSelectors.PAYWALL_INDICATOR)
            return el is not None
        except Exception:
            return False

    def _parse_article(self, page: Page, url: str) -> Article:
        """Parse article content from page."""
        title = self._safe_get_text_from_page(page, ScraperSelectors.ARTICLE_TITLE)
        if not title:
            title = page.title()

        author = self._get_author(page)
        published_at = self._get_publish_time(page)
        content_markdown = self._get_content_markdown(page)
        images = self._get_images(page)
        tags = self._get_tags(page)

        return Article(
            title=title.strip() if title else "Untitled",
            url=url,
            author=author,
            published_at=published_at,
            content_markdown=content_markdown,
            images=images,
            tags=tags,
        )

    def _safe_get_text_from_page(
        self, page: Page, selector: str, default: Optional[str] = None
    ) -> Optional[str]:
        """Safely get text from page element."""
        try:
            el = page.query_selector(selector)
            if el:
                return el.text_content()
        except Exception:
            pass
        return default

    def _get_author(self, page: Page) -> Optional[str]:
        """Get article author(s)."""
        selectors = [
            ScraperSelectors.ARTICLE_AUTHOR,
            '[data-testid="author"]',
            '.author',
            '[class*="Author"]',
        ]

        for selector in selectors:
            author = self._safe_get_text_from_page(page, selector)
            if author:
                return author.strip()

        return None

    def _get_publish_time(self, page: Page) -> Optional[str]:
        """Get article publish time."""
        try:
            time_el = page.query_selector(ScraperSelectors.ARTICLE_TIME)
            if time_el:
                datetime_attr = time_el.get_attribute("datetime")
                if datetime_attr:
                    return datetime_attr
                text = time_el.text_content()
                return text.strip() if text else None
        except Exception:
            pass
        return None

    def _get_content_markdown(self, page: Page) -> str:
        """Get article body content as markdown."""
        try:
            paragraphs = page.query_selector_all(ScraperSelectors.ARTICLE_PARAGRAPH)
            texts = []
            for p in paragraphs:
                text = p.text_content()
                if text and text.strip():
                    texts.append(text.strip())
            if texts:
                return "\n\n".join(texts)
        except Exception:
            pass

        try:
            body_el = page.query_selector(ScraperSelectors.ARTICLE_BODY)
            if body_el:
                html_content = body_el.inner_html()
                return html_to_markdown(html_content)
        except Exception:
            pass

        return ""

    def _get_images(self, page: Page) -> List[ArticleImage]:
        """Get article images."""
        images: List[ArticleImage] = []

        try:
            img_elements = page.query_selector_all(ScraperSelectors.ARTICLE_IMAGE)

            for img_el in img_elements:
                src = img_el.get_attribute("src")
                if not src:
                    continue

                caption = None
                try:
                    figure = img_el.evaluate_handle(
                        "el => el.closest('figure')"
                    ).as_element()
                    if figure:
                        caption_el = figure.query_selector(ScraperSelectors.ARTICLE_IMAGE_CAPTION)
                        if caption_el:
                            caption = caption_el.text_content()
                except Exception:
                    pass

                images.append(
                    ArticleImage(
                        url=src,
                        caption=caption.strip() if caption else None,
                    )
                )
        except Exception:
            pass

        return images

    def _get_tags(self, page: Page) -> List[str]:
        """Get article tags/topics."""
        tags: List[str] = []

        try:
            tag_elements = page.query_selector_all(ScraperSelectors.ARTICLE_TAGS)
            for tag_el in tag_elements:
                text = tag_el.text_content()
                if text and text.strip() and text.strip() not in tags:
                    if "Suggested Topics" not in text:
                        tags.append(text.strip())
        except Exception:
            pass

        return tags

    def scrape(self, url: str, **kwargs) -> Article:
        """Main scraping method - alias for fetch."""
        return self.fetch(url, **kwargs)
