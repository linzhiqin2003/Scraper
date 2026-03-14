"""CLI commands for Aigei GIF source."""
import re
from pathlib import Path
from typing import Optional

import typer
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from ...core.display import ColumnDef, console, display_options, display_saved, display_search_results
from ...core.storage import JSONStorage
from .config import SOURCE_NAME, RESOURCE_TYPES
from .scrapers import SearchScraper

app = typer.Typer(
    name=SOURCE_NAME,
    help="爱给网 GIF 素材搜索与下载。",
    no_args_is_help=True,
)


def _safe_filename(text: str) -> str:
    slug = re.sub(r'[<>:"/\\|?*\s]+', "_", text)
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug[:80] or "untitled"


# =============================================================================
# Status
# =============================================================================

@app.command()
def status() -> None:
    """Check Aigei connection status."""
    import requests
    try:
        resp = requests.get("https://www.aigei.com", timeout=10)
        if resp.status_code == 200:
            console.print("[green]✓[/green] 爱给网连接正常")
        else:
            console.print(f"[yellow]⚠[/yellow] HTTP {resp.status_code}")
    except Exception as e:
        console.print(f"[red]✗[/red] 连接失败: {e}")


# =============================================================================
# Options
# =============================================================================

@app.command()
def options() -> None:
    """Show available search options."""
    display_options(
        items=[
            {"option": "资源类型 (--type)", "values": ", ".join(RESOURCE_TYPES.keys())},
            {"option": "每页数量", "values": "~40 (由网站决定)"},
            {"option": "下载", "values": "--download 启用 GIF 文件下载"},
        ],
        columns=[
            ColumnDef("Option", "option", style="cyan"),
            ColumnDef("Values", "values"),
        ],
        title="Aigei Search Options",
    )


# =============================================================================
# Search
# =============================================================================

@app.command()
def search(
    keyword: list[str] = typer.Argument(..., help="搜索关键词，支持多个"),
    pages: Optional[int] = typer.Option(None, "--pages", "-p", help="每个关键词最多爬取页数"),
    all_pages: bool = typer.Option(False, "--all", help="爬取所有页"),
    limit: int = typer.Option(0, "--limit", "-n", help="每个关键词最多结果数 (0=不限)"),
    download: bool = typer.Option(False, "--download", help="下载 GIF 文件"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="输出文件路径"),
    save: bool = typer.Option(False, "--save", help="Save results"),
) -> None:
    """搜索爱给网 GIF 素材。

    支持多关键词批量搜索，默认爬取 2 页。

    Examples:
      scraper aigei search 猫 -p 5
      scraper aigei search 猫 狗 兔子 --all --download
      scraper aigei search cat --pages 3
    """
    max_pages = None if all_pages else (pages or 2)
    scraper = SearchScraper()
    storage = JSONStorage(source=SOURCE_NAME)

    try:
        _search_keywords(scraper, storage, keyword, max_pages, limit, download, output, save)
    finally:
        scraper.close()


def _search_keywords(
    scraper: SearchScraper,
    storage: JSONStorage,
    keyword: list[str],
    max_pages: Optional[int],
    limit: int,
    download: bool,
    output: Optional[str],
    save: bool,
) -> None:
    for kw in keyword:
        console.print(f"\n[bold]搜索关键词: {kw}[/bold] (最多 {max_pages or '全部'} 页)")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task(f"搜索 '{kw}'...", total=None)
            try:
                result = scraper.search(kw, max_pages=max_pages)
            except Exception as e:
                console.print(f"[red]Error:[/red] {e}")
                continue

        items = result.items
        if limit and len(items) > limit:
            items = items[:limit]

        if not items:
            console.print("[yellow]未找到结果[/yellow]")
            continue

        console.print(
            f"找到 [bold]{len(items)}[/bold] 个资源 "
            f"([green]免费: {sum(1 for it in items if not it.is_vip)}[/green], "
            f"[yellow]VIP: {sum(1 for it in items if it.is_vip)}[/yellow])"
        )

        # Display results table
        rows = [
            {
                "title": it.title,
                "vip": "[yellow]VIP[/yellow]" if it.is_vip else "[green]免费[/green]",
                "url": it.detail_url,
            }
            for it in items[:20]  # Show first 20 in table
        ]
        display_search_results(
            results=rows,
            columns=[
                ColumnDef("Title", "title", style="bold", max_width=40),
                ColumnDef("Type", "vip", width=6),
                ColumnDef("URL", "url", style="dim", max_width=50),
            ],
            title=f"搜索: {kw}",
            summary=f"共 {len(items)} 个结果" + (f" (显示前 20)" if len(items) > 20 else ""),
        )

        # Save
        if save:
            if output:
                import json
                data = [it.model_dump(mode="json") for it in items]
                with open(output, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                display_saved(output)
            else:
                slug = _safe_filename(kw)
                filename = storage.generate_filename("search", slug)
                storage.save(
                    [it.model_dump(mode="json") for it in items],
                    filename,
                    description=f"'{kw}' results",
                )

        # Download
        if download:
            free_items = [it for it in items if not it.is_vip]
            if not free_items:
                console.print("[yellow]没有免费资源可下载[/yellow]")
                continue

            download_dir = storage.create_folder(f"downloads/{_safe_filename(kw)}")
            console.print(f"\n下载 {len(free_items)} 个免费 GIF → {download_dir}")

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=console,
            ) as progress:
                task = progress.add_task("下载中...", total=len(free_items))
                success, fail = 0, 0
                for it in free_items:
                    ok, _ = scraper.download([it], download_dir)
                    success += ok
                    fail += (1 - ok)
                    progress.advance(task)

            console.print(
                f"下载完成: [green]{success}[/green] 成功, "
                f"[red]{fail}[/red] 失败"
            )


# =============================================================================
# Fetch (detail page)
# =============================================================================

@app.command()
def fetch(
    url: str = typer.Argument(..., help="爱给网资源详情页 URL"),
) -> None:
    """获取单个资源详情（暂仅展示 URL）。"""
    console.print(f"[dim]Detail page:[/dim] {url}")
    console.print("[yellow]详情页抓取功能待实现[/yellow]")
