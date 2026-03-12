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

    url: str = Field(description="Canonical video URL")
    aweme_id: str = Field(description="Video ID extracted from URL or ID")
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


class DouyinVideoInfo(BaseModel):
    """Resolved video metadata for a Douyin aweme."""

    aweme_id: str = Field(description="Video ID")
    desc: Optional[str] = Field(default=None, description="Video description")
    author_name: Optional[str] = Field(default=None, description="Author nickname")
    duration_ms: Optional[int] = Field(default=None, description="Duration in milliseconds")
    width: Optional[int] = Field(default=None, description="Video width")
    height: Optional[int] = Field(default=None, description="Video height")
    play_urls: List[str] = Field(default_factory=list, description="Playable video URLs")
    download_urls: List[str] = Field(default_factory=list, description="Download video URLs")
    cover_url: Optional[str] = Field(default=None, description="Cover image URL")
    source: str = Field(default="embedded_json", description="Metadata extraction method")


class DouyinUserProfile(BaseModel):
    """Full user profile from /aweme/v1/web/user/profile/other/ API."""

    uid: Optional[str] = Field(default=None, description="User numeric ID")
    sec_uid: Optional[str] = Field(default=None, description="Encrypted user ID")
    unique_id: Optional[str] = Field(default=None, description="Custom Douyin ID")
    nickname: Optional[str] = Field(default=None, description="Display name")
    signature: Optional[str] = Field(default=None, description="Bio / signature")
    avatar_url: Optional[str] = Field(default=None, description="Avatar thumbnail URL")
    avatar_larger_url: Optional[str] = Field(default=None, description="Avatar large URL")
    cover_url: Optional[str] = Field(default=None, description="Profile background cover URL")
    gender: Optional[int] = Field(default=None, description="Gender: 0=unset, 1=male, 2=female")
    city: Optional[str] = Field(default=None, description="City")
    province: Optional[str] = Field(default=None, description="Province")
    country: Optional[str] = Field(default=None, description="Country")
    ip_location: Optional[str] = Field(default=None, description="IP location label")
    school_name: Optional[str] = Field(default=None, description="School name")
    aweme_count: Optional[int] = Field(default=None, description="Total video count")
    follower_count: Optional[int] = Field(default=None, description="Follower count")
    following_count: Optional[int] = Field(default=None, description="Following count")
    total_favorited: Optional[int] = Field(default=None, description="Total likes received")
    favoriting_count: Optional[int] = Field(default=None, description="Videos liked by user")
    dongtai_count: Optional[int] = Field(default=None, description="Dongtai (dynamic) count")
    mix_count: Optional[int] = Field(default=None, description="Collection/mix count")
    verification_type: Optional[int] = Field(default=None, description="0=none, 1=personal, 2=enterprise")
    custom_verify: Optional[str] = Field(default=None, description="Custom verification text")
    enterprise_verify_reason: Optional[str] = Field(default=None, description="Enterprise verification reason")
    is_star: Optional[bool] = Field(default=None, description="Whether star creator")
    live_status: Optional[int] = Field(default=None, description="0=offline, 1=live")
    room_id: Optional[str] = Field(default=None, description="Live room ID")
    secret: Optional[int] = Field(default=None, description="0=public, 1=private account")
    show_favorite_list: Optional[bool] = Field(default=None, description="Whether favorite list is public")
    share_url: Optional[str] = Field(default=None, description="Share URL")


class DouyinVideoStatistics(BaseModel):
    """Video statistics."""

    digg_count: Optional[int] = Field(default=None, description="Like count")
    comment_count: Optional[int] = Field(default=None, description="Comment count")
    share_count: Optional[int] = Field(default=None, description="Share count")
    collect_count: Optional[int] = Field(default=None, description="Favorite/collect count")


class DouyinVideoItem(BaseModel):
    """A single video item from user's post list."""

    aweme_id: str = Field(description="Video ID")
    url: str = Field(description="Canonical Douyin video URL")
    desc: Optional[str] = Field(default=None, description="Video description")
    create_time: Optional[int] = Field(default=None, description="Publish time (unix timestamp)")
    duration: Optional[int] = Field(default=None, description="Duration in milliseconds")
    author_name: Optional[str] = Field(default=None, description="Author nickname")
    author_sec_uid: Optional[str] = Field(default=None, description="Author sec_uid")
    statistics: Optional[DouyinVideoStatistics] = Field(default=None, description="Video statistics")
    cover_url: Optional[str] = Field(default=None, description="Cover image URL")
    share_url: Optional[str] = Field(default=None, description="Share URL")
    is_top: Optional[bool] = Field(default=None, description="Whether pinned to top")
    aweme_type: Optional[int] = Field(default=None, description="0=video, 4=image post")
    media_type: Optional[int] = Field(default=None, description="4=video, 2=image post")


class DouyinProfileResponse(BaseModel):
    """Response for user profile fetch."""

    url: str = Field(description="Input user page URL")
    sec_uid: str = Field(description="User sec_uid")
    profile: DouyinUserProfile = Field(description="User profile data")
    method: str = Field(default="playwright_intercept", description="Fetch method")
    scraped_at: datetime = Field(default_factory=datetime.now, description="Scrape timestamp")

    model_config = {
        "json_encoders": {
            datetime: lambda v: v.isoformat() if v else None,
        }
    }


class DouyinVideosResponse(BaseModel):
    """Response for user video list fetch."""

    url: str = Field(description="Input user page URL")
    sec_uid: str = Field(description="User sec_uid")
    author_name: Optional[str] = Field(default=None, description="Author nickname")
    total_videos: Optional[int] = Field(default=None, description="Total video count from profile")
    videos: List[DouyinVideoItem] = Field(default_factory=list, description="Fetched videos")
    fetched_count: int = Field(default=0, description="Number of videos fetched")
    pages_fetched: int = Field(default=0, description="Number of API pages intercepted")
    has_more: bool = Field(default=False, description="Whether more videos are available")
    method: str = Field(default="playwright_intercept", description="Fetch method")
    scraped_at: datetime = Field(default_factory=datetime.now, description="Scrape timestamp")

    model_config = {
        "json_encoders": {
            datetime: lambda v: v.isoformat() if v else None,
        }
    }


class DouyinVideoDownloadResponse(BaseModel):
    """Response payload for a Douyin video download."""

    url: str = Field(description="Canonical video URL")
    aweme_id: str = Field(description="Video ID extracted from URL or ID")
    desc: Optional[str] = Field(default=None, description="Video description")
    author_name: Optional[str] = Field(default=None, description="Author nickname")
    video_url: str = Field(description="Resolved video CDN URL")
    output_path: str = Field(description="Saved local file path")
    metadata_path: str = Field(description="Saved local metadata JSON path")
    file_size: int = Field(default=0, description="Downloaded file size in bytes")
    duration_ms: Optional[int] = Field(default=None, description="Duration in milliseconds")
    method: str = Field(default="embedded_json", description="Resolution method")
    skipped: bool = Field(default=False, description="Whether existing files were reused")
    attempts: int = Field(default=1, description="Number of attempts performed")
    downloaded_at: datetime = Field(default_factory=datetime.now, description="Download timestamp")

    model_config = {
        "json_encoders": {
            datetime: lambda v: v.isoformat() if v else None,
        }
    }
