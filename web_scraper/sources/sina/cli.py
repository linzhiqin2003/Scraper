"""CLI commands for Sina news search."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Optional

import typer
from rich.progress import Progress, SpinnerColumn, TextColumn

from ...core.display import ColumnDef, console, display_saved, display_search_results, truncate
from .config import SOURCE_NAME
from .scrapers import SearchError, SearchScraper

app = typer.Typer(
    name=SOURCE_NAME,
    help="Sina news time-range search scraper.",
    no_args_is_help=True,
)


def _safe_filename(text: str) -> str:
    slug = re.sub(r'[<>:"/\\|?*\s]+', "_", text)
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug[:80] or "sina_search"


def _save_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


@app.command()
def search(
    query: str = typer.Argument(..., help="Search keyword, e.g. 楼市资本论"),
    start_time: str = typer.Option(..., "--start-time", "--start", help="Start time: YYYY-MM-DD HH:MM:SS"),
    end_time: str = typer.Option(..., "--end-time", "--end", help="End time: YYYY-MM-DD HH:MM:SS"),
    max_pages: int = typer.Option(20, "--max-pages", help="Maximum number of pages to fetch"),
    split_by_year: bool = typer.Option(False, "--split-by-year", help="Split the interval into one query per year"),
    adaptive: bool = typer.Option(False, "--adaptive", help="Automatically split dense time windows to avoid page caps"),
    limit: Optional[int] = typer.Option(None, "--limit", "-n", help="Optional maximum number of results"),
    source: str = typer.Option("", "--source", help="Optional source filter"),
    delay: float = typer.Option(0.2, "--delay", help="Delay between page requests in seconds"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output path without extension"),
) -> None:
    """Search Sina news within a time range and export results."""
    scraper = SearchScraper(delay=delay)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task(f"Searching Sina for '{query}'...", total=None)
        try:
            if adaptive:
                response = scraper.search_adaptive(
                    query=query,
                    start_time=start_time,
                    end_time=end_time,
                    max_pages=max_pages,
                    limit=limit,
                    source=source,
                )
            elif split_by_year:
                response = scraper.search_split_by_year(
                    query=query,
                    start_time=start_time,
                    end_time=end_time,
                    max_pages_per_year=max_pages,
                    limit=limit,
                    source=source,
                )
            else:
                response = scraper.search(
                    query=query,
                    start_time=start_time,
                    end_time=end_time,
                    max_pages=max_pages,
                    limit=limit,
                    source=source,
                )
        except SearchError as exc:
            console.print(f"[red]Error:[/red] {exc}")
            raise typer.Exit(1)

    if not response.results:
        console.print("[yellow]No results found.[/yellow]")
        return

    rows = [item.model_dump(mode="json") for item in response.results]
    display_search_results(
        rows,
        columns=[
            ColumnDef("Title", "title", style="bold", max_width=44, formatter=lambda v: truncate(str(v), 90)),
            ColumnDef("Published", "published_at", style="green", width=19),
            ColumnDef("Source", "source_name", style="cyan", max_width=18, formatter=lambda v: truncate(str(v or "-"), 24)),
            ColumnDef("URL", "url", style="dim", max_width=48, formatter=lambda v: truncate(str(v), 64)),
        ],
        title=f"Sina Search — {query}",
        summary=(
            f"Fetched {len(rows)} results across {response.fetched_pages} page(s)"
            + (f"; reported total {response.total_results}" if response.total_results is not None else "")
        ),
    )

    if output:
        base_path = Path(output)
    else:
        filename = _safe_filename(f"{query}_{start_time}_{end_time}")
        base_path = Path.cwd() / filename

    json_path = base_path.with_suffix(".json")
    csv_path = base_path.with_suffix(".csv")
    json_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "query": response.query,
        "start_time": response.start_time,
        "end_time": response.end_time,
        "total_results": response.total_results,
        "fetched_pages": response.fetched_pages,
        "results": rows,
    }

    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _save_csv(csv_path, rows)
    display_saved(json_path, description="JSON results")
    display_saved(csv_path, description="CSV results")


if __name__ == "__main__":
    app()
