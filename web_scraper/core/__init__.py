"""Core modules for the web scraper framework."""

from .exceptions import (
    ScraperError,
    NotLoggedInError,
    RateLimitedError,
    CaptchaError,
    ContentNotFoundError,
)
from .browser import BrowserManager, create_browser, get_browser
from .base import BaseScraper
from .async_base import AsyncBaseScraper
from .storage import JSONStorage, CSVStorage

__all__ = [
    "ScraperError",
    "NotLoggedInError",
    "RateLimitedError",
    "CaptchaError",
    "ContentNotFoundError",
    "BrowserManager",
    "create_browser",
    "get_browser",
    "BaseScraper",
    "AsyncBaseScraper",
    "JSONStorage",
    "CSVStorage",
]
