"""Base scraper class for Xiaohongshu."""

import asyncio
from abc import ABC, abstractmethod
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

from playwright.async_api import Page
from rich.console import Console

from ....core.browser import BrowserManager, random_delay
from ..config import Config, Selectors

console = Console()


class XHSBaseScraper(ABC):
    """Base class for all Xiaohongshu scrapers."""

    def __init__(self, browser: BrowserManager):
        """Initialize scraper.

        Args:
            browser: BrowserManager instance.
        """
        self.browser = browser
        self.config = Config

    async def _wait_for_element(
        self,
        page: Page,
        selector: str,
        timeout: int = 10000,
        state: str = "visible",
    ) -> bool:
        """Wait for an element to appear."""
        try:
            await page.wait_for_selector(selector, timeout=timeout, state=state)
            return True
        except Exception:
            return False

    async def _scroll_page(self, page: Page, scroll_count: int = 1) -> None:
        """Scroll page down."""
        for _ in range(scroll_count):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(self.config.scroll_delay)

    async def _extract_xsec_token(self, href: str) -> str:
        """Extract xsec_token from URL."""
        try:
            parsed = urlparse(href)
            params = parse_qs(parsed.query)
            return params.get("xsec_token", [""])[0]
        except Exception:
            return ""

    async def _extract_note_id(self, href: str) -> str:
        """Extract note ID from URL."""
        try:
            parsed = urlparse(href)
            path_parts = parsed.path.strip("/").split("/")
            if len(path_parts) >= 2:
                for i, part in enumerate(path_parts):
                    if part in ("explore", "search_result") and i + 1 < len(path_parts):
                        return path_parts[i + 1]
            return ""
        except Exception:
            return ""

    async def _extract_user_id(self, href: str) -> str:
        """Extract user ID from URL."""
        try:
            parsed = urlparse(href)
            path_parts = parsed.path.strip("/").split("/")
            if len(path_parts) >= 3 and path_parts[0] == "user" and path_parts[1] == "profile":
                return path_parts[2]
            return ""
        except Exception:
            return ""

    async def _close_login_modal(self, page: Page) -> None:
        """Try to close login modal if it appears."""
        try:
            close_btn = await page.query_selector('[aria-label="关闭"]')
            if close_btn:
                await close_btn.click()
                await random_delay(0.3, 0.5)
                return

            modal_mask = await page.query_selector('[aria-label="弹窗遮罩"]')
            if modal_mask:
                await modal_mask.click()
                await random_delay(0.3, 0.5)
        except Exception:
            pass

    async def _check_and_wait_for_captcha(
        self, page: Page, silent: bool = False
    ) -> tuple[bool, Optional[Page]]:
        """Check for security captcha/rate limit/login and wait for user to handle it."""
        current_url = page.url

        # Check for login required
        login_selectors = [
            'text=登录继续查看该笔记',
            'text=马上登录即可',
            'text=登录后查看更多',
            'text=刷到更懂你的优质内容',
            'text=登录小红书',
            'text=扫码登录',
            'button:has-text("登录")',
        ]

        for selector in login_selectors:
            try:
                login_prompt = await page.query_selector(selector)
                if login_prompt:
                    if not silent:
                        console.print(
                            "\n[bold red]Login required! (Cookies expired)[/bold red]\n"
                            "[yellow]Please run:[/yellow] scraper xhs login --qrcode"
                        )
                    return True, page
            except Exception:
                pass

        # Check for rate limit
        rate_limit_selectors = [
            'text=安全限制',
            'text=访问频次异常',
            'text=请勿频繁操作',
        ]

        for selector in rate_limit_selectors:
            try:
                rate_limit = await page.query_selector(selector)
                if rate_limit:
                    if not silent:
                        console.print(
                            "\n[bold red]Rate limit detected![/bold red]\n"
                            "[yellow]Pausing for 60 seconds...[/yellow]"
                        )
                    await asyncio.sleep(60)
                    return True, page
            except Exception:
                pass

        # Check for captcha
        captcha_selectors = [
            'text=安全验证',
            'text=请完成验证',
            'text=滑动验证',
            '.captcha-container',
        ]

        for selector in captcha_selectors:
            try:
                captcha = await page.query_selector(selector)
                if captcha:
                    if self.browser.headless:
                        if not silent:
                            console.print(
                                "\n[bold yellow]Security verification detected![/bold yellow]\n"
                                "[yellow]Switching to visible mode...[/yellow]"
                            )
                        await page.close()
                        page = await self.browser.switch_to_headed(current_url)
                        await asyncio.sleep(2)
                    else:
                        if not silent:
                            console.print(
                                "\n[bold yellow]Please complete verification in browser[/bold yellow]"
                            )

                    max_wait = 120
                    waited = 0
                    while waited < max_wait:
                        await asyncio.sleep(2)
                        waited += 2

                        still_present = False
                        for sel in captcha_selectors:
                            try:
                                el = await page.query_selector(sel)
                                if el:
                                    still_present = True
                                    break
                            except Exception:
                                pass

                        if not still_present:
                            if not silent:
                                console.print("[green]Verification completed![/green]")
                            await random_delay(1.0, 2.0)
                            return True, page

                    return True, page

            except Exception:
                pass

        return False, None

    def _parse_count(self, text: str) -> int:
        """Parse count from text like '1.2万' or '1234'."""
        text = text.strip()
        try:
            if "万" in text:
                num = float(text.replace("万", ""))
                return int(num * 10000)
            elif "亿" in text:
                num = float(text.replace("亿", ""))
                return int(num * 100000000)
            else:
                clean = "".join(c for c in text if c.isdigit() or c == ".")
                return int(float(clean)) if clean else 0
        except Exception:
            return 0

    @abstractmethod
    async def scrape(self, *args, **kwargs) -> Any:
        """Main scraping method to be implemented by subclasses."""
        pass
