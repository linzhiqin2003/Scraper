"""Data models for Zhihu scraper."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, computed_field


class SearchResult(BaseModel):
    """A single search result item."""

    title: str = Field(description="Content title")
    url: str = Field(description="Content URL")
    content_type: str = Field(default="answer", description="Type: answer, article, question, video")
    excerpt: str = Field(default="", description="Content excerpt/snippet")
    author: Optional[str] = Field(default=None, description="Author name")
    author_url: Optional[str] = Field(default=None, description="Author profile URL")
    upvotes: Optional[int] = Field(default=None, description="Upvote count")
    comments: Optional[int] = Field(default=None, description="Comment count")
    created_at: Optional[str] = Field(default=None, description="Creation time")
    # API-enriched fields
    follower_count: Optional[int] = Field(default=None, description="Author follower count (API)")
    view_count: Optional[int] = Field(default=None, description="View count (API)")
    answer_count: Optional[int] = Field(default=None, description="Answer count for questions (API)")
    data_source: str = Field(default="dom", description="Data source: dom, api_intercept, api_direct, pure_api")

    @computed_field
    @property
    def content_id(self) -> str:
        """Extract content ID from URL."""
        # https://www.zhihu.com/question/123/answer/456 -> "q123_a456"
        # https://zhuanlan.zhihu.com/p/789 -> "p789"
        url = self.url.rstrip("/")
        if "/answer/" in url:
            parts = url.split("/")
            try:
                q_idx = parts.index("question") + 1
                a_idx = parts.index("answer") + 1
                return f"q{parts[q_idx]}_a{parts[a_idx]}"
            except (ValueError, IndexError):
                pass
        if "/p/" in url:
            slug = url.split("/p/")[-1]
            return f"p{slug}"
        return url.split("/")[-1]


class SearchResponse(BaseModel):
    """Search response with multiple results."""

    query: str = Field(description="Search query")
    search_type: str = Field(default="content", description="Search type")
    results: List[SearchResult] = Field(default_factory=list, description="Search results")
    total: int = Field(default=0, description="Total results count")


class ArticleDetail(BaseModel):
    """Full article/answer content."""

    url: str = Field(description="Content URL")
    title: str = Field(description="Title")
    content: str = Field(default="", description="Full content text")
    author: Optional[str] = Field(default=None, description="Author name")
    author_url: Optional[str] = Field(default=None, description="Author profile URL")
    upvotes: Optional[int] = Field(default=None, description="Upvote count")
    comments: Optional[int] = Field(default=None, description="Comment count")
    created_at: Optional[str] = Field(default=None, description="Creation time")
    updated_at: Optional[str] = Field(default=None, description="Last update time")
    tags: List[str] = Field(default_factory=list, description="Content tags")
    images: List[str] = Field(default_factory=list, description="Image URLs")
    content_type: str = Field(default="article", description="Type: article, answer")
    question_title: Optional[str] = Field(default=None, description="Parent question title (for answers)")
    scraped_at: datetime = Field(default_factory=datetime.now, description="Scrape time")
    # API-enriched fields
    follower_count: Optional[int] = Field(default=None, description="Author follower count (API)")
    view_count: Optional[int] = Field(default=None, description="View count (API)")
    answer_count: Optional[int] = Field(default=None, description="Answer count for questions (API)")
    data_source: str = Field(default="dom", description="Data source: dom, api_intercept, api_direct, pure_api")

    model_config = {
        "json_encoders": {datetime: lambda v: v.isoformat() if v else None}
    }
