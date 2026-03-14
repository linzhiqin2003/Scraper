"""Yahoo Finance source — stock quotes, search, and financial news."""
from .. import register_source, SourceConfig
from .cli import app as cli_app

register_source(SourceConfig(
    name="yahoo",
    display_name="Yahoo Finance",
    cli_app=cli_app,
    data_dir_name="yahoo",
    is_async=False,
))

__all__ = ["cli_app"]
