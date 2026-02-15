"""CLI interface for Weibo scraper."""

import json
import re
from pathlib import Path
from typing import Optional

import typer
from rich.table import Table

from ...core.browser import get_state_path
from ...core.display import (
    ColumnDef,
    console,
    display_auth_status,
    display_detail,
    display_saved,
    display_search_results,
    format_stats,
    truncate,
)
from ...core.storage import JSONStorage
from .auth import AuthStatus, LoginStatus, interactive_login, check_saved_session, clear_session
from .models import WeiboDetailResponse, WeiboHotResponse, WeiboSearchResponse
from .scrapers import (
    DetailScraper,
    HotScraper,
    LoginRequiredError,
    RateLimitedError,
    SearchError,
    SearchScraper,
)
from .config import SOURCE_NAME

app = typer.Typer(
    name=SOURCE_NAME,
    help="Sina Weibo scraper",
    no_args_is_help=True,
)


def _require_login() -> None:
    """Check that saved session exists before running commands."""
    state_file = get_state_path(SOURCE_NAME)
    if state_file.exists():
        return
    console.print("[yellow]Not logged in.[/yellow]")
    console.print("[dim]Run 'scraper weibo login' to login first.[/dim]")
    raise typer.Exit(1)


def _safe_filename(text: str) -> str:
    """Convert free text into filesystem-safe slug."""
    slug = re.sub(r"[^\w\s-]", "", text)
    slug = re.sub(r"[\s-]+", "_", slug).strip("_")
    return slug[:50] or "query"


def _show_auth(auth: AuthStatus) -> None:
    extras: dict = {}
    if auth.checked_at:
        extras["Checked at"] = auth.checked_at.strftime("%Y-%m-%d %H:%M:%S")
    if auth.current_url:
        extras["URL"] = auth.current_url
    if auth.message:
        extras["Message"] = auth.message

    display_auth_status(
        source_name="Weibo",
        status=auth.status.value,
        extras=extras,
        state_file=get_state_path(SOURCE_NAME),
    )


def _show_search_results(response: WeiboSearchResponse) -> None:
    """Render search summary and top rows."""
    rows = []
    for item in response.results:
        rows.append({
            "user": item.user or "-",
            "time": item.posted_at or "-",
            "stats": format_stats(R=item.reposts or 0, C=item.comments or 0, L=item.likes or 0),
            "text": truncate(item.content, 120),
            "url": item.detail_url or "-",
        })

    display_search_results(
        results=rows,
        columns=[
            ColumnDef("User", "user", style="cyan", max_width=18),
            ColumnDef("Time", "time", style="green", max_width=18),
            ColumnDef("Stats", "stats", style="yellow", max_width=16),
            ColumnDef("Text", "text", max_width=64),
            ColumnDef("URL", "url", style="dim", max_width=52),
        ],
        title=f"Search Results",
        summary=(
            f"Found {len(response.results)} posts "
            f"(method={response.method}, pages={response.pages_fetched}/{response.pages_requested})"
        ),
    )


def _show_detail_result(response: WeiboDetailResponse) -> None:
    """Render detail summary, post text, and comments preview."""
    stats = format_stats(R=response.reposts_count or 0, C=response.comments_count or 0, L=response.attitudes_count or 0)

    meta = {
        "Method": f"[cyan]{response.method}[/]",
        "URL": response.current_url or "-",
        "MID": response.mid or "-",
        "Author": response.author or "-",
        "Created at": response.created_at or "-",
        "Region": response.region_name or "-",
        "Source": response.source or "-",
        "Stats": stats,
        "Images": str(len(response.images)),
    }
    if response.comments_included:
        meta["Comments"] = f"{len(response.comments)} (pages={response.comment_pages_fetched}/{response.comment_pages_requested})"
    else:
        meta["Comments"] = "not requested"

    # Build comment sub-table if available
    sub_tables = None
    if response.comments:
        comment_table = Table(show_header=True, header_style="bold magenta")
        comment_table.add_column("#", style="dim", width=4)
        comment_table.add_column("User", style="cyan", max_width=18)
        comment_table.add_column("Time", style="green", max_width=22)
        comment_table.add_column("Likes", style="yellow", width=8)
        comment_table.add_column("Text", max_width=84)

        for index, comment in enumerate(response.comments, 1):
            comment_table.add_row(
                str(index),
                comment.user or "-",
                comment.created_at or "-",
                str(comment.likes or 0),
                truncate(comment.text, 180),
            )
        sub_tables = [("Comments", comment_table)]

    display_detail(
        meta=meta,
        content=response.text or "",
        title="Weibo Detail",
        content_title="Post Text",
        sub_tables=sub_tables,
    )


def _show_hot_results(response: WeiboHotResponse) -> None:
    """Render hot-search summary and rows."""
    rows = []
    for item in response.items:
        rows.append({
            "rank": str(item.rank) if item.rank is not None else "-",
            "topic": item.topic or "-",
            "heat": f"{item.heat:,}" if item.heat is not None else "-",
            "label": item.label or "-",
            "url": item.search_url or "-",
        })

    display_search_results(
        results=rows,
        columns=[
            ColumnDef("Rank", "rank", style="yellow", width=6),
            ColumnDef("Topic", "topic", style="cyan", max_width=42),
            ColumnDef("Heat", "heat", style="green", width=12),
            ColumnDef("Label", "label", style="magenta", width=8),
            ColumnDef("URL", "url", style="dim", max_width=64),
        ],
        title="Hot Topics",
        summary=(
            f"Found {len(response.items)} hot topics "
            f"(method={response.method}, total={response.total_available})"
        ),
    )


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command()
def login(
    timeout: int = typer.Option(300, "--timeout", "-t", help="Login timeout in seconds"),
    headless: bool = typer.Option(False, "--headless/--no-headless", help="Run browser in headless mode"),
) -> None:
    """Open Weibo login page and save session after manual login."""
    console.print("[cyan]Opening browser for Weibo login...[/]")
    console.print(
        "[dim]Complete login (QR code, SMS, or account/password). "
        "Session will auto-save after successful redirect.[/]"
    )

    try:
        result = interactive_login(headless=headless, timeout_seconds=timeout)
        _show_auth(result)

        if result.status == LoginStatus.LOGGED_IN:
            raise typer.Exit(0)
        raise typer.Exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Login cancelled.[/]")
        raise typer.Exit(130)


@app.command()
def status() -> None:
    """Check saved Weibo login status."""
    try:
        with console.status("[cyan]Checking Weibo login status...[/]"):
            result = check_saved_session(headless=True)

        _show_auth(result)

        if result.status == LoginStatus.LOGGED_IN:
            raise typer.Exit(0)
        raise typer.Exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Status check cancelled.[/]")
        raise typer.Exit(130)


@app.command()
def search(
    query: str = typer.Argument(..., help="Search keyword"),
    pages: int = typer.Option(1, "--pages", "-p", min=1, help="Number of pages to fetch"),
    limit: Optional[int] = typer.Option(20, "--limit", "-n", min=1, help="Maximum number of results"),
    headless: bool = typer.Option(True, "--headless/--no-headless", help="Run fallback browser in headless mode"),
    no_fallback: bool = typer.Option(False, "--no-fallback", help="Disable Playwright fallback"),
    save: bool = typer.Option(True, "--save/--no-save", help="Save results to JSON"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output JSON file path"),
) -> None:
    """Search Weibo posts with HTTP-first strategy and Playwright fallback."""
    _require_login()
    scraper = SearchScraper(use_playwright_fallback=not no_fallback)

    try:
        with console.status(f"[cyan]Searching Weibo for '{query}'...[/]"):
            result = scraper.search(query=query, pages=pages, limit=limit, headless=headless)
    except LoginRequiredError as exc:
        console.print(f"[red]{exc}[/]")
        console.print("[dim]Run 'scraper weibo login' and retry.[/]")
        raise typer.Exit(1)
    except RateLimitedError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        raise typer.Exit(1)
    except SearchError as exc:
        console.print(f"[red]Search failed:[/red] {exc}")
        raise typer.Exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Search cancelled.[/]")
        raise typer.Exit(130)

    _show_search_results(result)

    output_path: Optional[Path] = None
    if output:
        output_path = output.expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2)
        )
    elif save:
        storage = JSONStorage(source=SOURCE_NAME)
        filename = storage.generate_filename("search", suffix=_safe_filename(query))
        output_path = storage.save(result, filename, description="posts", silent=True)

    if output_path:
        display_saved(output_path)


@app.command()
def hot(
    limit: Optional[int] = typer.Option(50, "--limit", "-n", min=1, help="Maximum number of hot topics"),
    headless: bool = typer.Option(True, "--headless/--no-headless", help="Run fallback browser in headless mode"),
    no_fallback: bool = typer.Option(False, "--no-fallback", help="Disable Playwright fallback"),
    save: bool = typer.Option(True, "--save/--no-save", help="Save results to JSON"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output JSON file path"),
) -> None:
    """Fetch Weibo hot-search topics."""
    _require_login()
    scraper = HotScraper(use_playwright_fallback=not no_fallback)

    try:
        with console.status("[cyan]Fetching Weibo hot-search topics...[/]"):
            result = scraper.scrape(limit=limit, headless=headless)
    except LoginRequiredError as exc:
        console.print(f"[red]{exc}[/]")
        console.print("[dim]Run 'scraper weibo login' and retry.[/]")
        raise typer.Exit(1)
    except RateLimitedError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        raise typer.Exit(1)
    except SearchError as exc:
        console.print(f"[red]Hot-search fetch failed:[/red] {exc}")
        raise typer.Exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Hot-search fetch cancelled.[/]")
        raise typer.Exit(130)

    _show_hot_results(result)

    output_path: Optional[Path] = None
    if output:
        output_path = output.expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2)
        )
    elif save:
        storage = JSONStorage(source=SOURCE_NAME)
        filename = storage.generate_filename("hot_search")
        output_path = storage.save(result, filename, description="hot topics", silent=True)

    if output_path:
        display_saved(output_path)


@app.command()
def fetch(
    url_or_mid: str = typer.Argument(..., help="Weibo detail URL or MID"),
    comments: bool = typer.Option(True, "--comments/--no-comments", help="Fetch comments"),
    comment_pages: int = typer.Option(1, "--comment-pages", min=1, help="Comment pages to fetch"),
    comment_count: int = typer.Option(20, "--comment-count", min=1, max=50, help="Comments per page"),
    headless: bool = typer.Option(True, "--headless/--no-headless", help="Run fallback browser in headless mode"),
    no_fallback: bool = typer.Option(False, "--no-fallback", help="Disable Playwright fallback"),
    save: bool = typer.Option(True, "--save/--no-save", help="Save result to JSON"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output JSON file path"),
) -> None:
    """Fetch a single Weibo post detail by URL or MID."""
    _require_login()
    scraper = DetailScraper(use_playwright_fallback=not no_fallback)

    try:
        with console.status(f"[cyan]Fetching Weibo detail for '{url_or_mid}'...[/]"):
            result = scraper.scrape(
                url_or_mid=url_or_mid,
                include_comments=comments,
                comment_pages=comment_pages,
                comment_count=comment_count,
                headless=headless,
            )
    except LoginRequiredError as exc:
        console.print(f"[red]{exc}[/]")
        console.print("[dim]Run 'scraper weibo login' and retry.[/]")
        raise typer.Exit(1)
    except RateLimitedError as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        raise typer.Exit(1)
    except SearchError as exc:
        console.print(f"[red]Detail fetch failed:[/red] {exc}")
        raise typer.Exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Detail fetch cancelled.[/]")
        raise typer.Exit(130)

    _show_detail_result(result)

    output_path: Optional[Path] = None
    if output:
        output_path = output.expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2)
        )
    elif save:
        storage = JSONStorage(source=SOURCE_NAME)
        suffix = _safe_filename(result.mblogid or result.mid or url_or_mid)
        filename = storage.generate_filename("detail", suffix=suffix)
        output_path = storage.save(result, filename, description="post detail", silent=True)

    if output_path:
        display_saved(output_path)


# Alias: `detail` → `fetch`
detail = app.command("detail", rich_help_panel="Aliases")(fetch)


@app.command()
def logout() -> None:
    """Clear saved Weibo session."""
    if clear_session():
        console.print("[green]Session cleared successfully.[/]")
    else:
        console.print("[dim]No session file found.[/]")
