"""Unified MCP Server — two tools: search and fetch."""

import time
from typing import List, Optional

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    name="web-scraper",
    instructions=(
        "Two tools available:\n\n"
        "1. search(source, search_keywords, limit, time_range, language)\n"
        "   Search content from a specific source. Available sources:\n"
        "   - reuters: Reuters news (no auth required)\n"
        "   - wsj: Wall Street Journal (requires imported cookies)\n"
        "   - scholar: Google Scholar academic papers\n"
        "   - zhihu: 知乎 articles and answers (requires login)\n"
        "   - dianping: 大众点评 shops and notes (requires imported cookies)\n"
        "   - serper: General web/news search via Serper API (requires SERPER_API_KEY)\n"
        "   - google: General web search via Google CSE (requires GOOGLE_CSE_API_KEY + GOOGLE_CSE_CX)\n\n"
        "2. fetch(url)\n"
        "   Fetch full content from any URL. Auto-detects the right fetcher:\n"
        "   reuters.com → Reuters client, wsj.com → WSJ scraper,\n"
        "   zhihu.com / dianping.com → source scraper, everything else → generic fetcher.\n"
    ),
)

# ──────────────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────────────

def _assert_source_enabled(source: str) -> Optional[dict]:
    """Return an error dict if *source* is disabled, else None."""
    from .core.config import get_config
    cfg = get_config()
    if not cfg.is_enabled(source):
        enabled = cfg.enabled_sources()
        hint = f"Enabled sources: {', '.join(enabled)}" if enabled else "No sources enabled."
        return {
            "error": f"Source '{source}' is disabled.",
            "hint": hint,
            "config_path": str(cfg.path),
        }
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

# Domains blocked from search results (slow or inaccessible from overseas)
_BLOCKED_DOMAINS = {"csdn.net"}

_REUTERS_TIME = {
    "day": "past_24_hours",
    "week": "past_week",
    "month": "past_month",
    "year": "past_year",
}
_WSJ_TIME = {
    "day": "day",
    "week": "week",
    "month": "month",
    "year": "year",
}
_SERPER_TIME = {
    "day": "qdr:d",
    "week": "qdr:w",
    "month": "qdr:m",
    "year": "qdr:y",
}
_GOOGLE_TIME = {
    "day": "d1",
    "week": "w1",
    "month": "m1",
    "year": "y1",
}


def _detect_source(url: str) -> str:
    """Detect source name from URL domain."""
    url_lower = url.lower()
    if "reuters.com" in url_lower:
        return "reuters"
    if "wsj.com" in url_lower or "barrons.com" in url_lower:
        return "wsj"
    if "zhihu.com" in url_lower or "zhuanlan.zhihu.com" in url_lower:
        return "zhihu"
    if "dianping.com" in url_lower:
        return "dianping"
    if "scholar.google" in url_lower:
        return "scholar"
    return "generic"


# ──────────────────────────────────────────────────────────────────────────────
# Tool 1: search
# ──────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def search(
    source: str,
    search_keywords: str,
    limit: int = 10,
    time_range: str = "",
    language: str = "",
) -> List[dict]:
    """Search content from a specific source.

    Args:
        source: Source to search from. One of:
                "reuters"  — Reuters News (no auth required)
                "wsj"      — Wall Street Journal (requires 'scraper wsj import-cookies')
                "scholar"  — Google Scholar academic papers
                "zhihu"    — 知乎 articles and answers (requires 'scraper zhihu login')
                "dianping" — 大众点评商户和笔记（requires 'scraper dianping import-cookies')
                "serper"   — General web/news search (requires SERPER_API_KEY env var)
                "google"   — Google Custom Search (requires GOOGLE_CSE_API_KEY + GOOGLE_CSE_CX)
        search_keywords: Search query string
        limit: Maximum number of results to return (default: 10)
        time_range: Optional time filter — "day", "week", "month", "year"
                    (not supported by all sources)
        language: Optional language code — e.g. "en", "zh-cn", "zh", "ja"
                  (not supported by all sources)

    Returns:
        List of result dicts. Common fields across all sources:
        - title (str): Result title or headline
        - url (str): Full URL to the content
        - snippet (str): Text preview or summary
        - source (str): Which source returned this result
        Additional source-specific fields may be present (year, authors, upvotes, etc.)

    Examples:
        search("reuters", "Federal Reserve interest rate", limit=5)
        search("scholar", "transformer attention mechanism", limit=10, time_range="year")
        search("serper", "Python 3.13 features", limit=8, time_range="month")
        search("zhihu", "量化交易策略", limit=10)
    """
    source = source.strip().lower()
    limit = max(1, min(limit, 50))

    err = _assert_source_enabled(source)
    if err:
        return [err]

    if source == "reuters":
        results = _search_reuters(search_keywords, limit, time_range)
    elif source == "wsj":
        results = _search_wsj(search_keywords, limit, time_range)
    elif source == "scholar":
        results = _search_scholar(search_keywords, limit, language)
    elif source == "zhihu":
        results = _search_zhihu(search_keywords, limit)
    elif source == "dianping":
        results = _search_dianping(search_keywords, limit)
    elif source == "serper":
        results = _search_serper(search_keywords, limit, time_range, language)
    elif source == "google":
        results = _search_google(search_keywords, limit, time_range, language)
    else:
        available = "reuters, wsj, scholar, zhihu, dianping, serper, google"
        return [{"error": f"Unknown source '{source}'. Available: {available}"}]

    return [
        r for r in results
        if not any(domain in r.get("url", "") for domain in _BLOCKED_DOMAINS)
    ]


def _search_reuters(query: str, limit: int, time_range: str) -> List[dict]:
    from .sources.reuters.client import ReutersClient
    try:
        client = ReutersClient()
        results = client.search(
            query=query,
            max_results=limit,
            date_range=_REUTERS_TIME.get(time_range),
        )
        if not results:
            return [{"error": "No results found", "hint": "Run 'scraper reuters login' to refresh session"}]
        return [
            {
                "title": r.title,
                "url": r.url,
                "snippet": r.summary or "",
                "published_at": r.published_at,
                "author": r.author,
                "category": r.category,
                "source": "reuters",
            }
            for r in results
        ]
    except Exception as e:
        return [{"error": str(e), "source": "reuters"}]


def _search_wsj(query: str, limit: int, time_range: str) -> List[dict]:
    from .sources.wsj.scrapers import SearchScraper
    try:
        scraper = SearchScraper()
    except FileNotFoundError:
        return [{"error": "WSJ cookies not found", "hint": "Run 'scraper wsj import-cookies <path>'"}]
    try:
        results = scraper.search_multi_pages(
            query=query,
            date_range=_WSJ_TIME.get(time_range),
        )
        if not results:
            return [{"error": "No results found"}]
        return [
            {
                "title": r.headline,
                "url": r.url,
                "snippet": "",
                "published_at": r.timestamp.isoformat() if r.timestamp else None,
                "author": r.author,
                "category": r.category,
                "source": "wsj",
            }
            for r in results[:limit]
        ]
    except Exception as e:
        return [{"error": str(e), "source": "wsj"}]


def _search_scholar(query: str, limit: int, language: str) -> List[dict]:
    from .sources.scholar.scrapers import SearchScraper
    try:
        scraper = SearchScraper()
        results = scraper.search_multi_pages(query=query, lang=language or None)
        if not results:
            return [{"error": "No results found or CAPTCHA triggered"}]
        return [
            {
                "title": r.title,
                "url": r.url,
                "snippet": r.snippet or "",
                "authors": r.authors,
                "year": r.year,
                "cited_by_count": r.cited_by_count,
                "pdf_url": r.pdf_url,
                "source": "scholar",
            }
            for r in results[:limit]
        ]
    except Exception as e:
        return [{"error": str(e), "source": "scholar"}]


def _search_zhihu(query: str, limit: int) -> List[dict]:
    from .sources.zhihu.scrapers import SearchScraper
    from .sources.zhihu.rate_limiter import RateLimiter
    from .sources.zhihu.config import STRATEGY_AUTO
    if not hasattr(_search_zhihu, "_rl"):
        _search_zhihu._rl = RateLimiter()
    rl = _search_zhihu._rl
    try:
        scraper = SearchScraper(rate_limiter=rl, strategy=STRATEGY_AUTO)
        results = scraper.search_multi_pages(query=query, max_results=limit)
        if not results:
            return [{"error": "No results found or blocked by anti-bot"}]
        return [
            {
                "title": r.title,
                "url": r.url,
                "snippet": r.excerpt or "",
                "author": r.author,
                "upvotes": r.upvotes,
                "content_type": r.content_type,
                "source": "zhihu",
            }
            for r in results
        ]
    except Exception as e:
        return [{"error": str(e), "source": "zhihu"}]


def _search_dianping(query: str, limit: int) -> List[dict]:
    from .sources.dianping.scrapers import SearchScraper
    try:
        with SearchScraper() as scraper:
            results = scraper.search(query=query, limit=limit)
        if not results:
            return [{"error": "No results found"}]
        return [
            {
                "title": r.title,
                "url": r.url,
                "snippet": " / ".join(x for x in [r.category, r.region, r.avg_price_text] if x),
                "review_count": r.review_count,
                "category": r.category,
                "region": r.region,
                "source": "dianping",
            }
            for r in results
        ]
    except FileNotFoundError:
        return [{"error": "Dianping cookies not found", "hint": "Run 'scraper dianping import-cookies <path>'"}]
    except Exception as e:
        return [{"error": str(e), "source": "dianping"}]


def _search_serper(query: str, limit: int, time_range: str, language: str) -> List[dict]:
    from .sources.serper.scrapers import SearchScraper
    from .sources.serper.config import TIME_RANGES, LANGUAGES
    try:
        scraper = SearchScraper()
        if not scraper.is_configured():
            return [{"error": "SERPER_API_KEY not set", "hint": "Get a key at https://serper.dev"}]
        resp = scraper.search(
            query,
            num=limit,
            time_range=TIME_RANGES.get(time_range, time_range),
            language=LANGUAGES.get(language, language),
        )
        if not resp.results:
            return [{"error": "No results found"}]
        return [
            {
                "title": r.title,
                "url": r.url,
                "snippet": r.snippet or "",
                "date": r.date or "",
                "domain": r.source or "",
                "source": "serper",
            }
            for r in resp.results
        ]
    except Exception as e:
        return [{"error": str(e), "source": "serper"}]


def _search_google(query: str, limit: int, time_range: str, language: str) -> List[dict]:
    from .sources.google.scrapers import SearchScraper
    from .sources.google.config import LANGUAGES
    try:
        scraper = SearchScraper()
        if not scraper.is_configured():
            return [{
                "error": "Google CSE not configured",
                "hint": "Set GOOGLE_CSE_API_KEY and GOOGLE_CSE_CX environment variables",
            }]
        resp = scraper.search(
            query,
            num=limit,
            date_restrict=_GOOGLE_TIME.get(time_range, time_range),
            language=LANGUAGES.get(language, language),
        )
        if not resp.results:
            return [{"error": "No results found"}]
        out = []
        for i, r in enumerate(resp.results):
            item = {
                "title": r.title,
                "url": r.url,
                "snippet": r.snippet or "",
                "display_link": r.display_link or "",
                "source": "google",
            }
            if i == 0 and resp.total_results:
                item["total_results"] = resp.total_results
            out.append(item)
        return out
    except Exception as e:
        return [{"error": str(e), "source": "google"}]


# ──────────────────────────────────────────────────────────────────────────────
# Tool 2: fetch
# ──────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def fetch(url: str) -> dict:
    """Fetch full content from a URL.

    Automatically selects the best fetcher based on the URL domain:
    - reuters.com       → Reuters authenticated client (requires prior login)
    - wsj.com           → WSJ article scraper (requires imported cookies)
    - zhihu.com         → Zhihu article/answer scraper
    - zhuanlan.zhihu.com → Zhihu column article scraper
    - everything else   → Crawl4AI → Jina Reader → ArticleFetcher (curl-cffi → httpx → Playwright)

    Args:
        url: Full URL of the page to fetch

    Returns:
        - url (str): The requested URL
        - title (str | null): Page title
        - content (str | null): Full page content in markdown
        - source (str): Which fetcher was used
        - is_accessible (bool): Whether full content was accessible
        - is_pdf (bool): Whether the URL points to a PDF file
        - error (str): Present only if fetching failed

    Examples:
        fetch("https://www.reuters.com/technology/article-slug-2025-01-01/")
        fetch("https://arxiv.org/abs/2310.06825")
        fetch("https://zhuanlan.zhihu.com/p/123456789")
    """
    from .core.config import get_config
    cfg = get_config()
    detected = _detect_source(url)

    # Use source-specific fetcher only when that source is enabled
    if detected == "reuters" and cfg.is_enabled("reuters"):
        return _fetch_reuters(url)
    if detected == "wsj" and cfg.is_enabled("wsj"):
        return _fetch_wsj(url)
    if detected == "zhihu" and cfg.is_enabled("zhihu"):
        return _fetch_zhihu(url)
    if detected == "dianping" and cfg.is_enabled("dianping"):
        return _fetch_dianping(url)
    if detected == "scholar":
        return _fetch_scholar(url)
    return _fetch_web(url)


def _fetch_reuters(url: str) -> dict:
    from .sources.reuters.client import ReutersClient
    try:
        client = ReutersClient()
        article = client.fetch_article(url)
        if not article:
            return _fetch_generic(url)
        return {
            "url": url,
            "title": article.title,
            "content": article.content_markdown,
            "published_at": article.published_at,
            "author": article.author,
            "tags": article.tags,
            "source": "reuters",
            "is_accessible": True,
            "is_pdf": False,
        }
    except Exception:
        return _fetch_generic(url)


def _fetch_wsj(url: str) -> dict:
    from .sources.wsj.scrapers import ArticleScraper
    try:
        scraper = ArticleScraper()
        article = scraper.scrape(url)
        return {
            "url": url,
            "title": article.title,
            "content": article.content,
            "is_paywalled": article.is_paywalled,
            "source": "wsj",
            "is_accessible": not article.is_paywalled,
            "is_pdf": False,
        }
    except FileNotFoundError:
        return _fetch_generic(url)
    except Exception:
        return _fetch_generic(url)


def _fetch_zhihu(url: str) -> dict:
    from .sources.zhihu.scrapers import ArticleScraper
    from .sources.zhihu.rate_limiter import RateLimiter
    from .sources.zhihu.config import STRATEGY_PURE_API
    if not hasattr(_fetch_zhihu, "_rl"):
        _fetch_zhihu._rl = RateLimiter()
    try:
        scraper = ArticleScraper(rate_limiter=_fetch_zhihu._rl, strategy=STRATEGY_PURE_API)
        article = scraper.scrape(url)
        return {
            "url": url,
            "title": article.title,
            "content": article.content,
            "author": article.author,
            "upvotes": article.upvotes,
            "tags": article.tags,
            "content_type": article.content_type,
            "data_source": article.data_source,
            "source": "zhihu",
            "is_accessible": True,
            "is_pdf": False,
        }
    except Exception as e:
        return {"url": url, "error": str(e), "source": "zhihu",
                "hint": "Run 'scraper zhihu login' to refresh session"}


def _fetch_dianping(url: str) -> dict:
    from .sources.dianping.scrapers import NoteScraper, ShopScraper
    try:
        if "/shop/" in url:
            with ShopScraper() as scraper:
                detail = scraper.fetch(url)
            return {
                "url": url,
                "title": detail.name,
                "content": "\n".join(
                    f"- {deal.title} | {deal.price or '-'} / {deal.value or '-'} | {deal.discount or '-'}"
                    for deal in detail.deals
                ),
                "address": detail.address,
                "category": detail.category,
                "region": detail.region,
                "price_text": detail.price_text,
                "score_text": detail.score_text,
                "source": "dianping",
                "is_accessible": True,
                "is_pdf": False,
            }
        if "/note/" in url or "/ugcdetail/" in url:
            with NoteScraper() as scraper:
                detail = scraper.fetch(url)
            return {
                "url": detail.url,
                "title": detail.title,
                "content": detail.content,
                "author": detail.author.nickname if detail.author else None,
                "published_at": detail.published_at,
                "like_count": detail.like_count,
                "comment_count": detail.comment_count,
                "topics": detail.topics,
                "source": "dianping",
                "is_accessible": True,
                "is_pdf": False,
            }
        return _fetch_generic(url)
    except FileNotFoundError:
        return {"url": url, "error": "Dianping cookies not found", "source": "dianping",
                "hint": "Run 'scraper dianping import-cookies <path>'"}
    except Exception as e:
        return {"url": url, "error": str(e), "source": "dianping"}


def _fetch_scholar(url: str) -> dict:
    """Scholar search result pages aren't directly fetchable; use generic fetcher."""
    result = _fetch_generic(url)
    result["source"] = "scholar"
    return result


def _fetch_crawl4ai(url: str) -> dict | None:
    """Fetch using Crawl4AI (primary for web URLs). Returns dict or None on failure."""
    try:
        import asyncio
        import concurrent.futures
        from crawl4ai import AsyncWebCrawler, BrowserConfig

        async def _crawl():
            cfg = BrowserConfig(
                headless=True,
                verbose=False,
                browser_type="webkit",   # WebKit (Safari engine) is stable on macOS arm64
            )
            async with AsyncWebCrawler(config=cfg) as crawler:
                return await crawler.arun(url=url)

        # Run in a dedicated thread to avoid event-loop conflicts with MCP server
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(asyncio.run, _crawl()).result(timeout=45)

        if not result.success:
            return None

        # markdown may be a MarkdownGenerationResult object in newer versions
        content = result.markdown
        if hasattr(content, "fit_markdown"):
            content = content.fit_markdown or content.raw_markdown or str(content)
        if not isinstance(content, str):
            content = str(content)
        if not content or len(content.strip()) < 50:
            return None

        title = result.metadata.get("title") if result.metadata else None
        return {
            "url": url,
            "title": title,
            "content": content.strip(),
            "is_accessible": True,
            "is_pdf": False,
            "source": "crawl4ai",
        }
    except Exception:
        return None


def _fetch_jina(url: str) -> dict | None:
    """Fetch using Jina Reader (https://r.jina.ai). Returns dict or None on failure."""
    try:
        import httpx
        response = httpx.get(
            f"https://r.jina.ai/{url}",
            headers={
                "Accept": "text/markdown",
                "X-Return-Format": "markdown",
                "X-Remove-Selector": "nav,footer,aside,.ads,.cookie-banner",
            },
            timeout=30.0,
            follow_redirects=True,
        )
        if response.status_code != 200:
            return None
        text = response.text.strip()
        if not text or len(text) < 50:
            return None
        # Extract title from first H1
        title = None
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("# "):
                title = stripped[2:].strip()
                break
        return {
            "url": url,
            "title": title,
            "content": text,
            "is_accessible": True,
            "is_pdf": False,
            "source": "jina",
        }
    except Exception:
        return None


def _fetch_web(url: str) -> dict:
    """Fetch a generic web URL: crawl4ai → jina → ArticleFetcher fallback."""
    result = _fetch_crawl4ai(url)
    if result:
        return result
    result = _fetch_jina(url)
    if result:
        return result
    return _fetch_generic(url)


def _fetch_generic(url: str) -> dict:
    from .sources.serper.scrapers import ArticleFetcher
    try:
        fetcher = ArticleFetcher()
        article = fetcher.fetch(url)
        return {
            "url": url,
            "title": article.title,
            "content": article.content,
            "published_date": article.published_date,
            "is_accessible": article.is_accessible,
            "is_pdf": article.is_pdf,
            "source": "generic",
        }
    except Exception as e:
        return {"url": url, "error": str(e), "source": "generic"}


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────

def main():
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
