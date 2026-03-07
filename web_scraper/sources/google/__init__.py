"""
Google Custom Search source.

Uses the Google Custom Search Engine (CSE) API for web search,
with optional full content fetching via curl-cffi/httpx/Playwright.

Requires:
  GOOGLE_CSE_API_KEY — API key from https://console.cloud.google.com
  GOOGLE_CSE_CX      — Engine ID from https://programmablesearchengine.google.com

Free tier: 100 queries/day.
"""
from .. import register_source, SourceConfig
from .cli import app as cli_app

register_source(
    SourceConfig(
        name="google",
        display_name="Google Custom Search",
        cli_app=cli_app,
        data_dir_name="google",
        is_async=False,
    )
)

__all__ = ["cli_app"]
