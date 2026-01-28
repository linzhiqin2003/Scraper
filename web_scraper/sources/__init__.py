"""Source registry for the unified scraper framework."""

from dataclasses import dataclass
from typing import Dict, Optional, Callable

import typer


@dataclass
class SourceConfig:
    """Configuration for a scraper source."""

    name: str                    # "reuters"
    display_name: str            # "路透社"
    cli_app: typer.Typer         # Typer sub-application
    data_dir_name: str           # Directory name for data storage
    is_async: bool = False       # Whether the source uses async scrapers


# Global source registry
SOURCES: Dict[str, SourceConfig] = {}


def register_source(config: SourceConfig) -> None:
    """Register a scraper source.

    Args:
        config: Source configuration.
    """
    SOURCES[config.name] = config


def get_source(name: str) -> Optional[SourceConfig]:
    """Get a source by name.

    Args:
        name: Source name.

    Returns:
        SourceConfig or None if not found.
    """
    return SOURCES.get(name)


def list_sources() -> Dict[str, SourceConfig]:
    """Get all registered sources.

    Returns:
        Dictionary of source name to config.
    """
    return SOURCES.copy()


# Import and register all sources
# This triggers the registration in each source's __init__.py

def _load_sources():
    """Load all available sources."""
    try:
        from . import reuters
    except ImportError:
        pass

    try:
        from . import xiaohongshu
    except ImportError:
        pass


_load_sources()
