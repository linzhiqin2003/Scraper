"""Pydantic data models for Reuters scraper."""

from typing import List, Optional

from pydantic import BaseModel, Field


class SearchResult(BaseModel):
    """A single search result item."""

    title: str = Field(description="Article title")
    summary: Optional[str] = Field(default=None, description="Article summary/snippet")
    url: str = Field(description="Article URL (relative or absolute)")
    published_at: Optional[str] = Field(default=None, description="Publication timestamp")
    category: Optional[str] = Field(default=None, description="Article category/section")
    author: Optional[str] = Field(default=None, description="Article author(s)")
    thumbnail: Optional[str] = Field(default=None, description="Thumbnail image URL")


class ArticleImage(BaseModel):
    """An image within an article."""

    url: str = Field(description="Image URL")
    caption: Optional[str] = Field(default=None, description="Image caption")


class Article(BaseModel):
    """A full article with content."""

    title: str = Field(description="Article title")
    url: str = Field(description="Article URL")
    author: Optional[str] = Field(default=None, description="Article author(s)")
    published_at: Optional[str] = Field(default=None, description="Publication timestamp")
    content_markdown: str = Field(description="Article body in Markdown format")
    images: List[ArticleImage] = Field(default_factory=list, description="Article images")
    tags: List[str] = Field(default_factory=list, description="Article tags/topics")


class SectionInfo(BaseModel):
    """Information about a Reuters section/category."""

    name: str = Field(description="Display name of the section")
    slug: str = Field(description="URL slug for the section")
    url: str = Field(description="Full URL path to the section")


class SectionArticle(BaseModel):
    """An article item from a section listing."""

    title: str = Field(description="Article title")
    summary: Optional[str] = Field(default=None, description="Article summary")
    url: str = Field(description="Article URL")
    published_at: Optional[str] = Field(default=None, description="Publication timestamp")
    thumbnail_url: Optional[str] = Field(default=None, description="Thumbnail image URL")
