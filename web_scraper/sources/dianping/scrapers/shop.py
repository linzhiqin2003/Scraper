"""Shop detail scraper for Dianping."""
from urllib.parse import urlparse

from ..config import WWW_BASE_URL
from ..models import DianpingShopDeal, DianpingShopDetail
from .base import DianpingBaseScraper, extract_assigned_json


class ShopScraper(DianpingBaseScraper):
    """Fetch Dianping shop details from SSR HTML and embedded xhr cache."""

    def fetch(self, target: str) -> DianpingShopDetail:
        """Fetch a shop by URL or shop UUID."""
        shop_uuid = self._extract_shop_uuid(target)
        url = f"{WWW_BASE_URL}/shop/{shop_uuid}"

        html = self.get_text(url, referer=WWW_BASE_URL)
        cache = extract_assigned_json(html, "window.__xhrCache__ = ")

        base_data = self._get_cache_payload(cache, "unify/shop.bin")
        shop_info = self._get_cache_payload(cache, "wxmapi/shop/shopinfo").get("shopInfo", {})
        shelf_data = self._get_cache_payload(cache, "/meishi/poi/v1/shelf/0")

        deals = []
        classification_list = (
            shelf_data.get("data", {})
            .get("meal", {})
            .get("classificationList", [])
        )
        for group in classification_list:
            for item in group.get("mealList", []):
                deals.append(DianpingShopDeal(
                    deal_id=str(item.get("id", "")),
                    title=item.get("title") or "",
                    price=item.get("price"),
                    value=item.get("value"),
                    discount=item.get("discount"),
                    solds_desc=item.get("soldsDesc"),
                    image_url=item.get("imgUrl") or item.get("squareImgUrl"),
                    tags=[tag.get("tagText", "") for tag in item.get("dealTags", []) if tag.get("tagText")],
                ))

        shop_status = base_data.get("shopStatusDetail") or {}

        return DianpingShopDetail(
            shop_uuid=shop_uuid,
            shop_id=str(base_data.get("id") or shop_info.get("shopId")) if (base_data.get("id") or shop_info.get("shopId")) else None,
            name=shop_info.get("shopName") or base_data.get("name") or shop_uuid,
            short_name=base_data.get("name"),
            title_name=shop_info.get("titleName"),
            url=url,
            score_text=base_data.get("scoreText"),
            price_text=base_data.get("priceText") or shop_info.get("avgPriceText"),
            category=base_data.get("categoryName"),
            region=base_data.get("regionName"),
            address=base_data.get("address") or shop_info.get("address"),
            phone_numbers=base_data.get("phoneNos") or [],
            shop_type=base_data.get("shopType") or shop_info.get("shopType"),
            lat=base_data.get("lat"),
            lng=base_data.get("lng"),
            status_text=shop_status.get("text"),
            cover_image=base_data.get("defaultPic"),
            deals=deals,
            cache_keys=list(cache.keys()),
        )

    @staticmethod
    def _get_cache_payload(cache: dict, key_fragment: str) -> dict:
        for key, value in cache.items():
            if key_fragment in key:
                return value.get("data", {})
        return {}

    @staticmethod
    def _extract_shop_uuid(target: str) -> str:
        if "/shop/" in target:
            parsed = urlparse(target)
            return parsed.path.rstrip("/").split("/")[-1]
        return target.strip()
