"""CLI commands for Google Scholar scraper."""
import json
import re
import time
from pathlib import Path
from typing import Optional

import typer
from rich.progress import Progress, SpinnerColumn, TextColumn

from ...core.display import (
    ColumnDef,
    console,
    display_options,
    display_saved,
)
from ...core.storage import JSONStorage
from .config import SOURCE_NAME, SEARCH_SORT, SEARCH_LANGUAGES, RATE_LIMIT
from .cookies import (
    load_cookies,
    import_cookies as do_import_cookies,
    check_cookies_valid_sync,
    get_cookies_path,
)
from .scrapers import SearchScraper, ArticleScraper

def _safe_filename(text: str) -> str:
    """Sanitize text into a safe filename slug."""
    # Replace / and \ with _
    slug = text.replace("/", "_").replace("\\", "_")
    # Remove or replace characters unsafe for filenames
    slug = re.sub(r'[<>:"|?*\s]+', "_", slug)
    # Collapse multiple underscores
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug[:80] or "untitled"


app = typer.Typer(
    name=SOURCE_NAME,
    help="Google Scholar scraping commands.",
    no_args_is_help=True,
)


# =============================================================================
# Cookie Management (optional)
# =============================================================================


@app.command("import-cookies")
def import_cookies(
    source: Path = typer.Argument(..., help="Source cookies.txt file"),
) -> None:
    """Import Google cookies.txt to reduce CAPTCHA frequency."""
    try:
        dest = do_import_cookies(source)
        console.print(f"[green]✓[/green] Cookies imported to {dest}")
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@app.command()
def status(
    cookies_file: Optional[Path] = typer.Option(
        None, "--cookies", "-c", help="Path to cookies.txt file"
    ),
) -> None:
    """Check that cookies are working for Google Scholar."""
    cookies_path = cookies_file or get_cookies_path()

    if not cookies_path.exists():
        console.print("[yellow]No cookies file found[/yellow]")
        console.print("Scholar works without cookies, but cookies can reduce CAPTCHA frequency.")
        console.print(f"To import: scraper {SOURCE_NAME} import-cookies <path>")
        return

    cookies = load_cookies(cookies_path)
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


# Alias: `check-cookies` → `status`
check_cookies = app.command("check-cookies", rich_help_panel="Aliases")(status)


# =============================================================================
# Options
# =============================================================================


@app.command()
def options() -> None:
    """Show available search filter options."""
    filter_rows = [
        {"option": "Sort (--sort)", "values": ", ".join(SEARCH_SORT.keys())},
        {"option": "Language (--lang)", "values": ", ".join(SEARCH_LANGUAGES.keys())},
        {"option": "Year From (--year-from)", "values": "e.g. 2020"},
        {"option": "Year To (--year-to)", "values": "e.g. 2024"},
    ]
    display_options(
        items=filter_rows,
        columns=[
            ColumnDef("Option", "option", style="cyan"),
            ColumnDef("Values", "values"),
        ],
        title="Search Options",
    )


# Alias: `search-options` → `options`
search_options = app.command("search-options", rich_help_panel="Aliases")(options)


# =============================================================================
# Search
# =============================================================================


def validate_sort(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if value not in SEARCH_SORT:
        raise typer.BadParameter(f"Must be one of: {', '.join(SEARCH_SORT.keys())}")
    return value


def validate_lang(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    if value not in SEARCH_LANGUAGES:
        raise typer.BadParameter(f"Must be one of: {', '.join(SEARCH_LANGUAGES.keys())}")
    return value


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    pages: int = typer.Option(1, "--pages", "-p", help="Number of pages to search"),
    limit: Optional[int] = typer.Option(None, "--limit", "-n", help="Max results to show"),
    sort: Optional[str] = typer.Option(None, "--sort", help="Sort: relevance, date", callback=validate_sort),
    year_from: Optional[int] = typer.Option(None, "--year-from", help="Papers from this year"),
    year_to: Optional[int] = typer.Option(None, "--year-to", help="Papers up to this year"),
    lang: Optional[str] = typer.Option(None, "--lang", help="Language filter (e.g. en, zh)", callback=validate_lang),
    shallow: bool = typer.Option(False, "--shallow", "-s", help="Only show search results without fetching content"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Disable Playwright browser fallback for content fetching"),
    delay: float = typer.Option(2.0, "--delay", "-d", help="Delay between requests (seconds)"),
    cookies_file: Optional[Path] = typer.Option(None, "--cookies", "-c", help="Path to cookies.txt"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Save results to JSON file"),
) -> None:
    """Search Google Scholar for academic papers.

    By default fetches full article content from publisher pages.
    Use --shallow to only show search results without content.

    Fetch strategy: curl-cffi -> httpx -> Playwright (headless Chrome).
    Use --no-browser to disable Playwright fallback.

    Filter options:
      --sort: relevance (default), date
      --year-from/--year-to: Year range filter
      --lang: Language filter (en, zh, ja, etc.)
    """
    search_scraper = SearchScraper(cookies_file)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task(f"Searching Scholar for '{query}'...", total=None)
        results = search_scraper.search_multi_pages(
            query,
            max_pages=pages,
            sort=sort,
            year_lo=year_from,
            year_hi=year_to,
            lang=lang,
        )

    if not results:
        console.print("[yellow]No results found[/yellow]")
        return

    if limit:
        results = results[:limit]

    console.print(f"\n[bold]Found {len(results)} results[/bold]\n")

    # Shallow mode: only show search results
    if shallow:
        for i, r in enumerate(results, 1):
            year_str = f" ({r.year})" if r.year else ""
            cited_str = f" [dim]Cited by {r.cited_by_count}[/dim]" if r.cited_by_count else ""
            pdf_str = " [green][PDF][/green]" if r.has_pdf else ""

            console.print(f"[cyan]{i:2}.[/cyan] [bold]{r.title}[/bold]{year_str}{pdf_str}")
            if r.authors:
                console.print(f"     [dim]{r.authors}[/dim]")
            if r.snippet:
                console.print(f"     {r.snippet[:150]}...")
            console.print(f"     {cited_str}")
            if r.url:
                console.print(f"     [dim]{r.url}[/dim]")
            console.print()

        if output:
            data = [r.model_dump(mode="json") for r in results]
            with open(output, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            display_saved(output)
        return

    # Full mode: fetch article content from publisher pages
    article_scraper = ArticleScraper(cookies_file, use_playwright=not no_browser)
    storage = JSONStorage(source=SOURCE_NAME)
    articles = []
    success_count = 0
    fail_count = 0

    for i, result in enumerate(results, 1):
        if not result.url or result.is_citation:
            console.print(f"[{i}/{len(results)}] [dim]Skipping (no URL): {result.title[:50]}[/dim]")
            continue

        console.print(f"[{i}/{len(results)}] {result.title[:60]}...")

        try:
            article = article_scraper.scrape(result.url)

            if article.is_pdf:
                console.print("  [yellow]⚠ PDF (skipped)[/yellow]")
            elif article.content:
                articles.append(article)
                console.print(f"  [green]✓[/green] {len(article.content)} chars")
                success_count += 1
            else:
                console.print("  [yellow]⚠ No content extracted[/yellow]")
                fail_count += 1

        except Exception as e:
            console.print(f"  [red]✗[/red] {e}")
            fail_count += 1

        if i < len(results):
            time.sleep(delay)

    console.print(
        f"\n[bold]Summary:[/bold] [green]{success_count}[/green] success, "
        f"[red]{fail_count}[/red] failed"
    )

    if output and articles:
        data = [a.model_dump(mode="json") for a in articles]
        with open(output, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        display_saved(output, description="Articles")
    elif articles:
        for article in articles:
            slug = _safe_filename(article.doi or article.title or "untitled")
            filename = f"{slug}.json"
            storage.save(
                article.model_dump(mode="json"),
                filename,
                description="article",
                silent=True,
            )
        console.print(f"[dim]Articles saved to: {storage.output_dir}[/dim]")


# =============================================================================
# Article Fetching
# =============================================================================


@app.command()
def fetch(
    url: str = typer.Argument(..., help="Article URL to scrape"),
    cookies_file: Optional[Path] = typer.Option(
        None, "--cookies", "-c", help="Path to cookies.txt file"
    ),
    no_browser: bool = typer.Option(False, "--no-browser", help="Disable Playwright browser fallback"),
    save: bool = typer.Option(True, "--save/--no-save", help="Save to data directory"),
    output: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
) -> None:
    """Fetch full content from a publisher article URL.

    Fetch strategy: curl-cffi -> httpx -> Playwright (headless Chrome).
    Use --no-browser to disable Playwright fallback.
    """
    scraper = ArticleScraper(cookies_file, use_playwright=not no_browser)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("Fetching article...", total=None)
        try:
            article = scraper.scrape(url)
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)

    # Display article
    if article.title:
        console.print(f"\n[bold]{article.title}[/bold]")
    if article.authors:
        console.print(f"[dim]By {', '.join(article.authors)}[/dim]")
    if article.journal:
        console.print(f"[dim]Journal: {article.journal}[/dim]")
    if article.doi:
        console.print(f"[dim]DOI: {article.doi}[/dim]")
    if article.published_date:
        console.print(f"[dim]Published: {article.published_date}[/dim]")

    if article.is_pdf:
        console.print("\n[yellow]⚠ PDF file - content extraction not supported[/yellow]")
    elif article.abstract:
        console.print(f"\n[italic]Abstract:[/italic] {article.abstract[:300]}...")

    if article.content and not article.is_pdf:
        preview = article.content[:500]
        if len(article.content) > 500:
            preview += "..."
        console.print(f"\n{preview}")
        console.print(f"\n[dim]({len(article.content)} chars)[/dim]")

    if not article.is_accessible:
        console.print("\n[yellow]⚠ Full content not accessible - showing available metadata only[/yellow]")

    # Save
    if save or output:
        storage = JSONStorage(source=SOURCE_NAME)
        data = article.model_dump(mode="json")

        if output:
            with open(output, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            display_saved(output, description="Article")
        else:
            slug = _safe_filename(article.doi or article.title or "untitled")
            filename = f"{slug}.json"
            save_path = storage.save(data, filename, description="article")
            display_saved(save_path, description="Article")


if __name__ == "__main__":
    app()
