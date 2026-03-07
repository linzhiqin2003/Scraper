"""CLI commands for Google Custom Search source."""
import json
import re
import time
from typing import Optional

import typer
from rich.progress import Progress, SpinnerColumn, TextColumn

from ...core.display import ColumnDef, console, display_options, display_saved
from ...core.storage import JSONStorage
from .config import (
    SOURCE_NAME,
    DATE_RESTRICT,
    SORT_OPTIONS,
    LANGUAGES,
    SAFE_SEARCH,
    SEARCH_TYPES,
    get_api_key,
    get_cx,
    is_configured,
)
from .scrapers import SearchScraper, ArticleFetcher


def _safe_filename(text: str) -> str:
    slug = re.sub(r'[<>:"/\\|?*\s]+', "_", text)
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug[:80] or "untitled"


app = typer.Typer(
    name=SOURCE_NAME,
    help="Google Custom Search commands (via CSE API).",
    no_args_is_help=True,
)


# =============================================================================
# Status
# =============================================================================


@app.command()
def status() -> None:
    """Check Google CSE API configuration."""
    api_key = get_api_key()
    cx = get_cx()

    if not api_key:
        console.print("[red]✗[/red] GOOGLE_CSE_API_KEY not set")
        console.print(
            "Get an API key at [link=https://console.cloud.google.com]"
            "https://console.cloud.google.com[/link]"
        )
    else:
        masked = api_key[:4] + "..." + api_key[-4:] if len(api_key) > 8 else "****"
        console.print(f"[green]✓[/green] GOOGLE_CSE_API_KEY configured: [dim]{masked}[/dim]")

    if not cx:
        console.print("[red]✗[/red] GOOGLE_CSE_CX not set")
        console.print(
            "Create a search engine at [link=https://programmablesearchengine.google.com]"
            "https://programmablesearchengine.google.com[/link]"
        )
    else:
        masked_cx = cx[:4] + "..." + cx[-4:] if len(cx) > 8 else cx
        console.print(f"[green]✓[/green] GOOGLE_CSE_CX configured: [dim]{masked_cx}[/dim]")

    if not is_configured():
        return

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("Testing API...", total=None)
        try:
            scraper = SearchScraper()
            resp = scraper.search("test", num=1)
            console.print(
                f"[green]✓[/green] API working — "
                f"{len(resp.results)} result(s)"
                + (f", ~{resp.total_results:,} total" if resp.total_results else "")
            )
        except Exception as e:
            console.print(f"[red]✗[/red] API test failed: {e}")


# =============================================================================
# Options
# =============================================================================


@app.command()
def options() -> None:
    """Show available search options."""
    display_options(
        items=[
            {"option": "Date Restrict (--date-restrict)", "values": ", ".join(DATE_RESTRICT.keys())},
            {"option": "Sort (--sort)", "values": ", ".join(SORT_OPTIONS.keys())},
            {"option": "Language (--lang)", "values": ", ".join(LANGUAGES.keys())},
            {"option": "Safe Search (--safe)", "values": ", ".join(SAFE_SEARCH.keys())},
            {"option": "Search Type (--type)", "values": ", ".join(SEARCH_TYPES.keys())},
        ],
        columns=[
            ColumnDef("Option", "option", style="cyan"),
            ColumnDef("Values", "values"),
        ],
        title="Google Custom Search Options",
    )
    console.print(
        "\n[dim]Setup:[/dim]\n"
        "  API key: [cyan]GOOGLE_CSE_API_KEY[/cyan] "
        "— https://console.cloud.google.com\n"
        "  Engine ID: [cyan]GOOGLE_CSE_CX[/cyan] "
        "— https://programmablesearchengine.google.com\n"
        "  Tip: Set CX to search all of the web: "
        'enable "Search the entire web" in engine settings.'
    )


# =============================================================================
# Search
# =============================================================================


def _validate_sort(value: Optional[str]) -> Optional[str]:
    if value and value not in SORT_OPTIONS:
        raise typer.BadParameter(f"Must be one of: {', '.join(SORT_OPTIONS.keys())}")
    return value


def _validate_date_restrict(value: Optional[str]) -> Optional[str]:
    if value and value not in DATE_RESTRICT:
        # Allow raw dateRestrict values like d1, w2
        import re as _re
        if not _re.match(r'^[dwmy]\d+$', value):
            raise typer.BadParameter(
                f"Must be one of: {', '.join(DATE_RESTRICT.keys())} or raw value (e.g. d1, w2)"
            )
    return value


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max results (1-100, fetched in pages of 10)"),
    date_restrict: Optional[str] = typer.Option(
        None, "--date-restrict", "--date",
        help="Date filter: day, week, month, year (or raw: d1, w2 ...)",
        callback=_validate_date_restrict,
    ),
    sort: Optional[str] = typer.Option(
        None, "--sort",
        help="Sort: relevance (default), date",
        callback=_validate_sort,
    ),
    language: Optional[str] = typer.Option(None, "--lang", help="Language code (e.g. en, zh-cn)"),
    safe: Optional[str] = typer.Option(None, "--safe", help="Safe search: off, medium, high"),
    search_type: Optional[str] = typer.Option(None, "--type", help="Search type: web (default), image"),
    shallow: bool = typer.Option(False, "--shallow", "-s", help="Only show results, don't fetch content"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Disable Playwright for content fetching"),
    delay: float = typer.Option(1.0, "--delay", "-d", help="Delay between content fetches (seconds)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Save results to JSON file"),
) -> None:
    """Search the web via Google Custom Search API.

    Requires GOOGLE_CSE_API_KEY and GOOGLE_CSE_CX environment variables.
    Run 'scraper google status' to check configuration.

    By default fetches full content from result URLs.
    Use --shallow to only show search results without content fetching.

    Note: Google CSE API provides 100 free queries/day.
    Each page of 10 results = 1 query. Fetching 100 results = 10 queries.

    Examples:
      scraper google search "machine learning" -n 5
      scraper google search "Python 3.12" --date-restrict week --shallow
      scraper google search "site:arxiv.org transformer" -n 3
    """
    if not is_configured():
        console.print("[red]✗[/red] Google CSE not configured. Run 'scraper google status' for setup instructions.")
        raise typer.Exit(1)

    stype = search_type or ""
    hl = LANGUAGES.get(language or "", language or "")

    scraper = SearchScraper()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task(f"Searching '{query}' via Google CSE...", total=None)
        try:
            resp = scraper.search(
                query,
                num=limit,
                date_restrict=date_restrict or "",
                sort=sort or "",
                language=hl,
                safe=safe or "",
                search_type=stype,
            )
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)

    if not resp.results:
        console.print("[yellow]No results found[/yellow]")
        return

    console.print(f"\n[bold]Found {len(resp.results)} results[/bold]", end="")
    if resp.total_results:
        console.print(f" [dim](~{resp.total_results:,} total)[/dim]", end="")
    if resp.search_time:
        console.print(f" [dim]({resp.search_time:.2f}s)[/dim]", end="")
    console.print()
    console.print()

    # Shallow mode
    if shallow or stype == "image":
        for i, r in enumerate(resp.results, 1):
            domain_str = f" [dim]— {r.display_link}[/dim]" if r.display_link else ""
            console.print(f"[cyan]{i:2}.[/cyan] [bold]{r.title}[/bold]{domain_str}")
            if r.snippet:
                console.print(f"     {r.snippet[:180]}")
            if r.image_url and stype == "image":
                console.print(f"     [dim]Image: {r.image_url[:80]}[/dim]")
            console.print(f"     [dim]{r.url}[/dim]")
            console.print()

        if output:
            data = [r.model_dump(mode="json") for r in resp.results]
            with open(output, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            display_saved(output)
        return

    # Full mode: fetch content
    fetcher = ArticleFetcher(use_playwright=not no_browser)
    storage = JSONStorage(source=SOURCE_NAME)
    articles = []
    success_count = 0
    fail_count = 0

    for i, result in enumerate(resp.results, 1):
        if not result.url:
            continue

        console.print(f"[{i}/{len(resp.results)}] {result.title[:60]}...")

        try:
            article = fetcher.fetch(result.url)

            if article.is_pdf:
                console.print("  [yellow]⚠ PDF (skipped)[/yellow]")
            elif article.content:
                if not article.title:
                    article = article.model_copy(update={"title": result.title})
                articles.append({
                    "search_result": result.model_dump(mode="json"),
                    "article": article.model_dump(mode="json"),
                })
                console.print(f"  [green]✓[/green] {len(article.content)} chars")
                success_count += 1
            else:
                console.print("  [yellow]⚠ No content extracted[/yellow]")
                fail_count += 1

        except Exception as e:
            console.print(f"  [red]✗[/red] {e}")
            fail_count += 1

        if i < len(resp.results):
            time.sleep(delay)

    console.print(
        f"\n[bold]Summary:[/bold] [green]{success_count}[/green] success, "
        f"[red]{fail_count}[/red] failed"
    )

    if output and articles:
        with open(output, "w", encoding="utf-8") as f:
            json.dump(articles, f, ensure_ascii=False, indent=2)
        display_saved(output)
    elif articles:
        for item in articles:
            title = item["article"].get("title") or item["search_result"].get("title") or "untitled"
            slug = _safe_filename(title)
            storage.save(item, f"{slug}.json", description="article", silent=True)
        console.print(f"[dim]Articles saved to: {storage.output_dir}[/dim]")


# =============================================================================
# Fetch
# =============================================================================


@app.command()
def fetch(
    url: str = typer.Argument(..., help="URL to fetch content from"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Disable Playwright fallback"),
    save: bool = typer.Option(True, "--save/--no-save", help="Save to data directory"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output file path"),
) -> None:
    """Fetch full content from any URL.

    Uses curl-cffi → httpx → Playwright fallback chain.
    Does not require Google CSE API keys.
    """
    fetcher = ArticleFetcher(use_playwright=not no_browser)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task(f"Fetching {url[:60]}...", total=None)
        try:
            article = fetcher.fetch(url)
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)

    if article.title:
        console.print(f"\n[bold]{article.title}[/bold]")
    if article.published_date:
        console.print(f"[dim]Published: {article.published_date}[/dim]")

    if article.is_pdf:
        console.print("\n[yellow]⚠ PDF file — content extraction not supported[/yellow]")
    elif article.content:
        preview = article.content[:500]
        if len(article.content) > 500:
            preview += "..."
        console.print(f"\n{preview}")
        console.print(f"\n[dim]({len(article.content)} chars)[/dim]")
    else:
        console.print("\n[yellow]No content extracted[/yellow]")

    if not article.is_accessible:
        console.print("\n[yellow]⚠ Full content not accessible[/yellow]")

    if save or output:
        storage = JSONStorage(source=SOURCE_NAME)
        data = article.model_dump(mode="json")

        if output:
            with open(output, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            display_saved(output, description="Article")
        else:
            slug = _safe_filename(article.title or url)
            save_path = storage.save(data, f"{slug}.json", description="article")
            display_saved(save_path, description="Article")


if __name__ == "__main__":
    app()
