"""Ctrip flight scrapers."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import httpx
from playwright.sync_api import TimeoutError as PlaywrightTimeout, sync_playwright

from ..config import (
    CTRIP_RATE_LIMIT,
    FLIGHT_DEFAULT_HEADERS,
    FLIGHT_LIST_URL,
    FLIGHT_LOWEST_PRICE_URL,
    FlightSelectors,
    normalize_flight_city,
    retry_on_error,
)
from ..cookies import get_cookies_path, load_cookies, load_playwright_cookies
from ..models import FlightCard, FlightCalendarPrice, FlightSearchResult

logger = logging.getLogger(__name__)

_CHINA_TZ = timezone(timedelta(hours=8))


def _extract_price_value(text: str | None) -> float | None:
    if not text:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)", text.replace(",", ""))
    return float(match.group(1)) if match else None


def _parse_ctrip_json_date(raw: str | None) -> str | None:
    if not raw:
        return None
    match = re.search(r"/Date\((\d+)([+-]\d{4})?\)/", raw)
    if not match:
        return None
    millis = int(match.group(1))
    dt = datetime.fromtimestamp(millis / 1000, tz=_CHINA_TZ)
    return dt.strftime("%Y-%m-%d")


def _sort_calendar_prices(prices: list[FlightCalendarPrice]) -> list[FlightCalendarPrice]:
    return sorted(prices, key=lambda item: item.date)


class FlightLowPriceScraper:
    """Fetch low-price calendar data via the public Ctrip SOA2 endpoint."""

    def __init__(self, cookies_path: Path | None = None):
        path = cookies_path or get_cookies_path()
        self.cookies = load_cookies(path) if path.exists() else httpx.Cookies()

        from ....core.rate_limiter import RateLimiter, RateLimiterConfig
        self._rate_limiter = RateLimiter(RateLimiterConfig(**CTRIP_RATE_LIMIT))

    @retry_on_error()
    def search(self, departure_city: str, arrival_city: str, departure_date: str) -> list[FlightCalendarPrice]:
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

        self._rate_limiter.wait()
        try:
            with httpx.Client(cookies=self.cookies, follow_redirects=True, timeout=20) as client:
                resp = client.post(FLIGHT_LOWEST_PRICE_URL, json=payload, headers=FLIGHT_DEFAULT_HEADERS)
                resp.raise_for_status()
                data = resp.json()
                self._rate_limiter.record_success()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                self._rate_limiter.record_rate_limit()
            raise
        except Exception:
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


class FlightSearchScraper:
    """Fetch flight list by rendering the Ctrip PC result page and parsing DOM."""

    def __init__(self, cookies_path: Path | None = None, headless: bool = True):
        self._cookies_path = cookies_path or get_cookies_path()
        self.headless = headless
        self.low_price_scraper = FlightLowPriceScraper(cookies_path=self._cookies_path)

    @staticmethod
    def _build_search_url(departure_code: str, arrival_code: str, departure_date: str) -> str:
        return (
            f"{FLIGHT_LIST_URL}/oneway-{departure_code.lower()}-{arrival_code.lower()}"
            f"?_=1&depdate={departure_date}&cabin=Y_S_C_F"
        )

    @staticmethod
    def _parse_cards(raw_cards: list[dict[str, Any]], direct_only: bool, limit: int) -> list[FlightCard]:
        cards: list[FlightCard] = []
        for idx, item in enumerate(raw_cards, start=1):
            airlines = [str(v).strip() for v in item.get("airlines", []) if str(v).strip()]
            flight_numbers = [str(v).strip() for v in item.get("flightNumbers", []) if str(v).strip()]
            cabin_classes = [str(v).strip() for v in item.get("cabinClasses", []) if str(v).strip()]
            tags = [str(v).strip() for v in item.get("tags", []) if str(v).strip()]
            transfer_count = int(item.get("transferCount") or 0)
            is_direct = transfer_count == 0
            if direct_only and not is_direct:
                continue

            cards.append(
                FlightCard(
                    sequence=idx,
                    airlines=airlines,
                    flight_numbers=flight_numbers,
                    aircraft_summary=item.get("aircraftSummary") or None,
                    departure_time=item.get("departureTime") or "",
                    arrival_time=item.get("arrivalTime") or "",
                    departure_airport=item.get("departureAirport") or "",
                    arrival_airport=item.get("arrivalAirport") or "",
                    departure_terminal=item.get("departureTerminal") or None,
                    arrival_terminal=item.get("arrivalTerminal") or None,
                    price=item.get("priceText") or None,
                    price_value=_extract_price_value(item.get("priceText")),
                    cabin_classes=cabin_classes,
                    tags=tags,
                    is_direct=is_direct,
                    transfer_count=transfer_count,
                    transfer_duration=item.get("transferDuration") or None,
                    transfer_description=item.get("transferDescription") or None,
                )
            )
            if len(cards) >= limit:
                break
        return cards

    def search(
        self,
        departure_city: str,
        arrival_city: str,
        departure_date: str,
        limit: int = 20,
        direct_only: bool = False,
        with_calendar: bool = True,
    ) -> FlightSearchResult:
        departure_code, departure_name = normalize_flight_city(departure_city)
        arrival_code, arrival_name = normalize_flight_city(arrival_city)
        url = self._build_search_url(departure_code, arrival_code, departure_date)

        pw_cookies = load_playwright_cookies(self._cookies_path)
        calendar: list[FlightCalendarPrice] = []
        if with_calendar:
            try:
                calendar = self.low_price_scraper.search(departure_code, arrival_code, departure_date)
            except Exception:
                calendar = []

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=self.headless,
                channel="chrome",
                args=["--disable-gpu", "--disable-blink-features=AutomationControlled"],
            )
            ctx = browser.new_context(
                user_agent=FLIGHT_DEFAULT_HEADERS["user-agent"],
                locale="zh-CN",
                extra_http_headers={"accept-language": "zh-CN,zh;q=0.9"},
                viewport={"width": 1440, "height": 1024},
            )
            if pw_cookies:
                ctx.add_cookies(pw_cookies)
            page = ctx.new_page()
            no_result_message = None

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_function(
                    """
                    (noResultText) => Boolean(
                      document.querySelector('.flight-item.domestic') ||
                      document.body.innerText.includes(noResultText)
                    )
                    """,
                    arg=FlightSelectors.NO_RESULT_TEXT,
                    timeout=30000,
                )
                raw_cards = page.evaluate(
                    """
                    () => Array.from(document.querySelectorAll('.flight-item.domestic')).map((item) => {
                      const text = (selector) => item.querySelector(selector)?.textContent?.replace(/\\s+/g, ' ').trim() || '';
                      const texts = (selector) => Array.from(item.querySelectorAll(selector))
                        .map((el) => (el.textContent || '').replace(/\\s+/g, ' ').trim())
                        .filter(Boolean);
                      const transferCountText = item.querySelector('.arrow-transfer span')?.textContent || '';
                      const transferMatch = transferCountText.match(/转(\\d+)次/);
                      return {
                        airlines: texts('.airline-item .airline-name').length
                          ? texts('.airline-item .airline-name')
                          : texts('.flight-airline .airline-name'),
                        flightNumbers: texts('.plane-No').map((value) => value.split(' ')[0]),
                        aircraftSummary: texts('.plane-No').join(' / '),
                        departureTime: text('.depart-box .time'),
                        arrivalTime: text('.arrive-box .time'),
                        departureAirport: text('.depart-box .airport .name'),
                        arrivalAirport: text('.arrive-box .airport .name'),
                        departureTerminal: text('.depart-box .airport .terminal'),
                        arrivalTerminal: text('.arrive-box .airport .terminal'),
                        priceText: text('.flight-operate .price'),
                        cabinClasses: texts('.sub-price-item'),
                        tags: texts('.flight-tags .tag'),
                        transferDuration: text('.transfer-duration'),
                        transferDescription: text('.transfer-info'),
                        transferCount: transferMatch ? parseInt(transferMatch[1], 10) : 0,
                      };
                    })
                    """,
                )
                if not raw_cards:
                    body_text = page.locator("body").inner_text()
                    if FlightSelectors.NO_RESULT_TEXT in body_text:
                        no_result_message = FlightSelectors.NO_RESULT_TEXT
                flights = self._parse_cards(raw_cards, direct_only=direct_only, limit=limit)
            except PlaywrightTimeout as exc:
                raise RuntimeError(f"机票搜索超时：{exc}") from exc
            finally:
                page.close()
                ctx.close()
                browser.close()

        return FlightSearchResult(
            departure_city=departure_name,
            departure_code=departure_code,
            arrival_city=arrival_name,
            arrival_code=arrival_code,
            departure_date=departure_date,
            direct_only=direct_only,
            search_url=url,
            flights=flights,
            calendar_prices=calendar,
            no_result_message=no_result_message,
        )
