"""Pydantic models for Sina news search."""

from typing import List, Optional

from pydantic import BaseModel, Field


class SinaSearchResult(BaseModel):
    """A single Sina search result."""

    title: str = Field(description="Article title")
    url: str = Field(description="Article URL")
    snippet: Optional[str] = Field(default=None, description="Search result snippet")
    source_name: Optional[str] = Field(default=None, description="Publisher/source label")
    published_at: Optional[str] = Field(default=None, description="Published timestamp")
    image_url: Optional[str] = Field(default=None, description="Thumbnail URL")


class SinaSearchResponse(BaseModel):
    """Search response metadata and items."""

    query: str = Field(description="Original search query")
    start_time: str = Field(description="Start time used in the query")
    end_time: str = Field(description="End time used in the query")
    total_results: Optional[int] = Field(default=None, description="Total results reported by Sina")
    fetched_pages: int = Field(default=0, description="Number of pages fetched")
    results: List[SinaSearchResult] = Field(default_factory=list, description="Collected results")

