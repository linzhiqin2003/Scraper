"""CLI interface for Reuters scraper."""

import time
from typing import List, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ...core.browser import create_browser, load_cookies_sync, get_state_path
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
console = Console()


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


def status_style(status: LoginStatus) -> str:
    """Get Rich style for login status."""
    styles = {
        LoginStatus.LOGGED_IN: "bold green",
        LoginStatus.LOGGED_OUT: "bold red",
        LoginStatus.SESSION_EXPIRED: "bold yellow",
        LoginStatus.UNKNOWN: "bold dim",
    }
    return styles.get(status, "")


def display_auth_status(auth: AuthStatus) -> None:
    """Display authentication status with Rich formatting."""
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Key", style="dim")
    table.add_column("Value")

    status_text = auth.status.value.replace("_", " ").title()
    table.add_row("Status", f"[{status_style(auth.status)}]{status_text}[/]")

    if auth.email:
        table.add_row("Email", auth.email)

    if auth.checked_at:
        table.add_row("Checked at", auth.checked_at.strftime("%Y-%m-%d %H:%M:%S"))

    if auth.message:
        table.add_row("Message", auth.message)

    state_file = get_state_path(SOURCE_NAME)
    session_status = "[green]exists[/]" if state_file.exists() else "[dim]not found[/]"
    table.add_row("Session file", session_status)

    console.print(Panel(table, title="[bold]Reuters Login Status[/]", border_style="blue"))


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

        display_auth_status(result)

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
    state_file = get_state_path(SOURCE_NAME)
    if not state_file.exists():
        result = AuthStatus(
            status=LoginStatus.LOGGED_OUT,
            message="No saved session found. Run 'scraper reuters login' first.",
        )
        display_auth_status(result)
        raise typer.Exit(1)

    try:
        with console.status("[cyan]Checking login status...[/]"):
            with create_browser(headless=True, source=SOURCE_NAME) as page:
                page.goto("https://www.reuters.com")
                load_cookies_sync(page, SOURCE_NAME)
                page.reload()
                result = check_login_status(page)

        display_auth_status(result)

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


@app.command()
def search(
    query: str = typer.Argument(..., help="Search keywords"),
    limit: int = typer.Option(10, "--limit", "-n", help="Maximum number of results"),
    sort: str = typer.Option("relevance", "--sort", "-s", help="Sort order: relevance or date"),
    section: Optional[str] = typer.Option(None, "--section", help="Filter by section", callback=validate_section),
    date_range: Optional[str] = typer.Option(None, "--date", "-d", help="Filter by date range", callback=validate_date_range),
    headless: bool = typer.Option(False, "--headless", help="Run browser in headless mode"),
    count_only: bool = typer.Option(False, "--count", "-c", help="Only show total result count"),
    shallow: bool = typer.Option(False, "--shallow", help="Only show search results without fetching details"),
    output: str = typer.Option("./output", "--output", "-o", help="Save results to directory"),
    no_save: bool = typer.Option(False, "--no-save", help="Don't save to files"),
) -> None:
    """Search Reuters for articles by keyword."""
    import re as regex
    import os
    import json

    state_file = get_state_path(SOURCE_NAME)
    if not state_file.exists():
        console.print("[red]Not logged in. Run 'scraper reuters login' first.[/]")
        raise typer.Exit(1)

    try:
        if not headless:
            console.print("[cyan]Opening browser for search...[/]")

        with create_browser(headless=headless, source=SOURCE_NAME) as page:
            page.goto("https://www.reuters.com")
            load_cookies_sync(page, SOURCE_NAME)
            page.reload()

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

            article_scraper = ArticleScraper(headless=headless, page=page)

            results = search_scraper.search(
                query=query, max_results=limit, section=section,
                date_range=date_range, sort_by=sort, page=page,
            )

            if not results:
                console.print(f"[yellow]No results found for '{query}'[/]")
                raise typer.Exit(0)

            table = Table(title=f"Search Results: {query}", show_lines=True)
            table.add_column("#", style="dim", width=3)
            table.add_column("Title", style="bold", max_width=40)
            table.add_column("URL", style="blue", max_width=50)
            table.add_column("Time", style="cyan", width=12)
            table.add_column("Category", style="green", width=10)

            for i, result in enumerate(results, 1):
                short_url = result.url.replace("https://www.reuters.com", "") if result.url else "-"
                table.add_row(str(i), result.title, short_url, result.published_at or "-", result.category or "-")

            console.print(table)
            console.print(f"\n[dim]Found {len(results)} results[/]")

            if shallow:
                return

            console.print(f"\n[cyan]Fetching article details...[/]")

            save_to_files = output and not no_save
            if save_to_files:
                os.makedirs(output, exist_ok=True)

            articles: List[Article] = []
            import random

            for i, result in enumerate(results, 1):
                if not result.url:
                    continue

                try:
                    with console.status(f"[cyan]Fetching article {i}/{len(results)}: {result.title[:40]}...[/]"):
                        article = article_scraper.fetch(result.url, page=page)
                        articles.append(article)
                        console.print(f"  [green]✓[/] {article.title[:60]}")

                    if i < len(results):
                        delay = random.uniform(2.0, 4.0)
                        time.sleep(delay)

                except Exception as e:
                    console.print(f"  [red]✗[/] {result.title[:40]}: {e}")
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
                console.print(f"[dim]Saved to {filepath}[/]")
            else:
                console.print(f"\n[green]Successfully fetched {len(articles)}/{len(results)} articles[/]")

    except CaptchaError as e:
        console.print(f"[yellow]{e}[/]")
        raise typer.Exit(1)

    except KeyboardInterrupt:
        console.print("\n[yellow]Search cancelled.[/]")
        raise typer.Exit(130)


@app.command()
def fetch(
    url: str = typer.Argument(..., help="Article URL"),
    headless: bool = typer.Option(False, "--headless", help="Run browser in headless mode"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Save article to file"),
) -> None:
    """Fetch and display a Reuters article."""
    state_file = get_state_path(SOURCE_NAME)
    if not state_file.exists():
        console.print("[red]Not logged in. Run 'scraper reuters login' first.[/]")
        raise typer.Exit(1)

    try:
        scraper = ArticleScraper(headless=headless)
        article = scraper.fetch(url)

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
            console.print(f"[green]Article saved to {output}[/]")
        else:
            console.print(Panel(md_content, title=f"[bold]{article.title}[/]", border_style="blue"))

    except Exception as e:
        console.print(f"[red]Error fetching article: {e}[/]")
        raise typer.Exit(1)


@app.command()
def section(
    section_name: str = typer.Argument(..., help="Section slug or 'list'"),
    limit: int = typer.Option(10, "--limit", "-n", help="Maximum number of articles"),
    headless: bool = typer.Option(False, "--headless", help="Run browser in headless mode"),
    shallow: bool = typer.Option(False, "--shallow", help="Only show article list"),
    output: str = typer.Option("./output", "--output", "-o", help="Save results to directory"),
    no_save: bool = typer.Option(False, "--no-save", help="Don't save to files"),
) -> None:
    """Browse articles from a Reuters section."""
    import re as regex
    import os
    import json

    if section_name.lower() == "list":
        table = Table(title="Available Sections", show_lines=False)
        table.add_column("Slug", style="cyan")
        table.add_column("Name", style="bold")
        table.add_column("URL", style="dim")

        for slug, info in sorted(SECTIONS.items()):
            table.add_row(slug, info["name"], info["url"])

        console.print(table)
        return

    if section_name not in SECTIONS:
        console.print(f"[red]Invalid section: {section_name}[/]")
        console.print(f"[dim]Run 'scraper reuters section list' to see available sections.[/]")
        raise typer.Exit(1)

    state_file = get_state_path(SOURCE_NAME)
    if not state_file.exists():
        console.print("[red]Not logged in. Run 'scraper reuters login' first.[/]")
        raise typer.Exit(1)

    try:
        section_info = SECTIONS[section_name]
        console.print(f"[cyan]Fetching articles from {section_info['name']}...[/]")

        with create_browser(headless=headless, source=SOURCE_NAME) as page:
            page.goto("https://www.reuters.com")
            load_cookies_sync(page, SOURCE_NAME)
            page.reload()

            section_scraper = SectionScraper(headless=headless, page=page)
            article_scraper = ArticleScraper(headless=headless, page=page)

            with console.status(f"[cyan]Loading articles (target: {limit})...[/]"):
                results = section_scraper.list_articles(section=section_name, max_articles=limit, page=page)

            if not results:
                console.print(f"[yellow]No articles found in {section_info['name']}[/]")
                raise typer.Exit(0)

            table = Table(title=f"Section: {section_info['name']}", show_lines=True)
            table.add_column("#", style="dim", width=3)
            table.add_column("Title", style="bold", max_width=50)
            table.add_column("Time", style="cyan", width=12)
            table.add_column("URL", style="blue", max_width=40)

            for i, result in enumerate(results, 1):
                short_url = result.url.replace("https://www.reuters.com", "") if result.url else "-"
                if len(short_url) > 40:
                    short_url = short_url[:37] + "..."
                table.add_row(
                    str(i),
                    result.title[:50] + ("..." if len(result.title) > 50 else ""),
                    result.published_at or "-",
                    short_url,
                )

            console.print(table)
            console.print(f"\n[dim]Found {len(results)} articles[/]")

            if shallow:
                return

            console.print(f"\n[cyan]Fetching article details...[/]")

            save_to_files = output and not no_save
            if save_to_files:
                os.makedirs(output, exist_ok=True)

            articles: List[Article] = []
            import random

            for i, result in enumerate(results, 1):
                if not result.url:
                    continue

                try:
                    with console.status(f"[cyan]Fetching article {i}/{len(results)}: {result.title[:40]}...[/]"):
                        article = article_scraper.fetch(result.url, page=page)
                        articles.append(article)
                        console.print(f"  [green]✓[/] {article.title[:60]}")

                    if i < len(results):
                        delay = random.uniform(2.0, 4.0)
                        time.sleep(delay)

                except Exception as e:
                    console.print(f"  [red]✗[/] {result.title[:40]}: {e}")
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
                console.print(f"[dim]Saved to {filepath}[/]")
            else:
                console.print(f"\n[green]Successfully fetched {len(articles)}/{len(results)} articles[/]")

    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled.[/]")
        raise typer.Exit(130)
