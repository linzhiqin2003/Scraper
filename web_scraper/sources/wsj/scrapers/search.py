"""WSJ search scraper using httpx."""
import json
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlencode

import httpx

from ..config import (
    SOURCE_NAME,
    BASE_URL,
    SEARCH_URL,
    DEFAULT_HEADERS,
    SEARCH_SORT,
    SEARCH_DATE_RANGE,
    SEARCH_SOURCES,
)
from ..models import SearchResult, SearchResponse
from ..cookies import load_cookies


def extract_search_results(html: str) -> List[dict]:
    """Extract searchResults JSON from HTML."""
    start_marker = '"searchResults":['
    start_idx = html.find(start_marker)
    if start_idx == -1:
        return []

    start_idx += len(start_marker) - 1  # Point to [

    # Bracket matching to find complete array
    depth = 0
    end_idx = start_idx
    for i, char in enumerate(html[start_idx:]):
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                end_idx = start_idx + i + 1
                break

    json_str = html[start_idx:end_idx]

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return []


def parse_search_result(item: dict) -> SearchResult:
    """Parse a single search result."""
    # Extract author
    author = None
    if item.get("bylineData"):
        author_parts = [
            part["text"]
            for part in item["bylineData"]
            if part.get("type") == "text" and part.get("text") != "By "
        ]
        author = "".join(author_parts).strip() or None

    # Parse timestamp
    timestamp = None
    if item.get("timestamp"):
        try:
            timestamp = datetime.fromisoformat(
                item["timestamp"].replace("Z", "+00:00")
            )
        except ValueError:
            pass

    return SearchResult(
        url=item.get("articleUrl", ""),
        headline=item.get("headline", ""),
        author=author,
        category=item.get("flashline"),
        image_url=item.get("imageUrl"),
        timestamp=timestamp,
    )


class SearchScraper:
    """WSJ search scraper using httpx."""

    SOURCE_NAME = SOURCE_NAME
    BASE_URL = BASE_URL

    def __init__(self, cookies_path: Optional[Path] = None):
        """Initialize scraper with cookies."""
        self.cookies = load_cookies(cookies_path)

    def search(
        self,
        query: str,
        page: int = 1,
        sort: Optional[str] = None,
        date_range: Optional[str] = None,
        sources: Optional[List[str]] = None,
    ) -> SearchResponse:
        """
        Search WSJ articles.

        Args:
            query: Search keywords
            page: Page number
            sort: Sort order - "newest", "oldest", "relevance" (default: "newest")
            date_range: Date filter - "day", "week", "month", "year", "all" (default: "all")
            sources: Content sources - list of "articles", "video", "audio", "livecoverage", "buyside"
                     (default: all sources)

        Returns:
            SearchResponse with results
        """
        # Build URL params
        params = {"query": query}

        # Sort
        if sort and sort in SEARCH_SORT:
            params["sort"] = SEARCH_SORT[sort]
        else:
            params["sort"] = "desc"  # Default to newest

        # Date range
        if date_range and date_range in SEARCH_DATE_RANGE:
            params["dateRange"] = SEARCH_DATE_RANGE[date_range]
        else:
            params["dateRange"] = "all"

        # Sources (products)
        if sources:
            valid_sources = [SEARCH_SOURCES[s] for s in sources if s in SEARCH_SOURCES]
            if valid_sources:
                params["products"] = ",".join(valid_sources)
        else:
            # Default: all sources
            params["products"] = ",".join(SEARCH_SOURCES.values())

        if page > 1:
            params["page"] = page

        url = f"{SEARCH_URL}?{urlencode(params)}"

        # Send request
        with httpx.Client(
            cookies=self.cookies,
            headers=DEFAULT_HEADERS,
            follow_redirects=True,
            timeout=30.0,
        ) as client:
            response = client.get(url)

            if response.status_code != 200:
                raise Exception(f"HTTP {response.status_code}: {response.text[:200]}")

            html = response.text

        # Check rate limiting
        if "Access is temporarily restricted" in html or "captcha" in html.lower():
            raise Exception("Access restricted, CAPTCHA required")

        # Extract data
        raw_results = extract_search_results(html)
        results = [parse_search_result(item) for item in raw_results]

        return SearchResponse(
            query=query,
            page=page,
            results=results,
            total_found=len(results),
        )

    def search_multi_pages(
        self,
        query: str,
        max_pages: int = 1,
        delay: float = 1.0,
        sort: Optional[str] = None,
        date_range: Optional[str] = None,
        sources: Optional[List[str]] = None,
    ) -> List[SearchResult]:
        """
        Search multiple pages.

        Args:
            query: Search keywords
            max_pages: Maximum pages to search
            delay: Delay between requests
            sort: Sort order - "newest", "oldest", "relevance"
            date_range: Date filter - "day", "week", "month", "year", "all"
            sources: Content sources - list of "articles", "video", "audio", "livecoverage", "buyside"

        Returns:
            List of all SearchResult items
        """
        all_results: List[SearchResult] = []

        for page in range(1, max_pages + 1):
            try:
                response = self.search(
                    query,
                    page=page,
                    sort=sort,
                    date_range=date_range,
                    sources=sources,
                )
                all_results.extend(response.results)

                if not response.results:
                    break

                if page < max_pages:
                    time.sleep(delay)

            except Exception as e:
                print(f"[Page {page}] Error: {e}")
                break

        return all_results
