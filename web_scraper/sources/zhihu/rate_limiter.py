"""Backward compatibility: re-export from core.rate_limiter."""

from ...core.rate_limiter import RateLimiterConfig, RateLimiter

__all__ = ["RateLimiterConfig", "RateLimiter"]
