"""Data models for Yahoo Finance source."""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class YahooQuote(BaseModel):
    """Stock/asset quote data."""
    symbol: str = Field(description="Ticker symbol")
    name: str = Field(default="", description="Company/asset name")
    quote_type: str = Field(default="", description="equity, etf, index, etc.")
    exchange: str = Field(default="", description="Exchange name")
    currency: str = Field(default="USD")
    price: Optional[float] = Field(default=None, description="Current price")
    change: Optional[float] = Field(default=None, description="Price change")
    change_percent: Optional[float] = Field(default=None, description="Change %")
    previous_close: Optional[float] = Field(default=None)
    open: Optional[float] = Field(default=None)
    day_high: Optional[float] = Field(default=None)
    day_low: Optional[float] = Field(default=None)
    volume: Optional[int] = Field(default=None)
    avg_volume: Optional[int] = Field(default=None)
    market_cap: Optional[int] = Field(default=None)
    pe_ratio: Optional[float] = Field(default=None, description="P/E ratio")
    eps: Optional[float] = Field(default=None, description="Earnings per share")
    dividend_yield: Optional[float] = Field(default=None)
    fifty_two_week_high: Optional[float] = Field(default=None)
    fifty_two_week_low: Optional[float] = Field(default=None)
    market_state: Optional[str] = Field(default=None, description="PRE, REGULAR, POST, CLOSED")


class YahooSearchResult(BaseModel):
    """Search result item."""
    symbol: str
    name: str = ""
    quote_type: str = ""
    exchange: str = ""
    score: Optional[float] = None


class YahooNews(BaseModel):
    """News article from Yahoo Finance."""
    title: str
    url: str
    publisher: str = ""
    published_at: Optional[int] = Field(default=None, description="Unix timestamp")
    thumbnail: Optional[str] = None
    related_tickers: List[str] = Field(default_factory=list)


class YahooSearchResponse(BaseModel):
    """Combined search response."""
    query: str
    quotes: List[YahooSearchResult] = Field(default_factory=list)
    news: List[YahooNews] = Field(default_factory=list)
    scraped_at: datetime = Field(default_factory=datetime.now)
