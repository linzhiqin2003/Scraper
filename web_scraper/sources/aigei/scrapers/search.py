"""Aigei GIF search scraper.

Uses Playwright to bypass IP ban + JS verification.
Falls back to HTTP requests for image downloads (CDN doesn't block).
"""
import base64
import logging
import re
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, Page, Browser

from ..config import (
    BASE_URL,
    CDN_BASE,
    DOWNLOAD_DELAY,
    HEADERS,
    REQUEST_DELAY,
    RESOURCE_TYPES,
    SEARCH_URL,
)
from ..models import GifItem, GifSearchResult

logger = logging.getLogger(__name__)

# Browser state file for persisting cookies across sessions
_STATE_DIR = Path.home() / ".web_scraper" / "aigei"
_STATE_FILE = _STATE_DIR / "browser_state.json"


class SearchScraper:
    """Search and download GIF resources from Aigei.

    Uses Playwright for search pages (bypasses IP ban + JS challenge),
    and plain HTTP for CDN image downloads.
    """

    def __init__(self):
        self._browser: Optional[Browser] = None
        self._page: Optional[Page] = None
        self._pw = None
        self._http = requests.Session()
        self._http.headers.update(HEADERS)

    def _ensure_browser(self) -> Page:
        """Launch browser and handle ban verification if needed."""
        if self._page and not self._page.is_closed():
            return self._page

        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )

        # Load saved state if available
        context_kwargs = {}
        if _STATE_FILE.exists():
            context_kwargs["storage_state"] = str(_STATE_FILE)

        context = self._browser.new_context(**context_kwargs)
        self._page = context.new_page()

        # Navigate and handle potential ban page
        self._page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
        self._handle_ban_if_needed(self._page)

        # Save state for next time
        _STATE_DIR.mkdir(parents=True, exist_ok=True)
        context.storage_state(path=str(_STATE_FILE))

        return self._page

    def _handle_ban_if_needed(self, page: Page) -> None:
        """Detect and handle the banip JS verification page."""
        # Check if we hit the ban page
        if "banip" not in page.content().lower():
            return

        logger.info("Detected IP ban page, completing JS verification...")

        # The ban page auto-submits a form, then shows a JS challenge.
        # Wait for the challenge page to load and auto-resolve.
        try:
            # Wait for the form to auto-submit and JS to execute
            page.wait_for_load_state("networkidle", timeout=15000)

            # Check if still on ban page after JS execution
            if "banip" in page.content().lower():
                # The JS challenge page may need more time
                page.wait_for_url(f"{BASE_URL}/**", timeout=20000)
        except Exception:
            # If timeout, the JS challenge might redirect via JS
            pass

        # Final check - try homepage again
        if "banip" in page.content().lower():
            page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_load_state("networkidle", timeout=15000)

        if "banip" not in page.content().lower():
            logger.info("IP ban verification passed")
        else:
            logger.warning("IP ban verification may have failed - continuing anyway")

    def search(
        self,
        keyword: str,
        max_pages: Optional[int] = None,
        resource_type: str = "gif",
    ) -> GifSearchResult:
        """Search for GIF resources by keyword.

        Args:
            keyword: Search keyword.
            max_pages: Max pages to scrape (None for all).
            resource_type: Resource type key from RESOURCE_TYPES.

        Returns:
            GifSearchResult with all found items.
        """
        type_param = RESOURCE_TYPES.get(resource_type, RESOURCE_TYPES["gif"])
        all_items: list[GifItem] = []

        page = self._ensure_browser()

        html = self._fetch_page_pw(page, keyword, 1, type_param)
        total_pages = self._get_total_pages(html)
        all_items.extend(self._parse_items(html))

        if max_pages:
            total_pages = min(total_pages, max_pages)

        for pg in range(2, total_pages + 1):
            time.sleep(REQUEST_DELAY)
            try:
                html = self._fetch_page_pw(page, keyword, pg, type_param)
                all_items.extend(self._parse_items(html))
            except Exception as e:
                logger.warning("Page %d failed: %s", pg, e)
                continue

        return GifSearchResult(
            keyword=keyword,
            total_pages=total_pages,
            items=all_items,
        )

    def download(
        self,
        items: list[GifItem],
        output_dir: Path,
        skip_vip: bool = True,
    ) -> tuple[int, int]:
        """Download GIF files via HTTP (CDN doesn't block)."""
        output_dir.mkdir(parents=True, exist_ok=True)
        success, fail = 0, 0

        download_items = [it for it in items if not it.is_vip] if skip_vip else items

        for item in download_items:
            if self._download_gif(item, output_dir):
                success += 1
            else:
                fail += 1
            time.sleep(DOWNLOAD_DELAY)

        return success, fail

    def close(self) -> None:
        """Close browser resources."""
        if self._page and not self._page.is_closed():
            # Save state before closing
            try:
                _STATE_DIR.mkdir(parents=True, exist_ok=True)
                self._page.context.storage_state(path=str(_STATE_FILE))
            except Exception:
                pass
            try:
                self._page.context.close()
            except Exception:
                pass
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
        if self._pw:
            try:
                self._pw.stop()
            except Exception:
                pass

    def __del__(self):
        self.close()

    # ── Playwright page fetching ──

    def _fetch_page_pw(self, page: Page, keyword: str, pg: int, type_param: str) -> str:
        """Fetch a search page using Playwright."""
        params = urlencode({"type": type_param, "q": keyword, "page": pg})
        url = f"{SEARCH_URL}?{params}"
        page.goto(url, wait_until="domcontentloaded", timeout=30000)

        # Handle ban if it reappears
        if "banip" in page.content()[:500].lower():
            self._handle_ban_if_needed(page)
            page.goto(url, wait_until="domcontentloaded", timeout=30000)

        # Wait for items to load
        try:
            page.wait_for_selector('div[id^="unitBox_item-"]', timeout=10000)
        except Exception:
            pass  # Page may have no results

        return page.content()

    # ── HTML parsing (static, reused from original) ──

    @staticmethod
    def _get_total_pages(html: str) -> int:
        """Extract total page count from HTML."""
        soup = BeautifulSoup(html, "html.parser")
        total_el = soup.select_one("i.pageInfo_totalPage")
        if total_el:
            try:
                return int(total_el.get_text(strip=True))
            except ValueError:
                pass
        return 1

    @staticmethod
    def _parse_items(html: str) -> list[GifItem]:
        """Parse GIF items from search page HTML."""
        soup = BeautifulSoup(html, "html.parser")
        containers = soup.select('div[id^="unitBox_item-"]')
        items: list[GifItem] = []

        for container in containers:
            itemid = container.get("itemid", "")
            if not itemid:
                continue

            item_code = container.get("js-item-code", "")

            title_el = container.select_one("b.trans-title")
            title = title_el.get_text(strip=True) if title_el else ""

            view_link = container.select_one(".item-view-url a")
            detail_href = view_link.get("href", "") if view_link else ""

            # Image URL: prefer loaded src, fallback to lazy-loaded base64
            img = container.select_one('img[src*="s1.aigei.com/src/img"]')
            img_url = ""
            if img:
                src = img.get("src", "")
                img_url = (CDN_BASE + src) if src.startswith("//") else src
            else:
                lazy = container.select_one('img[data-original^="aigei-image-encode-"]')
                if lazy:
                    encoded = lazy.get("data-original", "").replace("aigei-image-encode-", "")
                    try:
                        img_url = base64.b64decode(encoded.replace("\n", "")).decode()
                    except Exception:
                        pass

            is_vip = bool(container.select_one(".js-vip-tag-goods, .unit-tagtip-vip"))

            items.append(GifItem(
                itemid=str(itemid),
                item_code=str(item_code),
                title=title,
                detail_url=f"{BASE_URL}{detail_href}" if detail_href else "",
                img_url=img_url,
                is_vip=is_vip,
            ))

        return items

    # ── HTTP download (CDN doesn't enforce ban) ──

    def _download_gif(self, item: GifItem, output_dir: Path) -> bool:
        """Download a single GIF file."""
        if not item.img_url:
            return False

        filename = f"{item.itemid}_{_sanitize_filename(item.title)}.gif"
        filepath = output_dir / filename

        if filepath.exists():
            return True

        try:
            resp = self._http.get(item.img_url, timeout=30, stream=True)
            resp.raise_for_status()
            with open(filepath, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            return True
        except Exception:
            return False


def _sanitize_filename(name: str) -> str:
    """Sanitize filename."""
    name = re.sub(r'[\\/:*?"<>|]', "_", name)
    return name[:80]
