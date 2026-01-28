"""Unified exception hierarchy for all scrapers."""


class ScraperError(Exception):
    """Base exception for all scraper errors."""

    pass


class NotLoggedInError(ScraperError):
    """Raised when session is not authenticated."""

    pass


class RateLimitedError(ScraperError):
    """Raised when rate limited by the target site."""

    pass


class CaptchaError(ScraperError):
    """Raised when CAPTCHA verification is required."""

    pass


class ContentNotFoundError(ScraperError):
    """Raised when requested content is not found."""

    pass


class PaywallError(ScraperError):
    """Raised when content is behind a paywall."""

    pass


class AuthenticationError(ScraperError):
    """Raised when authentication fails."""

    pass


class SessionExpiredError(NotLoggedInError):
    """Raised when session/cookies have expired."""

    pass
