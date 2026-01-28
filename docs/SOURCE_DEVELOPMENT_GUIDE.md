# Web Scraper 源开发规范

本文档定义了向 WebScraper 框架添加新爬虫源的标准化要求和最佳实践。

---

## 目录

1. [架构概述](#1-架构概述)
2. [目录结构规范](#2-目录结构规范)
3. [源注册规范](#3-源注册规范)
4. [数据模型规范](#4-数据模型规范)
5. [爬虫实现规范](#5-爬虫实现规范)
6. [CLI 集成规范](#6-cli-集成规范)
7. [MCP 工具规范](#7-mcp-工具规范)
8. [配置与选择器规范](#8-配置与选择器规范)
9. [错误处理规范](#9-错误处理规范)
10. [测试规范](#10-测试规范)
11. [代码模板](#11-代码模板)

---

## 1. 架构概述

### 1.1 设计原则

WebScraper 采用**插件式架构**，每个爬虫源作为独立模块存在：

```
┌─────────────────────────────────────────────────────┐
│                    CLI / MCP Server                  │
├─────────────────────────────────────────────────────┤
│                   源注册系统 (Registry)              │
├──────────────┬──────────────┬──────────────┬────────┤
│   Reuters    │  Xiaohongshu │   NewSource  │  ...   │
├──────────────┴──────────────┴──────────────┴────────┤
│                   核心模块 (Core)                    │
│  ├── BaseScraper / AsyncBaseScraper                 │
│  ├── BrowserManager                                 │
│  ├── Storage (JSON/CSV)                             │
│  └── Exceptions                                     │
└─────────────────────────────────────────────────────┘
```

### 1.2 核心概念

| 概念 | 说明 |
|------|------|
| **Source** | 一个完整的爬虫源，包含配置、模型、爬虫、CLI 命令 |
| **Scraper** | 具体的爬虫类，继承基类，实现 `scrape()` 方法 |
| **Model** | Pydantic 数据模型，定义爬取数据的结构 |
| **Registry** | 源注册表，管理所有可用源 |

### 1.3 同步 vs 异步

| 场景 | 推荐模式 | 示例 |
|------|---------|------|
| 简单顺序爬取 | 同步 (`BaseScraper`) | Reuters |
| 并发/复杂交互 | 异步 (`AsyncBaseScraper`) | Xiaohongshu |
| 需要共享浏览器 | 异步 + `BrowserManager` | Xiaohongshu |

---

## 2. 目录结构规范

### 2.1 必需的目录结构

```
web_scraper/sources/{source_name}/
├── __init__.py              # [必需] 源注册入口
├── config.py                # [必需] 配置常量和选择器
├── models.py                # [必需] Pydantic 数据模型
├── cli.py                   # [必需] Typer CLI 命令
├── auth.py                  # [可选] 认证/登录逻辑
├── converters.py            # [可选] 数据转换器
└── scrapers/                # [必需] 爬虫实现
    ├── __init__.py          # 导出所有爬虫类
    ├── search.py            # 示例：搜索爬虫
    ├── item.py              # 示例：详情爬虫
    └── list.py              # 示例：列表爬虫
```

### 2.2 命名规范

| 类型 | 规范 | 示例 |
|------|------|------|
| 目录名 | 小写，下划线分隔 | `xiaohongshu`, `new_source` |
| 源标识符 | 小写，简短 | `xhs`, `reuters` |
| 类名 | PascalCase + 功能后缀 | `SearchScraper`, `ArticleScraper` |
| 模型名 | PascalCase，名词 | `Article`, `NoteCard`, `SearchResult` |

---

## 3. 源注册规范

### 3.1 注册文件 (`__init__.py`)

每个源必须在其 `__init__.py` 中调用 `register_source()`：

```python
"""
{Source Name} scraper source.

This module provides scraping capabilities for {website}.
"""
from .. import register_source, SourceConfig

# 延迟导入 CLI 以避免循环依赖
from .cli import app as cli_app

# 源注册 - 必需
register_source(SourceConfig(
    name="source_id",           # 唯一标识符，用于 CLI 子命令
    display_name="Source Name", # UI 显示名称
    cli_app=cli_app,            # Typer 子应用
    data_dir_name="source_dir", # ~/.web_scraper/{data_dir_name}/
    is_async=False,             # True 表示异步源
))

# 导出列表
__all__ = ["cli_app"]
```

### 3.2 SourceConfig 字段说明

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `name` | `str` | 是 | CLI 子命令名 (`scraper {name} ...`) |
| `display_name` | `str` | 是 | 在 `scraper sources` 中显示的名称 |
| `cli_app` | `typer.Typer` | 是 | 该源的 CLI 子应用 |
| `data_dir_name` | `str` | 是 | 数据存储目录名 |
| `is_async` | `bool` | 否 | 默认 `False`，异步源设为 `True` |

### 3.3 自动发现机制

框架会在 `sources/__init__.py` 中自动加载所有源：

```python
# sources/__init__.py 中的加载逻辑
def _load_sources():
    # 显式导入每个源以触发注册
    from . import reuters
    from . import xiaohongshu
    from . import new_source  # 新源需要添加到这里
```

**添加新源时**：必须在 `sources/__init__.py` 的 `_load_sources()` 中添加导入语句。

---

## 4. 数据模型规范

### 4.1 基本要求

所有数据模型必须：

1. 继承 `pydantic.BaseModel`
2. 使用 `Field()` 定义字段描述
3. 提供类型注解
4. 定义 `model_config` 配置（如需要）

```python
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class Author(BaseModel):
    """作者信息模型。"""
    user_id: str = Field(description="用户唯一标识")
    nickname: str = Field(description="用户昵称")
    avatar: Optional[str] = Field(default=None, description="头像 URL")


class Article(BaseModel):
    """文章详情模型。"""
    id: str = Field(description="文章唯一标识")
    title: str = Field(description="文章标题")
    content: str = Field(description="文章正文（Markdown 格式）")
    author: Author = Field(description="作者信息")
    published_at: Optional[datetime] = Field(default=None, description="发布时间")
    tags: List[str] = Field(default_factory=list, description="标签列表")
    url: str = Field(description="原文链接")

    model_config = {
        "json_encoders": {
            datetime: lambda v: v.isoformat() if v else None
        }
    }
```

### 4.2 标准模型模式

每个源应定义以下标准模型（按需）：

| 模型 | 用途 | 必需字段 |
|------|------|---------|
| `SearchResult` | 搜索结果列表项 | `id`, `title`, `url` |
| `ListItem` | 列表页项目 | `id`, `title`, `url`, `summary` |
| `Detail` | 详情页完整内容 | `id`, `title`, `content`, `url` |
| `Author` | 嵌套的作者信息 | `user_id`, `nickname` |

### 4.3 嵌套模型规范

```python
# 推荐：定义独立的嵌套模型
class Author(BaseModel):
    user_id: str
    nickname: str

class Article(BaseModel):
    author: Author  # 引用嵌套模型

# 避免：内联定义复杂嵌套
class Article(BaseModel):
    author: dict  # 不推荐
```

---

## 5. 爬虫实现规范

### 5.1 同步爬虫基类

继承 `BaseScraper` 实现同步爬虫：

```python
from web_scraper.core.base import BaseScraper
from .config import SOURCE_NAME, BASE_URL
from .models import SearchResult


class SearchScraper(BaseScraper):
    """搜索爬虫。"""

    # 必需的类属性
    SOURCE_NAME = SOURCE_NAME
    BASE_URL = BASE_URL

    # 可选：自定义速率限制检测模式
    RATE_LIMIT_PATTERN = r"rate limit|too many requests|429"

    def scrape(self, query: str, max_results: int = 10) -> List[SearchResult]:
        """
        主爬虫方法。

        Args:
            query: 搜索关键词
            max_results: 最大结果数

        Returns:
            搜索结果列表
        """
        with self.get_page() as page:
            # 1. 导航到搜索页
            page.goto(f"{self.BASE_URL}/search?q={query}")

            # 2. 等待结果加载
            self.wait_for_elements(page, ".result-item", timeout=10000)

            # 3. 检查速率限制
            if self.check_rate_limit(page):
                self.handle_rate_limit(page)

            # 4. 提取数据
            results = []
            items = page.query_selector_all(".result-item")[:max_results]
            for item in items:
                results.append(self._extract_result(item))

            return results

    def _extract_result(self, element) -> SearchResult:
        """从 DOM 元素提取搜索结果。"""
        return SearchResult(
            id=self.safe_get_attribute(element, "a", "data-id") or "",
            title=self.safe_get_text(element, ".title") or "",
            url=self.normalize_url(
                self.safe_get_attribute(element, "a", "href") or ""
            ),
        )
```

### 5.2 异步爬虫基类

继承 `AsyncBaseScraper` 实现异步爬虫：

```python
from web_scraper.core.async_base import AsyncBaseScraper
from web_scraper.core.browser import BrowserManager
from .config import SOURCE_NAME, BASE_URL
from .models import ExploreResult, NoteCard


class ExploreScraper(AsyncBaseScraper):
    """探索页爬虫。"""

    SOURCE_NAME = SOURCE_NAME
    BASE_URL = BASE_URL

    # 可选：定义选择器列表
    LOGIN_SELECTORS = [".login-modal", "#login-popup"]
    RATE_LIMIT_SELECTORS = [".rate-limit-warning"]
    CAPTCHA_SELECTORS = [".captcha-container"]

    def __init__(self, browser: BrowserManager):
        super().__init__(browser)

    async def scrape(
        self,
        category: str = "推荐",
        limit: int = 20,
    ) -> ExploreResult:
        """
        异步爬取探索页。

        Args:
            category: 分类名称
            limit: 获取数量

        Returns:
            探索结果
        """
        page = await self.browser.new_page()
        try:
            # 1. 导航
            await page.goto(f"{self.BASE_URL}/explore")

            # 2. 关闭登录弹窗（如有）
            await self._close_login_modal(page)

            # 3. 检查登录状态
            if await self._check_login_required(page):
                raise NotLoggedInError("需要登录")

            # 4. 滚动加载数据
            notes = await self._collect_items(page, limit)

            return ExploreResult(category=category, notes=notes)
        finally:
            await page.close()

    async def _collect_items(self, page, limit: int) -> List[NoteCard]:
        """滚动并收集项目。"""
        items = []
        seen_ids = set()

        while len(items) < limit:
            # 获取当前页面的项目
            elements = await page.query_selector_all(".note-item")
            for el in elements:
                item = await self._extract_item(el)
                if item and item.id not in seen_ids:
                    seen_ids.add(item.id)
                    items.append(item)

            # 滚动加载更多
            await self._scroll_page(page)
            await page.wait_for_timeout(1000)

        return items[:limit]
```

### 5.3 必须实现的方法

| 基类 | 必须实现 | 签名 |
|------|---------|------|
| `BaseScraper` | `scrape()` | `def scrape(self, *args, **kwargs) -> Any` |
| `AsyncBaseScraper` | `scrape()` | `async def scrape(self, *args, **kwargs) -> Any` |

### 5.4 可复用的基类方法

**同步基类 (`BaseScraper`)**

| 方法 | 用途 |
|------|------|
| `get_page()` | 获取已认证的 Page（上下文管理器） |
| `wait_for_element()` | 等待单个元素出现 |
| `wait_for_elements()` | 等待多个元素出现 |
| `safe_get_text()` | 安全获取元素文本 |
| `safe_get_attribute()` | 安全获取元素属性 |
| `normalize_url()` | 相对 URL 转绝对 URL |
| `scroll_to_load()` | 滚动加载更多内容 |
| `check_rate_limit()` | 检测速率限制 |
| `handle_rate_limit()` | 处理速率限制（指数退避） |

**异步基类 (`AsyncBaseScraper`)**

| 方法 | 用途 |
|------|------|
| `_wait_for_element()` | 异步等待元素 |
| `_scroll_page()` | 异步滚动页面 |
| `_scroll_and_load()` | 滚动并收集元素 |
| `_retry_operation()` | 带退避的重试 |
| `_check_login_required()` | 检测登录要求 |
| `_check_rate_limit()` | 检测速率限制 |
| `_check_captcha()` | 检测验证码 |
| `_close_login_modal()` | 关闭登录弹窗 |
| `_extract_param_from_url()` | 提取 URL 参数 |

---

## 6. CLI 集成规范

### 6.1 同步源 CLI

```python
"""CLI commands for {Source Name}."""
import typer
from rich.console import Console
from rich.table import Table

from web_scraper.core.storage import JSONStorage
from web_scraper.core.exceptions import NotLoggedInError
from .config import SOURCE_NAME
from .scrapers import SearchScraper, ArticleScraper

app = typer.Typer(
    name=SOURCE_NAME,
    help="{Source Name} scraping commands.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def search(
    query: str = typer.Argument(..., help="搜索关键词"),
    max_results: int = typer.Option(10, "-n", "--max", help="最大结果数"),
    output: str = typer.Option(None, "-o", "--output", help="输出文件名"),
) -> None:
    """搜索文章。"""
    try:
        scraper = SearchScraper(headless=True)
        results = scraper.search(query, max_results)

        # 保存结果
        if results:
            storage = JSONStorage(source=SOURCE_NAME)
            filename = output or storage.generate_filename("search", query)
            storage.save([r.model_dump() for r in results], filename)

        # 显示结果
        _display_results(results)

    except NotLoggedInError as e:
        console.print(f"[red]错误：{e}[/red]")
        console.print(f"[yellow]请先运行 'scraper {SOURCE_NAME} login' 登录[/yellow]")
        raise typer.Exit(1)


@app.command()
def login(
    interactive: bool = typer.Option(False, "-i", "--interactive", help="交互式登录"),
) -> None:
    """登录到 {Source Name}。"""
    from .auth import login as do_login
    do_login(interactive=interactive)


def _display_results(results: list) -> None:
    """以表格形式显示结果。"""
    if not results:
        console.print("[yellow]未找到结果[/yellow]")
        return

    table = Table(title=f"搜索结果 ({len(results)} 条)")
    table.add_column("标题", style="cyan")
    table.add_column("URL", style="dim")

    for r in results:
        table.add_row(r.title[:50], r.url[:60])

    console.print(table)
```

### 6.2 异步源 CLI

```python
"""CLI commands for {Async Source Name}."""
import asyncio
import typer
from rich.console import Console

from web_scraper.core.browser import get_browser
from web_scraper.core.storage import JSONStorage
from .config import SOURCE_NAME
from .scrapers import ExploreScraper

app = typer.Typer(
    name=SOURCE_NAME,
    help="{Async Source Name} scraping commands.",
    no_args_is_help=True,
)
console = Console()


def run_async(coro):
    """在同步上下文中运行异步协程。"""
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(coro)


@app.command()
def explore(
    category: str = typer.Option("推荐", "-c", "--category", help="分类"),
    limit: int = typer.Option(20, "-l", "--limit", help="获取数量"),
) -> None:
    """探索内容。"""

    async def _explore():
        async with get_browser(SOURCE_NAME, headless=True) as browser:
            scraper = ExploreScraper(browser)
            return await scraper.scrape(category=category, limit=limit)

    result = run_async(_explore())

    # 保存和显示
    storage = JSONStorage(source=SOURCE_NAME)
    storage.save(result.model_dump(), f"explore_{category}.json")
    console.print(f"[green]获取了 {len(result.notes)} 条内容[/green]")


@app.command()
def login(
    method: str = typer.Option("qrcode", help="登录方式: qrcode/phone"),
) -> None:
    """登录。"""
    from .auth import login as do_login
    run_async(do_login(method=method))
```

### 6.3 CLI 命令规范

| 命令 | 用途 | 必需 |
|------|------|------|
| `login` | 认证登录 | 是（如需认证） |
| `status` | 检查登录状态 | 推荐 |
| `search` | 搜索功能 | 按需 |
| `fetch`/`get` | 获取单项详情 | 按需 |
| `list` | 列出分类/频道 | 按需 |

---

## 7. MCP 工具规范

### 7.1 工具定义

在 `web_scraper/mcp_server.py` 中添加工具：

```python
from web_scraper.sources.newsource.scrapers import SearchScraper
from web_scraper.sources.newsource.config import SOURCE_NAME


@mcp.tool()
def newsource_search(
    query: str,
    max_results: int = 10,
) -> list[dict]:
    """
    搜索 {Source Name} 内容。

    Args:
        query: 搜索关键词
        max_results: 最大结果数 (默认 10)

    Returns:
        搜索结果列表
    """
    try:
        scraper = SearchScraper(headless=True)
        results = scraper.search(query, max_results)
        return [r.model_dump() for r in results]
    except NotLoggedInError:
        return {
            "error": "Not logged in",
            "action": f"Run 'scraper {SOURCE_NAME} login' to authenticate"
        }
    except Exception as e:
        return {"error": str(e)}
```

### 7.2 异步工具包装

```python
def _run_async(coro):
    """在 MCP 同步上下文中运行异步代码。"""
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    def run_in_thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    with ThreadPoolExecutor() as executor:
        future = executor.submit(run_in_thread)
        return future.result()


@mcp.tool()
def newsource_explore(category: str = "推荐", limit: int = 20) -> dict:
    """探索内容。"""

    async def _explore():
        async with get_browser(SOURCE_NAME, headless=True) as browser:
            scraper = ExploreScraper(browser)
            return await scraper.scrape(category=category, limit=limit)

    try:
        result = _run_async(_explore())
        return result.model_dump()
    except Exception as e:
        return {"error": str(e)}
```

### 7.3 MCP 工具命名规范

| 格式 | 示例 |
|------|------|
| `{source}_{action}` | `reuters_search`, `xhs_explore` |
| `{source}_{action}_{target}` | `reuters_fetch_article`, `xhs_fetch_note` |

---

## 8. 配置与选择器规范

### 8.1 配置文件结构 (`config.py`)

```python
"""Configuration for {Source Name} scraper."""
from dataclasses import dataclass
from typing import Dict

# 源标识
SOURCE_NAME = "newsource"
BASE_URL = "https://www.example.com"

# URL 模板
SEARCH_URL = f"{BASE_URL}/search"
LOGIN_URL = f"{BASE_URL}/login"


# 分类/频道映射
CATEGORIES: Dict[str, str] = {
    "推荐": "recommend",
    "热门": "hot",
    "最新": "latest",
}


# CSS 选择器（集中管理）
class Selectors:
    """CSS selectors for {Source Name}."""

    # 登录相关
    LOGIN_FORM = "form.login-form"
    EMAIL_INPUT = "input[name='email']"
    PASSWORD_INPUT = "input[name='password']"
    SUBMIT_BUTTON = "button[type='submit']"

    # 搜索相关
    SEARCH_RESULT_ITEM = ".search-result-item"
    SEARCH_RESULT_TITLE = ".result-title"
    SEARCH_RESULT_LINK = "a.result-link"

    # 详情页相关
    ARTICLE_TITLE = "h1.article-title"
    ARTICLE_CONTENT = ".article-content"
    ARTICLE_AUTHOR = ".author-name"
    ARTICLE_DATE = "time.publish-date"

    # 状态检测
    LOGIN_MODAL = ".login-modal"
    RATE_LIMIT_WARNING = ".rate-limit"
    CAPTCHA_CONTAINER = ".captcha"


# 超时配置
@dataclass
class Timeouts:
    """Timeout configurations in milliseconds."""
    DEFAULT = 30000
    NAVIGATION = 60000
    ELEMENT = 10000
    CAPTCHA = 120000  # 验证码等待时间


# 爬虫配置
@dataclass
class ScraperConfig:
    """Scraper behavior configuration."""
    max_scroll_attempts: int = 50
    scroll_delay: float = 1.5
    max_retries: int = 3
    retry_delay: float = 5.0
```

### 8.2 选择器最佳实践

| 优先级 | 选择器类型 | 示例 | 说明 |
|--------|-----------|------|------|
| 1 | data-testid | `[data-testid="title"]` | 最稳定 |
| 2 | 语义化类名 | `.article-title` | 较稳定 |
| 3 | 属性选择器 | `input[name="email"]` | 功能性 |
| 4 | 组合选择器 | `article h1` | 结构依赖 |
| 5 | 通用类名 | `.css-1234` | 不推荐，易变 |

---

## 9. 错误处理规范

### 9.1 标准异常使用

```python
from web_scraper.core.exceptions import (
    ScraperError,           # 基类
    NotLoggedInError,       # 未登录
    SessionExpiredError,    # 会话过期
    RateLimitedError,       # 速率限制
    CaptchaError,           # 验证码
    ContentNotFoundError,   # 内容不存在
    PaywallError,           # 付费墙
    AuthenticationError,    # 认证失败
)


class SearchScraper(BaseScraper):
    def scrape(self, query: str) -> List[SearchResult]:
        with self.get_page() as page:
            page.goto(self.SEARCH_URL)

            # 检测各种异常状态
            if self._is_login_required(page):
                raise NotLoggedInError("需要登录才能搜索")

            if self._is_rate_limited(page):
                raise RateLimitedError("请求过于频繁，请稍后再试")

            if self._has_captcha(page):
                raise CaptchaError("需要完成验证码验证")

            if self._is_404(page):
                raise ContentNotFoundError(f"未找到 '{query}' 的搜索结果")

            # 正常处理...
```

### 9.2 CLI 错误处理

```python
@app.command()
def search(query: str) -> None:
    try:
        scraper = SearchScraper()
        results = scraper.search(query)
        _display_results(results)

    except NotLoggedInError as e:
        console.print(f"[red]{e}[/red]")
        console.print(f"[yellow]请运行 'scraper {SOURCE_NAME} login' 登录[/yellow]")
        raise typer.Exit(1)

    except RateLimitedError as e:
        console.print(f"[yellow]速率限制：{e}[/yellow]")
        console.print("[dim]请等待几分钟后重试[/dim]")
        raise typer.Exit(2)

    except CaptchaError as e:
        console.print(f"[yellow]需要验证：{e}[/yellow]")
        console.print(f"[dim]请运行 'scraper {SOURCE_NAME} login -i' 手动验证[/dim]")
        raise typer.Exit(3)

    except ScraperError as e:
        console.print(f"[red]爬虫错误：{e}[/red]")
        raise typer.Exit(1)
```

### 9.3 MCP 错误处理

MCP 工具**不应抛出异常**，而是返回错误字典：

```python
@mcp.tool()
def newsource_search(query: str) -> list[dict] | dict:
    try:
        # 正常逻辑
        return [r.model_dump() for r in results]
    except NotLoggedInError:
        return {
            "error": "Not logged in",
            "action": f"Run 'scraper {SOURCE_NAME} login' to authenticate"
        }
    except RateLimitedError:
        return {
            "error": "Rate limited",
            "action": "Wait a few minutes and try again"
        }
    except Exception as e:
        return {"error": str(e)}
```

---

## 10. 测试规范

### 10.1 测试目录结构

```
tests/
├── conftest.py                  # pytest fixtures
├── sources/
│   ├── test_newsource/
│   │   ├── __init__.py
│   │   ├── test_scrapers.py     # 爬虫单元测试
│   │   ├── test_models.py       # 模型测试
│   │   └── test_cli.py          # CLI 集成测试
```

### 10.2 测试示例

```python
# tests/sources/test_newsource/test_scrapers.py
import pytest
from web_scraper.sources.newsource.scrapers import SearchScraper
from web_scraper.sources.newsource.models import SearchResult


class TestSearchScraper:
    """SearchScraper 测试。"""

    @pytest.fixture
    def scraper(self):
        return SearchScraper(headless=True)

    def test_search_returns_results(self, scraper):
        """测试搜索返回结果。"""
        results = scraper.search("test", max_results=5)

        assert isinstance(results, list)
        assert len(results) <= 5
        assert all(isinstance(r, SearchResult) for r in results)

    def test_search_result_has_required_fields(self, scraper):
        """测试结果包含必需字段。"""
        results = scraper.search("test", max_results=1)

        if results:
            result = results[0]
            assert result.id
            assert result.title
            assert result.url.startswith("http")


# tests/sources/test_newsource/test_models.py
import pytest
from web_scraper.sources.newsource.models import Article, Author


class TestArticleModel:
    """Article 模型测试。"""

    def test_model_serialization(self):
        """测试模型序列化。"""
        article = Article(
            id="123",
            title="Test Article",
            content="Content here",
            author=Author(user_id="1", nickname="Test"),
            url="https://example.com/123",
        )

        data = article.model_dump()

        assert data["id"] == "123"
        assert data["author"]["nickname"] == "Test"

    def test_model_json_mode(self):
        """测试 JSON 模式序列化。"""
        article = Article(...)

        json_data = article.model_dump(mode="json")
        # datetime 应被转换为 ISO 字符串
        assert isinstance(json_data.get("published_at"), (str, type(None)))
```

---

## 11. 代码模板

### 11.1 完整的新源模板

以下是添加新源的完整模板文件：

**`sources/newsource/__init__.py`**

```python
"""NewSource scraper source."""
from .. import register_source, SourceConfig
from .cli import app as cli_app

register_source(SourceConfig(
    name="newsource",
    display_name="New Source",
    cli_app=cli_app,
    data_dir_name="newsource",
    is_async=False,
))

__all__ = ["cli_app"]
```

**`sources/newsource/config.py`**

```python
"""Configuration for NewSource scraper."""
from dataclasses import dataclass
from typing import Dict

SOURCE_NAME = "newsource"
BASE_URL = "https://www.example.com"

CATEGORIES: Dict[str, str] = {
    "all": "all",
    "news": "news",
}

class Selectors:
    SEARCH_ITEM = ".search-item"
    SEARCH_TITLE = ".item-title"
    SEARCH_LINK = "a.item-link"
    ARTICLE_TITLE = "h1.title"
    ARTICLE_CONTENT = ".content"

@dataclass
class Timeouts:
    DEFAULT = 30000
    NAVIGATION = 60000
```

**`sources/newsource/models.py`**

```python
"""Data models for NewSource."""
from typing import List, Optional
from pydantic import BaseModel, Field


class SearchResult(BaseModel):
    id: str = Field(description="结果 ID")
    title: str = Field(description="标题")
    url: str = Field(description="链接")
    summary: Optional[str] = Field(default=None, description="摘要")


class Article(BaseModel):
    id: str = Field(description="文章 ID")
    title: str = Field(description="标题")
    content: str = Field(description="正文")
    url: str = Field(description="链接")
```

**`sources/newsource/scrapers/__init__.py`**

```python
"""Scrapers for NewSource."""
from .search import SearchScraper

__all__ = ["SearchScraper"]
```

**`sources/newsource/scrapers/search.py`**

```python
"""Search scraper for NewSource."""
from typing import List
from web_scraper.core.base import BaseScraper
from ..config import SOURCE_NAME, BASE_URL, Selectors
from ..models import SearchResult


class SearchScraper(BaseScraper):
    SOURCE_NAME = SOURCE_NAME
    BASE_URL = BASE_URL

    def scrape(self, query: str, max_results: int = 10) -> List[SearchResult]:
        with self.get_page() as page:
            page.goto(f"{self.BASE_URL}/search?q={query}")
            self.wait_for_elements(page, Selectors.SEARCH_ITEM)

            results = []
            items = page.query_selector_all(Selectors.SEARCH_ITEM)

            for item in items[:max_results]:
                result = SearchResult(
                    id=self.safe_get_attribute(item, "a", "data-id") or "",
                    title=self.safe_get_text(item, Selectors.SEARCH_TITLE) or "",
                    url=self.normalize_url(
                        self.safe_get_attribute(item, Selectors.SEARCH_LINK, "href") or ""
                    ),
                )
                results.append(result)

            return results
```

**`sources/newsource/cli.py`**

```python
"""CLI commands for NewSource."""
import typer
from rich.console import Console
from rich.table import Table

from web_scraper.core.storage import JSONStorage
from web_scraper.core.exceptions import NotLoggedInError
from .config import SOURCE_NAME
from .scrapers import SearchScraper

app = typer.Typer(name=SOURCE_NAME, help="NewSource commands.", no_args_is_help=True)
console = Console()


@app.command()
def search(
    query: str = typer.Argument(..., help="搜索关键词"),
    max_results: int = typer.Option(10, "-n", "--max", help="最大结果数"),
) -> None:
    """搜索内容。"""
    try:
        scraper = SearchScraper(headless=True)
        results = scraper.scrape(query, max_results)

        if results:
            storage = JSONStorage(source=SOURCE_NAME)
            storage.save([r.model_dump() for r in results], f"search_{query}.json")

        table = Table(title=f"搜索结果 ({len(results)})")
        table.add_column("标题")
        table.add_column("URL")

        for r in results:
            table.add_row(r.title[:40], r.url[:50])

        console.print(table)

    except NotLoggedInError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
```

---

## 检查清单

添加新源时，请确保完成以下检查：

### 必需项

- [ ] 创建 `sources/{name}/` 目录结构
- [ ] 实现 `__init__.py` 并调用 `register_source()`
- [ ] 在 `sources/__init__.py` 的 `_load_sources()` 中添加导入
- [ ] 定义 `config.py`（SOURCE_NAME, BASE_URL, Selectors）
- [ ] 定义 `models.py`（Pydantic 数据模型）
- [ ] 实现至少一个爬虫类，继承 `BaseScraper` 或 `AsyncBaseScraper`
- [ ] 实现 `cli.py` 并导出 `app`
- [ ] 所有爬虫类实现 `scrape()` 方法

### 推荐项

- [ ] 添加 `login` 命令（如需认证）
- [ ] 添加 `status` 命令
- [ ] 在 `mcp_server.py` 中添加 MCP 工具
- [ ] 编写单元测试
- [ ] 添加 CLI 帮助文本和参数描述
- [ ] 处理所有标准异常类型

### 代码质量

- [ ] 使用类型注解
- [ ] 使用 `Field(description=...)` 描述模型字段
- [ ] 集中管理 CSS 选择器
- [ ] 遵循命名规范
- [ ] 添加 docstring

---

## 参考资料

- [Playwright Python 文档](https://playwright.dev/python/)
- [Pydantic V2 文档](https://docs.pydantic.dev/latest/)
- [Typer 文档](https://typer.tiangolo.com/)
- [FastMCP 文档](https://github.com/jlowin/fastmcp)
