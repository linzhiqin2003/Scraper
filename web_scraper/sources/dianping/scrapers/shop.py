"""Shop detail scraper for Dianping."""
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from ..config import MOBILE_BASE_URL, WWW_BASE_URL
from ..models import (
    DianpingRecommendedDish,
    DianpingShopComment,
    DianpingShopDeal,
    DianpingShopDetail,
)
from .base import DianpingBaseScraper, extract_assigned_json


class ShopScraper(DianpingBaseScraper):
    """Fetch Dianping shop details from SSR HTML and embedded xhr cache."""

    def fetch(self, target: str, *, comment_limit: int = 5) -> DianpingShopDetail:
        """Fetch a shop by URL or shop UUID."""
        shop_uuid = self._extract_shop_uuid(target)
        url = f"{WWW_BASE_URL}/shop/{shop_uuid}"
        review_url = f"{MOBILE_BASE_URL}/shop/{shop_uuid}/review_all"

        html = self.get_text(url, referer=WWW_BASE_URL)
        soup = BeautifulSoup(html, "lxml")
        review_html = self._get_mobile_html(review_url, referer=url)
        review_soup = BeautifulSoup(review_html, "lxml")
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

        recommended_dishes = self._parse_recommended_dishes(soup)
        comments = self._parse_preview_comments(review_soup, limit=comment_limit)
        comment_count = self._parse_comment_count(soup)

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
            recommended_dishes=recommended_dishes,
            comment_count=comment_count,
            comments=comments,
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

    @staticmethod
    def _parse_recommended_dishes(soup: BeautifulSoup) -> list[DianpingRecommendedDish]:
        """Parse the recommended dish module from SSR HTML."""
        module = soup.select_one(".groupItem.dishInfo")
        if not module:
            return []

        cards = module.select(".recommendWrap")
        names = [node.get_text(strip=True) for node in module.select(".dishName")]
        results: list[DianpingRecommendedDish] = []

        for index, name in enumerate(names):
            card = cards[index] if index < len(cards) else None
            recommend_count = None
            image_url = None
            dish_url = None

            if card:
                recommend_text = card.select_one(".recomment-text")
                if recommend_text:
                    digits = "".join(ch for ch in recommend_text.get_text(strip=True) if ch.isdigit())
                    recommend_count = int(digits) if digits else None

                lazy_image = card.select_one(".lazyload-image")
                if lazy_image:
                    style = lazy_image.get("style", "")
                    marker = "background-image:url("
                    if marker in style:
                        start = style.find(marker) + len(marker)
                        end = style.find(")", start)
                        if end != -1:
                            image_url = style[start:end]

                dish_url = card.get("data-launch-h5-url")

            results.append(DianpingRecommendedDish(
                name=name,
                recommend_count=recommend_count,
                image_url=image_url,
                url=dish_url,
            ))

        return results

    @staticmethod
    def _parse_preview_comments(
        soup: BeautifulSoup,
        *,
        limit: int = 5,
    ) -> list[DianpingShopComment]:
        """Parse the first page of comments from mobile review_all HTML."""
        comments: list[DianpingShopComment] = []
        effective_limit = max(limit, 0)
        for item in soup.select(".comments-list .review-item")[:effective_limit]:
            author = item.select_one(".seed-user-name")
            publish_time = item.select_one(".seed-add-time")
            price = item.select_one(".seed-feeds-avg-price")
            content = item.select_one(".seed-feed-content-txt")
            images = item.select(".seed-image-display-wrapper img")
            like_block = item.select_one(".seed-reply-header-left")

            if not author or not content:
                continue

            like_count = None
            if like_block:
                digits = "".join(ch for ch in like_block.get_text(" ", strip=True) if ch.isdigit())
                like_count = int(digits) if digits else None

            star_nodes = item.select(".seed-star_icon .seed-star")
            rating_text = None
            if star_nodes:
                full_stars = sum(1 for node in star_nodes if "seed-star_50" in " ".join(node.get("class", [])))
                rating_text = f"{full_stars}星" if full_stars else None

            comments.append(DianpingShopComment(
                author_name=author.get_text(strip=True),
                publish_time=publish_time.get_text(strip=True) if publish_time else None,
                rating_text=rating_text,
                price_text=price.get_text(strip=True) if price else None,
                content=content.get_text(" ", strip=True),
                image_count=len(images),
                like_count=like_count,
            ))

        return comments

    @staticmethod
    def _parse_comment_count(soup: BeautifulSoup) -> int | None:
        """Parse total review count shown on the page header or review module."""
        review_node = soup.select_one(".reviews")
        if review_node:
            digits = "".join(ch for ch in review_node.get_text(strip=True) if ch.isdigit())
            if digits:
                return int(digits)

        for node in soup.find_all(string=True):
            text = node.strip()
            if text.startswith("评价(") and text.endswith(")"):
                digits = "".join(ch for ch in text if ch.isdigit())
                if digits:
                    return int(digits)
        return None

    def _get_mobile_html(self, url: str, *, referer: str) -> str:
        """Fetch a mobile Dianping page using an iPhone-like user agent."""
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                "Version/17.0 Mobile/15E148 Safari/604.1"
            ),
            "Referer": referer,
        }
        resp = self.client.get(url, headers=headers)
        self._raise_for_verify(resp)
        return resp.text
