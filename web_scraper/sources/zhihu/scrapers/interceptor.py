"""API response interceptor for Zhihu scraper.

Intercepts XHR responses from Zhihu's internal API endpoints during page navigation,
enabling structured JSON parsing instead of fragile DOM extraction.
"""

import json
import logging
import re
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from playwright.sync_api import Page, Response

from ..config import BASE_URL
from ..models import ArticleDetail, SearchResult

logger = logging.getLogger(__name__)

# API URL patterns to intercept
API_PATTERNS: Dict[str, re.Pattern] = {
    "search": re.compile(r"/api/v4/search_v3"),
    "answer": re.compile(r"/api/v4/answers/\d+"),
    "article": re.compile(r"/api/v4/articles/\d+"),
    "question": re.compile(r"/api/v4/questions/\d+"),
}


@dataclass
class CapturedResponse:
    """A captured API response."""

    pattern_name: str
    url: str
    status: int
    body: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class ResponseInterceptor:
    """Intercepts API responses from Zhihu pages.

    Usage:
        interceptor = ResponseInterceptor()
        interceptor.start(page, ["search"])
        page.goto(search_url)
        page.wait_for_timeout(3000)
        responses = interceptor.stop()
    """

    def __init__(self) -> None:
        self._captures: List[CapturedResponse] = []
        self._lock = threading.Lock()
        self._handler: Optional[Callable] = None
        self._page: Optional[Page] = None
        self._active_patterns: Dict[str, re.Pattern] = {}

    def start(self, page: Page, pattern_names: Optional[List[str]] = None) -> None:
        """Register the response interceptor on a page.

        Args:
            page: Playwright page to intercept responses from.
            pattern_names: Which API patterns to listen for. None = all.
        """
        self._page = page
        self._captures = []

        if pattern_names is None:
            self._active_patterns = dict(API_PATTERNS)
        else:
            self._active_patterns = {
                k: v for k, v in API_PATTERNS.items() if k in pattern_names
            }

        def on_response(response: Response) -> None:
            url = response.url
            for name, pattern in self._active_patterns.items():
                if pattern.search(url):
                    self._capture_response(name, response)
                    break

        self._handler = on_response
        page.on("response", on_response)
        logger.debug("Interceptor started for patterns: %s", list(self._active_patterns.keys()))

    def stop(self) -> List[CapturedResponse]:
        """Stop intercepting and return all captured responses."""
        if self._page and self._handler:
            try:
                self._page.remove_listener("response", self._handler)
            except Exception:
                pass
        self._handler = None
        self._page = None

        with self._lock:
            result = list(self._captures)
        logger.debug("Interceptor stopped, captured %d responses", len(result))
        return result

    def get_latest(self, pattern_name: str) -> Optional[CapturedResponse]:
        """Get the most recent captured response for a pattern."""
        with self._lock:
            for cap in reversed(self._captures):
                if cap.pattern_name == pattern_name:
                    return cap
        return None

    def _capture_response(self, pattern_name: str, response: Response) -> None:
        """Capture and parse an API response."""
        captured = CapturedResponse(
            pattern_name=pattern_name,
            url=response.url,
            status=response.status,
        )

        try:
            body = response.body()
            data = json.loads(body)
            captured.body = data
            logger.debug(
                "Captured %s response: %s (status=%d)",
                pattern_name, response.url, response.status,
            )
        except Exception as e:
            captured.error = str(e)
            logger.debug("Failed to parse %s response: %s", pattern_name, e)

        with self._lock:
            self._captures.append(captured)


# ---------------------------------------------------------------------------
# JSON -> Model parsers
# ---------------------------------------------------------------------------


def _safe_int(value: Any) -> Optional[int]:
    """Safely convert a value to int."""
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _extract_content_type(obj: Dict[str, Any]) -> str:
    """Determine content type from API object."""
    obj_type = obj.get("type", "")
    if obj_type == "answer" or "answer" in obj.get("url", ""):
        return "answer"
    if obj_type == "article" or "zhuanlan" in obj.get("url", ""):
        return "article"
    if obj_type == "question":
        return "question"
    if obj_type == "zvideo":
        return "video"
    return "answer"


def _normalize_url(url: str, obj: Optional[Dict[str, Any]] = None) -> str:
    """Convert API URLs to proper web URLs.

    API responses return URLs like https://api.zhihu.com/articles/123
    which need to be converted to https://zhuanlan.zhihu.com/p/123 etc.
    """
    if not url:
        return ""
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        return BASE_URL + url

    # Convert api.zhihu.com URLs to proper web URLs
    if "api.zhihu.com" in url:
        # articles: https://api.zhihu.com/articles/ID -> https://zhuanlan.zhihu.com/p/ID
        m = re.search(r"api\.zhihu\.com/articles/(\d+)", url)
        if m:
            return f"https://zhuanlan.zhihu.com/p/{m.group(1)}"

        # answers: need question ID from obj
        m = re.search(r"api\.zhihu\.com/answers/(\d+)", url)
        if m:
            a_id = m.group(1)
            q_id = ""
            if obj:
                question = obj.get("question", {})
                if isinstance(question, dict):
                    q_id = str(question.get("id", ""))
            if q_id:
                return f"{BASE_URL}/question/{q_id}/answer/{a_id}"
            return f"{BASE_URL}/answer/{a_id}"

        # questions: https://api.zhihu.com/questions/ID -> https://www.zhihu.com/question/ID
        m = re.search(r"api\.zhihu\.com/questions/(\d+)", url)
        if m:
            return f"{BASE_URL}/question/{m.group(1)}"

    return url


def parse_api_search_results(api_data: Dict[str, Any]) -> List[SearchResult]:
    """Parse search API JSON into SearchResult models.

    The search API (v4/search_v3) returns JSON like:
    {
        "data": [
            {
                "type": "search_result",
                "object": {
                    "type": "answer",
                    "id": 123,
                    "url": "...",
                    "question": {"title": "..."},
                    "excerpt": "...",
                    "author": {"name": "...", "url_token": "..."},
                    "voteup_count": 100,
                    "comment_count": 20,
                    "created_time": 1234567890
                }
            },
            ...
        ],
        "paging": {"is_end": false, "next": "..."}
    }
    """
    results = []
    data_list = api_data.get("data", [])

    for item in data_list:
        try:
            obj = item.get("object", item)
            if not obj:
                continue

            # Title
            title = obj.get("title", "")
            if not title:
                question = obj.get("question", {})
                if isinstance(question, dict):
                    title = question.get("title", "")
            if not title:
                continue

            # URL - prefer constructing from type+ID for reliability
            obj_type = obj.get("type", "")
            obj_id = obj.get("id")
            url = ""

            if obj_type == "answer" and obj_id:
                q_id = ""
                question = obj.get("question", {})
                if isinstance(question, dict):
                    q_id = str(question.get("id", ""))
                if q_id:
                    url = f"{BASE_URL}/question/{q_id}/answer/{obj_id}"
            elif obj_type == "article" and obj_id:
                url = f"https://zhuanlan.zhihu.com/p/{obj_id}"
            elif obj_type == "question" and obj_id:
                url = f"{BASE_URL}/question/{obj_id}"

            # Fallback: normalize the API-provided URL
            if not url:
                url = _normalize_url(obj.get("url", ""), obj)

            if not url:
                continue

            # Excerpt
            excerpt = obj.get("excerpt", "") or obj.get("content", "")
            if excerpt:
                # Strip HTML tags from excerpt
                excerpt = re.sub(r"<[^>]+>", "", excerpt)[:500]

            # Author
            author_info = obj.get("author", {})
            author = None
            author_url = None
            if isinstance(author_info, dict):
                author = author_info.get("name")
                url_token = author_info.get("url_token")
                if url_token:
                    author_url = f"{BASE_URL}/people/{url_token}"

            # Stats
            upvotes = _safe_int(obj.get("voteup_count"))
            comments = _safe_int(obj.get("comment_count"))

            # Time
            created_time = obj.get("created_time")
            created_at = None
            if created_time and isinstance(created_time, (int, float)):
                from datetime import datetime, timezone
                created_at = datetime.fromtimestamp(
                    created_time, tz=timezone.utc
                ).isoformat()

            content_type = _extract_content_type(obj)

            results.append(SearchResult(
                title=title,
                url=url,
                content_type=content_type,
                excerpt=excerpt,
                author=author,
                author_url=author_url,
                upvotes=upvotes,
                comments=comments,
                created_at=created_at,
            ))

        except Exception as e:
            logger.debug("Failed to parse search result item: %s", e)
            continue

    return results


def parse_api_article(api_data: Dict[str, Any], url: str) -> ArticleDetail:
    """Parse article/answer API JSON into ArticleDetail model.

    Answer API (v4/answers/{id}):
    {
        "id": 123,
        "type": "answer",
        "question": {"title": "...", "id": 456},
        "author": {"name": "...", "url_token": "..."},
        "content": "<p>HTML content</p>",
        "voteup_count": 100,
        "comment_count": 20,
        "created_time": 1234567890,
        "updated_time": 1234567890
    }

    Article API (v4/articles/{id}):
    {
        "id": 789,
        "type": "article",
        "title": "...",
        "author": {"name": "...", "url_token": "..."},
        "content": "<p>HTML content</p>",
        "voteup_count": 100,
        "comment_count": 20,
        "created": 1234567890,
        "updated": 1234567890
    }
    """
    from datetime import datetime, timezone

    # Title
    title = api_data.get("title", "")
    question_title = None
    content_type = "article"

    question = api_data.get("question")
    if isinstance(question, dict):
        question_title = question.get("title", "")
        if not title:
            title = question_title
        content_type = "answer"

    if api_data.get("type") == "answer":
        content_type = "answer"

    # Content - strip HTML
    raw_content = api_data.get("content", "")
    content = re.sub(r"<[^>]+>", "", raw_content) if raw_content else ""

    # Images from HTML content
    images = re.findall(r'src="(https?://[^"]+)"', raw_content) if raw_content else []

    # Author
    author_info = api_data.get("author", {})
    author = None
    author_url = None
    if isinstance(author_info, dict):
        author = author_info.get("name")
        url_token = author_info.get("url_token")
        if url_token:
            author_url = f"{BASE_URL}/people/{url_token}"

    # Stats
    upvotes = _safe_int(api_data.get("voteup_count"))
    comments = _safe_int(api_data.get("comment_count"))

    # Timestamps
    created_at = None
    updated_at = None

    for key in ("created_time", "created"):
        ts = api_data.get(key)
        if ts and isinstance(ts, (int, float)):
            created_at = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
            break

    for key in ("updated_time", "updated"):
        ts = api_data.get(key)
        if ts and isinstance(ts, (int, float)):
            updated_at = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
            break

    # Tags
    tags = []
    for topic in api_data.get("topics", []):
        if isinstance(topic, dict) and topic.get("name"):
            tags.append(topic["name"])

    return ArticleDetail(
        url=url,
        title=title,
        content=content,
        author=author,
        author_url=author_url,
        upvotes=upvotes,
        comments=comments,
        created_at=created_at,
        updated_at=updated_at,
        tags=tags,
        images=images,
        content_type=content_type,
        question_title=question_title,
        scraped_at=datetime.now(),
        data_source="api_intercept",
    )
