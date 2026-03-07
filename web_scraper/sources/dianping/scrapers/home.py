"""Home feed scraper for Dianping."""
from ..config import (
    DEFAULT_CITY_ID,
    DEFAULT_PAGE_SIZE,
    DEFAULT_SOURCE_ID,
    DP_HOME_URL,
    GROWTH_LIST_FEEDS_URL,
    GROWTH_QUERY_INDEX_URL,
    GROWTH_USER_INFO_URL,
    build_home_feed_payload,
)
from ..cookies import get_lx_cuid
from ..models import (
    DianpingFeedItem,
    DianpingFeedResponse,
    DianpingHomeSnapshot,
    DianpingNavigationItem,
    DianpingUserProfile,
)
from .base import DianpingBaseScraper


class HomeScraper(DianpingBaseScraper):
    """Scrape Dianping home navigation, profile and feeds."""

    def get_profile(self) -> DianpingUserProfile | None:
        """Fetch current logged-in user profile."""
        data = self.post_json(
            GROWTH_USER_INFO_URL,
            body={},
            referer=DP_HOME_URL,
            origin="https://m.dianping.com",
        )
        user = data.get("result", {})
        if not user:
            return None

        return DianpingUserProfile(
            user_id=str(user.get("userId", "")),
            nickname=user.get("userNickName") or "",
            avatar_url=user.get("userFace"),
            review_count=user.get("reviewCount"),
            fans_count=user.get("fansCount"),
            user_level=user.get("userLevel"),
        )

    def get_navigation(
        self,
        *,
        city_id: int = DEFAULT_CITY_ID,
        source_id: int = DEFAULT_SOURCE_ID,
    ) -> list[DianpingNavigationItem]:
        """Fetch home navigation entries."""
        data = self.post_json(
            GROWTH_QUERY_INDEX_URL,
            body={"cityId": city_id, "sourceId": source_id},
            referer=DP_HOME_URL,
            origin="https://m.dianping.com",
        )
        items = []
        for item in data.get("result", []):
            items.append(DianpingNavigationItem(
                config_id=item.get("configId", 0),
                title=item.get("title") or "",
                url=item.get("url") or "",
                icon_url=item.get("iconUrl"),
                sort_order=item.get("eleOrder"),
            ))
        return items

    def get_feed(
        self,
        *,
        city_id: int = DEFAULT_CITY_ID,
        page_start: int = 0,
        page_size: int = DEFAULT_PAGE_SIZE,
        source_id: int = DEFAULT_SOURCE_ID,
    ) -> DianpingFeedResponse:
        """Fetch home feed items."""
        body = build_home_feed_payload(
            page_start=page_start,
            page_size=page_size,
            city_id=city_id,
            source_id=source_id,
            lx_cuid=get_lx_cuid(self.cookies),
        )
        data = self.post_json(
            GROWTH_LIST_FEEDS_URL,
            body=body,
            referer=DP_HOME_URL,
            origin="https://m.dianping.com",
        )
        result = data.get("result", {})

        items = []
        for item in result.get("feedsRecordDTOS", []):
            items.append(DianpingFeedItem(
                biz_id=str(item.get("bizId", "")),
                content_id=item.get("contentId"),
                title=item.get("title") or "",
                url=item.get("schema") or "",
                author_name=item.get("userNickName"),
                author_id=str(item.get("userId")) if item.get("userId") is not None else None,
                like_count=item.get("likeCount"),
                comment_count=item.get("commentCount"),
                city_id=item.get("poiCityId"),
                cover_url=item.get("picUrl") or item.get("coverUrl") or item.get("picKey"),
            ))

        return DianpingFeedResponse(
            city_id=city_id,
            page_start=page_start,
            page_size=page_size,
            total_num=result.get("totalNum"),
            items=items,
        )

    def browse(
        self,
        *,
        city_id: int = DEFAULT_CITY_ID,
        page_start: int = 0,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> DianpingHomeSnapshot:
        """Fetch combined home snapshot."""
        profile = self.get_profile()
        navigation = self.get_navigation(city_id=city_id)
        feed = self.get_feed(city_id=city_id, page_start=page_start, page_size=page_size)
        return DianpingHomeSnapshot(
            profile=profile,
            navigation=navigation,
            feed=feed,
        )
