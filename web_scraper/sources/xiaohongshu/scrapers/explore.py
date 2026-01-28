"""Explore page scraper for Xiaohongshu."""

from typing import Optional, List

from playwright.async_api import Page, ElementHandle
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from ....core.browser import random_delay
from ..config import EXPLORE_URL, CATEGORY_CHANNELS, Config, Selectors
from ..models import Author, NoteCard, ExploreResult
from .base import XHSBaseScraper

console = Console()


class ExploreScraper(XHSBaseScraper):
    """Scraper for Xiaohongshu explore/home page."""

    async def scrape(
        self,
        category: str = "推荐",
        limit: int = 20,
    ) -> ExploreResult:
        """Scrape notes from explore page.

        Args:
            category: Category name (e.g., "推荐", "美食").
            limit: Maximum number of notes to collect.

        Returns:
            ExploreResult containing note cards.
        """
        page = await self.browser.new_page()

        try:
            channel_id = CATEGORY_CHANNELS.get(category, "homefeed_recommend")
            url = f"{EXPLORE_URL}?channel_id={channel_id}"

            console.print(f"[blue]Scraping explore page: {category}[/blue]")
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await random_delay(2.0, 3.0)

            await self._close_login_modal(page)
            await random_delay(1.0, 2.0)

            await page.wait_for_selector(Selectors.NOTE_ITEM, state="attached", timeout=30000)

            if category != "推荐":
                await self._select_category(page, category)

            notes = await self._collect_notes(page, limit)

            console.print(f"[green]Collected {len(notes)} notes from {category}[/green]")

            return ExploreResult(category=category, notes=notes)

        finally:
            await page.close()

    async def _select_category(self, page: Page, category: str) -> None:
        """Select a category tab."""
        try:
            category_selector = f'[cursor=pointer]:has-text("{category}")'
            tab = await page.query_selector(category_selector)
            if tab:
                await tab.click()
                await random_delay(1.0, 2.0)
                console.print(f"[dim]Selected category: {category}[/dim]")
        except Exception as e:
            console.print(f"[yellow]Could not select category {category}: {e}[/yellow]")

    async def _collect_notes(self, page: Page, limit: int) -> List[NoteCard]:
        """Collect note cards from the page."""
        notes: List[NoteCard] = []
        seen_ids: set = set()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("[cyan]Collecting notes...", total=None)

            scroll_count = 0
            max_scrolls = Config.max_scroll_attempts

            while len(notes) < limit and scroll_count < max_scrolls:
                note_items = await page.query_selector_all(Selectors.NOTE_ITEM)

                for item in note_items:
                    if len(notes) >= limit:
                        break

                    try:
                        note = await self._extract_note_from_item(item)
                        if note and note.note_id not in seen_ids:
                            notes.append(note)
                            seen_ids.add(note.note_id)
                            progress.update(task, description=f"[cyan]Collected {len(notes)} notes...")
                    except Exception:
                        continue

                if len(notes) >= limit:
                    break

                await self._scroll_page(page)
                scroll_count += 1
                await random_delay(0.5, 1.0)

        return notes

    async def _extract_note_from_item(self, item: ElementHandle) -> Optional[NoteCard]:
        """Extract note card information from a section.note-item element."""
        try:
            card_info = await item.evaluate(r"""item => {
                const noteLink = item.querySelector('a[href*="/explore/"][href*="xsec_token"]');
                if (!noteLink) return null;

                const href = noteLink.getAttribute('href') || '';
                const noteIdMatch = href.match(/\/explore\/([a-zA-Z0-9]+)/);
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

                const authorWrapper = footer.querySelector('.author-wrapper');
                let nickname = '';
                let avatar = '';
                let userId = '';

                if (authorWrapper) {
                    const authorLink = authorWrapper.querySelector('a[href*="/user/profile/"]');
                    if (authorLink) {
                        const authorHref = authorLink.getAttribute('href') || '';
                        const userIdMatch = authorHref.match(/\/user\/profile\/([^?]+)/);
                        userId = userIdMatch ? userIdMatch[1] : '';
                        const avatarImg = authorLink.querySelector('img');
                        avatar = avatarImg ? avatarImg.getAttribute('src') || '' : '';
                        const nameEl = authorLink.querySelector('span.name');
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
            console.print(f"[dim red]Error extracting note card: {e}[/dim red]")
            return None
