"""Douyin user profile & video list scraper using Playwright response interception."""

from __future__ import annotations

import logging
import re
from typing import Optional

from patchright.sync_api import Response, sync_playwright

from ....core.browser import get_state_path, STEALTH_SCRIPT
from ..config import (
    SOURCE_NAME,
    BASE_URL,
    USER_PROFILE_API_PATH,
    USER_POST_API_PATH,
    Timeouts,
)
from ..captcha_detect import handle_captcha
from ..models import (
    DouyinProfileResponse,
    DouyinUserProfile,
    DouyinVideoItem,
    DouyinVideoStatistics,
    DouyinVideosResponse,
)
from ..utils import build_video_url

logger = logging.getLogger(__name__)

# JS to scroll the page down to trigger more video loading
_SCROLL_JS = """
() => {
    window.scrollBy(0, 800);
}
"""


class UserProfileError(Exception):
    pass


class LoginRequiredError(UserProfileError):
    pass


def _extract_sec_uid(url: str) -> Optional[str]:
    """Extract sec_uid from a Douyin user profile URL.

    Formats:
      https://www.douyin.com/user/MS4wLjABAAAAxxx
      https://www.douyin.com/user/MS4wLjABAAAAxxx?from_tab_name=main&vid=123
    """
    match = re.search(r"/user/([A-Za-z0-9_-]+)", url)
    return match.group(1) if match else None


def _parse_profile(raw: dict) -> DouyinUserProfile:
    """Parse user profile from API response user object."""
    avatar_urls = (raw.get("avatar_thumb") or {}).get("url_list") or []
    avatar_larger_urls = (raw.get("avatar_larger") or {}).get("url_list") or []
    cover_urls = raw.get("cover_url") or []
    cover_url = None
    if isinstance(cover_urls, list) and cover_urls:
        first = cover_urls[0]
        if isinstance(first, dict):
            cover_url = (first.get("url_list") or [None])[0]
        elif isinstance(first, str):
            cover_url = first

    share_url = (raw.get("share_info") or {}).get("share_url")

    return DouyinUserProfile(
        uid=raw.get("uid"),
        sec_uid=raw.get("sec_uid"),
        unique_id=raw.get("unique_id"),
        nickname=raw.get("nickname"),
        signature=raw.get("signature"),
        avatar_url=avatar_urls[0] if avatar_urls else None,
        avatar_larger_url=avatar_larger_urls[0] if avatar_larger_urls else None,
        cover_url=cover_url,
        gender=raw.get("gender"),
        city=raw.get("city"),
        province=raw.get("province"),
        country=raw.get("country"),
        ip_location=raw.get("ip_location"),
        school_name=raw.get("school_name"),
        aweme_count=raw.get("aweme_count"),
        follower_count=raw.get("follower_count"),
        following_count=raw.get("following_count"),
        total_favorited=raw.get("total_favorited"),
        favoriting_count=raw.get("favoriting_count"),
        dongtai_count=raw.get("dongtai_count"),
        mix_count=raw.get("mix_count"),
        verification_type=raw.get("verification_type"),
        custom_verify=raw.get("custom_verify"),
        enterprise_verify_reason=raw.get("enterprise_verify_reason"),
        is_star=raw.get("is_star"),
        live_status=raw.get("live_status"),
        room_id=str(raw["room_id"]) if raw.get("room_id") else None,
        secret=raw.get("secret"),
        show_favorite_list=raw.get("show_favorite_list"),
        share_url=share_url,
    )


def _parse_video_item(raw: dict) -> DouyinVideoItem:
    """Parse a single video item from aweme_list."""
    stats_raw = raw.get("statistics") or {}
    statistics = DouyinVideoStatistics(
        digg_count=stats_raw.get("digg_count"),
        comment_count=stats_raw.get("comment_count"),
        share_count=stats_raw.get("share_count"),
        collect_count=stats_raw.get("collect_count"),
    )

    author = raw.get("author") or {}
    cover_urls = (raw.get("video") or {}).get("cover", {}).get("url_list") or []

    return DouyinVideoItem(
        aweme_id=raw.get("aweme_id", ""),
        url=build_video_url(raw.get("aweme_id", "")),
        desc=raw.get("desc"),
        create_time=raw.get("create_time"),
        duration=raw.get("duration"),
        author_name=author.get("nickname"),
        author_sec_uid=author.get("sec_uid"),
        statistics=statistics,
        cover_url=cover_urls[0] if cover_urls else None,
        share_url=raw.get("share_url"),
        is_top=bool(raw.get("is_top")),
        aweme_type=raw.get("aweme_type"),
        media_type=raw.get("media_type"),
    )


class UserProfileScraper:
    """Fetch Douyin user profile and video list via Playwright response interception."""

    def __init__(self, headless: bool = True):
        self.headless = headless

    def _build_user_url(self, sec_uid: str) -> str:
        return f"{BASE_URL}/user/{sec_uid}"

    def _setup_browser(self):
        """Create browser context with saved cookies."""
        state_file = get_state_path(SOURCE_NAME)
        storage_state = str(state_file) if state_file.exists() else None

        pw = sync_playwright().start()
        browser = pw.chromium.launch(
            headless=self.headless,
            channel="chrome",
            args=["--disable-blink-features=AutomationControlled"],
        )
        context_kwargs: dict = {
            "viewport": {"width": 1440, "height": 1024},
            "locale": "zh-CN",
        }
        if storage_state:
            context_kwargs["storage_state"] = storage_state

        context = browser.new_context(**context_kwargs)
        context.add_init_script(STEALTH_SCRIPT)
        page = context.new_page()
        return pw, browser, context, page

    def scrape_profile(self, url: str) -> DouyinProfileResponse:
        """Fetch user profile info by navigating to user page and intercepting API."""
        sec_uid = _extract_sec_uid(url)
        if not sec_uid:
            raise UserProfileError(f"Cannot extract sec_uid from URL: {url}")

        profile_data: dict = {}

        pw, browser, context, page = self._setup_browser()

        def on_response(response: Response) -> None:
            nonlocal profile_data
            if USER_PROFILE_API_PATH in response.url:
                try:
                    data = response.json()
                    if data.get("status_code") == 0 and data.get("user"):
                        profile_data = data["user"]
                except Exception:
                    pass

        page.on("response", on_response)

        try:
            target_url = self._build_user_url(sec_uid)
            page.goto(target_url, wait_until="domcontentloaded", timeout=Timeouts.NAVIGATION)
        except Exception as exc:
            context.close()
            browser.close()
            pw.stop()
            raise UserProfileError(f"Navigation failed: {exc}")

        if "/login" in page.url:
            context.close()
            browser.close()
            pw.stop()
            raise LoginRequiredError(
                "Not logged in - redirected to Douyin login page. "
                "Run 'scraper douyin login' or 'scraper douyin import-cookies'."
            )

        # Wait for profile API response
        page.wait_for_timeout(Timeouts.COMMENT_LOAD)

        # Check for CAPTCHA after initial load
        handle_captcha(page, headless=self.headless)

        context.close()
        browser.close()
        pw.stop()

        if not profile_data:
            raise UserProfileError("Failed to intercept user profile API response.")

        profile = _parse_profile(profile_data)

        return DouyinProfileResponse(
            url=url,
            sec_uid=sec_uid,
            profile=profile,
        )

    def scrape_videos(
        self,
        url: str,
        limit: int = 18,
    ) -> DouyinVideosResponse:
        """Fetch user's posted videos by intercepting API responses during scroll."""
        sec_uid = _extract_sec_uid(url)
        if not sec_uid:
            raise UserProfileError(f"Cannot extract sec_uid from URL: {url}")

        videos: list[DouyinVideoItem] = []
        seen_ids: set[str] = set()
        has_more = False
        pages_fetched = 0
        author_name: Optional[str] = None
        total_videos: Optional[int] = None
        profile_data: dict = {}

        pw, browser, context, page = self._setup_browser()

        def on_response(response: Response) -> None:
            nonlocal has_more, pages_fetched, author_name, total_videos, profile_data
            resp_url = response.url

            # Intercept profile API for metadata
            if USER_PROFILE_API_PATH in resp_url:
                try:
                    data = response.json()
                    if data.get("status_code") == 0 and data.get("user"):
                        profile_data = data["user"]
                        author_name = profile_data.get("nickname")
                        total_videos = profile_data.get("aweme_count")
                except Exception:
                    pass

            # Intercept video post list API
            if USER_POST_API_PATH in resp_url:
                try:
                    data = response.json()
                    if data.get("status_code") == 0:
                        for item in data.get("aweme_list") or []:
                            vid = item.get("aweme_id", "")
                            if vid and vid not in seen_ids:
                                seen_ids.add(vid)
                                videos.append(_parse_video_item(item))
                                if not author_name:
                                    author_name = (item.get("author") or {}).get("nickname")
                        has_more = bool(data.get("has_more"))
                        pages_fetched += 1
                except Exception:
                    pass

        page.on("response", on_response)

        try:
            target_url = self._build_user_url(sec_uid)
            page.goto(target_url, wait_until="domcontentloaded", timeout=Timeouts.NAVIGATION)
        except Exception as exc:
            context.close()
            browser.close()
            pw.stop()
            raise UserProfileError(f"Navigation failed: {exc}")

        if "/login" in page.url:
            context.close()
            browser.close()
            pw.stop()
            raise LoginRequiredError(
                "Not logged in - redirected to Douyin login page. "
                "Run 'scraper douyin login' or 'scraper douyin import-cookies'."
            )

        # Wait for initial data load
        page.wait_for_timeout(Timeouts.COMMENT_LOAD)

        # Check for CAPTCHA after initial load
        handle_captcha(page, headless=self.headless)

        # Scroll to load more videos
        max_scrolls = max(2, (limit // 18) + 3)
        for _ in range(max_scrolls):
            if len(videos) >= limit:
                break
            if pages_fetched > 0 and not has_more:
                break
            try:
                page.evaluate(_SCROLL_JS)
            except Exception:
                pass
            page.wait_for_timeout(Timeouts.SCROLL_WAIT)
            # Check for CAPTCHA during scrolling
            handle_captcha(page, headless=self.headless)

        context.close()
        browser.close()
        pw.stop()

        result_videos = videos[:limit]

        return DouyinVideosResponse(
            url=url,
            sec_uid=sec_uid,
            author_name=author_name,
            total_videos=total_videos,
            videos=result_videos,
            fetched_count=len(result_videos),
            pages_fetched=pages_fetched,
            has_more=has_more and len(videos) >= limit,
        )
