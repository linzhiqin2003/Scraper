"""CLI commands for WSJ scraper."""
import asyncio
import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from ...core.storage import JSONStorage
from .config import SOURCE_NAME, FEEDS
from .cookies import (
    load_cookies,
    validate_cookies,
    check_cookies_valid_sync,
    get_cookies_path,
)
from .scrapers import ArticleScraper, SearchScraper, FeedScraper

app = typer.Typer(
    name=SOURCE_NAME,
    help="Wall Street Journal scraping commands.",
    no_args_is_help=True,
)
console = Console()


# =============================================================================
# Cookie Management
# =============================================================================


@app.command("check-cookies")
def check_cookies(
    cookies_file: Optional[Path] = typer.Option(
        None, "--cookies", "-c", help="Path to cookies.txt file"
    ),
) -> None:
    """Verify that cookies are valid for WSJ access."""
    cookies_path = cookies_file or get_cookies_path()

    try:
        cookies = load_cookies(cookies_path)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        console.print("\n[yellow]To export cookies:[/yellow]")
        console.print("1. Install browser extension 'cookies.txt'")
        console.print("2. Log in to wsj.com")
        console.print(f"3. Export cookies to '{cookies_path}'")
        raise typer.Exit(1)

    if not validate_cookies(cookies):
        console.print("[yellow]Warning:[/yellow] No WSJ auth cookies detected")

    cookie_count = len(list(cookies.jar))
    console.print(f"Loaded [green]{cookie_count}[/green] cookies from {cookies_path}")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("Checking cookies online...", total=None)
        is_valid, message = check_cookies_valid_sync(cookies)

    if is_valid:
        console.print(f"[green]✓[/green] {message}")
    else:
        console.print(f"[red]✗[/red] {message}")
        raise typer.Exit(1)


@app.command("import-cookies")
def import_cookies(
    source: Path = typer.Argument(..., help="Source cookies.txt file"),
) -> None:
    """Import cookies.txt to the standard location."""
    if not source.exists():
        console.print(f"[red]Error:[/red] File not found: {source}")
        raise typer.Exit(1)

    dest = get_cookies_path()
    dest.parent.mkdir(parents=True, exist_ok=True)

    import shutil

    shutil.copy(source, dest)
    console.print(f"[green]✓[/green] Cookies imported to {dest}")


# =============================================================================
# RSS Feeds
# =============================================================================


@app.command()
def categories() -> None:
    """List available RSS feed categories."""
    table = Table(title="Available Categories")
    table.add_column("Category", style="cyan")
    table.add_column("Feed URL", style="dim")

    for name, url in FEEDS.items():
        table.add_row(name, url)

    console.print(table)


@app.command()
def feeds(
    category: Optional[str] = typer.Option(
        None, "--category", "-c", help="Filter by category"
    ),
    limit: int = typer.Option(20, "--limit", "-n", help="Maximum articles to show"),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Save to JSON file"
    ),
) -> None:
    """Fetch articles from RSS feeds."""
    if category and category not in FEEDS:
        console.print(f"[red]Error:[/red] Unknown category '{category}'")
        console.print(f"Available: {', '.join(FEEDS.keys())}")
        raise typer.Exit(1)

    scraper = FeedScraper()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("Fetching RSS feeds...", total=None)
        response = scraper.fetch(category)

    articles = response.articles[:limit]

    if not articles:
        console.print("[yellow]No articles found[/yellow]")
        return

    for i, article in enumerate(articles, 1):
        date_str = article.published_at.strftime("%m/%d %H:%M")
        console.print(f"[dim]{i:2}. {date_str}[/dim] [cyan]{article.category}[/cyan]")
        console.print(f"    [bold]{article.title}[/bold]")
        console.print(f"    [dim]{article.url}[/dim]\n")

    if output:
        data = [a.model_dump(mode="json") for a in articles]
        with open(output, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        console.print(f"[green]Saved to:[/green] {output}")


# =============================================================================
# Search
# =============================================================================


def validate_sort(value: Optional[str]) -> Optional[str]:
    """Validate sort option."""
    if value is None:
        return None
    valid = ["newest", "oldest", "relevance"]
    if value not in valid:
        raise typer.BadParameter(f"Must be one of: {', '.join(valid)}")
    return value


def validate_date_range(value: Optional[str]) -> Optional[str]:
    """Validate date range option."""
    if value is None:
        return None
    valid = ["day", "week", "month", "year", "all"]
    if value not in valid:
        raise typer.BadParameter(f"Must be one of: {', '.join(valid)}")
    return value


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    pages: int = typer.Option(1, "--pages", "-p", help="Number of pages to search"),
    limit: Optional[int] = typer.Option(None, "--limit", "-n", help="Max articles to scrape"),
    sort: Optional[str] = typer.Option(None, "--sort", help="Sort: newest, oldest, relevance", callback=validate_sort),
    date_range: Optional[str] = typer.Option(None, "--date", help="Date: day, week, month, year, all", callback=validate_date_range),
    sources: Optional[str] = typer.Option(None, "--sources", help="Sources: articles,video,audio,livecoverage,buyside (comma-separated)"),
    shallow: bool = typer.Option(False, "--shallow", "-s", help="Only show URLs without scraping content"),
    delay: float = typer.Option(1.0, "--delay", "-d", help="Delay between requests (seconds)"),
    cookies_file: Optional[Path] = typer.Option(None, "--cookies", "-c", help="Path to cookies.txt"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Save results to JSON file"),
) -> None:
    """Search WSJ articles and scrape full content.

    By default scrapes all article content. Use --shallow to only show URLs.

    Filter options:
      --sort: newest (default), oldest, relevance
      --date: day, week, month, year, all (default)
      --sources: articles, video, audio, livecoverage, buyside (comma-separated)
    """
    try:
        search_scraper = SearchScraper(cookies_file)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        console.print(f"Run 'scraper {SOURCE_NAME} import-cookies <path>' first")
        raise typer.Exit(1)

    # Parse sources
    source_list = None
    if sources:
        source_list = [s.strip() for s in sources.split(",")]

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task(f"Searching '{query}'...", total=None)
        results = search_scraper.search_multi_pages(
            query,
            max_pages=pages,
            sort=sort,
            date_range=date_range,
            sources=source_list,
        )

    if not results:
        console.print("[yellow]No results found[/yellow]")
        return

    if limit:
        results = results[:limit]

    console.print(f"\n[bold]Found {len(results)} articles[/bold]\n")

    # Shallow mode: only show URLs
    if shallow:
        for i, r in enumerate(results, 1):
            category = f"[dim][{r.category}][/dim] " if r.category else ""
            console.print(f"[cyan]{i:2}.[/cyan] {category}[bold]{r.headline}[/bold]")
            if r.author:
                console.print(f"     [dim]By {r.author}[/dim]")
            console.print(f"     [dim]{r.url}[/dim]\n")

        if output:
            data = [r.model_dump(mode="json") for r in results]
            with open(output, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            console.print(f"[green]Results saved to:[/green] {output}")
        return

    # Full mode: scrape article content
    try:
        article_scraper = ArticleScraper(cookies_file)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    import time
    storage = JSONStorage(source=SOURCE_NAME)
    articles = []
    success_count = 0
    fail_count = 0

    for i, result in enumerate(results, 1):
        console.print(f"[{i}/{len(results)}] {result.headline[:50]}...")

        try:
            article = article_scraper.scrape(result.url)

            if article.is_paywalled:
                console.print("  [yellow]⚠ Paywalled[/yellow]")
                fail_count += 1
            else:
                articles.append(article)
                console.print(f"  [green]✓[/green] {article.title[:50]}")
                success_count += 1

        except Exception as e:
            console.print(f"  [red]✗[/red] {e}")
            fail_count += 1

        if i < len(results):
            time.sleep(delay)

    console.print(
        f"\n[bold]Summary:[/bold] [green]{success_count}[/green] success, "
        f"[red]{fail_count}[/red] failed"
    )

    # Save results
    if output and articles:
        data = [a.model_dump(mode="json") for a in articles]
        with open(output, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        console.print(f"[green]Articles saved to:[/green] {output}")
    elif articles:
        # Save to default storage
        for article in articles:
            filename = f"{article.article_id}.json"
            storage.save(
                article.model_dump(mode="json"),
                filename,
                description="article",
                silent=True,
            )
        console.print(f"[dim]Articles saved to: {storage.data_dir}[/dim]")


# =============================================================================
# Article Scraping
# =============================================================================


@app.command()
def fetch(
    url: str = typer.Argument(..., help="Article URL to scrape"),
    cookies_file: Optional[Path] = typer.Option(
        None, "--cookies", "-c", help="Path to cookies.txt file"
    ),
    save: bool = typer.Option(True, "--save/--no-save", help="Save to data directory"),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
) -> None:
    """Scrape full content from a WSJ article URL."""
    try:
        scraper = ArticleScraper(cookies_file)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        console.print(f"Run 'scraper {SOURCE_NAME} import-cookies <path>' first")
        raise typer.Exit(1)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("Scraping article...", total=None)
        try:
            article = scraper.scrape(url)
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)

    # Display article
    console.print(f"\n[bold]{article.title}[/bold]")
    if article.subtitle:
        console.print(f"[italic]{article.subtitle}[/italic]")
    if article.author:
        console.print(f"[dim]By {article.author}[/dim]")
    if article.category:
        cat_str = article.category
        if article.subcategory:
            cat_str += f" > {article.subcategory}"
        console.print(f"[dim]Category: {cat_str}[/dim]")
    if article.published_at:
        console.print(f"[dim]Published: {article.published_at.strftime('%Y-%m-%d %H:%M %Z')}[/dim]")

    if article.is_paywalled:
        console.print("\n[yellow]⚠ Article is paywalled - content may be incomplete[/yellow]")

    if article.content:
        preview = article.content[:500]
        if len(article.content) > 500:
            preview += "..."
        console.print(f"\n{preview}")
        console.print(
            f"\n[dim]({len(article.content)} chars, {len(article.paragraphs)} paragraphs)[/dim]"
        )
    else:
        console.print("[yellow]No content extracted[/yellow]")

    # Save
    if save or output:
        storage = JSONStorage(source=SOURCE_NAME)

        if output:
            save_path = output
        else:
            filename = f"{article.article_id}.json"
            save_path = storage.save(
                article.model_dump(mode="json"),
                filename,
                description="article",
            )

        if output:
            with open(output, "w", encoding="utf-8") as f:
                json.dump(article.model_dump(mode="json"), f, ensure_ascii=False, indent=2)

        console.print(f"\n[green]Saved to:[/green] {save_path}")


@app.command("scrape-feeds")
def scrape_feeds(
    category: Optional[str] = typer.Option(
        None, "--category", "-c", help="Filter by category"
    ),
    limit: int = typer.Option(5, "--limit", "-n", help="Maximum articles to scrape"),
    cookies_file: Optional[Path] = typer.Option(
        None, "--cookies", help="Path to cookies.txt file"
    ),
    delay: float = typer.Option(
        1.5, "--delay", "-d", help="Delay between requests (seconds)"
    ),
) -> None:
    """Fetch RSS feeds and scrape full article content."""
    # Fetch RSS
    feed_scraper = FeedScraper()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("Fetching RSS feeds...", total=None)
        response = feed_scraper.fetch(category)

    articles = response.articles[:limit]

    if not articles:
        console.print("[yellow]No articles found[/yellow]")
        return

    console.print(f"Found [cyan]{len(articles)}[/cyan] articles, scraping full content...\n")

    # Scrape full content
    try:
        article_scraper = ArticleScraper(cookies_file)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        console.print(f"Run 'scraper {SOURCE_NAME} import-cookies <path>' first")
        raise typer.Exit(1)

    storage = JSONStorage(source=SOURCE_NAME)
    success_count = 0
    fail_count = 0

    import time

    for i, feed_article in enumerate(articles, 1):
        console.print(f"[{i}/{len(articles)}] {feed_article.title[:50]}...")

        try:
            full_article = article_scraper.scrape(feed_article.url)

            if full_article.is_paywalled:
                console.print("  [yellow]⚠ Paywalled[/yellow]")
                fail_count += 1
            else:
                filename = f"{full_article.article_id}.json"
                filepath = storage.save(
                    full_article.model_dump(mode="json"),
                    filename,
                    description="article",
                    silent=True,
                )
                console.print(f"  [green]✓[/green] {filepath}")
                success_count += 1

        except Exception as e:
            console.print(f"  [red]✗[/red] {e}")
            fail_count += 1

        if i < len(articles):
            time.sleep(delay)

    console.print(
        f"\n[bold]Done:[/bold] [green]{success_count}[/green] success, "
        f"[red]{fail_count}[/red] failed"
    )


if __name__ == "__main__":
    app()
