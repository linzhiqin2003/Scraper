"""Section scraper for Reuters."""

import time
from typing import List, Optional

from playwright.sync_api import Page, ElementHandle, TimeoutError as PlaywrightTimeout

from ....core.base import BaseScraper
from ..config import SOURCE_NAME, BASE_URL, SECTIONS, ScraperSelectors
from ..models import SectionArticle, SectionInfo


class SectionScraper(BaseScraper):
    """Scraper for Reuters section/category pages."""

    SOURCE_NAME = SOURCE_NAME
    BASE_URL = BASE_URL
    RATE_LIMIT_PATTERN = ScraperSelectors.RATE_LIMIT_TEXT

    def get_sections(self) -> List[SectionInfo]:
        """Get all available sections.

        Returns:
            List of SectionInfo objects.
        """
        return [
            SectionInfo(
                name=info["name"],
                slug=slug,
                url=f"{BASE_URL}{info['url']}",
            )
            for slug, info in SECTIONS.items()
        ]

    def list_articles(
        self,
        section: str,
        max_articles: int = 10,
        page: Optional[Page] = None,
    ) -> List[SectionArticle]:
        """List latest articles from a section.

        Args:
            section: Section slug (e.g., "world/china", "business").
            max_articles: Maximum number of articles to return.
            page: Optional existing Page instance to use.

        Returns:
            List of SectionArticle objects.

        Raises:
            ValueError: If section is not valid.
        """
        if section not in SECTIONS:
            valid_sections = ", ".join(SECTIONS.keys())
            raise ValueError(
                f"Invalid section: {section}. Valid sections: {valid_sections}"
            )

        section_url = f"{BASE_URL}{SECTIONS[section]['url']}"

        if page is not None:
            return self._do_list_articles(page, section_url, max_articles)

        with self.get_page() as p:
            return self._do_list_articles(p, section_url, max_articles)

    def _do_list_articles(
        self, page: Page, section_url: str, max_articles: int
    ) -> List[SectionArticle]:
        """Perform the actual article listing."""
        page.goto(section_url, wait_until="domcontentloaded", timeout=30000)

        try:
            page.wait_for_selector("main", timeout=10000)
        except Exception:
            pass

        time.sleep(2)

        if self.check_rate_limit(page):
            self.handle_rate_limit(page)

        self.wait_for_element(page, ScraperSelectors.SECTION_ARTICLE_ITEM, timeout=60)

        items = page.query_selector_all(ScraperSelectors.SECTION_ARTICLE_ITEM)
        if not items:
            items = page.query_selector_all('main li a[href*="-202"]')
            if not items:
                time.sleep(3)
                page.reload(wait_until="networkidle")
                time.sleep(2)

        self._load_more_until(page, max_articles)

        return self._parse_articles(page, max_articles)

    def _load_more_until(
        self,
        page: Page,
        target_count: int,
        max_clicks: int = 20,
        click_delay: float = 1.5,
    ) -> int:
        """Click 'Load more' button until we have enough articles."""
        no_new_count = 0
        prev_count = 0

        for _ in range(max_clicks):
            items = page.query_selector_all(ScraperSelectors.SECTION_ARTICLE_ITEM)
            current_count = len(items)

            if current_count >= target_count:
                break

            if current_count == prev_count:
                no_new_count += 1
                if no_new_count >= 3:
                    break
            else:
                no_new_count = 0

            prev_count = current_count

            try:
                load_more_btn = page.query_selector(ScraperSelectors.SECTION_LOAD_MORE)
                if not load_more_btn:
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(0.5)
                    load_more_btn = page.query_selector(ScraperSelectors.SECTION_LOAD_MORE)

                if load_more_btn:
                    load_more_btn.scroll_into_view_if_needed()
                    time.sleep(0.3)
                    load_more_btn.click()
                    time.sleep(click_delay)
                else:
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    time.sleep(click_delay)

            except PlaywrightTimeout:
                time.sleep(click_delay)
                continue
            except Exception:
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(click_delay)

        items = page.query_selector_all(ScraperSelectors.SECTION_ARTICLE_ITEM)
        return len(items)

    def _parse_articles(
        self, page: Page, max_articles: int
    ) -> List[SectionArticle]:
        """Parse article items from section page."""
        articles: List[SectionArticle] = []
        seen_urls: set = set()

        items = page.query_selector_all(ScraperSelectors.SECTION_ARTICLE_ITEM)

        for item in items:
            if len(articles) >= max_articles:
                break

            try:
                article = self._parse_single_article(item)
                if article and article.url not in seen_urls:
                    seen_urls.add(article.url)
                    articles.append(article)
            except Exception:
                continue

        return articles

    def _parse_single_article(self, item: ElementHandle) -> Optional[SectionArticle]:
        """Parse a single article item from section."""
        title_el = item.query_selector(ScraperSelectors.SECTION_ARTICLE_TITLE)
        if not title_el:
            title_el = item.query_selector("a[href*='/']")
        if not title_el:
            return None

        title = title_el.text_content()
        url = title_el.get_attribute("href")

        if not title or not url:
            return None

        if not url or "-202" not in url:
            all_links = item.query_selector_all("a[href*='-202']")
            if all_links:
                title_el = all_links[0]
                title = title_el.text_content()
                url = title_el.get_attribute("href")
            else:
                return None

        summary = self.safe_get_text(item, ScraperSelectors.SECTION_ARTICLE_SUMMARY)

        published_at = None
        try:
            time_el = item.query_selector(ScraperSelectors.SECTION_ARTICLE_TIME)
            if time_el:
                published_at = time_el.get_attribute("datetime")
                if not published_at:
                    published_at = time_el.text_content()
        except Exception:
            pass

        thumbnail_url = None
        try:
            thumb_el = item.query_selector(ScraperSelectors.SECTION_ARTICLE_THUMBNAIL)
            if thumb_el:
                thumbnail_url = thumb_el.get_attribute("src")
        except Exception:
            pass

        return SectionArticle(
            title=title.strip() if title else "",
            summary=summary.strip() if summary else None,
            url=self.normalize_url(url),
            published_at=published_at.strip() if published_at else None,
            thumbnail_url=thumbnail_url,
        )

    def scrape(self, section: str, max_articles: int = 10, **kwargs) -> List[SectionArticle]:
        """Main scraping method - alias for list_articles."""
        return self.list_articles(section, max_articles, **kwargs)
