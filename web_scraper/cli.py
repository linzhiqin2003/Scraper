"""Unified CLI entry point for the web scraper framework."""

import typer
from rich.console import Console
from rich.table import Table

from .sources import SOURCES

app = typer.Typer(
    name="scraper",
    help="Unified web scraping framework",
    no_args_is_help=True,
)
console = Console()


# Dynamically register all source sub-applications
for name, config in SOURCES.items():
    app.add_typer(
        config.cli_app,
        name=name,
        help=config.display_name,
    )


@app.command()
def sources() -> None:
    """List all available scraper sources."""
    table = Table(title="Available Scraper Sources", show_lines=False)
    table.add_column("Name", style="cyan")
    table.add_column("Description", style="bold")
    table.add_column("Type", style="dim")

    for name, config in sorted(SOURCES.items()):
        source_type = "async" if config.is_async else "sync"
        table.add_row(name, config.display_name, source_type)

    console.print(table)
    console.print("\n[dim]Use 'scraper <source> --help' for source-specific commands.[/dim]")


@app.command()
def version() -> None:
    """Show version information."""
    from . import __version__
    console.print(f"web-scraper version {__version__}")


if __name__ == "__main__":
    app()
