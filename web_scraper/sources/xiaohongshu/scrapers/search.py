"""Search scraper for Xiaohongshu."""

from typing import Optional, List
from urllib.parse import quote

from playwright.async_api import Page, ElementHandle
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from ....core.browser import random_delay
from ..config import SEARCH_URL, SEARCH_TYPES, Config, Selectors
from ..models import Author, NoteCard, SearchResult
from .base import XHSBaseScraper

console = Console()


class SearchScraper(XHSBaseScraper):
    """Scraper for Xiaohongshu search results."""

    async def scrape(
        self,
        keyword: str,
        search_type: str = "all",
        limit: int = 20,
    ) -> SearchResult:
        """Scrape search results for a keyword.

        Args:
            keyword: Search keyword.
            search_type: Type of search (all, notes, video, image, user).
            limit: Maximum number of results to collect.

        Returns:
            SearchResult containing note cards.
        """
        page = await self.browser.new_page()

        try:
            type_param = SEARCH_TYPES.get(search_type, "51")
            encoded_keyword = quote(keyword)
            url = f"{SEARCH_URL}?keyword={encoded_keyword}&source=web_search_result_notes&type={type_param}"

            console.print(f"[blue]Searching for: {keyword} (type: {search_type})[/blue]")
            await page.goto(url, wait_until="commit", timeout=60000)
            await random_delay(2.0, 3.0)

            await self._close_login_modal(page)

            login_required = await self._check_login_required(page)
            if login_required:
                console.print("[yellow]Login required for search. Please run 'scraper xhs login' first.[/yellow]")
                return SearchResult(keyword=keyword, total=0, notes=[])

            if search_type != "all":
                await self._select_search_type(page, search_type)

            notes = await self._collect_results(page, limit)

            console.print(f"[green]Found {len(notes)} results for '{keyword}'[/green]")

            return SearchResult(keyword=keyword, total=len(notes), notes=notes)

        finally:
            await page.close()

    async def _check_login_required(self, page: Page) -> bool:
        """Check if login is required to view search results."""
        try:
            login_prompt = await page.query_selector('text=登录后查看搜索结果')
            return login_prompt is not None
        except Exception:
            return False

    async def _select_search_type(self, page: Page, search_type: str) -> None:
        """Select a search type filter."""
        type_labels = {
            "all": "全部",
            "notes": "全部",
            "video": "视频",
            "image": "图文",
            "user": "用户",
        }

        label = type_labels.get(search_type, "全部")

        try:
            tab = await page.query_selector(f'[cursor=pointer]:has-text("{label}")')
            if tab:
                await tab.click()
                await random_delay(1.0, 2.0)
                console.print(f"[dim]Selected filter: {label}[/dim]")
        except Exception as e:
            console.print(f"[yellow]Could not select filter {label}: {e}[/yellow]")

    async def _collect_results(self, page: Page, limit: int) -> List[NoteCard]:
        """Collect search results from the page."""
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
                note_items = await page.query_selector_all(Selectors.NOTE_ITEM)

                for item in note_items:
                    if len(notes) >= limit:
                        break

                    try:
                        note = await self._extract_search_result(item)
                        if note and note.note_id not in seen_ids:
                            notes.append(note)
                            seen_ids.add(note.note_id)
                            progress.update(task, description=f"[cyan]Collected {len(notes)} results...")
                    except Exception:
                        continue

                if len(notes) >= limit:
                    break

                await self._scroll_page(page)
                scroll_count += 1
                await random_delay(0.5, 1.0)

        return notes

    async def _extract_search_result(self, item: ElementHandle) -> Optional[NoteCard]:
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

        except Exception as e:
            console.print(f"[dim red]Error extracting search result: {e}[/dim red]")
            return None
