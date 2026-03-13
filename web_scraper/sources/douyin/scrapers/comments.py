"""Douyin comment scraper using Playwright response interception."""

from __future__ import annotations

import re
from typing import Optional

from patchright.sync_api import Response, sync_playwright

from ....core.browser import get_state_path, STEALTH_SCRIPT
from ..config import (
    SOURCE_NAME,
    COMMENT_API_PATH,
    COMMENT_REPLY_API_PATH,
    Timeouts,
)
from ..captcha_detect import handle_captcha
from ..models import DouyinComment, DouyinFetchResponse, DouyinReply, DouyinUser
from ..utils import normalize_video_target

# JS to scroll the comment panel (tries class-name heuristics, then falls back to window scroll)
_SCROLL_JS = """
() => {
    const candidates = Array.from(document.querySelectorAll(
        '[class*="comment"], [class*="Comment"]'
    )).filter(el => el.scrollHeight > el.clientHeight + 100);
    if (candidates.length > 0) {
        candidates.sort((a, b) => b.scrollHeight - a.scrollHeight);
        candidates[0].scrollTop += 700;
        return true;
    }
    window.scrollBy(0, 700);
    return false;
}
"""

# JS to click all visible "expand replies" buttons
_EXPAND_REPLIES_JS = """
() => {
    const selectors = [
        '[class*="replyBtn"]',
        '[class*="reply-btn"]',
        '[class*="viewReply"]',
        '[class*="expand"]',
    ];
    let clicked = 0;
    for (const sel of selectors) {
        document.querySelectorAll(sel).forEach(btn => {
            if (btn.offsetParent !== null) {
                btn.click();
                clicked++;
            }
        });
    }
    return clicked;
}
"""


class CommentScrapingError(Exception):
    pass


class LoginRequiredError(CommentScrapingError):
    pass

def _parse_user(raw: dict) -> Optional[DouyinUser]:
    if not raw:
        return None
    avatar_urls = (raw.get("avatar_thumb") or {}).get("url_list") or []
    return DouyinUser(
        uid=raw.get("uid"),
        sec_uid=raw.get("sec_uid"),
        nickname=raw.get("nickname"),
        avatar_url=avatar_urls[0] if avatar_urls else None,
        ip_label=raw.get("ip_label"),
    )


def _parse_comment(raw: dict) -> DouyinComment:
    return DouyinComment(
        cid=str(raw["cid"]) if raw.get("cid") else None,
        text=raw.get("text", ""),
        user=_parse_user(raw.get("user") or {}),
        digg_count=raw.get("digg_count"),
        reply_count=raw.get("reply_comment_total"),
        created_at=raw.get("create_time"),
        ip_label=raw.get("ip_label"),
    )


def _parse_reply(raw: dict) -> DouyinReply:
    return DouyinReply(
        cid=str(raw["cid"]) if raw.get("cid") else None,
        text=raw.get("text", ""),
        user=_parse_user(raw.get("user") or {}),
        digg_count=raw.get("digg_count"),
        created_at=raw.get("create_time"),
        ip_label=raw.get("ip_label"),
    )


class CommentScraper:
    """Fetch Douyin video comments via Playwright response interception."""

    def __init__(self, headless: bool = True):
        self.headless = headless

    def scrape(
        self,
        url: str,
        limit: int = 20,
        with_replies: bool = False,
        reply_limit: int = 3,
    ) -> DouyinFetchResponse:
        aweme_id, canonical_url = normalize_video_target(url)
        if not aweme_id or not canonical_url:
            raise CommentScrapingError(f"Cannot extract video ID from URL or ID: {url}")

        state_file = get_state_path(SOURCE_NAME)
        storage_state = str(state_file) if state_file.exists() else None

        comments: list[DouyinComment] = []
        seen_cids: set[str] = set()
        total_comments: Optional[int] = None
        desc: Optional[str] = None
        author_name: Optional[str] = None
        pages_fetched = 0

        # cid → list of replies collected via response interception
        reply_batches: dict[str, list[DouyinReply]] = {}

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
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

            def on_response(response: Response) -> None:
                nonlocal total_comments, pages_fetched, desc, author_name
                resp_url = response.url

                if COMMENT_API_PATH in resp_url and COMMENT_REPLY_API_PATH not in resp_url:
                    try:
                        data = response.json()
                        if data.get("status_code") == 0:
                            if total_comments is None:
                                total_comments = data.get("total")
                            for rc in data.get("comments") or []:
                                c = _parse_comment(rc)
                                if c.cid and c.cid not in seen_cids:
                                    seen_cids.add(c.cid)
                                    comments.append(c)
                            pages_fetched += 1
                    except Exception:
                        pass

                elif with_replies and COMMENT_REPLY_API_PATH in resp_url:
                    try:
                        data = response.json()
                        if data.get("status_code") == 0:
                            replies = [_parse_reply(r) for r in data.get("comments") or []]
                            m = re.search(r"comment_id=(\d+)", resp_url)
                            if m:
                                parent_cid = m.group(1)
                                existing = reply_batches.setdefault(parent_cid, [])
                                existing.extend(replies)
                    except Exception:
                        pass

            page.on("response", on_response)

            try:
                page.goto(canonical_url, wait_until="domcontentloaded", timeout=Timeouts.NAVIGATION)
            except Exception as exc:
                context.close()
                browser.close()
                raise CommentScrapingError(f"Navigation failed: {exc}")

            if "/login" in page.url:
                context.close()
                browser.close()
                raise LoginRequiredError(
                    "Not logged in - redirected to Douyin login page. "
                    "Run 'scraper douyin login' or 'scraper douyin import-cookies'."
                )

            # Wait for initial batch of comments to load
            page.wait_for_timeout(Timeouts.COMMENT_LOAD)

            # Check for CAPTCHA after initial load
            handle_captcha(page, headless=self.headless)

            # Try to extract video metadata from page DOM
            try:
                desc = page.evaluate(
                    "() => {"
                    "  const el = document.querySelector('[class*=\"video-title\"], [class*=\"videoDesc\"], [class*=\"desc\"]');"
                    "  return el ? el.textContent.trim().slice(0, 200) : null;"
                    "}"
                )
                author_name = page.evaluate(
                    "() => {"
                    "  const el = document.querySelector('[class*=\"authorName\"], [class*=\"author-name\"], [class*=\"nickname\"]');"
                    "  return el ? el.textContent.trim().slice(0, 50) : null;"
                    "}"
                )
            except Exception:
                pass

            # Scroll to load more comments up to the requested limit
            max_scrolls = max(2, (limit // 10) + 3)
            for _ in range(max_scrolls):
                if len(comments) >= limit:
                    break
                try:
                    page.evaluate(_SCROLL_JS)
                except Exception:
                    pass
                page.wait_for_timeout(Timeouts.SCROLL_WAIT)
                # Check for CAPTCHA during scrolling
                handle_captcha(page, headless=self.headless)

            # If with_replies: click all visible "expand replies" buttons
            if with_replies and comments:
                try:
                    page.evaluate(_EXPAND_REPLIES_JS)
                    page.wait_for_timeout(Timeouts.SCROLL_WAIT)
                except Exception:
                    pass

            context.close()
            browser.close()

        # Trim to requested limit
        result_comments = comments[:limit]

        # Attach replies
        if with_replies:
            for c in result_comments:
                if c.cid and c.cid in reply_batches:
                    c.replies = reply_batches[c.cid][:reply_limit]

        return DouyinFetchResponse(
            url=canonical_url,
            aweme_id=aweme_id,
            desc=desc,
            author_name=author_name,
            total_comments=total_comments,
            comments=result_comments,
            fetched_count=len(result_comments),
            pages_fetched=pages_fetched,
        )
