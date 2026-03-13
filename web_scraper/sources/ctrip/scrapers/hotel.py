"""Ctrip hotel scrapers.

- HotelSearchScraper: Playwright response interception for fetchHotelList
  (bypasses phantom-token anti-bot protection).
- HotelApiScraper: pure httpx for recommendations, browse history, city list, filters.
- HotelDetailScraper: Playwright DOM parsing for hotel detail pages.
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
    BRAND_FILTERS,
    CITY_MAP,
    CTRIP_RATE_LIMIT,
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
    retry_on_error,
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
        keyword: str = "",
        brands: list[str] | None = None,
    ) -> HotelSearchResult:
        """Search hotels via Playwright (SSR + XHR interception).

        First page comes from __NEXT_DATA__ SSR; subsequent pages from
        fetchHotelList XHR triggered by scrolling.
        """
        from patchright.sync_api import sync_playwright
        from urllib.parse import quote

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
        if keyword:
            url += f"&keyword={quote(keyword)}"

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

        from ....core.rate_limiter import RateLimiter, RateLimiterConfig
        self._rate_limiter = RateLimiter(RateLimiterConfig(**CTRIP_RATE_LIMIT))

    # ─────────────────────────────────────────
    # Internals
    # ─────────────────────────────────────────

    def _post(self, url: str, payload: dict) -> dict:
        self._rate_limiter.wait()
        headers = {
            **DEFAULT_HEADERS,
            "referer": "https://hotels.ctrip.com/",
            "origin": "https://hotels.ctrip.com",
        }
        try:
            with httpx.Client(cookies=self.cookies, follow_redirects=True, timeout=15) as client:
                resp = client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                result = resp.json()
                self._rate_limiter.record_success()
                return result
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                self._rate_limiter.record_rate_limit()
            raise
        except Exception:
            raise

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
        brands: list[str] | None = None,
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

        # Brands
        for brand_name in (brands or []):
            brand_f = BRAND_FILTERS.get(brand_name)
            if brand_f:
                filters.append(brand_f)

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

    @retry_on_error()
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
        keyword: str = "",
        brands: list[str] | None = None,
    ) -> HotelSearchResult:
        """Search hotels via fetchHotelList API (no browser, no auth required)."""
        city_info = CITY_MAP.get(city_name)
        if city_info is None:
            raise ValueError(
                f"不支持的城市：{city_name}。"
                f"支持：{', '.join(CITY_MAP.keys())}"
            )
        city_id, country_id, _ = city_info

        filters = self._build_filters(sort, stars, breakfast, free_cancel, price_min, price_max, brands)
        hotels: List[HotelCard] = []
        session_id = ""
        shown_ids: list[str] = []
        page = 1

        while len(hotels) < limit:
            payload = {
                "destination": {
                    "type": 1,
                    "geo": {"cityId": city_id, "countryId": country_id, "provinceId": 0, "districtId": 0},
                    "keyword": {"word": keyword},
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

    @retry_on_error()
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


class HotelDetailScraper:
    """Fetch detailed hotel info from the detail page via Playwright."""

    def __init__(self, cookies_path: Path | None = None, headless: bool = True):
        self._cookies_path = cookies_path or get_cookies_path()
        self.headless = headless

    def fetch(
        self,
        hotel_id: str,
        city_id: int,
        checkin: str,
        checkout: str,
    ) -> "HotelDetail":
        from patchright.sync_api import sync_playwright
        from ..models import HotelDetail, HotelRoom

        url = (
            f"{HOTEL_DETAIL_URL}?hotelId={hotel_id}&cityId={city_id}"
            f"&checkIn={checkin}&checkOut={checkout}&adult=1&children=0&crn=1&curr=CNY"
        )

        pw_cookies = load_playwright_cookies(self._cookies_path)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless, channel="chrome")
            ctx = browser.new_context(
                user_agent=DEFAULT_HEADERS["user-agent"],
                locale="zh-CN",
                extra_http_headers={"accept-language": "zh-CN,zh;q=0.9"},
            )
            if pw_cookies:
                ctx.add_cookies(pw_cookies)
            page = ctx.new_page()

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                # Wait for hotel name to render
                page.wait_for_selector(
                    "h1, .hotel_info_name, [class*='hotelName']",
                    timeout=15000,
                )
                page.wait_for_timeout(2000)

                # Try SSR data first
                ssr = page.evaluate("""() => {
                    try {
                        const nd = window.__NEXT_DATA__ || {};
                        return nd.props?.pageProps || {};
                    } catch { return {}; }
                }""")

                # Extract from SSR or DOM
                hotel_info = ssr.get("hotelDetail", {}) or ssr.get("hotelInfo", {}) or {}
                basic = hotel_info.get("basicInfo", {}) or {}
                comment_info = hotel_info.get("commentInfo", {}) or {}

                # DOM fallback for basic info
                dom_data = page.evaluate("""() => {
                    const text = (sel) => {
                        const el = document.querySelector(sel);
                        return el ? el.textContent.replace(/\\s+/g, ' ').trim() : '';
                    };
                    const texts = (sel) => Array.from(document.querySelectorAll(sel))
                        .map(el => el.textContent.replace(/\\s+/g, ' ').trim())
                        .filter(Boolean);

                    return {
                        name: text('h1') || text('[class*="hotelName"]') || '',
                        score: text('[class*="score"]') || '',
                        scoreDesc: text('[class*="commentDesc"]') || text('[class*="comment-desc"]') || '',
                        commentCount: text('[class*="commentNum"]') || text('[class*="comment-num"]') || '',
                        address: text('[class*="address"]') || text('[class*="hotelAddress"]') || '',
                        tags: texts('[class*="hotelTag"] span, [class*="hotel-tag"] span'),
                        facilities: texts('[class*="facility"] li, [class*="facilit"] span, [class*="amenity"] span'),
                        images: Array.from(document.querySelectorAll('[class*="photo"] img, [class*="gallery"] img'))
                            .map(img => img.src || img.dataset?.src || '')
                            .filter(s => s.startsWith('http'))
                            .slice(0, 10),
                    };
                }""")

                # Extract rooms from DOM
                room_data = page.evaluate("""() => {
                    const rooms = [];
                    document.querySelectorAll('[class*="room-list"] tr, [class*="roomItem"], [class*="room_item"]').forEach(row => {
                        const text = (sel) => {
                            const el = row.querySelector(sel);
                            return el ? el.textContent.replace(/\\s+/g, ' ').trim() : '';
                        };
                        const texts = (sel) => Array.from(row.querySelectorAll(sel))
                            .map(el => el.textContent.replace(/\\s+/g, ' ').trim())
                            .filter(Boolean);
                        const name = text('[class*="room_type_name"], [class*="roomName"], .room-name');
                        if (!name) return;
                        rooms.push({
                            room_name: name,
                            bed_type: text('[class*="bed"], [class*="bedType"]') || null,
                            area: text('[class*="area"]') || null,
                            breakfast: text('[class*="breakfast"]') || null,
                            price: text('[class*="price"]') || null,
                            cancel_policy: text('[class*="cancel"]') || null,
                            tags: texts('[class*="tag"] span'),
                        });
                    });
                    return rooms;
                }""")

                # Build model
                name = basic.get("hotelName") or dom_data.get("name", "")
                star_val = basic.get("star") or None
                if isinstance(star_val, str):
                    m = re.search(r"\d+", star_val)
                    star_val = int(m.group()) if m else None

                rooms = [
                    HotelRoom(
                        room_name=r.get("room_name", ""),
                        bed_type=r.get("bed_type"),
                        area=r.get("area"),
                        breakfast=r.get("breakfast"),
                        price=r.get("price"),
                        cancel_policy=r.get("cancel_policy"),
                        tags=r.get("tags", []),
                    )
                    for r in (room_data or [])
                    if r.get("room_name")
                ]

                return HotelDetail(
                    hotel_id=hotel_id,
                    name=name,
                    name_en=basic.get("hotelNameEn") or None,
                    star=star_val,
                    score=comment_info.get("commentScore") or dom_data.get("score") or None,
                    score_desc=comment_info.get("commentDescription") or dom_data.get("scoreDesc") or None,
                    comment_count=comment_info.get("commenterNumber") or dom_data.get("commentCount") or None,
                    address=basic.get("address") or dom_data.get("address") or None,
                    phone=basic.get("phone") or None,
                    opening_year=basic.get("openingYear") or None,
                    renovation_year=basic.get("renovationYear") or None,
                    room_count=basic.get("roomCount") or None,
                    tags=dom_data.get("tags", []),
                    facilities=dom_data.get("facilities", []),
                    description=basic.get("description") or None,
                    images=dom_data.get("images", []),
                    rooms=rooms,
                    detail_url=url,
                )
            finally:
                page.close()
                ctx.close()
                browser.close()
