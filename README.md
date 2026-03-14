# Web Scraper

统一爬虫框架，整合 Reuters、WSJ、Google Scholar、Weibo、知乎、小红书、抖音、京东、新浪新闻、爱给网、Serper、Google CSE、携程、大众点评内容爬取，支持 CLI 和 MCP Server 两种使用方式。

## Features

- **14 源支持**: Reuters、WSJ、Scholar、Weibo、Zhihu、XHS、Douyin、JD、Sina、Aigei、Serper、Google CSE、Ctrip、Dianping
- **统一 CLI**: `scraper <source> <command>` 子命令模式，所有源命令标准化
- **MCP Server**: 可作为 LLM Agent 工具使用（`scraper-mcp`）
- **反检测**: Playwright + 真实 Chrome + Stealth 脚本 + UA 池 + 代理池
- **会话持久化**: Cookie 自动保存，支持断点续爬
- **API 优先**: Reuters 使用 Arc API，Zhihu 使用纯 Python 签名绕过，JD 使用 h5st 签名
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

# Install Patchright browsers (optional, for browser-based sources)
patchright install chromium
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
# Login with stored credentials (preferred, headed by default)
scraper wsj login

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

Stored credentials path: `~/.openclaw/credentials/wsj/account.json`

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

### Douyin (抖音)

```bash
# Import cookies from browser (Netscape .txt or JSON array)
scraper douyin import-cookies ~/Downloads/www.douyin.com_cookies.txt

# Check login status
scraper douyin status

# Login interactively (QR code in browser)
scraper douyin login

# Fetch comments from a video URL
scraper douyin fetch https://www.douyin.com/video/7613328220456226089

# Fetch comments directly from a video ID
scraper douyin fetch 7613328220456226089

# Fetch 100 comments
scraper douyin fetch <url> -n 100

# Fetch comments with replies
scraper douyin fetch <url> -n 50 --with-replies

# Download video to local MP4
scraper douyin download https://www.douyin.com/jingxuan?modal_id=7613349187447440817

# Download video to a specific file
scraper douyin download <url> -o /tmp/douyin_video.mp4

# Batch download multiple videos to one directory
scraper douyin download <url1> <url2> --output-dir /tmp/douyin_batch

# Batch download from a text file (one URL or video ID per line)
scraper douyin download --input-file urls.txt --output-dir /tmp/douyin_batch

# Fetch user profile
scraper douyin profile https://www.douyin.com/user/MS4wLjAB...

# Fetch user's video list
scraper douyin videos https://www.douyin.com/user/MS4wLjAB... --limit 50

# Save to specific file
scraper douyin fetch <url> -n 50 -o comments.json

# Clear saved session
scraper douyin logout
```

> **Note**: Douyin uses `a_bogus` request signing that can only be computed inside a real browser.
> The scraper uses Playwright response interception — the browser navigates to the video page and
> the comment API responses are captured automatically, requiring no manual signature computation.

### JD (京东)

```bash
# Import cookies from browser
scraper jd import-cookies ~/Downloads/jd_cookies.txt

# Check login & cookie validity
scraper jd status

# Search products
scraper jd search "机械键盘" -n 20

# Search with filters (sort, price, delivery)
scraper jd search "显卡" --sort price_asc --min-price 2000 --max-price 5000

# Fetch product detail (SKU variants, promotions, comments)
scraper jd fetch <sku_id>

# Fetch product comments
scraper jd comments <sku_id> -n 50

# Fetch comments with filters (score, pictures, sorting)
scraper jd comments <sku_id> --score good --has-pic --sort newest

# Batch scrape comments from search results
scraper jd batch-comments <search_result.json>

# Show sort modes and options
scraper jd options
```

> **Note**: JD 使用 h5st 签名机制绕过反爬，支持 API 模式（httpx + h5st）和 Playwright 回退两种策略。

### Sina News (新浪新闻)

```bash
# Search news with time range
scraper sina search "人工智能" --start-time "2025-01-01" --end-time "2025-12-31"

# Adaptive time-window splitting for large queries
scraper sina search "经济" --start-time "2020-01-01" --end-time "2025-12-31" --adaptive

# Split by year to avoid rate limits
scraper sina search "科技" --start-time "2020-01-01" --end-time "2025-12-31" --split-by-year

# Filter by source and limit results
scraper sina search "AI" --source 新浪科技 --limit 100

# Export to CSV/JSON
scraper sina search "keyword" -o results.csv
```

### Aigei (爱给网 GIF)

```bash
# Check website connectivity
scraper aigei status

# Search GIF resources
scraper aigei search "猫咪" -n 20

# Multi-keyword batch search
scraper aigei search "猫咪" "狗狗" "兔子" --pages 3

# Search and download free GIFs
scraper aigei search "表情包" --download

# Fetch all pages
scraper aigei search "动画" --all

# Show available options and resource types
scraper aigei options
```

### Serper (Google Search API)

```bash
# Requires: SERPER_API_KEY env var (https://serper.dev)
scraper serper status                                    # Check API key
scraper serper search "Python asyncio" -n 10             # Web search
scraper serper search "AI news" --type news --time week  # News search
scraper serper search "query" --country cn --lang zh-cn  # Localized search
scraper serper fetch <url>                               # Fetch URL content
scraper serper options                                   # Show options
```

### Google Custom Search

```bash
# Requires: GOOGLE_CSE_API_KEY + GOOGLE_CSE_CX env vars
scraper google status                                    # Check API config
scraper google search "machine learning" -n 5            # Web search
scraper google search "query" --date-restrict week       # Date filter
scraper google fetch <url>                               # Fetch URL content
scraper google options                                   # Show options + setup guide
```

### Ctrip (携程)

```bash
# Import cookies from browser
scraper ctrip import-cookies ~/Downloads/ctrip_cookies.txt

# Check login status
scraper ctrip status

# Search hotels
scraper ctrip search 上海 --checkin 2026-03-10 --checkout 2026-03-11 -n 10

# Search flights
scraper ctrip flight-search 上海 北京 --date 2026-03-10 -n 10

# Search direct flights only
scraper ctrip flight-search 上海 北京 --date 2026-03-10 --direct-only

# Query low-price calendar
scraper ctrip flight-calendar 上海 北京 --date 2026-03-10 --days 15

# Show built-in flight city codes
scraper ctrip flight-cities
```

### Dianping (大众点评)

```bash
# Login interactively (browser)
scraper dianping login

# Import cookies from browser
scraper dianping import-cookies ~/Downloads/dianping_cookies.txt

# Check login status
scraper dianping status

# Search shops (auto fallback to browser on verification)
scraper dianping search "北京 烤鸭" -n 10

# Force browser mode for search
scraper dianping search "上海 咖啡" --browser

# Browse home feed
scraper dianping browse --limit 20

# Fetch shop detail (deals, dishes, comments)
scraper dianping shop <url_or_uuid>

# Fetch note/article detail
scraper dianping note <url_or_id>

# Auto-detect and fetch (shop or note)
scraper dianping fetch <url>

# Clear session
scraper dianping logout
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
| `login` | Interactive login | Reuters, XHS, Zhihu, Weibo, Douyin, Dianping |
| `status` | Check auth/cookie status | All 14 sources |
| `logout` | Clear session | Reuters, XHS, Zhihu, Weibo, Douyin, Dianping |
| `import-cookies` | Import browser cookies | Reuters, WSJ, Scholar, Zhihu, Douyin, JD, Ctrip, Dianping |
| `search` | Search content | Reuters, WSJ, Scholar, Zhihu, Weibo, XHS, JD, Sina, Aigei, Dianping |
| `fetch` | Fetch single item by URL/ID | All 14 sources |
| `browse` | Browse/discover content | Reuters, XHS, WSJ, Weibo, Dianping |
| `options` | Show available filters/categories | Reuters, WSJ, Scholar, Zhihu, Weibo, XHS, JD, Aigei |

Standard parameters: `-n/--limit`, `-o/--output`, `--no-save`, `--shallow/-s`

### Source-specific Commands

| Command | Source | Function |
|---------|--------|----------|
| `download` | Douyin | Download videos (single/batch) |
| `profile` | Douyin | Fetch user profile |
| `videos` | Douyin | Fetch user's video list |
| `comments` | JD | Product comment scraping |
| `batch-comments` | JD | Batch comment scraping |
| `flight-search` | Ctrip | Search flights |
| `flight-calendar` | Ctrip | Low-price flight calendar |
| `flight-cities` | Ctrip | List flight city codes |
| `shop` | Dianping | Shop detail page |
| `note` | Dianping | Note/article detail |
| `hot` | Weibo | Hot-search topics |
| `proxy-status` | Zhihu | Proxy pool status |

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

> Douyin, JD, Sina, Aigei 目前为 CLI-only（未暴露为 MCP 工具）。

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
├── xiaohongshu/
│   ├── cookies.json          # Session cookies
│   └── exports/
├── douyin/
│   ├── browser_state.json    # Session (cookies from browser export)
│   └── exports/
├── jd/
│   ├── cookies.txt           # Netscape format cookies
│   └── exports/
├── sina/
│   └── exports/
├── aigei/
│   └── exports/
├── serper/
│   └── exports/
├── google/
│   └── exports/
├── ctrip/
│   ├── browser_state.json
│   └── exports/
└── dianping/
    ├── browser_state.json
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
│   │   ├── xiaohongshu/        # Xiaohongshu (async, Playwright)
│   │   ├── douyin/             # Douyin (sync, Playwright response interception)
│   │   ├── jd/                 # JD 京东 (httpx + h5st signing + Playwright)
│   │   ├── sina/               # Sina News 新浪新闻 (httpx)
│   │   ├── aigei/              # Aigei 爱给网 GIF (httpx)
│   │   ├── serper/             # Serper Google Search API
│   │   ├── google/             # Google Custom Search API
│   │   ├── ctrip/              # Ctrip 携程 (Playwright)
│   │   └── dianping/           # Dianping 大众点评 (Playwright)
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
- Playwright (for Reuters, Xiaohongshu, Zhihu fallback, Weibo fallback, Douyin, JD fallback, Ctrip, Dianping)
- httpx (for WSJ, Scholar, Zhihu, Weibo, JD, Sina, Aigei)
- Chrome browser (for best anti-detection)

## License

MIT
