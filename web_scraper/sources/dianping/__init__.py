"""Dianping scraper source."""
from .. import register_source, SourceConfig
from .cli import app as cli_app

register_source(SourceConfig(
    name="dianping",
    display_name="大众点评 Dianping",
    cli_app=cli_app,
    data_dir_name="dianping",
    is_async=False,
))

__all__ = ["cli_app"]
