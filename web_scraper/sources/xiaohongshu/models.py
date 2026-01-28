"""Data models for Xiaohongshu content."""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class Author(BaseModel):
    """Author/User basic information."""

    user_id: str = Field(..., description="User ID")
    nickname: str = Field(..., description="User nickname")
    avatar: str = Field(default="", description="Avatar URL")


class NoteCard(BaseModel):
    """Note card information from explore/search page."""

    note_id: str = Field(..., description="Note ID")
    title: str = Field(..., description="Note title")
    cover_url: str = Field(default="", description="Cover image URL")
    author: Author = Field(..., description="Author information")
    likes: int = Field(default=0, description="Number of likes")
    xsec_token: str = Field(default="", description="Security token for accessing note")
    note_type: str = Field(default="normal", description="Note type: normal/video")


class Note(BaseModel):
    """Full note information."""

    note_id: str = Field(..., description="Note ID")
    title: str = Field(..., description="Note title")
    content: str = Field(default="", description="Note content/description")
    images: List[str] = Field(default_factory=list, description="Image URLs")
    video_url: Optional[str] = Field(default=None, description="Video URL if exists")
    tags: List[str] = Field(default_factory=list, description="Hashtags")
    publish_time: Optional[datetime] = Field(default=None, description="Publish time")
    author: Author = Field(..., description="Author information")
    likes: int = Field(default=0, description="Number of likes")
    comments_count: int = Field(default=0, description="Number of comments")
    collects: int = Field(default=0, description="Number of collections")
    shares: int = Field(default=0, description="Number of shares")


class User(BaseModel):
    """Full user profile information."""

    user_id: str = Field(..., description="User ID")
    nickname: str = Field(..., description="User nickname")
    avatar: str = Field(default="", description="Avatar URL")
    description: str = Field(default="", description="User bio/description")
    gender: Optional[str] = Field(default=None, description="Gender")
    ip_location: Optional[str] = Field(default=None, description="IP location")
    followers: int = Field(default=0, description="Number of followers")
    following: int = Field(default=0, description="Number of following")
    likes: int = Field(default=0, description="Total likes received")
    notes_count: int = Field(default=0, description="Number of notes")


class Comment(BaseModel):
    """Comment information."""

    comment_id: str = Field(..., description="Comment ID")
    content: str = Field(..., description="Comment content")
    author: Author = Field(..., description="Comment author")
    likes: int = Field(default=0, description="Number of likes")
    create_time: Optional[datetime] = Field(default=None, description="Comment time")
    sub_comments: List["Comment"] = Field(
        default_factory=list, description="Sub-comments/replies"
    )


class SearchResult(BaseModel):
    """Search result containing notes."""

    keyword: str = Field(..., description="Search keyword")
    total: int = Field(default=0, description="Total results count")
    notes: List[NoteCard] = Field(default_factory=list, description="Note cards")


class ExploreResult(BaseModel):
    """Explore page result."""

    category: str = Field(default="推荐", description="Category name")
    notes: List[NoteCard] = Field(default_factory=list, description="Note cards")
