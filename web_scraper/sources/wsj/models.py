"""Data models for WSJ scraper."""
from datetime import datetime
from typing import List, Optional, Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field, computed_field


class FeedArticle(BaseModel):
    """Article from RSS feed (without full content)."""

    url: str = Field(description="Article URL")
    title: str = Field(description="Article title")
    description: str = Field(description="Article summary from RSS")
    published_at: datetime = Field(description="Publication time")
    category: str = Field(description="Feed category")
    author: Optional[str] = Field(default=None, description="Author name")
    images: List[str] = Field(default_factory=list, description="Image URLs from RSS")

    @computed_field
    @property
    def article_id(self) -> str:
        """Extract unique ID from URL."""
        path = urlparse(self.url).path
        slug = path.rstrip("/").split("/")[-1]
        return slug


class ArticleDetail(BaseModel):
    """Full article content."""

    url: str = Field(description="Article URL")
    title: str = Field(description="Article title")
    subtitle: Optional[str] = Field(default=None, description="Article subtitle/deck")
    author: Optional[str] = Field(default=None, description="Author name")
    author_url: Optional[str] = Field(default=None, description="Author profile URL")
    published_at: Optional[datetime] = Field(default=None, description="Publication time")
    published_at_raw: Optional[str] = Field(default=None, description="Raw time string")
    category: Optional[str] = Field(default=None, description="Primary category")
    subcategory: Optional[str] = Field(default=None, description="Sub-category")
    content: str = Field(default="", description="Full article text")
    paragraphs: List[str] = Field(default_factory=list, description="Content paragraphs")
    images: List[dict] = Field(default_factory=list, description="Images with src and alt")
    is_paywalled: bool = Field(default=False, description="Whether paywall was detected")
    scraped_at: datetime = Field(default_factory=datetime.now, description="Scrape time")

    @computed_field
    @property
    def article_id(self) -> str:
        """Extract unique ID from URL."""
        path = urlparse(self.url).path
        slug = path.rstrip("/").split("/")[-1]
        return slug

    model_config = {
        "json_encoders": {datetime: lambda v: v.isoformat() if v else None}
    }


class SearchResult(BaseModel):
    """Search result item."""

    url: str = Field(description="Article URL")
    headline: str = Field(description="Article headline")
    author: Optional[str] = Field(default=None, description="Author name")
    category: Optional[str] = Field(default=None, description="Category/flashline")
    image_url: Optional[str] = Field(default=None, description="Thumbnail image URL")
    timestamp: Optional[datetime] = Field(default=None, description="Publication time")

    model_config = {
        "json_encoders": {datetime: lambda v: v.isoformat() if v else None}
    }


class SearchResponse(BaseModel):
    """Search response with multiple results."""

    query: str = Field(description="Search query")
    page: int = Field(default=1, description="Current page number")
    results: List[SearchResult] = Field(default_factory=list, description="Search results")
    total_found: int = Field(default=0, description="Total results found")


class FeedResponse(BaseModel):
    """Feed response with articles."""

    category: Optional[str] = Field(default=None, description="Feed category or 'all'")
    articles: List[FeedArticle] = Field(default_factory=list, description="Articles")
    total: int = Field(default=0, description="Total articles")
