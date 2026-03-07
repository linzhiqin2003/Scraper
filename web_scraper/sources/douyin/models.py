"""Data models for Douyin scraper."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class DouyinUser(BaseModel):
    """Douyin user info embedded in comment/reply."""

    uid: Optional[str] = Field(default=None, description="User numeric ID")
    sec_uid: Optional[str] = Field(default=None, description="Encrypted user ID")
    nickname: Optional[str] = Field(default=None, description="Display name")
    avatar_url: Optional[str] = Field(default=None, description="Avatar thumbnail URL")
    ip_label: Optional[str] = Field(default=None, description="IP attribution label, e.g. 广东")


class DouyinReply(BaseModel):
    """A single reply (level-2 comment) under a parent comment."""

    cid: Optional[str] = Field(default=None, description="Reply comment ID")
    text: str = Field(default="", description="Reply text content")
    user: Optional[DouyinUser] = Field(default=None, description="Reply author")
    digg_count: Optional[int] = Field(default=None, description="Like count")
    created_at: Optional[int] = Field(default=None, description="Unix timestamp")
    ip_label: Optional[str] = Field(default=None, description="IP attribution label")


class DouyinComment(BaseModel):
    """A single top-level comment on a Douyin video."""

    cid: Optional[str] = Field(default=None, description="Comment ID")
    text: str = Field(default="", description="Comment text content")
    user: Optional[DouyinUser] = Field(default=None, description="Comment author")
    digg_count: Optional[int] = Field(default=None, description="Like count")
    reply_count: Optional[int] = Field(default=None, description="Total reply count")
    created_at: Optional[int] = Field(default=None, description="Unix timestamp")
    ip_label: Optional[str] = Field(default=None, description="IP attribution label")
    replies: List[DouyinReply] = Field(default_factory=list, description="Fetched replies")


class DouyinFetchResponse(BaseModel):
    """Response payload for a Douyin video comment fetch."""

    url: str = Field(description="Input video URL")
    aweme_id: str = Field(description="Video ID extracted from URL")
    desc: Optional[str] = Field(default=None, description="Video title/description")
    author_name: Optional[str] = Field(default=None, description="Video author nickname")
    total_comments: Optional[int] = Field(default=None, description="Total comment count from API")
    comments: List[DouyinComment] = Field(default_factory=list, description="Fetched comments")
    fetched_count: int = Field(default=0, description="Number of comments in this response")
    pages_fetched: int = Field(default=0, description="Number of comment API pages intercepted")
    method: str = Field(default="playwright_intercept", description="Fetch method")
    scraped_at: datetime = Field(default_factory=datetime.now, description="Scrape timestamp")

    model_config = {
        "json_encoders": {
            datetime: lambda v: v.isoformat() if v else None,
        }
    }
