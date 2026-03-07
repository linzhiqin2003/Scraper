"""Douyin scraper source."""

from .. import register_source, SourceConfig
from .cli import app as cli_app

register_source(
    SourceConfig(
        name="douyin",
        display_name="Douyin (抖音)",
        cli_app=cli_app,
        data_dir_name="douyin",
        is_async=False,
    )
)

__all__ = ["cli_app"]
