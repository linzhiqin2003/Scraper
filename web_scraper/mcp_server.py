"""MCP Server for news search - Reuters and WSJ."""

import time
from typing import List, Optional

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    name="news-search",
    instructions="Search news from Reuters and Wall Street Journal. "
                 "Use reuters_search for Reuters news, wsj_search for WSJ news. "
                 "Both tools return standardized article data with optional full content.",
)


@mcp.tool()
def reuters_search(
    query: str,
    limit: int = 10,
    fetch_content: bool = True,
    section: Optional[str] = None,
    date_range: Optional[str] = None,
) -> List[dict]:
    """Search Reuters for news articles.

    Args:
        query: Search keywords (e.g., "Fed interest rate", "Tesla earnings")
        limit: Maximum number of articles (default: 10, max: 30)
        fetch_content: Whether to fetch full article content (default: True)
        section: Filter by section (e.g., "business", "world", "technology")
        date_range: Filter by date (past_24_hours, past_week, past_month, past_year)

    Returns:
        List of articles. Each article contains:
        - title: Article headline
        - url: Full article URL
        - published_at: Publication time
        - author: Author name (if available)
        - summary: Article summary
        - content: Full article content in markdown (only if fetch_content=True)
        - tags: Article tags (only if fetch_content=True)

    Example:
        reuters_search("Federal Reserve", limit=5)
        reuters_search("climate change", limit=10, fetch_content=False)
    """
    from .sources.reuters.client import ReutersClient

    limit = min(limit, 30)

    try:
        client = ReutersClient()

        # Search
        results = client.search(
            query=query,
            max_results=limit,
            section=section,
            date_range=date_range,
        )

        if not results:
            return [{"error": "No results found or API blocked", "action": "Run 'scraper reuters login' to refresh session"}]

        articles = []
        for i, r in enumerate(results):
            article = {
                "title": r.title,
                "url": r.url,
                "published_at": r.published_at,
                "author": r.author,
                "summary": r.summary,
                "category": r.category,
            }

            # Fetch full content if requested
            if fetch_content and r.url:
                try:
                    full = client.fetch_article(r.url)
                    if full:
                        article["content"] = full.content_markdown
                        article["tags"] = full.tags
                    if i < len(results) - 1:
                        time.sleep(0.5)
                except Exception:
                    pass

            articles.append(article)

        return articles

    except Exception as e:
        return [{"error": f"Search failed: {str(e)}"}]


@mcp.tool()
def wsj_get_search_options() -> dict:
    """Get available search filter options for WSJ.

    Returns:
        Dictionary containing available options for:
        - sort: Sorting options (newest, oldest, relevance)
        - date_range: Date range filters (day, week, month, year, all)
        - sources: Content source types (articles, video, audio, livecoverage, buyside)

    Example:
        options = wsj_get_search_options()
        # Then use with wsj_search:
        # wsj_search("Tesla", sort="newest", date_range="week", sources=["articles"])
    """
    from .sources.wsj.config import SEARCH_SORT, SEARCH_DATE_RANGE, SEARCH_SOURCES

    return {
        "sort": {
            "options": list(SEARCH_SORT.keys()),
            "default": "newest",
            "description": "Sort order for search results",
        },
        "date_range": {
            "options": list(SEARCH_DATE_RANGE.keys()),
            "default": "all",
            "description": "Filter by publication date",
        },
        "sources": {
            "options": list(SEARCH_SOURCES.keys()),
            "default": "all sources",
            "description": "Filter by content type (can specify multiple)",
        },
    }


@mcp.tool()
def wsj_search(
    query: str,
    limit: int = 10,
    fetch_content: bool = True,
    pages: int = 1,
    sort: Optional[str] = None,
    date_range: Optional[str] = None,
    sources: Optional[List[str]] = None,
) -> List[dict]:
    """Search Wall Street Journal for news articles.

    Args:
        query: Search keywords (e.g., "Fed interest rate", "Nvidia")
        limit: Maximum number of articles (default: 10, max: 30)
        fetch_content: Whether to fetch full article content (default: True)
        pages: Number of search result pages (default: 1, max: 3)
        sort: Sort order - "newest", "oldest", "relevance" (default: "newest")
        date_range: Date filter - "day", "week", "month", "year", "all" (default: "all")
        sources: Content sources - list of "articles", "video", "audio", "livecoverage", "buyside"
                 (default: all sources)

    Returns:
        List of articles. Each article contains:
        - title: Article headline
        - url: Full article URL
        - published_at: Publication time
        - author: Author name (if available)
        - category: Article category
        - content: Full article content (only if fetch_content=True)
        - is_paywalled: Whether article is behind paywall (only if fetch_content=True)

    Example:
        wsj_search("Federal Reserve", limit=5)
        wsj_search("Tesla", limit=20, fetch_content=False)
        wsj_search("Nvidia", sort="newest", date_range="week", sources=["articles"])
    """
    from .sources.wsj.scrapers import SearchScraper, ArticleScraper

    limit = min(limit, 30)
    pages = min(pages, 3)

    try:
        search_scraper = SearchScraper()
    except FileNotFoundError:
        return [{"error": "Cookies not found", "action": "Run 'scraper wsj import-cookies <path>' to import cookies"}]

    try:
        # Search with filters
        results = search_scraper.search_multi_pages(
            query=query,
            max_pages=pages,
            sort=sort,
            date_range=date_range,
            sources=sources,
        )

        if not results:
            return [{"error": "No results found"}]

        results = results[:limit]
        articles = []

        # Optionally fetch full content
        article_scraper = None
        if fetch_content:
            try:
                article_scraper = ArticleScraper()
            except FileNotFoundError:
                pass

        for i, r in enumerate(results):
            article = {
                "title": r.headline,
                "url": r.url,
                "published_at": r.timestamp.isoformat() if r.timestamp else None,
                "author": r.author,
                "category": r.category,
            }

            # Fetch full content if requested
            if fetch_content and article_scraper and r.url:
                try:
                    full = article_scraper.scrape(r.url)
                    article["content"] = full.content
                    article["is_paywalled"] = full.is_paywalled
                    if i < len(results) - 1:
                        time.sleep(1.0)
                except Exception:
                    pass

            articles.append(article)

        return articles

    except Exception as e:
        return [{"error": f"Search failed: {str(e)}"}]


def main():
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
