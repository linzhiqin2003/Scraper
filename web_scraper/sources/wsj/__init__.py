"""
WSJ (Wall Street Journal) scraper source.

This module provides scraping capabilities for Wall Street Journal,
supporting both RSS feeds and full article extraction via httpx.
"""
from .. import register_source, SourceConfig
from .cli import app as cli_app

register_source(
    SourceConfig(
        name="wsj",
        display_name="Wall Street Journal",
        cli_app=cli_app,
        data_dir_name="wsj",
        is_async=False,  # Uses sync httpx for simplicity
    )
)

__all__ = ["cli_app"]
