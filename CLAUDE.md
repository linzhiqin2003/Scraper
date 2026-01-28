# Web Scraper - Unified Scraping Framework

## Project Overview

统一爬虫框架，整合 Reuters 和 Xiaohongshu 爬虫，支持 CLI 和 MCP Server 两种使用方式。

## Tech Stack

- Python 3.11+
- Playwright (sync & async API)
- Typer (CLI)
- Rich (Terminal UI)
- FastMCP (MCP Server)
- Pydantic (Data Models)

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
│   │   ├── storage.py          # Storage utilities
│   │   └── exceptions.py       # Exception hierarchy
│   │
│   ├── sources/                # Scraper sources
│   │   ├── __init__.py         # Source registry
│   │   ├── reuters/            # Reuters (sync)
│   │   └── xiaohongshu/        # Xiaohongshu (async)
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

```bash
# Show available sources
scraper sources

# Reuters
scraper reuters login [-e email] [-p password] [-i]
scraper reuters status
scraper reuters search "keyword" -n 10 --section world
scraper reuters fetch <url>
scraper reuters section list
scraper reuters section world/china -n 20

# Xiaohongshu
scraper xhs login [--qrcode | --phone]
scraper xhs auth
scraper xhs explore --category 推荐 -l 20
scraper xhs search "关键词" --type video -l 50
scraper xhs note <note_id> --token <xsec_token>
scraper xhs categories
```

## MCP Tools

### Reuters
- `reuters_search` - Search for news articles
- `reuters_fetch_article` - Fetch full article content
- `reuters_list_section` - List articles from a section
- `reuters_get_sections` - Get available sections

### Xiaohongshu
- `xhs_explore` - Explore notes by category
- `xhs_search` - Search for notes
- `xhs_fetch_note` - Fetch a specific note
- `xhs_get_categories` - Get available categories

## Data Storage

```
~/.web_scraper/
├── reuters/
│   ├── browser_state.json      # Session cookies + localStorage
│   └── exports/                # Exported data
├── xiaohongshu/
│   ├── cookies.json            # Session cookies
│   └── exports/                # Exported data
└── config.json                 # Global config (future)
```

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

- Reuters: Synchronous (simpler for sequential scraping)
- Xiaohongshu: Asynchronous (required for concurrent operations)

### Anti-Detection

Both sources share anti-detection measures in `core/browser.py`:
- webdriver property hidden
- Fake plugins/languages
- Chrome channel for real browser
- Cookie persistence per source
