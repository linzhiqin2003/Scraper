"""Data models for X (Twitter) source."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class XUser(BaseModel):
    """X user info."""
    id: str = Field(description="User ID")
    screen_name: str = Field(description="@handle")
    name: str = Field(description="Display name")
    followers_count: int = Field(default=0)
    following_count: int = Field(default=0)
    is_blue_verified: bool = Field(default=False)
    profile_image_url: Optional[str] = None


class XTweet(BaseModel):
    """A single tweet/post."""
    id: str = Field(description="Tweet ID")
    full_text: str = Field(description="Tweet text content")
    created_at: Optional[str] = Field(default=None, description="RFC2822 timestamp")
    author: Optional[XUser] = None
    favorite_count: int = Field(default=0, description="Likes")
    retweet_count: int = Field(default=0)
    reply_count: int = Field(default=0)
    bookmark_count: int = Field(default=0)
    view_count: Optional[str] = Field(default=None, description="View count string")
    lang: Optional[str] = None
    url: Optional[str] = Field(default=None, description="Tweet permalink")
    media_urls: List[str] = Field(default_factory=list, description="Attached media URLs")
    is_retweet: bool = False
    is_quote: bool = False
    quoted_tweet: Optional["XTweet"] = None


class XReplyThread(BaseModel):
    """A conversation thread (replies chain)."""
    replies: List[XTweet] = Field(default_factory=list)
    has_more: bool = Field(default=False, description="Has ShowMore cursor")


class XTweetDetail(BaseModel):
    """Full tweet detail with replies."""
    tweet: XTweet = Field(description="The focal tweet")
    replies: List[XReplyThread] = Field(default_factory=list, description="Reply threads")
    reply_count: int = Field(default=0, description="Total replies extracted")
    cursor_bottom: Optional[str] = Field(default=None, description="Pagination cursor")
    scraped_at: datetime = Field(default_factory=datetime.now)

    model_config = {
        "json_encoders": {datetime: lambda v: v.isoformat() if v else None}
    }


class XSearchResponse(BaseModel):
    """Search response."""
    query: str
    product: str = "Top"
    tweets: List[XTweet] = Field(default_factory=list)
    cursor_top: Optional[str] = None
    cursor_bottom: Optional[str] = None
    scraped_at: datetime = Field(default_factory=datetime.now)

    model_config = {
        "json_encoders": {datetime: lambda v: v.isoformat() if v else None}
    }
