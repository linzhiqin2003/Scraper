"""Search result scraper for Dianping."""
from urllib.parse import quote

from bs4 import BeautifulSoup

from ..config import DEFAULT_CITY_ID, WWW_BASE_URL
from ..models import DianpingSearchResult
from .base import DianpingBaseScraper, clean_int


class SearchScraper(DianpingBaseScraper):
    """Parse Dianping search result pages."""

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
        encoded_query = quote(query)
        url = f"{WWW_BASE_URL}/search/keyword/{city_id}/{channel}_{encoded_query}"
        if page > 1:
            url += f"/p{page}"

        html = self.get_text(url, referer=WWW_BASE_URL)
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
