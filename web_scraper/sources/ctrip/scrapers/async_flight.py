"""Async flight low-price calendar scraper."""

from __future__ import annotations

from pathlib import Path

import httpx

from ....core.rate_limiter import AsyncRateLimiter, RateLimiterConfig
from ..config import (
    CTRIP_RATE_LIMIT,
    FLIGHT_DEFAULT_HEADERS,
    FLIGHT_LOWEST_PRICE_URL,
    normalize_flight_city,
)
from ..cookies import get_cookies_path, load_cookies
from ..models import FlightCalendarPrice
from .flight import _parse_ctrip_json_date, _sort_calendar_prices


class AsyncFlightLowPriceScraper:
    """Async version of FlightLowPriceScraper."""

    def __init__(self, cookies_path: Path | None = None):
        path = cookies_path or get_cookies_path()
        self.cookies = load_cookies(path) if path.exists() else httpx.Cookies()
        self._rate_limiter = AsyncRateLimiter(RateLimiterConfig(**CTRIP_RATE_LIMIT))

    async def search(
        self, departure_city: str, arrival_city: str, departure_date: str
    ) -> list[FlightCalendarPrice]:
        """Async low-price calendar search."""
        depart_code, _ = normalize_flight_city(departure_city)
        arrive_code, _ = normalize_flight_city(arrival_city)
        payload = {
            "departNewCityCode": depart_code,
            "arriveNewCityCode": arrive_code,
            "startDate": departure_date,
            "grade": 15,
            "flag": 0,
            "channelName": "FlightOnline",
            "searchType": 1,
            "passengerList": [{"passengercount": 1, "passengertype": "Adult"}],
            "calendarSelections": [{"selectionType": 8, "selectionContent": ["15"]}],
        }

        await self._rate_limiter.wait()
        try:
            async with httpx.AsyncClient(
                cookies=self.cookies, follow_redirects=True, timeout=20
            ) as client:
                resp = await client.post(
                    FLIGHT_LOWEST_PRICE_URL, json=payload, headers=FLIGHT_DEFAULT_HEADERS
                )
                resp.raise_for_status()
                data = resp.json()
                self._rate_limiter.record_success()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                self._rate_limiter.record_rate_limit()
            raise

        ack = data.get("responseStatus", {}).get("Ack")
        if ack != "Success":
            raise RuntimeError("获取机票低价日历失败")

        prices: list[FlightCalendarPrice] = []
        for item in data.get("priceList", []):
            date = _parse_ctrip_json_date(item.get("departDate"))
            if not date:
                continue
            prices.append(
                FlightCalendarPrice(
                    date=date,
                    price=item.get("price"),
                    total_price=item.get("totalPrice"),
                    transport_price=item.get("transportPrice"),
                    discount_label="低价" if item.get("flag") == 1 else None,
                    direct_label=item.get("directCalendarText") or None,
                )
            )
        return _sort_calendar_prices(prices)
