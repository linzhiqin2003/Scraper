"""Zhihu API client with pure Python signature generation.

Two modes:
- PureAPIClient: No browser required. Uses crypto.py for signatures + cookies from file.
- ZhihuAPIClient: Uses CDP browser as JS oracle (legacy, kept as fallback).
"""

import hashlib
import json
import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlencode

import httpx

from ...core.user_agent import build_api_headers
from .anti_detect import BlockDetector, BlockStatus
from .config import BASE_URL, DATA_DIR, STATE_FILE
from .crypto import X_ZSE_93, generate_x_zse_96
from .models import ArticleDetail, SearchResult

logger = logging.getLogger(__name__)

# API endpoints
SEARCH_API = f"{BASE_URL}/api/v4/search_v3"
ANSWER_API = f"{BASE_URL}/api/v4/answers"
ARTICLE_API = f"{BASE_URL}/api/v4/articles"
QUESTION_API = f"{BASE_URL}/api/v4/questions"

# Common request headers
_BASE_HEADERS = build_api_headers(
    accept_language="zh-CN,zh;q=0.9,en;q=0.8",
    extra={
        "Referer": f"{BASE_URL}/",
        "Origin": BASE_URL,
        "x-requested-with": "fetch",
        "x-zse-93": X_ZSE_93,
    },
)


# ============================================================================
# Pure API Client (no browser dependency)
# ============================================================================


def _load_d_c0_from_state() -> Optional[str]:
    """Extract d_c0 cookie from the saved browser_state.json."""
    if not STATE_FILE.exists():
        return None

    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        for cookie in state.get("cookies", []):
            if cookie.get("name") == "d_c0":
                value = cookie.get("value", "")
                return value.strip('"')
    except Exception as e:
        logger.debug("Failed to read d_c0 from state file: %s", e)

    return None


def _load_cookies_from_state() -> Dict[str, str]:
    """Load all zhihu cookies from the saved browser_state.json."""
    if not STATE_FILE.exists():
        return {}

    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        cookies = {}
        for cookie in state.get("cookies", []):
            name = cookie.get("name", "")
            value = cookie.get("value", "")
            domain = cookie.get("domain", "")
            if name and "zhihu.com" in domain:
                cookies[name] = value
        return cookies
    except Exception as e:
        logger.debug("Failed to load cookies from state file: %s", e)
        return {}


class PureAPIClient:
    """Pure Python API client for Zhihu. No browser required.

    Uses crypto.py for x-zse-96 signature generation and cookies from
    the saved browser_state.json file.

    Usage:
        client = PureAPIClient()
        if client.initialize():
            results = client.search("transformer", limit=10)
            client.close()
    """

    def __init__(
        self,
        proxy_url: Optional[str] = None,
        d_c0: Optional[str] = None,
        cookies: Optional[Dict[str, str]] = None,
    ) -> None:
        self._proxy_url = proxy_url
        self._d_c0 = d_c0
        self._cookies = cookies
        self._detector = BlockDetector()
        self._client: Optional[httpx.Client] = None

    def initialize(self) -> bool:
        """Initialize the client by loading cookies and d_c0.

        Returns:
            True if initialization succeeded (d_c0 found).
        """
        # Load d_c0
        if not self._d_c0:
            self._d_c0 = _load_d_c0_from_state()

        if not self._d_c0:
            logger.warning("d_c0 cookie not found. Import cookies first: scraper zhihu import-cookies")
            return False

        # Load cookies
        if not self._cookies:
            self._cookies = _load_cookies_from_state()

        if not self._cookies:
            logger.warning("No cookies found in state file")
            return False

        # Create httpx client
        kwargs = {}
        if self._proxy_url:
            kwargs["proxy"] = self._proxy_url

        self._client = httpx.Client(
            timeout=30.0,
            follow_redirects=True,
            **kwargs,
        )

        # Set cookies
        for name, value in self._cookies.items():
            self._client.cookies.set(name, value, domain=".zhihu.com")

        logger.info("PureAPIClient initialized (d_c0=%s...)", self._d_c0[:10])
        return True

    def close(self) -> None:
        """Close the httpx client."""
        if self._client:
            self._client.close()
            self._client = None

    @property
    def is_ready(self) -> bool:
        return self._d_c0 is not None and self._client is not None

    def search(
        self,
        query: str,
        search_type: str = "general",
        limit: int = 20,
        offset: int = 0,
    ) -> Optional[List[SearchResult]]:
        """Search Zhihu via pure API with automatic pagination.

        Args:
            query: Search keywords.
            search_type: "general", "topic", "people", etc.
            limit: Total results desired.
            offset: Starting offset.

        Returns:
            List of SearchResult or None if failed.
        """
        if not self.is_ready:
            return None

        from .scrapers.interceptor import parse_api_search_results

        all_results: List[SearchResult] = []
        current_offset = offset
        max_pages = 5  # Safety limit to prevent infinite loops

        for _ in range(max_pages):
            params = {
                "t": search_type,
                "q": query,
                "correction": 1,
                "offset": current_offset,
                "limit": 20,  # API page size
            }
            api_path = f"/api/v4/search_v3?{urlencode(params)}"

            data = self._api_get(api_path)
            if data is None:
                break

            page_results = parse_api_search_results(data)
            if not page_results:
                break

            all_results.extend(page_results)

            if len(all_results) >= limit:
                break

            # Check pagination
            paging = data.get("paging", {})
            if paging.get("is_end", True):
                break

            # Use next URL's offset or increment
            next_url = paging.get("next", "")
            if next_url:
                # Extract offset from next URL
                match = re.search(r"offset=(\d+)", next_url)
                if match:
                    current_offset = int(match.group(1))
                else:
                    current_offset += len(page_results)
            else:
                current_offset += len(page_results)

        return all_results[:limit] if all_results else None

    def fetch_answer(self, answer_id: str) -> Optional[ArticleDetail]:
        """Fetch an answer by ID."""
        if not self.is_ready:
            return None

        api_path = (
            f"/api/v4/answers/{answer_id}"
            "?include=content,voteup_count,comment_count,created_time,updated_time"
        )
        data = self._api_get(api_path)
        if data is None:
            return None

        from .scrapers.interceptor import parse_api_article
        q_id = data.get("question", {}).get("id", "")
        url = f"{BASE_URL}/question/{q_id}/answer/{answer_id}"
        return parse_api_article(data, url)

    def fetch_article(self, article_id: str) -> Optional[ArticleDetail]:
        """Fetch an article by ID."""
        if not self.is_ready:
            return None

        api_path = (
            f"/api/v4/articles/{article_id}"
            "?include=content,voteup_count,comment_count,created,updated"
        )
        data = self._api_get(api_path)
        if data is None:
            return None

        from .scrapers.interceptor import parse_api_article
        url = f"https://zhuanlan.zhihu.com/p/{article_id}"
        return parse_api_article(data, url)

    def _api_get(self, api_path: str) -> Optional[Dict[str, Any]]:
        """Make a signed GET request to a Zhihu API endpoint."""
        x_zse_96 = generate_x_zse_96(
            x_zse_93=X_ZSE_93,
            api_path=api_path,
            d_c0=self._d_c0,
        )

        url = f"{BASE_URL}{api_path}"
        headers = {
            **_BASE_HEADERS,
            "x-zse-96": x_zse_96,
        }

        try:
            resp = self._client.get(url, headers=headers)

            block_status = self._detector.check_api_response(resp.status_code)
            if block_status.is_blocked:
                logger.warning("API blocked: %s (status=%d)", block_status.message, resp.status_code)
                return None

            if resp.status_code != 200:
                logger.debug("API returned status %d for %s", resp.status_code, api_path)
                return None

            return resp.json()

        except Exception as e:
            logger.debug("API request failed: %s", e)
            return None


# ============================================================================
# Browser-based API Client (legacy, requires Playwright)
# ============================================================================


class SignatureOracle:
    """Generate x-zse-96 signatures using the browser's JS context.

    Legacy approach - kept as fallback. For most use cases, prefer PureAPIClient.
    """

    def __init__(self, page: "Any") -> None:
        self._page = page
        self._d_c0: Optional[str] = None
        self._encrypt_fn_located: bool = False
        self._initialized: bool = False

    def initialize(self) -> bool:
        self._d_c0 = self._get_d_c0()
        if not self._d_c0:
            logger.warning("Failed to extract d_c0 cookie")
            return False

        self._encrypt_fn_located = self._locate_encrypt_fn()
        if not self._encrypt_fn_located:
            logger.warning("Failed to locate __g._encrypt function")
            return False

        self._initialized = True
        logger.info("Signature oracle initialized (d_c0=%s...)", self._d_c0[:10])
        return True

    def sign(self, api_path: str) -> Optional[Dict[str, str]]:
        if not self._initialized:
            return None

        try:
            x_zst_81 = self._get_x_zst_81()
            plaintext = f"{X_ZSE_93}+{api_path}+{self._d_c0}+{x_zst_81}"
            md5_hash = hashlib.md5(plaintext.encode()).hexdigest()

            encrypted = self._page.evaluate(
                """(hash) => {
                    try {
                        if (typeof __g !== 'undefined' && __g._encrypt) return __g._encrypt(hash);
                        if (window.__g && window.__g._encrypt) return window.__g._encrypt(hash);
                        return null;
                    } catch (e) { return null; }
                }""",
                md5_hash,
            )

            if not encrypted:
                return None

            return {"x-zse-96": f"2.0_{encrypted}", "x-zse-93": X_ZSE_93}

        except Exception as e:
            logger.debug("Signature generation failed: %s", e)
            return None

    @property
    def is_ready(self) -> bool:
        return self._initialized

    def _get_d_c0(self) -> Optional[str]:
        try:
            cookies = self._page.context.cookies(["https://www.zhihu.com"])
            for cookie in cookies:
                if cookie.get("name") == "d_c0":
                    return cookie.get("value", "").strip('"')
        except Exception:
            pass
        return None

    def _get_x_zst_81(self) -> str:
        try:
            result = self._page.evaluate("""() => {
                try { return window.__zst81 || ''; } catch(e) { return ''; }
            }""")
            return result or ""
        except Exception:
            return ""

    def _locate_encrypt_fn(self) -> bool:
        try:
            result = self._page.evaluate("""() => {
                if (typeof __g !== 'undefined' && typeof __g._encrypt === 'function') return 'found';
                if (window.__g && typeof window.__g._encrypt === 'function') return 'found';
                return 'not_found';
            }""")
            return result == "found"
        except Exception:
            return False


class ZhihuAPIClient:
    """Browser-based API client for Zhihu (requires Playwright page).

    Legacy approach. For most use cases, prefer PureAPIClient.
    """

    def __init__(self, page: "Any", proxy_url: Optional[str] = None) -> None:
        self._page = page
        self._oracle = SignatureOracle(page)
        self._detector = BlockDetector()
        self._proxy_url = proxy_url
        self._client: Optional[httpx.Client] = None

    def initialize(self) -> bool:
        current_url = self._page.url
        if "zhihu.com" not in current_url:
            self._page.goto(f"{BASE_URL}/", wait_until="domcontentloaded", timeout=30000)
            self._page.wait_for_timeout(2000)

        if not self._oracle.initialize():
            return False

        kwargs = {}
        if self._proxy_url:
            kwargs["proxy"] = self._proxy_url

        self._client = httpx.Client(timeout=30.0, follow_redirects=True, **kwargs)
        self._sync_cookies()
        return True

    def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None

    @property
    def is_ready(self) -> bool:
        return self._oracle.is_ready and self._client is not None

    def search(self, query: str, search_type: str = "general",
               limit: int = 20, offset: int = 0) -> Optional[List[SearchResult]]:
        if not self.is_ready:
            return None
        params = {"t": search_type, "q": query, "correction": 1, "offset": offset, "limit": limit}
        api_path = f"/api/v4/search_v3?{urlencode(params)}"
        data = self._api_get(api_path)
        if data is None:
            return None
        from .scrapers.interceptor import parse_api_search_results
        return parse_api_search_results(data)

    def fetch_answer(self, answer_id: str) -> Optional[ArticleDetail]:
        if not self.is_ready:
            return None
        api_path = f"/api/v4/answers/{answer_id}?include=content,voteup_count,comment_count,created_time,updated_time"
        data = self._api_get(api_path)
        if data is None:
            return None
        from .scrapers.interceptor import parse_api_article
        q_id = data.get("question", {}).get("id", "")
        return parse_api_article(data, f"{BASE_URL}/question/{q_id}/answer/{answer_id}")

    def fetch_article(self, article_id: str) -> Optional[ArticleDetail]:
        if not self.is_ready:
            return None
        api_path = f"/api/v4/articles/{article_id}?include=content,voteup_count,comment_count,created,updated"
        data = self._api_get(api_path)
        if data is None:
            return None
        from .scrapers.interceptor import parse_api_article
        return parse_api_article(data, f"https://zhuanlan.zhihu.com/p/{article_id}")

    def _api_get(self, api_path: str) -> Optional[Dict[str, Any]]:
        sig_headers = self._oracle.sign(api_path)
        if not sig_headers:
            return None
        try:
            resp = self._client.get(f"{BASE_URL}{api_path}", headers={**_BASE_HEADERS, **sig_headers})
            block = self._detector.check_api_response(resp.status_code)
            if block.is_blocked:
                return None
            if resp.status_code != 200:
                return None
            return resp.json()
        except Exception:
            return None

    def _sync_cookies(self) -> None:
        try:
            for cookie in self._page.context.cookies(["https://www.zhihu.com"]):
                self._client.cookies.set(
                    cookie["name"], cookie["value"],
                    domain=cookie.get("domain", ".zhihu.com"),
                    path=cookie.get("path", "/"),
                )
        except Exception:
            pass
