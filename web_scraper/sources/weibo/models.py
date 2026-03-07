"""Data models for Weibo scraper."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class WeiboSearchResult(BaseModel):
    """A single Weibo search result card."""

    mid: Optional[str] = Field(default=None, description="Weibo post MID")
    user: Optional[str] = Field(default=None, description="Display name")
    user_url: Optional[str] = Field(default=None, description="User profile URL")
    posted_at: Optional[str] = Field(default=None, description="Displayed publish time text")
    source: Optional[str] = Field(default=None, description="Post source/app")
    content: str = Field(default="", description="Post text content")
    detail_url: Optional[str] = Field(default=None, description="Post detail URL")
    reposts: Optional[int] = Field(default=None, description="Repost count")
    comments: Optional[int] = Field(default=None, description="Comment count")
    likes: Optional[int] = Field(default=None, description="Like count")
    card_type: Optional[str] = Field(default=None, description="Raw card action-type")


class WeiboSearchResponse(BaseModel):
    """Search response payload for Weibo."""

    query: str = Field(description="Search query keyword")
    method: str = Field(description="Fetch method: http or playwright")
    pages_requested: int = Field(default=1, description="Requested page count")
    pages_fetched: int = Field(default=0, description="Actual fetched page count")
    results: List[WeiboSearchResult] = Field(default_factory=list, description="Result list")
    current_url: Optional[str] = Field(default=None, description="Last page URL")
    scraped_at: datetime = Field(default_factory=datetime.now, description="Scrape timestamp")

    model_config = {
        "json_encoders": {
            datetime: lambda value: value.isoformat() if value else None,
        }
    }


class WeiboImage(BaseModel):
    """Image metadata from a Weibo post."""

    pic_id: Optional[str] = Field(default=None, description="Picture ID")
    url: str = Field(description="Best quality image URL")
    thumbnail_url: Optional[str] = Field(default=None, description="Thumbnail URL")
    width: Optional[int] = Field(default=None, description="Image width")
    height: Optional[int] = Field(default=None, description="Image height")


class WeiboComment(BaseModel):
    """Comment item for Weibo detail."""

    comment_id: Optional[str] = Field(default=None, description="Comment ID")
    root_id: Optional[str] = Field(default=None, description="Root comment ID")
    user_id: Optional[str] = Field(default=None, description="Comment user ID")
    user: Optional[str] = Field(default=None, description="Comment user display name")
    user_url: Optional[str] = Field(default=None, description="Comment user profile URL")
    text: str = Field(default="", description="Comment text content")
    created_at: Optional[str] = Field(default=None, description="Comment publish time")
    source: Optional[str] = Field(default=None, description="Comment source")
    likes: Optional[int] = Field(default=None, description="Comment like count")
    reply_count: Optional[int] = Field(default=None, description="Nested reply count")


class WeiboDetailResponse(BaseModel):
    """Detail response payload for a single Weibo post."""

    input_value: str = Field(description="Input URL or post ID")
    method: str = Field(description="Fetch method: http or playwright")
    current_url: Optional[str] = Field(default=None, description="Resolved detail URL")
    post_id: Optional[str] = Field(default=None, description="Numeric post ID")
    mid: Optional[str] = Field(default=None, description="Weibo MID")
    mblogid: Optional[str] = Field(default=None, description="Short weibo ID in URL")

    author: Optional[str] = Field(default=None, description="Author display name")
    author_id: Optional[str] = Field(default=None, description="Author user ID")
    author_url: Optional[str] = Field(default=None, description="Author profile URL")
    created_at: Optional[str] = Field(default=None, description="Post publish time")
    region_name: Optional[str] = Field(default=None, description="Post region text")
    source: Optional[str] = Field(default=None, description="Post source/app")
    text: str = Field(default="", description="Post full text")

    reposts_count: Optional[int] = Field(default=None, description="Repost count")
    comments_count: Optional[int] = Field(default=None, description="Comment count")
    attitudes_count: Optional[int] = Field(default=None, description="Like count")

    images: List[WeiboImage] = Field(default_factory=list, description="Post images")
    comments: List[WeiboComment] = Field(default_factory=list, description="Fetched comments")
    comment_pages_requested: int = Field(default=0, description="Requested comment pages")
    comment_pages_fetched: int = Field(default=0, description="Fetched comment pages")
    comments_included: bool = Field(default=False, description="Whether comments were fetched")

    scraped_at: datetime = Field(default_factory=datetime.now, description="Scrape timestamp")

    model_config = {
        "json_encoders": {
            datetime: lambda value: value.isoformat() if value else None,
        }
    }


class WeiboRetweetedPost(BaseModel):
    """Simplified retweet (转发) info embedded in a profile post."""

    id: Optional[str] = Field(default=None, description="Retweeted post ID")
    mblogid: Optional[str] = Field(default=None, description="Retweeted post short ID")
    user_id: Optional[str] = Field(default=None, description="Original author user ID")
    user_screen_name: Optional[str] = Field(default=None, description="Original author name")
    created_at: Optional[str] = Field(default=None, description="Original post time (raw string)")
    text_raw: Optional[str] = Field(default=None, description="Original post plain text")


class WeiboPost(BaseModel):
    """A single Weibo post from a user's profile timeline."""

    id: Optional[str] = Field(default=None, description="Numeric post ID")
    mid: Optional[str] = Field(default=None, description="Weibo MID")
    mblogid: Optional[str] = Field(default=None, description="Short post ID used in URL")
    detail_url: Optional[str] = Field(default=None, description="Full detail URL")

    user_id: Optional[str] = Field(default=None, description="Author user ID")
    user_screen_name: Optional[str] = Field(default=None, description="Author display name")

    created_at: Optional[str] = Field(default=None, description="Post time (raw string from API)")
    source: Optional[str] = Field(default=None, description="Post source device/app")
    region_name: Optional[str] = Field(default=None, description="IP region text, e.g. 发布于 北京")

    text_raw: str = Field(default="", description="Post plain text (no HTML)")
    is_long_text: bool = Field(default=False, description="Whether post has truncated long text")

    reposts_count: Optional[int] = Field(default=None, description="Repost count")
    comments_count: Optional[int] = Field(default=None, description="Comment count")
    attitudes_count: Optional[int] = Field(default=None, description="Like count")

    pic_ids: List[str] = Field(default_factory=list, description="Picture IDs attached to the post")
    pic_num: int = Field(default=0, description="Number of pictures")

    is_top: bool = Field(default=False, description="Whether post is pinned to top")
    is_ad: bool = Field(default=False, description="Whether post is an advertisement")
    retweeted: Optional[WeiboRetweetedPost] = Field(default=None, description="Retweeted post info if this is a repost")


class WeiboProfileResponse(BaseModel):
    """Response payload for a user's profile posts."""

    uid: str = Field(description="Target user ID")
    screen_name: Optional[str] = Field(default=None, description="User display name")
    total_posts: Optional[int] = Field(default=None, description="Total posts on user's profile")

    mode: str = Field(description="Fetch mode: 'latest', 'time_range', 'keyword', 'time_range+keyword'")
    keyword: Optional[str] = Field(default=None, description="Keyword filter (q param)")
    start_time: Optional[int] = Field(default=None, description="Unix timestamp range start")
    end_time: Optional[int] = Field(default=None, description="Unix timestamp range end")
    total_in_range: Optional[int] = Field(default=None, description="Total posts matching filters")

    posts: List[WeiboPost] = Field(default_factory=list, description="Fetched post list")
    pages_fetched: int = Field(default=0, description="Number of API pages fetched")
    since_id: Optional[str] = Field(default=None, description="Cursor for next page (latest mode)")

    scraped_at: datetime = Field(default_factory=datetime.now, description="Scrape timestamp")

    model_config = {
        "json_encoders": {
            datetime: lambda value: value.isoformat() if value else None,
        }
    }


class WeiboHotItem(BaseModel):
    """A single item from Weibo hot-search list."""

    rank: Optional[int] = Field(default=None, description="Hot-search rank")
    topic: str = Field(default="", description="Hot topic keyword")
    word_scheme: Optional[str] = Field(default=None, description="Topic scheme text")
    search_url: Optional[str] = Field(default=None, description="Topic search URL")
    heat: Optional[int] = Field(default=None, description="Heat metric")
    label: Optional[str] = Field(default=None, description="Badge label, e.g. 热/新/沸")
    topic_flag: Optional[int] = Field(default=None, description="Topic flag from API")
    icon: Optional[str] = Field(default=None, description="Badge icon URL")


class WeiboHotResponse(BaseModel):
    """Hot-search response payload for Weibo."""

    method: str = Field(description="Fetch method: http or playwright")
    current_url: Optional[str] = Field(default=None, description="Resolved hot-search URL")
    total_available: int = Field(default=0, description="Total rows available before slicing")
    limit: Optional[int] = Field(default=None, description="Requested result limit")
    items: List[WeiboHotItem] = Field(default_factory=list, description="Hot-topic rows")
    scraped_at: datetime = Field(default_factory=datetime.now, description="Scrape timestamp")

    model_config = {
        "json_encoders": {
            datetime: lambda value: value.isoformat() if value else None,
        }
    }
