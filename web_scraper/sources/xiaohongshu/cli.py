"""CLI interface for Xiaohongshu scraper."""

import asyncio
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from ...core.browser import get_browser
from ...core.storage import JSONStorage
from .auth import AuthManager
from .config import SOURCE_NAME, CATEGORY_CHANNELS, SEARCH_TYPES, COOKIE_PATH
from .scrapers import ExploreScraper, SearchScraper, NoteScraper

app = typer.Typer(
    name="xhs",
    help="Xiaohongshu (Little Red Book) scraper",
    no_args_is_help=True,
)
console = Console()


def run_async(coro):
    """Run async function in sync context."""
    return asyncio.get_event_loop().run_until_complete(coro)


@app.command()
def login(
    qrcode: bool = typer.Option(False, "--qrcode", "-q", help="Use QR code login"),
    phone: Optional[str] = typer.Option(None, "--phone", "-p", help="Phone number for SMS login"),
) -> None:
    """Login to Xiaohongshu."""
    async def _login():
        async with get_browser(SOURCE_NAME, headless=False) as browser:
            auth = AuthManager(browser)

            if qrcode:
                success = await auth.login_with_qrcode()
            elif phone:
                success = await auth.login_with_phone(phone)
            else:
                console.print("[yellow]Please specify login method:[/yellow]")
                console.print("  --qrcode, -q  QR code login (recommended)")
                console.print("  --phone, -p   Phone number login")
                return

            if success:
                console.print("[green]Login successful![/green]")
            else:
                console.print("[red]Login failed.[/red]")
                raise typer.Exit(1)

    run_async(_login())


@app.command()
def auth() -> None:
    """Check login status."""
    async def _check():
        if not COOKIE_PATH.exists():
            console.print("[yellow]Not logged in. No cookies found.[/yellow]")
            console.print("[dim]Run 'scraper xhs login --qrcode' to login.[/dim]")
            raise typer.Exit(1)

        async with get_browser(SOURCE_NAME, headless=True) as browser:
            auth_manager = AuthManager(browser)
            is_logged_in = await auth_manager.check_login_status()

            if is_logged_in:
                console.print("[green]Session is valid.[/green]")
            else:
                console.print("[yellow]Session expired. Please login again.[/yellow]")
                raise typer.Exit(1)

    run_async(_check())


@app.command()
def logout() -> None:
    """Clear login session."""
    if COOKIE_PATH.exists():
        COOKIE_PATH.unlink()
        console.print("[green]Session cleared successfully.[/green]")
    else:
        console.print("[dim]No session file found.[/dim]")


@app.command()
def explore(
    category: str = typer.Option("推荐", "--category", "-c", help="Category to explore"),
    limit: int = typer.Option(20, "--limit", "-l", help="Maximum number of notes"),
    headless: bool = typer.Option(True, "--headless/--no-headless", help="Run browser in headless mode"),
    output: str = typer.Option("./output", "--output", "-o", help="Save results to directory"),
    no_save: bool = typer.Option(False, "--no-save", help="Don't save to files"),
) -> None:
    """Explore notes from Xiaohongshu homepage."""
    if category not in CATEGORY_CHANNELS:
        console.print(f"[red]Invalid category: {category}[/red]")
        console.print(f"[dim]Valid categories: {', '.join(CATEGORY_CHANNELS.keys())}[/dim]")
        raise typer.Exit(1)

    async def _explore():
        async with get_browser(SOURCE_NAME, headless=headless) as browser:
            scraper = ExploreScraper(browser)
            result = await scraper.scrape(category=category, limit=limit)

            if not result.notes:
                console.print(f"[yellow]No notes found in {category}[/yellow]")
                return

            table = Table(title=f"Explore: {category}", show_lines=True)
            table.add_column("#", style="dim", width=3)
            table.add_column("Title", style="bold", max_width=40)
            table.add_column("Author", style="cyan", max_width=15)
            table.add_column("Likes", style="green", width=8)
            table.add_column("Note ID", style="dim", width=20)

            for i, note in enumerate(result.notes, 1):
                table.add_row(
                    str(i),
                    note.title[:40] + ("..." if len(note.title) > 40 else ""),
                    note.author.nickname[:15],
                    str(note.likes),
                    note.note_id,
                )

            console.print(table)
            console.print(f"\n[dim]Found {len(result.notes)} notes[/dim]")

            if not no_save:
                import os
                os.makedirs(output, exist_ok=True)
                storage = JSONStorage(SOURCE_NAME, output_dir=None)
                storage.output_dir.mkdir(parents=True, exist_ok=True)
                from datetime import datetime
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"explore_{category}_{timestamp}.json"
                storage.save(result.notes, filename, description="notes")

    run_async(_explore())


@app.command()
def search(
    keyword: str = typer.Argument(..., help="Search keyword"),
    search_type: str = typer.Option("all", "--type", "-t", help="Search type: all, video, image"),
    limit: int = typer.Option(20, "--limit", "-l", help="Maximum number of results"),
    headless: bool = typer.Option(True, "--headless/--no-headless", help="Run browser in headless mode"),
    output: str = typer.Option("./output", "--output", "-o", help="Save results to directory"),
    no_save: bool = typer.Option(False, "--no-save", help="Don't save to files"),
) -> None:
    """Search for notes on Xiaohongshu."""
    if search_type not in SEARCH_TYPES:
        console.print(f"[red]Invalid search type: {search_type}[/red]")
        console.print(f"[dim]Valid types: {', '.join(SEARCH_TYPES.keys())}[/dim]")
        raise typer.Exit(1)

    async def _search():
        async with get_browser(SOURCE_NAME, headless=headless) as browser:
            scraper = SearchScraper(browser)
            result = await scraper.scrape(keyword=keyword, search_type=search_type, limit=limit)

            if not result.notes:
                console.print(f"[yellow]No results found for '{keyword}'[/yellow]")
                return

            table = Table(title=f"Search: {keyword}", show_lines=True)
            table.add_column("#", style="dim", width=3)
            table.add_column("Title", style="bold", max_width=40)
            table.add_column("Author", style="cyan", max_width=15)
            table.add_column("Likes", style="green", width=8)
            table.add_column("Type", style="magenta", width=6)

            for i, note in enumerate(result.notes, 1):
                table.add_row(
                    str(i),
                    note.title[:40] + ("..." if len(note.title) > 40 else ""),
                    note.author.nickname[:15],
                    str(note.likes),
                    note.note_type,
                )

            console.print(table)
            console.print(f"\n[dim]Found {len(result.notes)} results[/dim]")

            if not no_save:
                import os
                import re
                os.makedirs(output, exist_ok=True)
                storage = JSONStorage(SOURCE_NAME, output_dir=None)
                storage.output_dir.mkdir(parents=True, exist_ok=True)
                from datetime import datetime
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_keyword = re.sub(r'[^\w\s-]', '', keyword)[:20].strip()
                safe_keyword = re.sub(r'[-\s]+', '-', safe_keyword)
                filename = f"search_{safe_keyword}_{timestamp}.json"
                storage.save(result.notes, filename, description="notes")

    run_async(_search())


@app.command()
def note(
    note_id: str = typer.Argument(..., help="Note ID to fetch"),
    token: Optional[str] = typer.Option(None, "--token", "-t", help="xsec_token for access"),
    headless: bool = typer.Option(False, "--headless/--no-headless", help="Run browser in headless mode"),
) -> None:
    """Fetch a specific note by ID."""
    async def _fetch():
        async with get_browser(SOURCE_NAME, headless=headless) as browser:
            scraper = NoteScraper(browser)
            result, _ = await scraper.scrape(note_id=note_id, xsec_token=token or "")

            if not result:
                console.print(f"[red]Failed to fetch note: {note_id}[/red]")
                raise typer.Exit(1)

            content = f"# {result.title}\n\n"
            content += f"**Author:** {result.author.nickname}\n"
            content += f"**Published:** {result.publish_time}\n"
            content += f"**Likes:** {result.likes} | **Comments:** {result.comments_count} | **Collects:** {result.collects}\n\n"
            if result.tags:
                content += f"**Tags:** {', '.join(result.tags)}\n\n"
            content += "---\n\n"
            content += result.content

            console.print(Panel(content, title=f"[bold]{result.title}[/]", border_style="blue"))

    run_async(_fetch())


@app.command()
def categories() -> None:
    """List available explore categories."""
    table = Table(title="Available Categories", show_lines=False)
    table.add_column("Category", style="cyan")
    table.add_column("Channel ID", style="dim")

    for category, channel_id in CATEGORY_CHANNELS.items():
        table.add_row(category, channel_id)

    console.print(table)
