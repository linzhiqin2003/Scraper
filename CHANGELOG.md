# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- **反爬基础设施抽取到 core/** - 将散落在各源的反爬能力统一为可复用的核心模块
  - `core/user_agent.py` — UA 池 + Header 生成（UAProfile 绑定 UA + Sec-Ch-Ua + platform，`build_browser_headers()` / `build_api_headers()` 替代各源硬编码 DEFAULT_HEADERS）
  - `core/proxy.py` — 从 zhihu 迁移的通用代理池（健康评分、自动轮换、API 刷新）
  - `core/rate_limiter.py` — 从 zhihu 迁移的滑动窗口限速器 + 新增 `AsyncRateLimiter`（异步源用）
  - `core/captcha.py` — 打码接口抽象（`CaptchaSolver` ABC + `NullCaptchaSolver` 默认 + `TwoCaptchaSolver` 实现）
  - 各源 scraper 构造函数新增可选 `rate_limiter` / `proxy_pool` 参数（依赖注入模式）
  - Zhihu proxy.py / rate_limiter.py 改为 re-export shim，向后兼容

### Changed
- **各源 DEFAULT_HEADERS 统一** — Reuters/WSJ/Scholar/Weibo/Zhihu 的硬编码 headers 改用 `build_browser_headers()` / `build_api_headers()` 生成
- **core/browser.py** — 删除 UA 列表，改用 `core/user_agent.py` 的 `get_random_user_agent()`
- **共享 Rich UI display 模块** (`core/display.py`) - 统一所有源的终端输出风格
  - `display_auth_status()` - 认证状态 Panel（蓝色边框 + key-value 表格）
  - `display_search_results()` - 搜索结果表格（自动编号、magenta 表头、show_lines）
  - `display_detail()` - 详情显示（元数据 Panel + 正文 Panel + 可选子表格）
  - `display_options()` - 选项/分类列表
  - `display_saved()` - 保存路径反馈
  - `ColumnDef` 数据类定义表格列（支持 style, max_width, formatter）
  - 统一样式规范：标题=bold, URL=dim, 时间=green, 作者=cyan, 分类=magenta, 统计=yellow

### Changed
- **CLI 命令标准化** - 所有 6 个源统一命令规范，旧命令保留为隐藏别名
  - 认证检查统一为 `status`（替代 `auth`, `check-cookies`）
  - 单篇获取统一为 `fetch`（替代 `note`, `detail`）
  - 浏览/发现统一为 `browse`（替代 `section`, `explore`, `feeds`, `hot`）
  - 辅助信息统一为 `options`（替代 `categories`, `search-options`, `search-types`）
  - 结果数量参数统一为 `-n/--limit`（XHS 从 `-l` 改为 `-n`）
  - WSJ `feeds` + `scrape-feeds` 合并为 `browse`（`--shallow/--no-shallow` 控制）
- **所有源 CLI 改用共享 display 模块** - 移除各源内部重复的 Rich 渲染代码
  - Reuters: 移除 `status_style()`, `display_auth_status()`，改用共享函数
  - Xiaohongshu: 移除本地 Console 实例，改用共享 `console`
  - WSJ: 移除本地 Console 实例，feed 结果改用表格渲染
  - Scholar: 移除本地 Console 实例，改用 `display_options()` 和 `display_saved()`
  - Zhihu: 移除 `_status_style()`, `_display_auth_status()`，改用共享函数
  - Weibo: 移除 5 个本地 display 函数，全部改用共享模块

- **知乎全面反爬绕过** - 5 阶段综合反爬对策
  - **纯 Python API 客户端** (`crypto.py` + `api_client.py:PureAPIClient`) - 完全无浏览器依赖
    - 纯 Python 实现知乎 x-zse-96 签名算法（逆向自 JSVMP 保护的 JS）
    - SM4 分组密码 + CBC 模式 + 自定义编码（当前生产版本）
    - 简单 XOR + 字符编码（旧版本，保留为 fallback）
    - 仅需 httpx + 保存的 cookies（`browser_state.json`）即可工作
  - **API 响应拦截** (`scrapers/interceptor.py`) - 通过 `page.on('response')` 拦截知乎内部 API 的 JSON 响应，替代脆弱的 DOM CSS 选择器
  - **浏览器 API 直连 + 签名预言机** (`api_client.py:ZhihuAPIClient`) - 利用 CDP 浏览器 JS 上下文生成 x-zse-96 签名（legacy fallback）
  - **智能限速器** (`rate_limiter.py`) - 线程安全的滑动窗口计数器，支持 per-minute/per-hour 限制和指数退避
  - **代理池管理** (`proxy.py`) - HTTP API 代理获取、健康评分、自动封禁/轮换
  - **封禁检测与恢复** (`anti_detect.py`) - CAPTCHA/频率限制/IP 封禁/会话过期检测，附恢复建议
  - **多策略提取链** - SearchScraper/ArticleScraper 现在按 纯API→浏览器API→API拦截→DOM提取 顺序尝试
  - **data_source 字段** - SearchResult 和 ArticleDetail 新增 `data_source` 标记数据来源（pure_api/api_direct/api_intercept/dom）
  - **CLI 新增选项**: `--strategy` (auto/pure_api/api/intercept/dom), `--proxy-api`
  - **CLI 新命令**: `scraper zhihu proxy-status`
  - **MCP 集成**: 模块级单例限速器，auto 策略优先纯 API，对外接口不变（向后兼容）

- **Google Scholar 源** - 新增学术论文搜索与内容抓取
  - 使用 httpx + BeautifulSoup 实现（与 WSJ 模式一致，无需 Playwright）
  - 搜索功能：解析 Scholar HTML 页面，提取标题、作者、摘要、引用数、PDF 链接等
  - 文章全文抓取：通用出版商页面内容提取（支持 `<article>`、`<main>`、已知 class 模式、meta 标签回退）
  - 搜索筛选：按相关度/日期排序、年份范围、语言过滤
  - 多页翻页支持，带随机延迟防反爬
  - CAPTCHA 检测（`/sorry/` 重定向、captcha 表单、429 状态码）
  - 可选 Google cookies 导入（降低 CAPTCHA 频率）
  - CLI 命令: `search`, `fetch`, `import-cookies`, `check-cookies`, `search-options`
  - MCP 工具: `scholar_search`, `scholar_fetch_article`, `scholar_get_search_options`
  - 数据存储在 `~/.web_scraper/scholar/`

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
