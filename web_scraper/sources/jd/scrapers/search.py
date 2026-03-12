"""JD product search scraper.

Strategy: Playwright navigates to search.jd.com, intercepts the
pc_search_searchWare API response, and parses product data.

Unlike the comment API (which uses client.action and works with httpx),
the search API endpoint (api.m.jd.com/api) rejects non-browser HTTP clients
via TLS fingerprint detection. So we rely on Playwright interception.

For pagination, we trigger the page's own "next page" mechanism by scrolling
to load more results, or by directly navigating to the next page URL.
"""
import json
import logging
import re
import time
from math import ceil
from pathlib import Path
from typing import List, Optional
from urllib.parse import parse_qs, quote, urlparse

from ..config import Timeouts
from ..cookies import get_cookies_path, netscape_to_playwright
from ..models import SearchProduct, SearchResult

logger = logging.getLogger(__name__)

CDN_IMAGE_BASE = "https://img14.360buyimg.com/n1/"

# Sorting options (mapped to URL param values)
SORT_OPTIONS = {
    "default": "",
    "sales": "sort_totalsales15_desc",
    "price_asc": "sort_price_asc",
    "price_desc": "sort_price_desc",
    "comments": "sort_commentcount_desc",
}

# HTML tag stripper
_TAG_RE = re.compile(r"<[^>]+>")


def _clean_html(text: str) -> str:
    """Remove HTML tags from text (e.g. <font class='skcolor_ljg'>)."""
    return _TAG_RE.sub("", text).strip()


def _parse_ware_list(ware_list: list) -> List[SearchProduct]:
    """Parse wareList from search API response."""
    products = []
    for item in ware_list:
        image = item.get("imageurl", "")
        if image and not image.startswith("http"):
            image = CDN_IMAGE_BASE + image

        cid1 = item.get("cid1", "")
        cid2 = item.get("cid2", "")
        cid3 = item.get("catid", "")
        cat_ids = "/".join(filter(None, [cid1, cid2, cid3])) or None

        name = _clean_html(item.get("wareName", "") or item.get("name", ""))
        price = item.get("jdPrice") or item.get("price")

        products.append(SearchProduct(
            sku_id=item.get("skuId", ""),
            name=name,
            price=str(price) if price else None,
            image_url=image or None,
            shop_id=item.get("shopId"),
            shop_name=item.get("shopName"),
            brand=item.get("brand") or None,
            brand_id=item.get("brandId") or None,
            comment_count=item.get("comment"),
            average_score=item.get("averageScore"),
            subtitle=item.get("color"),
            is_plus_shop=bool(item.get("isPlusShop")),
            category_ids=cat_ids,
        ))
    return products


def _build_search_url(
    keyword: str,
    page: int = 1,
    sort: str = "",
    price_range: str | None = None,
    delivery: bool = False,
) -> str:
    """Build JD search URL with filters."""
    url = f"https://search.jd.com/Search?keyword={quote(keyword)}&enc=utf-8&page={page}"
    if sort:
        url += f"&psort={sort}"
    if price_range:
        url += f"&ev=exprice_{price_range}"
    if delivery:
        url += "&delivery=1"
    return url


class SearchScraper:
    """JD search scraper using Playwright response interception."""

    def __init__(self, cookies_path: Path | None = None):
        if cookies_path is None:
            cookies_path = get_cookies_path()
        if not cookies_path.exists():
            raise FileNotFoundError(
                f"Cookies file not found: {cookies_path}\n"
                f"Run 'scraper jd import-cookies <path>' first."
            )
        self.cookies_path = cookies_path

    def search(
        self,
        keyword: str,
        max_pages: int | None = None,
        max_results: int | None = None,
        sort: str = "default",
        price_range: str | None = None,
        delivery: bool = False,
        delay: float = 1.5,
        on_progress=None,
    ) -> SearchResult:
        """Search JD products.

        Args:
            keyword: Search keyword.
            max_pages: Max pages to fetch (30 products per page).
            max_results: Max products to collect.
            sort: Sort order: default, sales, price_asc, price_desc, comments.
            price_range: Price filter, format "min-max" (e.g. "100-500").
            delivery: Filter for JD delivery only.
            delay: Delay between pages (seconds).
            on_progress: Optional callback(page, total_pages, count).
        """
        from playwright.sync_api import sync_playwright

        sort_value = SORT_OPTIONS.get(sort, "")
        pw_cookies = netscape_to_playwright(self.cookies_path)

        all_products: List[SearchProduct] = []
        total_count: int | None = None
        normalized_keyword: str | None = None
        effective_max = max_pages

        # Shared state for response handler
        page_responses: list = []

        def handle_response(response):
            url = response.url
            if "api.m.jd.com" not in url:
                return
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            fid = params.get("functionId", [""])[0]
            if fid != "pc_search_searchWare":
                return
            try:
                if response.status == 200:
                    data = response.json()
                    page_responses.append(data)
            except Exception as e:
                logger.warning(f"Failed to parse search response: {e}")

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
            )
            context = browser.new_context(
                viewport={"width": 1440, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
            )
            context.add_cookies(pw_cookies)
            page = context.new_page()
            page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            )
            page.on("response", handle_response)

            page_num = 1
            while True:
                search_url = _build_search_url(
                    keyword, page=page_num, sort=sort_value,
                    price_range=price_range, delivery=delivery,
                )

                page_responses.clear()
                logger.info(f"Loading search page {page_num}: {search_url}")

                page.goto(
                    search_url,
                    wait_until="domcontentloaded",
                    timeout=Timeouts.NAVIGATION,
                )

                # Wait for search API response
                deadline = time.time() + 15
                while not page_responses and time.time() < deadline:
                    page.wait_for_timeout(500)

                # Check for risk control
                if "risk_handler" in page.url or "passport.jd.com" in page.url:
                    browser.close()
                    raise Exception(
                        "JD risk control triggered. Visit https://search.jd.com "
                        "in your browser to pass CAPTCHA, then retry."
                    )

                if not page_responses:
                    if page_num == 1:
                        browser.close()
                        raise Exception("No search data intercepted. Page may not have loaded correctly.")
                    logger.info(f"No data on page {page_num}, stopping")
                    break

                # Parse the last response (in case of multiple)
                data = page_responses[-1]
                result_data = data.get("data", {})
                ware_list = result_data.get("wareList", [])

                if not ware_list:
                    logger.info(f"Empty wareList on page {page_num}, stopping")
                    break

                products = _parse_ware_list(ware_list)
                all_products.extend(products)
                logger.info(f"Page {page_num}: {len(products)} products (total: {len(all_products)})")

                # Extract metadata from first page
                if page_num == 1:
                    total_count = result_data.get("resultCount")
                    normalized_keyword = result_data.get("listKeyWord")
                    if total_count and effective_max is None:
                        effective_max = ceil(total_count / 30)

                if on_progress:
                    on_progress(page_num, effective_max, len(all_products))

                # Stop conditions
                if max_results and len(all_products) >= max_results:
                    break
                if effective_max and page_num >= effective_max:
                    break

                page_num += 1
                time.sleep(delay)

            browser.close()

        # Trim
        if max_results:
            all_products = all_products[:max_results]

        return SearchResult(
            keyword=keyword,
            normalized_keyword=normalized_keyword,
            total_count=total_count,
            products=all_products,
            page=page_num,
            pages_fetched=page_num,
        )
