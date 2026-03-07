"""Weibo profile scraper — sync (default) + async parallel (--parallel) modes."""

from __future__ import annotations

import asyncio
import json
import re
import time as _time_module
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

import httpx

from ..config import (
    BASE_URL,
    PROFILE_INFO_API,
    PROFILE_MYMBLOG_API,
    PROFILE_SEARCH_API,
    SOURCE_NAME,
    DEFAULT_HEADERS,
)
from ..models import WeiboPost, WeiboProfileResponse, WeiboRetweetedPost
from ....core.browser import get_state_path, DEFAULT_DATA_DIR
from .search import LoginRequiredError, RateLimitedError, SearchError

# Shared
_MAX_RETRIES = 3

# Sync-mode constants
_MAX_ERROR_ADVANCES = 10
_ERROR_ADVANCE_STEP = 86400  # 1 day

# Async-mode constants
_MAX_CONCURRENT = 5        # concurrent chunk fetchers
_CHUNK_DAYS = 365          # days per chunk (1 year); inner continuation handles density
_CHECKPOINT_BATCH = 5      # save checkpoint every N completed chunks
_MAX_PAGES_PER_WINDOW = 50 # inner page-loop safety cap per sub-window
_MAX_ERROR_ADVANCES_CHUNK = 5  # error-advance retries inside one chunk
_MAX_RL_RETRIES = 60       # max 60 × 60s = 60 min waiting on rate-limit before skipping


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean(value: Optional[Any]) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", str(value)).replace("\u200b", "").strip()


def _safe_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    text = _clean(str(value)).replace(",", "")
    match = re.search(r"(\d+(?:\.\d+)?)\s*([万亿]?)", text)
    if not match:
        return None
    num = float(match.group(1))
    unit = match.group(2)
    if unit == "万":
        num *= 10_000
    elif unit == "亿":
        num *= 100_000_000
    return int(num)


def _parse_weibo_time(raw: Optional[str]) -> Optional[int]:
    """Parse Weibo time string like 'Thu Jan 01 07:33:00 +0800 2026' → Unix timestamp."""
    if not raw:
        return None
    try:
        return int(datetime.strptime(raw.strip(), "%a %b %d %H:%M:%S %z %Y").timestamp())
    except (ValueError, AttributeError):
        return None


def _build_detail_url(user_id: Optional[str], mblogid: Optional[str], post_id: Optional[str]) -> Optional[str]:
    if user_id and mblogid:
        return f"{BASE_URL}/{user_id}/{mblogid}"
    if post_id:
        return f"{BASE_URL}/detail/{post_id}"
    return None


def _parse_post(raw: Any) -> Optional[WeiboPost]:
    if not isinstance(raw, dict):
        return None
    user = raw.get("user") or {}
    user_id = str(user.get("id")) if user.get("id") is not None else None
    mblogid = raw.get("mblogid") or raw.get("bid") or raw.get("idstr")
    post_id = str(raw.get("id")) if raw.get("id") is not None else None
    text_raw = _clean(raw.get("text_raw") or raw.get("text") or "")
    retweeted_raw = raw.get("retweeted_status")
    retweeted: Optional[WeiboRetweetedPost] = None
    if isinstance(retweeted_raw, dict):
        rt_user = retweeted_raw.get("user") or {}
        retweeted = WeiboRetweetedPost(
            id=str(retweeted_raw["id"]) if retweeted_raw.get("id") is not None else None,
            mblogid=retweeted_raw.get("mblogid") or retweeted_raw.get("idstr"),
            user_id=str(rt_user.get("id")) if rt_user.get("id") is not None else None,
            user_screen_name=_clean(rt_user.get("screen_name")),
            created_at=_clean(retweeted_raw.get("created_at")),
            text_raw=_clean(retweeted_raw.get("text_raw") or retweeted_raw.get("text") or ""),
        )
    pic_ids_raw = raw.get("pic_ids")
    pic_ids = [str(p) for p in pic_ids_raw] if isinstance(pic_ids_raw, list) else []
    return WeiboPost(
        id=post_id,
        mid=str(raw.get("mid")) if raw.get("mid") is not None else None,
        mblogid=str(mblogid) if mblogid is not None else None,
        detail_url=_build_detail_url(user_id, mblogid, post_id),
        user_id=user_id,
        user_screen_name=_clean(user.get("screen_name")),
        created_at=_clean(raw.get("created_at")),
        source=_clean(raw.get("source")),
        region_name=_clean(raw.get("region_name")),
        text_raw=text_raw,
        is_long_text=bool(raw.get("isLongText")),
        reposts_count=_safe_int(raw.get("reposts_count")),
        comments_count=_safe_int(raw.get("comments_count")),
        attitudes_count=_safe_int(raw.get("attitudes_count")),
        pic_ids=pic_ids,
        pic_num=_safe_int(raw.get("pic_num")) or len(pic_ids),
        is_top=bool(raw.get("isTop")),
        is_ad=bool(raw.get("isAd")),
        retweeted=retweeted,
    )


def _split_time_range(start: int, end: int, chunk_days: int = _CHUNK_DAYS) -> list[tuple[int, int]]:
    """Split [start, end] into fixed-size chunks (newest-first)."""
    step = chunk_days * 86400
    chunks: list[tuple[int, int]] = []
    cur_end = end
    while cur_end > start:
        cur_start = max(start, cur_end - step + 1)
        chunks.append((cur_start, cur_end))
        cur_end = cur_start - 1
    return chunks


def _deduplicate_and_sort(posts: list[WeiboPost]) -> list[WeiboPost]:
    """Remove duplicate posts (by ID) and sort newest-first."""
    seen: set[str] = set()
    unique: list[WeiboPost] = []
    for post in posts:
        key = post.id or post.mblogid or post.mid
        if key:
            if key in seen:
                continue
            seen.add(key)
        unique.append(post)
    unique.sort(key=lambda p: _parse_weibo_time(p.created_at) or 0, reverse=True)
    return unique


# ---------------------------------------------------------------------------
# Checkpoint  (v1 = sync sequential, v2 = async parallel)
# ---------------------------------------------------------------------------

def _checkpoint_dir() -> Path:
    return DEFAULT_DATA_DIR / SOURCE_NAME / "checkpoints"


def save_checkpoint(
    path: Path,
    posts: list[WeiboPost],
    seen_ids: set[str],
    total_pages: int,
    # v1 (sync) fields:
    current_end_time: Optional[int] = None,
    total_in_range: Optional[int] = None,
    # v2 (async) fields:
    remaining_chunks: Optional[list[tuple[int, int]]] = None,
) -> None:
    """Save checkpoint. Pass ``remaining_chunks`` for async mode, ``current_end_time`` for sync."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if remaining_chunks is not None:
        # v2 format (async parallel mode)
        data: dict = {
            "version": 2,
            "posts": [p.model_dump(mode="json") for p in posts],
            "seen_ids": list(seen_ids),
            "remaining_chunks": [list(c) for c in remaining_chunks],
            "total_pages": total_pages,
            # compat hint for CLI display
            "current_end_time": current_end_time or (remaining_chunks[0][1] if remaining_chunks else None),
        }
    else:
        # v1 format (sync sequential mode)
        data = {
            "version": 1,
            "posts": [p.model_dump(mode="json") for p in posts],
            "seen_ids": list(seen_ids),
            "current_end_time": current_end_time,
            "total_pages": total_pages,
            "total_in_range": total_in_range,
        }
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def load_checkpoint(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        posts = [WeiboPost.model_validate(p) for p in raw.get("posts", [])]
        seen_ids = set(raw.get("seen_ids", []))
        version = raw.get("version", 1)

        if version >= 2:
            remaining_chunks: list[tuple[int, int]] = [
                tuple(c) for c in raw.get("remaining_chunks", [])  # type: ignore[misc]
            ]
            return {
                "version": 2,
                "posts": posts,
                "seen_ids": seen_ids,
                "remaining_chunks": remaining_chunks,
                "total_pages": raw.get("total_pages", 0),
                "current_end_time": raw.get("current_end_time")
                    or (remaining_chunks[0][1] if remaining_chunks else None),
            }
        else:
            return {
                "version": 1,
                "posts": posts,
                "seen_ids": seen_ids,
                "remaining_chunks": None,
                "current_end_time": raw.get("current_end_time"),
                "total_pages": raw.get("total_pages", 0),
                "total_in_range": raw.get("total_in_range"),
            }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# HTTP client factory
# ---------------------------------------------------------------------------

def _load_cookies_from_state() -> dict[str, str]:
    state_file = get_state_path(SOURCE_NAME)
    if not state_file.exists():
        return {}
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
        return {
            c["name"]: c["value"]
            for c in state.get("cookies", [])
            if "weibo.com" in c.get("domain", "")
        }
    except Exception:
        return {}


def _client_kwargs() -> dict:
    return {
        "cookies": _load_cookies_from_state(),
        "headers": {
            **DEFAULT_HEADERS,
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": BASE_URL,
        },
        "timeout": 20,
        "follow_redirects": True,
    }


# ---------------------------------------------------------------------------
# Async chunk fetcher  (used only in parallel mode)
# ---------------------------------------------------------------------------

async def _fetch_chunk(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    base_params: dict,
    chunk_start: int,
    chunk_end: int,
    on_page: Optional[Callable[[int], None]] = None,
    on_status: Optional[Callable[[str], None]] = None,
) -> tuple[list[WeiboPost], int]:
    """Fetch ALL posts within [chunk_start, chunk_end] with internal time-window continuation.

    No within-chunk dedup — caller is responsible for deduplication.
    ``on_page(n)`` is called after each page with the number of posts parsed.
    ``on_status(msg)`` is called on warnings (rate limit backoff, error advances, etc.).
    """
    async with semaphore:
        posts: list[WeiboPost] = []
        pages_total = 0
        current_end = chunk_end
        error_advances = 0

        while current_end > chunk_start:
            since_id: Optional[str] = None
            page_num = 1
            window_added = 0
            window_had_error = False
            window_oldest_ts: Optional[int] = None

            # Inner page loop: exhaust cursor for current sub-window
            for _ in range(_MAX_PAGES_PER_WINDOW):
                page_params = {
                    **base_params,
                    "starttime": chunk_start,
                    "endtime": current_end,
                    "page": page_num,
                }
                if since_id:
                    page_params["since_id"] = since_id

                # Fetch with rate-limit-aware retry: 418/429 → 60s wait loop
                data: Optional[dict] = None
                rl_retries = 0

                while True:
                    # Network-level retries (transient connection errors)
                    resp = None
                    for attempt in range(_MAX_RETRIES):
                        try:
                            resp = await client.get(PROFILE_SEARCH_API, params=page_params)
                            break
                        except asyncio.CancelledError:
                            raise
                        except Exception as exc:
                            if attempt < _MAX_RETRIES - 1:
                                await asyncio.sleep(2 * (attempt + 1))
                            else:
                                if on_status:
                                    on_status(f"network error: {exc}")

                    if resp is None:
                        break  # persistent network error

                    if resp.status_code == 403:
                        raise LoginRequiredError("HTTP 403")

                    if resp.status_code in (418, 429):
                        rl_retries += 1
                        if rl_retries > _MAX_RL_RETRIES:
                            if on_status:
                                on_status(f"HTTP {resp.status_code} — max retries ({_MAX_RL_RETRIES}) exceeded, skipping page")
                            break
                        if on_status:
                            on_status(f"HTTP {resp.status_code} — rate limited, waiting 60s (retry #{rl_retries}/{_MAX_RL_RETRIES})...")
                        await asyncio.sleep(60)
                        continue

                    try:
                        raw_json = resp.json()
                    except Exception:
                        break  # bad JSON

                    if not isinstance(raw_json, dict):
                        break

                    ok_val = raw_json.get("ok")
                    if ok_val == -100:
                        raise LoginRequiredError("Session expired.")
                    if ok_val == 0:
                        msg = str(raw_json.get("message") or raw_json.get("msg") or "")
                        if "频繁" in msg or "验证" in msg or "captcha" in msg.lower():
                            rl_retries += 1
                            if rl_retries > _MAX_RL_RETRIES:
                                if on_status:
                                    on_status(f"rate limited — max retries exceeded, skipping page")
                                break
                            if on_status:
                                on_status(f"rate limited — waiting 60s (retry #{rl_retries}/{_MAX_RL_RETRIES})...")
                            await asyncio.sleep(60)
                            continue
                        break  # other soft error: skip page

                    data = raw_json
                    break  # success

                if data is None:
                    window_had_error = True
                    break

                list_data = data.get("data") or {}
                raw_items = list_data.get("list") or []
                if not isinstance(raw_items, list) or not raw_items:
                    break

                pages_total += 1
                new_since_id = list_data.get("since_id")
                if new_since_id:
                    since_id = str(new_since_id)

                # No within-chunk dedup: track all posts, let caller dedup
                page_new = 0
                for raw in raw_items:
                    post = _parse_post(raw)
                    if post is None:
                        continue
                    posts.append(post)
                    window_added += 1
                    page_new += 1
                    ts = _parse_weibo_time(post.created_at)
                    if ts and (window_oldest_ts is None or ts < window_oldest_ts):
                        window_oldest_ts = ts

                if on_page:
                    on_page(page_new)

                if not new_since_id:
                    break
                page_num += 1

            # Time-window continuation decision
            if window_added == 0:
                if window_had_error and error_advances < _MAX_ERROR_ADVANCES_CHUNK:
                    error_advances += 1
                    current_end -= _ERROR_ADVANCE_STEP
                    if on_status:
                        on_status(f"error advance #{error_advances}: skip to {datetime.fromtimestamp(current_end).strftime('%Y-%m-%d')}")
                    if current_end <= chunk_start:
                        break
                    continue
                break  # truly empty or persistent error

            error_advances = 0

            if window_oldest_ts is None or window_oldest_ts <= chunk_start:
                break
            current_end = window_oldest_ts - 1

        return posts, pages_total


# ---------------------------------------------------------------------------
# ProfileScraper
# ---------------------------------------------------------------------------

class ProfileScraper:
    """Fetch posts from a Weibo user's profile via direct httpx API.

    Two modes for ``scrape_filtered``:
    - Default (sync): sequential time-window continuation, incremental progress,
      supports ``total_in_range`` estimate and fine-grained error recovery.
    - Parallel (use_async=True): pre-splits range into 30-day chunks, fetches
      concurrently (up to 5 at a time), deduplicates at the end.  Faster for
      large time ranges but no per-chunk ``total_in_range``.
    """

    def __init__(self, headless: bool = True) -> None:
        self.headless = headless  # kept for API compat

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scrape_latest(
        self,
        uid: str,
        limit: int = 20,
        skip_ads: bool = True,
    ) -> WeiboProfileResponse:
        """Fetch the latest N posts (cursor-based, sequential)."""
        state_file = get_state_path(SOURCE_NAME)
        if not state_file.exists():
            raise LoginRequiredError("No saved Weibo session. Run 'scraper weibo login' first.")

        with httpx.Client(**_client_kwargs()) as client:
            screen_name, total_posts = self._profile_info(client, uid)
            posts, pages_fetched, since_id = self._latest_posts(
                client, uid, limit=limit, skip_ads=skip_ads
            )

        return WeiboProfileResponse(
            uid=uid,
            screen_name=screen_name,
            total_posts=total_posts,
            mode="latest",
            posts=posts,
            pages_fetched=pages_fetched,
            since_id=since_id,
        )

    def scrape_filtered(
        self,
        uid: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        keyword: Optional[str] = None,
        limit: Optional[int] = None,
        has_ori: bool = True,
        has_text: bool = True,
        has_pic: bool = True,
        has_video: bool = True,
        has_music: bool = True,
        has_ret: bool = True,
        skip_ads: bool = True,
        progress_callback: Optional[Callable[[int, int, Optional[int]], None]] = None,
        checkpoint_path: Optional[Path] = None,
        use_async: bool = False,
        status_callback: Optional[Callable[[str], None]] = None,
        max_concurrent: int = _MAX_CONCURRENT,
    ) -> WeiboProfileResponse:
        """Fetch posts via searchProfile API.

        Args:
            use_async: If True, use parallel async time-window fetching (faster
                       for large ranges, splits into yearly chunks).  Default False
                       uses sequential mode.
            status_callback: Called with a status message string on warnings such
                             as rate-limit backoff, 418/429 responses, or error advances.
            max_concurrent: Max parallel chunk fetchers (async mode only, default 5).
                            Reduce to 2-3 to avoid triggering Weibo anti-bot detection.
        """
        if use_async:
            return asyncio.run(
                self._async_filtered(
                    uid=uid,
                    start_time=start_time,
                    end_time=end_time,
                    keyword=keyword,
                    limit=limit,
                    has_ori=has_ori,
                    has_text=has_text,
                    has_pic=has_pic,
                    has_video=has_video,
                    has_music=has_music,
                    has_ret=has_ret,
                    skip_ads=skip_ads,
                    progress_callback=progress_callback,
                    checkpoint_path=checkpoint_path,
                    status_callback=status_callback,
                    max_concurrent=max_concurrent,
                )
            )
        return self._sync_filtered(
            uid=uid,
            start_time=start_time,
            end_time=end_time,
            keyword=keyword,
            limit=limit,
            has_ori=has_ori,
            has_text=has_text,
            has_pic=has_pic,
            has_video=has_video,
            has_music=has_music,
            has_ret=has_ret,
            skip_ads=skip_ads,
            progress_callback=progress_callback,
            checkpoint_path=checkpoint_path,
        )

    # ------------------------------------------------------------------
    # Sync implementation  (default)
    # ------------------------------------------------------------------

    def _sync_filtered(
        self,
        uid: str,
        start_time: Optional[int],
        end_time: Optional[int],
        keyword: Optional[str],
        limit: Optional[int],
        has_ori: bool,
        has_text: bool,
        has_pic: bool,
        has_video: bool,
        has_music: bool,
        has_ret: bool,
        skip_ads: bool,
        progress_callback: Optional[Callable[[int, int, Optional[int]], None]],
        checkpoint_path: Optional[Path],
    ) -> WeiboProfileResponse:
        state_file = get_state_path(SOURCE_NAME)
        if not state_file.exists():
            raise LoginRequiredError("No saved Weibo session. Run 'scraper weibo login' first.")

        with httpx.Client(**_client_kwargs()) as client:
            screen_name, total_posts_count = self._profile_info(client, uid)
            posts, pages_fetched, total_in_range = self._fetch_filtered_posts(
                client,
                uid=uid,
                start_time=start_time,
                end_time=end_time,
                keyword=keyword,
                limit=limit,
                has_ori=has_ori,
                has_text=has_text,
                has_pic=has_pic,
                has_video=has_video,
                has_music=has_music,
                has_ret=has_ret,
                skip_ads=skip_ads,
                progress_callback=progress_callback,
                checkpoint_path=checkpoint_path,
            )

        mode = "time_range" if (start_time or end_time) else "keyword"
        if start_time and end_time and keyword:
            mode = "time_range+keyword"
        elif keyword and not start_time and not end_time:
            mode = "keyword"

        return WeiboProfileResponse(
            uid=uid,
            screen_name=screen_name,
            total_posts=total_posts_count,
            mode=mode,
            keyword=keyword,
            start_time=start_time,
            end_time=end_time,
            total_in_range=total_in_range,
            posts=posts,
            pages_fetched=pages_fetched,
        )

    def _fetch_filtered_posts(
        self,
        client: httpx.Client,
        uid: str,
        start_time: Optional[int],
        end_time: Optional[int],
        keyword: Optional[str],
        limit: Optional[int],
        has_ori: bool,
        has_text: bool,
        has_pic: bool,
        has_video: bool,
        has_music: bool,
        has_ret: bool,
        skip_ads: bool,
        progress_callback: Optional[Callable[[int, int, Optional[int]], None]],
        checkpoint_path: Optional[Path],
    ) -> tuple[list[WeiboPost], int, Optional[int]]:
        """Sequential time-window continuation via searchProfile API."""
        # Load checkpoint
        ckpt = load_checkpoint(checkpoint_path) if checkpoint_path else None
        if ckpt:
            all_posts: list[WeiboPost] = list(ckpt["posts"])
            seen_ids: set[str] = ckpt["seen_ids"]
            total_pages: int = ckpt.get("total_pages", 0)
            total_in_range: Optional[int] = ckpt.get("total_in_range")
            current_end_time: Optional[int] = ckpt.get("current_end_time") or end_time
        else:
            all_posts = []
            seen_ids = set()
            total_pages = 0
            total_in_range = None
            current_end_time = end_time

        # Static filter params
        filter_params: dict = {"uid": uid}
        if keyword:
            filter_params["q"] = keyword
        if has_ori:
            filter_params["hasori"] = 1
        if has_text:
            filter_params["hastext"] = 1
        if has_pic:
            filter_params["haspic"] = 1
        if has_video:
            filter_params["hasvideo"] = 1
        if has_music:
            filter_params["hasmusic"] = 1
        if has_ret:
            filter_params["hasret"] = 1

        error_advances = 0

        while True:
            base_params = dict(filter_params)
            if start_time is not None:
                base_params["starttime"] = start_time
            if current_end_time is not None:
                base_params["endtime"] = current_end_time

            page_num = 1
            since_id: Optional[str] = None
            chunk_added = 0
            chunk_had_error = False

            while True:
                params = dict(base_params)
                params["page"] = page_num
                if since_id:
                    params["since_id"] = since_id

                data = self._fetch_json_with_retry(client, PROFILE_SEARCH_API, params)

                if data is None:
                    chunk_had_error = True
                    break

                list_data = data.get("data") or {}
                raw_items = list_data.get("list") or []

                if not isinstance(raw_items, list) or not raw_items:
                    break

                total_pages += 1

                if total_in_range is None:
                    total_in_range = _safe_int(list_data.get("total"))

                new_since_id = list_data.get("since_id")
                if new_since_id:
                    since_id = str(new_since_id)

                added_this_page = 0
                for raw in raw_items:
                    post = _parse_post(raw)
                    if post is None:
                        continue
                    if skip_ads and post.is_ad:
                        continue
                    post_key = post.id or post.mblogid or post.mid
                    if post_key:
                        if post_key in seen_ids:
                            continue
                        seen_ids.add(post_key)
                    all_posts.append(post)
                    added_this_page += 1
                    chunk_added += 1
                    if limit is not None and len(all_posts) >= limit:
                        break

                if progress_callback:
                    progress_callback(total_pages, len(all_posts), total_in_range)

                if limit is not None and len(all_posts) >= limit:
                    break
                if total_in_range is not None and len(all_posts) >= total_in_range:
                    break
                if added_this_page == 0 and not new_since_id:
                    break
                if not new_since_id:
                    break

                page_num += 1

            if limit is not None and len(all_posts) >= limit:
                break
            if total_in_range is not None and len(all_posts) >= total_in_range:
                break

            if chunk_added == 0:
                if chunk_had_error and error_advances < _MAX_ERROR_ADVANCES:
                    error_advances += 1
                    current_end_time = (current_end_time or 0) - _ERROR_ADVANCE_STEP
                    if start_time is not None and current_end_time <= start_time:
                        break
                    if checkpoint_path and all_posts:
                        save_checkpoint(
                            checkpoint_path, all_posts, seen_ids, total_pages,
                            current_end_time=current_end_time, total_in_range=total_in_range,
                        )
                    continue
                break

            error_advances = 0

            oldest_ts = _parse_weibo_time(all_posts[-1].created_at)
            if oldest_ts is None:
                break
            if start_time is not None and oldest_ts <= start_time:
                break
            current_end_time = oldest_ts - 1

            if checkpoint_path and all_posts:
                save_checkpoint(
                    checkpoint_path, all_posts, seen_ids, total_pages,
                    current_end_time=current_end_time, total_in_range=total_in_range,
                )

        return all_posts, total_pages, total_in_range

    # ------------------------------------------------------------------
    # Async implementation  (use_async=True)
    # ------------------------------------------------------------------

    async def _async_filtered(
        self,
        uid: str,
        start_time: Optional[int],
        end_time: Optional[int],
        keyword: Optional[str],
        limit: Optional[int],
        has_ori: bool,
        has_text: bool,
        has_pic: bool,
        has_video: bool,
        has_music: bool,
        has_ret: bool,
        skip_ads: bool,
        progress_callback: Optional[Callable[[int, int, Optional[int]], None]],
        checkpoint_path: Optional[Path],
        status_callback: Optional[Callable[[str], None]] = None,
        max_concurrent: int = _MAX_CONCURRENT,
    ) -> WeiboProfileResponse:
        state_file = get_state_path(SOURCE_NAME)
        if not state_file.exists():
            raise LoginRequiredError("No saved Weibo session. Run 'scraper weibo login' first.")

        base_params: dict = {"uid": uid}
        if keyword:
            base_params["q"] = keyword
        if has_ori:
            base_params["hasori"] = 1
        if has_text:
            base_params["hastext"] = 1
        if has_pic:
            base_params["haspic"] = 1
        if has_video:
            base_params["hasvideo"] = 1
        if has_music:
            base_params["hasmusic"] = 1
        if has_ret:
            base_params["hasret"] = 1

        # Load or init state
        ckpt = load_checkpoint(checkpoint_path) if checkpoint_path else None
        if ckpt:
            all_posts: list[WeiboPost] = list(ckpt["posts"])
            seen_ids: set[str] = ckpt["seen_ids"]
            total_pages = ckpt.get("total_pages", 0)

            if ckpt.get("version", 1) >= 2 and ckpt.get("remaining_chunks"):
                # v2 checkpoint: resume from stored remaining chunks
                remaining: list[tuple[int, int]] = list(ckpt["remaining_chunks"])
            else:
                # v1 checkpoint: re-split from saved end_time
                old_end = ckpt.get("current_end_time") or end_time or int(_time_module.time())
                remaining = _split_time_range(start_time or 0, old_end)
        else:
            all_posts = []
            seen_ids = set()
            total_pages = 0
            eff_end = end_time or int(_time_module.time())
            remaining = _split_time_range(start_time or 0, eff_end)

        # Fetch profile info once (sync)
        with httpx.Client(**_client_kwargs()) as sync_client:
            screen_name, total_posts_count = self._profile_info(sync_client, uid)

        # Shared mutable counters (asyncio is single-threaded — no lock needed)
        pages_counter = [total_pages]
        posts_counter = [len(all_posts)]

        def on_page(new_posts: int = 0) -> None:
            pages_counter[0] += 1
            posts_counter[0] += new_posts  # real-time count (pre-dedup, close enough)
            if progress_callback:
                progress_callback(pages_counter[0], posts_counter[0], None)

        semaphore = asyncio.Semaphore(max_concurrent)

        async with httpx.AsyncClient(**_client_kwargs()) as client:
            while remaining and (limit is None or len(all_posts) < limit):
                batch, remaining = remaining[:_CHECKPOINT_BATCH], remaining[_CHECKPOINT_BATCH:]

                try:
                    results = await asyncio.gather(
                        *[
                            _fetch_chunk(client, semaphore, base_params, s, e, on_page=on_page, on_status=status_callback)
                            for s, e in batch
                        ],
                        return_exceptions=True,
                    )
                except asyncio.CancelledError:
                    # Ctrl+C mid-batch: persist current posts + unfinished chunks
                    if checkpoint_path:
                        save_checkpoint(
                            checkpoint_path, all_posts, seen_ids, pages_counter[0],
                            remaining_chunks=batch + remaining,
                        )
                    raise

                for result in results:
                    if isinstance(result, (LoginRequiredError, RateLimitedError)):
                        raise result  # type: ignore[misc]
                    if isinstance(result, Exception):
                        continue  # skip failed chunks silently
                    chunk_posts, _chunk_pages = result  # type: ignore[misc]
                    for post in chunk_posts:
                        if skip_ads and post.is_ad:
                            continue
                        key = post.id or post.mblogid or post.mid
                        if key and key in seen_ids:
                            continue
                        if key:
                            seen_ids.add(key)
                        all_posts.append(post)
                        posts_counter[0] = len(all_posts)
                        if limit is not None and len(all_posts) >= limit:
                            break

                if checkpoint_path and remaining:
                    save_checkpoint(
                        checkpoint_path, all_posts, seen_ids, pages_counter[0],
                        remaining_chunks=remaining,
                    )

                if limit is not None and len(all_posts) >= limit:
                    break

        # Deduplicate + sort newest-first
        final_posts = _deduplicate_and_sort(all_posts)
        if limit is not None:
            final_posts = final_posts[:limit]

        mode = "time_range" if (start_time or end_time) else "keyword"
        if start_time and end_time and keyword:
            mode = "time_range+keyword"
        elif keyword and not start_time and not end_time:
            mode = "keyword"

        return WeiboProfileResponse(
            uid=uid,
            screen_name=screen_name,
            total_posts=total_posts_count,
            mode=mode,
            keyword=keyword,
            start_time=start_time,
            end_time=end_time,
            posts=final_posts,
            pages_fetched=pages_counter[0],
        )

    # ------------------------------------------------------------------
    # Shared sync helpers
    # ------------------------------------------------------------------

    def _fetch_json(self, client: httpx.Client, url: str, params: dict) -> dict:
        try:
            resp = client.get(url, params=params)
        except httpx.RequestError as exc:
            raise SearchError(f"HTTP request failed: {exc}") from exc
        if resp.status_code == 403:
            raise LoginRequiredError("Session expired (HTTP 403).")
        try:
            data = resp.json()
        except Exception as exc:
            raise SearchError("Invalid JSON response") from exc
        if not isinstance(data, dict):
            raise SearchError("Unexpected non-dict response")
        ok_val = data.get("ok")
        if ok_val == 0 or ok_val == -100:
            msg = str(data.get("message") or data.get("msg") or "")
            if ok_val == -100 or "登录" in msg or "login" in msg.lower():
                raise LoginRequiredError("Session expired.")
            if "频繁" in msg or "验证" in msg or "captcha" in msg.lower():
                raise RateLimitedError("Rate limited.")
            if msg:
                raise SearchError(f"API error: {msg}")
        return data

    def _fetch_json_with_retry(self, client: httpx.Client, url: str, params: dict) -> Optional[dict]:
        """Fetch JSON with retries on transient errors. Returns None on persistent failure."""
        for attempt in range(_MAX_RETRIES):
            try:
                return self._fetch_json(client, url, params)
            except (LoginRequiredError, RateLimitedError):
                raise
            except SearchError:
                if attempt < _MAX_RETRIES - 1:
                    import time
                    time.sleep(2 * (attempt + 1))
        return None

    def _profile_info(self, client: httpx.Client, uid: str) -> tuple[Optional[str], Optional[int]]:
        try:
            data = self._fetch_json(client, PROFILE_INFO_API, {"uid": uid})
            user = (data.get("data") or {}).get("user") or {}
            return _clean(user.get("screen_name")) or None, _safe_int(user.get("statuses_count"))
        except Exception:
            return None, None

    def _latest_posts(
        self,
        client: httpx.Client,
        uid: str,
        limit: int,
        skip_ads: bool,
    ) -> tuple[list[WeiboPost], int, Optional[str]]:
        posts: list[WeiboPost] = []
        pages_fetched = 0
        since_id: Optional[str] = None
        page_num = 1

        while len(posts) < limit:
            params: dict = {"uid": uid, "page": page_num, "feature": 0}
            if since_id:
                params["since_id"] = since_id
            data = self._fetch_json(client, PROFILE_MYMBLOG_API, params)
            list_data = data.get("data") or {}
            raw_items = list_data.get("list") or []
            if not isinstance(raw_items, list) or not raw_items:
                break
            pages_fetched += 1
            since_id = list_data.get("since_id")
            for raw in raw_items:
                if len(posts) >= limit:
                    break
                post = _parse_post(raw)
                if post is None or (skip_ads and post.is_ad):
                    continue
                posts.append(post)
            page_num += 1
            if not since_id or len(raw_items) < 10:
                break

        return posts, pages_fetched, since_id
