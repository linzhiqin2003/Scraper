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
