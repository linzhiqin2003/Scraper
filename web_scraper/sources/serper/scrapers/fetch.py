"""Generic web article fetcher for Serper source.

Wraps the Scholar ArticleScraper (which is a generic article fetcher)
and returns WebArticle models.
"""
from pathlib import Path
from typing import Optional

from ...scholar.scrapers.article import ArticleScraper as _ArticleScraper
from ..models import WebArticle


class ArticleFetcher:
    """Fetch full content from any web URL.

    Uses a three-tier fallback strategy:
    1. curl-cffi (Chrome TLS fingerprint impersonation)
    2. httpx (plain HTTP)
    3. Playwright headless Chrome (if enabled)
    """

    def __init__(
        self,
        cookies_path: Optional[Path] = None,
        use_playwright: bool = True,
    ):
        self._scraper = _ArticleScraper(
            cookies_path=cookies_path,
            use_playwright=use_playwright,
        )

    def fetch(self, url: str) -> WebArticle:
        """Fetch and extract content from a URL.

        Args:
            url: Target URL.

        Returns:
            WebArticle with extracted content.

        Raises:
            Exception: If all fetch methods fail.
        """
        result = self._scraper.scrape(url)
        return WebArticle(
            url=result.url,
            title=result.title,
            content=result.content,
            published_date=result.published_date,
            is_accessible=result.is_accessible,
            is_pdf=result.is_pdf,
        )
