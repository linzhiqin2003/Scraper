"""CLI interface for Reuters scraper."""

import time
from typing import List, Optional

import typer

from ...core.browser import create_browser, get_state_path
from ...core.display import (
    ColumnDef,
    console,
    display_auth_status,
    display_options,
    display_saved,
    display_search_results,
    truncate,
)
from .auth import AuthStatus, LoginStatus, check_login_status, interactive_login, perform_login
from .config import SOURCE_NAME, VALID_SECTIONS, VALID_DATE_RANGES, SECTIONS
from .models import Article
from .scrapers import SearchScraper, ArticleScraper, SectionScraper
from .scrapers.search import CaptchaError

app = typer.Typer(
    name="reuters",
    help="Reuters news scraper",
    no_args_is_help=True,
)


def validate_section(value: Optional[str]) -> Optional[str]:
    """Validate section parameter."""
    if value is None:
        return None
    value_lower = value.lower()
    if value_lower not in VALID_SECTIONS:
        raise typer.BadParameter(
            f"Invalid section '{value}'. Valid options: {', '.join(VALID_SECTIONS)}"
        )
    return value_lower


def validate_date_range(value: Optional[str]) -> Optional[str]:
    """Validate date range parameter."""
    if value is None:
        return None
    if value not in VALID_DATE_RANGES:
        raise typer.BadParameter(
            f"Invalid date range '{value}'. Valid options: {', '.join(VALID_DATE_RANGES)}"
        )
    return value


def _show_auth(auth: AuthStatus) -> None:
    extras: dict = {}
    if auth.email:
        extras["Email"] = auth.email
    if auth.checked_at:
        extras["Checked at"] = auth.checked_at.strftime("%Y-%m-%d %H:%M:%S")
    if auth.message:
        extras["Message"] = auth.message

    display_auth_status(
        source_name="Reuters",
        status=auth.status.value,
        extras=extras,
        state_file=get_state_path(SOURCE_NAME),
    )


@app.command()
def login(
    email: Optional[str] = typer.Option(None, "--email", "-e", help="Email address for login"),
    password: Optional[str] = typer.Option(None, "--password", "-p", help="Password for login", hide_input=True),
    interactive: bool = typer.Option(False, "--interactive", "-i", help="Open browser for interactive login"),
) -> None:
    """Login to Reuters and save session."""
    try:
        if interactive:
            console.print("[cyan]Opening browser for interactive login...[/]")
            result = interactive_login(headless=False)
        else:
            if not email:
                email = typer.prompt("Email")
            if not password:
                password = typer.prompt("Password", hide_input=True)

            with console.status("[cyan]Logging in...[/]"):
                result = perform_login(email, password, headless=False)

        _show_auth(result)

        if result.status == LoginStatus.LOGGED_IN:
            raise typer.Exit(0)
        else:
            raise typer.Exit(1)

    except KeyboardInterrupt:
        console.print("\n[yellow]Login cancelled.[/]")
        raise typer.Exit(130)


@app.command()
def status() -> None:
    """Check current login status."""
    from datetime import datetime
    from .client import ReutersClient

    state_file = get_state_path(SOURCE_NAME)
    if not state_file.exists():
        result = AuthStatus(
            status=LoginStatus.LOGGED_OUT,
            message="No saved session found. Run 'scraper reuters login' or 'import-cookies' first.",
        )
        _show_auth(result)
        raise typer.Exit(1)

    try:
        with console.status("[cyan]Checking login status...[/]"):
            client = ReutersClient(use_playwright_fallback=False)

            if not client.is_ready():
                result = AuthStatus(
                    status=LoginStatus.LOGGED_OUT,
                    checked_at=datetime.now(),
                    message="No cookies loaded from state file.",
                )
            elif client.check_login_status():
                result = AuthStatus(
                    status=LoginStatus.LOGGED_IN,
                    checked_at=datetime.now(),
                    message="Logged in - Sign In link not visible",
                )
            else:
                result = AuthStatus(
                    status=LoginStatus.LOGGED_OUT,
                    checked_at=datetime.now(),
                    message="Not logged in - Sign In link visible",
                )

        _show_auth(result)

        if result.status == LoginStatus.LOGGED_IN:
            raise typer.Exit(0)
        else:
            raise typer.Exit(1)

    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled.[/]")
        raise typer.Exit(130)


@app.command()
def logout() -> None:
    """Clear saved login session."""
    state_file = get_state_path(SOURCE_NAME)
    if state_file.exists():
        state_file.unlink()
        console.print("[green]Session cleared successfully.[/]")
    else:
        console.print("[dim]No session file found.[/]")


@app.command("import-state")
def import_state(
    path: str = typer.Argument(..., help="Path to state JSON file (from bookmarklet)"),
) -> None:
    """Import browser state from bookmarklet export.

    Use bookmarklet to export: In browser console on reuters.com (logged in), run:

    javascript:(function(){const data={cookies:document.cookie.split(';').map(c=>{const[n,v]=c.trim().split('=');return{name:n,value:v,domain:'.reuters.com',path:'/'}}),origins:[{origin:location.origin,localStorage:Object.entries(localStorage).map(([k,v])=>({name:k,value:v}))}]};const blob=new Blob([JSON.stringify(data,null,2)],{type:'application/json'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='reuters_state.json';a.click();})();

    Or add this as a bookmark and click it on reuters.com.

    Example:
        scraper reuters import-state ~/Downloads/reuters_state.json
    """
    import json
    from pathlib import Path

    state_path = Path(path).expanduser()
    if not state_path.exists():
        console.print(f"[red]File not found: {path}[/]")
        raise typer.Exit(1)

    try:
        data = json.loads(state_path.read_text())
    except Exception as e:
        console.print(f"[red]Failed to parse JSON: {e}[/]")
        raise typer.Exit(1)

    cookies = data.get("cookies", [])
    origins = data.get("origins", [])

    # Normalize cookies
    normalized_cookies = []
    for c in cookies:
        normalized_cookies.append({
            "name": c.get("name", ""),
            "value": c.get("value", ""),
            "domain": c.get("domain", ".reuters.com"),
            "path": c.get("path", "/"),
            "expires": c.get("expires", -1),
            "httpOnly": c.get("httpOnly", False),
            "secure": c.get("secure", False),
            "sameSite": c.get("sameSite", "Lax"),
        })

    state_file = get_state_path(SOURCE_NAME)
    state_file.parent.mkdir(parents=True, exist_ok=True)

    state = {
        "cookies": normalized_cookies,
        "origins": origins
    }

    state_file.write_text(json.dumps(state, indent=2))

    ls_count = sum(len(o.get("localStorage", [])) for o in origins)
    console.print(f"[green]Imported {len(normalized_cookies)} cookies and {ls_count} localStorage items.[/]")
    console.print(f"[dim]Saved to: {state_file}[/]")


@app.command("import-cookies")
def import_cookies(
    path: str = typer.Argument(..., help="Path to cookies file (JSON or Netscape format)"),
    localstorage: Optional[str] = typer.Option(None, "--localstorage", "-l", help="Path to localStorage JSON file"),
) -> None:
    """Import cookies and localStorage from browser export (legacy).

    Supports two formats for cookies:
    1. JSON format (from browser extensions like "Cookie-Editor")
    2. Netscape/Mozilla cookies.txt format (from "cookies.txt" extension)

    For localStorage (required for login):
    - Open browser console on reuters.com
    - Run: copy(JSON.stringify(localStorage))
    - Paste into a file and use --localstorage option

    Example:
        scraper reuters import-cookies ~/Downloads/cookies.json
        scraper reuters import-cookies ~/Downloads/cookies.txt -l ~/Downloads/localstorage.json
    """
    import json
    from pathlib import Path

    cookies_path = Path(path).expanduser()
    if not cookies_path.exists():
        console.print(f"[red]File not found: {path}[/]")
        raise typer.Exit(1)

    content = cookies_path.read_text()

    # Detect format and parse
    cookies = []
    try:
        if content.strip().startswith("[") or content.strip().startswith("{"):
            # JSON format
            data = json.loads(content)
            if isinstance(data, dict):
                data = [data]
            for c in data:
                cookie = {
                    "name": c.get("name", ""),
                    "value": c.get("value", ""),
                    "domain": c.get("domain", ".reuters.com"),
                    "path": c.get("path", "/"),
                    "expires": c.get("expirationDate", c.get("expires", -1)),
                    "httpOnly": c.get("httpOnly", False),
                    "secure": c.get("secure", False),
                    "sameSite": c.get("sameSite", "Lax"),
                }
                if "reuters.com" in cookie["domain"]:
                    cookies.append(cookie)
        else:
            # Netscape cookies.txt format
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) >= 7:
                    domain = parts[0]
                    if "reuters.com" in domain:
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
    except Exception as e:
        console.print(f"[red]Failed to parse cookies: {e}[/]")
        raise typer.Exit(1)

    if not cookies:
        console.print("[yellow]No Reuters cookies found in file.[/]")
        raise typer.Exit(1)

    # Parse localStorage if provided
    local_storage_items = []
    if localstorage:
        ls_path = Path(localstorage).expanduser()
        if not ls_path.exists():
            console.print(f"[red]localStorage file not found: {localstorage}[/]")
            raise typer.Exit(1)
        try:
            ls_data = json.loads(ls_path.read_text())
            if isinstance(ls_data, dict):
                local_storage_items = [{"name": k, "value": v} for k, v in ls_data.items()]
            console.print(f"[green]Parsed {len(local_storage_items)} localStorage items.[/]")
        except Exception as e:
            console.print(f"[red]Failed to parse localStorage: {e}[/]")
            raise typer.Exit(1)

    # Save to state file
    state_file = get_state_path(SOURCE_NAME)
    state_file.parent.mkdir(parents=True, exist_ok=True)

    state = {
        "cookies": cookies,
        "origins": [
            {
                "origin": "https://www.reuters.com",
                "localStorage": local_storage_items
            }
        ] if local_storage_items else []
    }

    state_file.write_text(json.dumps(state, indent=2))
    console.print(f"[green]Imported {len(cookies)} Reuters cookies.[/]")
    if local_storage_items:
        console.print(f"[green]Imported {len(local_storage_items)} localStorage items.[/]")
    console.print(f"[dim]Saved to: {state_file}[/]")


@app.command()
def search(
    query: str = typer.Argument(..., help="Search keywords"),
    limit: int = typer.Option(10, "--limit", "-n", help="Maximum number of results"),
    sort: str = typer.Option("relevance", "--sort", "-s", help="Sort order: relevance or date"),
    section: Optional[str] = typer.Option(None, "--section", help="Filter by section", callback=validate_section),
    date_range: Optional[str] = typer.Option(None, "--date", "-d", help="Filter by date range", callback=validate_date_range),
    browser: bool = typer.Option(False, "--browser", "-b", help="Force browser mode (skip API)"),
    headless: bool = typer.Option(True, "--headless", help="Run browser in headless mode"),
    count_only: bool = typer.Option(False, "--count", "-c", help="Only show total result count"),
    shallow: bool = typer.Option(False, "--shallow", help="Only show search results without fetching details"),
    output: str = typer.Option("./output", "--output", "-o", help="Save results to directory"),
    no_save: bool = typer.Option(False, "--no-save", help="Don't save to files"),
) -> None:
    """Search Reuters for articles by keyword.

    By default uses fast API mode. Use --browser to force Playwright mode.
    """
    import re as regex
    import os
    import json
    from .client import ReutersClient

    state_file = get_state_path(SOURCE_NAME)
    if not state_file.exists():
        console.print("[red]Not logged in. Run 'scraper reuters login' first.[/]")
        raise typer.Exit(1)

    # Try API first (unless --browser is specified)
    api_success = False
    results = []

    if not browser:
        try:
            client = ReutersClient()

            if count_only:
                with console.status("[cyan]Querying API for count...[/]"):
                    total = client.get_search_count(query=query, section=section, date_range=date_range)
                if total is not None:
                    filters = []
                    if section:
                        filters.append(f"section={section}")
                    if date_range:
                        filters.append(f"date={date_range}")
                    filter_str = f" ({', '.join(filters)})" if filters else ""
                    console.print(f"\n[bold]Query:[/] {query}{filter_str}")
                    console.print(f"[bold green]Total results:[/] {total:,}")
                    console.print("[dim](via API)[/]")
                    return
            else:
                with console.status("[cyan]Searching via API...[/]"):
                    results = client.search(
                        query=query,
                        max_results=limit,
                        section=section,
                        date_range=date_range,
                        sort_by=sort,
                    )
                if results:
                    api_success = True
                    console.print("[dim](via API)[/]")
        except Exception as e:
            console.print(f"[yellow]API failed: {e}, falling back to browser...[/]")

    # Fallback to Playwright if API failed
    if not api_success and not count_only:
        try:
            console.print("[cyan]Using browser mode...[/]")
            with create_browser(headless=headless, source=SOURCE_NAME) as page:
                search_scraper = SearchScraper(headless=headless, page=page)

                if count_only:
                    total = search_scraper.get_total_count(query=query, section=section, date_range=date_range, page=page)
                    filters = []
                    if section:
                        filters.append(f"section={section}")
                    if date_range:
                        filters.append(f"date={date_range}")
                    filter_str = f" ({', '.join(filters)})" if filters else ""
                    console.print(f"\n[bold]Query:[/] {query}{filter_str}")
                    console.print(f"[bold green]Total results:[/] {total:,}")
                    return

                results = search_scraper.search(
                    query=query, max_results=limit, section=section,
                    date_range=date_range, sort_by=sort, page=page,
                )
        except CaptchaError as e:
            console.print(f"[yellow]{e}[/]")
            raise typer.Exit(1)
        except KeyboardInterrupt:
            console.print("\n[yellow]Search cancelled.[/]")
            raise typer.Exit(130)

    if not results:
        console.print(f"[yellow]No results found for '{query}'[/]")
        raise typer.Exit(0)

    # Display results using shared display
    rows = []
    for result in results:
        url = result.url if hasattr(result, 'url') else ""
        short_url = url.replace("https://www.reuters.com", "") if url else "-"
        rows.append({
            "title": result.title if hasattr(result, 'title') else str(result),
            "url": short_url,
            "time": (result.published_at if hasattr(result, 'published_at') else "-") or "-",
            "category": (result.category if hasattr(result, 'category') else "-") or "-",
        })

    display_search_results(
        results=rows,
        columns=[
            ColumnDef("Title", "title", style="bold", max_width=40),
            ColumnDef("URL", "url", style="dim", max_width=50),
            ColumnDef("Time", "time", style="green", width=12),
            ColumnDef("Category", "category", style="magenta", width=10),
        ],
        title=f"Search Results: {query}",
        summary=f"Found {len(results)} results",
    )

    if shallow:
        return

    # Fetch article details
    console.print(f"\n[cyan]Fetching article details...[/]")

    save_to_files = output and not no_save
    if save_to_files:
        os.makedirs(output, exist_ok=True)

    articles: List[Article] = []
    import random

    # Use API client for fetching articles too
    client = ReutersClient()

    for i, result in enumerate(results, 1):
        url = result.url if hasattr(result, 'url') else ""
        if not url:
            continue

        try:
            title = result.title if hasattr(result, 'title') else str(result)
            with console.status(f"[cyan]Fetching article {i}/{len(results)}: {title[:40]}...[/]"):
                article = client.fetch_article(url)
                if article:
                    articles.append(article)
                    console.print(f"  [green]✓[/] {article.title[:60]}")
                else:
                    console.print(f"  [yellow]⚠[/] {title[:40]}: No content")

            if i < len(results):
                delay = random.uniform(0.5, 1.5)  # Faster with API
                time.sleep(delay)

        except Exception as e:
            console.print(f"  [red]✗[/] {title[:40]}: {e}")
            continue

    if save_to_files and articles:
        safe_query = regex.sub(r'[^\w\s-]', '', query)[:30].strip()
        safe_query = regex.sub(r'[-\s]+', '-', safe_query)
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{safe_query}_{timestamp}.json"
        filepath = f"{output}/{filename}"

        articles_data = {
            "query": query,
            "fetched_at": datetime.now().isoformat(),
            "total_results": len(results),
            "fetched_articles": len(articles),
            "articles": [article.model_dump() for article in articles],
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(articles_data, f, ensure_ascii=False, indent=2)

        console.print(f"\n[green]Successfully fetched {len(articles)}/{len(results)} articles[/]")
        display_saved(filepath)
    else:
        console.print(f"\n[green]Successfully fetched {len(articles)}/{len(results)} articles[/]")


@app.command()
def fetch(
    url: str = typer.Argument(..., help="Article URL"),
    browser: bool = typer.Option(False, "--browser", "-b", help="Force browser mode (skip API)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Save article to file"),
) -> None:
    """Fetch and display a Reuters article.

    By default uses fast API mode. Use --browser to force Playwright mode.
    """
    from rich.panel import Panel
    from .client import ReutersClient

    state_file = get_state_path(SOURCE_NAME)
    if not state_file.exists():
        console.print("[red]Not logged in. Run 'scraper reuters login' first.[/]")
        raise typer.Exit(1)

    article = None

    # Try API first
    if not browser:
        try:
            with console.status("[cyan]Fetching via API...[/]"):
                client = ReutersClient()
                article = client.fetch_article(url)
            if article:
                console.print("[dim](via API)[/]")
        except Exception as e:
            console.print(f"[yellow]API failed: {e}, falling back to browser...[/]")

    # Fallback to browser
    if not article:
        try:
            console.print("[cyan]Using browser mode...[/]")
            scraper = ArticleScraper(headless=True)
            article = scraper.fetch(url)
        except Exception as e:
            console.print(f"[red]Error fetching article: {e}[/]")
            raise typer.Exit(1)

    if not article:
        console.print("[red]Failed to fetch article[/]")
        raise typer.Exit(1)

    md_content = f"# {article.title}\n\n"
    if article.author:
        md_content += f"**Author:** {article.author}\n\n"
    if article.published_at:
        md_content += f"**Published:** {article.published_at}\n\n"
    md_content += f"**URL:** {article.url}\n\n"
    if article.tags:
        md_content += f"**Tags:** {', '.join(article.tags)}\n\n"
    md_content += "---\n\n"
    md_content += article.content_markdown

    if output:
        with open(output, "w") as f:
            f.write(md_content)
        display_saved(output, description="Article")
    else:
        console.print(Panel(md_content, title=f"[bold]{article.title}[/]", border_style="cyan"))


@app.command()
def browse(
    section_name: str = typer.Argument(..., help="Section slug or 'list'"),
    limit: int = typer.Option(10, "--limit", "-n", help="Maximum number of articles"),
    browser: bool = typer.Option(False, "--browser", "-b", help="Force browser mode (skip API)"),
    headless: bool = typer.Option(True, "--headless", help="Run browser in headless mode"),
    shallow: bool = typer.Option(False, "--shallow", help="Only show article list"),
    output: str = typer.Option("./output", "--output", "-o", help="Save results to directory"),
    no_save: bool = typer.Option(False, "--no-save", help="Don't save to files"),
) -> None:
    """Browse articles from a Reuters section.

    By default uses fast API mode. Use --browser to force Playwright mode.
    """
    import re as regex
    import os
    import json
    from .client import ReutersClient

    if section_name.lower() == "list":
        rows = []
        for slug, info in sorted(SECTIONS.items()):
            rows.append({"slug": slug, "name": info["name"], "url": info["url"]})

        display_options(
            items=rows,
            columns=[
                ColumnDef("Slug", "slug", style="cyan"),
                ColumnDef("Name", "name", style="bold"),
                ColumnDef("URL", "url", style="dim"),
            ],
            title="Available Sections",
        )
        return

    if section_name not in SECTIONS:
        console.print(f"[red]Invalid section: {section_name}[/]")
        console.print(f"[dim]Run 'scraper reuters browse list' to see available sections.[/]")
        raise typer.Exit(1)

    state_file = get_state_path(SOURCE_NAME)
    if not state_file.exists():
        console.print("[red]Not logged in. Run 'scraper reuters login' first.[/]")
        raise typer.Exit(1)

    section_info = SECTIONS[section_name]
    results = []
    api_success = False

    # Try API first
    if not browser:
        try:
            client = ReutersClient()
            with console.status(f"[cyan]Fetching {section_info['name']} via API...[/]"):
                results = client.get_section_articles(section=section_name, max_articles=limit)
            if results:
                api_success = True
                console.print("[dim](via API)[/]")
        except Exception as e:
            console.print(f"[yellow]API failed: {e}, falling back to browser...[/]")

    # Fallback to browser
    if not api_success:
        try:
            console.print("[cyan]Using browser mode...[/]")
            with create_browser(headless=headless, source=SOURCE_NAME) as page:
                section_scraper = SectionScraper(headless=headless, page=page)
                with console.status(f"[cyan]Loading articles (target: {limit})...[/]"):
                    results = section_scraper.list_articles(section=section_name, max_articles=limit, page=page)
        except KeyboardInterrupt:
            console.print("\n[yellow]Cancelled.[/]")
            raise typer.Exit(130)

    if not results:
        console.print(f"[yellow]No articles found in {section_info['name']}[/]")
        raise typer.Exit(0)

    # Display results using shared display
    rows = []
    for result in results:
        url = result.url if hasattr(result, 'url') else ""
        short_url = url.replace("https://www.reuters.com", "") if url else "-"
        if len(short_url) > 40:
            short_url = short_url[:37] + "..."
        rows.append({
            "title": truncate(result.title if hasattr(result, 'title') else str(result), 50),
            "time": (result.published_at if hasattr(result, 'published_at') else "-") or "-",
            "url": short_url,
        })

    display_search_results(
        results=rows,
        columns=[
            ColumnDef("Title", "title", style="bold", max_width=50),
            ColumnDef("Time", "time", style="green", width=12),
            ColumnDef("URL", "url", style="dim", max_width=40),
        ],
        title=f"Section: {section_info['name']}",
        summary=f"Found {len(results)} articles",
    )

    if shallow:
        return

    console.print(f"\n[cyan]Fetching article details...[/]")

    save_to_files = output and not no_save
    if save_to_files:
        os.makedirs(output, exist_ok=True)

    articles: List[Article] = []
    import random

    # Use API client for fetching articles
    client = ReutersClient()

    for i, result in enumerate(results, 1):
        url = result.url if hasattr(result, 'url') else ""
        if not url:
            continue

        try:
            title = result.title if hasattr(result, 'title') else str(result)
            with console.status(f"[cyan]Fetching article {i}/{len(results)}: {title[:40]}...[/]"):
                article = client.fetch_article(url)
                if article:
                    articles.append(article)
                    console.print(f"  [green]✓[/] {article.title[:60]}")
                else:
                    console.print(f"  [yellow]⚠[/] {title[:40]}: No content")

            if i < len(results):
                delay = random.uniform(0.5, 1.5)  # Faster with API
                time.sleep(delay)

        except Exception as e:
            console.print(f"  [red]✗[/] {title[:40]}: {e}")
            continue

    if save_to_files and articles:
        safe_section = regex.sub(r'[^\w\s-]', '_', section_name)
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"section_{safe_section}_{timestamp}.json"
        filepath = f"{output}/{filename}"

        articles_data = {
            "section": section_name,
            "section_name": section_info["name"],
            "fetched_at": datetime.now().isoformat(),
            "total_listed": len(results),
            "fetched_articles": len(articles),
            "articles": [article.model_dump() for article in articles],
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(articles_data, f, ensure_ascii=False, indent=2)

        console.print(f"\n[green]Successfully fetched {len(articles)}/{len(results)} articles[/]")
        display_saved(filepath)
    else:
        console.print(f"\n[green]Successfully fetched {len(articles)}/{len(results)} articles[/]")


# Alias: `section` → `browse`
section = app.command("section", rich_help_panel="Aliases")(browse)


@app.command()
def options() -> None:
    """Show available sections, sort options, and date ranges."""
    # Sections
    section_rows = []
    for slug, info in sorted(SECTIONS.items()):
        section_rows.append({"slug": slug, "name": info["name"]})

    display_options(
        items=section_rows,
        columns=[
            ColumnDef("Slug", "slug", style="cyan"),
            ColumnDef("Name", "name", style="bold"),
        ],
        title="Available Sections",
    )

    # Sort options
    console.print()
    display_options(
        items=[
            {"option": "Sort (--sort)", "values": "relevance, date"},
            {"option": "Date Range (--date)", "values": ", ".join(VALID_DATE_RANGES)},
        ],
        columns=[
            ColumnDef("Option", "option", style="cyan"),
            ColumnDef("Values", "values"),
        ],
        title="Search Options",
    )
