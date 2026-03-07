"""Google Custom Search Engine (CSE) search scraper."""
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

from ..config import (
    GOOGLE_CSE_BASE_URL,
    DATE_RESTRICT,
    SORT_OPTIONS,
    get_api_key,
    get_cx,
)
from ..models import GoogleSearchResponse, GoogleSearchResult


class SearchScraper:
    """Search using the Google Custom Search API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        cx: Optional[str] = None,
    ):
        self.api_key = api_key or get_api_key()
        self.cx = cx or get_cx()

    def is_configured(self) -> bool:
        """Check if API key and CX are configured."""
        return bool(self.api_key and self.cx)

    def search(
        self,
        query: str,
        num: int = 10,
        date_restrict: str = "",
        sort: str = "",
        language: str = "",
        safe: str = "",
        search_type: str = "",
        start: int = 1,
    ) -> GoogleSearchResponse:
        """Search using Google Custom Search API.

        Args:
            query: Search query string.
            num: Results per page (1-10, API limit).
            date_restrict: Date restriction key from DATE_RESTRICT or raw value (e.g. d1).
            sort: Sort option key from SORT_OPTIONS.
            language: Language code for results (e.g. "zh-cn").
            safe: Safe search level: off, medium, high.
            search_type: "image" for image search, empty for web.
            start: Start index for pagination (1-based).

        Returns:
            GoogleSearchResponse with results.

        Raises:
            RuntimeError: On API errors or missing configuration.
        """
        if not self.api_key:
            raise RuntimeError(
                "GOOGLE_CSE_API_KEY not set. "
                "Get a key at https://console.cloud.google.com and set "
                "GOOGLE_CSE_API_KEY env var."
            )
        if not self.cx:
            raise RuntimeError(
                "GOOGLE_CSE_CX not set. "
                "Create a Custom Search Engine at https://programmablesearchengine.google.com "
                "and set GOOGLE_CSE_CX env var."
            )

        # Build results in pages of 10 (API limit)
        all_results: list[GoogleSearchResult] = []
        total_results = None
        search_time = None
        max_per_page = 10

        # Calculate how many pages needed
        pages = (num + max_per_page - 1) // max_per_page
        for page in range(pages):
            page_start = start + page * max_per_page
            page_num = min(max_per_page, num - len(all_results))

            resp = self._fetch_page(
                query=query,
                num=page_num,
                date_restrict=date_restrict,
                sort=sort,
                language=language,
                safe=safe,
                search_type=search_type,
                start=page_start,
            )

            page_results = resp.get("items", [])
            if not page_results:
                break

            for item in page_results:
                all_results.append(GoogleSearchResult(
                    title=item.get("title", ""),
                    url=item.get("link", ""),
                    snippet=item.get("snippet"),
                    display_link=item.get("displayLink"),
                    mime_type=item.get("mime"),
                    kind=item.get("kind"),
                    image_url=(
                        item.get("pagemap", {})
                        .get("cse_thumbnail", [{}])[0]
                        .get("src")
                        if item.get("pagemap", {}).get("cse_thumbnail")
                        else None
                    ),
                ))

            # Extract totals from first page
            if total_results is None:
                try:
                    total_results = int(
                        resp.get("searchInformation", {})
                        .get("totalResults", 0)
                    )
                    search_time = float(
                        resp.get("searchInformation", {})
                        .get("searchTime", 0.0)
                    )
                except (TypeError, ValueError):
                    pass

            if len(all_results) >= num:
                break

        return GoogleSearchResponse(
            query=query,
            results=all_results[:num],
            total_results=total_results,
            search_time=search_time,
        )

    def _fetch_page(
        self,
        query: str,
        num: int,
        date_restrict: str,
        sort: str,
        language: str,
        safe: str,
        search_type: str,
        start: int,
    ) -> dict:
        """Fetch a single page from the Google CSE API."""
        params: dict[str, str] = {
            "key": self.api_key,
            "cx": self.cx,
            "q": query,
            "num": str(min(num, 10)),
            "start": str(start),
        }

        # Date restriction
        if date_restrict:
            params["dateRestrict"] = DATE_RESTRICT.get(date_restrict, date_restrict)

        # Sort
        if sort:
            sort_val = SORT_OPTIONS.get(sort, sort)
            if sort_val:
                params["sort"] = sort_val

        # Language
        if language:
            params["hl"] = language

        # Safe search
        if safe:
            params["safe"] = safe

        # Image search
        if search_type == "image":
            params["searchType"] = "image"

        query_string = urllib.parse.urlencode(params)
        url = f"{GOOGLE_CSE_BASE_URL}?{query_string}"

        req = urllib.request.Request(url, method="GET")

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="ignore")
                err_data = json.loads(body)
                msg = err_data.get("error", {}).get("message", "")
            except Exception:
                msg = body[:200]

            if e.code == 400:
                raise RuntimeError(f"Google CSE bad request: {msg}") from e
            if e.code == 403:
                raise RuntimeError(
                    f"Google CSE access denied (check API key / quota): {msg}"
                ) from e
            if e.code == 429:
                raise RuntimeError("Google CSE rate limit exceeded.") from e
            raise RuntimeError(f"Google CSE error: HTTP {e.code} — {msg}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"Network error: {e}") from e
