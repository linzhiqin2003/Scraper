"""CLI interface for Douyin scraper."""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.table import Table

from ...core.browser import get_state_path
from ...core.display import (
    ColumnDef,
    console,
    display_auth_status,
    display_detail,
    display_saved,
)
from ...core.storage import JSONStorage
from ...core.exceptions import CaptchaError
from .auth import AuthStatus, LoginStatus, check_saved_session, clear_session, interactive_login
from .config import SOURCE_NAME
from .scrapers import (
    CommentScraper,
    CommentScrapingError,
    LoginRequiredError,
    UserProfileError,
    UserProfileScraper,
    VideoDownloadError,
    VideoDownloader,
)

app = typer.Typer(
    name=SOURCE_NAME,
    help="Douyin video comment scraper (Playwright response interception).",
    no_args_is_help=True,
)


def _require_login() -> None:
    state_file = get_state_path(SOURCE_NAME)
    if state_file.exists():
        return
    console.print("[yellow]Not logged in.[/yellow]")
    console.print("[dim]Run one of:[/dim]")
    console.print("  scraper douyin login                  [dim]# Interactive browser login[/dim]")
    console.print("  scraper douyin import-cookies <file>  [dim]# Import cookies from browser[/dim]")
    raise typer.Exit(1)


def _show_auth(auth: AuthStatus) -> None:
    extras: dict = {}
    if auth.checked_at:
        extras["Checked at"] = auth.checked_at.strftime("%Y-%m-%d %H:%M:%S")
    if auth.current_url:
        extras["URL"] = auth.current_url
    if auth.message:
        extras["Message"] = auth.message

    display_auth_status(
        source_name="Douyin",
        status=auth.status.value,
        extras=extras,
        state_file=get_state_path(SOURCE_NAME),
    )


def _normalize_same_site(value: object) -> str:
    text = str(value or "Lax").strip().lower()
    if text == "strict":
        return "Strict"
    if text == "none":
        return "None"
    return "Lax"


def _load_urls_from_file(path: Path) -> list[str]:
    """Load newline-delimited URLs from text file."""
    urls: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        urls.append(line)
    return urls


# ---------------------------------------------------------------------------
# Cookie import helper
# ---------------------------------------------------------------------------

def _parse_cookies_file(path: Path) -> list[dict]:
    """Parse Netscape or JSON cookies file and return Playwright-compatible cookie list."""
    content = path.read_text(encoding="utf-8")
    cookies: list[dict] = []

    stripped = content.strip()
    if stripped.startswith("[") or stripped.startswith("{"):
        # JSON format (array or Playwright state)
        data = json.loads(stripped)
        if isinstance(data, dict) and isinstance(data.get("cookies"), list):
            raw_cookies = data["cookies"]
        else:
            raw_cookies = data if isinstance(data, list) else [data]

        for c in raw_cookies:
            domain = str(c.get("domain") or ".douyin.com")
            if "douyin.com" not in domain and "bytedance.com" not in domain:
                continue
            cookies.append({
                "name": c.get("name", ""),
                "value": str(c.get("value", "")),
                "domain": domain,
                "path": c.get("path", "/"),
                "expires": c.get("expirationDate", c.get("expires", -1)),
                "httpOnly": bool(c.get("httpOnly", False)),
                "secure": bool(c.get("secure", False)),
                "sameSite": _normalize_same_site(c.get("sameSite")),
            })
    else:
        # Netscape format: domain  flag  path  secure  expiry  name  value
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 7:
                continue
            domain = parts[0]
            if "douyin.com" not in domain and "bytedance.com" not in domain:
                continue
            cookies.append({
                "name": parts[5],
                "value": parts[6],
                "domain": domain,
                "path": parts[2],
                "expires": int(parts[4]) if parts[4].isdigit() else -1,
                "httpOnly": False,
                "secure": parts[3].upper() == "TRUE",
                "sameSite": "Lax",
            })

    return cookies


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command("import-cookies")
def import_cookies(
    path: str = typer.Argument(..., help="Path to cookies file (Netscape .txt or JSON array)"),
) -> None:
    """Import Douyin cookies from browser export into browser_state.json."""
    cookies_path = Path(path).expanduser()
    if not cookies_path.exists():
        console.print(f"[red]File not found: {path}[/]")
        raise typer.Exit(1)

    try:
        cookies = _parse_cookies_file(cookies_path)
    except Exception as exc:
        console.print(f"[red]Failed to parse cookies: {exc}[/]")
        raise typer.Exit(1)

    if not cookies:
        console.print("[yellow]No Douyin cookies found in file (expected domain: .douyin.com).[/]")
        raise typer.Exit(1)

    state_file = get_state_path(SOURCE_NAME)
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state = {"cookies": cookies, "origins": []}
    state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    console.print(f"[green]Imported {len(cookies)} Douyin cookies.[/]")
    console.print(f"[dim]Saved to: {state_file}[/]")
    console.print("[dim]Run 'scraper douyin status' to verify.[/]")


@app.command()
def login(
    timeout: int = typer.Option(300, "--timeout", "-t", help="Login timeout in seconds"),
    headless: bool = typer.Option(False, "--headless/--no-headless", help="Run browser in headless mode"),
) -> None:
    """Open Douyin login page and save session after manual login."""
    console.print("[cyan]Opening browser for Douyin login...[/]")
    console.print("[dim]Complete login (QR code or phone). Session will auto-save after successful login.[/]")

    try:
        result = interactive_login(headless=headless, timeout_seconds=timeout)
        _show_auth(result)
        raise typer.Exit(0 if result.status == LoginStatus.LOGGED_IN else 1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Login cancelled.[/]")
        raise typer.Exit(130)


@app.command()
def status() -> None:
    """Check saved Douyin login status."""
    try:
        with console.status("[cyan]Checking Douyin login status...[/]"):
            result = check_saved_session(headless=True)
        _show_auth(result)
        raise typer.Exit(0 if result.status == LoginStatus.LOGGED_IN else 1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Status check cancelled.[/]")
        raise typer.Exit(130)


@app.command()
def logout() -> None:
    """Clear saved Douyin session."""
    if clear_session():
        console.print("[green]Session cleared successfully.[/]")
    else:
        console.print("[dim]No session file found.[/]")


@app.command()
def fetch(
    url: str = typer.Argument(..., help="Douyin video URL or video ID"),
    limit: int = typer.Option(20, "--limit", "-n", min=1, help="Maximum number of comments to fetch"),
    with_replies: bool = typer.Option(False, "--with-replies", help="Also fetch replies for each comment"),
    reply_limit: int = typer.Option(3, "--reply-limit", min=1, help="Max replies per comment"),
    headless: bool = typer.Option(True, "--headless/--no-headless", help="Run browser in headless mode"),
    save: bool = typer.Option(True, "--save/--no-save", help="Save results to JSON"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output JSON file path"),
) -> None:
    """Fetch comments from a Douyin video by URL or video ID.

    Examples:

      scraper douyin fetch https://www.douyin.com/video/7613328220456226089

      scraper douyin fetch 7613328220456226089

      scraper douyin fetch https://www.douyin.com/video/7613328220456226089 -n 100

      scraper douyin fetch https://www.douyin.com/video/7613328220456226089 --with-replies

      scraper douyin fetch <url> -n 50 --no-save
    """
    _require_login()
    scraper = CommentScraper(headless=headless)

    try:
        with console.status(f"[cyan]Fetching comments for {url}...[/]"):
            result = scraper.scrape(
                url=url,
                limit=limit,
                with_replies=with_replies,
                reply_limit=reply_limit,
            )
    except LoginRequiredError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1)
    except CaptchaError as exc:
        console.print(f"[yellow]{exc}[/]")
        raise typer.Exit(1)
    except CommentScrapingError as exc:
        console.print(f"[red]Fetch failed:[/red] {exc}")
        raise typer.Exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Fetch cancelled.[/]")
        raise typer.Exit(130)

    # --- Display summary ---
    meta = {
        "Video ID": result.aweme_id,
        "URL": result.url,
        "Description": (result.desc or "-")[:100],
        "Author": result.author_name or "-",
        "Total comments (API)": str(result.total_comments) if result.total_comments is not None else "-",
        "Fetched": str(result.fetched_count),
        "Pages intercepted": str(result.pages_fetched),
        "Method": result.method,
        "Scraped at": result.scraped_at.strftime("%Y-%m-%d %H:%M:%S"),
    }

    comment_table = None
    if result.comments:
        comment_table = Table(show_header=True, header_style="bold magenta")
        comment_table.add_column("#", style="dim", width=4)
        comment_table.add_column("User", style="cyan", max_width=18)
        comment_table.add_column("IP", style="dim", max_width=8)
        comment_table.add_column("Likes", style="yellow", width=7)
        comment_table.add_column("Replies", style="blue", width=8)
        comment_table.add_column("Text", max_width=80)

        for idx, c in enumerate(result.comments, 1):
            reply_str = str(c.reply_count or 0)
            if c.replies:
                reply_str += f" ({len(c.replies)} fetched)"
            comment_table.add_row(
                str(idx),
                (c.user.nickname if c.user else "-") or "-",
                (c.ip_label or c.user.ip_label if c.user else "") or "-",
                str(c.digg_count or 0),
                reply_str,
                c.text[:200],
            )

    display_detail(
        meta=meta,
        content="",
        title="Douyin Comments",
        content_title=None,
        sub_tables=[("Comments", comment_table)] if comment_table else None,
    )

    # --- Save ---
    output_path: Optional[Path] = None
    if output:
        output_path = output.expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    elif save:
        storage = JSONStorage(source=SOURCE_NAME)
        filename = storage.generate_filename("comments", suffix=result.aweme_id)
        output_path = storage.save(result, filename, description="comments", silent=True)

    if output_path:
        display_saved(output_path)


@app.command()
def download(
    urls: Optional[list[str]] = typer.Argument(None, help="One or more Douyin video URLs, jingxuan URLs, or video IDs"),
    headless: bool = typer.Option(True, "--headless/--no-headless", help="Run browser in headless mode"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output MP4 file path"),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir", help="Output directory for batch downloads"),
    input_file: Optional[Path] = typer.Option(None, "--input-file", help="Text file with one Douyin URL or video ID per line"),
    retries: int = typer.Option(3, "--retries", min=1, help="Retry attempts per URL"),
) -> None:
    """Download one or more Douyin videos to local disk."""
    _require_login()
    all_urls = list(urls or [])
    if input_file is not None:
        path = input_file.expanduser()
        if not path.exists():
            console.print(f"[red]Input file not found:[/red] {path}")
            raise typer.Exit(1)
        all_urls.extend(_load_urls_from_file(path))
    if not all_urls:
        console.print("[red]Provide at least one URL or use --input-file.[/]")
        raise typer.Exit(1)
    deduped_urls = list(dict.fromkeys(all_urls))

    downloader = VideoDownloader(headless=headless, max_retries=retries)
    if len(deduped_urls) > 1 and output is not None:
        console.print("[red]--output only supports a single URL. Use --output-dir for batch downloads.[/]")
        raise typer.Exit(1)

    results = []
    failures: list[tuple[str, str]] = []
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Downloading Douyin videos...", total=len(deduped_urls))
        for index, url in enumerate(deduped_urls):
            target_output = output if index == 0 else None
            try:
                progress.update(task, description=f"Processing {index + 1}/{len(deduped_urls)}")
                result = downloader.download(url=url, output=target_output, output_dir=output_dir)
                results.append(result)
            except VideoDownloadError as exc:
                failures.append((url, str(exc)))
            except KeyboardInterrupt:
                console.print("\n[yellow]Download cancelled.[/]")
                raise typer.Exit(130)
            finally:
                progress.advance(task)

    if len(results) == 1 and not failures:
        result = results[0]
        meta = {
            "Video ID": result.aweme_id,
            "Description": (result.desc or "-")[:100],
            "Author": result.author_name or "-",
            "Method": result.method,
            "Duration (ms)": result.duration_ms or "-",
            "File size": result.file_size,
            "Video URL": result.video_url,
            "Saved to": result.output_path,
            "Metadata": result.metadata_path,
            "Status": "skipped" if result.skipped else "downloaded",
            "Attempts": result.attempts,
            "Downloaded at": result.downloaded_at.strftime("%Y-%m-%d %H:%M:%S"),
        }
        display_detail(meta=meta, content="", title="Douyin Video")
        display_saved(result.output_path, description="Video")
        display_saved(result.metadata_path, description="Metadata")
        return

    if results:
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("#", style="dim", width=4)
        table.add_column("Video ID", style="cyan", width=20)
        table.add_column("Author", style="cyan", max_width=16)
        table.add_column("Status", style="green", width=10)
        table.add_column("Size", style="yellow", width=10)
        table.add_column("MP4", max_width=42)
        table.add_column("JSON", max_width=42)
        for idx, result in enumerate(results, 1):
            table.add_row(
                str(idx),
                result.aweme_id,
                result.author_name or "-",
                "skipped" if result.skipped else "downloaded",
                str(result.file_size),
                result.output_path,
                result.metadata_path,
            )
        console.print(table)

    if failures:
        table = Table(show_header=True, header_style="bold red")
        table.add_column("#", style="dim", width=4)
        table.add_column("URL", max_width=48)
        table.add_column("Error", max_width=80)
        for idx, (url, error) in enumerate(failures, 1):
            table.add_row(str(idx), url, error)
        console.print(table)
        raise typer.Exit(1)


def _format_count(n: Optional[int]) -> str:
    """Format large numbers with wan (万) suffix."""
    if n is None:
        return "-"
    if n >= 100_000_000:
        return f"{n / 100_000_000:.1f}亿"
    if n >= 10_000:
        return f"{n / 10_000:.1f}万"
    return str(n)


def _format_gender(g: Optional[int]) -> str:
    if g == 1:
        return "男"
    if g == 2:
        return "女"
    return "-"


def _format_timestamp(ts: Optional[int]) -> str:
    if ts is None:
        return "-"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def _format_duration(ms: Optional[int]) -> str:
    if ms is None:
        return "-"
    secs = ms // 1000
    mins, secs = divmod(secs, 60)
    return f"{mins}:{secs:02d}"


@app.command()
def profile(
    url: str = typer.Argument(..., help="Douyin user profile URL"),
    headless: bool = typer.Option(True, "--headless/--no-headless", help="Run browser in headless mode"),
    save: bool = typer.Option(True, "--save/--no-save", help="Save results to JSON"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output JSON file path"),
) -> None:
    """Fetch a Douyin user's profile information.

    Examples:

      scraper douyin profile https://www.douyin.com/user/MS4wLjABAAAAxxx

      scraper douyin profile <url> --no-save
    """
    _require_login()
    scraper = UserProfileScraper(headless=headless)

    try:
        with console.status("[cyan]Fetching user profile...[/]"):
            result = scraper.scrape_profile(url=url)
    except LoginRequiredError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1)
    except CaptchaError as exc:
        console.print(f"[yellow]{exc}[/]")
        raise typer.Exit(1)
    except UserProfileError as exc:
        console.print(f"[red]Profile fetch failed:[/red] {exc}")
        raise typer.Exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Fetch cancelled.[/]")
        raise typer.Exit(130)

    p = result.profile
    meta = {
        "UID": p.uid or "-",
        "Sec UID": p.sec_uid or "-",
        "Douyin ID": p.unique_id or "-",
        "Nickname": p.nickname or "-",
        "Gender": _format_gender(p.gender),
        "Location": ", ".join(filter(None, [p.city, p.province, p.country])) or "-",
        "IP Location": p.ip_location or "-",
        "School": p.school_name or "-",
        "Followers": _format_count(p.follower_count),
        "Following": _format_count(p.following_count),
        "Videos": _format_count(p.aweme_count),
        "Total Likes": _format_count(p.total_favorited),
        "Collections": str(p.mix_count) if p.mix_count is not None else "-",
        "Verification": p.custom_verify or (
            {0: "None", 1: "Personal", 2: "Enterprise"}.get(p.verification_type or 0, "-")
        ),
        "Live Status": "Live" if p.live_status == 1 else "Offline",
        "Account": "Private" if p.secret == 1 else "Public",
        "Scraped at": result.scraped_at.strftime("%Y-%m-%d %H:%M:%S"),
    }

    display_detail(
        meta=meta,
        content=p.signature or "",
        title="Douyin User Profile",
        content_title="Bio",
    )

    output_path: Optional[Path] = None
    if output:
        output_path = output.expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    elif save:
        storage = JSONStorage(source=SOURCE_NAME)
        filename = storage.generate_filename("profile", suffix=p.uid or result.sec_uid)
        output_path = storage.save(result, filename, description="profile", silent=True)

    if output_path:
        display_saved(output_path)


@app.command()
def videos(
    url: str = typer.Argument(..., help="Douyin user profile URL"),
    limit: int = typer.Option(18, "--limit", "-n", min=1, help="Maximum number of videos to fetch"),
    headless: bool = typer.Option(True, "--headless/--no-headless", help="Run browser in headless mode"),
    save: bool = typer.Option(True, "--save/--no-save", help="Save results to JSON"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output JSON file path"),
) -> None:
    """Fetch a Douyin user's posted video list.

    Examples:

      scraper douyin videos https://www.douyin.com/user/MS4wLjABAAAAxxx

      scraper douyin videos <url> -n 50

      scraper douyin videos <url> -n 100 --no-save
    """
    _require_login()
    scraper = UserProfileScraper(headless=headless)

    try:
        with console.status(f"[cyan]Fetching videos (limit={limit})...[/]"):
            result = scraper.scrape_videos(url=url, limit=limit)
    except LoginRequiredError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1)
    except CaptchaError as exc:
        console.print(f"[yellow]{exc}[/]")
        raise typer.Exit(1)
    except UserProfileError as exc:
        console.print(f"[red]Videos fetch failed:[/red] {exc}")
        raise typer.Exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Fetch cancelled.[/]")
        raise typer.Exit(130)

    meta = {
        "Author": result.author_name or "-",
        "Sec UID": result.sec_uid,
        "Total Videos": str(result.total_videos) if result.total_videos is not None else "-",
        "Fetched": str(result.fetched_count),
        "Pages": str(result.pages_fetched),
        "Has More": "Yes" if result.has_more else "No",
        "Method": result.method,
        "Scraped at": result.scraped_at.strftime("%Y-%m-%d %H:%M:%S"),
    }

    video_table = None
    if result.videos:
        video_table = Table(show_header=True, header_style="bold magenta")
        video_table.add_column("#", style="dim", width=4)
        video_table.add_column("Video ID", style="cyan", width=20)
        video_table.add_column("Published", style="dim", width=16)
        video_table.add_column("Duration", style="dim", width=8)
        video_table.add_column("Likes", style="yellow", width=10)
        video_table.add_column("Comments", style="blue", width=10)
        video_table.add_column("Shares", style="green", width=10)
        video_table.add_column("Collects", style="magenta", width=10)
        video_table.add_column("Description", max_width=50)

        for idx, v in enumerate(result.videos, 1):
            stats = v.statistics
            top_mark = " [red]TOP[/red]" if v.is_top else ""
            video_table.add_row(
                str(idx),
                v.aweme_id,
                _format_timestamp(v.create_time),
                _format_duration(v.duration),
                _format_count(stats.digg_count if stats else None),
                _format_count(stats.comment_count if stats else None),
                _format_count(stats.share_count if stats else None),
                _format_count(stats.collect_count if stats else None),
                ((v.desc or "")[:100] + top_mark),
            )

    display_detail(
        meta=meta,
        content="",
        title="Douyin User Videos",
        content_title=None,
        sub_tables=[("Videos", video_table)] if video_table else None,
    )

    output_path: Optional[Path] = None
    if output:
        output_path = output.expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    elif save:
        storage = JSONStorage(source=SOURCE_NAME)
        filename = storage.generate_filename("videos", suffix=result.sec_uid[:16])
        output_path = storage.save(result, filename, description="videos", silent=True)

    if output_path:
        display_saved(output_path)
