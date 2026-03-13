"""WeChat MP article scraper.

Fetches and parses public WeChat articles via HTTP.
Uses curl-cffi for TLS fingerprint impersonation to avoid blocks.
"""
import logging
import re
import time
from datetime import datetime
from typing import List, Optional

from bs4 import BeautifulSoup
from markdownify import markdownify as md

from ....core.http_client import HttpClient
from ..config import RATE_LIMIT_DELAY, Selectors, Timeouts
from ..models import WechatArticle

logger = logging.getLogger(__name__)


class ArticleScraper:
    """Fetch and parse WeChat MP articles."""

    def __init__(self):
        self._client = HttpClient(
            headers={
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
                "referer": "https://mp.weixin.qq.com/",
            },
            timeout=Timeouts.DEFAULT,
        )
        self._last_request_time = 0.0

    def fetch(self, url: str) -> WechatArticle:
        """Fetch a single article by URL.

        Args:
            url: WeChat article URL (mp.weixin.qq.com/s/...).

        Returns:
            Parsed WechatArticle.

        Raises:
            ValueError: If URL is not a valid WeChat article link.
            RuntimeError: If fetch fails or article content not found.
        """
        if "mp.weixin.qq.com" not in url:
            raise ValueError(f"Not a WeChat article URL: {url}")

        self._rate_limit()
        resp = self._client.get(url)
        self._client.raise_for_status(resp, context="WeChat article")

        html = resp.text
        return self._parse_article(html, url)

    def fetch_batch(self, urls: List[str]) -> List[WechatArticle]:
        """Fetch multiple articles with rate limiting.

        Args:
            urls: List of WeChat article URLs.

        Returns:
            List of successfully parsed articles.
        """
        articles = []
        for i, url in enumerate(urls):
            try:
                article = self.fetch(url)
                articles.append(article)
                logger.info("Fetched (%d/%d): %s", i + 1, len(urls), article.title)
            except Exception as e:
                logger.warning("Failed (%d/%d) %s: %s", i + 1, len(urls), url, e)
        return articles

    def _rate_limit(self):
        """Enforce rate limiting between requests."""
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < RATE_LIMIT_DELAY:
            time.sleep(RATE_LIMIT_DELAY - elapsed)
        self._last_request_time = time.monotonic()

    def _parse_article(self, html: str, url: str) -> WechatArticle:
        """Parse article HTML into model."""
        soup = BeautifulSoup(html, "lxml")

        # Title: prefer og:title, fallback to #activity-name
        title = self._get_meta(soup, Selectors.OG_TITLE)
        if not title:
            el = soup.select_one(Selectors.TITLE)
            title = el.get_text(strip=True) if el else ""
        if not title:
            raise RuntimeError("Could not extract article title — page may be blocked")

        # Account name
        account_el = soup.select_one(Selectors.ACCOUNT_NAME)
        account_name = account_el.get_text(strip=True) if account_el else ""

        # Description
        description = self._get_meta(soup, Selectors.OG_DESCRIPTION)

        # Cover image
        cover_image = self._get_meta(soup, Selectors.OG_IMAGE)

        # Content → Markdown
        content_el = soup.select_one(Selectors.CONTENT)
        content_md = ""
        images = []
        if content_el:
            content_md = md(content_el.decode_contents(), strip=["img", "script", "style"]).strip()
            # Extract image URLs
            for img in content_el.select("img"):
                src = img.get("data-src") or img.get("src", "")
                if src and "mmbiz.qpic.cn" in src:
                    images.append(src)

        # Extract metadata from inline script
        account_id = self._extract_script_var(html, "user_name")
        create_ts = self._extract_script_var(html, "ct")
        publish_time = None
        if create_ts and create_ts.isdigit():
            publish_time = datetime.fromtimestamp(int(create_ts))

        # Publish time fallback from #publish_time element
        if not publish_time:
            pt_el = soup.select_one(Selectors.PUBLISH_TIME)
            if pt_el:
                pt_text = pt_el.get_text(strip=True)
                if pt_text:
                    try:
                        publish_time = datetime.strptime(pt_text, "%Y-%m-%d %H:%M")
                    except ValueError:
                        pass

        return WechatArticle(
            title=title,
            account_name=account_name,
            account_id=account_id or None,
            description=description or None,
            content=content_md,
            url=url,
            cover_image=cover_image or None,
            images=images,
            publish_time=publish_time,
            create_timestamp=int(create_ts) if create_ts and create_ts.isdigit() else None,
        )

    @staticmethod
    def _get_meta(soup: BeautifulSoup, selector: str) -> str:
        """Extract content attribute from a meta tag."""
        el = soup.select_one(selector)
        if el:
            return el.get("content", "")
        return ""

    @staticmethod
    def _extract_script_var(html: str, var_name: str) -> Optional[str]:
        """Extract a JavaScript variable value from inline scripts."""
        pattern = rf'var\s+{re.escape(var_name)}\s*=\s*["\']([^"\']*)["\']'
        m = re.search(pattern, html)
        return m.group(1) if m else None
