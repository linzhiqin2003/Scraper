"""CLI commands for Dianping source."""
import json
import re
from pathlib import Path
from typing import Optional

import typer
from rich.progress import Progress, SpinnerColumn, TextColumn

from ...core.browser import get_state_path
from ...core.display import ColumnDef, console, display_detail, display_saved, display_search_results
from ...core.storage import JSONStorage
from .config import SOURCE_NAME, DEFAULT_CITY_ID, DEFAULT_PAGE_SIZE
from .auth import (
    LoginStatus as BrowserLoginStatus,
    check_saved_session,
    clear_session,
    interactive_login,
)
from .cookies import (
    get_cookies_path,
    load_cookies,
    validate_cookies,
    check_cookies_valid,
)
from .scrapers import HomeScraper, SearchScraper, ShopScraper, NoteScraper

app = typer.Typer(
    name=SOURCE_NAME,
    help="大众点评 Dianping 抓取命令。",
    no_args_is_help=True,
)


def _safe_filename(text: str) -> str:
    slug = re.sub(r'[<>:"/\\|?*\s]+', "_", text)
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug[:80] or "untitled"


def _save_payload(data: object, default_name: str, output: Optional[Path]) -> Path:
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        payload = data.model_dump(mode="json") if hasattr(data, "model_dump") else data
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return output

    storage = JSONStorage(source=SOURCE_NAME)
    return storage.save(data, default_name, description="result", silent=True)


def _require_cookies() -> None:
    path = get_cookies_path()
    if not path.exists():
        console.print("[yellow]未找到 cookies 文件[/yellow]")
        console.print(f"[dim]请运行：scraper {SOURCE_NAME} import-cookies <文件路径>[/dim]")
        raise typer.Exit(1)


@app.command("import-cookies")
def import_cookies(
    cookies_file: str = typer.Argument(..., help="Netscape 格式 cookies.txt 文件路径"),
) -> None:
    """Import cookies exported from the browser."""
    src = Path(cookies_file).expanduser()
    if not src.exists():
        console.print(f"[red]文件不存在：{src}[/red]")
        raise typer.Exit(1)

    from ...core.cookies import import_cookies as _import_cookies
    dest = _import_cookies(src, SOURCE_NAME)
    console.print(f"[green]✓ Cookies 已导入：{dest}[/green]")

    try:
        cookies = load_cookies(dest)
        if validate_cookies(cookies):
            console.print("[green]✓ 检测到点评登录相关 Cookie[/green]")
            console.print(f"[dim]运行 'scraper {SOURCE_NAME} status' 验证接口连通性[/dim]")
        else:
            console.print("[yellow]⚠ 未检测到典型登录 Cookie，仍可继续尝试 status 验证[/yellow]")
    except Exception as e:
        console.print(f"[yellow]⚠ Cookie 解析警告：{e}[/yellow]")


@app.command()
def login(
    timeout: int = typer.Option(300, "--timeout", "-t", help="等待手动验证完成的秒数"),
    headless: bool = typer.Option(False, "--headless/--no-headless", help="Run browser in headless mode"),
    query: str = typer.Option("瑞幸", "--query", help="用于建立搜索会话的测试关键词"),
) -> None:
    """Open a real browser, let the user pass verification, and save browser session."""
    console.print("[cyan]正在打开大众点评浏览器会话…[/]")
    console.print("[dim]如果出现验证页，请在浏览器里手动完成。搜索结果可见后会自动保存会话。[/]")

    result = interactive_login(
        headless=headless,
        timeout_seconds=timeout,
        query=query,
    )
    if result.status == BrowserLoginStatus.LOGGED_IN:
        console.print(f"[green]✓ {result.message}[/green]")
        console.print(f"[dim]当前页：{result.current_url}[/dim]")
        return

    console.print(f"[red]✗ {result.message}[/red]")
    if result.current_url:
        console.print(f"[dim]当前页：{result.current_url}[/dim]")
    raise typer.Exit(1)


@app.command()
def status() -> None:
    """Check cookie API status and saved browser search session."""
    _require_cookies()

    try:
        cookies = load_cookies()
    except Exception as e:
        console.print(f"[red]读取 cookies 失败：{e}[/red]")
        raise typer.Exit(1)

    if not validate_cookies(cookies):
        console.print("[yellow]⚠ 未检测到完整认证 Cookie，继续尝试在线校验[/yellow]")

    console.print("[dim]正在验证大众点评登录状态…[/dim]")
    ok, msg = check_cookies_valid(cookies)
    if ok:
        console.print(f"[green]✓ Cookie/API: {msg}[/green]")
    else:
        console.print(f"[red]✗ Cookie/API: {msg}[/red]")

    state_file = get_state_path(SOURCE_NAME)
    if state_file.exists():
        console.print("[dim]正在验证浏览器搜索会话…[/dim]")
        browser_status = check_saved_session(headless=True)
        if browser_status.status == BrowserLoginStatus.LOGGED_IN:
            console.print(f"[green]✓ Browser: {browser_status.message}[/green]")
        else:
            console.print(f"[yellow]⚠ Browser: {browser_status.message}[/yellow]")
    else:
        console.print(f"[yellow]⚠ Browser: 未找到已保存会话，运行 'scraper {SOURCE_NAME} login' 可建立搜索态[/yellow]")

    if ok:
        return
    raise typer.Exit(1)


@app.command()
def logout() -> None:
    """Clear saved browser session."""
    if clear_session():
        console.print("[green]✓ 已清除浏览器会话[/green]")
    else:
        console.print("[yellow]未找到浏览器会话，无需清除[/yellow]")


@app.command()
def browse(
    limit: int = typer.Option(DEFAULT_PAGE_SIZE, "--limit", "-n", help="Feed item count"),
    page_start: int = typer.Option(0, "--page-start", help="Feed offset"),
    city_id: int = typer.Option(DEFAULT_CITY_ID, "--city-id", help="City ID"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Save JSON to file"),
) -> None:
    """Fetch Dianping home navigation, profile, and feed."""
    _require_cookies()

    try:
        scraper = HomeScraper()
    except Exception as e:
        console.print(f"[red]初始化失败：{e}[/red]")
        raise typer.Exit(1)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("抓取首页 feed…", total=None)
        try:
            snapshot = scraper.browse(city_id=city_id, page_start=page_start, page_size=limit)
        except Exception as e:
            console.print(f"[red]请求失败：{e}[/red]")
            raise typer.Exit(1)

    if snapshot.profile:
        console.print(
            f"[bold]{snapshot.profile.nickname}[/bold] "
            f"[dim](Lv.{snapshot.profile.user_level or '-'} "
            f"点评 {snapshot.profile.review_count or 0} / 粉丝 {snapshot.profile.fans_count or 0})[/dim]"
        )

    if snapshot.navigation:
        nav_preview = "、".join(item.title for item in snapshot.navigation[:8])
        console.print(f"[dim]首页导航：{nav_preview}[/dim]\n")

    rows = [
        {
            "title": item.title,
            "author": item.author_name,
            "stats": f"赞 {item.like_count or 0} / 评 {item.comment_count or 0}",
            "url": item.url,
        }
        for item in snapshot.feed.items
    ]
    display_search_results(
        results=rows,
        columns=[
            ColumnDef("Title", "title", style="bold", max_width=36),
            ColumnDef("Author", "author", style="cyan", width=14),
            ColumnDef("Stats", "stats", style="yellow", width=16),
            ColumnDef("URL", "url", style="dim", max_width=56),
        ],
        title="大众点评首页 Feed",
        summary=f"共 {len(snapshot.feed.items)} 条，offset={snapshot.feed.page_start}",
    )

    if output:
        path = _save_payload(snapshot, "home_snapshot.json", output)
        display_saved(path)


@app.command()
def search(
    query: str = typer.Argument(..., help="搜索关键词"),
    page: int = typer.Option(1, "--page", "-p", help="结果页码，从 1 开始"),
    limit: int = typer.Option(10, "--limit", "-n", help="最大结果数"),
    city_id: int = typer.Option(DEFAULT_CITY_ID, "--city-id", help="City ID"),
    channel: int = typer.Option(0, "--channel", help="频道 ID，0 为不限，10 为美食"),
    browser: bool = typer.Option(False, "--browser", help="强制使用浏览器会话搜索"),
    manual: bool = typer.Option(False, "--manual", help="搜索前允许人工处理验证页，需要 --no-headless"),
    headless: bool = typer.Option(True, "--headless/--no-headless", help="浏览器模式是否无头"),
    timeout: int = typer.Option(120, "--timeout", help="浏览器模式等待结果页的秒数"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Save JSON to file"),
) -> None:
    """Search Dianping shop results by parsing SSR HTML, with browser-session fallback."""
    _require_cookies()
    if manual and headless:
        console.print("[red]--manual 需要配合 --no-headless 使用[/red]")
        raise typer.Exit(1)
    if browser and not manual and not get_state_path(SOURCE_NAME).exists():
        console.print(f"[red]未找到浏览器搜索会话，请先运行 'scraper {SOURCE_NAME} login'[/red]")
        raise typer.Exit(1)

    try:
        scraper = SearchScraper()
    except Exception as e:
        console.print(f"[red]初始化失败：{e}[/red]")
        raise typer.Exit(1)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task(f"搜索“{query}”…", total=None)
        try:
            if browser:
                if manual:
                    console.print("[dim]浏览器已打开后，如遇验证页请手动完成。结果页出现后会自动继续。[/dim]")
                results = scraper.search_with_browser(
                    query=query,
                    city_id=city_id,
                    channel=channel,
                    page=page,
                    limit=limit,
                    headless=headless,
                    timeout_seconds=timeout,
                )
            else:
                results = scraper.search(
                    query=query,
                    city_id=city_id,
                    channel=channel,
                    page=page,
                    limit=limit,
                )
        except Exception as e:
            if "验证页" in str(e):
                can_fallback = manual or get_state_path(SOURCE_NAME).exists()
                if can_fallback:
                    console.print("[yellow]HTTP 搜索触发验证，正在切换到浏览器会话模式…[/yellow]")
                    if manual:
                        console.print("[dim]如浏览器停在验证页，请手动完成后等待结果页出现。[/dim]")
                    try:
                        results = scraper.search_with_browser(
                            query=query,
                            city_id=city_id,
                            channel=channel,
                            page=page,
                            limit=limit,
                            headless=headless,
                            timeout_seconds=timeout,
                        )
                    except Exception as browser_exc:
                        console.print(f"[red]浏览器搜索失败：{browser_exc}[/red]")
                        raise typer.Exit(1)
                else:
                    console.print(f"[red]搜索失败：{e}[/red]")
                    console.print(f"[dim]建议先运行 'scraper {SOURCE_NAME} login' 建立浏览器搜索会话[/dim]")
                    raise typer.Exit(1)
            else:
                console.print(f"[red]搜索失败：{e}[/red]")
                raise typer.Exit(1)

    if not results:
        console.print("[yellow]未找到结果[/yellow]")
        return

    rows = [
        {
            "title": item.title,
            "reviews": item.review_count or 0,
            "price": item.avg_price_text or "-",
            "tags": " / ".join(x for x in [item.category, item.region] if x),
            "url": item.url,
        }
        for item in results
    ]
    display_search_results(
        results=rows,
        columns=[
            ColumnDef("Title", "title", style="bold", max_width=30),
            ColumnDef("Reviews", "reviews", style="yellow", width=8),
            ColumnDef("Price", "price", style="yellow", width=10),
            ColumnDef("Tags", "tags", style="magenta", max_width=24),
            ColumnDef("URL", "url", style="dim", max_width=48),
        ],
        title=f"大众点评搜索: {query}",
        summary=f"第 {page} 页，返回 {len(results)} 条",
    )

    if output:
        path = _save_payload(results, f"search_{_safe_filename(query)}.json", output)
        display_saved(path)


@app.command()
def shop(
    target: str = typer.Argument(..., help="商户 URL 或 shopUuid"),
    comment_limit: int = typer.Option(5, "--comment-limit", min=1, help="返回首屏评论条数"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Save JSON to file"),
) -> None:
    """Fetch a Dianping shop detail page."""
    _require_cookies()

    try:
        scraper = ShopScraper()
        detail = scraper.fetch(target, comment_limit=comment_limit)
    except Exception as e:
        console.print(f"[red]抓取商户失败：{e}[/red]")
        raise typer.Exit(1)

    detail_lines = [
        f"- {deal.title} | {deal.price or '-'} / {deal.value or '-'} | {deal.discount or '-'}"
        for deal in detail.deals[:8]
    ]
    if detail.recommended_dishes:
        detail_lines.append("")
        detail_lines.append("推荐菜:")
        for dish in detail.recommended_dishes[:8]:
            detail_lines.append(
                f"- {dish.name} | 推荐 {dish.recommend_count or 0}"
            )

    if detail.comments:
        detail_lines.append("")
        detail_lines.append(f"首屏评论({len(detail.comments)}/{detail.comment_count or len(detail.comments)}):")
        for comment in detail.comments:
            snippet = comment.content[:80] + ("..." if len(comment.content) > 80 else "")
            meta = " / ".join(
                x for x in [comment.publish_time, comment.rating_text, comment.price_text] if x
            )
            if meta:
                detail_lines.append(f"- {comment.author_name} | {meta}")
                detail_lines.append(f"  {snippet}")
            else:
                detail_lines.append(f"- {comment.author_name}: {snippet}")

    content = "\n".join(detail_lines)

    display_detail(
        meta={
            "名称": detail.name,
            "标题": detail.title_name,
            "评分": detail.score_text,
            "价格": detail.price_text,
            "分类": detail.category,
            "区域": detail.region,
            "地址": detail.address,
            "电话": ", ".join(detail.phone_numbers) if detail.phone_numbers else None,
            "坐标": f"{detail.lat}, {detail.lng}" if detail.lat and detail.lng else None,
            "评价数": detail.comment_count,
            "推荐菜": len(detail.recommended_dishes),
            "首屏评论": len(detail.comments),
            "缓存接口数": len(detail.cache_keys),
        },
        content=content,
        title="商户详情",
        content_title="套餐 / 推荐菜 / 首屏评论",
    )

    path = _save_payload(detail, f"shop_{detail.shop_uuid}.json", output)
    display_saved(path)


@app.command()
def note(
    target: str = typer.Argument(..., help="笔记 URL、ugcdetail URL，或 noteId_feedType"),
    rec_limit: int = typer.Option(3, "--rec-limit", help="推荐内容条数"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Save JSON to file"),
) -> None:
    """Fetch a Dianping note detail page."""
    _require_cookies()

    try:
        scraper = NoteScraper()
        detail = scraper.fetch(target, rec_limit=rec_limit)
    except Exception as e:
        console.print(f"[red]抓取笔记失败：{e}[/red]")
        raise typer.Exit(1)

    preview = detail.content or ""
    if len(preview) > 800:
        preview = preview[:800] + "..."

    display_detail(
        meta={
            "标题": detail.title,
            "作者": detail.author.nickname if detail.author else None,
            "发布时间": detail.published_at,
            "点赞": detail.like_count,
            "评论": detail.comment_count,
            "收藏": detail.collect_count,
            "话题": "、".join(detail.topics[:6]) if detail.topics else None,
            "图片数": len(detail.images),
            "推荐数": len(detail.recommendations),
        },
        content=preview,
        title="笔记详情",
        content_title="正文预览",
    )

    path = _save_payload(detail, f"note_{detail.note_id}_{detail.feed_type}.json", output)
    display_saved(path)


@app.command()
def fetch(
    target: str = typer.Argument(..., help="商户或笔记 URL"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Save JSON to file"),
) -> None:
    """Auto-detect whether the target is a shop or a note."""
    target_lower = target.lower()

    if "/note/" in target_lower or "/ugcdetail/" in target_lower or re.fullmatch(r"\d+_\d+", target):
        note(target=target, rec_limit=3, output=output)
        return

    if "/shop/" in target_lower or re.fullmatch(r"[A-Za-z0-9-]{8,}", target):
        shop(target=target, output=output)
        return

    console.print("[red]无法判断目标类型，请使用 shop 或 note 子命令[/red]")
    raise typer.Exit(1)
