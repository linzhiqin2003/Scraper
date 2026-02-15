"""Weibo search scraper with HTTP-first and Playwright fallback."""

from __future__ import annotations

import json
import re
from typing import Any, Optional
from urllib.parse import urlencode, urljoin

import requests
from bs4 import BeautifulSoup

from ....core.browser import get_state_path
from ....core.rate_limiter import RateLimiter
from ..auth import LoginStatus, _classify_url, _open_weibo_page
from ..config import (
    DEFAULT_HEADERS,
    LOGGED_OUT_KEYWORDS,
    RATE_LIMIT_KEYWORDS,
    SEARCH_BASE_URL,
    SOURCE_NAME,
    Selectors,
    Timeouts,
)
from ..models import WeiboSearchResponse, WeiboSearchResult


class SearchError(Exception):
    """Generic error while searching Weibo."""


class LoginRequiredError(SearchError):
    """Saved session is missing or no longer valid."""


class RateLimitedError(SearchError):
    """Request has been blocked by rate limiting or verification."""


def _clean_text(value: Optional[str]) -> str:
    """Normalize spaces for extracted text."""
    if not value:
        return ""
    compact = re.sub(r"\s+", " ", value)
    return compact.replace("\u200b", "").strip()


def _parse_metric_count(text: str) -> Optional[int]:
    """Parse count text like '1.2万' or '23'."""
    normalized = _clean_text(text).replace(",", "")
    if not normalized:
        return None

    if normalized in {"转发", "评论", "赞"}:
        return None

    match = re.search(r"(\d+(?:\.\d+)?)\s*([万亿]?)", normalized)
    if not match:
        return None

    try:
        value = float(match.group(1))
    except ValueError:
        return None

    unit = match.group(2)
    if unit == "万":
        value *= 10_000
    elif unit == "亿":
        value *= 100_000_000

    return int(value)


def _to_absolute_url(url: Optional[str], base_url: str) -> Optional[str]:
    """Return absolute URL when possible."""
    if not url:
        return None
    cleaned = url.strip()
    if not cleaned:
        return None
    if cleaned.startswith("//"):
        return f"https:{cleaned}"
    return urljoin(base_url, cleaned)


def _build_search_url(query: str, page: int) -> str:
    """Build Weibo search URL with query parameters."""
    params = {"q": query}
    if page > 1:
        params["page"] = str(page)
    return f"{SEARCH_BASE_URL}?{urlencode(params)}"


class SearchScraper:
    """Weibo search scraper.

    Strategy:
    1. HTTP request with saved session cookies (fast path)
    2. Playwright with saved storage state (fallback)
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

    def search(
        self,
        query: str,
        pages: int = 1,
        limit: Optional[int] = 20,
        headless: bool = True,
    ) -> WeiboSearchResponse:
        """Search Weibo and return parsed cards."""
        keyword = query.strip()
        if not keyword:
            raise SearchError("Search query cannot be empty.")

        max_pages = max(1, pages)
        max_results = limit if limit and limit > 0 else None

        errors: list[Exception] = []

        try:
            return self._search_via_http(keyword, max_pages=max_pages, max_results=max_results)
        except SearchError as exc:
            errors.append(exc)

        if self.use_playwright_fallback:
            try:
                return self._search_via_playwright(
                    keyword,
                    max_pages=max_pages,
                    max_results=max_results,
                    headless=headless,
                )
            except SearchError as exc:
                errors.append(exc)

        details = "; ".join(str(err) for err in errors if str(err))
        raise SearchError(details or "Failed to fetch Weibo search results.")

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

            # Some cookies are created for dot-prefixed domains; add host variant too.
            if domain.startswith("."):
                self.session.cookies.set(name, value, domain=domain[1:], path=path)

        return loaded > 0

    def _search_via_http(
        self,
        query: str,
        max_pages: int,
        max_results: Optional[int],
    ) -> WeiboSearchResponse:
        """HTTP-first search implementation."""
        if not self.cookies_loaded:
            raise LoginRequiredError("No saved Weibo session found. Run 'scraper weibo login' first.")

        items: list[WeiboSearchResult] = []
        seen: set[str] = set()
        pages_fetched = 0
        current_url: Optional[str] = None

        for page_number in range(1, max_pages + 1):
            url = _build_search_url(query, page=page_number)
            try:
                response = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            except requests.RequestException as exc:
                raise SearchError(f"HTTP request failed on page {page_number}: {exc}") from exc

            current_url = str(response.url)
            if response.status_code >= 400:
                raise SearchError(f"Weibo returned HTTP {response.status_code} on page {page_number}.")

            html = response.text
            if self._looks_logged_out(current_url, html):
                raise LoginRequiredError("Saved session expired or login required.")
            if self._looks_rate_limited(html):
                raise RateLimitedError("Weibo requires security verification or rate-limited this request.")

            page_items = self._parse_results_from_html(html, base_url=current_url)
            pages_fetched += 1

            if page_number == 1 and not page_items and not self._has_no_result_marker(html):
                raise SearchError("HTTP parse returned no feed cards. Will try Playwright fallback.")

            for item in page_items:
                key = item.detail_url or item.mid or item.content[:80]
                if not key or key in seen:
                    continue
                seen.add(key)
                items.append(item)
                if max_results is not None and len(items) >= max_results:
                    break

            if max_results is not None and len(items) >= max_results:
                break
            if not self._has_next_page(html):
                break

        return WeiboSearchResponse(
            query=query,
            method="http",
            pages_requested=max_pages,
            pages_fetched=pages_fetched,
            results=items,
            current_url=current_url,
        )

    def _search_via_playwright(
        self,
        query: str,
        max_pages: int,
        max_results: Optional[int],
        headless: bool,
    ) -> WeiboSearchResponse:
        """Playwright fallback search implementation."""
        state_file = get_state_path(SOURCE_NAME)
        if not state_file.exists():
            raise LoginRequiredError("No saved Weibo session found. Run 'scraper weibo login' first.")

        items: list[WeiboSearchResult] = []
        seen: set[str] = set()
        pages_fetched = 0
        current_url: Optional[str] = None

        try:
            with _open_weibo_page(headless=headless, use_storage_state=True) as page:
                for page_number in range(1, max_pages + 1):
                    url = _build_search_url(query, page=page_number)
                    page.goto(url, wait_until="domcontentloaded", timeout=Timeouts.NAVIGATION)
                    page.wait_for_timeout(1500)
                    current_url = page.url

                    if _classify_url(current_url) == LoginStatus.LOGGED_OUT:
                        raise LoginRequiredError("Saved session expired or login required.")

                    body_preview = page.evaluate(
                        "() => document.body ? document.body.innerText.slice(0, 6000) : ''"
                    )
                    if self._looks_rate_limited(body_preview):
                        raise RateLimitedError("Weibo requires security verification or rate-limited this request.")

                    raw_cards = page.evaluate(
                        """
                        () => {
                          const cards = Array.from(
                            document.querySelectorAll('#pl_feedlist_index .card-wrap')
                          );
                          return cards.map((card) => {
                            const norm = (value) =>
                              value ? value.replace(/\\s+/g, ' ').trim() : null;
                            const textEl =
                              card.querySelector('p[node-type="feed_list_content_full"]') ||
                              card.querySelector('p[node-type="feed_list_content"]');
                            const userEl =
                              card.querySelector('.card-feed .name') ||
                              card.querySelector('.content .name');
                            const timeEl = card.querySelector('.card-feed .from > a[href]');
                            const sourceEl = card.querySelector('.card-feed .from > a + a');
                            const actions = Array.from(
                              card.querySelectorAll('.card-act ul li')
                            )
                              .map((li) => norm(li.textContent))
                              .filter(Boolean)
                              .slice(0, 3);
                            return {
                              mid: card.getAttribute('mid'),
                              cardType: card.getAttribute('action-type'),
                              user: norm(userEl ? userEl.textContent : null),
                              userUrl: userEl ? userEl.getAttribute('href') : null,
                              postedAt: norm(timeEl ? timeEl.textContent : null),
                              detailUrl: timeEl ? timeEl.getAttribute('href') : null,
                              source: norm(sourceEl ? sourceEl.textContent : null),
                              content: norm(textEl ? textEl.textContent : null),
                              actions
                            };
                          }).filter((item) => item.content || item.detailUrl);
                        }
                        """
                    )

                    pages_fetched += 1
                    parsed_items = self._parse_results_from_payload(raw_cards, base_url=current_url)

                    if (
                        page_number == 1
                        and not parsed_items
                        and page.query_selector(Selectors.NO_RESULT) is None
                    ):
                        raise SearchError("Playwright parse returned no feed cards.")

                    for item in parsed_items:
                        key = item.detail_url or item.mid or item.content[:80]
                        if not key or key in seen:
                            continue
                        seen.add(key)
                        items.append(item)
                        if max_results is not None and len(items) >= max_results:
                            break

                    if max_results is not None and len(items) >= max_results:
                        break
                    if page.query_selector(Selectors.NEXT_PAGE) is None:
                        break

        except LoginRequiredError:
            raise
        except RateLimitedError:
            raise
        except Exception as exc:
            raise SearchError(f"Playwright fallback failed: {exc}") from exc

        return WeiboSearchResponse(
            query=query,
            method="playwright",
            pages_requested=max_pages,
            pages_fetched=pages_fetched,
            results=items,
            current_url=current_url,
        )

    def _looks_logged_out(self, url: str, html: str) -> bool:
        """Detect whether response indicates not logged in."""
        status = _classify_url(url)
        if status == LoginStatus.LOGGED_OUT:
            return True

        body = html.lower()
        return any(marker.lower() in body for marker in LOGGED_OUT_KEYWORDS)

    def _looks_rate_limited(self, body: str) -> bool:
        """Detect rate-limit / verification pages."""
        content = (body or "").lower()
        return any(keyword.lower() in content for keyword in RATE_LIMIT_KEYWORDS)

    def _has_no_result_marker(self, html: str) -> bool:
        """Detect zero-result state."""
        soup = BeautifulSoup(html, "lxml")
        return soup.select_one(Selectors.NO_RESULT) is not None

    def _has_next_page(self, html: str) -> bool:
        """Detect if next page entry exists."""
        soup = BeautifulSoup(html, "lxml")
        return soup.select_one(Selectors.NEXT_PAGE) is not None

    def _parse_results_from_html(self, html: str, base_url: str) -> list[WeiboSearchResult]:
        """Parse card list from server-rendered search page."""
        soup = BeautifulSoup(html, "lxml")
        cards = soup.select(Selectors.FEED_CARD)
        if not cards:
            cards = soup.select(Selectors.FEED_CARD_FALLBACK)

        parsed: list[WeiboSearchResult] = []
        for card in cards:
            text_el = card.select_one(Selectors.FEED_TEXT_FULL) or card.select_one(Selectors.FEED_TEXT)
            user_el = card.select_one(".card-feed .name") or card.select_one(".content .name")
            time_el = card.select_one(Selectors.FEED_TIME)
            source_el = card.select_one(Selectors.FEED_SOURCE)

            content = _clean_text(text_el.get_text(" ", strip=True) if text_el else "")
            detail_url = _to_absolute_url(time_el.get("href") if time_el else None, base_url)
            if not content and not detail_url:
                continue

            action_items = [
                _clean_text(item.get_text(" ", strip=True))
                for item in card.select(Selectors.FEED_ACTION)
            ]
            action_items = [item for item in action_items if item][:3]

            parsed.append(
                WeiboSearchResult(
                    mid=card.get("mid"),
                    card_type=card.get("action-type"),
                    user=_clean_text(user_el.get_text(" ", strip=True) if user_el else ""),
                    user_url=_to_absolute_url(user_el.get("href") if user_el else None, base_url),
                    posted_at=_clean_text(time_el.get_text(" ", strip=True) if time_el else ""),
                    detail_url=detail_url,
                    source=_clean_text(source_el.get_text(" ", strip=True) if source_el else ""),
                    content=content,
                    reposts=_parse_metric_count(action_items[0]) if len(action_items) > 0 else None,
                    comments=_parse_metric_count(action_items[1]) if len(action_items) > 1 else None,
                    likes=_parse_metric_count(action_items[2]) if len(action_items) > 2 else None,
                )
            )

        return parsed

    def _parse_results_from_payload(
        self,
        payload: Any,
        base_url: str,
    ) -> list[WeiboSearchResult]:
        """Parse card list returned by page.evaluate()."""
        if not isinstance(payload, list):
            return []

        parsed: list[WeiboSearchResult] = []
        for item in payload:
            if not isinstance(item, dict):
                continue

            content = _clean_text(str(item.get("content") or ""))
            detail_url = _to_absolute_url(item.get("detailUrl"), base_url)
            if not content and not detail_url:
                continue

            actions = item.get("actions")
            if not isinstance(actions, list):
                actions = []
            action_items = [_clean_text(str(value)) for value in actions if value][:3]

            parsed.append(
                WeiboSearchResult(
                    mid=item.get("mid"),
                    card_type=item.get("cardType"),
                    user=_clean_text(str(item.get("user") or "")),
                    user_url=_to_absolute_url(item.get("userUrl"), base_url),
                    posted_at=_clean_text(str(item.get("postedAt") or "")),
                    detail_url=detail_url,
                    source=_clean_text(str(item.get("source") or "")),
                    content=content,
                    reposts=_parse_metric_count(action_items[0]) if len(action_items) > 0 else None,
                    comments=_parse_metric_count(action_items[1]) if len(action_items) > 1 else None,
                    likes=_parse_metric_count(action_items[2]) if len(action_items) > 2 else None,
                )
            )

        return parsed
