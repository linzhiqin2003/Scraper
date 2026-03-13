"""API-based scraper for Xiaohongshu.

Uses Playwright as a signing oracle:
- Note detail: extracted from SSR __INITIAL_STATE__ (no API signing needed)
- Comments: fetched via /api/sns/web/v2/comment/page through browser's network stack
- Images: direct CDN download (no auth needed)

This is significantly faster and more reliable than DOM parsing.
"""

import json
import re
from datetime import datetime
from typing import Optional, List, Tuple

from patchright.async_api import Page
from rich.console import Console

from ....core.browser import random_delay
from ..config import EXPLORE_URL, SEARCH_API_URL, SEARCH_URL
from ..models import Author, Comment, Note, NoteCard, SearchResult
from .base import XHSBaseScraper

console = Console()


class XHSApiScraper(XHSBaseScraper):
    """API-based scraper that extracts data from SSR state and browser API calls."""

    async def scrape(self, *args, **kwargs):
        """Delegate to fetch_note."""
        return await self.fetch_note(*args, **kwargs)

    @staticmethod
    def parse_note_url(url: str) -> Tuple[str, str]:
        """Parse note_id and xsec_token from a XHS URL.

        Supports formats:
        - https://www.xiaohongshu.com/explore/{note_id}?xsec_token=...
        - https://www.xiaohongshu.com/discovery/item/{note_id}?...
        - https://xhslink.com/xxx (short link)
        - Just a note_id string

        Returns:
            (note_id, xsec_token)
        """
        note_id = ""
        xsec_token = ""

        # Extract note_id
        patterns = [
            r'/explore/([a-zA-Z0-9]+)',
            r'/discovery/item/([a-zA-Z0-9]+)',
            r'/note/([a-zA-Z0-9]+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                note_id = match.group(1)
                break

        if not note_id:
            # Assume the URL is just a note_id
            clean = url.strip().split('?')[0].split('/')[-1]
            if re.match(r'^[a-zA-Z0-9]+$', clean):
                note_id = clean

        # Extract xsec_token
        token_match = re.search(r'xsec_token=([^&]+)', url)
        if token_match:
            xsec_token = token_match.group(1)

        return note_id, xsec_token

    async def _warm_up_session(self, page: Page, silent: bool = False) -> bool:
        """Navigate to explore page to establish session and pass any CAPTCHA.

        Returns True if the session is ready.
        """
        try:
            if not silent:
                console.print("[dim]Warming up session...[/dim]")
            await page.goto(
                EXPLORE_URL, wait_until="commit", timeout=60000
            )
            # Wait for page to settle (CAPTCHA auto-solve, redirects, etc.)
            await random_delay(3.0, 5.0)

            # Check if we landed on the explore page
            if "/explore" in page.url and "/404" not in page.url:
                await self._close_login_modal(page)
                return True

            # Might be stuck on CAPTCHA — wait longer
            if not silent:
                console.print("[yellow]Waiting for CAPTCHA resolution...[/yellow]")
            await random_delay(10.0, 15.0)
            return "/explore" in page.url and "/404" not in page.url

        except Exception as e:
            if not silent:
                console.print(f"[dim]Session warm-up error: {e}[/dim]")
            return False

    async def fetch_note(
        self,
        url: str,
        fetch_comments: bool = True,
        max_comments: int = 50,
        silent: bool = False,
        page: Optional[Page] = None,
    ) -> Optional[Note]:
        """Fetch a note by URL using API extraction.

        Args:
            url: Xiaohongshu note URL or note ID.
            fetch_comments: Whether to fetch comments.
            max_comments: Maximum comments to fetch.
            silent: Suppress console output.
            page: Reuse an existing page (for batch fetching).

        Returns:
            Note object or None on failure.
        """
        note_id, xsec_token = self.parse_note_url(url)
        if not note_id:
            if not silent:
                console.print(f"[red]Cannot parse note ID from URL: {url}[/red]")
            return None

        own_page = page is None
        if own_page:
            page = await self.browser.new_page()

        try:
            page_url = f"{EXPLORE_URL}/{note_id}"
            if xsec_token:
                page_url += f"?xsec_token={xsec_token}&xsec_source="

            if not silent:
                console.print(f"[blue]Fetching note: {note_id}[/blue]")

            # Navigate to note page
            try:
                await page.goto(page_url, wait_until="domcontentloaded", timeout=30000)
            except Exception:
                # Timeout is ok — page might be slow
                pass

            await random_delay(1.0, 2.0)

            # Check if redirected (CAPTCHA or 404)
            current_url = page.url
            if "/404" in current_url or (f"/explore/{note_id}" not in current_url and note_id not in current_url):
                if not silent:
                    console.print("[dim]Redirected, warming up session...[/dim]")

                # Warm up session first
                if not await self._warm_up_session(page, silent):
                    if not silent:
                        console.print("[yellow]Session warm-up failed[/yellow]")
                    if own_page:
                        await page.close()
                    return None

                # Retry navigation to note page
                try:
                    await page.goto(page_url, wait_until="domcontentloaded", timeout=30000)
                except Exception:
                    pass
                await random_delay(1.0, 2.0)

                # Still redirected?
                if f"/explore/{note_id}" not in page.url and note_id not in page.url:
                    if not silent:
                        console.print(f"[yellow]Cannot access note {note_id}, token may be expired[/yellow]")
                    if own_page:
                        await page.close()
                    return None

            await self._close_login_modal(page)

            # Extract note from SSR state
            note = await self._extract_from_ssr(page, note_id)
            if not note:
                if not silent:
                    console.print("[yellow]SSR extraction failed, note may be inaccessible[/yellow]")
                if own_page:
                    await page.close()
                return None

            # Fetch comments via API
            if fetch_comments:
                comments = await self._fetch_comments_api(
                    page, note_id, xsec_token, max_comments
                )
                note.comments = comments
                note.comments_count = max(note.comments_count, len(comments))

            if not silent:
                title_preview = (note.title[:30] + "...") if len(note.title) > 30 else note.title
                console.print(
                    f"[green]Fetched: {title_preview} "
                    f"({len(note.images)} images, {len(note.comments)} comments)[/green]"
                )

            if own_page:
                await page.close()
            return note

        except Exception as e:
            if not silent:
                console.print(f"[red]Error fetching note: {e}[/red]")
            if own_page:
                await page.close()
            return None

    async def _extract_from_ssr(self, page: Page, note_id: str) -> Optional[Note]:
        """Extract note data from __INITIAL_STATE__ SSR data.

        This is much more reliable than DOM parsing because:
        - Data is structured JSON, not HTML dependent on CSS selectors
        - Contains complete info including all image URLs, stats, etc.
        - Doesn't require scrolling or waiting for elements
        """
        try:
            data = await page.evaluate("""(noteId) => {
                // Try window global first, then parse from script tag
                // (XHS deletes window.__INITIAL_STATE__ after initialization)
                let state = window.__INITIAL_STATE__;
                if (!state || !state.note) {
                    const scripts = document.querySelectorAll('script');
                    for (const s of scripts) {
                        const t = s.textContent || '';
                        const idx = t.indexOf('__INITIAL_STATE__=');
                        if (idx === -1) continue;
                        try {
                            const jsonStr = t.substring(idx + '__INITIAL_STATE__='.length)
                                .replace(/undefined/g, 'null');
                            state = JSON.parse(jsonStr);
                            break;
                        } catch(e) { continue; }
                    }
                }
                if (!state || !state.note || !state.note.noteDetailMap) return null;

                const noteData = state.note.noteDetailMap[noteId];
                if (!noteData || !noteData.note) return null;

                const n = noteData.note;
                return {
                    noteId: n.noteId,
                    title: n.title || '',
                    desc: n.desc || '',
                    type: n.type || 'normal',
                    time: n.time,
                    lastUpdateTime: n.lastUpdateTime,
                    ipLocation: n.ipLocation || '',
                    imageList: (n.imageList || []).map(img => ({
                        width: img.width,
                        height: img.height,
                        urlDefault: img.urlDefault || '',
                        urlPre: img.urlPre || '',
                        infoList: (img.infoList || []).map(info => ({
                            imageScene: info.imageScene,
                            url: info.url,
                        })),
                    })),
                    video: n.video ? {
                        url: n.video.media?.stream?.h264?.[0]?.masterUrl || '',
                        duration: n.video.duration || 0,
                        image: n.video.image || {},
                    } : null,
                    tagList: (n.tagList || []).map(t => ({ id: t.id, name: t.name, type: t.type })),
                    atUserList: n.atUserList || [],
                    user: n.user ? {
                        userId: n.user.userId || '',
                        nickname: n.user.nickname || '',
                        avatar: n.user.avatar || '',
                    } : null,
                    interactInfo: n.interactInfo ? {
                        likedCount: n.interactInfo.likedCount || '0',
                        collectedCount: n.interactInfo.collectedCount || '0',
                        commentCount: n.interactInfo.commentCount || '0',
                        shareCount: n.interactInfo.shareCount || '0',
                        liked: n.interactInfo.liked || false,
                        collected: n.interactInfo.collected || false,
                    } : null,
                    shareInfo: n.shareInfo || {},
                };
            }""", note_id)

            if not data:
                return None

            # Build image URL list
            images = []
            for img in data.get("imageList", []):
                # Prefer high-quality default URL
                url = img.get("urlDefault", "")
                if not url:
                    for info in img.get("infoList", []):
                        if info.get("imageScene") == "WB_DFT":
                            url = info["url"]
                            break
                if not url:
                    for info in img.get("infoList", []):
                        url = info.get("url", "")
                        if url:
                            break
                if url:
                    images.append(url)

            # Extract video URL
            video_url = None
            if data.get("video"):
                video_url = data["video"].get("url")

            # Parse stats
            interact = data.get("interactInfo") or {}
            likes = self._parse_count(str(interact.get("likedCount", "0")))
            collects = self._parse_count(str(interact.get("collectedCount", "0")))
            comments_count = self._parse_count(str(interact.get("commentCount", "0")))
            shares = self._parse_count(str(interact.get("shareCount", "0")))

            # Parse time
            publish_time = None
            ts = data.get("time")
            if ts:
                try:
                    publish_time = datetime.fromtimestamp(ts / 1000)
                except (ValueError, OSError):
                    pass

            # Build author
            user = data.get("user") or {}
            author = Author(
                user_id=user.get("userId", ""),
                nickname=user.get("nickname", ""),
                avatar=user.get("avatar", ""),
            )

            # Tags
            tags = [t["name"] for t in data.get("tagList", []) if t.get("name")]

            return Note(
                note_id=data.get("noteId", note_id),
                title=data.get("title", ""),
                content=data.get("desc", ""),
                images=images,
                video_url=video_url,
                tags=tags,
                publish_time=publish_time,
                author=author,
                likes=likes,
                comments_count=comments_count,
                collects=collects,
                shares=shares,
                ip_location=data.get("ipLocation", ""),
                note_type=data.get("type", "normal"),
            )

        except Exception as e:
            console.print(f"[dim]SSR extraction error: {e}[/dim]")
            return None

    async def _fetch_comments_api(
        self,
        page: Page,
        note_id: str,
        xsec_token: str,
        max_comments: int = 50,
    ) -> List[Comment]:
        """Fetch comments via the API through the browser's network stack.

        The browser's service worker handles signing automatically.
        """
        all_comments = []
        cursor = ""

        while len(all_comments) < max_comments:
            try:
                result = await page.evaluate("""async ({noteId, xsecToken, cursor}) => {
                    const params = new URLSearchParams({
                        note_id: noteId,
                        cursor: cursor,
                        top_comment_id: '',
                        image_formats: 'jpg,webp,avif',
                        xsec_token: xsecToken,
                    });
                    const url = `https://edith.xiaohongshu.com/api/sns/web/v2/comment/page?${params}`;

                    const resp = await fetch(url, {
                        method: 'GET',
                        credentials: 'include',
                        headers: {
                            'Accept': 'application/json, text/plain, */*',
                            'Origin': 'https://www.xiaohongshu.com',
                            'Referer': 'https://www.xiaohongshu.com/',
                        },
                    });

                    const data = await resp.json();
                    if (!data.data) return { comments: [], hasMore: false, cursor: '' };

                    return {
                        comments: (data.data.comments || []).map(c => ({
                            id: c.id,
                            content: c.content,
                            likeCount: c.like_count || '0',
                            createTime: c.create_time,
                            ipLocation: c.ip_location || '',
                            user: c.user_info ? {
                                userId: c.user_info.user_id,
                                nickname: c.user_info.nickname,
                                avatar: c.user_info.image,
                            } : null,
                            subCommentCount: parseInt(c.sub_comment_count || '0'),
                            subComments: (c.sub_comments || []).map(sc => ({
                                id: sc.id,
                                content: sc.content,
                                likeCount: sc.like_count || '0',
                                createTime: sc.create_time,
                                ipLocation: sc.ip_location || '',
                                user: sc.user_info ? {
                                    userId: sc.user_info.user_id,
                                    nickname: sc.user_info.nickname,
                                    avatar: sc.user_info.image,
                                } : null,
                            })),
                        })),
                        hasMore: data.data.has_more || false,
                        cursor: data.data.cursor || '',
                    };
                }""", {"noteId": note_id, "xsecToken": xsec_token, "cursor": cursor})

                if not result or not result.get("comments"):
                    break

                for c in result["comments"]:
                    comment = self._build_comment(c)
                    if comment:
                        all_comments.append(comment)

                if not result.get("hasMore"):
                    break

                cursor = result.get("cursor", "")
                if not cursor:
                    break

                await random_delay(0.5, 1.0)

            except Exception as e:
                console.print(f"[dim]Comment fetch error: {e}[/dim]")
                break

        return all_comments[:max_comments]

    async def search_notes(
        self,
        keyword: str,
        limit: int = 20,
        sort: str = "general",
        note_type: int = 0,
    ) -> SearchResult:
        """Search notes via response interception.

        Navigates to search page and intercepts API responses. The browser's
        JS SDK handles request signing (x-s, x-t, x-s-common) automatically.
        Pagination is triggered by scrolling the page.

        Args:
            keyword: Search keyword.
            limit: Maximum number of results.
            sort: Sort order (general, time_descending, popularity_descending,
                  comment_descending, collect_descending).
            note_type: Note type filter (0=all, 1=video, 2=image).

        Returns:
            SearchResult with note cards.
        """
        from urllib.parse import quote

        page = await self.browser.new_page()
        notes: list[NoteCard] = []
        seen_ids: set[str] = set()
        api_results: list[dict] = []

        async def on_response(response):
            if '/api/sns/web/v1/search/notes' not in response.url:
                return
            if response.status != 200:
                return
            try:
                body = await response.json()
                if body.get("code") == 0 and body.get("data", {}).get("items"):
                    api_results.append(body["data"])
            except Exception:
                pass

        page.on("response", on_response)

        try:
            # Intercept search API requests to inject sort/note_type
            if sort != "general" or note_type > 0:
                async def modify_search_request(route):
                    request = route.request
                    if request.method == "POST" and request.post_data:
                        try:
                            body = json.loads(request.post_data)
                            if sort != "general":
                                body["sort"] = sort
                            if note_type > 0:
                                body["note_type"] = note_type
                            await route.continue_(
                                post_data=json.dumps(body),
                            )
                            return
                        except (json.JSONDecodeError, TypeError):
                            pass
                    await route.continue_()

                await page.route("**/api/sns/web/v1/search/notes", modify_search_request)

            search_url = f"{SEARCH_URL}?keyword={quote(keyword)}&source=web_search_result_notes"
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            await random_delay(3.0, 4.0)

            await self._close_login_modal(page)

            # Process initial results
            self._extract_notes_from_api(api_results, notes, seen_ids)

            # Scroll to load more pages
            max_scrolls = (limit + 19) // 20 + 2  # extra buffer
            scroll_count = 0
            no_new_count = 0

            while len(notes) < limit and scroll_count < max_scrolls:
                prev_count = len(notes)
                api_results.clear()

                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await random_delay(1.5, 2.5)

                self._extract_notes_from_api(api_results, notes, seen_ids)
                scroll_count += 1

                if len(notes) == prev_count:
                    no_new_count += 1
                    if no_new_count >= 3:
                        break  # No more results
                else:
                    no_new_count = 0

        finally:
            await page.close()

        return SearchResult(
            keyword=keyword,
            total=len(notes),
            notes=notes[:limit],
        )

    def _extract_notes_from_api(
        self,
        api_results: list[dict],
        notes: list[NoteCard],
        seen_ids: set[str],
    ) -> None:
        """Extract NoteCard objects from intercepted API responses."""
        for data in api_results:
            for item in data.get("items", []):
                note_id = item.get("id", "")
                if not note_id or note_id in seen_ids:
                    continue
                seen_ids.add(note_id)

                card = item.get("note_card")
                if not card:
                    continue

                user = card.get("user") or {}
                interact = card.get("interact_info") or {}

                notes.append(NoteCard(
                    note_id=note_id,
                    title=card.get("display_title", ""),
                    cover_url=(card.get("cover") or {}).get("url_default", ""),
                    author=Author(
                        user_id=user.get("user_id", ""),
                        nickname=user.get("nickname") or user.get("nick_name", ""),
                        avatar=user.get("avatar", ""),
                    ),
                    likes=self._parse_count(interact.get("liked_count", "0")),
                    xsec_token=item.get("xsec_token", ""),
                    note_type=card.get("type", "normal"),
                ))

    def _build_comment(self, data: dict) -> Optional[Comment]:
        """Build a Comment object from API response data."""
        if not data or not data.get("content"):
            return None

        user = data.get("user") or {}
        author = Author(
            user_id=user.get("userId", ""),
            nickname=user.get("nickname", ""),
            avatar=user.get("avatar", ""),
        )

        create_time = None
        ts = data.get("createTime")
        if ts:
            try:
                create_time = datetime.fromtimestamp(ts / 1000)
            except (ValueError, OSError):
                pass

        # Build sub-comments
        sub_comments = []
        for sc in data.get("subComments", []):
            sub = self._build_comment(sc)
            if sub:
                sub_comments.append(sub)

        return Comment(
            comment_id=data.get("id", ""),
            content=data.get("content", ""),
            author=author,
            likes=self._parse_count(str(data.get("likeCount", "0"))),
            create_time=create_time,
            sub_comments=sub_comments,
            ip_location=data.get("ipLocation", ""),
        )
