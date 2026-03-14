"""CLI interface for Weibo scraper."""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TaskProgressColumn, TimeElapsedColumn
from rich.table import Table

from ...core.browser import get_state_path, DEFAULT_DATA_DIR
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
from .models import WeiboDetailResponse, WeiboHotResponse, WeiboProfileResponse, WeiboSearchResponse
from .scrapers import (
    DetailScraper,
    HotScraper,
    LoginRequiredError,
    ProfileScraper,
    RateLimitedError,
    SearchError,
    SearchScraper,
)
from .scrapers.profile import load_checkpoint, save_checkpoint
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


def _fmt_weibo_time(raw: Optional[str]) -> str:
    """Convert Weibo raw time string (e.g. 'Thu Jan 01 07:33:00 +0800 2026') to 'YYYY-MM-DD HH:MM'."""
    if not raw:
        return "-"
    try:
        dt = datetime.strptime(raw.strip(), "%a %b %d %H:%M:%S %z %Y")
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, AttributeError):
        return raw


def _profile_dir(uid: str) -> Path:
    """Per-user data directory: ~/.web_scraper/weibo/profiles/{uid}/"""
    return DEFAULT_DATA_DIR / SOURCE_NAME / "profiles" / uid


def _profile_job_tag(start: Optional[int], end: Optional[int], keyword: Optional[str]) -> str:
    """Short tag describing job parameters, used in file names."""
    parts = []
    if start:
        parts.append(datetime.fromtimestamp(start).strftime("%Y%m%d"))
    if end:
        parts.append(datetime.fromtimestamp(end).strftime("%Y%m%d"))
    if keyword:
        parts.append(_safe_filename(keyword))
    return "_".join(parts) if parts else "all"


def _profile_checkpoint_path(uid: str, start: Optional[int], end: Optional[int], keyword: Optional[str]) -> Path:
    """Stable checkpoint path inside the per-user folder."""
    tag = _profile_job_tag(start, end, keyword)
    return _profile_dir(uid) / f"checkpoint_{tag}.json"


def _parse_date(date_str: str, end_of_day: bool = False) -> int:
    """Convert YYYYMMDD or YYYY-MM-DD to Unix timestamp."""
    normalized = date_str.replace("-", "")
    try:
        dt = datetime.strptime(normalized, "%Y%m%d")
    except ValueError:
        raise typer.BadParameter(f"Invalid date '{date_str}', expected YYYYMMDD or YYYY-MM-DD.")
    if end_of_day:
        dt = dt.replace(hour=23, minute=59, second=59)
    return int(dt.timestamp())


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
    save: bool = typer.Option(False, "--save", help="Save results"),
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
    save: bool = typer.Option(False, "--save", help="Save results"),
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
    save: bool = typer.Option(False, "--save", help="Save results"),
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


def _show_profile_results(
    response: WeiboProfileResponse,
    excluded: Optional[set[str]] = None,
    use_async: bool = False,
) -> None:
    """Render first 20 profile posts + summary stats.

    Args:
        excluded: set of excluded post types, e.g. {"repost", "original", "pic", "video"}.
        use_async: whether parallel async mode was used (affects total_in_range display).
    """
    excluded = excluded or set()
    posts = response.posts
    display_posts = posts[:20]

    rows = []
    for post in display_posts:
        rows.append({
            "time": _fmt_weibo_time(post.created_at),
            "stats": format_stats(R=post.reposts_count or 0, C=post.comments_count or 0, L=post.attitudes_count or 0),
            "text": truncate(post.text_raw, 80),
            "flags": ("📌" if post.is_top else "") + ("🔁" if post.retweeted else ""),
            "url": post.detail_url or "-",
        })

    parts = []
    if response.start_time and response.end_time:
        start_str = datetime.fromtimestamp(response.start_time).strftime("%Y%m%d")
        end_str = datetime.fromtimestamp(response.end_time).strftime("%Y%m%d")
        parts.append(f"{start_str}~{end_str}")
    if response.keyword:
        parts.append(f'keyword="{response.keyword}"')
    mode_info = f"{response.mode}[{', '.join(parts)}]" if parts else response.mode

    display_search_results(
        results=rows,
        columns=[
            ColumnDef("Time", "time", style="green", max_width=20),
            ColumnDef("Stats", "stats", style="yellow", max_width=16),
            ColumnDef("Text", "text", max_width=60),
            ColumnDef("", "flags", max_width=4),
            ColumnDef("URL", "url", style="dim", max_width=44),
        ],
        title=f"Profile: {response.screen_name or response.uid}  (showing {len(display_posts)}/{len(posts)})",
        summary=None,
    )

    # ---- Summary stats ----
    total = len(posts)
    # These counts only reflect FETCHED posts (after filters applied)
    original_fetched = sum(1 for p in posts if p.retweeted is None and not p.is_ad)
    repost_fetched   = sum(1 for p in posts if p.retweeted is not None)
    with_pic  = sum(1 for p in posts if p.pic_num > 0)
    top_pinned = sum(1 for p in posts if p.is_top)

    oldest = _fmt_weibo_time(posts[-1].created_at) if posts else "-"
    newest = _fmt_weibo_time(posts[0].created_at) if posts else "-"

    # Build per-type display (mark excluded types clearly)
    ori_str    = "[dim]excluded[/]" if "original" in excluded else str(original_fetched)
    repost_str = "[dim]excluded[/]" if "repost"   in excluded else str(repost_fetched)
    pic_str    = "[dim]excluded[/]" if "pic"      in excluded else str(with_pic)

    # Active filter summary
    filter_tags = sorted(excluded)
    filter_line = (f"  Filters   : [yellow]--no-{', --no-'.join(filter_tags)}[/]  "
                   f"[dim](counts below reflect fetched data only)[/]") if filter_tags else ""

    console.print()
    console.print(f"[bold]── Stats ──────────────────────────────────────────[/]")
    console.print(f"  Fetched   : [cyan]{total}[/] posts  (mode={mode_info})")

    # Pages + total hints
    page_line = f"  Pages     : {response.pages_fetched}"
    if response.total_in_range:
        page_line += f"  |  est. total in range: {response.total_in_range}"
    elif use_async:
        page_line += "  |  est. total in range: N/A (parallel mode)"
    if response.total_posts:
        page_line += f"  |  user total (all types): {response.total_posts}"
    console.print(page_line)

    console.print(f"  Newest    : [green]{newest}[/]   →   Oldest: [green]{oldest}[/]")
    if filter_line:
        console.print(filter_line)
    console.print(
        f"  Original  : [white]{ori_str}[/]"
        f"  |  Repost: {repost_str}"
        f"  |  With pic: {pic_str}"
        f"  |  Pinned: {top_pinned}"
    )


@app.command()
def profile(
    uid: str = typer.Argument(..., help="User ID (numeric, e.g. 2761980643)"),
    limit: Optional[int] = typer.Option(None, "--limit", "-n", min=1, help="Max posts (default: all for filtered, 20 for latest)"),
    keyword: Optional[str] = typer.Option(None, "--keyword", "-k", help="Keyword filter"),
    start_time: Optional[str] = typer.Option(None, "--start-time", help="Filter start date (YYYYMMDD or YYYY-MM-DD)"),
    end_time: Optional[str] = typer.Option(None, "--end-time", help="Filter end date (YYYYMMDD or YYYY-MM-DD)"),
    no_ori: bool = typer.Option(False, "--no-ori", help="Exclude original posts"),
    no_text: bool = typer.Option(False, "--no-text", help="Exclude text posts"),
    no_pic: bool = typer.Option(False, "--no-pic", help="Exclude picture posts"),
    no_video: bool = typer.Option(False, "--no-video", help="Exclude video posts"),
    no_music: bool = typer.Option(False, "--no-music", help="Exclude music posts"),
    no_forward: bool = typer.Option(False, "--no-forward", help="Exclude forwarded posts"),
    include_ads: bool = typer.Option(False, "--include-ads", help="Include ad posts"),
    parallel: Optional[int] = typer.Option(None, "--parallel", min=1, max=10, help="Enable parallel mode with N concurrent yearly chunks (e.g. --parallel 2; use 1 if getting 418 blocks)"),
    headless: bool = typer.Option(True, "--headless/--no-headless", help="Run browser in headless mode"),
    save: bool = typer.Option(False, "--save", help="Save results"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output JSON file path"),
) -> None:
    """Fetch posts from a Weibo user's profile by UID.

    Examples:

      scraper weibo profile 2761980643 -n 50

      scraper weibo profile 2761980643 --keyword 老外

      scraper weibo profile 2761980643 --start-time 20260101 --end-time 20260201

      scraper weibo profile 2761980643 -k 老外 --start-time 2026-01-01 --end-time 2026-02-01
    """
    _require_login()
    scraper = ProfileScraper(headless=headless)

    use_filtered = keyword is not None or start_time is not None or end_time is not None

    # Convert date strings to Unix timestamps
    start_ts: Optional[int] = None
    end_ts: Optional[int] = None
    if start_time is not None:
        start_ts = _parse_date(start_time, end_of_day=False)
    if end_time is not None:
        end_ts = _parse_date(end_time, end_of_day=True)

    ckpt_path = _profile_checkpoint_path(uid, start_ts, end_ts, keyword)
    existing_ckpt = load_checkpoint(ckpt_path) if use_filtered else None
    if existing_ckpt:
        n_posts = len(existing_ckpt["posts"])
        remaining = existing_ckpt.get("remaining_chunks") or []
        hint = f"{len(remaining)} chunks remaining" if remaining else f"end_time={existing_ckpt.get('current_end_time')}"
        console.print(
            f"[yellow]Resuming from checkpoint:[/] {n_posts} posts already fetched, {hint}"
        )

    result: Optional[WeiboProfileResponse] = None
    try:
        if use_filtered:
            if (start_ts is None) != (end_ts is None):
                console.print("[red]Both --start-time and --end-time are required together.[/]")
                raise typer.Exit(1)
            with Progress(
                SpinnerColumn(),
                "[progress.description]{task.description}",
                BarColumn(),
                MofNCompleteColumn(),
                TimeElapsedColumn(),
                console=console,
                transient=True,
            ) as progress:
                task_id = progress.add_task(f"uid={uid} page=0 fetched=0", total=None)

                def on_progress(pages: int, fetched: int, total: Optional[int]) -> None:
                    progress.update(
                        task_id,
                        completed=fetched,
                        total=total,
                        description=f"uid={uid} page={pages} fetched={fetched}",
                    )

                def on_status(msg: str) -> None:
                    progress.console.print(f"[yellow]⚠  {msg}[/]")

                result = scraper.scrape_filtered(
                    uid=uid,
                    keyword=keyword,
                    start_time=start_ts,
                    end_time=end_ts,
                    limit=limit,
                    has_ori=not no_ori,
                    has_text=not no_text,
                    has_pic=not no_pic,
                    has_video=not no_video,
                    has_music=not no_music,
                    has_ret=not no_forward,
                    skip_ads=not include_ads,
                    progress_callback=on_progress,
                    checkpoint_path=ckpt_path,
                    use_async=parallel is not None,
                    status_callback=on_status,
                    max_concurrent=parallel or 2,
                )
            # Success — remove checkpoint
            if ckpt_path.exists():
                ckpt_path.unlink()
        else:
            with console.status(f"[cyan]Fetching latest posts for uid={uid}...[/]"):
                result = scraper.scrape_latest(
                    uid=uid,
                    limit=limit or 20,
                    skip_ads=not include_ads,
                )
    except (LoginRequiredError, RateLimitedError, SearchError, KeyboardInterrupt, Exception) as exc:
        # Save whatever was collected before the error
        if use_filtered and ckpt_path.exists():
            ckpt = load_checkpoint(ckpt_path)
            if ckpt and ckpt["posts"]:
                console.print(
                    f"\n[yellow]Interrupted after {len(ckpt['posts'])} posts.[/] "
                    f"Checkpoint saved to [dim]{ckpt_path}[/dim]\n"
                    f"[dim]Re-run the same command to resume.[/dim]"
                )
        if isinstance(exc, LoginRequiredError):
            console.print(f"[red]{exc}[/]")
            console.print("[dim]Run 'scraper weibo login' and retry.[/]")
        elif isinstance(exc, RateLimitedError):
            console.print(f"[yellow]{exc}[/yellow]")
        elif isinstance(exc, KeyboardInterrupt):
            console.print("\n[yellow]Cancelled.[/]")
        elif isinstance(exc, SearchError):
            console.print(f"[red]Profile fetch failed:[/red] {exc}")
        else:
            raise
        raise typer.Exit(1)

    if result is None:
        raise typer.Exit(1)

    # Collect which post types were excluded (for stats display clarification)
    excluded_types: set[str] = set()
    if no_forward:
        excluded_types.add("repost")
    if no_ori:
        excluded_types.add("original")
    if no_pic:
        excluded_types.add("pic")
    if no_video:
        excluded_types.add("video")
    if no_music:
        excluded_types.add("music")
    if no_text:
        excluded_types.add("text")

    _show_profile_results(result, excluded=excluded_types, use_async=parallel is not None)

    output_path: Optional[Path] = None
    if output:
        output_path = output.expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    elif save:
        uid_dir = _profile_dir(uid)
        uid_dir.mkdir(parents=True, exist_ok=True)

        # user_info.json — lightweight user metadata, always refreshed
        user_info = {
            "uid": result.uid,
            "screen_name": result.screen_name,
            "total_posts": result.total_posts,
            "updated_at": datetime.now().isoformat(),
        }
        (uid_dir / "user_info.json").write_text(
            json.dumps(user_info, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # posts_{tag}.json — the actual post data
        tag = _profile_job_tag(start_ts, end_ts, keyword) if use_filtered else "latest"
        output_path = uid_dir / f"posts_{tag}.json"
        output_path.write_text(
            json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    if output_path:
        display_saved(output_path)


@app.command()
def logout() -> None:
    """Clear saved Weibo session."""
    if clear_session():
        console.print("[green]Session cleared successfully.[/]")
    else:
        console.print("[dim]No session file found.[/]")
