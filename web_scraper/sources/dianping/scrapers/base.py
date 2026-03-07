"""Shared HTTP and parsing helpers for Dianping scrapers."""
from __future__ import annotations

import json
import re
from typing import Optional
from urllib.parse import urljoin

import httpx

from ..config import (
    DEFAULT_HEADERS,
    JSON_HEADERS,
    DEFAULT_TIMEOUT,
    VERIFY_BASE_URL,
    WWW_BASE_URL,
)
from ..cookies import load_cookies


class DianpingBaseScraper:
    """Common client wrapper for Dianping scrapers."""

    def __init__(self, cookies: Optional[httpx.Cookies] = None):
        self.cookies = cookies or load_cookies()
        self.client = httpx.Client(
            cookies=self.cookies,
            headers=DEFAULT_HEADERS,
            follow_redirects=True,
            timeout=DEFAULT_TIMEOUT,
            http2=True,
        )

    def close(self) -> None:
        """Close underlying HTTP client."""
        self.client.close()

    def __enter__(self) -> "DianpingBaseScraper":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def get_text(self, url: str, *, referer: Optional[str] = None) -> str:
        """GET HTML content and block on verify pages."""
        headers = dict(DEFAULT_HEADERS)
        if referer:
            headers["Referer"] = referer

        resp = self.client.get(url, headers=headers)
        self._raise_for_verify(resp)
        return resp.text

    def get_json(self, url: str, *, referer: Optional[str] = None, params: Optional[dict] = None) -> dict:
        """GET a JSON response."""
        headers = dict(JSON_HEADERS)
        if referer:
            headers["Referer"] = referer
        resp = self.client.get(url, headers=headers, params=params)
        self._raise_for_verify(resp)
        return resp.json()

    def post_json(
        self,
        url: str,
        *,
        body: dict,
        referer: Optional[str] = None,
        origin: Optional[str] = None,
    ) -> dict:
        """POST a JSON request and return JSON response."""
        headers = dict(JSON_HEADERS)
        headers["Content-Type"] = "application/json"
        if referer:
            headers["Referer"] = referer
        if origin:
            headers["Origin"] = origin
        resp = self.client.post(url, headers=headers, json=body)
        self._raise_for_verify(resp)
        return resp.json()

    @staticmethod
    def _raise_for_verify(resp: httpx.Response) -> None:
        url = str(resp.url)
        if VERIFY_BASE_URL in url or "verify.meituan.com" in resp.text:
            raise RuntimeError("触发大众点评验证页，当前环境下无法继续抓取")


def extract_script_json(html: str, script_id: str) -> dict:
    """Extract JSON payload from a script tag by id."""
    pattern = rf'<script id="{re.escape(script_id)}"[^>]*>(.*?)</script>'
    match = re.search(pattern, html, re.S)
    if not match:
        raise RuntimeError(f"未找到脚本数据：{script_id}")
    return json.loads(match.group(1))


def extract_assigned_json(html: str, marker: str) -> dict:
    """Extract an assigned JSON object like `window.foo = {...}`."""
    marker_index = html.find(marker)
    if marker_index == -1:
        raise RuntimeError(f"未找到内联数据：{marker}")

    start = html.find("{", marker_index + len(marker))
    if start == -1:
        raise RuntimeError(f"未找到 JSON 起始位置：{marker}")

    return json.loads(extract_balanced_json(html, start))


def extract_balanced_json(text: str, start_index: int) -> str:
    """Extract a balanced JSON object from arbitrary text."""
    depth = 0
    in_string = False
    escaped = False

    for index in range(start_index, len(text)):
        ch = text[index]

        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue

        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start_index:index + 1]

    raise RuntimeError("内联 JSON 解析失败：未找到结束括号")


def clean_int(text: str | None) -> Optional[int]:
    """Extract an integer from free-form text."""
    if not text:
        return None
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


def ensure_absolute_url(url: str) -> str:
    """Resolve Dianping relative URLs."""
    return urljoin(WWW_BASE_URL, url)
