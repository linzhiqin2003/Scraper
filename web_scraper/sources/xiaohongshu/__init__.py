"""Xiaohongshu (Little Red Book) scraper source."""

import typer

from .. import register_source, SourceConfig
from .cli import app as cli_app

# Register this source
register_source(SourceConfig(
    name="xhs",
    display_name="Xiaohongshu (Little Red Book)",
    cli_app=cli_app,
    data_dir_name="xiaohongshu",
    is_async=True,
))

__all__ = ["cli_app"]
