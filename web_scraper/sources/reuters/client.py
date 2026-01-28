"""Unified Reuters client - requests first, Playwright fallback.

This module provides a unified interface that:
1. Tries HTTP/API methods first (fast, low resource)
2. Falls back to Playwright when needed (CAPTCHA, complex scenarios)
"""

import json
import re
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .config import (
    BASE_URL,
    STATE_FILE,
    SECTIONS,
    SEARCH_API,
    SECTION_API,
    DEFAULT_HEADERS,
)
from .models import Article, ArticleImage, SearchResult, SectionArticle, SectionInfo


class CaptchaRequired(Exception):
    """Raised when CAPTCHA verification is needed."""

    pass


class ReutersClient:
    """Unified Reuters client with requests-first strategy.

    This client tries HTTP requests first for speed, and falls back
    to Playwright when CAPTCHA or other issues are detected.
    """

    def __init__(self, timeout: int = 30, use_playwright_fallback: bool = True):
        """Initialize client.

        Args:
            timeout: Request timeout in seconds.
            use_playwright_fallback: Whether to fall back to Playwright on failure.
        """
        self.timeout = timeout
        self.use_playwright_fallback = use_playwright_fallback
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self._cookies_loaded = self._load_cookies()

    def _load_cookies(self) -> bool:
        """Load cookies from saved state file."""
        if not STATE_FILE.exists():
            return False

        try:
            with open(STATE_FILE) as f:
                state = json.load(f)

            count = 0
            for cookie in state.get("cookies", []):
                domain = cookie.get("domain", "")
                if "reuters.com" in domain:
                    self.session.cookies.set(
                        cookie["name"],
                        cookie["value"],
                        domain=domain,
                        path=cookie.get("path", "/"),
                    )
                    count += 1
            return count > 0
        except Exception:
            return False

    def _api_request(
        self, endpoint: str, query: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Make API request with JSON query parameter."""
        query.setdefault("website", "reuters")
        params = {"query": json.dumps(query)}
        headers = {**DEFAULT_HEADERS, "Accept": "application/json"}

        try:
            resp = self.session.get(
                endpoint, params=params, headers=headers, timeout=self.timeout
            )
            # Check for CAPTCHA redirect (401 with captcha URL)
            if resp.status_code == 401:
                try:
                    data = resp.json()
                    if "captcha" in data.get("url", "").lower():
                        return None  # API blocked by CAPTCHA
                except Exception:
                    pass
                return None
            resp.raise_for_status()
            data = resp.json()
            if data.get("result") is not None:
                return data["result"]
            return None
        except Exception:
            return None

    def _is_captcha_page(self, html: str) -> bool:
        """Check if page shows CAPTCHA."""
        indicators = [
            "Verification Required",
            "verify you are human",
            "captcha",
            "Slide right to secure",
        ]
        html_lower = html.lower()
        return any(ind.lower() in html_lower for ind in indicators)

    # ========== Search ==========

    def search(
        self,
        query: str,
        max_results: int = 20,
        section: Optional[str] = None,
        date_range: Optional[str] = None,
        sort_by: str = "relevance",
        headless: bool = True,
    ) -> List[SearchResult]:
        """Search articles - tries API first, falls back to Playwright.

        Args:
            query: Search keyword.
            max_results: Maximum results to return.
            section: Filter by section (e.g., 'world', 'business').
            date_range: Filter by date (past_24_hours, past_week, etc.).
            sort_by: Sort order (relevance, date).
            headless: Playwright headless mode (for fallback).

        Returns:
            List of SearchResult objects.
        """
        # Try API first
        results = self._search_via_api(query, max_results, section, date_range, sort_by)
        if results:
            return results

        # Fallback to Playwright
        if self.use_playwright_fallback:
            return self._search_via_playwright(
                query, max_results, section, date_range, sort_by, headless
            )

        return []

    def _search_via_api(
        self,
        query: str,
        max_results: int,
        section: Optional[str],
        date_range: Optional[str],
        sort_by: str,
    ) -> List[SearchResult]:
        """Search via API."""
        results: List[SearchResult] = []
        offset = 0
        page_size = min(20, max_results)

        sort_map = {"relevance": "relevance", "date": "date:desc"}
        sort = sort_map.get(sort_by, sort_by)

        while len(results) < max_results:
            api_query: Dict[str, Any] = {
                "keyword": query,
                "offset": offset,
                "size": page_size,
                "sort": sort,
            }
            if section:
                api_query["section"] = section
            if date_range:
                api_query["date"] = date_range

            result = self._api_request(SEARCH_API, api_query)
            if not result:
                break

            articles = result.get("articles", [])
            if not articles:
                break

            for article in articles:
                if len(results) >= max_results:
                    break
                results.append(self._parse_api_article(article))

            offset += page_size
            pagination = result.get("pagination", {})
            total = pagination.get("total", 0)
            if offset >= total:
                break

        return results

    def _search_via_playwright(
        self,
        query: str,
        max_results: int,
        section: Optional[str],
        date_range: Optional[str],
        sort_by: str,
        headless: bool,
    ) -> List[SearchResult]:
        """Search via Playwright (fallback)."""
        from .scrapers import SearchScraper

        try:
            scraper = SearchScraper(headless=headless)
            return scraper.search(
                query=query,
                max_results=max_results,
                section=section,
                date_range=date_range,
                sort_by=sort_by,
            )
        except Exception:
            return []

    def get_search_count(
        self,
        query: str,
        section: Optional[str] = None,
        date_range: Optional[str] = None,
    ) -> int:
        """Get total search result count - uses API."""
        api_query: Dict[str, Any] = {
            "keyword": query,
            "offset": 0,
            "size": 1,  # Minimal fetch
        }
        if section:
            api_query["section"] = section
        if date_range:
            api_query["date"] = date_range

        result = self._api_request(SEARCH_API, api_query)
        if result:
            return result.get("pagination", {}).get("total", 0)
        return 0

    # ========== Section ==========

    def get_section_articles(
        self,
        section: str,
        max_articles: int = 20,
        headless: bool = True,
    ) -> List[SectionArticle]:
        """Get articles from a section - tries API first, falls back to Playwright.

        Args:
            section: Section slug (e.g., 'world', 'world/china').
            max_articles: Maximum articles to return.
            headless: Playwright headless mode (for fallback).

        Returns:
            List of SectionArticle objects.
        """
        # Try API first
        results = self._get_section_via_api(section, max_articles)
        if results:
            return results

        # Fallback to Playwright
        if self.use_playwright_fallback:
            return self._get_section_via_playwright(section, max_articles, headless)

        return []

    def _get_section_via_api(
        self, section: str, max_articles: int
    ) -> List[SectionArticle]:
        """Get section articles via API."""
        # Normalize section to path format
        section_id = section
        if not section_id.startswith("/"):
            section_id = "/" + section_id
        if not section_id.endswith("/"):
            section_id = section_id + "/"

        results: List[SectionArticle] = []
        offset = 0
        page_size = min(20, max_articles)

        while len(results) < max_articles:
            api_query = {
                "section_id": section_id,
                "offset": offset,
                "size": page_size,
            }

            result = self._api_request(SECTION_API, api_query)
            if not result:
                break

            articles = result.get("articles", [])
            if not articles:
                break

            for article in articles:
                if len(results) >= max_articles:
                    break
                results.append(self._parse_api_section_article(article))

            offset += page_size

        return results

    def _get_section_via_playwright(
        self, section: str, max_articles: int, headless: bool
    ) -> List[SectionArticle]:
        """Get section articles via Playwright (fallback)."""
        from .scrapers import SectionScraper

        try:
            scraper = SectionScraper(headless=headless)
            return scraper.list_articles(section=section, max_articles=max_articles)
        except Exception:
            return []

    def get_sections(self) -> List[SectionInfo]:
        """Get all available sections."""
        return [
            SectionInfo(
                name=info["name"],
                slug=slug,
                url=urljoin(BASE_URL, info["url"]),
            )
            for slug, info in SECTIONS.items()
        ]

    # ========== Article ==========

    def fetch_article(
        self,
        url: str,
        use_playwright: bool = False,
        headless: bool = True,
        on_captcha: Optional[Callable[[], None]] = None,
        include_images: bool = False,
    ) -> Optional[Article]:
        """Fetch full article content.

        Tries HTTP first, falls back to Playwright if CAPTCHA detected.

        Args:
            url: Article URL (absolute or relative).
            use_playwright: Force Playwright mode.
            headless: Playwright headless mode (only if using Playwright).
            on_captcha: Callback when CAPTCHA is detected.
            include_images: Include image URLs in result (default: False).

        Returns:
            Article object or None on failure.

        Raises:
            CaptchaRequired: If CAPTCHA detected and no fallback available.
        """
        # Normalize URL
        if not url.startswith("http"):
            url = urljoin(BASE_URL, url)

        # Try HTTP first (unless forced to use Playwright)
        if not use_playwright:
            try:
                resp = self.session.get(url, timeout=self.timeout)
                resp.raise_for_status()

                if self._is_captcha_page(resp.text):
                    if on_captcha:
                        on_captcha()
                    if self.use_playwright_fallback:
                        return self._fetch_article_playwright(url, headless)
                    raise CaptchaRequired("CAPTCHA verification required")

                return self._parse_article_html(resp.text, url, include_images)
            except CaptchaRequired:
                raise
            except requests.RequestException:
                # Network error - try Playwright fallback
                if self.use_playwright_fallback:
                    return self._fetch_article_playwright(url, headless)
                return None

        # Use Playwright directly
        return self._fetch_article_playwright(url, headless)

    def _fetch_article_playwright(
        self, url: str, headless: bool = True
    ) -> Optional[Article]:
        """Fetch article using Playwright (fallback)."""
        from .scrapers import ArticleScraper

        try:
            scraper = ArticleScraper(headless=headless)
            return scraper.fetch(url)
        except Exception:
            return None

    # ========== Parsing ==========

    def _parse_api_article(self, data: Dict[str, Any]) -> SearchResult:
        """Parse API article response into SearchResult."""
        title = data.get("title") or data.get("headlines", {}).get("basic", "")
        url = data.get("canonical_url") or data.get("website_url", "")
        if url and not url.startswith("http"):
            url = urljoin(BASE_URL, url)

        description = data.get("description", "")
        if isinstance(description, dict):
            description = description.get("basic", "")

        published_at = (
            data.get("published_time")
            or data.get("display_time")
            or data.get("first_publish_date")
        )

        authors = data.get("authors", [])
        author = None
        if authors:
            author_names = [a.get("name", "") for a in authors if a.get("name")]
            author = ", ".join(author_names) if author_names else None

        thumbnail = None
        promo_items = data.get("promo_items", {})
        if promo_items:
            basic = promo_items.get("basic", {})
            thumbnail = basic.get("url")

        # Extract category from URL
        category = None
        if url:
            match = re.search(r"reuters\.com/([^/]+)/", url)
            if match:
                category = match.group(1)

        return SearchResult(
            title=title,
            url=url,
            summary=description,
            published_at=published_at,
            author=author,
            thumbnail=thumbnail,
            category=category,
        )

    def _parse_api_section_article(self, data: Dict[str, Any]) -> SectionArticle:
        """Parse API article response into SectionArticle."""
        title = data.get("title") or data.get("headlines", {}).get("basic", "")
        url = data.get("canonical_url") or data.get("website_url", "")
        if url and not url.startswith("http"):
            url = urljoin(BASE_URL, url)

        description = data.get("description", "")
        if isinstance(description, dict):
            description = description.get("basic", "")

        published_at = (
            data.get("published_time")
            or data.get("display_time")
            or data.get("first_publish_date")
        )

        thumbnail = None
        promo_items = data.get("promo_items", {})
        if promo_items:
            basic = promo_items.get("basic", {})
            thumbnail = basic.get("url")

        return SectionArticle(
            title=title,
            url=url,
            summary=description,
            published_at=published_at,
            thumbnail_url=thumbnail,
        )

    def _parse_article_html(
        self, html: str, url: str, include_images: bool = False
    ) -> Article:
        """Parse article content from HTML."""
        soup = BeautifulSoup(html, "lxml")

        # Title
        title_el = soup.select_one('h1[data-testid="Heading"]')
        title = title_el.get_text(strip=True) if title_el else ""
        if not title and soup.title:
            title = soup.title.string or ""

        # Author
        author_el = soup.select_one('[data-testid="AuthorNameLink"]')
        author = author_el.get_text(strip=True) if author_el else None

        # Published time
        time_el = soup.select_one('time[data-testid="DateLine"]')
        published_at = None
        if time_el:
            published_at = time_el.get("datetime") or time_el.get_text(strip=True)

        # Content
        paragraphs = soup.select('[class*="article-body-module__paragraph"]')
        content = "\n\n".join(
            p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)
        )

        # Images (optional)
        images: List[ArticleImage] = []
        if include_images:
            for img in soup.select(
                '[data-testid="ArticleBody"] img, [data-testid="Image"] img'
            ):
                src = img.get("src")
                if src:
                    figure = img.find_parent("figure")
                    caption = None
                    if figure:
                        caption_el = figure.select_one("figcaption")
                        if caption_el:
                            caption = caption_el.get_text(strip=True)
                    images.append(ArticleImage(url=src, caption=caption))

        # Tags
        tags = []
        for tag_el in soup.select('[class*="tags-line"] a[data-testid="TextButton"]'):
            tag_text = tag_el.get_text(strip=True)
            if tag_text and "Suggested Topics" not in tag_text:
                tags.append(tag_text)

        return Article(
            title=title,
            url=url,
            author=author,
            published_at=published_at,
            content_markdown=content,
            images=images,
            tags=tags,
        )

    # ========== Utilities ==========

    def check_login_status(self) -> bool:
        """Check if currently logged in (via HTTP)."""
        try:
            resp = self.session.get(BASE_URL, timeout=self.timeout)
            return 'href="/account/sign-in"' not in resp.text
        except Exception:
            return False

    def is_ready(self) -> bool:
        """Check if client has cookies loaded."""
        return self._cookies_loaded
