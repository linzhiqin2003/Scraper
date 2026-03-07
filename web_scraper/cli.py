"""Unified CLI entry point for the web scraper framework."""

import json
import sys
from typing import Optional

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
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
    from .core.config import get_config
    cfg = get_config()

    table = Table(title="Available Scraper Sources", show_lines=False)
    table.add_column("Name", style="cyan")
    table.add_column("Description", style="bold")
    table.add_column("Type", style="dim")
    table.add_column("MCP", style="dim")

    for name, source_cfg in sorted(SOURCES.items()):
        source_type = "async" if source_cfg.is_async else "sync"
        mcp_status = "[green]on[/green]" if cfg.is_enabled(name) else "[dim]off[/dim]"
        table.add_row(name, source_cfg.display_name, source_type, mcp_status)

    console.print(table)
    console.print("\n[dim]Use 'scraper <source> --help' for source-specific commands.[/dim]")
    console.print(f"[dim]MCP column shows enabled state in the MCP server (config: {get_config().path})[/dim]")


# =============================================================================
# Config command group
# =============================================================================

config_app = typer.Typer(
    name="config",
    help="Manage MCP server source configuration.",
    no_args_is_help=True,
)
app.add_typer(config_app, name="config")

_ALL_SOURCES = ["reuters", "wsj", "scholar", "zhihu", "dianping", "serper", "google"]


@config_app.command("list")
def config_list() -> None:
    """Show which sources are enabled in the MCP server."""
    from .core.config import get_config
    cfg = get_config()

    table = Table(title="MCP Source Configuration", show_lines=False)
    table.add_column("Source", style="cyan")
    table.add_column("Status")
    table.add_column("Notes", style="dim")

    notes = {
        "reuters": "no auth required",
        "wsj": "requires: scraper wsj import-cookies",
        "scholar": "no auth required",
        "zhihu": "requires: scraper zhihu login",
        "dianping": "requires: scraper dianping import-cookies",
        "serper": "requires: SERPER_API_KEY env var",
        "google": "requires: GOOGLE_CSE_API_KEY + GOOGLE_CSE_CX env vars",
    }

    for source, enabled in sorted(cfg.all_sources().items()):
        status = "[green]enabled[/green]" if enabled else "[dim]disabled[/dim]"
        table.add_row(source, status, notes.get(source, ""))

    console.print(table)
    console.print(f"\n[dim]Config file: {cfg.path}[/dim]")


@config_app.command("enable")
def config_enable(
    source: str = typer.Argument(..., help=f"Source to enable: {', '.join(_ALL_SOURCES)}"),
) -> None:
    """Enable a source in the MCP server."""
    from .core.config import get_config
    try:
        cfg = get_config()
        cfg.set_enabled(source, True)
        console.print(f"[green]✓[/green] '{source}' enabled")
        console.print(f"[dim]Config saved to {cfg.path}[/dim]")
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@config_app.command("disable")
def config_disable(
    source: str = typer.Argument(..., help=f"Source to disable: {', '.join(_ALL_SOURCES)}"),
) -> None:
    """Disable a source in the MCP server."""
    from .core.config import get_config
    try:
        cfg = get_config()
        cfg.set_enabled(source, False)
        console.print(f"[dim]✓ '{source}' disabled[/dim]")
        console.print(f"[dim]Config saved to {cfg.path}[/dim]")
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@config_app.command("set")
def config_set(
    sources_on: Optional[str] = typer.Option(
        None, "--enable", help="Comma-separated sources to enable"
    ),
    sources_off: Optional[str] = typer.Option(
        None, "--disable", help="Comma-separated sources to disable"
    ),
) -> None:
    """Enable and/or disable multiple sources at once.

    Examples:
      scraper config set --enable serper,google
      scraper config set --enable reuters --disable wsj
    """
    from .core.config import get_config
    if not sources_on and not sources_off:
        console.print("[yellow]Nothing to do. Use --enable and/or --disable.[/yellow]")
        raise typer.Exit()

    cfg = get_config()
    errors = []

    if sources_on:
        for s in sources_on.split(","):
            s = s.strip()
            if not s:
                continue
            try:
                cfg.set_enabled(s, True)
                console.print(f"[green]✓[/green] '{s}' enabled")
            except ValueError as e:
                errors.append(str(e))

    if sources_off:
        for s in sources_off.split(","):
            s = s.strip()
            if not s:
                continue
            try:
                cfg.set_enabled(s, False)
                console.print(f"[dim]✓ '{s}' disabled[/dim]")
            except ValueError as e:
                errors.append(str(e))

    console.print(f"[dim]Config saved to {cfg.path}[/dim]")

    if errors:
        for e in errors:
            console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@app.command()
def search(
    source: str = typer.Argument(..., help="Source: reuters, wsj, scholar, zhihu, dianping, serper, google"),
    keywords: str = typer.Argument(..., help="Search keywords"),
    limit: int = typer.Option(10, "-n", "--limit", help="Max results (1-50)"),
    time_range: str = typer.Option("", "-t", "--time-range", help="Time filter: day, week, month, year"),
    language: str = typer.Option("", "-l", "--language", help="Language code: en, zh, zh-cn, ja"),
    output: Optional[str] = typer.Option(None, "-o", "--output", help="Save results to JSON file"),
    raw: bool = typer.Option(False, "--raw", help="Print raw JSON instead of table"),
) -> None:
    """Search content from a source (mirrors MCP search tool).

    Examples:

      scraper search serper "Python 3.13 features" -n 5

      scraper search reuters "Federal Reserve" --time-range week

      scraper search scholar "transformer attention" -n 10 -l en

      scraper search zhihu "量化交易策略" -n 8
    """
    from .mcp_server import search as _search
    results = _search(
        source=source,
        search_keywords=keywords,
        limit=limit,
        time_range=time_range,
        language=language,
    )

    # Save to file if requested
    if output:
        path = output if output.endswith(".json") else output + ".json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        console.print(f"[dim]Saved {len(results)} results to {path}[/dim]")
        return

    # Raw JSON mode
    if raw:
        console.print_json(json.dumps(results, ensure_ascii=False))
        return

    # Check for error
    if results and "error" in results[0]:
        err = results[0]
        console.print(f"[red]Error:[/red] {err['error']}")
        if "hint" in err:
            console.print(f"[dim]Hint: {err['hint']}[/dim]")
        raise typer.Exit(1)

    if not results:
        console.print("[yellow]No results found.[/yellow]")
        return

    # Build display table — columns depend on source
    first = results[0]
    table = Table(
        title=f"{source.upper()} — \"{keywords}\" ({len(results)} results)",
        show_lines=True,
        expand=True,
    )
    table.add_column("#", style="dim", width=3, no_wrap=True)
    table.add_column("Title", style="bold", ratio=3)

    # Source-specific extra columns
    extra_cols: list[str] = []
    if "published_at" in first:
        table.add_column("Date", style="cyan", width=12, no_wrap=True)
        extra_cols.append("published_at")
    if "authors" in first:
        table.add_column("Authors", style="cyan", ratio=2)
        extra_cols.append("authors")
    if "year" in first:
        table.add_column("Year", style="cyan", width=6, no_wrap=True)
        extra_cols.append("year")
    if "cited_by_count" in first:
        table.add_column("Cited", style="cyan", width=6, no_wrap=True)
        extra_cols.append("cited_by_count")
    if "author" in first:
        table.add_column("Author", style="cyan", width=16, no_wrap=True)
        extra_cols.append("author")
    if "upvotes" in first:
        table.add_column("Upvotes", style="cyan", width=8, no_wrap=True)
        extra_cols.append("upvotes")
    if "date" in first:
        table.add_column("Date", style="cyan", width=12, no_wrap=True)
        extra_cols.append("date")

    table.add_column("Snippet / URL", style="dim", ratio=4)

    for i, r in enumerate(results, 1):
        title = r.get("title") or ""
        url = r.get("url") or ""
        snippet = r.get("snippet") or ""
        preview = (snippet[:120] + "…") if len(snippet) > 120 else snippet
        detail = f"{preview}\n[link]{url}[/link]" if preview else f"[link]{url}[/link]"

        row = [str(i), title]
        for col in extra_cols:
            val = r.get(col)
            if val is None:
                row.append("")
            elif isinstance(val, list):
                row.append(", ".join(str(v) for v in val[:3]))
            else:
                row.append(str(val))
        row.append(detail)
        table.add_row(*row)

    console.print(table)


@app.command()
def fetch(
    url: str = typer.Argument(..., help="Full URL to fetch"),
    output: Optional[str] = typer.Option(None, "-o", "--output", help="Save result to JSON file"),
    raw: bool = typer.Option(False, "--raw", help="Print raw JSON instead of formatted content"),
) -> None:
    """Fetch full content from a URL (mirrors MCP fetch tool).

    Auto-routes by domain:

      reuters.com → Reuters client

      wsj.com → WSJ scraper

      zhihu.com → Zhihu scraper

      everything else → generic fetcher

    Examples:

      scraper fetch "https://arxiv.org/abs/2310.06825"

      scraper fetch "https://zhuanlan.zhihu.com/p/123456789"
    """
    from .mcp_server import fetch as _fetch
    result = _fetch(url=url)

    # Save to file
    if output:
        path = output if output.endswith(".json") else output + ".json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        console.print(f"[dim]Saved to {path}[/dim]")
        return

    # Raw JSON mode
    if raw:
        console.print_json(json.dumps(result, ensure_ascii=False))
        return

    # Error
    if "error" in result:
        console.print(f"[red]Error:[/red] {result['error']}")
        raise typer.Exit(1)

    # Header panel with metadata
    source = result.get("source", "")
    title = result.get("title") or "(no title)"
    is_accessible = result.get("is_accessible", True)
    is_pdf = result.get("is_pdf", False)

    meta_lines = [f"[bold]{title}[/bold]"]
    meta_lines.append(f"[dim]URL:[/dim] {url}")
    meta_lines.append(f"[dim]Source:[/dim] {source}  |  [dim]Accessible:[/dim] {'[green]yes[/green]' if is_accessible else '[red]no[/red]'}  |  [dim]PDF:[/dim] {'yes' if is_pdf else 'no'}")

    for key in ("published_at", "published_date", "author", "upvotes", "content_type"):
        val = result.get(key)
        if val:
            meta_lines.append(f"[dim]{key}:[/dim] {val}")
    if result.get("tags"):
        meta_lines.append(f"[dim]tags:[/dim] {', '.join(result['tags'])}")

    console.print(Panel("\n".join(meta_lines), expand=False))

    # Content
    content = result.get("content")
    if content:
        console.print(Markdown(content))
    else:
        console.print("[yellow](no content)[/yellow]")


@app.command()
def version() -> None:
    """Show version information."""
    from . import __version__
    console.print(f"web-scraper version {__version__}")


if __name__ == "__main__":
    app()
