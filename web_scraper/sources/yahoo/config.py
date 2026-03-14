"""Configuration for Yahoo Finance source."""

SOURCE_NAME = "yahoo"

# Yahoo Finance API endpoints (no key required, cookie+crumb auth)
SEARCH_URL = "https://query2.finance.yahoo.com/v1/finance/search"
QUOTE_URL = "https://query1.finance.yahoo.com/v7/finance/quote"
CHART_URL = "https://query2.finance.yahoo.com/v8/finance/chart"
CRUMB_URL = "https://query1.finance.yahoo.com/v1/test/getcrumb"

# Search result types
QUOTE_TYPES = {
    "equity": "Stock",
    "etf": "ETF",
    "mutualfund": "Mutual Fund",
    "index": "Index",
    "currency": "Currency",
    "future": "Future",
    "cryptocurrency": "Crypto",
    "option": "Option",
}

# Chart periods
CHART_PERIODS = ["1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"]

# Chart intervals
CHART_INTERVALS = ["1m", "5m", "15m", "1h", "1d", "1wk", "1mo"]
