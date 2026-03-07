"""Data models for Google Custom Search source."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class GoogleSearchResult(BaseModel):
    """A single search result from Google CSE."""

    title: str = Field(description="Result title")
    url: str = Field(description="Result URL (link)")
    snippet: Optional[str] = Field(default=None, description="Text snippet")
    display_link: Optional[str] = Field(default=None, description="Display URL")
    date: Optional[str] = Field(default=None, description="Publication date if available")
    mime_type: Optional[str] = Field(default=None, description="File MIME type if not HTML")
    image_url: Optional[str] = Field(default=None, description="Thumbnail URL")
    kind: Optional[str] = Field(default=None, description="Result kind from API")


class GoogleSearchResponse(BaseModel):
    """Search response from Google CSE."""

    query: str = Field(description="Search query")
    results: List[GoogleSearchResult] = Field(default_factory=list)
    total_results: Optional[int] = Field(default=None, description="Estimated total results")
    search_time: Optional[float] = Field(default=None, description="Search time in seconds")


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
