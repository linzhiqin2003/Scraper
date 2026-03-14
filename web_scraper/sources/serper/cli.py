"""CLI commands for Serper search source."""
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
    SEARCH_TYPES,
    TIME_RANGES,
    COUNTRIES,
    LANGUAGES,
    get_api_key,
)
from .scrapers import SearchScraper, ArticleFetcher


def _safe_filename(text: str) -> str:
    slug = re.sub(r'[<>:"/\\|?*\s]+', "_", text)
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug[:80] or "untitled"


app = typer.Typer(
    name=SOURCE_NAME,
    help="Serper web search commands (Google search via API).",
    no_args_is_help=True,
)


# =============================================================================
# Status
# =============================================================================


@app.command()
def status() -> None:
    """Check Serper API key configuration."""
    api_key = get_api_key()
    if not api_key:
        console.print("[red]✗[/red] SERPER_API_KEY not set")
        console.print(
            "Get a key at [link=https://serper.dev]https://serper.dev[/link] "
            "and set the SERPER_API_KEY environment variable."
        )
        return

    masked = api_key[:4] + "..." + api_key[-4:] if len(api_key) > 8 else "****"
    console.print(f"[green]✓[/green] SERPER_API_KEY configured: [dim]{masked}[/dim]")

    # Quick connectivity test
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("Testing API...", total=None)
        try:
            scraper = SearchScraper(api_key)
            resp = scraper.search("test", num=1)
            console.print(
                f"[green]✓[/green] API working — "
                f"{len(resp.results)} result(s) returned"
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
            {"option": "Type (--type)", "values": ", ".join(SEARCH_TYPES.keys())},
            {"option": "Time (--time)", "values": ", ".join(TIME_RANGES.keys())},
            {"option": "Country (--country)", "values": ", ".join(COUNTRIES.keys())},
            {"option": "Language (--lang)", "values": ", ".join(LANGUAGES.keys())},
        ],
        columns=[
            ColumnDef("Option", "option", style="cyan"),
            ColumnDef("Values", "values"),
        ],
        title="Serper Search Options",
    )


# =============================================================================
# Search
# =============================================================================


def _validate_type(value: Optional[str]) -> Optional[str]:
    if value and value not in SEARCH_TYPES:
        raise typer.BadParameter(f"Must be one of: {', '.join(SEARCH_TYPES.keys())}")
    return value


def _validate_time(value: Optional[str]) -> Optional[str]:
    if value and value not in TIME_RANGES:
        # Allow raw tbs values like "qdr:d"
        if not value.startswith("qdr:"):
            raise typer.BadParameter(
                f"Must be one of: {', '.join(TIME_RANGES.keys())} or raw tbs value"
            )
    return value


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max results (1-100)"),
    search_type: Optional[str] = typer.Option(
        None, "--type", "-t",
        help="Search type: search (default), news, images",
        callback=_validate_type,
    ),
    time: Optional[str] = typer.Option(
        None, "--time",
        help="Time range: day, week, month, year, hour",
        callback=_validate_time,
    ),
    country: Optional[str] = typer.Option(None, "--country", help="Country code (e.g. us, cn)"),
    language: Optional[str] = typer.Option(None, "--lang", help="Language code (e.g. en, zh-cn)"),
    shallow: bool = typer.Option(False, "--shallow", "-s", help="Only show results, don't fetch content"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Disable Playwright for content fetching"),
    delay: float = typer.Option(1.0, "--delay", "-d", help="Delay between content fetches (seconds)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Save results to JSON file"),
) -> None:
    """Search the web via Serper API (Google search).

    By default fetches full content from result URLs.
    Use --shallow to only show search results without fetching.

    Search types:
      search (default) — general web search
      news — news articles
      images — image search (shallow only)

    Examples:
      scraper serper search "Python asyncio" -n 5
      scraper serper search "AI news" --type news --time week
      scraper serper search "site:github.com fastapi" --shallow
    """
    stype = search_type or "search"

    # Resolve time range
    tbs = ""
    if time:
        tbs = TIME_RANGES.get(time, time)

    # Resolve country/language
    gl = COUNTRIES.get(country or "", country or "")
    hl = LANGUAGES.get(language or "", language or "")

    scraper = SearchScraper()
    if not scraper.is_configured():
        console.print("[red]✗[/red] SERPER_API_KEY not set. Run 'scraper serper status' for setup instructions.")
        raise typer.Exit(1)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task(f"Searching '{query}' via Serper...", total=None)
        try:
            resp = scraper.search(
                query,
                num=limit,
                search_type=stype,
                time_range=tbs,
                country=gl,
                language=hl,
            )
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)

    if not resp.results:
        console.print("[yellow]No results found[/yellow]")
        return

    console.print(f"\n[bold]Found {len(resp.results)} results[/bold]")
    if resp.credits_used is not None:
        console.print(f"[dim]Credits used: {resp.credits_used}[/dim]")

    # Show answer box / knowledge graph if present
    if resp.answer_box:
        ab = resp.answer_box
        console.print(f"\n[bold cyan]Answer:[/bold cyan] {ab.get('answer', ab.get('snippet', ''))}")

    console.print()

    # Shallow mode: display results only
    if shallow or stype == "images":
        for i, r in enumerate(resp.results, 1):
            date_str = f" [dim]({r.date})[/dim]" if r.date else ""
            source_str = f" [dim]— {r.source}[/dim]" if r.source else ""
            console.print(f"[cyan]{i:2}.[/cyan] [bold]{r.title}[/bold]{date_str}{source_str}")
            if r.snippet:
                console.print(f"     {r.snippet[:180]}")
            console.print(f"     [dim]{r.url}[/dim]")
            console.print()

        if output:
            data = [r.model_dump(mode="json") for r in resp.results]
            with open(output, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            display_saved(output)
        return

    # Full mode: fetch content for each result
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
                # Merge snippet as fallback context
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
    save: bool = typer.Option(False, "--save", help="Save results"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output file path"),
) -> None:
    """Fetch full content from any URL.

    Uses curl-cffi → httpx → Playwright fallback chain.
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
