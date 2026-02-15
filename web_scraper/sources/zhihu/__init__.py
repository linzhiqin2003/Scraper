"""Zhihu scraper source."""

from .. import register_source, SourceConfig
from .cli import app as cli_app

register_source(
    SourceConfig(
        name="zhihu",
        display_name="Zhihu",
        cli_app=cli_app,
        data_dir_name="zhihu",
        is_async=False,
    )
)

__all__ = ["cli_app"]
