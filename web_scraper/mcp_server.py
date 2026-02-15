"""MCP Server for news search - Reuters, WSJ, and Google Scholar."""

import time
from typing import List, Optional

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    name="news-search",
    instructions="Search news from Reuters, Wall Street Journal, Google Scholar, and Zhihu. "
                 "Use reuters_search for Reuters news, wsj_search for WSJ news, "
                 "scholar_search for academic papers, zhihu_search for Zhihu content. "
                 "All tools return standardized data with optional full content.",
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


@mcp.tool()
def scholar_get_search_options() -> dict:
    """Get available search filter options for Google Scholar.

    Returns:
        Dictionary containing available options for:
        - sort: Sorting options (relevance, date)
        - languages: Language filter options
        - year_range: Year range filter description

    Example:
        options = scholar_get_search_options()
    """
    from .sources.scholar.config import SEARCH_SORT, SEARCH_LANGUAGES

    return {
        "sort": {
            "options": list(SEARCH_SORT.keys()),
            "default": "relevance",
            "description": "Sort order for search results",
        },
        "languages": {
            "options": list(SEARCH_LANGUAGES.keys()),
            "default": "any",
            "description": "Filter by paper language",
        },
        "year_range": {
            "description": "Filter by year range using year_lo and year_hi parameters",
            "example": "year_lo=2020, year_hi=2024",
        },
    }


@mcp.tool()
def scholar_search(
    query: str,
    limit: int = 10,
    fetch_content: bool = False,
    pages: int = 1,
    sort: Optional[str] = None,
    year_lo: Optional[int] = None,
    year_hi: Optional[int] = None,
    lang: Optional[str] = None,
) -> List[dict]:
    """Search Google Scholar for academic papers.

    Args:
        query: Search keywords (e.g., "machine learning", "quantitative trading")
        limit: Maximum number of results (default: 10, max: 30)
        fetch_content: Whether to fetch full article content from publisher pages (default: False).
                       Note: fetching content is slower and may trigger rate limits.
        pages: Number of search result pages (default: 1, max: 3)
        sort: Sort order - "relevance" (default), "date"
        year_lo: Filter papers from this year onwards (e.g., 2020)
        year_hi: Filter papers up to this year (e.g., 2024)
        lang: Language filter - "en", "zh", "ja", etc. (default: any)

    Returns:
        List of papers. Each paper contains:
        - title: Paper title
        - url: Link to publisher page
        - authors: Authors string
        - snippet: Abstract preview
        - year: Publication year
        - cited_by_count: Number of citations
        - pdf_url: Direct PDF link (if available)
        - content: Full article content (only if fetch_content=True)

    Example:
        scholar_search("transformer attention mechanism", limit=5)
        scholar_search("deep learning", year_lo=2023, sort="date")
    """
    from .sources.scholar.scrapers import SearchScraper, ArticleScraper

    limit = min(limit, 30)
    pages = min(pages, 3)

    try:
        search_scraper = SearchScraper()
        results = search_scraper.search_multi_pages(
            query=query,
            max_pages=pages,
            sort=sort,
            year_lo=year_lo,
            year_hi=year_hi,
            lang=lang,
        )

        if not results:
            return [{"error": "No results found or CAPTCHA triggered"}]

        results = results[:limit]
        articles = []

        article_scraper = None
        if fetch_content:
            article_scraper = ArticleScraper()

        for i, r in enumerate(results):
            article = {
                "title": r.title,
                "url": r.url,
                "authors": r.authors,
                "snippet": r.snippet,
                "year": r.year,
                "cited_by_count": r.cited_by_count,
                "pdf_url": r.pdf_url,
                "source": r.source,
            }

            if fetch_content and article_scraper and r.url and not r.is_citation:
                try:
                    full = article_scraper.scrape(r.url)
                    article["content"] = full.content
                    article["abstract"] = full.abstract
                    article["doi"] = full.doi
                    article["journal"] = full.journal
                    article["is_accessible"] = full.is_accessible
                    if i < len(results) - 1:
                        time.sleep(2.0)
                except Exception:
                    pass

            articles.append(article)

        return articles

    except Exception as e:
        return [{"error": f"Search failed: {str(e)}"}]


@mcp.tool()
def scholar_fetch_article(url: str) -> dict:
    """Fetch full content from a publisher article page.

    Use this to get the full text of a paper found via scholar_search.

    Args:
        url: Article URL (from scholar_search results)

    Returns:
        Article details:
        - title: Article title
        - authors: List of author names
        - abstract: Article abstract
        - content: Full article content in markdown
        - doi: DOI identifier
        - journal: Journal name
        - is_accessible: Whether full content was accessible
        - is_pdf: Whether URL points to a PDF

    Example:
        scholar_fetch_article("https://arxiv.org/abs/2301.12345")
    """
    from .sources.scholar.scrapers import ArticleScraper

    try:
        scraper = ArticleScraper()
        article = scraper.scrape(url)

        return {
            "title": article.title,
            "authors": article.authors,
            "abstract": article.abstract,
            "content": article.content,
            "doi": article.doi,
            "journal": article.journal,
            "published_date": article.published_date,
            "is_accessible": article.is_accessible,
            "is_pdf": article.is_pdf,
            "url": article.url,
        }

    except Exception as e:
        return {"error": f"Failed to fetch article: {str(e)}", "url": url}


@mcp.tool()
def zhihu_search(
    query: str,
    limit: int = 10,
    search_type: str = "content",
    fetch_content: bool = False,
) -> List[dict]:
    """Search Zhihu for articles, answers, and discussions.

    Requires Chrome with remote debugging enabled (--remote-debugging-port=9222)
    or a saved Zhihu login session.

    Uses multi-strategy extraction: API direct → API intercept → DOM extraction.
    Includes automatic rate limiting.

    Args:
        query: Search keywords (e.g., "transformer", "机器学习")
        limit: Maximum number of results (default: 10, max: 30)
        search_type: Search type - "content" (综合), "people" (用户), "scholar" (论文),
                     "column" (专栏), "topic" (话题), "zvideo" (视频)
        fetch_content: Whether to fetch full article content (default: False, slower)

    Returns:
        List of results. Each result contains:
        - title: Content title
        - url: Content URL
        - content_type: Type (answer, article, question, video)
        - excerpt: Content excerpt
        - author: Author name
        - upvotes: Upvote count
        - data_source: Extraction method (pure_api, api_direct, api_intercept, dom)
        - content: Full content (only if fetch_content=True)

    Example:
        zhihu_search("transformer 原理", limit=5)
        zhihu_search("量化交易", search_type="column")
    """
    from .sources.zhihu.scrapers import SearchScraper, ArticleScraper
    from .sources.zhihu.rate_limiter import RateLimiter
    from .sources.zhihu.config import STRATEGY_AUTO

    limit = min(limit, 30)

    # Module-level rate limiter singleton for MCP
    if not hasattr(zhihu_search, "_rate_limiter"):
        zhihu_search._rate_limiter = RateLimiter()

    try:
        # Auto strategy: pure API first, then browser-based fallbacks
        search_scraper = SearchScraper(
            rate_limiter=zhihu_search._rate_limiter,
            strategy=STRATEGY_AUTO,
        )
        results = search_scraper.search_multi_pages(
            query=query,
            search_type=search_type,
            max_results=limit,
        )

        if not results:
            return [{"error": "No results found or blocked by anti-bot"}]

        articles = []
        article_scraper = None
        if fetch_content:
            article_scraper = ArticleScraper(rate_limiter=zhihu_search._rate_limiter)

        for i, r in enumerate(results):
            article = {
                "title": r.title,
                "url": r.url,
                "content_type": r.content_type,
                "excerpt": r.excerpt,
                "author": r.author,
                "upvotes": r.upvotes,
                "comments": r.comments,
                "data_source": r.data_source,
            }

            if fetch_content and article_scraper and r.url:
                try:
                    full = article_scraper.scrape(r.url)
                    article["content"] = full.content
                    article["tags"] = full.tags
                    article["data_source"] = full.data_source
                except Exception:
                    pass

            articles.append(article)

        return articles

    except Exception as e:
        return [{"error": f"Search failed: {str(e)}"}]


@mcp.tool()
def zhihu_fetch_article(url: str) -> dict:
    """Fetch full content from a Zhihu article or answer URL.

    Uses multi-strategy extraction: API direct → API intercept → DOM extraction.

    Args:
        url: Zhihu article or answer URL
             (e.g., "https://zhuanlan.zhihu.com/p/123456" or
              "https://www.zhihu.com/question/123/answer/456")

    Returns:
        Article details:
        - title: Content title
        - content: Full content text
        - author: Author name
        - upvotes: Upvote count
        - tags: Content tags
        - content_type: article or answer
        - data_source: Extraction method used

    Example:
        zhihu_fetch_article("https://zhuanlan.zhihu.com/p/123456")
    """
    from .sources.zhihu.scrapers import ArticleScraper
    from .sources.zhihu.rate_limiter import RateLimiter
    from .sources.zhihu.config import STRATEGY_AUTO

    # Reuse rate limiter singleton
    if not hasattr(zhihu_search, "_rate_limiter"):
        zhihu_search._rate_limiter = RateLimiter()

    try:
        # Auto strategy: pure API first, then browser-based fallbacks
        scraper = ArticleScraper(
            rate_limiter=zhihu_search._rate_limiter,
            strategy=STRATEGY_AUTO,
        )
        article = scraper.scrape(url)

        return {
            "title": article.title,
            "url": article.url,
            "content": article.content,
            "author": article.author,
            "upvotes": article.upvotes,
            "comments": article.comments,
            "created_at": article.created_at,
            "tags": article.tags,
            "content_type": article.content_type,
            "question_title": article.question_title,
            "data_source": article.data_source,
        }

    except Exception as e:
        return {"error": f"Failed to fetch article: {str(e)}", "url": url}


@mcp.tool()
def zhihu_get_search_types() -> dict:
    """Get available search types for Zhihu.

    Returns:
        Dictionary of search types with their URL parameters.
    """
    from .sources.zhihu.config import SEARCH_TYPES

    return {
        "search_types": {
            "options": list(SEARCH_TYPES.keys()),
            "params": SEARCH_TYPES,
            "default": "content",
            "description": "Search content type filter",
        },
    }


def main():
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
