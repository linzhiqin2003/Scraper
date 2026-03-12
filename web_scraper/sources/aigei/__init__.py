"""爱给网 GIF 素材爬虫 source."""
from .. import register_source, SourceConfig
from .cli import app as cli_app

register_source(
    SourceConfig(
        name="aigei",
        display_name="爱给网 Aigei (GIF素材)",
        cli_app=cli_app,
        data_dir_name="aigei",
        is_async=False,
    )
)

__all__ = ["cli_app"]
