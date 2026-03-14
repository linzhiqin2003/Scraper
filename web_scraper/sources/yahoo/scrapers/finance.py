"""Yahoo Finance scraper — search, quotes, and news via Yahoo's public API."""
import logging
from typing import List, Optional

from curl_cffi import requests as cffi_requests

from ..config import CRUMB_URL, QUOTE_URL, SEARCH_URL
from ..models import (
    YahooNews,
    YahooQuote,
    YahooSearchResponse,
    YahooSearchResult,
)

logger = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class FinanceScraper:
    """Yahoo Finance API client (cookie+crumb auth, no API key needed).

    Uses curl-cffi Session to maintain cookie jar across requests.
    """

    def __init__(self):
        self._session = cffi_requests.Session(
            impersonate="chrome131",
            timeout=30,
        )
        self._crumb: Optional[str] = None

    def _ensure_crumb(self) -> str:
        """Fetch session cookie + crumb token."""
        if self._crumb:
            return self._crumb

        # Step 1: Visit Yahoo Finance to get session cookies
        self._session.get("https://finance.yahoo.com/quote/AAPL/")

        # Step 2: Get crumb (cookies are auto-maintained by Session)
        resp = self._session.get(CRUMB_URL)
        if resp.status_code != 200:
            raise RuntimeError(f"Failed to get crumb: HTTP {resp.status_code}")
        self._crumb = resp.text.strip()
        return self._crumb

    def search(
        self,
        query: str,
        max_results: int = 10,
        news_count: int = 5,
    ) -> YahooSearchResponse:
        """Search for tickers, companies, and related news."""
        resp = self._session.get(
            SEARCH_URL,
            params={
                "q": query,
                "quotesCount": str(max_results),
                "newsCount": str(news_count),
                "enableFuzzyQuery": "true",
                "quotesQueryId": "tss_match_phrase_query",
            },
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Yahoo Search: HTTP {resp.status_code}")
        data = resp.json()

        quotes = []
        for q in data.get("quotes", []):
            quotes.append(YahooSearchResult(
                symbol=q.get("symbol", ""),
                name=q.get("shortname") or q.get("longname", ""),
                quote_type=q.get("quoteType", "").lower(),
                exchange=q.get("exchDisp", ""),
                score=q.get("score"),
            ))

        news = []
        for n in data.get("news", []):
            thumbnail = None
            thumbs = n.get("thumbnail", {}).get("resolutions", [])
            if thumbs:
                thumbnail = thumbs[0].get("url")

            news.append(YahooNews(
                title=n.get("title", ""),
                url=n.get("link", ""),
                publisher=n.get("publisher", ""),
                published_at=n.get("providerPublishTime"),
                thumbnail=thumbnail,
                related_tickers=n.get("relatedTickers", []),
            ))

        return YahooSearchResponse(query=query, quotes=quotes, news=news)

    def quote(self, symbols: List[str]) -> List[YahooQuote]:
        """Get real-time quotes for one or more symbols."""
        crumb = self._ensure_crumb()
        resp = self._session.get(
            QUOTE_URL,
            params={
                "symbols": ",".join(symbols),
                "crumb": crumb,
            },
        )
        if resp.status_code == 401:
            # Crumb expired, retry with fresh session
            self._crumb = None
            self._session.cookies.clear()
            crumb = self._ensure_crumb()
            resp = self._session.get(
                QUOTE_URL,
                params={"symbols": ",".join(symbols), "crumb": crumb},
            )
        if resp.status_code != 200:
            raise RuntimeError(f"Yahoo Quote: HTTP {resp.status_code}")
        data = resp.json()

        results = []
        for q in data.get("quoteResponse", {}).get("result", []):
            results.append(YahooQuote(
                symbol=q.get("symbol", ""),
                name=q.get("shortName") or q.get("longName", ""),
                quote_type=q.get("quoteType", "").lower(),
                exchange=q.get("fullExchangeName", ""),
                currency=q.get("currency", "USD"),
                price=q.get("regularMarketPrice"),
                change=q.get("regularMarketChange"),
                change_percent=q.get("regularMarketChangePercent"),
                previous_close=q.get("regularMarketPreviousClose"),
                open=q.get("regularMarketOpen"),
                day_high=q.get("regularMarketDayHigh"),
                day_low=q.get("regularMarketDayLow"),
                volume=q.get("regularMarketVolume"),
                avg_volume=q.get("averageDailyVolume3Month"),
                market_cap=q.get("marketCap"),
                pe_ratio=q.get("trailingPE"),
                eps=q.get("epsTrailingTwelveMonths"),
                dividend_yield=q.get("dividendYield"),
                fifty_two_week_high=q.get("fiftyTwoWeekHigh"),
                fifty_two_week_low=q.get("fiftyTwoWeekLow"),
                market_state=q.get("marketState"),
            ))

        return results

    def news(self, query: str, count: int = 10) -> List[YahooNews]:
        """Get financial news for a query or ticker."""
        resp = self.search(query, max_results=0, news_count=count)
        return resp.news
