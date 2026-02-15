"""
Google Scholar scraper source.

This module provides scraping capabilities for Google Scholar,
supporting search result parsing and publisher article content extraction.
"""
from .. import register_source, SourceConfig
from .cli import app as cli_app

register_source(
    SourceConfig(
        name="scholar",
        display_name="Google Scholar",
        cli_app=cli_app,
        data_dir_name="scholar",
        is_async=False,
    )
)

__all__ = ["cli_app"]
