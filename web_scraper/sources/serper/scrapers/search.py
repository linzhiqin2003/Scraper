"""Serper API search scraper."""
import json
import urllib.error
import urllib.request
from typing import Optional

from ..config import SERPER_BASE_URL, SEARCH_TYPES, get_api_key
from ..models import SerperSearchResponse, SerperSearchResult


class SearchScraper:
    """Search using the Serper API (Google search wrapper)."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or get_api_key()

    def is_configured(self) -> bool:
        """Check if API key is configured."""
        return bool(self.api_key)

    def search(
        self,
        query: str,
        num: int = 10,
        search_type: str = "search",
        time_range: str = "",
        country: str = "",
        language: str = "",
    ) -> SerperSearchResponse:
        """Search using Serper API.

        Args:
            query: Search query string.
            num: Max results (1-100).
            search_type: "search", "news", or "images".
            time_range: Time filter key from TIME_RANGES or raw tbs value.
            country: Country code (e.g. "us", "cn").
            language: Language code (e.g. "en", "zh-cn").

        Returns:
            SerperSearchResponse with results.

        Raises:
            RuntimeError: On API errors.
        """
        if not self.api_key:
            raise RuntimeError(
                "SERPER_API_KEY not set. "
                "Get a key at https://serper.dev and set SERPER_API_KEY env var."
            )

        endpoint = SEARCH_TYPES.get(search_type, "/search")
        url = SERPER_BASE_URL + endpoint

        payload: dict = {"q": query, "num": min(num, 100)}
        if time_range:
            payload["tbs"] = time_range
        if country:
            payload["gl"] = country
        if language:
            payload["hl"] = language

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "X-API-KEY": self.api_key,
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise RuntimeError("Serper API authentication failed. Check SERPER_API_KEY.") from e
            if e.code == 429:
                raise RuntimeError("Serper API rate limit exceeded.") from e
            raise RuntimeError(f"Serper API error: HTTP {e.code}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"Network error: {e}") from e

        return self._parse_response(query, search_type, result)

    @staticmethod
    def _parse_response(
        query: str, search_type: str, data: dict
    ) -> SerperSearchResponse:
        """Parse raw Serper API response."""
        results = []

        if search_type == "news":
            raw_items = data.get("news", [])
            for item in raw_items:
                results.append(SerperSearchResult(
                    title=item.get("title", ""),
                    url=item.get("link", ""),
                    snippet=item.get("snippet"),
                    position=item.get("position"),
                    date=item.get("date"),
                    source=item.get("source"),
                    image_url=item.get("imageUrl"),
                ))
        elif search_type == "images":
            raw_items = data.get("images", [])
            for item in raw_items:
                results.append(SerperSearchResult(
                    title=item.get("title", ""),
                    url=item.get("link", ""),
                    snippet=item.get("imageUrl"),
                    position=item.get("position"),
                    image_url=item.get("imageUrl"),
                ))
        else:
            raw_items = data.get("organic", [])
            for item in raw_items:
                results.append(SerperSearchResult(
                    title=item.get("title", ""),
                    url=item.get("link", ""),
                    snippet=item.get("snippet"),
                    position=item.get("position"),
                    date=item.get("date"),
                ))

        # Extract knowledge graph and answer box
        knowledge_graph = data.get("knowledgeGraph")
        answer_box = data.get("answerBox")
        credits_used = data.get("credits")

        return SerperSearchResponse(
            query=query,
            search_type=search_type,
            results=results,
            knowledge_graph=knowledge_graph,
            answer_box=answer_box,
            credits_used=credits_used,
        )
