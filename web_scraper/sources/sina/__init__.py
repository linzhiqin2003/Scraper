"""Sina news search source."""

from .. import SourceConfig, register_source
from .cli import app as cli_app

register_source(
    SourceConfig(
        name="sina",
        display_name="Sina News Search",
        cli_app=cli_app,
        data_dir_name="sina",
        is_async=False,
    )
)

__all__ = ["cli_app"]

