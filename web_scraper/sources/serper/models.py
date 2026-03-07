"""Data models for Serper search source."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class SerperSearchResult(BaseModel):
    """A single search result from Serper API."""

    title: str = Field(description="Result title")
    url: str = Field(description="Result URL")
    snippet: Optional[str] = Field(default=None, description="Text snippet")
    position: Optional[int] = Field(default=None, description="Position in search results")
    date: Optional[str] = Field(default=None, description="Publication date (news only)")
    source: Optional[str] = Field(default=None, description="Source domain (news only)")
    image_url: Optional[str] = Field(default=None, description="Thumbnail image URL")


class SerperSearchResponse(BaseModel):
    """Search response from Serper API."""

    query: str = Field(description="Search query")
    search_type: str = Field(default="search", description="Search type: search, news")
    results: List[SerperSearchResult] = Field(default_factory=list)
    knowledge_graph: Optional[dict] = Field(default=None, description="Knowledge graph data if available")
    answer_box: Optional[dict] = Field(default=None, description="Answer box if available")
    credits_used: Optional[int] = Field(default=None, description="API credits used")


class WebArticle(BaseModel):
    """Generic web article fetched from a URL."""

    url: str = Field(description="Article URL")
    title: Optional[str] = Field(default=None, description="Article title")
    content: Optional[str] = Field(default=None, description="Full content in markdown")
    published_date: Optional[str] = Field(default=None, description="Publication date")
    is_accessible: bool = Field(default=True, description="Whether content was accessible")
    is_pdf: bool = Field(default=False, description="Whether URL points to a PDF")
    scraped_at: datetime = Field(default_factory=datetime.now, description="Scrape timestamp")

    model_config = {
        "json_encoders": {datetime: lambda v: v.isoformat() if v else None}
    }
