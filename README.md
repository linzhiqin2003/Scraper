# Web Scraper

统一爬虫框架，整合 Reuters、WSJ、Google Scholar、Weibo、知乎和小红书内容爬取，支持 CLI 和 MCP Server 两种使用方式。

## Features

- **6 源支持**: Reuters、WSJ、Google Scholar、Weibo、Zhihu、Xiaohongshu
- **统一 CLI**: `scraper <source> <command>` 子命令模式，所有源命令标准化
- **MCP Server**: 可作为 LLM Agent 工具使用（`scraper-mcp`）
- **反检测**: Playwright + 真实 Chrome + Stealth 脚本 + UA 池 + 代理池
- **会话持久化**: Cookie 自动保存，支持断点续爬
- **API 优先**: Reuters 使用 Arc API，Zhihu 使用纯 Python 签名绕过
- **统一输出**: Rich 表格渲染，统一色彩规范

## Installation

```bash
# Clone repository
git clone git@github.com:linzhiqin2003/Scraper.git
cd Scraper

# Install with Poetry
poetry install

# Or with pip
pip install -e .

# Install Playwright browsers (optional, for browser-based sources)
playwright install chromium
```

## Quick Start

### Reuters

```bash
# Login (interactive mode for CAPTCHA)
scraper reuters login -i

# Check login status
scraper reuters status

# Search articles (API mode, fast)
scraper reuters search "Federal Reserve" -n 10

# Browse section
scraper reuters browse world/china -n 20

# Fetch full article
scraper reuters fetch "https://www.reuters.com/world/article-url/"
```

### WSJ (Wall Street Journal)

```bash
# Import cookies from browser
scraper wsj import-cookies ~/Downloads/cookies.txt

# Check cookies validity
scraper wsj status

# Browse RSS feed articles
scraper wsj browse -c technology -n 20

# Browse with full content
scraper wsj browse -c markets -n 5 --no-shallow

# Search articles with filters
scraper wsj search "Nvidia" --sort newest --date week --sources articles

# Fetch full article
scraper wsj fetch "https://www.wsj.com/articles/..."
```

### Google Scholar

```bash
# Search papers (results only)
scraper scholar search "transformer attention" -n 10 --shallow

# Search + fetch full content
scraper scholar search "transformer attention" -n 5

# Search with filters
scraper scholar search "machine learning" --sort date --year-from 2023

# Fetch single article
scraper scholar fetch "https://arxiv.org/abs/..."

# Import Google cookies (optional, reduces CAPTCHA)
scraper scholar import-cookies ~/Downloads/google_cookies.txt

# Show filter options
scraper scholar options
```

### Zhihu (知乎)

```bash
# Login (interactive browser)
scraper zhihu login

# Or import cookies
scraper zhihu import-cookies ~/Downloads/cookies.json

# Check login status
scraper zhihu status

# Search content (auto strategy: pure API → browser API → intercept → DOM)
scraper zhihu search "transformer" -n 10

# Search with specific strategy
scraper zhihu search "transformer" -n 10 --strategy pure_api

# Search columns
scraper zhihu search "机器学习" -t column

# Fetch article/answer
scraper zhihu fetch "https://zhuanlan.zhihu.com/p/..."

# Show proxy pool status
scraper zhihu proxy-status --proxy-api <url>

# Show search types and strategies
scraper zhihu options
```

### Weibo (微博)

```bash
# Login (interactive browser)
scraper weibo login

# Check login status
scraper weibo status

# Search posts
scraper weibo search "keyword" -n 20

# Fetch post detail
scraper weibo fetch "https://weibo.com/..."

# Browse hot topics
scraper weibo browse

# Clear session
scraper weibo logout
```

### Xiaohongshu (小红书)

```bash
# Login via QR code
scraper xhs login --qrcode

# Check login status
scraper xhs status

# Browse by category
scraper xhs browse --category 美食 -n 20

# Search notes
scraper xhs search "旅行攻略" --type video -n 30

# Fetch specific note
scraper xhs fetch <note_id> --token <xsec_token>

# Show categories and search types
scraper xhs options
```

## CLI Reference

```bash
# Show all available sources
scraper sources

# Show version
scraper version

# Source-specific help
scraper <source> --help
```

### Standardized Commands

All sources follow a unified command convention:

| Command | Function | Sources |
|---------|----------|---------|
| `login` | Interactive login | Reuters, XHS, Zhihu, Weibo |
| `status` | Check auth/cookie status | All 6 sources |
| `logout` | Clear session | Reuters, XHS, Zhihu, Weibo |
| `import-cookies` | Import browser cookies | Reuters, WSJ, Scholar, Zhihu |
| `search` | Search content | All 6 sources |
| `fetch` | Fetch single item by URL/ID | All 6 sources |
| `browse` | Browse/discover content | Reuters, XHS, WSJ, Weibo |
| `options` | Show available filters/categories | All 6 sources |

Standard parameters: `-n/--limit`, `-o/--output`, `--no-save`, `--shallow/-s`

## MCP Server

Run as MCP server for LLM integration:

```bash
scraper-mcp
```

### Available Tools

**Reuters:**
- `reuters_search` - Search for news articles
- `reuters_fetch_article` - Fetch full article content
- `reuters_list_section` - List articles from a section
- `reuters_get_sections` - Get available sections

**WSJ:**
- `wsj_search` - Search for news articles (sort, date_range, sources filters)
- `wsj_fetch_article` - Fetch full article content
- `wsj_feeds` - Get articles from RSS feeds
- `wsj_get_categories` - Get available RSS categories
- `wsj_get_search_options` - Get search filter options

**Google Scholar:**
- `scholar_search` - Search academic papers
- `scholar_fetch_article` - Fetch full article content
- `scholar_get_search_options` - Get search filter options

**Zhihu:**
- `zhihu_search` - Search content (multi-strategy)
- `zhihu_fetch_article` - Fetch article/answer content
- `zhihu_get_search_types` - Get search type filters

**Weibo:**
- `weibo_search` - Search posts
- `weibo_fetch_detail` - Fetch post detail
- `weibo_hot` - Get hot topics

**Xiaohongshu:**
- `xhs_explore` - Explore notes by category
- `xhs_search` - Search notes
- `xhs_fetch_note` - Fetch a specific note
- `xhs_get_categories` - Get available categories

### Claude Code Configuration

```json
{
  "mcpServers": {
    "web-scraper": {
      "command": "scraper-mcp",
      "cwd": "/path/to/WebScraper"
    }
  }
}
```

## Data Storage

```
~/.web_scraper/
├── reuters/
│   ├── browser_state.json    # Session (cookies + localStorage)
│   └── exports/              # Exported data
├── wsj/
│   ├── cookies.txt           # Netscape format cookies
│   └── exports/
├── scholar/
│   ├── cookies.txt           # Google cookies (optional)
│   └── exports/
├── zhihu/
│   ├── browser_state.json    # Session (cookies + localStorage)
│   └── exports/
├── weibo/
│   ├── browser_state.json    # Session
│   └── exports/
└── xiaohongshu/
    ├── cookies.json          # Session cookies
    └── exports/
```

## Project Structure

```
WebScraper/
├── web_scraper/
│   ├── cli.py                  # Unified CLI entry
│   ├── mcp_server.py           # Unified MCP Server
│   │
│   ├── core/                   # Core modules (shared)
│   │   ├── browser.py          # Browser management (sync + async)
│   │   ├── base.py             # Sync scraper base class
│   │   ├── async_base.py       # Async scraper base class
│   │   ├── display.py          # Shared Rich UI display module
│   │   ├── storage.py          # Storage utilities
│   │   ├── exceptions.py       # Exception hierarchy
│   │   ├── user_agent.py       # UA pool + header generation
│   │   ├── proxy.py            # Proxy pool with health scoring
│   │   ├── rate_limiter.py     # Rate limiter (sync + async)
│   │   └── captcha.py          # CAPTCHA solver interface
│   │
│   ├── sources/                # Scraper sources
│   │   ├── reuters/            # Reuters (sync, Playwright + API)
│   │   ├── wsj/                # WSJ (sync, httpx)
│   │   ├── scholar/            # Google Scholar (sync, httpx + BeautifulSoup)
│   │   ├── zhihu/              # Zhihu (httpx API + Playwright CDP)
│   │   ├── weibo/              # Weibo (httpx API + Playwright fallback)
│   │   └── xiaohongshu/        # Xiaohongshu (async, Playwright)
│   │
│   └── converters/             # Content converters
│       └── markdown.py
│
├── docs/                       # Documentation
├── tests/
├── pyproject.toml
├── CLAUDE.md
├── CHANGELOG.md
└── README.md
```

## Requirements

- Python 3.11+
- Playwright (for Reuters, Xiaohongshu, Zhihu fallback, Weibo fallback)
- httpx (for WSJ, Scholar, Zhihu, Weibo)
- Chrome browser (for best anti-detection)

## License

MIT
