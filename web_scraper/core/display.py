"""Shared Rich UI display module for all CLI sources.

Style guide:
    | Element           | Style                                    |
    |-------------------|------------------------------------------|
    | Row number column  | dim, width=4                             |
    | Title / main text  | bold                                     |
    | URL                | dim                                      |
    | Time               | green                                    |
    | Author / user      | cyan                                     |
    | Category / tag     | magenta                                  |
    | Stats              | yellow                                   |
    | Auth Panel         | border_style=blue                        |
    | Content Panel      | border_style=cyan                        |
    | Search results tbl | header_style=bold magenta, show_lines=True|
    | Saved path         | dim prefix + green path                  |
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


# ---------------------------------------------------------------------------
# ColumnDef
# ---------------------------------------------------------------------------

@dataclass
class ColumnDef:
    """Definition for a single table column."""

    name: str
    key: str
    style: str = ""
    max_width: int | None = None
    width: int | None = None
    formatter: Callable[[Any], str] | None = None


# ---------------------------------------------------------------------------
# 1. Auth status
# ---------------------------------------------------------------------------

def display_auth_status(
    source_name: str,
    status: str,
    extras: dict[str, Any] | None = None,
    state_file: Path | None = None,
) -> None:
    """Display authentication status panel.

    Args:
        source_name: Human-readable source name (e.g. "Reuters").
        status: One of "logged_in", "logged_out", "session_expired",
                "blocked", "unknown".
        extras: Additional key-value pairs to display.
        state_file: Path to the session / state file (shows exists/not found).
    """
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Key", style="dim")
    table.add_column("Value")

    label = status.replace("_", " ").title()
    table.add_row("Status", f"[{status_style(status)}]{label}[/]")

    if extras:
        for key, value in extras.items():
            table.add_row(key, str(value))

    if state_file is not None:
        file_status = "[green]exists[/]" if state_file.exists() else "[dim]not found[/]"
        table.add_row("Session file", file_status)

    console.print(Panel(table, title=f"[bold]{source_name} Status[/]", border_style="blue"))


# ---------------------------------------------------------------------------
# 2. Search results table
# ---------------------------------------------------------------------------

def display_search_results(
    results: Sequence[dict[str, Any]],
    columns: list[ColumnDef],
    title: str = "",
    summary: str = "",
) -> None:
    """Render a search results table with auto-numbered rows.

    Args:
        results: List of result dicts.
        columns: Column definitions.
        title: Table title.
        summary: Summary line printed below the table.
    """
    table = Table(title=title, show_lines=True, header_style="bold magenta")
    table.add_column("#", style="dim", width=4)

    for col in columns:
        kwargs: dict[str, Any] = {}
        if col.style:
            kwargs["style"] = col.style
        if col.max_width is not None:
            kwargs["max_width"] = col.max_width
        if col.width is not None:
            kwargs["width"] = col.width
        table.add_column(col.name, **kwargs)

    for i, row in enumerate(results, 1):
        cells = [str(i)]
        for col in columns:
            raw = row.get(col.key, "-")
            if col.formatter:
                cells.append(col.formatter(raw))
            else:
                cells.append(str(raw) if raw is not None else "-")
        table.add_row(*cells)

    console.print(table)

    if summary:
        console.print(f"\n[dim]{summary}[/]")


# ---------------------------------------------------------------------------
# 3. Detail display
# ---------------------------------------------------------------------------

def display_detail(
    meta: dict[str, Any],
    content: str,
    title: str = "",
    content_title: str = "Content",
    sub_tables: list[tuple[str, Table]] | None = None,
) -> None:
    """Display detail view with metadata panel + content panel.

    Args:
        meta: Key-value metadata dict.
        title: Panel title for metadata.
        content: Body text.
        content_title: Title for the content panel.
        sub_tables: Optional list of (title, Table) for extra tables.
    """
    meta_table = Table(show_header=False, box=None, padding=(0, 2))
    meta_table.add_column("Key", style="dim")
    meta_table.add_column("Value")

    for key, value in meta.items():
        if value is not None:
            meta_table.add_row(key, str(value))

    console.print(Panel(meta_table, title=f"[bold]{title}[/]", border_style="blue"))

    if content:
        console.print(Panel(content, title=f"[bold]{content_title}[/]", border_style="cyan"))

    if sub_tables:
        for sub_title, sub_table in sub_tables:
            console.print(sub_table)


# ---------------------------------------------------------------------------
# 4. Options / categories list
# ---------------------------------------------------------------------------

def display_options(
    items: Sequence[dict[str, Any]],
    columns: list[ColumnDef],
    title: str = "",
) -> None:
    """Render a simple options / categories table.

    Args:
        items: List of option dicts.
        columns: Column definitions.
        title: Table title.
    """
    table = Table(title=title, show_lines=False)

    for col in columns:
        kwargs: dict[str, Any] = {}
        if col.style:
            kwargs["style"] = col.style
        if col.max_width is not None:
            kwargs["max_width"] = col.max_width
        if col.width is not None:
            kwargs["width"] = col.width
        table.add_column(col.name, **kwargs)

    for row in items:
        cells = []
        for col in columns:
            raw = row.get(col.key, "-")
            if col.formatter:
                cells.append(col.formatter(raw))
            else:
                cells.append(str(raw) if raw is not None else "-")
        table.add_row(*cells)

    console.print(table)


# ---------------------------------------------------------------------------
# 5. Save feedback
# ---------------------------------------------------------------------------

def display_saved(path: Path | str, description: str = "Results") -> None:
    """Print a standardised 'saved to' message."""
    console.print(f"[green]{description} saved to:[/green] {path}")


# ---------------------------------------------------------------------------
# 6. Utility helpers
# ---------------------------------------------------------------------------

def truncate(text: str, max_len: int = 120) -> str:
    """Truncate text with ellipsis."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def format_stats(**kwargs: Any) -> str:
    """Format key-value pairs as compact stats string.

    Example::

        format_stats(R=99, C=152, L=3126) -> "R:99 C:152 L:3126"
    """
    return " ".join(f"{k}:{v}" for k, v in kwargs.items() if v is not None)


def status_style(status: str) -> str:
    """Map status string to Rich style."""
    mapping = {
        "logged_in": "bold green",
        "logged_out": "bold red",
        "session_expired": "bold yellow",
        "blocked": "bold yellow",
        "unknown": "bold dim",
    }
    return mapping.get(status, "")
