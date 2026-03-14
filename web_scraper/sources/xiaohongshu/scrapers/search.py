"""Search scraper for Xiaohongshu.

Uses response interception to capture search API results directly,
avoiding DOM parsing race conditions (navigation destroying context).
"""

import asyncio
import json
from typing import Optional, List
from urllib.parse import quote

from patchright.async_api import Page, Response
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from ....core.browser import random_delay
from ..config import SEARCH_URL, SEARCH_TYPES, Config, Selectors
from ..models import Author, NoteCard, SearchResult
from .base import XHSBaseScraper

console = Console()

# Search API note_type mapping (from API exploration)
API_NOTE_TYPE = {
    "all": 0,
    "notes": 0,
    "video": 1,
    "image": 2,
}


class SearchScraper(XHSBaseScraper):
    """Scraper for Xiaohongshu search results using API interception."""

    async def scrape(
        self,
        keyword: str,
        search_type: str = "all",
        limit: int = 20,
    ) -> SearchResult:
        """Scrape search results for a keyword.

        Primary: intercept search/notes API response (fast, reliable).
        Fallback: DOM parsing (legacy, for edge cases).

        Args:
            keyword: Search keyword.
            search_type: Type of search (all, notes, video, image, user).
            limit: Maximum number of results to collect.

        Returns:
            SearchResult containing note cards.
        """
        page = await self.browser.new_page()

        try:
            console.print(f"[blue]Searching for: {keyword} (type: {search_type})[/blue]")
            notes = await self._search_via_api(page, keyword, search_type, limit)

            if not notes:
                console.print("[dim]API interception returned no results, trying DOM fallback...[/dim]")
                notes = await self._search_via_dom(page, keyword, search_type, limit)

            console.print(f"[green]Found {len(notes)} results for '{keyword}'[/green]")
            return SearchResult(keyword=keyword, total=len(notes), notes=notes)

        finally:
            await page.close()

    # ── API interception approach ──────────────────────────────────────

    async def _search_via_api(
        self, page: Page, keyword: str, search_type: str, limit: int
    ) -> List[NoteCard]:
        """Search by intercepting the search/notes API response."""
        captured: List[dict] = []
        capture_done = asyncio.Event()

        async def on_response(response: Response) -> None:
            if "api/sns/web/v1/search/notes" not in response.url:
                return
            if response.request.method != "POST":
                return
            try:
                body = await response.json()
                if body.get("success") and body.get("data", {}).get("items"):
                    captured.append(body["data"])
                    capture_done.set()
            except Exception:
                pass

        page.on("response", on_response)

        # Navigate to search page — the page's JS will make the API call
        # with proper signing headers automatically
        type_param = SEARCH_TYPES.get(search_type, "51")
        encoded_keyword = quote(keyword)
        url = f"{SEARCH_URL}?keyword={encoded_keyword}&source=web_search_result_notes&type={type_param}"

        try:
            await page.goto(url, wait_until="commit", timeout=60000)
        except Exception:
            pass  # Timeout is ok — we just need the API call to fire

        # Wait for first API response (or timeout)
        try:
            await asyncio.wait_for(capture_done.wait(), timeout=15)
        except asyncio.TimeoutError:
            page.remove_listener("response", on_response)
            return []

        # Accept cookie banner to unblock further interactions
        await self._dismiss_cookie_banner(page)

        # Collect initial results
        all_notes = []
        seen_ids: set = set()

        for data in captured:
            notes = self._parse_api_items(data.get("items", []))
            for note in notes:
                if note.note_id not in seen_ids:
                    all_notes.append(note)
                    seen_ids.add(note.note_id)

        # If we need more results, scroll to trigger pagination
        if len(all_notes) < limit:
            has_more = captured[-1].get("has_more", False) if captured else False
            page_num = len(captured) + 1  # Already got page 1 (and maybe 2)

            while has_more and len(all_notes) < limit:
                capture_done.clear()
                captured.clear()

                # Scroll to trigger next page load
                await self._scroll_page(page)
                await random_delay(1.0, 2.0)

                try:
                    await asyncio.wait_for(capture_done.wait(), timeout=10)
                except asyncio.TimeoutError:
                    break

                for data in captured:
                    notes = self._parse_api_items(data.get("items", []))
                    for note in notes:
                        if note.note_id not in seen_ids:
                            all_notes.append(note)
                            seen_ids.add(note.note_id)
                    has_more = data.get("has_more", False)

                page_num += 1

        page.remove_listener("response", on_response)
        return all_notes[:limit]

    def _parse_api_items(self, items: list) -> List[NoteCard]:
        """Parse note cards from search API response items."""
        notes = []
        for item in items:
            try:
                if item.get("model_type") != "note":
                    continue

                card = item.get("note_card", {})
                if not card:
                    continue

                note_id = item.get("id", "")
                xsec_token = item.get("xsec_token", "")
                title = card.get("display_title", "")
                note_type = card.get("type", "normal")

                # Author
                user = card.get("user", {})
                author = Author(
                    user_id=user.get("user_id", user.get("userId", "")),
                    nickname=user.get("nick_name", user.get("nickname", "")),
                    avatar=user.get("avatar", ""),
                )

                # Cover image
                cover = card.get("cover", {})
                cover_url = cover.get("url_default", cover.get("url_pre", ""))

                # Interaction stats
                interact = card.get("interact_info", {})
                likes = self._parse_count(str(interact.get("liked_count", "0")))

                notes.append(NoteCard(
                    note_id=note_id,
                    title=title,
                    cover_url=cover_url,
                    author=author,
                    likes=likes,
                    xsec_token=xsec_token,
                    note_type=note_type,
                ))
            except Exception:
                continue

        return notes

    async def _dismiss_cookie_banner(self, page: Page) -> None:
        """Dismiss the cookie consent banner if present."""
        try:
            await page.evaluate(
                'document.querySelector(".cookie-banner__btn--primary")?.click()'
            )
        except Exception:
            pass

    # ── DOM fallback approach ──────────────────────────────────────────

    async def _search_via_dom(
        self, page: Page, keyword: str, search_type: str, limit: int
    ) -> List[NoteCard]:
        """Fallback: collect results via DOM parsing."""
        # Page should already be on search results from API attempt
        await random_delay(2.0, 3.0)
        await self._close_login_modal(page)

        notes: List[NoteCard] = []
        seen_ids: set = set()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("[cyan]Collecting search results...", total=None)

            scroll_count = 0
            max_scrolls = Config.max_scroll_attempts

            while len(notes) < limit and scroll_count < max_scrolls:
                try:
                    note_items = await page.query_selector_all(Selectors.NOTE_ITEM)
                except Exception:
                    # Navigation destroyed context — bail out
                    break

                for item in note_items:
                    if len(notes) >= limit:
                        break
                    try:
                        note = await self._extract_search_result(item)
                        if note and note.note_id not in seen_ids:
                            notes.append(note)
                            seen_ids.add(note.note_id)
                            progress.update(
                                task,
                                description=f"[cyan]Collected {len(notes)} results...",
                            )
                    except Exception:
                        continue

                if len(notes) >= limit:
                    break

                await self._scroll_page(page)
                scroll_count += 1
                await random_delay(0.5, 1.0)

        return notes

    async def _extract_search_result(self, item) -> Optional[NoteCard]:
        """Extract search result information from a section.note-item element."""
        try:
            card_info = await item.evaluate(r"""item => {
                const noteLink = item.querySelector('a[href*="xsec_token"]');
                if (!noteLink) return null;

                const href = noteLink.getAttribute('href') || '';
                const noteIdMatch = href.match(/(?:explore|search_result)\/([a-zA-Z0-9]+)/);
                const noteId = noteIdMatch ? noteIdMatch[1] : '';
                const tokenMatch = href.match(/xsec_token=([^&]+)/);
                const xsecToken = tokenMatch ? tokenMatch[1] : '';

                const coverImg = item.querySelector('a.cover img, img');
                const coverUrl = coverImg ? coverImg.getAttribute('src') || '' : '';

                const hasVideo = item.querySelector('svg, [class*="video"]') !== null;
                const noteType = hasVideo ? 'video' : 'normal';

                const footer = item.querySelector('.footer');
                if (!footer) return { noteId, xsecToken, coverUrl, noteType, title: '', nickname: '', avatar: '', userId: '', likes: '0' };

                const titleEl = footer.querySelector('a.title, .title');
                const title = titleEl ? titleEl.textContent?.trim() : '';

                const authorContainer = footer.querySelector('.author-wrapper, .card-bottom-wrapper');
                let nickname = '';
                let avatar = '';
                let userId = '';

                if (authorContainer) {
                    const authorLink = authorContainer.querySelector('a[href*="/user/profile/"]');
                    if (authorLink) {
                        const authorHref = authorLink.getAttribute('href') || '';
                        const userIdMatch = authorHref.match(/\/user\/profile\/([^?]+)/);
                        userId = userIdMatch ? userIdMatch[1] : '';
                        const avatarImg = authorLink.querySelector('img');
                        avatar = avatarImg ? avatarImg.getAttribute('src') || '' : '';
                        const nameEl = authorLink.querySelector('.name');
                        nickname = nameEl ? nameEl.textContent?.trim() : '';
                    }
                }

                const likesEl = footer.querySelector('.like-wrapper .count, span.count');
                const likes = likesEl ? likesEl.textContent?.trim() : '0';

                return { noteId, xsecToken, coverUrl, noteType, title, nickname, avatar, userId, likes };
            }""")

            if not card_info or not card_info.get("noteId"):
                return None

            author = Author(
                user_id=card_info.get("userId", ""),
                nickname=card_info.get("nickname", ""),
                avatar=card_info.get("avatar", ""),
            )

            return NoteCard(
                note_id=card_info.get("noteId", ""),
                title=card_info.get("title", ""),
                cover_url=card_info.get("coverUrl", ""),
                author=author,
                likes=self._parse_count(card_info.get("likes", "0")),
                xsec_token=card_info.get("xsecToken", ""),
                note_type=card_info.get("noteType", "normal"),
            )

        except Exception:
            return None
