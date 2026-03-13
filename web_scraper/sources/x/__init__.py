"""
X (Twitter) source.

Uses X GraphQL API with cookie-based authentication for searching tweets.
Requires: Import cookies from browser via `scraper x import-cookies <cookies.txt>`.
"""
from .. import register_source, SourceConfig
from .cli import app as cli_app

register_source(
    SourceConfig(
        name="x",
        display_name="X (Twitter)",
        cli_app=cli_app,
        data_dir_name="x",
        is_async=False,
    )
)

__all__ = ["cli_app"]
