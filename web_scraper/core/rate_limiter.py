"""Rate limiter with sliding window and adaptive backoff.

Thread-safe synchronous implementation + async wrapper for async sources.
"""

import asyncio
import logging
import random
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class RateLimiterConfig:
    """Rate limiter configuration."""

    min_delay: float = 2.0
    max_delay: float = 5.0
    requests_per_minute: int = 15
    requests_per_hour: int = 500
    backoff_base: float = 5.0
    backoff_max: float = 60.0
    jitter_range: float = 1.0


class RateLimiter:
    """Thread-safe sliding window rate limiter with adaptive backoff.

    Usage:
        limiter = RateLimiter()
        limiter.wait()        # blocks until safe to proceed
        # ... make request ...
        limiter.record_success()
        # or
        limiter.record_rate_limit()   # triggers exponential backoff
    """

    def __init__(self, config: Optional[RateLimiterConfig] = None) -> None:
        self._config = config or RateLimiterConfig()
        self._lock = threading.Lock()

        # Sliding window timestamps
        self._minute_window: deque = deque()
        self._hour_window: deque = deque()

        # Backoff state
        self._consecutive_failures: int = 0
        self._last_request_time: float = 0.0

    @property
    def config(self) -> RateLimiterConfig:
        return self._config

    def wait(self) -> None:
        """Block until it's safe to make a request.

        Respects per-minute and per-hour limits, minimum delay between requests,
        and any active backoff from recent failures.
        """
        with self._lock:
            now = time.monotonic()

            # Clean expired entries
            self._clean_windows(now)

            # Calculate minimum wait time
            wait_time = 0.0

            # 1. Respect min delay since last request
            if self._last_request_time > 0:
                elapsed = now - self._last_request_time
                base_delay = random.uniform(
                    self._config.min_delay, self._config.max_delay
                )
                if elapsed < base_delay:
                    wait_time = max(wait_time, base_delay - elapsed)

            # 2. Per-minute rate limit
            if len(self._minute_window) >= self._config.requests_per_minute:
                oldest = self._minute_window[0]
                wait_until = oldest + 60.0
                if wait_until > now:
                    wait_time = max(wait_time, wait_until - now)

            # 3. Per-hour rate limit
            if len(self._hour_window) >= self._config.requests_per_hour:
                oldest = self._hour_window[0]
                wait_until = oldest + 3600.0
                if wait_until > now:
                    wait_time = max(wait_time, wait_until - now)

            # 4. Backoff from failures
            if self._consecutive_failures > 0:
                backoff = min(
                    self._config.backoff_base * (2 ** (self._consecutive_failures - 1)),
                    self._config.backoff_max,
                )
                backoff += random.uniform(0, self._config.jitter_range)
                wait_time = max(wait_time, backoff)

        if wait_time > 0:
            logger.debug("Rate limiter waiting %.1fs", wait_time)
            time.sleep(wait_time)

        # Record the request time
        with self._lock:
            now = time.monotonic()
            self._last_request_time = now
            self._minute_window.append(now)
            self._hour_window.append(now)

    def record_success(self) -> None:
        """Record a successful request, resetting backoff."""
        with self._lock:
            self._consecutive_failures = 0

    def record_rate_limit(self) -> None:
        """Record a rate limit response, triggering exponential backoff."""
        with self._lock:
            self._consecutive_failures += 1
            logger.warning(
                "Rate limited (consecutive failures: %d, next backoff: %.1fs)",
                self._consecutive_failures,
                min(
                    self._config.backoff_base * (2 ** (self._consecutive_failures - 1)),
                    self._config.backoff_max,
                ),
            )

    def record_block(self) -> None:
        """Record an IP block or severe rate limit, applying aggressive backoff."""
        with self._lock:
            self._consecutive_failures = max(self._consecutive_failures + 2, 4)
            logger.warning(
                "Block detected (severity: %d, next backoff: %.1fs)",
                self._consecutive_failures,
                min(
                    self._config.backoff_base * (2 ** (self._consecutive_failures - 1)),
                    self._config.backoff_max,
                ),
            )

    def get_stats(self) -> dict:
        """Get current rate limiter statistics."""
        with self._lock:
            now = time.monotonic()
            self._clean_windows(now)
            return {
                "requests_last_minute": len(self._minute_window),
                "requests_last_hour": len(self._hour_window),
                "consecutive_failures": self._consecutive_failures,
                "limits": {
                    "per_minute": self._config.requests_per_minute,
                    "per_hour": self._config.requests_per_hour,
                },
            }

    def _clean_windows(self, now: float) -> None:
        """Remove expired entries from sliding windows. Must hold _lock."""
        minute_cutoff = now - 60.0
        while self._minute_window and self._minute_window[0] < minute_cutoff:
            self._minute_window.popleft()

        hour_cutoff = now - 3600.0
        while self._hour_window and self._hour_window[0] < hour_cutoff:
            self._hour_window.popleft()


class AsyncRateLimiter:
    """Async wrapper around RateLimiter for async sources (XHS, Weibo).

    Delegates blocking wait() to a thread so it doesn't block the event loop.
    """

    def __init__(self, config: Optional[RateLimiterConfig] = None) -> None:
        self._sync = RateLimiter(config)

    @property
    def config(self) -> RateLimiterConfig:
        return self._sync.config

    async def wait(self) -> None:
        """Async wait — runs the blocking wait in a thread."""
        await asyncio.to_thread(self._sync.wait)

    def record_success(self) -> None:
        self._sync.record_success()

    def record_rate_limit(self) -> None:
        self._sync.record_rate_limit()

    def record_block(self) -> None:
        self._sync.record_block()

    def get_stats(self) -> dict:
        return self._sync.get_stats()
