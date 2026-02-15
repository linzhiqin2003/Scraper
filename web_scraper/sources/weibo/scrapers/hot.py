"""Weibo hot-search scraper with API-first and Playwright fallback."""

from __future__ import annotations

import json
import re
from typing import Any, Optional
from urllib.parse import quote_plus, urljoin

import requests

from ....core.browser import get_state_path
from ....core.rate_limiter import RateLimiter
from ..auth import LoginStatus, _classify_url, _open_weibo_page
from ..config import (
    BASE_URL,
    DEFAULT_HEADERS,
    HOT_SEARCH_API,
    HOT_SEARCH_URL,
    LOGGED_OUT_KEYWORDS,
    RATE_LIMIT_KEYWORDS,
    SOURCE_NAME,
    Timeouts,
)
from ..models import WeiboHotItem, WeiboHotResponse
from .search import LoginRequiredError, RateLimitedError, SearchError


def _clean_text(value: Optional[str]) -> str:
    """Normalize spaces for extracted text."""
    if not value:
        return ""
    compact = re.sub(r"\s+", " ", value)
    return compact.replace("\u200b", "").strip()


def _safe_int(value: Any) -> Optional[int]:
    """Best-effort conversion to integer, supporting 万/亿."""
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)

    text = _clean_text(str(value)).replace(",", "")
    if not text:
        return None

    match = re.search(r"(\d+(?:\.\d+)?)\s*([万亿]?)", text)
    if not match:
        return None

    number = float(match.group(1))
    unit = match.group(2)
    if unit == "万":
        number *= 10_000
    elif unit == "亿":
        number *= 100_000_000
    return int(number)


def _to_absolute_url(url: Optional[str], base_url: str = BASE_URL) -> Optional[str]:
    """Convert relative URL into absolute URL."""
    if not url:
        return None
    normalized = url.strip()
    if not normalized:
        return None
    if normalized.startswith("//"):
        return f"https:{normalized}"
    return urljoin(base_url, normalized)


def _build_weibo_search_url(query: str) -> str:
    """Build Weibo search URL from keyword/topic string."""
    return f"https://s.weibo.com/weibo?q={quote_plus(query)}"


class HotScraper:
    """Fetch Weibo hot search list.

    Strategy:
    1. HTTP API (`/ajax/side/hotSearch`)
    2. Playwright DOM parsing fallback
    """

    def __init__(
        self,
        timeout: int = 30,
        use_playwright_fallback: bool = True,
        rate_limiter: Optional[RateLimiter] = None,
    ) -> None:
        self.timeout = timeout
        self.use_playwright_fallback = use_playwright_fallback
        self.rate_limiter = rate_limiter
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self.cookies_loaded = self._load_cookies_from_state()

    def scrape(
        self,
        limit: Optional[int] = 50,
        headless: bool = True,
    ) -> WeiboHotResponse:
        """Fetch hot-search topics with optional result limit."""
        max_results = limit if limit and limit > 0 else None
        errors: list[Exception] = []

        try:
            return self._scrape_via_http(max_results=max_results)
        except SearchError as exc:
            errors.append(exc)

        if self.use_playwright_fallback:
            try:
                return self._scrape_via_playwright(max_results=max_results, headless=headless)
            except SearchError as exc:
                errors.append(exc)

        details = "; ".join(str(err) for err in errors if str(err))
        raise SearchError(details or "Failed to fetch Weibo hot-search topics.")

    def _load_cookies_from_state(self) -> bool:
        """Load cookies from Playwright storage_state JSON."""
        state_file = get_state_path(SOURCE_NAME)
        if not state_file.exists():
            return False

        try:
            state = json.loads(state_file.read_text())
        except Exception:
            return False

        loaded = 0
        for cookie in state.get("cookies", []):
            name = cookie.get("name")
            value = cookie.get("value")
            if not name or value is None:
                continue

            domain = cookie.get("domain") or ".weibo.com"
            path = cookie.get("path") or "/"
            self.session.cookies.set(name, value, domain=domain, path=path)
            loaded += 1

            if domain.startswith("."):
                self.session.cookies.set(name, value, domain=domain[1:], path=path)

        return loaded > 0

    def _scrape_via_http(self, max_results: Optional[int]) -> WeiboHotResponse:
        """API-first hot-search implementation."""
        if not self.cookies_loaded:
            raise LoginRequiredError("No saved Weibo session found. Run 'scraper weibo login' first.")

        try:
            response = self.session.get(
                HOT_SEARCH_API,
                timeout=self.timeout,
                allow_redirects=True,
                headers={
                    **DEFAULT_HEADERS,
                    "Accept": "application/json,text/plain,*/*",
                    "Referer": HOT_SEARCH_URL,
                },
            )
        except requests.RequestException as exc:
            raise SearchError(f"HTTP request failed: {exc}") from exc

        if response.status_code >= 400:
            raise SearchError(f"Weibo returned HTTP {response.status_code} for hot search API.")

        final_url = str(response.url)
        body = response.text
        if self._looks_logged_out(final_url, body):
            raise LoginRequiredError("Saved session expired or login required.")
        if self._looks_rate_limited(body):
            raise RateLimitedError("Weibo requires security verification or rate-limited this request.")

        try:
            payload = response.json()
        except ValueError as exc:
            raise SearchError("Expected JSON response from hot search API.") from exc

        if not isinstance(payload, dict):
            raise SearchError("Unexpected hot search API response format.")

        if payload.get("ok") == 0:
            message = str(payload.get("msg") or payload.get("message") or "API returned ok=0")
            lower = message.lower()
            if "登录" in message or "login" in lower:
                raise LoginRequiredError("Saved session expired or login required.")
            if "频繁" in message or "验证" in message or "captcha" in lower:
                raise RateLimitedError("Weibo requires security verification or rate-limited this request.")
            raise SearchError(f"Weibo API error: {message}")

        realtime = (payload.get("data") or {}).get("realtime")
        if not isinstance(realtime, list):
            realtime = []

        items = self._parse_api_rows(realtime, max_results=max_results)
        if not items:
            raise SearchError("Hot search API returned no realtime rows.")

        return WeiboHotResponse(
            method="http",
            current_url=HOT_SEARCH_URL,
            items=items,
            total_available=len(realtime),
            limit=max_results,
        )

    def _scrape_via_playwright(
        self,
        max_results: Optional[int],
        headless: bool,
    ) -> WeiboHotResponse:
        """Playwright fallback when API is blocked or unavailable."""
        state_file = get_state_path(SOURCE_NAME)
        if not state_file.exists():
            raise LoginRequiredError("No saved Weibo session found. Run 'scraper weibo login' first.")

        try:
            with _open_weibo_page(headless=headless, use_storage_state=True) as page:
                page.goto(HOT_SEARCH_URL, wait_until="domcontentloaded", timeout=Timeouts.NAVIGATION)
                page.wait_for_timeout(1500)

                if _classify_url(page.url) == LoginStatus.LOGGED_OUT:
                    raise LoginRequiredError("Saved session expired or login required.")

                body_preview = page.evaluate(
                    "() => document.body ? document.body.innerText.slice(0, 6000) : ''"
                )
                if self._looks_rate_limited(body_preview):
                    raise RateLimitedError("Weibo requires security verification or rate-limited this request.")

                raw_rows = page.evaluate(
                    r"""
                    (maxRows) => {
                      const norm = (v) => (v ? v.replace(/\s+/g, ' ').trim() : '');
                      const rows = Array.from(document.querySelectorAll('main [data-index][data-active]'));

                      const parseMetric = (value) => {
                        const text = norm(value).replace(/,/g, '');
                        if (!text) return null;
                        const m = text.match(/(\d+(?:\.\d+)?)([万亿]?)/);
                        if (!m) return null;
                        let num = parseFloat(m[1]);
                        if (m[2] === '万') num *= 10000;
                        if (m[2] === '亿') num *= 100000000;
                        return Math.floor(num);
                      };

                      const parsed = rows.map((row) => {
                        const topicEl = row.querySelector('a[href*="/weibo?q="]');
                        const numEl = row.querySelector('div[class*="num"] span');
                        const badgeEl = row.querySelector('.wbpro-icon-search-2');

                        const rowText = norm(row.textContent || '');
                        const rankMatch = rowText.match(/^(\d{1,3})/);
                        const trailingMetric = rowText.match(/(\d[\d,.]*\s*[万亿]?)$/);

                        const rank = rankMatch ? Number(rankMatch[1]) : null;
                        const hotnessText = norm(numEl ? numEl.textContent : (trailingMetric ? trailingMetric[1] : ''));

                        return {
                          topic: norm(topicEl ? topicEl.textContent : ''),
                          href: topicEl ? topicEl.getAttribute('href') : null,
                          rank,
                          heat: parseMetric(hotnessText),
                          label: norm(badgeEl ? badgeEl.textContent : ''),
                          dataIndex: row.getAttribute('data-index'),
                        };
                      }).filter((item) => item.topic);

                      return typeof maxRows === 'number' && maxRows > 0
                        ? parsed.slice(0, maxRows)
                        : parsed;
                    }
                    """,
                    max_results,
                )

                if not isinstance(raw_rows, list) or not raw_rows:
                    raise SearchError("Playwright parse returned no hot-search rows.")

                items = self._parse_dom_rows(raw_rows, max_results=max_results)
                if not items:
                    raise SearchError("Playwright parse returned no usable hot-search rows.")

                return WeiboHotResponse(
                    method="playwright",
                    current_url=page.url,
                    items=items,
                    total_available=len(raw_rows),
                    limit=max_results,
                )

        except LoginRequiredError:
            raise
        except RateLimitedError:
            raise
        except Exception as exc:
            raise SearchError(f"Playwright fallback failed: {exc}") from exc

    def _parse_api_rows(
        self,
        rows: list[Any],
        max_results: Optional[int],
    ) -> list[WeiboHotItem]:
        """Convert hotSearch API realtime rows into model output."""
        items: list[WeiboHotItem] = []

        for raw in rows:
            if not isinstance(raw, dict):
                continue

            topic = _clean_text(str(raw.get("word") or raw.get("note") or ""))
            if not topic:
                continue

            word_scheme = _clean_text(str(raw.get("word_scheme") or ""))
            search_url = self._resolve_topic_url(
                href=raw.get("url") or raw.get("href"),
                word_scheme=word_scheme,
                topic=topic,
            )

            label = _clean_text(
                str(raw.get("label_name") or raw.get("icon_desc") or raw.get("small_icon_desc") or "")
            )
            rank = _safe_int(raw.get("realpos"))
            if rank is None:
                rank = _safe_int(raw.get("rank"))

            items.append(
                WeiboHotItem(
                    rank=rank,
                    topic=topic,
                    word_scheme=word_scheme or None,
                    search_url=search_url,
                    heat=_safe_int(raw.get("num")),
                    label=label or None,
                    topic_flag=_safe_int(raw.get("topic_flag")),
                    icon=_to_absolute_url(raw.get("icon")),
                )
            )

            if max_results is not None and len(items) >= max_results:
                break

        return items

    def _parse_dom_rows(
        self,
        rows: list[Any],
        max_results: Optional[int],
    ) -> list[WeiboHotItem]:
        """Convert Playwright DOM payload into model output."""
        items: list[WeiboHotItem] = []

        for row in rows:
            if not isinstance(row, dict):
                continue

            topic = _clean_text(str(row.get("topic") or ""))
            if not topic:
                continue

            rank = _safe_int(row.get("rank"))
            if rank is None:
                data_index = _safe_int(row.get("dataIndex"))
                if data_index is not None:
                    rank = data_index + 1

            items.append(
                WeiboHotItem(
                    rank=rank,
                    topic=topic,
                    word_scheme=None,
                    search_url=self._resolve_topic_url(
                        href=row.get("href"),
                        word_scheme=None,
                        topic=topic,
                    ),
                    heat=_safe_int(row.get("heat")),
                    label=_clean_text(str(row.get("label") or "")) or None,
                    topic_flag=None,
                    icon=None,
                )
            )

            if max_results is not None and len(items) >= max_results:
                break

        return items

    def _resolve_topic_url(
        self,
        *,
        href: Optional[str],
        word_scheme: Optional[str],
        topic: str,
    ) -> str:
        """Resolve best-effort search URL for a hot topic."""
        absolute_href = _to_absolute_url(href, BASE_URL)
        if absolute_href:
            return absolute_href

        if word_scheme:
            return _build_weibo_search_url(word_scheme)

        return _build_weibo_search_url(topic)

    def _looks_logged_out(self, url: str, html: str) -> bool:
        """Detect whether response indicates unauthenticated state."""
        if _classify_url(url) == LoginStatus.LOGGED_OUT:
            return True
        body = (html or "").lower()
        return any(marker.lower() in body for marker in LOGGED_OUT_KEYWORDS)

    def _looks_rate_limited(self, body: str) -> bool:
        """Detect anti-crawl or CAPTCHA pages."""
        content = (body or "").lower()
        return any(keyword.lower() in content for keyword in RATE_LIMIT_KEYWORDS)
