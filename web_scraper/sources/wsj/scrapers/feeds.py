"""WSJ RSS feeds scraper."""
import asyncio
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import List, Optional

import feedparser
import httpx

from ..config import SOURCE_NAME, FEEDS
from ..models import FeedArticle, FeedResponse


def parse_pub_date(date_str: Optional[str]) -> datetime:
    """Parse RSS pubDate to datetime."""
    if not date_str:
        return datetime.now()
    try:
        return parsedate_to_datetime(date_str)
    except (ValueError, TypeError):
        return datetime.now()


async def fetch_feed(feed_url: str) -> str:
    """Fetch RSS feed content."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            feed_url,
            headers={"User-Agent": "WebScraper/1.0"},
            timeout=30.0,
        )
        resp.raise_for_status()
        return resp.text


def parse_feed(feed_content: str, category: str) -> List[FeedArticle]:
    """Parse RSS feed content into FeedArticle objects."""
    feed = feedparser.parse(feed_content)
    articles = []

    for entry in feed.entries:
        # Extract image URL if available
        images = []
        if hasattr(entry, "media_content"):
            for media in entry.media_content:
                if media.get("url"):
                    images.append(media["url"])

        article = FeedArticle(
            url=entry.get("link", ""),
            title=entry.get("title", ""),
            description=entry.get("description", entry.get("summary", "")),
            published_at=parse_pub_date(entry.get("published")),
            category=category,
            author=entry.get("author"),
            images=images,
        )
        articles.append(article)

    return articles


class FeedScraper:
    """WSJ RSS feed scraper."""

    SOURCE_NAME = SOURCE_NAME
    FEEDS = FEEDS

    def get_categories(self) -> List[str]:
        """Return available feed categories."""
        return list(FEEDS.keys())

    async def fetch_async(
        self,
        category: Optional[str] = None,
    ) -> FeedResponse:
        """
        Fetch articles from RSS feeds asynchronously.

        Args:
            category: Specific category to fetch, or None for all.

        Returns:
            FeedResponse with articles.
        """
        if category:
            if category not in FEEDS:
                raise ValueError(
                    f"Unknown category: {category}. Available: {list(FEEDS.keys())}"
                )
            feeds_to_fetch = {category: FEEDS[category]}
        else:
            feeds_to_fetch = FEEDS

        all_articles: List[FeedArticle] = []
        seen_urls = set()

        for cat, url in feeds_to_fetch.items():
            try:
                content = await fetch_feed(url)
                articles = parse_feed(content, cat)

                for article in articles:
                    if article.url not in seen_urls:
                        seen_urls.add(article.url)
                        all_articles.append(article)
            except httpx.RequestError as e:
                print(f"Error fetching {cat} feed: {e}")
                continue

        # Sort by publication date (newest first)
        all_articles.sort(key=lambda a: a.published_at, reverse=True)

        return FeedResponse(
            category=category or "all",
            articles=all_articles,
            total=len(all_articles),
        )

    def fetch(self, category: Optional[str] = None) -> FeedResponse:
        """
        Fetch articles from RSS feeds synchronously.

        Args:
            category: Specific category to fetch, or None for all.

        Returns:
            FeedResponse with articles.
        """
        return asyncio.get_event_loop().run_until_complete(
            self.fetch_async(category)
        )
