"""Data models for Google Scholar scraper."""
import re
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, computed_field


class ScholarResult(BaseModel):
    """A single search result from Google Scholar."""

    title: str = Field(description="Paper title")
    url: Optional[str] = Field(default=None, description="Link to the paper/publisher page")
    authors: Optional[str] = Field(default=None, description="Authors string (e.g. 'J Smith, A Lee - Journal, 2023')")
    snippet: Optional[str] = Field(default=None, description="Text snippet / abstract preview")
    cited_by_count: Optional[int] = Field(default=None, description="Number of citations")
    cited_by_url: Optional[str] = Field(default=None, description="URL to citing articles")
    year: Optional[int] = Field(default=None, description="Publication year")
    pdf_url: Optional[str] = Field(default=None, description="Direct PDF link if available")
    source: Optional[str] = Field(default=None, description="Journal/conference/publisher name")
    is_citation: bool = Field(default=False, description="Whether this is a [CITATION] entry (no link)")

    @computed_field
    @property
    def has_pdf(self) -> bool:
        """Whether a PDF link is available."""
        return self.pdf_url is not None


class ScholarSearchResponse(BaseModel):
    """Search response from Google Scholar."""

    query: str = Field(description="Search query")
    results: List[ScholarResult] = Field(default_factory=list, description="Search results")
    total_results: Optional[int] = Field(default=None, description="Approximate total results (from Scholar)")
    page: int = Field(default=1, description="Current page number")
    has_next_page: bool = Field(default=False, description="Whether more pages are available")


class ScholarArticle(BaseModel):
    """Full article content fetched from publisher page."""

    url: str = Field(description="Article URL")
    title: Optional[str] = Field(default=None, description="Article title")
    authors: List[str] = Field(default_factory=list, description="Author names")
    abstract: Optional[str] = Field(default=None, description="Article abstract")
    content: Optional[str] = Field(default=None, description="Full article content in markdown")
    doi: Optional[str] = Field(default=None, description="DOI identifier")
    journal: Optional[str] = Field(default=None, description="Journal name")
    published_date: Optional[str] = Field(default=None, description="Publication date string")
    is_accessible: bool = Field(default=True, description="Whether full content was accessible")
    is_pdf: bool = Field(default=False, description="Whether URL points to a PDF")
    scraped_at: datetime = Field(default_factory=datetime.now, description="Scrape timestamp")

    model_config = {
        "json_encoders": {datetime: lambda v: v.isoformat() if v else None}
    }
