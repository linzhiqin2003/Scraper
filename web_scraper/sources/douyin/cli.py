"""CLI interface for Douyin scraper."""

import json
from datetime import datetime
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
)
from ...core.storage import JSONStorage
from .auth import AuthStatus, LoginStatus, check_saved_session, clear_session, interactive_login
from .config import SOURCE_NAME
from .scrapers import CommentScraper, CommentScrapingError, LoginRequiredError

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
    url: str = typer.Argument(..., help="Douyin video URL (e.g. https://www.douyin.com/video/XXXXXX)"),
    limit: int = typer.Option(20, "--limit", "-n", min=1, help="Maximum number of comments to fetch"),
    with_replies: bool = typer.Option(False, "--with-replies", help="Also fetch replies for each comment"),
    reply_limit: int = typer.Option(3, "--reply-limit", min=1, help="Max replies per comment"),
    headless: bool = typer.Option(True, "--headless/--no-headless", help="Run browser in headless mode"),
    save: bool = typer.Option(True, "--save/--no-save", help="Save results to JSON"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output JSON file path"),
) -> None:
    """Fetch comments from a Douyin video by URL.

    Examples:

      scraper douyin fetch https://www.douyin.com/video/7613328220456226089

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
