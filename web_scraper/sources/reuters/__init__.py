"""Reuters news scraper source."""

import typer

from ..  import register_source, SourceConfig
from .cli import app as cli_app

# Register this source
register_source(SourceConfig(
    name="reuters",
    display_name="Reuters News",
    cli_app=cli_app,
    data_dir_name="reuters",
    is_async=False,
))

__all__ = ["cli_app"]
