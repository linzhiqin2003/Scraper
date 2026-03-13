"""Search result scraper for Dianping."""
from bs4 import BeautifulSoup
from patchright.sync_api import TimeoutError as PlaywrightTimeout

from ....core.browser import create_browser, get_state_path
from ..config import DEFAULT_CITY_ID, SOURCE_NAME, WWW_BASE_URL, build_search_url
from ..cookies import get_cookies_path, load_playwright_cookies
from ..models import DianpingSearchResult
from .base import DianpingBaseScraper, clean_int


class SearchScraper(DianpingBaseScraper):
    """Parse Dianping search result pages."""

    @staticmethod
    def parse_html(html: str, limit: int = 10) -> list[DianpingSearchResult]:
        """Parse Dianping SSR search HTML into structured results."""
        soup = BeautifulSoup(html, "lxml")

        results: list[DianpingSearchResult] = []
        for li in soup.select(".shop-all-list li"):
            title_node = li.select_one(".tit h4")
            link_node = li.select_one('.tit a[href*="/shop/"]')
            if not title_node or not link_node:
                continue

            shop_url = link_node.get("href") or ""
            shop_uuid = shop_url.rstrip("/").split("/")[-1]

            review_text = li.select_one(".comment .review-num")
            avg_price = li.select_one(".comment .mean-price b")
            tags = [tag.get_text(strip=True) for tag in li.select(".tag-addr .tag")]
            image = li.select_one(".pic img")

            results.append(DianpingSearchResult(
                shop_uuid=shop_uuid,
                title=title_node.get_text(strip=True),
                url=shop_url,
                review_count=clean_int(review_text.get_text(" ", strip=True) if review_text else ""),
                avg_price_text=avg_price.get_text(strip=True) if avg_price else None,
                category=tags[0] if tags else None,
                region=tags[1] if len(tags) > 1 else None,
                image_url=(image.get("src") or image.get("data-src")) if image else None,
            ))

            if len(results) >= limit:
                break

        return results

    def search(
        self,
        *,
        query: str,
        city_id: int = DEFAULT_CITY_ID,
        channel: int = 0,
        page: int = 1,
        limit: int = 10,
    ) -> list[DianpingSearchResult]:
        """Search shops from the Dianping SSR result page."""
        url = build_search_url(query=query, city_id=city_id, channel=channel, page=page)
        html = self.get_text(url, referer=WWW_BASE_URL)
        return self.parse_html(html, limit=limit)

    def search_with_browser(
        self,
        *,
        query: str,
        city_id: int = DEFAULT_CITY_ID,
        channel: int = 0,
        page: int = 1,
        limit: int = 10,
        headless: bool = True,
        timeout_seconds: int = 120,
    ) -> list[DianpingSearchResult]:
        """Search by loading the SSR page in a real browser session."""
        url = build_search_url(query=query, city_id=city_id, channel=channel, page=page)
        state_file = get_state_path(SOURCE_NAME)
        if not state_file.exists() and headless:
            raise RuntimeError(
                "未找到已保存的浏览器搜索会话。"
                "请先运行 'scraper dianping login'，或使用 '--browser --manual --no-headless'。"
            )

        try:
            with create_browser(
                headless=headless,
                source=SOURCE_NAME,
                use_storage_state=True,
            ) as page_obj:
                if not state_file.exists():
                    cookies_path = get_cookies_path()
                    if cookies_path.exists():
                        page_obj.context.add_cookies(load_playwright_cookies(cookies_path))

                page_obj.goto(url, wait_until="domcontentloaded", timeout=60000)
                page_obj.wait_for_selector(".shop-all-list li", state="visible", timeout=timeout_seconds * 1000)
                state_file.parent.mkdir(parents=True, exist_ok=True)
                page_obj.context.storage_state(path=str(state_file))
                return self.parse_html(page_obj.content(), limit=limit)
        except PlaywrightTimeout as exc:
            raise RuntimeError(
                "浏览器模式等待搜索结果超时。"
                "如果页面停在验证页，请先运行 'scraper dianping login' 完成人工验证。"
            ) from exc
