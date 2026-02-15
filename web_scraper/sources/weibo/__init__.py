"""Weibo scraper source."""

from .. import register_source, SourceConfig
from .cli import app as cli_app

register_source(
    SourceConfig(
        name="weibo",
        display_name="Sina Weibo",
        cli_app=cli_app,
        data_dir_name="weibo",
        is_async=False,
    )
)

__all__ = ["cli_app"]
