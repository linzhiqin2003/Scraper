"""Note detail page scraper for Xiaohongshu."""

import re
from datetime import datetime, timedelta
from typing import Optional, List, Tuple

from patchright.async_api import Page
from rich.console import Console

from ....core.browser import random_delay
from ..config import EXPLORE_URL, Selectors
from ..models import Author, Comment, Note
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
        fetch_comments: bool = False,
        max_comments: int = 50,
    ) -> Tuple[Optional[Note], Optional[Page]]:
        """Scrape note detail page.

        Args:
            note_id: Note ID.
            xsec_token: Security token (required for access).
            keep_page: If True, return the page object for reuse.
            silent: If True, suppress console output.
            fetch_comments: If True, also fetch comments.
            max_comments: Maximum number of comments to fetch.

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

            note = await self._extract_note_details(
                page, note_id, fetch_comments=fetch_comments, max_comments=max_comments
            )

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

    async def _extract_note_details(
        self,
        page: Page,
        note_id: str,
        fetch_comments: bool = False,
        max_comments: int = 50,
    ) -> Optional[Note]:
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

            # Fetch comments if requested
            comments: List[Comment] = []
            if fetch_comments:
                comments = await self._extract_comments(page, max_comments)

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
                comments=comments,
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

    async def _extract_comments(self, page: Page, max_comments: int = 50) -> List[Comment]:
        """Extract comments from the note page.

        Args:
            page: Playwright Page object.
            max_comments: Maximum number of comments to extract.

        Returns:
            List of Comment objects.
        """
        comments: List[Comment] = []

        try:
            # Scroll to comments section to trigger loading
            comments_section = await page.query_selector(Selectors.COMMENTS_CONTAINER)
            if comments_section:
                await comments_section.scroll_into_view_if_needed()
                await random_delay(1.0, 2.0)

            # Try to expand/load more comments
            for _ in range(5):  # Try up to 5 times to load more comments
                expand_btn = await page.query_selector(Selectors.COMMENTS_TOGGLE)
                if expand_btn:
                    try:
                        await expand_btn.click()
                        await random_delay(1.0, 1.5)
                    except Exception:
                        break
                else:
                    break

                # Check if we have enough comments
                comment_items = await page.query_selector_all(Selectors.COMMENT_ITEM)
                if len(comment_items) >= max_comments:
                    break

            # Extract comment items
            comment_items = await page.query_selector_all(Selectors.COMMENT_ITEM)

            for i, item in enumerate(comment_items[:max_comments]):
                try:
                    comment = await self._extract_single_comment(item)
                    if comment:
                        comments.append(comment)
                except Exception:
                    continue

        except Exception as e:
            console.print(f"[dim]Warning: Error extracting comments: {e}[/dim]")

        return comments

    async def _extract_single_comment(self, element) -> Optional[Comment]:
        """Extract a single comment from an element.

        Args:
            element: Playwright ElementHandle for the comment item.

        Returns:
            Comment object or None.
        """
        try:
            # Extract comment ID from element attributes or generate one
            comment_id = await element.get_attribute("data-id") or ""
            if not comment_id:
                comment_id = await element.get_attribute("id") or ""
            if not comment_id:
                # Generate a simple hash from content
                content_el = await element.query_selector(Selectors.COMMENT_CONTENT)
                if content_el:
                    content_text = await content_el.text_content() or ""
                    comment_id = str(hash(content_text))[:12]

            # Extract content
            content = ""
            content_el = await element.query_selector(Selectors.COMMENT_CONTENT)
            if content_el:
                content = await content_el.text_content() or ""
            content = content.strip()

            if not content:
                return None

            # Extract author info
            author_name = ""
            author_id = ""
            author_avatar = ""

            name_el = await element.query_selector(Selectors.COMMENT_AUTHOR_NAME)
            if name_el:
                author_name = await name_el.text_content() or ""
                author_name = author_name.strip()

            link_el = await element.query_selector(Selectors.COMMENT_AUTHOR_LINK)
            if link_el:
                href = await link_el.get_attribute("href") or ""
                author_id = await self._extract_user_id(href)

            avatar_el = await element.query_selector(Selectors.COMMENT_AUTHOR_AVATAR)
            if avatar_el:
                author_avatar = await avatar_el.get_attribute("src") or ""

            author = Author(
                user_id=author_id,
                nickname=author_name,
                avatar=author_avatar,
            )

            # Extract likes
            likes = 0
            likes_el = await element.query_selector(Selectors.COMMENT_LIKES)
            if likes_el:
                likes_text = await likes_el.text_content() or "0"
                likes = self._parse_count(likes_text)

            # Extract time
            create_time = None
            time_el = await element.query_selector(Selectors.COMMENT_TIME)
            if time_el:
                time_text = await time_el.text_content() or ""
                create_time = self._parse_time(time_text)

            # Extract sub-comments (replies)
            sub_comments: List[Comment] = []
            sub_container = await element.query_selector(Selectors.SUB_COMMENT_CONTAINER)
            if sub_container:
                # Try to expand sub-comments
                show_more = await sub_container.query_selector(Selectors.SUB_COMMENT_SHOW_MORE)
                if show_more:
                    try:
                        await show_more.click()
                        await random_delay(0.5, 1.0)
                    except Exception:
                        pass

                sub_items = await sub_container.query_selector_all(Selectors.COMMENT_ITEM)
                for sub_item in sub_items[:10]:  # Limit sub-comments to 10
                    try:
                        sub_comment = await self._extract_single_comment(sub_item)
                        if sub_comment:
                            sub_comments.append(sub_comment)
                    except Exception:
                        continue

            return Comment(
                comment_id=comment_id,
                content=content,
                author=author,
                likes=likes,
                create_time=create_time,
                sub_comments=sub_comments,
            )

        except Exception:
            return None
