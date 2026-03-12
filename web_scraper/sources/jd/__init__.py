"""
JD (京东) scraper source.

This module provides scraping capabilities for JD.com product pages,
using Playwright response interception to bypass h5st signing mechanism.
"""
from .. import register_source, SourceConfig
from .cli import app as cli_app

register_source(
    SourceConfig(
        name="jd",
        display_name="京东 (JD.com)",
        cli_app=cli_app,
        data_dir_name="jd",
        is_async=False,
    )
)

__all__ = ["cli_app"]
