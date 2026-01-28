# Web Scraper

统一爬虫框架，整合 Reuters、WSJ 新闻和小红书内容爬取，支持 CLI 和 MCP Server 两种使用方式。

## Features

- **多源支持**: Reuters 新闻、Wall Street Journal、小红书笔记
- **统一 CLI**: `scraper <source> <command>` 子命令模式
- **MCP Server**: 可作为 LLM Agent 工具使用
- **反检测**: Playwright + 真实 Chrome 浏览器 + Stealth 脚本
- **会话持久化**: Cookie 自动保存，支持断点续爬
- **API 优先**: Reuters 使用 Arc Publishing API（更快），失败时回退到 Playwright

## Installation

```bash
# Clone repository
git clone git@github.com:linzhiqin2003/Scraper.git
cd Scraper

# Install with Poetry
poetry install

# Or with pip
pip install -e .

# Install Playwright browsers
playwright install chromium
```

## Quick Start

### Reuters

```bash
# Login (interactive mode for CAPTCHA)
scraper reuters login -i

# Or import browser state from Chrome DevTools
scraper reuters import-state browser_state.json

# Check login status
scraper reuters status

# Search articles (API mode, fast)
scraper reuters search "Federal Reserve" -n 10

# Browse section
scraper reuters section world/china -n 20

# Fetch article
scraper reuters fetch "https://www.reuters.com/world/article-url/"
```

### WSJ (Wall Street Journal)

```bash
# Import cookies from browser (cookies.txt extension)
scraper wsj import-cookies ~/Downloads/cookies.txt

# Check cookies validity
scraper wsj check-cookies

# List RSS categories
scraper wsj categories

# Get RSS feed articles
scraper wsj feeds -c technology -n 20

# Search articles with filters
scraper wsj search "Nvidia" --sort newest --date week --sources articles
scraper wsj search "Tesla" -p 2 --shallow  # Only show URLs

# Fetch full article
scraper wsj fetch "https://www.wsj.com/articles/..."

# RSS + full content scraping
scraper wsj scrape-feeds -c markets -n 5
```

### Xiaohongshu (小红书)

```bash
# Login via QR code
scraper xhs login --qrcode

# Check login status
scraper xhs auth

# Explore by category
scraper xhs explore --category 美食 -l 20

# Search notes
scraper xhs search "旅行攻略" --type video -l 30

# Fetch specific note
scraper xhs note <note_id> --token <xsec_token>
```

## CLI Reference

```bash
# Show all available sources
scraper sources

# Show version
scraper version

# Source-specific help
scraper reuters --help
scraper wsj --help
scraper xhs --help
```

### Reuters Commands

| Command | Description |
|---------|-------------|
| `login` | Login to Reuters (`-i` for interactive, `-e`/`-p` for credentials) |
| `import-state` | Import browser state (cookies + localStorage) from JSON file |
| `status` | Check current login status |
| `logout` | Clear saved session |
| `search` | Search articles by keyword (API mode by default, `-b` for browser) |
| `fetch` | Fetch full article content |
| `section` | Browse articles from a section (`list` to show all sections) |

### WSJ Commands

| Command | Description |
|---------|-------------|
| `import-cookies` | Import cookies.txt from browser |
| `check-cookies` | Verify cookies are valid |
| `categories` | List available RSS feed categories |
| `feeds` | Fetch articles from RSS feeds |
| `search` | Search articles with filters (`--sort`, `--date`, `--sources`) |
| `fetch` | Fetch full article content |
| `scrape-feeds` | RSS feeds + full content scraping |

### Xiaohongshu Commands

| Command | Description |
|---------|-------------|
| `login` | Login (`--qrcode` or `--phone`) |
| `auth` | Check login status |
| `logout` | Clear session |
| `explore` | Browse notes by category |
| `search` | Search notes |
| `note` | Fetch specific note by ID |
| `categories` | List available categories |

## MCP Server

Run as MCP server for LLM integration:

```bash
scraper-mcp
```

### Available Tools

**Reuters:**
- `reuters_search` - Search for news articles (supports section, date_range filters)

**WSJ:**
- `wsj_search` - Search for news articles (supports sort, date_range, sources filters)
- `wsj_get_search_options` - Get available search filter options

### Claude Code Configuration

```json
{
  "mcpServers": {
    "news-search": {
      "command": "scraper-mcp",
      "cwd": "/path/to/Scraper"
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
│   └── exports/              # Exported data
└── xiaohongshu/
    ├── cookies.json          # Session cookies
    └── exports/              # Exported data
```

## Project Structure

```
Scraper/
├── web_scraper/
│   ├── cli.py                # Unified CLI entry
│   ├── mcp_server.py         # MCP Server (news-search)
│   ├── core/                 # Core modules
│   │   ├── browser.py        # Browser management
│   │   ├── base.py           # Sync scraper base
│   │   ├── async_base.py     # Async scraper base
│   │   ├── storage.py        # Storage utilities
│   │   └── exceptions.py     # Exception hierarchy
│   ├── sources/              # Scraper sources
│   │   ├── reuters/          # Reuters (sync, Playwright + API)
│   │   ├── wsj/              # WSJ (sync, httpx)
│   │   └── xiaohongshu/      # Xiaohongshu (async, Playwright)
│   └── converters/           # Content converters
├── scripts/                  # Utility scripts
├── docs/                     # Documentation
├── tests/
├── pyproject.toml
├── CLAUDE.md                 # Project memory for Claude
├── CHANGELOG.md              # Development changelog
└── README.md
```

## Requirements

- Python 3.11+
- Playwright (for Reuters, Xiaohongshu)
- httpx (for WSJ)
- Chrome browser (for best anti-detection)

## License

MIT
