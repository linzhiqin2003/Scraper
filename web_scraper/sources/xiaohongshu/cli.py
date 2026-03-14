"""CLI interface for Xiaohongshu scraper."""

import asyncio
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from urllib.parse import parse_qs, urlparse

import httpx
import typer
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table

from ...core.browser import get_browser
from ...core.cookies import parse_netscape_cookies, to_playwright
from ...core.display import (
    ColumnDef,
    console,
    display_options,
    display_search_results,
)
from ...core.storage import JSONStorage
from .auth import AuthManager
from .config import SOURCE_NAME, CATEGORY_CHANNELS, SEARCH_TYPES, SEARCH_SORT_OPTIONS, SEARCH_NOTE_TYPES, COOKIE_PATH, DATA_DIR
from .models import Note
from .scrapers import ExploreScraper, SearchScraper, NoteScraper
from .scrapers.api import XHSApiScraper

app = typer.Typer(
    name="xhs",
    help="Xiaohongshu (Little Red Book) scraper",
    no_args_is_help=True,
)


def run_async(coro):
    """Run async function in sync context."""
    return asyncio.get_event_loop().run_until_complete(coro)


def _require_login() -> None:
    """Check that cookies exist before running commands that need login."""
    if not COOKIE_PATH.exists():
        console.print("[yellow]Not logged in.[/yellow]")
        console.print("[dim]Run 'scraper xhs login --qrcode' to login first.[/dim]")
        raise typer.Exit(1)


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
def status() -> None:
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


# Alias: `auth` → `status`


@app.command()
def logout() -> None:
    """Clear login session."""
    if COOKIE_PATH.exists():
        COOKIE_PATH.unlink()
        console.print("[green]Session cleared successfully.[/green]")
    else:
        console.print("[dim]No session file found.[/dim]")


@app.command("import-cookies")
def import_cookies(
    cookies_file: Path = typer.Argument(..., help="Path to Netscape-format cookies.txt file"),
) -> None:
    """Import cookies from a browser-exported cookies.txt file.

    Use browser extensions like EditThisCookie or Cookie-Editor to export
    cookies in Netscape format, then import them here.
    """
    if not cookies_file.exists():
        console.print(f"[red]File not found: {cookies_file}[/red]")
        raise typer.Exit(1)

    try:
        parsed = parse_netscape_cookies(cookies_file)
    except Exception as e:
        console.print(f"[red]Failed to parse cookies file: {e}[/red]")
        raise typer.Exit(1)

    if not parsed:
        console.print("[red]No valid cookies found in the file.[/red]")
        raise typer.Exit(1)

    # Convert to Playwright format and save as cookies.json
    pw_cookies = to_playwright(parsed)
    COOKIE_PATH.parent.mkdir(parents=True, exist_ok=True)
    COOKIE_PATH.write_text(json.dumps(pw_cookies, ensure_ascii=False, indent=2))

    # Count XHS-specific cookies
    xhs_domains = [c for c in parsed if "xiaohongshu" in c.get("domain", "")]
    console.print(f"[green]Imported {len(pw_cookies)} cookies ({len(xhs_domains)} for xiaohongshu)[/green]")
    console.print(f"[dim]Saved to: {COOKIE_PATH}[/dim]")

    # Check for key cookies
    cookie_names = {c["name"] for c in parsed}
    key_cookies = ["web_session", "a1", "webId"]
    missing = [k for k in key_cookies if k not in cookie_names]
    if missing:
        console.print(f"[yellow]Warning: Missing key cookies: {', '.join(missing)}[/yellow]")
    else:
        console.print("[green]All key cookies present (web_session, a1, webId)[/green]")


@app.command()
def browse(
    category: str = typer.Option("推荐", "--category", "-c", help="Category to explore"),
    limit: int = typer.Option(20, "--limit", "-n", help="Maximum number of notes"),
    headless: bool = typer.Option(True, "--headless/--no-headless", help="Run browser in headless mode"),
    output: str = typer.Option("./output", "--output", "-o", help="Save results to directory"),
    save: bool = typer.Option(False, "--save", help="Save results"),
) -> None:
    """Browse notes from Xiaohongshu homepage by category."""
    _require_login()
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

            rows = []
            for note in result.notes:
                rows.append({
                    "title": note.title[:40] + ("..." if len(note.title) > 40 else ""),
                    "author": note.author.nickname[:15],
                    "likes": str(note.likes),
                    "note_id": note.note_id,
                })

            display_search_results(
                results=rows,
                columns=[
                    ColumnDef("Title", "title", style="bold", max_width=40),
                    ColumnDef("Author", "author", style="cyan", max_width=15),
                    ColumnDef("Likes", "likes", style="yellow", width=8),
                    ColumnDef("Note ID", "note_id", style="dim", width=20),
                ],
                title=f"Browse: {category}",
                summary=f"Found {len(result.notes)} notes",
            )

            if save:
                import os
                os.makedirs(output, exist_ok=True)
                storage = JSONStorage(SOURCE_NAME, output_dir=None)
                storage.output_dir.mkdir(parents=True, exist_ok=True)
                from datetime import datetime
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"explore_{category}_{timestamp}.json"
                storage.save(result.notes, filename, description="notes")

    run_async(_explore())


# Alias: `explore` → `browse`


@app.command()
def search(
    keyword: str = typer.Argument(..., help="Search keyword"),
    mode: str = typer.Option("api", "--mode", "-m", help="Search mode: api (fast) or dom (legacy)"),
    search_type: str = typer.Option("image", "--type", "-t", help="Note type filter: all, video, image"),
    sort: str = typer.Option("general", "--sort", "-s", help="Sort: general, time_descending, popularity_descending, comment_descending, collect_descending"),
    limit: int = typer.Option(20, "--limit", "-n", help="Maximum number of results"),
    headless: bool = typer.Option(True, "--headless/--no-headless", help="Run browser in headless mode"),
    output: str = typer.Option("./output", "--output", "-o", help="Save results to directory"),
    save: bool = typer.Option(False, "--save", help="Save results"),
) -> None:
    """Search for notes on Xiaohongshu.

    Examples:
        scraper xhs search "AI" -n 30
        scraper xhs search "美食" --sort popularity_descending
        scraper xhs search "旅行" --type video --sort time_descending
        scraper xhs search "穿搭" --mode dom -t image
    """
    _require_login()

    if mode not in ("api", "dom"):
        console.print("[red]Invalid mode. Choose: api, dom[/red]")
        raise typer.Exit(1)

    if mode == "dom" and search_type not in SEARCH_TYPES:
        console.print(f"[red]Invalid search type: {search_type}[/red]")
        console.print(f"[dim]Valid types: {', '.join(SEARCH_TYPES.keys())}[/dim]")
        raise typer.Exit(1)

    if mode == "api":
        if sort not in SEARCH_SORT_OPTIONS:
            console.print(f"[red]Invalid sort: {sort}[/red]")
            console.print(f"[dim]Valid sorts: {', '.join(SEARCH_SORT_OPTIONS.keys())}[/dim]")
            raise typer.Exit(1)
        if search_type not in SEARCH_NOTE_TYPES:
            console.print(f"[red]Invalid type for API mode: {search_type}[/red]")
            console.print(f"[dim]Valid types: {', '.join(SEARCH_NOTE_TYPES.keys())}[/dim]")
            raise typer.Exit(1)

    async def _search():
        async with get_browser(SOURCE_NAME, headless=headless) as browser:
            if mode == "api":
                scraper = XHSApiScraper(browser)
                result = await scraper.search_notes(
                    keyword=keyword,
                    limit=limit,
                    sort=sort,
                    note_type=SEARCH_NOTE_TYPES.get(search_type, 0),
                )
            else:
                scraper = SearchScraper(browser)
                result = await scraper.scrape(keyword=keyword, search_type=search_type, limit=limit)

            if not result.notes:
                console.print(f"[yellow]No results found for '{keyword}'[/yellow]")
                return

            rows = []
            for note in result.notes:
                url = f"https://www.xiaohongshu.com/explore/{note.note_id}"
                if note.xsec_token:
                    url += f"?xsec_token={note.xsec_token}"
                rows.append({
                    "title": note.title[:40] + ("..." if len(note.title) > 40 else ""),
                    "author": note.author.nickname[:15],
                    "likes": str(note.likes),
                    "type": note.note_type,
                    "url": url,
                })

            display_search_results(
                results=rows,
                columns=[
                    ColumnDef("Title", "title", style="bold", max_width=40),
                    ColumnDef("Author", "author", style="cyan", max_width=15),
                    ColumnDef("Likes", "likes", style="yellow", width=8),
                    ColumnDef("Type", "type", style="magenta", width=6),
                    ColumnDef("URL", "url", style="dim"),
                ],
                title=f"Search: {keyword}",
                summary=f"Found {len(result.notes)} results",
            )

            if save:
                storage = JSONStorage(SOURCE_NAME, output_dir=None)
                storage.output_dir.mkdir(parents=True, exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_keyword = re.sub(r'[^\w\s-]', '', keyword)[:20].strip()
                safe_keyword = re.sub(r'[-\s]+', '-', safe_keyword)
                filename = f"search_{safe_keyword}_{timestamp}.json"
                storage.save(result.notes, filename, description="notes")

    run_async(_search())


def _parse_url(url: str) -> tuple[str, str]:
    """Parse note ID and xsec_token from URL.

    Supports formats:
    - https://www.xiaohongshu.com/explore/note_id?xsec_token=xxx
    - https://www.xiaohongshu.com/discovery/item/note_id?xsec_token=xxx
    - note_id (plain ID)
    """
    if not url.startswith("http"):
        # Plain note ID
        return url.strip(), ""

    parsed = urlparse(url)
    path_parts = parsed.path.strip("/").split("/")

    note_id = ""
    for i, part in enumerate(path_parts):
        if part in ("explore", "discovery", "item", "search_result") and i + 1 < len(path_parts):
            note_id = path_parts[i + 1]
            break

    # If no recognized path pattern, use the last part
    if not note_id and path_parts:
        note_id = path_parts[-1]

    # Extract xsec_token from query params
    params = parse_qs(parsed.query)
    xsec_token = params.get("xsec_token", [""])[0]

    return note_id, xsec_token


async def _download_image(url: str, save_path: Path, client: httpx.AsyncClient) -> bool:
    """Download an image from URL."""
    try:
        response = await client.get(url, timeout=30.0)
        if response.status_code == 200:
            save_path.write_bytes(response.content)
            return True
    except Exception:
        pass
    return False


async def _download_note_images(
    note: Note,
    output_dir: Path,
    client: httpx.AsyncClient,
    progress: Progress,
    task_id,
) -> List[Path]:
    """Download all images for a note."""
    downloaded: List[Path] = []
    note_dir = output_dir / note.note_id

    if not note.images:
        return downloaded

    note_dir.mkdir(parents=True, exist_ok=True)

    for i, img_url in enumerate(note.images):
        ext = ".jpg"
        if "png" in img_url.lower():
            ext = ".png"
        elif "webp" in img_url.lower():
            ext = ".webp"
        elif "gif" in img_url.lower():
            ext = ".gif"

        filename = f"image_{i+1:02d}{ext}"
        save_path = note_dir / filename

        if await _download_image(img_url, save_path, client):
            downloaded.append(save_path)
            progress.update(task_id, advance=1)

    return downloaded


@app.command()
def fetch(
    urls: List[str] = typer.Argument(..., help="Note URLs or IDs to fetch"),
    file: Optional[Path] = typer.Option(None, "--file", "-f", help="File containing URLs (one per line)"),
    mode: str = typer.Option("api", "--mode", "-m", help="Fetch mode: api (fast) or dom (legacy)"),
    comments: bool = typer.Option(True, "--comments/--no-comments", "-c/-C", help="Fetch comments"),
    max_comments: int = typer.Option(50, "--max-comments", help="Maximum comments per note"),
    download_images: bool = typer.Option(False, "--download-images", "-d", help="Download images to local"),
    output: Path = typer.Option(Path("./xhs_output"), "--output", "-o", help="Output directory"),
    headless: bool = typer.Option(True, "--headless/--no-headless", help="Run browser in headless mode"),
    delay: float = typer.Option(2.0, "--delay", help="Delay between requests (seconds)"),
    save: bool = typer.Option(False, "--save", help="Save results"),
) -> None:
    """Fetch one or more notes by URL or ID.

    Supports single and batch fetching. Default mode is 'api' (faster),
    use '--mode dom' for legacy DOM scraping.

    Examples:
        scraper xhs fetch <url>
        scraper xhs fetch <url1> <url2> <url3> -d
        scraper xhs fetch <url> --mode dom --no-comments
        scraper xhs fetch -f urls.txt -c -d
    """
    _require_login()

    if mode not in ("api", "dom"):
        console.print("[red]Invalid mode. Choose: api, dom[/red]")
        raise typer.Exit(1)

    # Collect all URLs from arguments and file
    all_urls: List[str] = list(urls) if urls else []

    if file:
        if not file.exists():
            console.print(f"[red]File not found: {file}[/red]")
            raise typer.Exit(1)
        with open(file, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#"):
                    all_urls.append(line)

    if not all_urls:
        console.print("[red]No URLs provided. Use arguments or --file option.[/red]")
        raise typer.Exit(1)

    is_batch = len(all_urls) > 1

    async def _fetch():
        results: List[Note] = []
        failed: List[str] = []

        async with get_browser(SOURCE_NAME, headless=headless) as browser:
            if mode == "api":
                scraper = XHSApiScraper(browser)
            else:
                scraper = NoteScraper(browser)

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn() if is_batch else TextColumn(""),
                TaskProgressColumn() if is_batch else TextColumn(""),
                console=console,
            ) as progress:

                fetch_task = progress.add_task(
                    "[cyan]Fetching notes...",
                    total=len(all_urls),
                )

                for i, url in enumerate(all_urls):
                    # Parse URL
                    if mode == "api":
                        note_id, _ = XHSApiScraper.parse_note_url(url)
                    else:
                        note_id, _ = _parse_url(url)
                    short_id = note_id[:12] if note_id else url[:20]

                    progress.update(
                        fetch_task,
                        description=f"[cyan]Fetching {short_id}...",
                    )

                    try:
                        if mode == "api":
                            note = await scraper.fetch_note(
                                url=url,
                                fetch_comments=comments,
                                max_comments=max_comments,
                                silent=is_batch,
                            )
                        else:
                            _, xsec_token = _parse_url(url)
                            note, _ = await scraper.scrape(
                                note_id=note_id,
                                xsec_token=xsec_token,
                                fetch_comments=comments,
                                max_comments=max_comments,
                                silent=is_batch,
                            )

                        if note:
                            results.append(note)
                        else:
                            failed.append(short_id)

                    except Exception as e:
                        console.print(f"[dim]Error fetching {short_id}: {e}[/dim]")
                        failed.append(short_id)

                    progress.update(fetch_task, advance=1)

                    # Delay between requests (except last one)
                    if i < len(all_urls) - 1:
                        await asyncio.sleep(delay)

        if not results:
            console.print("[yellow]No notes fetched successfully.[/yellow]")
            return

        # ── Display ──────────────────────────────────────────────────────
        if is_batch:
            # Table summary for batch
            table = Table(title="Fetch Results", show_header=True, header_style="bold cyan")
            table.add_column("Note ID", style="dim", width=24)
            table.add_column("Title", max_width=35)
            table.add_column("Author", style="cyan", max_width=15)
            table.add_column("Likes", style="yellow", justify="right", width=8)
            table.add_column("Comments", style="green", justify="right", width=8)
            table.add_column("Images", style="magenta", justify="right", width=8)

            for note in results:
                table.add_row(
                    note.note_id,
                    note.title[:35] + ("..." if len(note.title) > 35 else ""),
                    note.author.nickname[:15],
                    str(note.likes),
                    str(len(note.comments)) if comments else str(note.comments_count),
                    str(len(note.images)),
                )

            console.print()
            console.print(table)
            console.print()
            console.print(f"[green]Fetched: {len(results)}/{len(all_urls)} notes[/green]")
            if failed:
                console.print(f"[yellow]Failed: {', '.join(failed[:5])}{'...' if len(failed) > 5 else ''}[/yellow]")
        else:
            # Detailed display for single note
            note = results[0]
            content = f"# {note.title}\n\n"
            content += f"**Author:** {note.author.nickname}\n"
            if note.publish_time:
                pub_str = note.publish_time.strftime('%Y-%m-%d %H:%M') if hasattr(note.publish_time, 'strftime') else str(note.publish_time)
                content += f"**Published:** {pub_str}\n"
            if note.ip_location:
                content += f"**IP Location:** {note.ip_location}\n"
            content += f"**Likes:** {note.likes} | **Comments:** {note.comments_count} | **Collects:** {note.collects} | **Shares:** {note.shares}\n"
            content += f"**Images:** {len(note.images)} | **Type:** {note.note_type}\n"
            if note.tags:
                content += f"**Tags:** {', '.join(note.tags)}\n"
            content += "\n---\n\n"
            content += note.content

            console.print(Panel(content, title=f"[bold]{note.title}[/]", border_style="cyan"))

            # Comments
            if comments and note.comments:
                console.print()
                console.print(f"[cyan]Comments ({len(note.comments)}):[/cyan]")
                for j, comment in enumerate(note.comments[:10], 1):
                    loc = f" [{comment.ip_location}]" if hasattr(comment, 'ip_location') and comment.ip_location else ""
                    console.print(
                        f"  {j}. [bold]{comment.author.nickname}[/bold]{loc}: "
                        f"{comment.content[:80]}{'...' if len(comment.content) > 80 else ''}"
                    )
                    if comment.sub_comments:
                        for sub in comment.sub_comments[:3]:
                            console.print(
                                f"     ↳ [dim]{sub.author.nickname}: "
                                f"{sub.content[:60]}{'...' if len(sub.content) > 60 else ''}[/dim]"
                            )
                if len(note.comments) > 10:
                    console.print(f"  [dim]... and {len(note.comments) - 10} more comments[/dim]")

            # Image URLs
            if note.images:
                console.print()
                console.print(f"[cyan]Images ({len(note.images)}):[/cyan]")
                for j, img_url in enumerate(note.images, 1):
                    console.print(f"  {j}. {img_url}")

        # ── Download images ──────────────────────────────────────────────
        if download_images:
            notes_with_images = [n for n in results if n.images]
            if notes_with_images:
                console.print()
                console.print(f"[cyan]Downloading images...[/cyan]")
                async with httpx.AsyncClient(
                    headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
                    follow_redirects=True,
                ) as client:
                    for note in notes_with_images:
                        note_dir = output / "images" / note.note_id
                        note_dir.mkdir(parents=True, exist_ok=True)
                        downloaded = 0
                        for j, img_url in enumerate(note.images):
                            ext = ".jpg"
                            if "png" in img_url.lower():
                                ext = ".png"
                            elif "webp" in img_url.lower():
                                ext = ".webp"
                            save_path = note_dir / f"image_{j+1:02d}{ext}"
                            if await _download_image(img_url, save_path, client):
                                downloaded += 1
                        console.print(f"  [green]{note.note_id}: {downloaded}/{len(note.images)} images → {note_dir}[/green]")

        # ── Save ─────────────────────────────────────────────────────────
        if save and results:
            output.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            if len(results) == 1:
                json_path = output / f"note_{results[0].note_id}_{timestamp}.json"
            else:
                json_path = output / f"batch_{timestamp}.json"

            data = [n.model_dump(mode="json") for n in results]
            with open(json_path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
            console.print(f"[dim]Saved to: {json_path}[/dim]")

    run_async(_fetch())


# Aliases for backward compatibility
app.command("note", hidden=True)(fetch)
app.command("batch-fetch", hidden=True)(fetch)
app.command("api-fetch", hidden=True)(fetch)


@app.command()
def options() -> None:
    """List available categories and search types."""
    # Categories
    cat_rows = [{"category": cat, "channel_id": ch_id} for cat, ch_id in CATEGORY_CHANNELS.items()]
    display_options(
        items=cat_rows,
        columns=[
            ColumnDef("Category", "category", style="cyan"),
            ColumnDef("Channel ID", "channel_id", style="dim"),
        ],
        title="Browse Categories",
    )

    console.print()

    # Search types
    type_rows = [{"type": name, "param": param} for name, param in SEARCH_TYPES.items()]
    display_options(
        items=type_rows,
        columns=[
            ColumnDef("Type", "type", style="cyan"),
            ColumnDef("Param", "param", style="dim"),
        ],
        title="Search Types (DOM mode)",
    )

    console.print()

    # API search sort options
    sort_rows = [{"sort": k, "label": v} for k, v in SEARCH_SORT_OPTIONS.items()]
    display_options(
        items=sort_rows,
        columns=[
            ColumnDef("Sort (--sort)", "sort", style="cyan"),
            ColumnDef("Label", "label"),
        ],
        title="Search Sort (API mode)",
    )


# Alias: `categories` → `options`
