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
from .user_agent import (
    UAProfile,
    get_random_profile,
    get_random_user_agent,
    build_browser_headers,
    build_api_headers,
)
from .proxy import ProxyInfo, ProxyPoolConfig, ProxyPool
from .rate_limiter import RateLimiterConfig, RateLimiter, AsyncRateLimiter
from .captcha import (
    CaptchaType,
    CaptchaChallenge,
    CaptchaSolution,
    CaptchaSolver,
    NullCaptchaSolver,
)

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
    # user_agent
    "UAProfile",
    "get_random_profile",
    "get_random_user_agent",
    "build_browser_headers",
    "build_api_headers",
    # proxy
    "ProxyInfo",
    "ProxyPoolConfig",
    "ProxyPool",
    # rate_limiter
    "RateLimiterConfig",
    "RateLimiter",
    "AsyncRateLimiter",
    # captcha
    "CaptchaType",
    "CaptchaChallenge",
    "CaptchaSolution",
    "CaptchaSolver",
    "NullCaptchaSolver",
]
