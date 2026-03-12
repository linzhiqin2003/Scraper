"""Tests for Ctrip flight helpers."""

from web_scraper.sources.ctrip.config import normalize_flight_city
from web_scraper.sources.ctrip.scrapers.flight import (
    FlightSearchScraper,
    _extract_price_value,
    _parse_ctrip_json_date,
)


def test_normalize_flight_city_with_name() -> None:
    code, name = normalize_flight_city("上海")
    assert code == "SHA"
    assert name == "上海"


def test_normalize_flight_city_with_code_and_label() -> None:
    assert normalize_flight_city("bjs") == ("BJS", "北京")
    assert normalize_flight_city("上海(SHA)") == ("SHA", "上海")


def test_extract_price_value() -> None:
    assert _extract_price_value("¥330起") == 330
    assert _extract_price_value("价格 520.5") == 520.5
    assert _extract_price_value(None) is None


def test_parse_ctrip_json_date() -> None:
    assert _parse_ctrip_json_date("/Date(1773072000000+0800)/") == "2026-03-10"


def test_build_flight_search_url() -> None:
    url = FlightSearchScraper._build_search_url("SHA", "BJS", "2026-03-10")
    assert url == "https://flights.ctrip.com/online/list/oneway-sha-bjs?_=1&depdate=2026-03-10&cabin=Y_S_C_F"
