"""Async hotel API scraper for concurrent operations."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

import httpx

from ....core.rate_limiter import AsyncRateLimiter, RateLimiterConfig
from ..config import (
    BRAND_FILTERS,
    CITY_MAP,
    CTRIP_RATE_LIMIT,
    DEFAULT_HEADERS,
    HOTEL_AD_URL,
    HOTEL_BROWSE_URL,
    HOTEL_CITY_URL,
    HOTEL_DETAIL_URL,
    HOTEL_SEARCH_URL,
    PRICE_RANGE_FILTERS,
    SORT_FILTERS,
    STAR_FILTERS,
    hotel_head,
)
from ..cookies import get_cookies_path, get_guid, load_cookies
from ..models import HotelCard, HotelCity, HotelSearchResult
from .hotel import HotelApiScraper  # reuse _parse_hotel and _build_filters

logger = logging.getLogger(__name__)


class AsyncHotelApiScraper:
    """Async version of HotelApiScraper for concurrent hotel operations."""

    PAGE_SIZE = 10

    def __init__(self, cookies_path: Path | None = None):
        path = cookies_path or get_cookies_path()
        if path and path.exists():
            self.cookies = load_cookies(path)
            self._guid = get_guid(self.cookies)
        else:
            self.cookies = httpx.Cookies()
            self._guid = ""
        self._rate_limiter = AsyncRateLimiter(RateLimiterConfig(**CTRIP_RATE_LIMIT))

    async def _post(self, url: str, payload: dict) -> dict:
        await self._rate_limiter.wait()
        headers = {
            **DEFAULT_HEADERS,
            "referer": "https://hotels.ctrip.com/",
            "origin": "https://hotels.ctrip.com",
        }
        try:
            async with httpx.AsyncClient(
                cookies=self.cookies, follow_redirects=True, timeout=15
            ) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                result = resp.json()
                self._rate_limiter.record_success()
                return result
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                self._rate_limiter.record_rate_limit()
            raise

    def _hotel_head(self, checkin: str = "", checkout: str = "") -> dict:
        return hotel_head(self._guid, checkin, checkout)

    async def search(
        self,
        city_name: str,
        checkin: str,
        checkout: str,
        adult: int = 1,
        rooms: int = 1,
        limit: int = 20,
        sort: str = "popular",
        stars: list[int] | None = None,
        breakfast: bool = False,
        free_cancel: bool = False,
        price_min: int | None = None,
        price_max: int | None = None,
        keyword: str = "",
        brands: list[str] | None = None,
    ) -> HotelSearchResult:
        """Async hotel search via fetchHotelList API."""
        city_info = CITY_MAP.get(city_name)
        if city_info is None:
            raise ValueError(
                f"不支持的城市：{city_name}。"
                f"支持：{', '.join(CITY_MAP.keys())}"
            )
        city_id, country_id, _ = city_info

        filters = HotelApiScraper._build_filters(
            sort, stars, breakfast, free_cancel, price_min, price_max, brands
        )
        hotels: List[HotelCard] = []
        session_id = ""
        shown_ids: list[str] = []
        page = 1

        while len(hotels) < limit:
            payload = {
                "destination": {
                    "type": 1,
                    "geo": {
                        "cityId": city_id,
                        "countryId": country_id,
                        "provinceId": 0,
                        "districtId": 0,
                    },
                    "keyword": {"word": keyword},
                },
                "checkInfo": {"checkIn": checkin, "checkOut": checkout},
                "guest": {"adult": adult, "children": 0, "ages": "", "roomsNum": rooms},
                "paging": {
                    "pageIndex": page,
                    "pageSize": self.PAGE_SIZE,
                    "pageCode": "",
                },
                "filters": filters,
                "extraFilter": {
                    "ctripMainLandBDCoordinate": True,
                    "sessionId": session_id,
                    "extendableParams": {"tripWalkDriveSwitch": "T"},
                },
                "hotelIdFilter": {"hotelAldyShown": shown_ids},
                "head": self._hotel_head(checkin, checkout),
            }

            data = (await self._post(HOTEL_SEARCH_URL, payload)).get("data", {})
            extra = data.get("hotelListAddtionInfo", {})

            for item in data.get("hotelList", []):
                card = HotelApiScraper._parse_hotel(item, city_id, checkin, checkout)
                if card:
                    hotels.append(card)
                    shown_ids.append(card.hotel_id)

            session_id = extra.get("sessionId", session_id)
            if extra.get("isLastPage", True):
                break
            page += 1

        return HotelSearchResult(
            city_id=city_id,
            city_name=city_name,
            checkin=checkin,
            checkout=checkout,
            hotels=hotels[:limit],
        )

    async def get_recommendations(
        self,
        city_id: int,
        checkin: str,
        checkout: str,
        positions: list[str] | None = None,
    ) -> List[HotelCard]:
        """Async version of get_recommendations."""
        if positions is None:
            positions = ["HTL_LST_002", "HTL_LST_001", "HTL_LST_003"]

        head = self._hotel_head(checkin, checkout)
        head["extension"].append({"name": "cityId", "value": str(city_id)})

        payload = {"cityId": city_id, "adPositionCodes": positions, "head": head}
        data = await self._post(HOTEL_AD_URL, payload)

        hotels: List[HotelCard] = []
        for ad in data.get("data", {}).get("adList", []):
            for h in ad.get("hotels", []):
                base = h.get("base", {})
                comment = h.get("comment", {})
                money = h.get("money", {})
                hotel_id = str(base.get("hotelId", ""))
                hotels.append(
                    HotelCard(
                        hotel_id=hotel_id,
                        name=base.get("hotelName", ""),
                        score=comment.get("score"),
                        score_desc=comment.get("description"),
                        comment_num=comment.get("number"),
                        price=money.get("price"),
                        free_cancel=not money.get("soldOut", False),
                        is_ad=True,
                        detail_url=(
                            f"{HOTEL_DETAIL_URL}?hotelId={hotel_id}&cityId={city_id}"
                            f"&checkIn={checkin}&checkOut={checkout}"
                        )
                        if hotel_id
                        else None,
                    )
                )
        return hotels

    async def get_cities(self, checkin: str = "", checkout: str = "") -> List[HotelCity]:
        """Async version of get_cities."""
        head = self._hotel_head(checkin, checkout)
        payload = {"requestType": "5", "head": head}
        data = await self._post(HOTEL_CITY_URL, payload)

        cities: List[HotelCity] = []
        inland = data.get("data", {}).get("inlandCityModel", {})
        for group in inland.get("cityModelGroups", []):
            group_name = group.get("displayControlModel", {}).get("fullName", "")
            for region in group.get("regionModels", []):
                basic = region.get("basicCityModel", {})
                display = region.get("displayCityModel", {})
                cities.append(
                    HotelCity(
                        city_id=basic.get("cityId", 0),
                        city_name=display.get("destinationName", ""),
                        country_id=basic.get("countryId", 1),
                        group_name=group_name,
                    )
                )
        return cities
