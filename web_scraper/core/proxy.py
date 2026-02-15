"""Proxy pool manager with health tracking and automatic rotation.

Supports HTTP API-based proxy providers. Thread-safe.
"""

import json
import logging
import random
import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class ProxyInfo:
    """A single proxy with health metrics."""

    url: str  # e.g., "http://user:pass@host:port" or "http://host:port"
    successes: int = 0
    failures: int = 0
    blocks: int = 0
    last_used: float = 0.0
    banned_until: float = 0.0

    @property
    def score(self) -> float:
        """Health score: higher is better."""
        total = self.successes + self.failures + self.blocks
        if total == 0:
            return 0.5  # neutral score for unused proxies
        success_rate = self.successes / total
        # Penalize blocks more heavily
        block_penalty = self.blocks * 0.2
        return max(0.0, success_rate - block_penalty)

    @property
    def is_banned(self) -> bool:
        return time.monotonic() < self.banned_until


@dataclass
class ProxyPoolConfig:
    """Proxy pool configuration."""

    api_url: Optional[str] = None
    ban_duration: float = 300.0  # seconds to ban a failed proxy
    refresh_interval: float = 600.0  # auto-refresh every N seconds
    min_pool_size: int = 3
    max_pool_size: int = 50


class ProxyPool:
    """Proxy pool with health tracking and automatic rotation.

    Usage:
        pool = ProxyPool(config=ProxyPoolConfig(api_url="http://api.proxy.com/get?num=10"))
        pool.refresh()  # fetch proxies from API

        proxy = pool.get_best()
        if proxy:
            # use proxy.url in httpx or Playwright
            pool.record_success(proxy.url)
    """

    def __init__(self, config: Optional[ProxyPoolConfig] = None) -> None:
        self._config = config or ProxyPoolConfig()
        self._lock = threading.Lock()
        self._proxies: Dict[str, ProxyInfo] = {}
        self._last_refresh: float = 0.0

    @property
    def config(self) -> ProxyPoolConfig:
        return self._config

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._proxies)

    def add(self, proxy_url: str) -> None:
        """Add a single proxy to the pool."""
        with self._lock:
            if proxy_url not in self._proxies:
                self._proxies[proxy_url] = ProxyInfo(url=proxy_url)

    def add_many(self, proxy_urls: List[str]) -> int:
        """Add multiple proxies. Returns count of newly added."""
        added = 0
        with self._lock:
            for url in proxy_urls:
                if url and url not in self._proxies:
                    self._proxies[url] = ProxyInfo(url=url)
                    added += 1
        return added

    def refresh(self) -> int:
        """Fetch new proxies from the configured API.

        Returns:
            Number of new proxies added.
        """
        if not self._config.api_url:
            return 0

        try:
            resp = httpx.get(self._config.api_url, timeout=10.0)
            resp.raise_for_status()

            proxies = self._parse_proxy_response(resp.text)
            added = self.add_many(proxies)

            with self._lock:
                self._last_refresh = time.monotonic()

            logger.info("Refreshed proxy pool: %d new, %d total", added, self.size)
            return added

        except Exception as e:
            logger.warning("Failed to refresh proxy pool: %s", e)
            return 0

    def get_best(self) -> Optional[ProxyInfo]:
        """Return the proxy with the highest health score."""
        self._maybe_auto_refresh()

        with self._lock:
            available = [p for p in self._proxies.values() if not p.is_banned]
            if not available:
                return None

            available.sort(key=lambda p: p.score, reverse=True)
            proxy = available[0]
            proxy.last_used = time.monotonic()
            return proxy

    def get_random(self) -> Optional[ProxyInfo]:
        """Return a random available proxy, weighted by health score."""
        self._maybe_auto_refresh()

        with self._lock:
            available = [p for p in self._proxies.values() if not p.is_banned]
            if not available:
                return None

            # Weighted random selection by score
            weights = [max(p.score, 0.01) for p in available]
            total = sum(weights)
            r = random.uniform(0, total)
            cumulative = 0.0
            for proxy, w in zip(available, weights):
                cumulative += w
                if r <= cumulative:
                    proxy.last_used = time.monotonic()
                    return proxy

            # Fallback
            proxy = available[-1]
            proxy.last_used = time.monotonic()
            return proxy

    def record_success(self, proxy_url: str) -> None:
        """Record a successful request through a proxy."""
        with self._lock:
            if proxy_url in self._proxies:
                self._proxies[proxy_url].successes += 1

    def record_failure(self, proxy_url: str) -> None:
        """Record a failed request through a proxy."""
        with self._lock:
            if proxy_url in self._proxies:
                p = self._proxies[proxy_url]
                p.failures += 1
                # Ban if too many failures
                if p.failures >= 3 and p.score < 0.3:
                    p.banned_until = time.monotonic() + self._config.ban_duration
                    logger.info("Proxy banned for %ds: %s", self._config.ban_duration, proxy_url)

    def record_block(self, proxy_url: str) -> None:
        """Record an IP block detected through this proxy."""
        with self._lock:
            if proxy_url in self._proxies:
                p = self._proxies[proxy_url]
                p.blocks += 1
                # Immediate ban on block
                p.banned_until = time.monotonic() + self._config.ban_duration * 2
                logger.warning("Proxy blocked and banned: %s", proxy_url)

    def get_stats(self) -> dict:
        """Get pool statistics."""
        with self._lock:
            proxies = list(self._proxies.values())

        available = [p for p in proxies if not p.is_banned]
        banned = [p for p in proxies if p.is_banned]

        return {
            "total": len(proxies),
            "available": len(available),
            "banned": len(banned),
            "api_url": self._config.api_url or "not configured",
            "proxies": [
                {
                    "url": p.url[:30] + "..." if len(p.url) > 30 else p.url,
                    "score": round(p.score, 2),
                    "successes": p.successes,
                    "failures": p.failures,
                    "blocks": p.blocks,
                    "banned": p.is_banned,
                }
                for p in sorted(proxies, key=lambda x: x.score, reverse=True)[:20]
            ],
        }

    def _parse_proxy_response(self, text: str) -> List[str]:
        """Parse proxy API response (supports JSON and plain text)."""
        text = text.strip()

        # Try JSON
        if text.startswith(("{", "[")):
            try:
                data = json.loads(text)
                if isinstance(data, list):
                    return [self._normalize_proxy(p) for p in data if p]
                if isinstance(data, dict):
                    # Common API formats
                    proxies = data.get("data", data.get("proxies", data.get("result", [])))
                    if isinstance(proxies, list):
                        return [self._normalize_proxy(p) for p in proxies if p]
            except json.JSONDecodeError:
                pass

        # Plain text: one proxy per line
        results = []
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                results.append(self._normalize_proxy(line))
        return results

    def _normalize_proxy(self, proxy: object) -> str:
        """Normalize proxy to URL format."""
        if isinstance(proxy, dict):
            host = proxy.get("ip", proxy.get("host", ""))
            port = proxy.get("port", "")
            user = proxy.get("user", proxy.get("username", ""))
            passwd = proxy.get("pass", proxy.get("password", ""))
            scheme = proxy.get("scheme", proxy.get("protocol", "http"))
            if user and passwd:
                return f"{scheme}://{user}:{passwd}@{host}:{port}"
            return f"{scheme}://{host}:{port}"

        s = str(proxy).strip()
        if not s.startswith(("http://", "https://", "socks")):
            s = "http://" + s
        return s

    def _maybe_auto_refresh(self) -> None:
        """Auto-refresh if pool is low or stale."""
        if not self._config.api_url:
            return

        with self._lock:
            now = time.monotonic()
            available_count = sum(1 for p in self._proxies.values() if not p.is_banned)
            stale = (now - self._last_refresh) > self._config.refresh_interval

        if available_count < self._config.min_pool_size or stale:
            self.refresh()
