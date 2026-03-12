"""Data models for Dianping source."""
from typing import Any, List, Optional

from pydantic import BaseModel, Field


class DianpingNavigationItem(BaseModel):
    """Top navigation item from Dianping home."""

    config_id: int = Field(description="Navigation config id")
    title: str = Field(description="Navigation title")
    url: str = Field(description="Target URL")
    icon_url: Optional[str] = Field(default=None, description="Icon URL")
    sort_order: Optional[int] = Field(default=None, description="Display order")


class DianpingUserProfile(BaseModel):
    """Logged-in Dianping user profile."""

    user_id: str = Field(description="User ID")
    nickname: str = Field(description="Nickname")
    avatar_url: Optional[str] = Field(default=None, description="Avatar URL")
    review_count: Optional[int] = Field(default=None, description="Review count")
    fans_count: Optional[int] = Field(default=None, description="Fans count")
    user_level: Optional[int] = Field(default=None, description="User level")


class DianpingFeedItem(BaseModel):
    """A single item from the Dianping home feed."""

    biz_id: str = Field(description="Feed biz id")
    content_id: Optional[int] = Field(default=None, description="Feed content id")
    title: str = Field(description="Feed title")
    url: str = Field(description="Detail URL")
    author_name: Optional[str] = Field(default=None, description="Author nickname")
    author_id: Optional[str] = Field(default=None, description="Author user id")
    like_count: Optional[int] = Field(default=None, description="Like count")
    comment_count: Optional[int] = Field(default=None, description="Comment count")
    city_id: Optional[int] = Field(default=None, description="POI city id")
    cover_url: Optional[str] = Field(default=None, description="Cover image URL or key")


class DianpingFeedResponse(BaseModel):
    """Home feed response."""

    city_id: int = Field(description="City id")
    page_start: int = Field(description="Feed offset")
    page_size: int = Field(description="Feed page size")
    total_num: Optional[int] = Field(default=None, description="Total feed count")
    items: List[DianpingFeedItem] = Field(default_factory=list, description="Feed items")


class DianpingSearchResult(BaseModel):
    """Search result item for Dianping shops."""

    shop_uuid: str = Field(description="Shop UUID")
    title: str = Field(description="Shop title")
    url: str = Field(description="Shop URL")
    review_count: Optional[int] = Field(default=None, description="Review count")
    avg_price_text: Optional[str] = Field(default=None, description="Average price text")
    category: Optional[str] = Field(default=None, description="Category")
    region: Optional[str] = Field(default=None, description="Region")
    image_url: Optional[str] = Field(default=None, description="Shop image URL")


class DianpingShopDeal(BaseModel):
    """Deal item from shop detail."""

    deal_id: str = Field(description="Deal ID")
    title: str = Field(description="Deal title")
    price: Optional[float] = Field(default=None, description="Selling price")
    value: Optional[float] = Field(default=None, description="Original value")
    discount: Optional[str] = Field(default=None, description="Discount text")
    solds_desc: Optional[str] = Field(default=None, description="Sales text")
    image_url: Optional[str] = Field(default=None, description="Deal image")
    tags: List[str] = Field(default_factory=list, description="Deal tags")


class DianpingRecommendedDish(BaseModel):
    """Recommended dish parsed from shop detail SSR."""

    name: str = Field(description="Dish name")
    recommend_count: Optional[int] = Field(default=None, description="Number of recommendations")
    image_url: Optional[str] = Field(default=None, description="Dish image URL")
    url: Optional[str] = Field(default=None, description="Dish detail URL")


class DianpingShopComment(BaseModel):
    """Preview comment shown on the shop detail page."""

    author_name: str = Field(description="Comment author")
    publish_time: Optional[str] = Field(default=None, description="Display time")
    rating_text: Optional[str] = Field(default=None, description="Short rating text")
    price_text: Optional[str] = Field(default=None, description="Per-person text in comment")
    content: str = Field(description="Comment content")
    image_count: int = Field(default=0, description="Number of attached images in preview")
    like_count: Optional[int] = Field(default=None, description="Like count")


class DianpingShopDetail(BaseModel):
    """Shop detail parsed from Dianping shop page."""

    shop_uuid: str = Field(description="Shop UUID")
    shop_id: Optional[str] = Field(default=None, description="Shop numeric ID")
    name: str = Field(description="Shop display name")
    short_name: Optional[str] = Field(default=None, description="Short shop name")
    title_name: Optional[str] = Field(default=None, description="SEO title name")
    url: str = Field(description="Shop URL")
    score_text: Optional[str] = Field(default=None, description="Score text")
    price_text: Optional[str] = Field(default=None, description="Price text")
    category: Optional[str] = Field(default=None, description="Primary category")
    region: Optional[str] = Field(default=None, description="Region")
    address: Optional[str] = Field(default=None, description="Address")
    phone_numbers: List[str] = Field(default_factory=list, description="Phone numbers")
    shop_type: Optional[int] = Field(default=None, description="Shop type")
    lat: Optional[float] = Field(default=None, description="Latitude")
    lng: Optional[float] = Field(default=None, description="Longitude")
    status_text: Optional[str] = Field(default=None, description="Shop status text")
    cover_image: Optional[str] = Field(default=None, description="Cover image URL")
    deals: List[DianpingShopDeal] = Field(default_factory=list, description="Deals")
    recommended_dishes: List[DianpingRecommendedDish] = Field(
        default_factory=list,
        description="Recommended dishes shown on page",
    )
    comment_count: Optional[int] = Field(default=None, description="Total review count")
    comments: List[DianpingShopComment] = Field(
        default_factory=list,
        description="Preview comments shown on page",
    )
    cache_keys: List[str] = Field(default_factory=list, description="Embedded cache keys")


class DianpingAuthor(BaseModel):
    """Author on Dianping content."""

    user_id: str = Field(description="Author user ID")
    nickname: str = Field(description="Author nickname")
    avatar_url: Optional[str] = Field(default=None, description="Avatar URL")


class DianpingNoteRecommendation(BaseModel):
    """Recommended note under note detail."""

    title: Optional[str] = Field(default=None, description="Recommendation title")
    content: Optional[str] = Field(default=None, description="Recommendation content")
    author_name: Optional[str] = Field(default=None, description="Author nickname")
    like_count: Optional[int] = Field(default=None, description="Like count")
    comment_count: Optional[int] = Field(default=None, description="Comment count")
    image_urls: List[str] = Field(default_factory=list, description="Recommendation image URLs")


class DianpingNoteDetail(BaseModel):
    """Note detail parsed from SSR __NEXT_DATA__."""

    note_id: str = Field(description="Note main ID")
    feed_type: int = Field(description="Feed type")
    url: str = Field(description="Canonical note URL")
    title: Optional[str] = Field(default=None, description="Note title")
    content: Optional[str] = Field(default=None, description="Note body text")
    author: Optional[DianpingAuthor] = Field(default=None, description="Author info")
    like_count: Optional[int] = Field(default=None, description="Like count")
    comment_count: Optional[int] = Field(default=None, description="Comment count")
    collect_count: Optional[int] = Field(default=None, description="Collect count")
    published_at: Optional[str] = Field(default=None, description="Publish time")
    images: List[str] = Field(default_factory=list, description="Image URLs")
    topics: List[str] = Field(default_factory=list, description="Topics")
    recommendations: List[DianpingNoteRecommendation] = Field(
        default_factory=list,
        description="Recommended note list",
    )
    raw_page: Optional[str] = Field(default=None, description="Next.js page id")


class DianpingHomeSnapshot(BaseModel):
    """Combined response for home browse command."""

    profile: Optional[DianpingUserProfile] = Field(default=None, description="User profile")
    navigation: List[DianpingNavigationItem] = Field(default_factory=list, description="Home navigation")
    feed: DianpingFeedResponse = Field(description="Home feed response")


class DianpingFetchBundle(BaseModel):
    """Generic fetch response wrapper."""

    kind: str = Field(description="Fetched resource kind")
    data: dict[str, Any] = Field(description="Serialized payload")
