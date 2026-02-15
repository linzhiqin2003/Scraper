# Web Scraper - Unified Scraping Framework

## Project Overview

统一爬虫框架，整合 Reuters、Xiaohongshu、WSJ、Google Scholar 爬虫，支持 CLI 和 MCP Server 两种使用方式。

## Tech Stack

- Python 3.11+
- Playwright (sync & async API)
- Typer (CLI)
- Rich (Terminal UI)
- FastMCP (MCP Server)
- Pydantic (Data Models)
- httpx (HTTP client for WSJ, Scholar)
- BeautifulSoup4 + lxml (HTML parsing for Scholar)
- feedparser (RSS parsing)

## Project Structure

```
WebScraper/
├── web_scraper/
│   ├── __init__.py
│   ├── cli.py                  # Unified CLI entry
│   ├── mcp_server.py           # Unified MCP Server
│   │
│   ├── core/                   # Core modules (shared)
│   │   ├── browser.py          # Browser management
│   │   ├── base.py             # Sync scraper base class
│   │   ├── async_base.py       # Async scraper base class
│   │   ├── display.py          # Shared Rich UI display module
│   │   ├── user_agent.py       # UA pool + HTTP header generation
│   │   ├── proxy.py            # Proxy pool with health tracking
│   │   ├── rate_limiter.py     # Sliding window rate limiter + async wrapper
│   │   ├── captcha.py          # CAPTCHA solver interface (pluggable)
│   │   ├── storage.py          # Storage utilities
│   │   └── exceptions.py       # Exception hierarchy
│   │
│   ├── sources/                # Scraper sources
│   │   ├── __init__.py         # Source registry
│   │   ├── reuters/            # Reuters (sync, Playwright)
│   │   ├── xiaohongshu/        # Xiaohongshu (async, Playwright)
│   │   ├── wsj/                # WSJ (sync, httpx)
│   │   ├── scholar/            # Google Scholar (sync, httpx+BeautifulSoup)
│   │   ├── zhihu/              # Zhihu (httpx API + Playwright CDP)
│   │   └── weibo/              # Weibo (async, Playwright)
│   │
│   └── converters/             # Content converters
│       └── markdown.py
│
├── tests/
├── pyproject.toml
├── README.md
└── CLAUDE.md
```

## CLI Commands

### Unified Command Convention

All sources follow a standardized command structure:

| Command | Function | Sources |
|---------|----------|---------|
| `login` | Interactive login | Reuters, XHS, Zhihu, Weibo |
| `status` | Check auth/cookie status | All 6 sources |
| `logout` | Clear session | Reuters, XHS, Zhihu, Weibo |
| `import-cookies` | Import browser cookies | Reuters, WSJ, Scholar, Zhihu |
| `search` | Search content | All 6 sources |
| `fetch` | Fetch single item by URL/ID | All 6 sources |
| `browse` | Browse/discover content | Reuters, XHS, WSJ |
| `options` | Show available filters/categories | All 6 sources |

Standard parameters: `-n/--limit`, `-o/--output`, `--no-save`, `--shallow/-s`

```bash
# Show available sources
scraper sources

# Reuters
scraper reuters login [-e email] [-p password] [-i]
scraper reuters status
scraper reuters search "keyword" -n 10 --section world
scraper reuters fetch <url>
scraper reuters browse list                # List available sections
scraper reuters browse world/china -n 20   # Browse section
scraper reuters options                    # Show sections + search options

# Xiaohongshu
scraper xhs login [--qrcode | --phone]
scraper xhs status                         # Check login status
scraper xhs browse --category 推荐 -n 20   # Browse by category
scraper xhs search "关键词" --type video -n 50
scraper xhs fetch <note_id> --token <xsec_token>  # Fetch note
scraper xhs options                        # Show categories + search types

# WSJ (Wall Street Journal)
scraper wsj import-cookies <cookies.txt>   # Import cookies from browser
scraper wsj status                         # Verify cookies
scraper wsj browse -c technology -n 20     # Browse RSS feeds (shallow by default)
scraper wsj browse -c markets -n 5 --no-shallow  # Browse + fetch full content
scraper wsj search "keyword" -p 2          # Search articles
scraper wsj fetch <url>                    # Fetch full article
scraper wsj search-scrape "query" -n 10    # Search + full content
scraper wsj options                        # Show categories + search filters

# Google Scholar
scraper scholar search "query" -n 10 --shallow     # Search papers (results only)
scraper scholar search "query" -n 5                 # Search + fetch full content
scraper scholar search "query" --sort date --year-from 2023  # With filters
scraper scholar fetch <url>                          # Fetch single article
scraper scholar import-cookies <cookies.txt>         # Import Google cookies (optional)
scraper scholar status                               # Check cookies
scraper scholar options                              # Show filter options

# Zhihu (知乎)
scraper zhihu search "transformer" -n 10 --strategy pure_api  # Pure API search
scraper zhihu search "transformer" -n 10             # Search content (auto strategy)
scraper zhihu search "机器学习" -t column            # Search columns
scraper zhihu fetch <url>                            # Fetch full article/answer
scraper zhihu fetch <url> --strategy api             # Fetch via browser API
scraper zhihu options                                # List search types + strategies
scraper zhihu proxy-status --proxy-api <url>         # Show proxy pool status
scraper zhihu login                                  # Interactive login (Playwright)
scraper zhihu import-cookies <cookies.json>          # Import cookies
scraper zhihu status                                 # Check status

# Weibo (微博)
scraper weibo login                        # Interactive login
scraper weibo status                       # Check login status
scraper weibo logout                       # Clear session
scraper weibo search "keyword" -n 20       # Search posts
scraper weibo hot -n 50                    # Fetch hot-search topics
scraper weibo fetch <url>                  # Fetch post detail
```

### Aliases (backward compatibility)

Old command names are preserved as visible aliases (grouped under "Aliases" in `--help`):
- `scraper reuters section` → `browse`
- `scraper xhs auth` → `status`, `note` → `fetch`, `explore` → `browse`, `categories` → `options`
- `scraper wsj check-cookies` → `status`, `feeds` → `browse`, `scrape-feeds` → `browse`, `categories` → `options`
- `scraper scholar check-cookies` → `status`, `search-options` → `options`
- `scraper zhihu search-types` → `options`
- `scraper weibo detail` → `fetch`

### Source-specific Commands

Some sources have unique commands beyond the standard set:
- `scraper weibo hot` — Fetch hot-search topics
- `scraper zhihu proxy-status` — Show proxy pool status

## MCP Tools

### Reuters
- `reuters_search` - Search for news articles (API → Playwright fallback)
- `reuters_fetch_article` - Fetch full article content (HTTP → Playwright fallback)
- `reuters_list_section` - List articles from a section (API → Playwright fallback)
- `reuters_get_sections` - Get available sections
- `reuters_get_search_count` - Get total search result count

### Xiaohongshu
- `xhs_explore` - Explore notes by category
- `xhs_search` - Search for notes
- `xhs_fetch_note` - Fetch a specific note
- `xhs_get_categories` - Get available categories

### WSJ
- `wsj_search` - Search for news articles (supports sort, date_range, sources filters)
- `wsj_fetch_article` - Fetch full article content
- `wsj_feeds` - Get articles from RSS feeds
- `wsj_get_categories` - Get available RSS categories
- `wsj_get_search_options` - Get available search filter options (sort, date_range, sources)

### Google Scholar
- `scholar_search` - Search academic papers (supports sort, year range, language, optional content fetching)
- `scholar_fetch_article` - Fetch full article content from publisher page
- `scholar_get_search_options` - Get available search filter options (sort, languages, year range)

### Zhihu
- `zhihu_search` - Search Zhihu content (multi-strategy: API direct → API intercept → DOM)
- `zhihu_fetch_article` - Fetch full article/answer content (multi-strategy extraction)
- `zhihu_get_search_types` - Get available search type filters

## Data Storage

```
~/.web_scraper/
├── reuters/
│   ├── browser_state.json      # Session cookies + localStorage
│   └── exports/                # Exported data
├── xiaohongshu/
│   ├── cookies.json            # Session cookies
│   └── exports/                # Exported data
├── wsj/
│   ├── cookies.txt             # Netscape format cookies (from browser)
│   └── exports/                # Exported data
├── scholar/
│   ├── cookies.txt             # Google cookies (optional, reduces CAPTCHA)
│   └── exports/                # Exported data
└── config.json                 # Global config (future)
```

## Documentation

- **[Source Development Guide](docs/SOURCE_DEVELOPMENT_GUIDE.md)** - 新源开发规范，所有子爬虫必须遵循

## Development Notes

### Source Registration

Each source registers itself via `register_source()` in its `__init__.py`:

```python
from .. import register_source, SourceConfig
from .cli import app as cli_app

register_source(SourceConfig(
    name="reuters",
    display_name="Reuters News",
    cli_app=cli_app,
    data_dir_name="reuters",
    is_async=False,
))
```

### Sync vs Async

- Reuters: Synchronous Playwright (simpler for sequential scraping)
- Xiaohongshu: Asynchronous Playwright (required for concurrent operations)
- WSJ: Synchronous httpx (lightweight HTTP client, no browser needed)
- Scholar: Synchronous httpx + BeautifulSoup (HTML parsing, no API available)
- Zhihu: Pure httpx API (preferred) or Playwright via CDP (fallback, connects to user's real Chrome)

### Anti-Detection

Sources share anti-detection measures in `core/browser.py`:
- webdriver property hidden
- Fake plugins/languages
- Chrome channel for real browser
- Cookie persistence per source

### Zhihu Anti-Bot Strategy

Zhihu has very aggressive anti-bot detection. Multi-layered bypass strategy:

**Data Extraction** (auto mode tries in order):
1. **Pure API** (`crypto.py` + `api_client.py:PureAPIClient`) - No browser needed. Pure Python x-zse-96 signature (SM4 cipher) + httpx + saved cookies
2. **Browser API Direct** (`api_client.py:ZhihuAPIClient`) - SignatureOracle uses browser JS to generate x-zse-96 (legacy fallback)
3. **API Intercept** (`scrapers/interceptor.py`) - `page.on('response')` captures API JSON during navigation
4. **DOM Extraction** (original) - CSS selector parsing, scroll pagination

**Browser Connection** (only needed for strategies 2-4):
1. CDP (Chrome DevTools Protocol): `connect_over_cdp()` — undetectable
2. Fallback: launch Playwright with storage_state (may get blocked)

**Anti-Detection Layers**:
- `rate_limiter.py` - Sliding window rate limiting with exponential backoff
- `proxy.py` - Proxy pool with health scoring and automatic rotation
- `anti_detect.py` - CAPTCHA/rate-limit/IP-ban/session-expiry detection with recovery
