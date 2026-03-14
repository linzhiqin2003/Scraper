"""CLI commands for Yahoo Finance source."""
import json
import re
from typing import Optional

import typer
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from ...core.display import ColumnDef, console, display_options, display_saved
from ...core.storage import JSONStorage
from .config import CHART_INTERVALS, CHART_PERIODS, QUOTE_TYPES, SOURCE_NAME
from .scrapers import FinanceScraper


def _safe_filename(text: str) -> str:
    slug = re.sub(r'[<>:"/\\|?*\s]+', "_", text)
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug[:80] or "untitled"


app = typer.Typer(
    name=SOURCE_NAME,
    help="Yahoo Finance — stock quotes, search, and financial news.",
    no_args_is_help=True,
)


# =============================================================================
# Status
# =============================================================================


@app.command()
def status() -> None:
    """Check Yahoo Finance API connectivity."""
    scraper = FinanceScraper()
    try:
        resp = scraper.search("AAPL", max_results=1, news_count=0)
        if resp.quotes:
            console.print("[green]✓[/green] Yahoo Finance API is accessible")
            console.print(f"  [dim]Test: found {resp.quotes[0].symbol} ({resp.quotes[0].name})[/dim]")
        else:
            console.print("[yellow]⚠[/yellow] API responded but no results")
    except Exception as e:
        console.print(f"[red]✗[/red] API check failed: {e}")


# =============================================================================
# Options
# =============================================================================


@app.command()
def options() -> None:
    """Show available options and asset types."""
    display_options(
        items=[
            {"option": "Quote Types", "values": ", ".join(f"{k} ({v})" for k, v in QUOTE_TYPES.items())},
            {"option": "Chart Periods (--period)", "values": ", ".join(CHART_PERIODS)},
            {"option": "Chart Intervals (--interval)", "values": ", ".join(CHART_INTERVALS)},
        ],
        columns=[
            ColumnDef("Option", "option", style="cyan"),
            ColumnDef("Values", "values"),
        ],
        title="Yahoo Finance Options",
    )
    console.print("\n[dim]No API key required. Uses Yahoo's public finance API.[/dim]")


# =============================================================================
# Search
# =============================================================================


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query (ticker, company name, keyword)"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max results"),
    news: int = typer.Option(5, "--news", help="Number of news articles (0 to skip)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Save to JSON file"),
    save: bool = typer.Option(False, "--save", help="Save results"),
) -> None:
    """Search for tickers, companies, and related news.

    Examples:
      scraper yahoo search "Apple"
      scraper yahoo search TSLA --news 10
      scraper yahoo search "semiconductor" -n 20
    """
    scraper = FinanceScraper()
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task(f"Searching '{query}'...", total=None)
            resp = scraper.search(query, max_results=limit, news_count=news)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    # Quotes table
    if resp.quotes:
        table = Table(title=f"Tickers matching '{query}'", show_lines=False)
        table.add_column("#", style="dim", width=3)
        table.add_column("Symbol", style="cyan bold")
        table.add_column("Name")
        table.add_column("Type", style="dim")
        table.add_column("Exchange", style="dim")

        for i, q in enumerate(resp.quotes, 1):
            type_label = QUOTE_TYPES.get(q.quote_type, q.quote_type)
            table.add_row(str(i), q.symbol, q.name, type_label, q.exchange)
        console.print(table)

    # News table
    if resp.news:
        console.print()
        table = Table(title=f"News for '{query}'", show_lines=True, expand=True)
        table.add_column("#", style="dim", width=3)
        table.add_column("Title", style="bold", ratio=3)
        table.add_column("Publisher", style="cyan", width=16)
        table.add_column("Tickers", style="dim", width=16)
        table.add_column("URL", style="dim", ratio=2)

        for i, n in enumerate(resp.news, 1):
            tickers = ", ".join(n.related_tickers[:5]) if n.related_tickers else ""
            table.add_row(str(i), n.title, n.publisher, tickers, n.url)
        console.print(table)

    if not resp.quotes and not resp.news:
        console.print("[yellow]No results found[/yellow]")
        return

    # Save
    if output:
        data = resp.model_dump(mode="json")
        with open(output, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        display_saved(output)
    elif save:
        storage = JSONStorage(source=SOURCE_NAME)
        data = resp.model_dump(mode="json")
        slug = _safe_filename(query)
        path = storage.save(data, f"search_{slug}.json", description="search results")
        display_saved(path)


# =============================================================================
# Quote
# =============================================================================


@app.command()
def quote(
    symbols: str = typer.Argument(..., help="Ticker symbol(s), comma-separated (e.g. AAPL,MSFT,GOOG)"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Save to JSON file"),
    save: bool = typer.Option(False, "--save", help="Save results"),
) -> None:
    """Get real-time stock quotes.

    Examples:
      scraper yahoo quote AAPL
      scraper yahoo quote "AAPL,MSFT,GOOG,AMZN"
      scraper yahoo quote TSLA -o tesla.json
    """
    symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]

    scraper = FinanceScraper()
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task(f"Fetching quotes for {', '.join(symbol_list)}...", total=None)
            quotes = scraper.quote(symbol_list)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if not quotes:
        console.print("[yellow]No quotes found[/yellow]")
        return

    table = Table(title="Stock Quotes", show_lines=True)
    table.add_column("Symbol", style="cyan bold")
    table.add_column("Name")
    table.add_column("Price", justify="right")
    table.add_column("Change", justify="right")
    table.add_column("Change %", justify="right")
    table.add_column("Volume", justify="right", style="dim")
    table.add_column("Mkt Cap", justify="right", style="dim")
    table.add_column("P/E", justify="right", style="dim")
    table.add_column("52W Range", style="dim")

    for q in quotes:
        # Color change
        if q.change is not None and q.change >= 0:
            change_str = f"[green]+{q.change:.2f}[/green]"
            pct_str = f"[green]+{q.change_percent:.2f}%[/green]"
        elif q.change is not None:
            change_str = f"[red]{q.change:.2f}[/red]"
            pct_str = f"[red]{q.change_percent:.2f}%[/red]"
        else:
            change_str = "-"
            pct_str = "-"

        price_str = f"{q.price:.2f}" if q.price is not None else "-"
        vol_str = _fmt_number(q.volume) if q.volume else "-"
        cap_str = _fmt_number(q.market_cap) if q.market_cap else "-"
        pe_str = f"{q.pe_ratio:.1f}" if q.pe_ratio else "-"
        range_str = (
            f"{q.fifty_two_week_low:.2f} - {q.fifty_two_week_high:.2f}"
            if q.fifty_two_week_low and q.fifty_two_week_high
            else "-"
        )

        table.add_row(q.symbol, q.name, price_str, change_str, pct_str, vol_str, cap_str, pe_str, range_str)

    console.print(table)

    # Save
    if output:
        data = [q.model_dump(mode="json") for q in quotes]
        with open(output, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        display_saved(output)
    elif save:
        storage = JSONStorage(source=SOURCE_NAME)
        data = [q.model_dump(mode="json") for q in quotes]
        slug = "_".join(symbol_list[:5])
        path = storage.save(data, f"quote_{slug}.json", description="quotes")
        display_saved(path)


# =============================================================================
# News
# =============================================================================


@app.command()
def news(
    query: str = typer.Argument(..., help="Ticker or keyword for news"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max news articles"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Save to JSON file"),
    save: bool = typer.Option(False, "--save", help="Save results"),
) -> None:
    """Get financial news for a ticker or topic.

    Examples:
      scraper yahoo news AAPL
      scraper yahoo news "Federal Reserve" -n 20
    """
    scraper = FinanceScraper()
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task(f"Fetching news for '{query}'...", total=None)
            articles = scraper.news(query, count=limit)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if not articles:
        console.print("[yellow]No news found[/yellow]")
        return

    table = Table(title=f"News: {query}", show_lines=True, expand=True)
    table.add_column("#", style="dim", width=3)
    table.add_column("Title", style="bold", ratio=3)
    table.add_column("Publisher", style="cyan", width=16)
    table.add_column("Tickers", style="dim", width=16)
    table.add_column("URL", style="dim", ratio=2)

    for i, n in enumerate(articles, 1):
        tickers = ", ".join(n.related_tickers[:5]) if n.related_tickers else ""
        table.add_row(str(i), n.title, n.publisher, tickers, n.url)

    console.print(table)

    # Save
    if output:
        data = [n.model_dump(mode="json") for n in articles]
        with open(output, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        display_saved(output)
    elif save:
        storage = JSONStorage(source=SOURCE_NAME)
        data = [n.model_dump(mode="json") for n in articles]
        slug = _safe_filename(query)
        path = storage.save(data, f"news_{slug}.json", description="news")
        display_saved(path)


# =============================================================================
# Helpers
# =============================================================================


def _fmt_number(n: Optional[int]) -> str:
    """Format large numbers with K/M/B suffix."""
    if n is None:
        return "-"
    if n >= 1_000_000_000_000:
        return f"{n / 1_000_000_000_000:.1f}T"
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f}B"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)
