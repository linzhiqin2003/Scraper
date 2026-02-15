"""WSJ article scraper using httpx."""
import json
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import httpx
from bs4 import BeautifulSoup

from ....core.rate_limiter import RateLimiter
from ..config import SOURCE_NAME, BASE_URL, DEFAULT_HEADERS
from ..models import ArticleDetail
from ..cookies import load_cookies


def parse_datetime_text(text: str) -> Optional[datetime]:
    """Parse time text like 'Jan. 28, 2026 2:59 am ET'."""
    patterns = [
        r"(\w+\.?\s+\d+,?\s+\d{4}\s+\d+:\d+\s*[ap]m)",
        r"(\w+\s+\d+,?\s+\d{4})",
        r"(\d{1,2}/\d{1,2}/\d{2,4})",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            date_str = match.group(1)
            for fmt in [
                "%b. %d, %Y %I:%M %p",
                "%b %d, %Y %I:%M %p",
                "%B %d, %Y %I:%M %p",
                "%b. %d, %Y",
                "%b %d, %Y",
                "%B %d, %Y",
                "%m/%d/%Y",
            ]:
                try:
                    return datetime.strptime(date_str.strip(), fmt)
                except ValueError:
                    continue
    return None


def parse_article_html(html: str, url: str) -> ArticleDetail:
    """Parse article HTML page."""
    soup = BeautifulSoup(html, "lxml")

    # Check paywall
    is_paywalled = False
    if soup.select_one('button:-soup-contains("Subscribe Now")'):
        is_paywalled = True
    if soup.select_one(':-soup-contains("Special Offer")'):
        is_paywalled = True

    # Extract title
    h1 = soup.find("h1")
    title = h1.get_text(strip=True) if h1 else ""

    # Extract subtitle
    subtitle = None
    h2 = soup.select_one("h1 + h2, h1 ~ h2")
    if h2:
        text = h2.get_text(strip=True)
        if 10 < len(text) < 500:
            subtitle = text

    # Extract author
    author = None
    author_url = None
    author_link = soup.select_one('a[href*="/news/author/"]')
    if author_link:
        author = author_link.get_text(strip=True)
        author_url = author_link.get("href")

    # Extract time - prefer <time> tag, fallback to meta tags
    published_at = None
    published_at_raw = None

    # 1. Try <time> tag
    time_el = soup.find("time")
    if time_el:
        published_at_raw = time_el.get_text(strip=True)
        datetime_attr = time_el.get("datetime")
        if datetime_attr:
            try:
                published_at = datetime.fromisoformat(
                    datetime_attr.replace("Z", "+00:00")
                )
            except ValueError:
                pass
        if not published_at and published_at_raw:
            published_at = parse_datetime_text(published_at_raw)

    # 2. Fallback: meta tags (article:published_time, article.published)
    if not published_at:
        for meta_name in ["article:published_time", "article.published"]:
            meta_el = (
                soup.find("meta", attrs={"property": meta_name})
                or soup.find("meta", attrs={"name": meta_name})
            )
            if meta_el and meta_el.get("content"):
                try:
                    published_at = datetime.fromisoformat(
                        meta_el["content"].replace("Z", "+00:00")
                    )
                    published_at_raw = meta_el["content"]
                    break
                except ValueError:
                    pass

    # 3. Fallback: Live Coverage - extract from __NEXT_DATA__ JSON
    if not published_at and "/livecoverage/" in url:
        next_data_script = soup.find("script", id="__NEXT_DATA__")
        if next_data_script and next_data_script.string:
            try:
                data = json.loads(next_data_script.string)
                # Try liveBlogUpdate for card pages
                seo_schema = data.get("props", {}).get("pageProps", {}).get("seoSchema", [])
                if seo_schema:
                    live_updates = seo_schema[0].get("liveBlogUpdate", [])
                    if live_updates:
                        # Use dateModified (Last Updated) or datePublished
                        date_str = live_updates[0].get("dateModified") or live_updates[0].get("datePublished")
                        if date_str:
                            published_at = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                            published_at_raw = date_str
            except (json.JSONDecodeError, KeyError, IndexError, ValueError):
                pass

    # Extract category
    category = None
    subcategory = None
    breadcrumb_links = soup.select('nav[aria-label*="breadcrumb"] a')
    categories = [
        a.get_text(strip=True)
        for a in breadcrumb_links
        if a.get_text(strip=True) not in ["Home", "WSJ"]
    ]
    if len(categories) >= 2:
        category, subcategory = categories[0], categories[1]
    elif len(categories) == 1:
        category = categories[0]

    # Extract paragraphs
    paragraphs: List[str] = []
    content_container = soup.find("article") or soup.find("main")
    if content_container:
        for p in content_container.find_all("p"):
            text = p.get_text(strip=True)
            if not text or len(text) < 30:
                continue
            if "Copyright" in text or "All Rights Reserved" in text:
                continue
            if text.startswith("By ") and len(text) < 100:
                continue
            paragraphs.append(text)

    content = "\n\n".join(paragraphs)

    # Extract images
    images: List[dict] = []
    if content_container:
        for img in content_container.find_all("img"):
            src = img.get("src") or img.get("data-src")
            if not src:
                continue
            if "1x1" in src or "pixel" in src or "icon" in src:
                continue
            alt = img.get("alt", "")
            images.append({"src": src, "alt": alt})

    return ArticleDetail(
        url=url,
        title=title,
        subtitle=subtitle,
        author=author,
        author_url=author_url,
        published_at=published_at,
        published_at_raw=published_at_raw,
        category=category,
        subcategory=subcategory,
        content=content,
        paragraphs=paragraphs,
        images=images,
        is_paywalled=is_paywalled,
        scraped_at=datetime.now(),
    )


class ArticleScraper:
    """WSJ article scraper using httpx."""

    SOURCE_NAME = SOURCE_NAME
    BASE_URL = BASE_URL

    def __init__(
        self,
        cookies_path: Optional[Path] = None,
        rate_limiter: Optional[RateLimiter] = None,
    ):
        """Initialize scraper with cookies.

        Args:
            cookies_path: Optional path to cookies file.
            rate_limiter: Optional rate limiter for request throttling.
        """
        self.cookies = load_cookies(cookies_path)
        self.rate_limiter = rate_limiter

    def scrape(self, url: str) -> ArticleDetail:
        """
        Scrape a single article.

        Args:
            url: Article URL

        Returns:
            ArticleDetail object

        Raises:
            Exception: HTTP errors or access restrictions
        """
        with httpx.Client(
            cookies=self.cookies,
            headers=DEFAULT_HEADERS,
            follow_redirects=True,
            timeout=30.0,
        ) as client:
            response = client.get(url)

            if response.status_code == 401:
                raise Exception("401 Unauthorized: Cookies may be expired")

            if response.status_code != 200:
                raise Exception(f"HTTP {response.status_code}: {response.text[:200]}")

            html = response.text

        # Check access restrictions
        if "Access is temporarily restricted" in html or "captcha-delivery" in html:
            raise Exception("Access restricted, CAPTCHA required")

        return parse_article_html(html, url)

    def scrape_batch(
        self,
        urls: List[str],
        delay: float = 1.0,
    ) -> List[dict]:
        """
        Scrape multiple articles.

        Args:
            urls: List of article URLs
            delay: Delay between requests in seconds

        Returns:
            List of result dicts with status, url, title/error
        """
        import time

        results = []

        for i, url in enumerate(urls, 1):
            try:
                article = self.scrape(url)
                results.append(
                    {
                        "status": "success",
                        "url": url,
                        "title": article.title,
                        "article": article,
                    }
                )
            except Exception as e:
                results.append(
                    {
                        "status": "error",
                        "url": url,
                        "error": str(e),
                    }
                )

            if i < len(urls):
                time.sleep(delay)

        return results
