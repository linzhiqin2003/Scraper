"""Sina news search scraper based on server-rendered search pages."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from ..config import DEFAULT_HEADERS, DEFAULT_PAGE_SIZE, SEARCH_URL
from ..models import SinaSearchResponse, SinaSearchResult


class SearchError(Exception):
    """Generic error for Sina search failures."""


@dataclass(slots=True)
class _ParsedPage:
    results: list[SinaSearchResult]
    total_results: Optional[int]
    max_page: Optional[int]


def _clean_text(value: Optional[str]) -> str:
    """Normalize text extracted from HTML."""
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).replace("\xa0", " ").strip()


def _extract_source_and_time(text: str) -> tuple[Optional[str], Optional[str]]:
    """Split source label and timestamp from the footer text."""
    cleaned = _clean_text(text)
    if not cleaned:
        return None, None

    match = re.search(r"(?P<dt>\d{4}-\d{2}-\d{2}(?: \d{2}:\d{2}:\d{2})?)$", cleaned)
    if not match:
        return cleaned, None

    published_at = match.group("dt")
    source_name = cleaned[: match.start()].strip(" -|")
    return source_name or None, published_at


class SearchScraper:
    """Scrape Sina's news search result pages."""

    def __init__(
        self,
        timeout: int = 30,
        delay: float = 0.2,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.timeout = timeout
        self.delay = max(0.0, delay)
        self.session = session or requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def search(
        self,
        query: str,
        start_time: str,
        end_time: str,
        max_pages: int = 20,
        limit: Optional[int] = None,
        source: str = "",
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> SinaSearchResponse:
        """Fetch Sina search results across multiple pages."""
        keyword = query.strip()
        if not keyword:
            raise SearchError("Search query cannot be empty.")
        if not start_time.strip() or not end_time.strip():
            raise SearchError("Both start_time and end_time are required.")

        max_pages = max(1, max_pages)
        page_size = max(1, min(page_size, 50))
        max_results = limit if limit and limit > 0 else None

        all_results: list[SinaSearchResult] = []
        seen_urls: set[str] = set()
        total_results: Optional[int] = None
        discovered_max_page: Optional[int] = None
        fetched_pages = 0

        for page in range(1, max_pages + 1):
            parsed = self._fetch_page(
                query=keyword,
                start_time=start_time,
                end_time=end_time,
                page=page,
                source=source,
                page_size=page_size,
            )
            fetched_pages += 1

            if total_results is None:
                total_results = parsed.total_results
            if discovered_max_page is None and parsed.max_page is not None:
                discovered_max_page = parsed.max_page

            if not parsed.results:
                break

            for item in parsed.results:
                if item.url in seen_urls:
                    continue
                seen_urls.add(item.url)
                all_results.append(item)
                if max_results is not None and len(all_results) >= max_results:
                    return SinaSearchResponse(
                        query=keyword,
                        start_time=start_time,
                        end_time=end_time,
                        total_results=total_results,
                        fetched_pages=fetched_pages,
                        results=all_results[:max_results],
                    )

            if discovered_max_page is not None and page >= discovered_max_page:
                break

            if self.delay and page < max_pages:
                time.sleep(self.delay)

        return SinaSearchResponse(
            query=keyword,
            start_time=start_time,
            end_time=end_time,
            total_results=total_results,
            fetched_pages=fetched_pages,
            results=all_results,
        )

    def search_split_by_year(
        self,
        query: str,
        start_time: str,
        end_time: str,
        max_pages_per_year: int = 20,
        limit: Optional[int] = None,
        source: str = "",
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> SinaSearchResponse:
        """Fetch results by splitting a long interval into year-sized queries."""
        start_dt = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
        end_dt = datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
        if end_dt < start_dt:
            raise SearchError("end_time must be greater than or equal to start_time.")

        merged: list[SinaSearchResult] = []
        seen_urls: set[str] = set()
        fetched_pages = 0
        total_results = 0
        max_results = limit if limit and limit > 0 else None

        for year in range(start_dt.year, end_dt.year + 1):
            chunk_start = max(start_dt, datetime(year, 1, 1, 0, 0, 0))
            chunk_end = min(end_dt, datetime(year, 12, 31, 23, 59, 59))
            response = self.search(
                query=query,
                start_time=chunk_start.strftime("%Y-%m-%d %H:%M:%S"),
                end_time=chunk_end.strftime("%Y-%m-%d %H:%M:%S"),
                max_pages=max_pages_per_year,
                limit=None,
                source=source,
                page_size=page_size,
            )
            fetched_pages += response.fetched_pages
            total_results += response.total_results or len(response.results)

            for item in response.results:
                if item.url in seen_urls:
                    continue
                seen_urls.add(item.url)
                merged.append(item)
                if max_results is not None and len(merged) >= max_results:
                    return SinaSearchResponse(
                        query=query,
                        start_time=start_time,
                        end_time=end_time,
                        total_results=total_results,
                        fetched_pages=fetched_pages,
                        results=merged[:max_results],
                    )

        merged.sort(key=lambda item: item.published_at or "", reverse=True)
        return SinaSearchResponse(
            query=query,
            start_time=start_time,
            end_time=end_time,
            total_results=total_results,
            fetched_pages=fetched_pages,
            results=merged,
        )

    def search_adaptive(
        self,
        query: str,
        start_time: str,
        end_time: str,
        max_pages: int = 20,
        limit: Optional[int] = None,
        source: str = "",
        page_size: int = DEFAULT_PAGE_SIZE,
        min_interval_seconds: int = 3600,
    ) -> SinaSearchResponse:
        """Recursively split the time range when Sina truncates deep result sets."""
        start_dt = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
        end_dt = datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
        if end_dt < start_dt:
            raise SearchError("end_time must be greater than or equal to start_time.")

        max_results = limit if limit and limit > 0 else None
        seen_urls: set[str] = set()
        merged: list[SinaSearchResult] = []
        stats = {"pages": 0, "reported_total": 0}

        def collect(window_start: datetime, window_end: datetime) -> None:
            nonlocal merged
            if max_results is not None and len(merged) >= max_results:
                return

            response = self.search(
                query=query,
                start_time=window_start.strftime("%Y-%m-%d %H:%M:%S"),
                end_time=window_end.strftime("%Y-%m-%d %H:%M:%S"),
                max_pages=max_pages,
                limit=None,
                source=source,
                page_size=page_size,
            )
            stats["pages"] += response.fetched_pages
            stats["reported_total"] += response.total_results or len(response.results)

            truncated = (
                response.total_results is not None
                and response.total_results > len(response.results)
            )
            interval_seconds = int((window_end - window_start).total_seconds())

            if truncated and interval_seconds > min_interval_seconds:
                midpoint = window_start + (window_end - window_start) / 2
                midpoint = midpoint.replace(microsecond=0)
                if midpoint <= window_start:
                    midpoint = window_start + timedelta(seconds=1)
                if midpoint > window_end:
                    midpoint = window_end

                left_end = midpoint
                right_start = midpoint + timedelta(seconds=1)
                collect(window_start, left_end)
                if right_start <= window_end:
                    collect(right_start, window_end)
                return

            for item in response.results:
                if item.url in seen_urls:
                    continue
                seen_urls.add(item.url)
                merged.append(item)
                if max_results is not None and len(merged) >= max_results:
                    return

        from datetime import timedelta

        collect(start_dt, end_dt)
        merged.sort(key=lambda item: item.published_at or "", reverse=True)
        return SinaSearchResponse(
            query=query,
            start_time=start_time,
            end_time=end_time,
            total_results=stats["reported_total"],
            fetched_pages=stats["pages"],
            results=merged[:max_results] if max_results is not None else merged,
        )

    def _fetch_page(
        self,
        query: str,
        start_time: str,
        end_time: str,
        page: int,
        source: str,
        page_size: int,
    ) -> _ParsedPage:
        """Fetch and parse a single search page."""
        params = {
            "q": query,
            "c": "news",
            "sort": "time",
            "stime": start_time,
            "etime": end_time,
            "page": str(page),
            "size": str(page_size),
            "source": source,
        }

        try:
            response = self.session.get(SEARCH_URL, params=params, timeout=self.timeout)
        except requests.RequestException as exc:
            raise SearchError(f"Failed to fetch page {page}: {exc}") from exc

        if response.status_code >= 400:
            raise SearchError(f"Sina search returned HTTP {response.status_code} on page {page}.")

        return self._parse_page(response.text)

    @staticmethod
    def _parse_page(html: str) -> _ParsedPage:
        """Parse search results from HTML."""
        soup = BeautifulSoup(html, "lxml")
        items: list[SinaSearchResult] = []

        for node in soup.select("div.box-result.clearfix"):
            title_link = node.select_one("h2 a[href]")
            if not title_link:
                continue

            title = title_link.get_text("", strip=True)
            url = urljoin(SEARCH_URL, title_link.get("href", "").strip())
            if not title or not url:
                continue

            snippet = _clean_text(node.select_one("p.content").get_text(" ", strip=True) if node.select_one("p.content") else "")
            source_and_time = node.select_one(".fgray_time")
            source_name, published_at = _extract_source_and_time(
                source_and_time.get_text(" ", strip=True) if source_and_time else ""
            )
            image = node.select_one("img.left_img")
            image_url = urljoin(SEARCH_URL, image.get("src", "").strip()) if image and image.get("src") else None

            items.append(
                SinaSearchResult(
                    title=title,
                    url=url,
                    snippet=snippet or None,
                    source_name=source_name,
                    published_at=published_at,
                    image_url=image_url,
                )
            )

        count_text = _clean_text(soup.select_one(".l_v2").get_text(" ", strip=True) if soup.select_one(".l_v2") else "")
        total_results = None
        count_match = re.search(r"找到相关新闻(\d+)篇", count_text)
        if count_match:
            total_results = int(count_match.group(1))

        max_page = None
        page_numbers: list[int] = []
        for link in soup.select(".pagebox a"):
            text = _clean_text(link.get_text(" ", strip=True))
            if text.isdigit():
                page_numbers.append(int(text))
                continue
            title = _clean_text(link.get("title", ""))
            title_match = re.match(r"第(\d+)页", title)
            if title_match:
                page_numbers.append(int(title_match.group(1)))

        if page_numbers:
            max_page = max(page_numbers)

        return _ParsedPage(results=items, total_results=total_results, max_page=max_page)
