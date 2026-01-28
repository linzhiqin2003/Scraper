"""Note detail page scraper for Xiaohongshu."""

import re
from datetime import datetime, timedelta
from typing import Optional, List, Tuple

from playwright.async_api import Page
from rich.console import Console

from ....core.browser import random_delay
from ..config import EXPLORE_URL, Selectors
from ..models import Author, Note
from .base import XHSBaseScraper

console = Console()


class NoteScraper(XHSBaseScraper):
    """Scraper for Xiaohongshu note detail pages."""

    async def scrape(
        self,
        note_id: str,
        xsec_token: str = "",
        keep_page: bool = False,
        silent: bool = False,
    ) -> Tuple[Optional[Note], Optional[Page]]:
        """Scrape note detail page.

        Args:
            note_id: Note ID.
            xsec_token: Security token (required for access).
            keep_page: If True, return the page object for reuse.
            silent: If True, suppress console output.

        Returns:
            Tuple of (Note object or None, Page object or None if keep_page=False).
        """
        page = await self.browser.new_page()

        try:
            url = f"{EXPLORE_URL}/{note_id}"
            if xsec_token:
                url = f"{url}?xsec_token={xsec_token}&xsec_source="

            if not silent:
                console.print(f"[blue]Scraping note: {note_id}[/blue]")
            await page.goto(url, wait_until="commit", timeout=60000)
            await random_delay(2.0, 3.0)

            await self._close_login_modal(page)

            login_detected, new_page = await self._check_and_wait_for_captcha(page, silent=silent)
            if login_detected and new_page:
                page = new_page
                await random_delay(2.0, 3.0)

            error_msg = await page.query_selector(Selectors.NOTE_ERROR)
            if error_msg:
                if not silent:
                    console.print("[yellow]Note is not accessible. Try getting xsec_token from explore page.[/yellow]")
                if not keep_page:
                    await page.close()
                return None, None

            note = await self._extract_note_details(page, note_id)

            if not silent:
                if note:
                    title_preview = note.title[:30] + "..." if len(note.title) > 30 else note.title
                    console.print(f"[green]Successfully scraped note: {title_preview}[/green]")
                else:
                    console.print("[yellow]Failed to extract note details[/yellow]")

            if keep_page:
                return note, page
            else:
                await page.close()
                return note, None

        except Exception as e:
            if not silent:
                console.print(f"[red]Error scraping note: {e}[/red]")
            if not keep_page:
                await page.close()
            return None, None

    async def _extract_note_details(self, page: Page, note_id: str) -> Optional[Note]:
        """Extract note details from the page."""
        try:
            await self._wait_for_element(page, '.note-content, #detail-title', timeout=10000)

            title = ""
            title_el = await page.query_selector(Selectors.NOTE_TITLE_DETAIL)
            if title_el:
                title = await title_el.text_content() or ""
            title = title.strip()

            content = ""
            content_el = await page.query_selector(Selectors.NOTE_CONTENT)
            if content_el:
                content = await content_el.text_content() or ""
            content = content.strip()

            images: List[str] = []
            img_elements = await page.query_selector_all(Selectors.NOTE_IMAGES)
            for img in img_elements:
                src = await img.get_attribute("src")
                if src and "http" in src:
                    images.append(src)

            if not images:
                main_img = await page.query_selector('[class*="cover"] img, [class*="main"] img')
                if main_img:
                    src = await main_img.get_attribute("src")
                    if src:
                        images.append(src)

            video_url = None
            video_el = await page.query_selector(Selectors.NOTE_VIDEO)
            if video_el:
                video_url = await video_el.get_attribute("src")

            tags: List[str] = []
            tag_elements = await page.query_selector_all(Selectors.NOTE_TAGS)
            for tag_el in tag_elements:
                tag_text = await tag_el.text_content()
                if tag_text:
                    tag_text = tag_text.strip().replace("#", "")
                    if tag_text and tag_text not in tags:
                        tags.append(tag_text)

            publish_time = None
            time_el = await page.query_selector(Selectors.NOTE_TIME)
            if time_el:
                time_text = await time_el.text_content() or ""
                publish_time = self._parse_time(time_text)

            author = await self._extract_author(page)

            likes = await self._extract_stat(page, "like", "赞")
            comments_count = await self._extract_stat(page, "comment", "评论")
            collects = await self._extract_stat(page, "collect", "收藏")
            shares = await self._extract_stat(page, "share", "分享")

            return Note(
                note_id=note_id,
                title=title,
                content=content,
                images=images,
                video_url=video_url,
                tags=tags,
                publish_time=publish_time,
                author=author,
                likes=likes,
                comments_count=comments_count,
                collects=collects,
                shares=shares,
            )

        except Exception as e:
            console.print(f"[red]Error extracting note details: {e}[/red]")
            return None

    async def _extract_author(self, page: Page) -> Author:
        """Extract author information from the page."""
        try:
            author_container = await page.query_selector(Selectors.AUTHOR_CONTAINER)
            if not author_container:
                return Author(user_id="", nickname="", avatar="")

            author_link = await author_container.query_selector(Selectors.AUTHOR_LINK)
            if not author_link:
                return Author(user_id="", nickname="", avatar="")

            href = await author_link.get_attribute("href")
            user_id = await self._extract_user_id(href or "")

            nickname = ""
            nickname_el = await author_container.query_selector('.name, .username')
            if nickname_el:
                nickname = await nickname_el.text_content() or ""

            avatar = ""
            avatar_el = await author_container.query_selector('img.avatar-item, .avatar img, img')
            if avatar_el:
                avatar = await avatar_el.get_attribute("src") or ""

            return Author(
                user_id=user_id,
                nickname=nickname.strip(),
                avatar=avatar,
            )

        except Exception:
            return Author(user_id="", nickname="", avatar="")

    async def _extract_stat(self, page: Page, stat_class: str, stat_text: str) -> int:
        """Extract engagement stat from the page."""
        try:
            el = await page.query_selector(f'[class*="{stat_class}"] [class*="count"], [class*="{stat_class}"] span')
            if el:
                text = await el.text_content() or "0"
                return self._parse_count(text)

            el = await page.query_selector(f'[class*="count"]:has-text("{stat_text}")')
            if el:
                text = await el.text_content() or "0"
                return self._parse_count(text)

            return 0

        except Exception:
            return 0

    def _parse_time(self, text: str) -> Optional[datetime]:
        """Parse time from various formats."""
        text = text.strip()

        patterns = [
            r"(\d{4})-(\d{2})-(\d{2})",
            r"(\d{4})年(\d{1,2})月(\d{1,2})日",
            r"(\d{1,2})-(\d{1,2})",
            r"(\d{1,2})月(\d{1,2})日",
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                groups = match.groups()
                try:
                    if len(groups) == 3:
                        year, month, day = int(groups[0]), int(groups[1]), int(groups[2])
                        if year < 100:
                            year += 2000
                        return datetime(year, month, day)
                    elif len(groups) == 2:
                        month, day = int(groups[0]), int(groups[1])
                        year = datetime.now().year
                        return datetime(year, month, day)
                except Exception:
                    continue

        if "刚刚" in text or "秒前" in text:
            return datetime.now()
        elif "分钟前" in text:
            match = re.search(r"(\d+)分钟前", text)
            if match:
                minutes = int(match.group(1))
                return datetime.now() - timedelta(minutes=minutes)
        elif "小时前" in text:
            match = re.search(r"(\d+)小时前", text)
            if match:
                hours = int(match.group(1))
                return datetime.now() - timedelta(hours=hours)
        elif "天前" in text:
            match = re.search(r"(\d+)天前", text)
            if match:
                days = int(match.group(1))
                return datetime.now() - timedelta(days=days)

        return None
