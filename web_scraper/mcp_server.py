"""Unified MCP Server for web scraping tools."""

import asyncio
from typing import List, Optional

from mcp.server.fastmcp import FastMCP

# Initialize MCP server
mcp = FastMCP(
    name="web-scraper",
    instructions="Unified web scraping tools for Reuters and Xiaohongshu. "
                 "Use reuters_* tools for news, xhs_* tools for social content.",
)


def _run_async(coro):
    """Run async function in sync context."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
    else:
        return asyncio.run(coro)


# ==================== Reuters Tools ====================

@mcp.tool()
def reuters_search(
    query: str,
    max_results: int = 10,
    section: Optional[str] = None,
    sort_by: str = "relevance",
) -> List[dict]:
    """Search Reuters for news articles.

    Args:
        query: Search query string (e.g., "Fed interest rate", "climate change")
        max_results: Maximum number of results to return (default: 10, max: 50)
        section: Filter by section slug (e.g., "business", "world/china")
        sort_by: Sort order - "relevance" or "date" (default: "relevance")

    Returns:
        List of search results with title, summary, url, published_at, and category

    Example:
        reuters_search(query="Federal Reserve", max_results=5, section="business")
    """
    from .sources.reuters.scrapers import SearchScraper
    from .core.exceptions import NotLoggedInError, RateLimitedError

    max_results = min(max_results, 50)

    try:
        scraper = SearchScraper(headless=True)
        results = scraper.search(
            query=query,
            max_results=max_results,
            section=section,
            sort_by=sort_by,
        )
        return [r.model_dump() for r in results]
    except NotLoggedInError as e:
        return [{"error": str(e), "action": "Run 'scraper reuters login -i' to authenticate"}]
    except RateLimitedError as e:
        return [{"error": str(e), "action": "Wait and try again later"}]
    except Exception as e:
        return [{"error": f"Search failed: {str(e)}"}]


@mcp.tool()
def reuters_fetch_article(url: str) -> dict:
    """Fetch full article content from Reuters.

    Args:
        url: Article URL (absolute or relative, e.g., "/business/us-economy-2024-01-15/")

    Returns:
        Article object with title, author, published_at, content_markdown, images, and tags

    Example:
        reuters_fetch_article(url="/world/china/china-economy-growth-2024/")
    """
    from .sources.reuters.scrapers import ArticleScraper
    from .core.exceptions import NotLoggedInError, RateLimitedError, ContentNotFoundError, PaywallError

    try:
        scraper = ArticleScraper(headless=True)
        article = scraper.fetch(url)
        return article.model_dump()
    except NotLoggedInError as e:
        return {"error": str(e), "action": "Run 'scraper reuters login -i' to authenticate"}
    except ContentNotFoundError as e:
        return {"error": str(e)}
    except PaywallError as e:
        return {"error": str(e), "note": "Article requires subscription"}
    except RateLimitedError as e:
        return {"error": str(e), "action": "Wait and try again later"}
    except Exception as e:
        return {"error": f"Failed to fetch article: {str(e)}"}


@mcp.tool()
def reuters_list_section(
    section: str,
    max_articles: int = 10,
) -> List[dict]:
    """List latest articles from a Reuters section.

    Args:
        section: Section slug (use reuters_get_sections to see available sections)
                 Examples: "world", "world/china", "business", "technology"
        max_articles: Maximum number of articles to return (default: 10, max: 30)

    Returns:
        List of articles with title, summary, url, published_at, and thumbnail_url

    Example:
        reuters_list_section(section="world/china", max_articles=5)
    """
    from .sources.reuters.scrapers import SectionScraper
    from .core.exceptions import NotLoggedInError, RateLimitedError

    max_articles = min(max_articles, 30)

    try:
        scraper = SectionScraper(headless=True)
        articles = scraper.list_articles(section=section, max_articles=max_articles)
        return [a.model_dump() for a in articles]
    except NotLoggedInError as e:
        return [{"error": str(e), "action": "Run 'scraper reuters login -i' to authenticate"}]
    except ValueError as e:
        return [{"error": str(e)}]
    except RateLimitedError as e:
        return [{"error": str(e), "action": "Wait and try again later"}]
    except Exception as e:
        return [{"error": f"Failed to list section: {str(e)}"}]


@mcp.tool()
def reuters_get_sections() -> List[dict]:
    """Get all available Reuters sections/categories.

    Returns:
        List of sections with name, slug, and url
    """
    from .sources.reuters.scrapers import SectionScraper

    scraper = SectionScraper(headless=True)
    sections = scraper.get_sections()
    return [s.model_dump() for s in sections]


# ==================== Xiaohongshu Tools ====================

@mcp.tool()
def xhs_explore(
    category: str = "推荐",
    limit: int = 20,
) -> dict:
    """Explore notes from Xiaohongshu homepage.

    Args:
        category: Category to explore (e.g., "推荐", "美食", "穿搭", "旅行")
        limit: Maximum number of notes to collect (default: 20, max: 50)

    Returns:
        ExploreResult with category and list of note cards

    Example:
        xhs_explore(category="美食", limit=10)
    """
    from .core.browser import get_browser
    from .sources.xiaohongshu.config import SOURCE_NAME, CATEGORY_CHANNELS
    from .sources.xiaohongshu.scrapers import ExploreScraper

    if category not in CATEGORY_CHANNELS:
        return {"error": f"Invalid category: {category}", "valid_categories": list(CATEGORY_CHANNELS.keys())}

    limit = min(limit, 50)

    async def _explore():
        async with get_browser(SOURCE_NAME, headless=True) as browser:
            scraper = ExploreScraper(browser)
            return await scraper.scrape(category=category, limit=limit)

    try:
        result = _run_async(_explore())
        return result.model_dump()
    except Exception as e:
        return {"error": f"Explore failed: {str(e)}"}


@mcp.tool()
def xhs_search(
    keyword: str,
    search_type: str = "all",
    limit: int = 20,
) -> dict:
    """Search for notes on Xiaohongshu.

    Args:
        keyword: Search keyword
        search_type: Type of search - "all", "video", "image", "user" (default: "all")
        limit: Maximum number of results (default: 20, max: 50)

    Returns:
        SearchResult with keyword, total count, and list of note cards

    Example:
        xhs_search(keyword="美食推荐", search_type="video", limit=10)
    """
    from .core.browser import get_browser
    from .sources.xiaohongshu.config import SOURCE_NAME, SEARCH_TYPES
    from .sources.xiaohongshu.scrapers import SearchScraper

    if search_type not in SEARCH_TYPES:
        return {"error": f"Invalid search type: {search_type}", "valid_types": list(SEARCH_TYPES.keys())}

    limit = min(limit, 50)

    async def _search():
        async with get_browser(SOURCE_NAME, headless=True) as browser:
            scraper = SearchScraper(browser)
            return await scraper.scrape(keyword=keyword, search_type=search_type, limit=limit)

    try:
        result = _run_async(_search())
        return result.model_dump()
    except Exception as e:
        return {"error": f"Search failed: {str(e)}"}


@mcp.tool()
def xhs_fetch_note(
    note_id: str,
    xsec_token: str = "",
) -> dict:
    """Fetch a specific note from Xiaohongshu.

    Args:
        note_id: Note ID to fetch
        xsec_token: Security token (optional, may be required for some notes)

    Returns:
        Note object with full content, images, tags, and engagement stats

    Example:
        xhs_fetch_note(note_id="abc123", xsec_token="token_from_explore")
    """
    from .core.browser import get_browser
    from .sources.xiaohongshu.config import SOURCE_NAME
    from .sources.xiaohongshu.scrapers import NoteScraper

    async def _fetch():
        async with get_browser(SOURCE_NAME, headless=True) as browser:
            scraper = NoteScraper(browser)
            note, _ = await scraper.scrape(note_id=note_id, xsec_token=xsec_token, silent=True)
            return note

    try:
        result = _run_async(_fetch())
        if result:
            return result.model_dump()
        else:
            return {"error": "Failed to fetch note", "note_id": note_id}
    except Exception as e:
        return {"error": f"Fetch failed: {str(e)}"}


@mcp.tool()
def xhs_get_categories() -> List[dict]:
    """Get available Xiaohongshu explore categories.

    Returns:
        List of categories with name and channel_id
    """
    from .sources.xiaohongshu.config import CATEGORY_CHANNELS

    return [{"name": name, "channel_id": channel_id} for name, channel_id in CATEGORY_CHANNELS.items()]


def main():
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
