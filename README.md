# Web Scraper

统一爬虫框架，整合 Reuters 新闻和小红书内容爬取，支持 CLI 和 MCP Server 两种使用方式。

## Features

- **多源支持**: Reuters 新闻、小红书笔记
- **统一 CLI**: `scraper <source> <command>` 子命令模式
- **MCP Server**: 可作为 LLM Agent 工具使用
- **反检测**: Playwright + 真实 Chrome 浏览器 + Stealth 脚本
- **会话持久化**: Cookie 自动保存，支持断点续爬

## Installation

```bash
# Clone repository
git clone git@github.com:linzhiqin2003/Scraper.git
cd Scraper

# Install dependencies
pip install -e .

# Install Playwright browsers
playwright install chromium
```

## Quick Start

### Reuters

```bash
# Login (interactive mode for CAPTCHA)
scraper reuters login -i

# Check login status
scraper reuters status

# Search articles
scraper reuters search "Federal Reserve" -n 10

# Browse section
scraper reuters section world/china -n 20

# Fetch article
scraper reuters fetch "/world/china/article-url/"
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
scraper xhs --help
```

### Reuters Commands

| Command | Description |
|---------|-------------|
| `login` | Login to Reuters (`-i` for interactive, `-e`/`-p` for credentials) |
| `status` | Check current login status |
| `logout` | Clear saved session |
| `search` | Search articles by keyword |
| `fetch` | Fetch full article content |
| `section` | Browse articles from a section (`list` to show all sections) |

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
- `reuters_search` - Search for news articles
- `reuters_fetch_article` - Fetch full article content
- `reuters_list_section` - List articles from a section
- `reuters_get_sections` - Get available sections

**Xiaohongshu:**
- `xhs_explore` - Explore notes by category
- `xhs_search` - Search for notes
- `xhs_fetch_note` - Fetch a specific note
- `xhs_get_categories` - Get available categories

### Claude Code Configuration

```json
{
  "mcpServers": {
    "web-scraper": {
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
└── xiaohongshu/
    ├── cookies.json          # Session cookies
    └── exports/              # Exported data
```

## Project Structure

```
Scraper/
├── web_scraper/
│   ├── cli.py                # Unified CLI entry
│   ├── mcp_server.py         # MCP Server
│   ├── core/                 # Core modules
│   │   ├── browser.py        # Browser management
│   │   ├── base.py           # Sync scraper base
│   │   ├── async_base.py     # Async scraper base
│   │   ├── storage.py        # Storage utilities
│   │   └── exceptions.py     # Exception hierarchy
│   ├── sources/              # Scraper sources
│   │   ├── reuters/          # Reuters (sync)
│   │   └── xiaohongshu/      # Xiaohongshu (async)
│   └── converters/           # Content converters
├── tests/
├── pyproject.toml
└── README.md
```

## Requirements

- Python 3.11+
- Playwright
- Chrome browser (for best anti-detection)

## License

MIT
