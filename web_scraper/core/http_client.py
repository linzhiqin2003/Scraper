"""HTTP client with TLS fingerprint impersonation.

Wraps curl-cffi to provide Chrome-like TLS fingerprints, preventing
sites from detecting and blocking Python HTTP requests.

Usage:
    from web_scraper.core.http_client import HttpClient

    client = HttpClient(cookies={"auth": "token"})
    resp = client.get("https://example.com/api", headers={"x-custom": "val"})
    data = resp.json()

    # POST with JSON body
    resp = client.post("https://example.com/api", json={"key": "value"})
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from curl_cffi import requests as cffi_requests
from curl_cffi.requests import Response

logger = logging.getLogger(__name__)

# Supported browser impersonation targets (curl-cffi)
IMPERSONATE_TARGETS = [
    "chrome",       # latest stable
    "chrome131",
    "chrome124",
    "chrome120",
    "chrome116",
    "chrome110",
    "safari",
    "safari17_0",
]

DEFAULT_IMPERSONATE = "chrome131"


@dataclass
class HttpClient:
    """HTTP client with TLS fingerprint impersonation via curl-cffi.

    Attributes:
        cookies: Cookie dict to send with all requests.
        headers: Default headers merged into every request.
        impersonate: Browser to impersonate for TLS fingerprint.
        timeout: Request timeout in seconds.
        follow_redirects: Whether to follow HTTP redirects.
    """

    cookies: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    impersonate: str = DEFAULT_IMPERSONATE
    timeout: int = 30
    follow_redirects: bool = True

    def get(
        self,
        url: str,
        *,
        params: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
        cookies: Optional[dict[str, str]] = None,
        **kwargs: Any,
    ) -> Response:
        """Send GET request with TLS fingerprint impersonation."""
        return self._request("GET", url, params=params, headers=headers,
                             cookies=cookies, **kwargs)

    def post(
        self,
        url: str,
        *,
        json: Optional[Any] = None,
        data: Optional[Any] = None,
        params: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
        cookies: Optional[dict[str, str]] = None,
        **kwargs: Any,
    ) -> Response:
        """Send POST request with TLS fingerprint impersonation."""
        return self._request("POST", url, json=json, data=data, params=params,
                             headers=headers, cookies=cookies, **kwargs)

    def put(
        self,
        url: str,
        *,
        json: Optional[Any] = None,
        data: Optional[Any] = None,
        headers: Optional[dict[str, str]] = None,
        cookies: Optional[dict[str, str]] = None,
        **kwargs: Any,
    ) -> Response:
        """Send PUT request with TLS fingerprint impersonation."""
        return self._request("PUT", url, json=json, data=data,
                             headers=headers, cookies=cookies, **kwargs)

    def _request(
        self,
        method: str,
        url: str,
        *,
        params: Optional[dict[str, Any]] = None,
        json: Optional[Any] = None,
        data: Optional[Any] = None,
        headers: Optional[dict[str, str]] = None,
        cookies: Optional[dict[str, str]] = None,
        **kwargs: Any,
    ) -> Response:
        """Execute HTTP request with merged defaults and TLS impersonation."""
        merged_headers = {**self.headers}
        if headers:
            merged_headers.update(headers)

        merged_cookies = {**self.cookies}
        if cookies:
            merged_cookies.update(cookies)

        resp = cffi_requests.request(
            method,
            url,
            params=params,
            json=json,
            data=data,
            headers=merged_headers,
            cookies=merged_cookies or None,
            impersonate=self.impersonate,
            timeout=self.timeout,
            allow_redirects=self.follow_redirects,
            **kwargs,
        )

        logger.debug(
            "%s %s → %d (%d bytes)",
            method, url[:100], resp.status_code, len(resp.content),
        )
        return resp

    def raise_for_status(self, resp: Response, context: str = "") -> None:
        """Raise RuntimeError with context on non-200 responses."""
        if resp.status_code == 200:
            return
        prefix = f"{context}: " if context else ""
        body_preview = resp.text[:500] if resp.text else "(empty)"
        if resp.status_code == 401:
            raise RuntimeError(f"{prefix}Authentication failed (401). Check cookies/tokens.")
        if resp.status_code == 403:
            raise RuntimeError(f"{prefix}Access forbidden (403).")
        if resp.status_code == 429:
            raise RuntimeError(f"{prefix}Rate limit exceeded (429).")
        raise RuntimeError(f"{prefix}HTTP {resp.status_code} — {body_preview}")
