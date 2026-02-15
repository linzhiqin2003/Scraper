"""CLI interface for Zhihu scraper."""

import json
from pathlib import Path
from typing import Optional

import typer
from rich.progress import Progress, SpinnerColumn, TextColumn

from ...core.browser import get_state_path
from ...core.display import (
    ColumnDef,
    console,
    display_auth_status,
    display_detail,
    display_options,
    display_saved,
    display_search_results,
    truncate,
)
from ...core.storage import JSONStorage
from .auth import AuthStatus, LoginStatus, check_saved_session, clear_session, interactive_login
from .browser import is_cdp_available
from .config import DEFAULT_CDP_PORT, SEARCH_TYPES, SOURCE_NAME, STRATEGY_AUTO, STRATEGY_PURE_API

app = typer.Typer(
    name=SOURCE_NAME,
    help="Zhihu scraper (connect to Chrome via CDP for best results).",
    no_args_is_help=True,
)


def _require_login() -> None:
    """Check that saved session or CDP is available before running commands."""
    state_file = get_state_path(SOURCE_NAME)
    if state_file.exists() or is_cdp_available():
        return
    console.print("[yellow]Not logged in.[/yellow]")
    console.print("[dim]Run one of the following to set up:[/dim]")
    console.print("  scraper zhihu login              [dim]# Interactive browser login[/dim]")
    console.print("  scraper zhihu import-cookies ...  [dim]# Import cookies from browser[/dim]")
    raise typer.Exit(1)


def _show_auth(auth: AuthStatus) -> None:
    extras: dict = {}
    if auth.checked_at:
        extras["Checked at"] = auth.checked_at.strftime("%Y-%m-%d %H:%M:%S")
    if auth.current_url:
        extras["URL"] = auth.current_url
    if auth.message:
        extras["Message"] = auth.message

    state_file = get_state_path(SOURCE_NAME)
    cdp_status = "[green]connected[/]" if is_cdp_available() else "[dim]not available[/]"
    extras["Chrome CDP"] = cdp_status

    display_auth_status(
        source_name="Zhihu",
        status=auth.status.value,
        extras=extras,
        state_file=state_file,
    )


def _normalize_same_site(value: object) -> str:
    """Normalize sameSite value to Playwright-compatible string."""
    text = str(value or "Lax").strip().lower()
    if text == "strict":
        return "Strict"
    if text == "none":
        return "None"
    return "Lax"


# =============================================================================
# Cookie Management
# =============================================================================


@app.command("import-cookies")
def import_cookies(
    path: str = typer.Argument(..., help="Path to cookies file (JSON/Netscape/state JSON)"),
    localstorage: Optional[str] = typer.Option(
        None,
        "--localstorage",
        "-l",
        help="Path to localStorage JSON file (object format)",
    ),
) -> None:
    """Import Zhihu cookies into browser_state.json."""
    cookies_path = Path(path).expanduser()
    if not cookies_path.exists():
        console.print(f"[red]File not found: {path}[/]")
        raise typer.Exit(1)

    content = cookies_path.read_text(encoding="utf-8")

    cookies = []
    origins_from_file = []
    try:
        stripped = content.strip()
        if stripped.startswith("[") or stripped.startswith("{"):
            data = json.loads(stripped)

            if isinstance(data, dict) and isinstance(data.get("cookies"), list):
                raw_cookies = data.get("cookies", [])
                if isinstance(data.get("origins"), list):
                    origins_from_file = data.get("origins", [])
            else:
                raw_cookies = data if isinstance(data, list) else [data]

            for c in raw_cookies:
                domain = str(c.get("domain") or ".zhihu.com")
                if "zhihu.com" not in domain:
                    continue
                cookies.append(
                    {
                        "name": c.get("name", ""),
                        "value": c.get("value", ""),
                        "domain": domain,
                        "path": c.get("path", "/"),
                        "expires": c.get("expirationDate", c.get("expires", -1)),
                        "httpOnly": c.get("httpOnly", False),
                        "secure": c.get("secure", False),
                        "sameSite": _normalize_same_site(c.get("sameSite")),
                    }
                )
        else:
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) < 7:
                    continue
                domain = parts[0]
                if "zhihu.com" not in domain:
                    continue
                cookies.append(
                    {
                        "name": parts[5],
                        "value": parts[6],
                        "domain": domain,
                        "path": parts[2],
                        "expires": int(parts[4]) if parts[4].isdigit() else -1,
                        "httpOnly": False,
                        "secure": parts[3].upper() == "TRUE",
                        "sameSite": "Lax",
                    }
                )
    except Exception as exc:
        console.print(f"[red]Failed to parse cookies: {exc}[/]")
        raise typer.Exit(1)

    if not cookies:
        console.print("[yellow]No Zhihu cookies found in file.[/]")
        raise typer.Exit(1)

    local_storage_items = []
    if localstorage:
        ls_path = Path(localstorage).expanduser()
        if not ls_path.exists():
            console.print(f"[red]localStorage file not found: {localstorage}[/]")
            raise typer.Exit(1)
        try:
            ls_data = json.loads(ls_path.read_text(encoding="utf-8"))
            if isinstance(ls_data, dict):
                local_storage_items = [{"name": k, "value": v} for k, v in ls_data.items()]
            console.print(f"[green]Parsed {len(local_storage_items)} localStorage items.[/]")
        except Exception as exc:
            console.print(f"[red]Failed to parse localStorage: {exc}[/]")
            raise typer.Exit(1)

    state_file = get_state_path(SOURCE_NAME)
    state_file.parent.mkdir(parents=True, exist_ok=True)

    if local_storage_items:
        origins = [{"origin": "https://www.zhihu.com", "localStorage": local_storage_items}]
    else:
        origins = origins_from_file if origins_from_file else []

    state = {"cookies": cookies, "origins": origins}
    state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    console.print(f"[green]Imported {len(cookies)} Zhihu cookies.[/]")
    console.print(f"[dim]Saved to: {state_file}[/]")


# =============================================================================
# Authentication
# =============================================================================


@app.command()
def login(
    timeout: int = typer.Option(300, "--timeout", "-t", help="Login timeout in seconds"),
    headless: bool = typer.Option(False, "--headless/--no-headless", help="Run browser in headless mode"),
) -> None:
    """Open Zhihu login page and save session after manual login."""
    console.print("[cyan]Opening browser for Zhihu login...[/]")
    console.print(
        "[dim]Complete login (QR code / SMS / password). "
        "Session will auto-save after successful status check.[/]"
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
    """Check Zhihu login status.

    Uses CDP connection if available (more reliable), otherwise Playwright.
    """
    # First check CDP
    if is_cdp_available():
        console.print("[green]Chrome CDP available[/] on port 9222")
        console.print("[dim]Scraper will use your real Chrome browser.[/]")
        return

    try:
        with console.status("[cyan]Checking Zhihu login status...[/]"):
            result = check_saved_session(headless=False)

        _show_auth(result)

        if result.status == LoginStatus.LOGGED_IN:
            raise typer.Exit(0)
        raise typer.Exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Status check cancelled.[/]")
        raise typer.Exit(130)


@app.command()
def logout() -> None:
    """Clear saved Zhihu login session."""
    if clear_session():
        console.print("[green]Session cleared successfully.[/]")
    else:
        console.print("[dim]No session file found.[/]")


# =============================================================================
# Search
# =============================================================================


@app.command()
def search(
    query: str = typer.Argument(..., help="Search keywords"),
    search_type: str = typer.Option("content", "--type", "-t", help="Search type: content, people, scholar, column, topic, zvideo"),
    limit: int = typer.Option(20, "--limit", "-n", help="Maximum results"),
    cdp_port: int = typer.Option(DEFAULT_CDP_PORT, "--cdp-port", help="Chrome CDP port"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Save to JSON file"),
    strategy: str = typer.Option(STRATEGY_AUTO, "--strategy", "-s", help="Extraction strategy: auto, pure_api, api, intercept, dom"),
    proxy_api: Optional[str] = typer.Option(None, "--proxy-api", help="Proxy pool API URL"),
) -> None:
    """Search Zhihu content.

    Strategy 'pure_api' requires only saved cookies (no browser).
    Other strategies require Chrome with remote debugging enabled:
      chrome --remote-debugging-port=9222
    """
    _require_login()

    from .scrapers import SearchScraper
    from .rate_limiter import RateLimiter
    from .proxy import ProxyPool, ProxyPoolConfig

    if strategy != STRATEGY_PURE_API and not is_cdp_available(cdp_port):
        console.print(
            "[yellow]Chrome CDP not detected.[/] For best results, start Chrome with:\n"
            f"  [cyan]chrome --remote-debugging-port={cdp_port}[/]\n"
            "[dim]Or use --strategy pure_api to avoid browser dependency.[/]\n"
        )

    rate_limiter = RateLimiter()
    proxy_pool = None
    if proxy_api:
        proxy_pool = ProxyPool(config=ProxyPoolConfig(api_url=proxy_api))
        proxy_pool.refresh()

    scraper = SearchScraper(
        cdp_port=cdp_port,
        rate_limiter=rate_limiter,
        proxy_pool=proxy_pool,
        strategy=strategy,
    )

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task(f"Searching '{query}'...", total=None)
        try:
            response = scraper.search(
                query=query,
                search_type=search_type,
                limit=limit,
            )
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)

    if not response.results:
        console.print("[yellow]No results found[/]")
        return

    data_sources = {r.data_source for r in response.results}
    source_info = ", ".join(data_sources)

    rows = []
    for r in response.results:
        stats_parts = []
        if r.upvotes is not None:
            stats_parts.append(f"{r.upvotes}赞")
        if r.comments is not None:
            stats_parts.append(f"{r.comments}评")
        rows.append({
            "type": r.content_type,
            "title": truncate(r.title, 40),
            "author": r.author or "-",
            "stats": " ".join(stats_parts),
            "url": r.url,
        })

    display_search_results(
        results=rows,
        columns=[
            ColumnDef("Type", "type", style="magenta", width=8),
            ColumnDef("Title", "title", style="bold", max_width=40),
            ColumnDef("Author", "author", style="cyan", max_width=16),
            ColumnDef("Stats", "stats", style="yellow", max_width=14),
            ColumnDef("URL", "url", style="dim", max_width=52),
        ],
        title=f"Search: {query}",
        summary=f"Found {len(response.results)} results (source: {source_info})",
    )

    if output:
        data = [r.model_dump(mode="json") for r in response.results]
        with open(output, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        display_saved(output)


@app.command()
def options() -> None:
    """List available search types and strategies."""
    # Search types
    type_rows = [{"name": name, "param": param} for name, param in SEARCH_TYPES.items()]
    display_options(
        items=type_rows,
        columns=[
            ColumnDef("Name", "name", style="cyan"),
            ColumnDef("Type Param", "param", style="dim"),
        ],
        title="Search Types",
    )

    console.print()

    # Strategies
    strategy_rows = [
        {"strategy": "auto", "description": "Try pure_api -> api -> intercept -> dom"},
        {"strategy": "pure_api", "description": "Pure Python API (no browser needed)"},
        {"strategy": "api", "description": "Browser API direct (needs CDP)"},
        {"strategy": "intercept", "description": "API response intercept (needs CDP)"},
        {"strategy": "dom", "description": "DOM extraction (needs CDP)"},
    ]
    display_options(
        items=strategy_rows,
        columns=[
            ColumnDef("Strategy", "strategy", style="cyan"),
            ColumnDef("Description", "description"),
        ],
        title="Extraction Strategies",
    )


# Alias: `search-types` → `options`
search_types = app.command("search-types", rich_help_panel="Aliases")(options)


# =============================================================================
# Article Fetching
# =============================================================================


@app.command()
def fetch(
    url: str = typer.Argument(..., help="Article or answer URL"),
    cdp_port: int = typer.Option(DEFAULT_CDP_PORT, "--cdp-port", help="Chrome CDP port"),
    save: bool = typer.Option(True, "--save/--no-save", help="Save to data directory"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file path"),
    strategy: str = typer.Option(STRATEGY_AUTO, "--strategy", "-s", help="Extraction strategy: auto, pure_api, api, intercept, dom"),
    proxy_api: Optional[str] = typer.Option(None, "--proxy-api", help="Proxy pool API URL"),
) -> None:
    """Fetch full content from a Zhihu article or answer URL.

    Strategy 'pure_api' requires only saved cookies (no browser).
    """
    _require_login()

    from .scrapers import ArticleScraper
    from .rate_limiter import RateLimiter
    from .proxy import ProxyPool, ProxyPoolConfig

    if strategy != STRATEGY_PURE_API and not is_cdp_available(cdp_port):
        console.print(
            "[yellow]Chrome CDP not detected.[/] Start Chrome with:\n"
            f"  [cyan]chrome --remote-debugging-port={cdp_port}[/]\n"
            "[dim]Or use --strategy pure_api to avoid browser dependency.[/]\n"
        )

    rate_limiter = RateLimiter()
    proxy_pool = None
    if proxy_api:
        proxy_pool = ProxyPool(config=ProxyPoolConfig(api_url=proxy_api))
        proxy_pool.refresh()

    scraper = ArticleScraper(
        cdp_port=cdp_port,
        rate_limiter=rate_limiter,
        proxy_pool=proxy_pool,
        strategy=strategy,
    )

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("Fetching content...", total=None)
        try:
            article = scraper.scrape(url)
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)

    # Display
    stats_parts = []
    if article.upvotes is not None:
        stats_parts.append(f"{article.upvotes} 赞")
    if article.comments is not None:
        stats_parts.append(f"{article.comments} 评论")

    meta = {
        "URL": article.url,
        "Type": article.content_type,
        "Author": article.author or "-",
        "Created": article.created_at or "-",
        "Stats": " · ".join(stats_parts) if stats_parts else "-",
        "Data source": article.data_source,
    }
    if article.question_title and article.question_title != article.title:
        meta["Question"] = article.question_title
    if article.tags:
        meta["Tags"] = ", ".join(article.tags)

    display_detail(
        meta=meta,
        content=article.content or "",
        title=article.title,
        content_title="Content",
    )

    # Save
    if save or output:
        storage = JSONStorage(source=SOURCE_NAME)

        if output:
            with open(output, "w", encoding="utf-8") as f:
                json.dump(article.model_dump(mode="json"), f, ensure_ascii=False, indent=2)
            display_saved(output, description="Article")
        else:
            filename = f"{article.content_type}_{article.url.split('/')[-1]}.json"
            save_path = storage.save(
                article.model_dump(mode="json"),
                filename,
                description="article",
            )
            display_saved(save_path, description="Article")


# =============================================================================
# Proxy Management
# =============================================================================


@app.command("proxy-status")
def proxy_status(
    proxy_api: Optional[str] = typer.Option(None, "--proxy-api", help="Proxy pool API URL"),
) -> None:
    """Show proxy pool status and health."""
    from .proxy import ProxyPool, ProxyPoolConfig

    if not proxy_api:
        console.print("[yellow]No proxy API configured.[/]")
        console.print("[dim]Use --proxy-api <url> to configure.[/]")
        return

    pool = ProxyPool(config=ProxyPoolConfig(api_url=proxy_api))
    with console.status("[cyan]Refreshing proxy pool...[/]"):
        count = pool.refresh()

    if count == 0 and pool.size == 0:
        console.print("[red]No proxies available from API.[/]")
        return

    stats = pool.get_stats()

    # Pool overview
    overview_rows = [
        {"property": "API URL", "value": stats["api_url"]},
        {"property": "Total Proxies", "value": str(stats["total"])},
        {"property": "Available", "value": f"[green]{stats['available']}[/]"},
        {"property": "Banned", "value": f"[red]{stats['banned']}[/]" if stats["banned"] > 0 else "0"},
    ]
    display_options(
        items=overview_rows,
        columns=[
            ColumnDef("Property", "property", style="cyan"),
            ColumnDef("Value", "value"),
        ],
        title="Proxy Pool Status",
    )

    if stats["proxies"]:
        from rich.table import Table
        proxy_table = Table(title="Top Proxies")
        proxy_table.add_column("URL", style="dim")
        proxy_table.add_column("Score", justify="right")
        proxy_table.add_column("OK", justify="right", style="green")
        proxy_table.add_column("Fail", justify="right", style="red")
        proxy_table.add_column("Block", justify="right", style="yellow")
        proxy_table.add_column("Status")

        for p in stats["proxies"][:10]:
            status_text = "[red]Banned[/]" if p["banned"] else "[green]Active[/]"
            proxy_table.add_row(
                p["url"],
                f"{p['score']:.2f}",
                str(p["successes"]),
                str(p["failures"]),
                str(p["blocks"]),
                status_text,
            )

        console.print(proxy_table)
