"""CLI interface for Xiaohongshu scraper."""

import asyncio
import hashlib
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
from ...core.display import (
    ColumnDef,
    console,
    display_options,
    display_search_results,
)
from ...core.storage import JSONStorage
from .auth import AuthManager
from .config import SOURCE_NAME, CATEGORY_CHANNELS, SEARCH_TYPES, COOKIE_PATH, DATA_DIR
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
auth = app.command("auth", rich_help_panel="Aliases")(status)


@app.command()
def logout() -> None:
    """Clear login session."""
    if COOKIE_PATH.exists():
        COOKIE_PATH.unlink()
        console.print("[green]Session cleared successfully.[/green]")
    else:
        console.print("[dim]No session file found.[/dim]")


@app.command()
def browse(
    category: str = typer.Option("推荐", "--category", "-c", help="Category to explore"),
    limit: int = typer.Option(20, "--limit", "-n", help="Maximum number of notes"),
    headless: bool = typer.Option(True, "--headless/--no-headless", help="Run browser in headless mode"),
    output: str = typer.Option("./output", "--output", "-o", help="Save results to directory"),
    no_save: bool = typer.Option(False, "--no-save", help="Don't save to files"),
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


# Alias: `explore` → `browse`
explore = app.command("explore", rich_help_panel="Aliases")(browse)


@app.command()
def search(
    keyword: str = typer.Argument(..., help="Search keyword"),
    search_type: str = typer.Option("all", "--type", "-t", help="Search type: all, video, image"),
    limit: int = typer.Option(20, "--limit", "-n", help="Maximum number of results"),
    headless: bool = typer.Option(True, "--headless/--no-headless", help="Run browser in headless mode"),
    output: str = typer.Option("./output", "--output", "-o", help="Save results to directory"),
    no_save: bool = typer.Option(False, "--no-save", help="Don't save to files"),
) -> None:
    """Search for notes on Xiaohongshu."""
    _require_login()
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

            rows = []
            for note in result.notes:
                rows.append({
                    "title": note.title[:40] + ("..." if len(note.title) > 40 else ""),
                    "author": note.author.nickname[:15],
                    "likes": str(note.likes),
                    "type": note.note_type,
                })

            display_search_results(
                results=rows,
                columns=[
                    ColumnDef("Title", "title", style="bold", max_width=40),
                    ColumnDef("Author", "author", style="cyan", max_width=15),
                    ColumnDef("Likes", "likes", style="yellow", width=8),
                    ColumnDef("Type", "type", style="magenta", width=6),
                ],
                title=f"Search: {keyword}",
                summary=f"Found {len(result.notes)} results",
            )

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
    note_id: str = typer.Argument(..., help="Note ID or URL to fetch"),
    token: Optional[str] = typer.Option(None, "--token", "-t", help="xsec_token for access"),
    comments: bool = typer.Option(False, "--comments", "-c", help="Also fetch comments"),
    max_comments: int = typer.Option(50, "--max-comments", help="Maximum comments to fetch"),
    download_images: bool = typer.Option(False, "--download-images", "-d", help="Download images to local"),
    output: Path = typer.Option(Path("./xhs_output"), "--output", "-o", help="Output directory for images"),
    headless: bool = typer.Option(False, "--headless/--no-headless", help="Run browser in headless mode"),
) -> None:
    """Fetch a specific note by ID or URL."""
    _require_login()

    # Parse URL if provided
    parsed_id, parsed_token = _parse_url(note_id)
    actual_id = parsed_id
    actual_token = token or parsed_token

    async def _fetch():
        async with get_browser(SOURCE_NAME, headless=headless) as browser:
            scraper = NoteScraper(browser)
            result, _ = await scraper.scrape(
                note_id=actual_id,
                xsec_token=actual_token,
                fetch_comments=comments,
                max_comments=max_comments,
            )

            if not result:
                console.print(f"[red]Failed to fetch note: {actual_id}[/red]")
                raise typer.Exit(1)

            # Display note content
            content = f"# {result.title}\n\n"
            content += f"**Author:** {result.author.nickname}\n"
            content += f"**Published:** {result.publish_time}\n"
            content += f"**Likes:** {result.likes} | **Comments:** {result.comments_count} | **Collects:** {result.collects}\n"
            content += f"**Images:** {len(result.images)}\n\n"
            if result.tags:
                content += f"**Tags:** {', '.join(result.tags)}\n\n"
            content += "---\n\n"
            content += result.content

            console.print(Panel(content, title=f"[bold]{result.title}[/]", border_style="cyan"))

            # Display comments if fetched
            if comments and result.comments:
                console.print()
                console.print(f"[cyan]Comments ({len(result.comments)}):[/cyan]")
                for i, comment in enumerate(result.comments[:10], 1):
                    console.print(f"  {i}. [bold]{comment.author.nickname}[/bold]: {comment.content[:80]}{'...' if len(comment.content) > 80 else ''}")
                    if comment.sub_comments:
                        for sub in comment.sub_comments[:3]:
                            console.print(f"     ↳ [dim]{sub.author.nickname}: {sub.content[:60]}{'...' if len(sub.content) > 60 else ''}[/dim]")
                if len(result.comments) > 10:
                    console.print(f"  [dim]... and {len(result.comments) - 10} more comments[/dim]")

            # Download images if requested
            if download_images and result.images:
                output.mkdir(parents=True, exist_ok=True)
                images_dir = output / "images" / actual_id
                images_dir.mkdir(parents=True, exist_ok=True)

                console.print()
                console.print(f"[cyan]Downloading {len(result.images)} images...[/cyan]")

                async with httpx.AsyncClient(
                    headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
                    follow_redirects=True,
                ) as client:
                    downloaded = 0
                    for i, img_url in enumerate(result.images):
                        ext = ".jpg"
                        if "png" in img_url.lower():
                            ext = ".png"
                        elif "webp" in img_url.lower():
                            ext = ".webp"

                        save_path = images_dir / f"image_{i+1:02d}{ext}"
                        if await _download_image(img_url, save_path, client):
                            downloaded += 1

                    console.print(f"[green]Downloaded {downloaded}/{len(result.images)} images to {images_dir}[/green]")

            # Display image URLs
            if result.images:
                console.print()
                console.print("[cyan]Image URLs:[/cyan]")
                for i, url in enumerate(result.images, 1):
                    console.print(f"  {i}. {url[:80]}...")

    run_async(_fetch())


# Alias: `note` → `fetch`
note = app.command("note", rich_help_panel="Aliases")(fetch)


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
        title="Search Types",
    )


# Alias: `categories` → `options`
categories = app.command("categories", rich_help_panel="Aliases")(options)


@app.command("batch-fetch")
def batch_fetch(
    urls: List[str] = typer.Argument(None, help="List of URLs or note IDs to fetch"),
    file: Optional[Path] = typer.Option(None, "--file", "-f", help="File containing URLs (one per line)"),
    output: Path = typer.Option(Path("./xhs_output"), "--output", "-o", help="Output directory"),
    comments: bool = typer.Option(False, "--comments", "-c", help="Also fetch comments"),
    max_comments: int = typer.Option(50, "--max-comments", help="Maximum comments per note"),
    download_images: bool = typer.Option(False, "--download-images", "-d", help="Download images to local"),
    headless: bool = typer.Option(True, "--headless/--no-headless", help="Run browser in headless mode"),
    delay: float = typer.Option(3.0, "--delay", help="Delay between requests (seconds)"),
    no_save: bool = typer.Option(False, "--no-save", help="Don't save JSON results"),
) -> None:
    """Batch fetch multiple notes by URLs or IDs.

    Examples:
        scraper xhs batch-fetch URL1 URL2 URL3
        scraper xhs batch-fetch -f urls.txt -c -d
        scraper xhs batch-fetch NOTE_ID1 NOTE_ID2 --comments --download-images
    """
    _require_login()

    # Collect URLs from arguments and file
    all_urls: List[str] = []

    if urls:
        all_urls.extend(urls)

    if file:
        if not file.exists():
            console.print(f"[red]File not found: {file}[/red]")
            raise typer.Exit(1)
        with open(file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    all_urls.append(line)

    if not all_urls:
        console.print("[red]No URLs provided. Use arguments or --file option.[/red]")
        raise typer.Exit(1)

    # Parse URLs to get note IDs and tokens
    parsed_notes = []
    for url in all_urls:
        note_id, xsec_token = _parse_url(url)
        if note_id:
            parsed_notes.append({"note_id": note_id, "xsec_token": xsec_token, "url": url})

    if not parsed_notes:
        console.print("[red]No valid note IDs found in provided URLs.[/red]")
        raise typer.Exit(1)

    console.print(f"[cyan]Batch fetching {len(parsed_notes)} notes...[/cyan]")
    if comments:
        console.print(f"[dim]Comments enabled (max {max_comments} per note)[/dim]")
    if download_images:
        console.print(f"[dim]Image download enabled[/dim]")

    async def _batch_fetch():
        results: List[Note] = []
        failed: List[str] = []
        all_downloaded_images: List[Path] = []

        output.mkdir(parents=True, exist_ok=True)
        images_dir = output / "images"

        async with get_browser(SOURCE_NAME, headless=headless) as browser:
            scraper = NoteScraper(browser)

            # Create HTTP client for image downloads
            async with httpx.AsyncClient(
                headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
                follow_redirects=True,
            ) as http_client:

                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TaskProgressColumn(),
                    console=console,
                ) as progress:

                    fetch_task = progress.add_task("[cyan]Fetching notes...", total=len(parsed_notes))

                    for i, item in enumerate(parsed_notes):
                        note_id = item["note_id"]
                        xsec_token = item["xsec_token"]

                        progress.update(fetch_task, description=f"[cyan]Fetching {note_id[:8]}...")

                        try:
                            note, _ = await scraper.scrape(
                                note_id=note_id,
                                xsec_token=xsec_token,
                                silent=True,
                                fetch_comments=comments,
                                max_comments=max_comments,
                            )

                            if note:
                                results.append(note)

                                # Download images if requested
                                if download_images and note.images:
                                    img_task = progress.add_task(
                                        f"[dim]Downloading images for {note_id[:8]}...",
                                        total=len(note.images),
                                    )
                                    downloaded = await _download_note_images(
                                        note, images_dir, http_client, progress, img_task
                                    )
                                    all_downloaded_images.extend(downloaded)
                                    progress.remove_task(img_task)
                            else:
                                failed.append(note_id)

                        except Exception as e:
                            console.print(f"[dim]Error fetching {note_id}: {e}[/dim]")
                            failed.append(note_id)

                        progress.update(fetch_task, advance=1)

                        # Delay between requests (except last one)
                        if i < len(parsed_notes) - 1:
                            await asyncio.sleep(delay)

        # Display results summary
        console.print()
        table = Table(title="Batch Fetch Results", show_header=True, header_style="bold cyan")
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

        console.print(table)

        # Summary
        console.print()
        console.print(f"[green]Successfully fetched: {len(results)}/{len(parsed_notes)} notes[/green]")
        if failed:
            console.print(f"[yellow]Failed: {len(failed)} notes[/yellow]")
            console.print(f"[dim]Failed IDs: {', '.join(failed[:5])}{'...' if len(failed) > 5 else ''}[/dim]")
        if download_images and all_downloaded_images:
            console.print(f"[magenta]Downloaded: {len(all_downloaded_images)} images to {images_dir}[/magenta]")

        # Save results
        if not no_save and results:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            json_path = output / f"batch_results_{timestamp}.json"
            storage = JSONStorage(SOURCE_NAME, output_dir=output)

            # Convert to dict for JSON serialization
            data = [note.model_dump(mode="json") for note in results]
            with open(json_path, "w", encoding="utf-8") as f:
                import json
                json.dump(data, f, ensure_ascii=False, indent=2)

            console.print(f"[dim]Results saved to: {json_path}[/dim]")

    run_async(_batch_fetch())


@app.command("api-fetch")
def api_fetch(
    urls: List[str] = typer.Argument(..., help="Note URLs or IDs to fetch"),
    comments: bool = typer.Option(True, "--comments/--no-comments", "-c/-C", help="Fetch comments"),
    max_comments: int = typer.Option(50, "--max-comments", help="Maximum comments per note"),
    download_images: bool = typer.Option(False, "--download-images", "-d", help="Download images to local"),
    output: Path = typer.Option(Path("./xhs_output"), "--output", "-o", help="Output directory"),
    headless: bool = typer.Option(True, "--headless/--no-headless", help="Run browser in headless mode"),
    delay: float = typer.Option(2.0, "--delay", help="Delay between requests (seconds)"),
    no_save: bool = typer.Option(False, "--no-save", help="Don't save JSON results"),
) -> None:
    """Fetch notes via API extraction (faster & more reliable).

    Uses SSR __INITIAL_STATE__ for note data and browser API for comments.
    Much faster than DOM scraping.

    Examples:
        scraper xhs api-fetch https://www.xiaohongshu.com/explore/xxx?xsec_token=yyy
        scraper xhs api-fetch URL1 URL2 URL3 -d
        scraper xhs api-fetch NOTE_ID --no-comments
    """
    _require_login()

    async def _api_fetch():
        results: List[Note] = []
        failed: List[str] = []

        async with get_browser(SOURCE_NAME, headless=headless) as browser:
            scraper = XHSApiScraper(browser)

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=console,
            ) as progress:

                fetch_task = progress.add_task("[cyan]Fetching notes...", total=len(urls))

                for i, url in enumerate(urls):
                    note_id, _ = XHSApiScraper.parse_note_url(url)
                    short_id = note_id[:12] if note_id else url[:20]
                    progress.update(fetch_task, description=f"[cyan]Fetching {short_id}...")

                    try:
                        note = await scraper.fetch_note(
                            url=url,
                            fetch_comments=comments,
                            max_comments=max_comments,
                            silent=True,
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
                    if i < len(urls) - 1:
                        await asyncio.sleep(delay)

        # Display results
        for note in results:
            content = f"# {note.title}\n\n"
            content += f"**Author:** {note.author.nickname}\n"
            if note.publish_time:
                content += f"**Published:** {note.publish_time.strftime('%Y-%m-%d %H:%M')}\n"
            if note.ip_location:
                content += f"**IP Location:** {note.ip_location}\n"
            content += f"**Likes:** {note.likes} | **Comments:** {note.comments_count} | **Collects:** {note.collects} | **Shares:** {note.shares}\n"
            content += f"**Images:** {len(note.images)} | **Type:** {note.note_type}\n"
            if note.tags:
                content += f"**Tags:** {', '.join(note.tags)}\n"
            content += "\n---\n\n"
            content += note.content

            console.print(Panel(content, title=f"[bold]{note.title}[/]", border_style="cyan"))

            # Display comments
            if comments and note.comments:
                console.print(f"[cyan]Comments ({len(note.comments)}):[/cyan]")
                for j, comment in enumerate(note.comments[:10], 1):
                    loc = f" [{comment.ip_location}]" if comment.ip_location else ""
                    console.print(
                        f"  {j}. [bold]{comment.author.nickname}[/bold]{loc}: "
                        f"{comment.content[:80]}{'...' if len(comment.content) > 80 else ''}"
                        f"  [dim]👍 {comment.likes}[/dim]"
                    )
                    for sub in comment.sub_comments[:3]:
                        console.print(
                            f"     ↳ [dim]{sub.author.nickname}: "
                            f"{sub.content[:60]}{'...' if len(sub.content) > 60 else ''}[/dim]"
                        )
                if len(note.comments) > 10:
                    console.print(f"  [dim]... and {len(note.comments) - 10} more comments[/dim]")

            # Display image URLs
            if note.images:
                console.print(f"[cyan]Images ({len(note.images)}):[/cyan]")
                for j, img_url in enumerate(note.images, 1):
                    console.print(f"  {j}. {img_url}")

            console.print()

        # Download images
        if download_images:
            images_to_download = [(n, img) for n in results for img in n.images if n.images]
            if images_to_download:
                console.print(f"[cyan]Downloading images...[/cyan]")
                async with httpx.AsyncClient(
                    headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
                    follow_redirects=True,
                ) as client:
                    for note in results:
                        if not note.images:
                            continue
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

        # Summary
        if len(urls) > 1:
            console.print(f"[green]Fetched: {len(results)}/{len(urls)} notes[/green]")
            if failed:
                console.print(f"[yellow]Failed: {', '.join(failed)}[/yellow]")

        # Save results
        if not no_save and results:
            output.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            if len(results) == 1:
                json_path = output / f"note_{results[0].note_id}_{timestamp}.json"
            else:
                json_path = output / f"api_batch_{timestamp}.json"

            data = [note.model_dump(mode="json") for note in results]
            with open(json_path, "w", encoding="utf-8") as f:
                import json
                json.dump(data, f, ensure_ascii=False, indent=2)
            console.print(f"[dim]Saved to: {json_path}[/dim]")

    run_async(_api_fetch())


# Alias: `batch` → `batch-fetch`
batch = app.command("batch", rich_help_panel="Aliases")(batch_fetch)
