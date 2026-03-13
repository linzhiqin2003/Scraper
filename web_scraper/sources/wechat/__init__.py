"""
WeChat Official Accounts (微信公众号) source.

Fetches and parses WeChat MP articles by URL using HTTP requests.
No authentication required for public articles.
"""
from .. import register_source, SourceConfig
from .cli import app as cli_app

register_source(
    SourceConfig(
        name="wechat",
        display_name="WeChat Official Accounts (微信公众号)",
        cli_app=cli_app,
        data_dir_name="wechat",
        is_async=False,
    )
)

__all__ = ["cli_app"]
