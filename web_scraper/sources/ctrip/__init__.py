"""Ctrip (携程) scraper source."""
from .. import register_source, SourceConfig
from .cli import app as cli_app

register_source(SourceConfig(
    name="ctrip",
    display_name="携程 Ctrip",
    cli_app=cli_app,
    data_dir_name="ctrip",
    is_async=False,
))

__all__ = ["cli_app"]
