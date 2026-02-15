"""Weibo detail scraper with API-first and Playwright fallback."""

from __future__ import annotations

import json
import re
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from ....core.browser import get_state_path
from ....core.rate_limiter import RateLimiter
from ..auth import LoginStatus, _classify_url, _open_weibo_page
from ..config import (
    BASE_URL,
    DEFAULT_HEADERS,
    DETAIL_COMMENTS_API,
    DETAIL_FALLBACK_URL,
    DETAIL_SHOW_API,
    LOGGED_OUT_KEYWORDS,
    RATE_LIMIT_KEYWORDS,
    SOURCE_NAME,
    Timeouts,
)
from ..models import WeiboComment, WeiboDetailResponse, WeiboImage
from .search import LoginRequiredError, RateLimitedError, SearchError


def _clean_text(value: Optional[str]) -> str:
    """Normalize spaces and trim."""
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).replace("\u200b", "").strip()


def _strip_html(value: Optional[str]) -> str:
    """Convert HTML fragment to plain text."""
    if not value:
        return ""
    text = str(value)
    if "<" not in text and ">" not in text:
        return _clean_text(text)
    return _clean_text(BeautifulSoup(text, "lxml").get_text(" ", strip=True))


def _to_absolute_url(url: Optional[str], base_url: str) -> Optional[str]:
    """Normalize URL as absolute."""
    if not url:
        return None
    normalized = url.strip()
    if not normalized:
        return None
    if normalized.startswith("//"):
        return f"https:{normalized}"
    return urljoin(base_url, normalized)


def _safe_int(value: Any) -> Optional[int]:
    """Best-effort conversion to int."""
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

    if text in {"转发", "评论", "赞"}:
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


def _extract_user_id_from_url(user_url: Optional[str]) -> Optional[str]:
    """Extract numeric user ID from profile URL."""
    if not user_url:
        return None
    parsed = urlparse(_to_absolute_url(user_url, BASE_URL) or "")
    segments = [part for part in parsed.path.split("/") if part]
    if "u" in segments:
        index = segments.index("u")
        if index + 1 < len(segments) and segments[index + 1].isdigit():
            return segments[index + 1]
    if segments and segments[-1].isdigit():
        return segments[-1]
    return None


class DetailScraper:
    """Fetch Weibo detail by URL or MID.

    Strategy:
    1. API first (`statuses/show` + `statuses/buildComments`)
    2. Playwright fallback for anti-crawl or unexpected API failures
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
        url_or_mid: str,
        include_comments: bool = True,
        comment_pages: int = 1,
        comment_count: int = 20,
        headless: bool = True,
    ) -> WeiboDetailResponse:
        """Fetch a single Weibo post detail."""
        post = self._normalize_input(url_or_mid)
        requested_comment_pages = max(1, int(comment_pages))
        requested_comment_count = max(1, int(comment_count))

        errors: list[Exception] = []
        try:
            return self._scrape_via_http(
                post,
                include_comments=include_comments,
                comment_pages=requested_comment_pages,
                comment_count=requested_comment_count,
            )
        except SearchError as exc:
            errors.append(exc)

        if self.use_playwright_fallback:
            try:
                return self._scrape_via_playwright(
                    post,
                    include_comments=include_comments,
                    comment_pages=requested_comment_pages,
                    comment_count=requested_comment_count,
                    headless=headless,
                )
            except SearchError as exc:
                errors.append(exc)

        details = "; ".join(str(err) for err in errors if str(err))
        raise SearchError(details or "Failed to fetch Weibo detail.")

    def _normalize_input(self, value: str) -> dict[str, Optional[str]]:
        """Normalize input URL/MID into parsing hints."""
        raw = _clean_text(value)
        if not raw:
            raise SearchError("Input URL or MID cannot be empty.")

        if raw.startswith("http://") or raw.startswith("https://"):
            parsed = urlparse(raw)
            segments = [part for part in parsed.path.split("/") if part]
            if not segments:
                raise SearchError(f"Invalid Weibo URL: {value}")

            uid_hint: Optional[str] = None
            post_id = segments[-1]
            if segments[0] == "detail" and len(segments) >= 2:
                post_id = segments[1]
            elif len(segments) >= 2:
                if segments[-2].isdigit():
                    uid_hint = segments[-2]
            detail_url = raw
        else:
            post_id = raw
            uid_hint = None
            if ":" in raw:
                left, right = raw.split(":", 1)
                if left.isdigit():
                    uid_hint = left
                    post_id = right
            detail_url = self._build_detail_url(post_id=post_id, uid=uid_hint)

        post_id = post_id.split("?")[0].split("#")[0].strip("/")
        if not post_id:
            raise SearchError(f"Invalid input: {value}")

        return {
            "input_value": raw,
            "post_id": post_id,
            "uid_hint": uid_hint,
            "detail_url": detail_url,
        }

    def _build_detail_url(self, post_id: str, uid: Optional[str] = None) -> str:
        """Build a detail page URL."""
        if uid and uid.isdigit():
            return f"{BASE_URL}/{uid}/{post_id}"
        return f"{DETAIL_FALLBACK_URL}/{post_id}"

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

    def _scrape_via_http(
        self,
        post: dict[str, Optional[str]],
        include_comments: bool,
        comment_pages: int,
        comment_count: int,
    ) -> WeiboDetailResponse:
        """API-first detail implementation."""
        if not self.cookies_loaded:
            raise LoginRequiredError("No saved Weibo session found. Run 'scraper weibo login' first.")

        show_data = self._request_show_payload(post["post_id"] or "")

        comments: list[WeiboComment] = []
        comment_pages_fetched = 0
        if include_comments:
            mid = str(show_data.get("id") or show_data.get("mid") or post["post_id"] or "")
            uid = str((show_data.get("user") or {}).get("id") or post.get("uid_hint") or "")
            if mid:
                comments, comment_pages_fetched = self._fetch_comments_api(
                    mid=mid,
                    uid=uid or None,
                    max_pages=comment_pages,
                    count=comment_count,
                )

        detail = self._build_response_from_show(
            input_value=post["input_value"] or "",
            method="http",
            current_url=post["detail_url"],
            show_data=show_data,
            comments=comments,
            comment_pages_requested=comment_pages if include_comments else 0,
            comment_pages_fetched=comment_pages_fetched,
            comments_included=include_comments,
        )
        return detail

    def _request_show_payload(self, post_id: str) -> dict[str, Any]:
        """Call statuses/show endpoint."""
        data = self._request_json(
            DETAIL_SHOW_API,
            params={
                "id": post_id,
                "locale": "zh-CN",
                "isGetLongText": "true",
            },
        )
        if not isinstance(data, dict):
            raise SearchError("Unexpected detail API response format.")
        if not data.get("id") and not data.get("mid"):
            raise SearchError("Post not found or inaccessible.")
        return data

    def _fetch_comments_api(
        self,
        mid: str,
        uid: Optional[str],
        max_pages: int,
        count: int,
    ) -> tuple[list[WeiboComment], int]:
        """Fetch comments through statuses/buildComments."""
        comments: list[WeiboComment] = []
        pages_fetched = 0
        max_id: Optional[int] = None

        for page_index in range(1, max_pages + 1):
            params: dict[str, Any] = {
                "is_reload": 1,
                "id": mid,
                "is_show_bulletin": 2,
                "is_mix": 0,
                "count": count,
                "fetch_level": 0,
                "locale": "zh-CN",
            }
            if uid:
                params["uid"] = uid
            if max_id is not None:
                params["flow"] = 0
                params["max_id"] = max_id

            payload = self._request_json(DETAIL_COMMENTS_API, params=params)
            if not isinstance(payload, dict):
                break

            page_items = payload.get("data") or payload.get("comments") or []
            if not isinstance(page_items, list):
                page_items = []

            pages_fetched += 1
            for raw in page_items:
                parsed = self._parse_comment_payload(raw)
                if parsed:
                    comments.append(parsed)

            max_id = _safe_int(payload.get("max_id"))
            if not page_items or not max_id:
                break

        return comments, pages_fetched

    def _request_json(self, url: str, params: Optional[dict[str, Any]] = None) -> Any:
        """Issue an HTTP GET and parse JSON payload."""
        try:
            response = self.session.get(
                url,
                params=params,
                timeout=self.timeout,
                allow_redirects=True,
                headers={
                    **DEFAULT_HEADERS,
                    "Accept": "application/json,text/plain,*/*",
                },
            )
        except requests.RequestException as exc:
            raise SearchError(f"HTTP request failed: {exc}") from exc

        final_url = str(response.url)
        body = response.text
        if response.status_code >= 400:
            raise SearchError(f"Weibo returned HTTP {response.status_code} for {url}.")
        if self._looks_logged_out(final_url, body):
            raise LoginRequiredError("Saved session expired or login required.")
        if self._looks_rate_limited(body):
            raise RateLimitedError("Weibo requires security verification or rate-limited this request.")

        try:
            data = response.json()
        except ValueError as exc:
            raise SearchError(f"Expected JSON response from {url}.") from exc

        if isinstance(data, dict):
            ok = data.get("ok")
            if ok == 0:
                message = data.get("msg") or data.get("message") or "API returned ok=0"
                message_text = str(message)
                lower = message_text.lower()
                if "登录" in message_text or "login" in lower:
                    raise LoginRequiredError("Saved session expired or login required.")
                if "频繁" in message_text or "验证" in message_text or "captcha" in lower:
                    raise RateLimitedError("Weibo requires security verification or rate-limited this request.")
                raise SearchError(f"Weibo API error: {message_text}")

        return data

    def _build_response_from_show(
        self,
        *,
        input_value: str,
        method: str,
        current_url: Optional[str],
        show_data: dict[str, Any],
        comments: list[WeiboComment],
        comment_pages_requested: int,
        comment_pages_fetched: int,
        comments_included: bool,
    ) -> WeiboDetailResponse:
        """Convert detail API payload into output model."""
        user = show_data.get("user") or {}
        author_id = str(user.get("id")) if user.get("id") is not None else None
        mblogid = (
            show_data.get("mblogid")
            or show_data.get("bid")
            or show_data.get("idstr")
        )
        detail_url = current_url
        if author_id and mblogid:
            detail_url = f"{BASE_URL}/{author_id}/{mblogid}"

        source = _strip_html(show_data.get("source"))
        text = (
            show_data.get("text_raw")
            or show_data.get("longTextContent")
            or (show_data.get("longText") or {}).get("longTextContent")
            or _strip_html(show_data.get("text"))
        )

        images = self._extract_images(show_data)

        return WeiboDetailResponse(
            input_value=input_value,
            method=method,
            current_url=detail_url,
            post_id=str(show_data.get("id")) if show_data.get("id") is not None else None,
            mid=str(show_data.get("mid")) if show_data.get("mid") is not None else None,
            mblogid=str(mblogid) if mblogid is not None else None,
            author=_clean_text(user.get("screen_name")),
            author_id=author_id,
            author_url=_to_absolute_url(user.get("profile_url"), BASE_URL),
            created_at=_clean_text(show_data.get("created_at")),
            region_name=_clean_text(show_data.get("region_name")),
            source=source,
            text=_clean_text(text),
            reposts_count=_safe_int(show_data.get("reposts_count")),
            comments_count=_safe_int(show_data.get("comments_count")),
            attitudes_count=_safe_int(show_data.get("attitudes_count")),
            images=images,
            comments=comments,
            comment_pages_requested=comment_pages_requested,
            comment_pages_fetched=comment_pages_fetched,
            comments_included=comments_included,
        )

    def _extract_images(self, show_data: dict[str, Any]) -> list[WeiboImage]:
        """Extract images from `pic_infos` map in detail payload."""
        pic_infos = show_data.get("pic_infos")
        if not isinstance(pic_infos, dict):
            return []

        pic_ids = show_data.get("pic_ids") if isinstance(show_data.get("pic_ids"), list) else None
        ordered_ids = pic_ids or list(pic_infos.keys())
        images: list[WeiboImage] = []

        for pic_id in ordered_ids:
            info = pic_infos.get(pic_id, {})
            if not isinstance(info, dict):
                continue

            largest = info.get("largest") or {}
            original = info.get("original") or {}
            mw2000 = info.get("mw2000") or {}
            bmiddle = info.get("bmiddle") or {}
            thumbnail = info.get("thumbnail") or {}

            url = (
                largest.get("url")
                or original.get("url")
                or mw2000.get("url")
                or bmiddle.get("url")
                or thumbnail.get("url")
            )
            if not url:
                continue

            images.append(
                WeiboImage(
                    pic_id=str(pic_id),
                    url=url,
                    thumbnail_url=thumbnail.get("url") or bmiddle.get("url"),
                    width=_safe_int(largest.get("width") or original.get("width")),
                    height=_safe_int(largest.get("height") or original.get("height")),
                )
            )

        return images

    def _parse_comment_payload(self, raw: Any) -> Optional[WeiboComment]:
        """Parse a single comment object from buildComments API."""
        if not isinstance(raw, dict):
            return None

        user = raw.get("user") or {}
        text = raw.get("text_raw") or _strip_html(raw.get("text"))
        if not text:
            return None

        user_id = user.get("id")
        return WeiboComment(
            comment_id=str(raw.get("id")) if raw.get("id") is not None else None,
            root_id=str(raw.get("rootid")) if raw.get("rootid") is not None else None,
            user_id=str(user_id) if user_id is not None else None,
            user=_clean_text(user.get("screen_name")),
            user_url=_to_absolute_url(user.get("profile_url"), BASE_URL),
            text=_clean_text(text),
            created_at=_clean_text(raw.get("created_at")),
            source=_strip_html(raw.get("source")),
            likes=_safe_int(raw.get("like_counts")),
            reply_count=_safe_int(raw.get("total_number")),
        )

    def _scrape_via_playwright(
        self,
        post: dict[str, Optional[str]],
        include_comments: bool,
        comment_pages: int,
        comment_count: int,
        headless: bool,
    ) -> WeiboDetailResponse:
        """Playwright fallback detail parsing."""
        state_file = get_state_path(SOURCE_NAME)
        if not state_file.exists():
            raise LoginRequiredError("No saved Weibo session found. Run 'scraper weibo login' first.")

        target_url = post["detail_url"] or self._build_detail_url(post["post_id"] or "")

        try:
            with _open_weibo_page(headless=headless, use_storage_state=True) as page:
                page.goto(target_url, wait_until="domcontentloaded", timeout=Timeouts.NAVIGATION)
                page.wait_for_timeout(1800)

                if _classify_url(page.url) == LoginStatus.LOGGED_OUT:
                    raise LoginRequiredError("Saved session expired or login required.")

                body_preview = page.evaluate(
                    "() => document.body ? document.body.innerText.slice(0, 6000) : ''"
                )
                if self._looks_rate_limited(body_preview):
                    raise RateLimitedError("Weibo requires security verification or rate-limited this request.")

                if include_comments and comment_pages > 1:
                    for _ in range(comment_pages - 1):
                        page.mouse.wheel(0, 2000)
                        page.wait_for_timeout(1200)

                payload = page.evaluate(
                    """
                    (maxComments) => {
                      const norm = (v) => (v ? v.replace(/\\s+/g, ' ').trim() : '');
                      const article = document.querySelector('main article');
                      const getText = (selector, root = document) => {
                        const el = root.querySelector(selector);
                        return el ? norm(el.textContent) : null;
                      };
                      const getAttr = (selector, attr, root = document) => {
                        const el = root.querySelector(selector);
                        return el ? el.getAttribute(attr) : null;
                      };
                      const getCount = (value) => {
                        if (!value) return null;
                        const text = String(value).replace(/,/g, '');
                        const m = text.match(/(\\d+(?:\\.\\d+)?)([万亿]?)/);
                        if (!m) return null;
                        let num = parseFloat(m[1]);
                        if (m[2] === '万') num *= 10000;
                        if (m[2] === '亿') num *= 100000000;
                        return Math.floor(num);
                      };

                      let reposts = null;
                      let comments = null;
                      let likes = null;
                      const footer = document.querySelector('main article footer[aria-label]');
                      const footerLabel = footer ? footer.getAttribute('aria-label') : null;
                      if (footerLabel) {
                        const nums = footerLabel.split(',').map((v) => getCount(v));
                        if (nums.length >= 3) {
                          reposts = nums[0];
                          comments = nums[1];
                          likes = nums[2];
                        }
                      }
                      const likeCountText = getText('main article footer button[title="赞"] .woo-like-count');
                      if (likes == null && likeCountText) {
                        likes = getCount(likeCountText);
                      }

                      const images = article
                        ? Array.from(article.querySelectorAll('.wbpro-feed-content img'))
                            .map((img, idx) => ({
                              picId: img.getAttribute('pic-id') || String(idx),
                              url: img.getAttribute('src') || img.getAttribute('data-src') || null,
                            }))
                            .filter((item) => !!item.url)
                        : [];

                      const commentRows = Array.from(
                        document.querySelectorAll('#scroller .wbpro-scroller-item .wbpro-list .item1')
                      );
                      const commentsData = commentRows.slice(0, maxComments).map((row) => {
                        const userEl = row.querySelector('.text > a[href*="/u/"]');
                        const textEl = row.querySelector('.text > span');
                        const metaEl = row.querySelector('.info > div:first-child');
                        const likeBtn = row.querySelector('button[title="赞"]');
                        return {
                          user: userEl ? norm(userEl.textContent) : null,
                          userUrl: userEl ? userEl.getAttribute('href') : null,
                          text: textEl ? norm(textEl.textContent) : null,
                          meta: metaEl ? norm(metaEl.textContent) : null,
                          likes: likeBtn ? getCount(norm(likeBtn.textContent)) : null,
                        };
                      });

                      return {
                        url: location.href,
                        title: document.title,
                        mblogid: location.pathname.split('/').filter(Boolean).pop() || null,
                        author: getText('main article header a[href*="/u/"] span[title]') || getText('main article header a[href*="/u/"]'),
                        authorUrl: getAttr('main article header a[href*="/u/"]', 'href'),
                        createdAt: getText('main article header a[href^="https://weibo.com/"]'),
                        regionName: getAttr('main article header [title^="发布于 "]', 'title') || getText('main article header [title^="发布于 "]'),
                        source: getAttr('main article header [title^="来自 "]', 'title') || getText('main article header [title^="来自 "]'),
                        text: getText('main article .wbpro-feed-content div[class*="_wbtext_"]'),
                        reposts,
                        commentsCount: comments,
                        attitudesCount: likes,
                        images,
                        commentsData,
                      };
                    }
                    """,
                    max(comment_count * max(comment_pages, 1), comment_count),
                )

                comments: list[WeiboComment] = []
                if include_comments and isinstance(payload, dict):
                    for item in payload.get("commentsData") or []:
                        if not isinstance(item, dict):
                            continue
                        text = _clean_text(item.get("text"))
                        if not text:
                            continue
                        user_url = _to_absolute_url(item.get("userUrl"), payload.get("url") or BASE_URL)
                        user_id = _extract_user_id_from_url(user_url)
                        comments.append(
                            WeiboComment(
                                user=_clean_text(item.get("user")),
                                user_url=user_url,
                                user_id=user_id,
                                text=text,
                                created_at=_clean_text(item.get("meta")),
                                likes=_safe_int(item.get("likes")),
                            )
                        )

                detail_url = payload.get("url") if isinstance(payload, dict) else page.url
                author_url = _to_absolute_url(payload.get("authorUrl"), detail_url or BASE_URL)
                author_id = _extract_user_id_from_url(author_url)
                post_id = post.get("post_id")

                images: list[WeiboImage] = []
                if isinstance(payload, dict):
                    for raw in payload.get("images") or []:
                        if not isinstance(raw, dict):
                            continue
                        url = raw.get("url")
                        if not url:
                            continue
                        images.append(
                            WeiboImage(
                                pic_id=str(raw.get("picId")) if raw.get("picId") is not None else None,
                                url=url,
                            )
                        )

                return WeiboDetailResponse(
                    input_value=post["input_value"] or "",
                    method="playwright",
                    current_url=detail_url,
                    post_id=post_id,
                    mid=post_id,
                    mblogid=payload.get("mblogid") if isinstance(payload, dict) else None,
                    author=_clean_text(payload.get("author")) if isinstance(payload, dict) else None,
                    author_id=author_id,
                    author_url=author_url,
                    created_at=_clean_text(payload.get("createdAt")) if isinstance(payload, dict) else None,
                    region_name=_clean_text(payload.get("regionName")) if isinstance(payload, dict) else None,
                    source=_clean_text(payload.get("source")) if isinstance(payload, dict) else None,
                    text=_clean_text(payload.get("text")) if isinstance(payload, dict) else "",
                    reposts_count=_safe_int(payload.get("reposts")) if isinstance(payload, dict) else None,
                    comments_count=_safe_int(payload.get("commentsCount")) if isinstance(payload, dict) else None,
                    attitudes_count=_safe_int(payload.get("attitudesCount")) if isinstance(payload, dict) else None,
                    images=images,
                    comments=comments,
                    comment_pages_requested=comment_pages if include_comments else 0,
                    comment_pages_fetched=1 if include_comments else 0,
                    comments_included=include_comments,
                )

        except LoginRequiredError:
            raise
        except RateLimitedError:
            raise
        except Exception as exc:
            raise SearchError(f"Playwright fallback failed: {exc}") from exc

    def _looks_logged_out(self, url: str, html: str) -> bool:
        """Detect login redirect or unauthenticated responses."""
        if _classify_url(url) == LoginStatus.LOGGED_OUT:
            return True
        body = (html or "").lower()
        return any(marker.lower() in body for marker in LOGGED_OUT_KEYWORDS)

    def _looks_rate_limited(self, body: str) -> bool:
        """Detect anti-crawl / CAPTCHA page content."""
        content = (body or "").lower()
        return any(keyword.lower() in content for keyword in RATE_LIMIT_KEYWORDS)
