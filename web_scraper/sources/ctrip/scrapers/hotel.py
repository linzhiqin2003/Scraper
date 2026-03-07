"""Ctrip hotel scrapers.

- HotelSearchScraper: Playwright response interception for fetchHotelList
  (bypasses phantom-token anti-bot protection).
- HotelApiScraper: pure httpx for recommendations, browse history, city list, filters.
"""
from __future__ import annotations

import json
import logging
import re
import threading
from pathlib import Path
from typing import List, Optional

import httpx

from ..config import (
    CITY_MAP,
    DEFAULT_HEADERS,
    HOTEL_AD_URL,
    HOTEL_BROWSE_URL,
    HOTEL_CITY_URL,
    HOTEL_DETAIL_URL,
    HOTEL_FILTER_URL,
    HOTEL_LIST_URL,
    HOTEL_SEARCH_URL,
    PRICE_RANGE_FILTERS,
    SORT_FILTERS,
    STAR_FILTERS,
    hotel_head,
)
from ..cookies import get_cookies_path, get_guid, load_cookies, load_playwright_cookies
from ..models import HotelCard, HotelCity, HotelSearchResult

logger = logging.getLogger(__name__)


class HotelSearchScraper:
    """Hotel search via Playwright response interception.

    Navigates to hotels.ctrip.com/hotels/list and captures fetchHotelList XHR
    responses, completely bypassing the phantom-token anti-bot protection.
    Cookies are optional but improve result quality.
    """

    # URL sort param mapping (matches SORT_FILTERS values)
    _SORT_URL_MAP = {
        "popular": "1", "smart": "9", "score": "6",
        "price_asc": "3", "price_desc": "4", "distance": "5", "star": "14",
    }

    def __init__(self, cookies_path: Path | None = None) -> None:
        self._cookies_path = cookies_path or get_cookies_path()

    def search(
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
    ) -> HotelSearchResult:
        """Search hotels via Playwright (SSR + XHR interception).

        First page comes from __NEXT_DATA__ SSR; subsequent pages from
        fetchHotelList XHR triggered by scrolling.
        """
        from playwright.sync_api import sync_playwright

        city_info = CITY_MAP.get(city_name)
        if city_info is None:
            raise ValueError(
                f"不支持的城市：{city_name}。"
                f"支持：{', '.join(CITY_MAP.keys())}"
            )
        city_id, _, _ = city_info

        sort_id = self._SORT_URL_MAP.get(sort, "1")
        url = (
            f"{HOTEL_LIST_URL}?cityId={city_id}"
            f"&checkIn={checkin}&checkOut={checkout}"
            f"&adult={adult}&crn={rooms}&curr=CNY"
            f"&sortId={sort_id}"
        )

        xhr_pages: list[dict] = []
        lock = threading.Lock()

        def _on_response(response) -> None:
            if "fetchHotelList" not in response.url or response.status != 200:
                return
            try:
                data = json.loads(response.body())
                if isinstance(data, dict):
                    with lock:
                        xhr_pages.append(data)
                    logger.debug("Captured fetchHotelList XHR (%d bytes)", len(response.body()))
            except Exception as exc:
                logger.debug("Failed to parse fetchHotelList XHR: %s", exc)

        pw_cookies = load_playwright_cookies(self._cookies_path)
        hotels: List[HotelCard] = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, channel="chrome")
            ctx = browser.new_context(
                user_agent=DEFAULT_HEADERS["user-agent"],
                locale="zh-CN",
                extra_http_headers={"accept-language": "zh-CN,zh;q=0.9"},
            )
            if pw_cookies:
                ctx.add_cookies(pw_cookies)

            page = ctx.new_page()
            page.on("response", _on_response)

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(2000)

                # ── Phase 1: Parse SSR __NEXT_DATA__ (first page, ~13 hotels) ──
                try:
                    # Playwright auto-serializes JS objects to Python dicts
                    ssr_list_data = page.evaluate(
                        "() => (window.__NEXT_DATA__ || {}).props?.pageProps?.initListData || {}"
                    )
                    if not isinstance(ssr_list_data, dict):
                        ssr_list_data = {}
                    for item in ssr_list_data.get("hotelList", []):
                        if not isinstance(item, dict):
                            continue
                        card = HotelApiScraper._parse_hotel(item, city_id, checkin, checkout)
                        if card:
                            hotels.append(card)
                    ssr_extra = ssr_list_data.get("hotelListAddtionInfo", {})
                    is_last = bool(ssr_extra.get("isLastPage", True) if isinstance(ssr_extra, dict) else True)
                    logger.debug("SSR hotels: %d, isLastPage: %s", len(hotels), is_last)
                except Exception as exc:
                    logger.debug("SSR parse failed: %s", exc)
                    is_last = False

                # ── Phase 2: Scroll-triggered XHR pagination ──
                scroll_attempts = 0
                max_scrolls = max(1, (limit - len(hotels)) // 10 + 2)

                while len(hotels) < limit and not is_last and scroll_attempts < max_scrolls:
                    prev_count = len(xhr_pages)
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    page.wait_for_timeout(3500)
                    scroll_attempts += 1

                    with lock:
                        new_pages = xhr_pages[prev_count:]

                    if not new_pages:
                        break

                    for page_data in new_pages:
                        data = page_data.get("data", {})
                        extra = data.get("hotelListAddtionInfo", {})
                        for item in data.get("hotelList", []):
                            card = HotelApiScraper._parse_hotel(item, city_id, checkin, checkout)
                            if card:
                                hotels.append(card)
                        if extra.get("isLastPage", True):
                            is_last = True

            finally:
                page.close()
                ctx.close()
                browser.close()

        return HotelSearchResult(
            city_id=city_id,
            city_name=city_name,
            checkin=checkin,
            checkout=checkout,
            hotels=hotels[:limit],
        )


class HotelApiScraper:
    """All hotel operations via direct httpx API calls."""

    PAGE_SIZE = 10

    def __init__(self, cookies_path: Path | None = None):
        path = cookies_path or get_cookies_path()
        # Cookies are optional — API works without login
        if path and path.exists():
            self.cookies = load_cookies(path)
            self._guid = get_guid(self.cookies)
        else:
            self.cookies = httpx.Cookies()
            self._guid = ""

    # ─────────────────────────────────────────
    # Internals
    # ─────────────────────────────────────────

    def _post(self, url: str, payload: dict) -> dict:
        headers = {
            **DEFAULT_HEADERS,
            "referer": "https://hotels.ctrip.com/",
            "origin": "https://hotels.ctrip.com",
        }
        with httpx.Client(cookies=self.cookies, follow_redirects=True, timeout=15) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            return resp.json()

    def _hotel_head(self, checkin: str = "", checkout: str = "") -> dict:
        return hotel_head(self._guid, checkin, checkout)

    @staticmethod
    def _build_filters(
        sort: str,
        stars: list[int] | None,
        breakfast: bool,
        free_cancel: bool,
        price_min: int | None,
        price_max: int | None,
    ) -> list[dict]:
        filters = []

        # Sort
        sort_f = SORT_FILTERS.get(sort, SORT_FILTERS["popular"])
        filters.append(sort_f)

        # Stars
        for s in (stars or []):
            if s in STAR_FILTERS:
                filters.append(STAR_FILTERS[s])

        # Breakfast
        if breakfast:
            filters.append({"filterId": "5|1", "type": "5", "value": "1", "subType": "2"})

        # Free cancel
        if free_cancel:
            filters.append({"filterId": "23|10", "type": "23", "value": "10", "subType": "2"})

        # Price range
        if price_min is not None or price_max is not None:
            mn = price_min or 0
            mx = price_max or 99999
            # Try predefined ranges first, fall back to custom
            matched = False
            for (lo, hi), f in PRICE_RANGE_FILTERS.items():
                if mn == lo and mx == hi:
                    filters.append(f)
                    matched = True
                    break
            if not matched:
                filters.append({
                    "filterId": "15|Range",
                    "type": "15",
                    "value": f"{mn}|{mx}",
                    "subType": "2",
                })

        return filters

    @staticmethod
    def _parse_hotel(item: dict, city_id: int, checkin: str, checkout: str) -> Optional[HotelCard]:
        info = item.get("hotelInfo", {})
        summary = info.get("summary", {})
        hotel_id = str(summary.get("hotelId", ""))
        if not hotel_id:
            return None

        name_info = info.get("nameInfo", {})
        comment = info.get("commentInfo", {})
        position = info.get("positionInfo", {})
        star_info = info.get("hotelStar", {})

        # Room / price from first roomInfo entry
        rooms = item.get("roomInfo", [])
        room_name = None
        price_str = None
        free_cancel = False
        promotion = None
        if rooms:
            r = rooms[0]
            room_name = r.get("summary", {}).get("saleRoomName")
            price_info = r.get("priceInfo", {})
            price_str = price_info.get("displayPrice")
            room_tags = r.get("roomTags", []) or []
            for tag in room_tags:
                if not isinstance(tag, dict):
                    continue
                tag_text = str(tag.get("tagContent", "") or tag.get("text", ""))
                if "免费取消" in tag_text:
                    free_cancel = True
                elif tag_text:
                    promotion = tag_text

        detail_url = (
            f"{HOTEL_DETAIL_URL}?hotelId={hotel_id}&cityId={city_id}"
            f"&checkIn={checkin}&checkOut={checkout}&adult=1&children=0&crn=1&curr=CNY"
        )

        return HotelCard(
            hotel_id=hotel_id,
            name=name_info.get("name", ""),
            star=star_info.get("star"),
            score=comment.get("commentScore"),
            score_desc=comment.get("commentDescription"),
            comment_num=comment.get("commenterNumber"),
            address=position.get("positionDesc"),
            room_name=room_name,
            price=price_str,
            promotion=promotion,
            free_cancel=free_cancel,
            is_ad=False,
            detail_url=detail_url,
        )

    # ─────────────────────────────────────────
    # Public: search
    # ─────────────────────────────────────────

    def search(
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
    ) -> HotelSearchResult:
        """Search hotels via fetchHotelList API (no browser, no auth required)."""
        city_info = CITY_MAP.get(city_name)
        if city_info is None:
            raise ValueError(
                f"不支持的城市：{city_name}。"
                f"支持：{', '.join(CITY_MAP.keys())}"
            )
        city_id, country_id, _ = city_info

        filters = self._build_filters(sort, stars, breakfast, free_cancel, price_min, price_max)
        hotels: List[HotelCard] = []
        session_id = ""
        shown_ids: list[str] = []
        page = 1

        while len(hotels) < limit:
            payload = {
                "destination": {
                    "type": 1,
                    "geo": {"cityId": city_id, "countryId": country_id, "provinceId": 0, "districtId": 0},
                    "keyword": {"word": ""},
                },
                "checkInfo": {"checkIn": checkin, "checkOut": checkout},
                "guest": {"adult": adult, "children": 0, "ages": "", "roomsNum": rooms},
                "paging": {"pageIndex": page, "pageSize": self.PAGE_SIZE, "pageCode": ""},
                "filters": filters,
                "extraFilter": {
                    "ctripMainLandBDCoordinate": True,
                    "sessionId": session_id,
                    "extendableParams": {"tripWalkDriveSwitch": "T"},
                },
                "hotelIdFilter": {"hotelAldyShown": shown_ids},
                "head": self._hotel_head(checkin, checkout),
            }

            data = self._post(HOTEL_SEARCH_URL, payload).get("data", {})
            extra = data.get("hotelListAddtionInfo", {})

            for item in data.get("hotelList", []):
                card = self._parse_hotel(item, city_id, checkin, checkout)
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

    # ─────────────────────────────────────────
    # Public: recommendations / history / cities
    # ─────────────────────────────────────────

    def get_recommendations(
        self,
        city_id: int,
        checkin: str,
        checkout: str,
        positions: list[str] | None = None,
    ) -> List[HotelCard]:
        """Fetch ad hotel recommendations for a city."""
        if positions is None:
            positions = ["HTL_LST_002", "HTL_LST_001", "HTL_LST_003"]

        head = self._hotel_head(checkin, checkout)
        head["extension"].append({"name": "cityId", "value": str(city_id)})

        payload = {"cityId": city_id, "adPositionCodes": positions, "head": head}
        data = self._post(HOTEL_AD_URL, payload)

        hotels: List[HotelCard] = []
        for ad in data.get("data", {}).get("adList", []):
            for h in ad.get("hotels", []):
                base = h.get("base", {})
                comment = h.get("comment", {})
                money = h.get("money", {})
                hotel_id = str(base.get("hotelId", ""))
                hotels.append(HotelCard(
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
                    ) if hotel_id else None,
                ))
        return hotels

    def get_browse_history(self, checkin: str, checkout: str) -> List[HotelCard]:
        """Fetch hotels recently browsed by the logged-in user."""
        head = self._hotel_head(checkin, checkout)
        payload = {"hotelIdFilter": {"hotelForceShow": []}, "head": head}
        data = self._post(HOTEL_BROWSE_URL, payload)

        hotels: List[HotelCard] = []
        for item in data.get("data", {}).get("hotelList", []):
            info = item.get("hotelInfo", {})
            summary = info.get("summary", {})
            name_info = info.get("nameInfo", {})
            hotel_id = str(summary.get("hotelId", ""))
            hotels.append(HotelCard(
                hotel_id=hotel_id,
                name=name_info.get("name", ""),
                detail_url=(
                    f"{HOTEL_DETAIL_URL}?hotelId={hotel_id}"
                    f"&checkIn={checkin}&checkOut={checkout}"
                ) if hotel_id else None,
            ))
        return hotels

    def get_cities(self, checkin: str = "", checkout: str = "") -> List[HotelCity]:
        """Fetch available cities for hotel search."""
        head = self._hotel_head(checkin, checkout)
        payload = {"requestType": "5", "head": head}
        data = self._post(HOTEL_CITY_URL, payload)

        cities: List[HotelCity] = []
        inland = data.get("data", {}).get("inlandCityModel", {})
        for group in inland.get("cityModelGroups", []):
            group_name = group.get("displayControlModel", {}).get("fullName", "")
            for region in group.get("regionModels", []):
                basic = region.get("basicCityModel", {})
                display = region.get("displayCityModel", {})
                cities.append(HotelCity(
                    city_id=basic.get("cityId", 0),
                    city_name=display.get("destinationName", ""),
                    country_id=basic.get("countryId", 1),
                    group_name=group_name,
                ))
        return cities

    def get_filters(self, city_id: int, checkin: str, checkout: str) -> dict:
        """Fetch all available filter options for a city search."""
        payload = {
            "destination": {
                "type": 1,
                "geo": {"cityId": city_id, "countryId": 1, "provinceId": 0, "districtId": 0},
                "keyword": {"word": ""},
            },
            "checkInfo": {"checkIn": checkin, "checkOut": checkout},
            "guest": {"adult": 1, "children": 0, "roomsNum": 1},
            "filters": [],
            "head": self._hotel_head(checkin, checkout),
        }
        return self._post(HOTEL_FILTER_URL, payload)
