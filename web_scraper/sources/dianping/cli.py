"""CLI commands for Dianping source."""
import json
import re
import shutil
from pathlib import Path
from typing import Optional

import typer
from rich.progress import Progress, SpinnerColumn, TextColumn

from ...core.display import ColumnDef, console, display_detail, display_saved, display_search_results
from ...core.storage import JSONStorage
from .config import SOURCE_NAME, DEFAULT_CITY_ID, DEFAULT_PAGE_SIZE
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

    dest = get_cookies_path()
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
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
def status() -> None:
    """Check whether imported cookies are still valid."""
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
        console.print(f"[green]✓ {msg}[/green]")
    else:
        console.print(f"[red]✗ {msg}[/red]")
        raise typer.Exit(1)


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
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Save JSON to file"),
) -> None:
    """Search Dianping shop results by parsing SSR HTML."""
    _require_cookies()

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
            results = scraper.search(
                query=query,
                city_id=city_id,
                channel=channel,
                page=page,
                limit=limit,
            )
        except Exception as e:
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
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Save JSON to file"),
) -> None:
    """Fetch a Dianping shop detail page."""
    _require_cookies()

    try:
        scraper = ShopScraper()
        detail = scraper.fetch(target)
    except Exception as e:
        console.print(f"[red]抓取商户失败：{e}[/red]")
        raise typer.Exit(1)

    deal_lines = [
        f"- {deal.title} | {deal.price or '-'} / {deal.value or '-'} | {deal.discount or '-'}"
        for deal in detail.deals[:8]
    ]
    content = "\n".join(deal_lines)

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
            "缓存接口数": len(detail.cache_keys),
        },
        content=content,
        title="商户详情",
        content_title="团购/套餐",
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
