"""
Serper web search source.

Uses the Serper API (Google search wrapper) for web and news search,
with optional full content fetching via curl-cffi/httpx/Playwright.

Requires: SERPER_API_KEY environment variable.
Get a key at https://serper.dev
"""
from .. import register_source, SourceConfig
from .cli import app as cli_app

register_source(
    SourceConfig(
        name="serper",
        display_name="Serper (Google Search API)",
        cli_app=cli_app,
        data_dir_name="serper",
        is_async=False,
    )
)

__all__ = ["cli_app"]
