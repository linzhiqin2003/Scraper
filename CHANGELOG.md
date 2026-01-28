# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- **WSJ MCP Tool `wsj_get_search_options`** - 获取可用的搜索筛选选项
  - 返回 sort, date_range, sources 三类筛选的可用值
  - 方便 AI 在调用 `wsj_search` 前了解可用选项

### Fixed
- **WSJ 搜索参数修正** - 通过 Playwright 实际探索 WSJ 搜索页面验证正确的 URL 参数值
  - 日期范围参数：
    - `week`: `1w` → `7d`
    - `month`: `1m` → `30d`
    - `year`: `1y` → `1yr`
  - 排序参数：
    - `relevance`: `""` (空字符串) → `"relevance"`

### Added
- `docs/SOURCE_DEVELOPMENT_GUIDE.md` - 完整的源开发规范文档
  - 架构概述和设计原则
  - 目录结构和命名规范
  - 源注册机制说明
  - 数据模型 (Pydantic) 规范
  - 同步/异步爬虫实现指南
  - CLI 集成规范 (Typer)
  - MCP 工具规范 (FastMCP)
  - 配置与选择器最佳实践
  - 错误处理规范
  - 测试规范
  - 完整的代码模板

- **WSJ (Wall Street Journal) 源** - 从 wsjscraper 项目合并
  - 使用 httpx + BeautifulSoup 实现（轻量级，无需浏览器）
  - RSS Feeds 支持 (6 个分类: world, markets, technology, business, opinion, lifestyle)
  - 搜索功能（解析 SSR 页面中的 JSON 数据）
  - 文章全文抓取（支持 paywall 检测）
  - 发布时间提取：优先 `<time>` 标签，回退到 meta 标签，Live Coverage 页面从 `__NEXT_DATA__` JSON 提取
  - Netscape cookies.txt 格式支持
  - CLI 命令: `check-cookies`, `import-cookies`, `categories`, `feeds`, `search`, `fetch`, `scrape-feeds`
  - MCP 工具: `wsj_search`
  - Cookies 存储在 `~/.web_scraper/wsj/cookies.txt`

- **Reuters API 客户端** (`client.py`) - 从 ReuterNews 项目迁移
  - 统一客户端: API 优先，Playwright 回退
  - Arc Publishing API 端点支持 (search, section)
  - CAPTCHA 检测和自动回退机制
  - HTTP 文章抓取（比 Playwright 快 5x）
  - MCP 工具: `reuters_search`

- **Reuters 浏览器状态导出脚本** (`scripts/export_reuters_state.js`)
  - 从 Chrome 控制台导出 cookies + localStorage
  - 用于绑过 Datadome TLS 指纹检测
  - 配合 `scraper reuters import-state` 命令使用

- **Reuters CLI 命令** - API 优先模式
  - `import-state` - 导入浏览器状态（cookies + localStorage）
  - `search`, `fetch`, `section` 命令现在默认使用 API，失败时回退到 Playwright
  - 添加 `--browser` / `-b` 选项强制使用浏览器模式
  - API 模式比 Playwright 快 5-10 倍

### Changed
- **MCP Server 简化** - 只暴露两个搜索工具
  - `reuters_search(query, limit, fetch_content, section, date_range)`
  - `wsj_search(query, limit, fetch_content, pages, sort, date_range, sources)`
  - `fetch_content` 参数控制是否获取文章全文（默认 True）
  - 返回标准化结构：title, url, published_at, author, content
- **WSJ `search` 命令重构** - 合并原 `search` 和 `search-scrape` 命令
  - 默认：搜索并抓取所有文章内容
  - `--shallow` / `-s`：仅显示 URL，不抓取内容
  - `--limit` / `-n`：限制抓取文章数量
  - `--delay` / `-d`：请求间隔（秒）
  - **新增搜索筛选器**（通过探索真实搜索页面获取）：
    - `--sort`：排序方式 - newest, oldest, relevance
    - `--date`：时间范围 - day, week, month, year, all
    - `--sources`：内容来源 - articles, video, audio, livecoverage, buyside（逗号分隔）
- 添加 `httpx`, `feedparser`, `lxml`, `requests` 依赖到 `pyproject.toml`
- 更新 MCP Server 说明以包含 WSJ 工具
- WSJ CLI `fetch` 命令现在显示发布时间
- Reuters MCP 工具现在使用 API 客户端（更快，资源占用更低）
- `core/browser.py` - 使用 Playwright `storage_state` 恢复完整浏览器状态（cookies + localStorage）
- `core/browser.py` - 使用 `--headless=new` Chrome 新 headless 模式（更难被检测）
- `core/base.py` - 移除冗余的 cookie 加载，storage_state 现在在创建 context 时自动加载
- Reuters API 客户端改用 `requests.Session()` 正确设置 cookie domain/path

## [0.1.0] - 2026-01-28

### Added
- 初始版本：统一爬虫框架
- 核心模块 (`core/`)
  - `BaseScraper` - 同步爬虫基类
  - `AsyncBaseScraper` - 异步爬虫基类
  - `BrowserManager` - 浏览器生命周期管理
  - `JSONStorage` / `CSVStorage` - 数据存储
  - 标准异常层级
- Reuters 源
  - 搜索、文章详情、栏目列表功能
  - 90+ 栏目配置
- Xiaohongshu 源
  - 探索、搜索、笔记详情功能
  - 11 个分类频道
- 统一 CLI 入口 (`scraper`)
- MCP Server 集成
- 反检测措施（隐身脚本、Cookie 持久化）
