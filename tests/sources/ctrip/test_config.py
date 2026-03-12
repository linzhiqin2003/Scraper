"""Tests for Ctrip config utilities."""

import pytest

from web_scraper.sources.ctrip.config import (
    BRAND_FILTERS,
    CITY_MAP,
    FLIGHT_CITY_CODE_MAP,
    FLIGHT_CODE_NAME_MAP,
    GRADE_MAP,
    SORT_FILTERS,
    STAR_FILTERS,
    hotel_head,
    normalize_flight_city,
    retry_on_error,
    soa2_head,
)


def test_city_map_not_empty() -> None:
    assert len(CITY_MAP) >= 18


def test_flight_city_code_map_bidirectional() -> None:
    for name, code in FLIGHT_CITY_CODE_MAP.items():
        assert FLIGHT_CODE_NAME_MAP[code] == name


def test_brand_filters_not_empty() -> None:
    assert len(BRAND_FILTERS) >= 10
    for name, f in BRAND_FILTERS.items():
        assert f["type"] == "4"
        assert "filterId" in f


def test_soa2_head_default() -> None:
    head = soa2_head()
    assert head["cver"] == "1.0"
    assert head["lang"] == "01"
    assert "cid" in head


def test_soa2_head_with_guid() -> None:
    head = soa2_head("custom-guid")
    assert head["cid"] == "custom-guid"


def test_hotel_head_structure() -> None:
    head = hotel_head("test-guid", "2026-03-10", "2026-03-12")
    assert head["platform"] == "PC"
    assert head["cid"] == "test-guid"
    assert head["bu"] == "HBU"
    exts = {e["name"]: e["value"] for e in head["extension"]}
    assert exts["checkIn"] == "2026-03-10"
    assert exts["checkOut"] == "2026-03-12"


def test_normalize_flight_city_name() -> None:
    code, name = normalize_flight_city("上海")
    assert code == "SHA"
    assert name == "上海"


def test_normalize_flight_city_code() -> None:
    code, name = normalize_flight_city("BJS")
    assert code == "BJS"
    assert name == "北京"


def test_normalize_flight_city_with_parens() -> None:
    code, name = normalize_flight_city("上海(SHA)")
    assert code == "SHA"


def test_normalize_flight_city_case_insensitive() -> None:
    code, _ = normalize_flight_city("sha")
    assert code == "SHA"


def test_normalize_flight_city_invalid() -> None:
    with pytest.raises(ValueError, match="暂不支持"):
        normalize_flight_city("火星")


def test_normalize_flight_city_empty() -> None:
    with pytest.raises(ValueError, match="城市不能为空"):
        normalize_flight_city("  ")


def test_retry_on_error_success() -> None:
    call_count = 0

    @retry_on_error(max_retries=2, retry_delay=0.01)
    def ok():
        nonlocal call_count
        call_count += 1
        return 42

    assert ok() == 42
    assert call_count == 1


def test_retry_on_error_retries_then_succeeds() -> None:
    call_count = 0

    @retry_on_error(max_retries=2, retry_delay=0.01)
    def flaky():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise RuntimeError("fail")
        return "ok"

    assert flaky() == "ok"
    assert call_count == 3


def test_retry_on_error_does_not_retry_valueerror() -> None:
    call_count = 0

    @retry_on_error(max_retries=3, retry_delay=0.01)
    def bad():
        nonlocal call_count
        call_count += 1
        raise ValueError("programming error")

    with pytest.raises(ValueError):
        bad()
    assert call_count == 1


def test_retry_on_error_exhausted() -> None:
    call_count = 0

    @retry_on_error(max_retries=1, retry_delay=0.01)
    def always_fail():
        nonlocal call_count
        call_count += 1
        raise RuntimeError("always fails")

    with pytest.raises(RuntimeError, match="always fails"):
        always_fail()
    assert call_count == 2  # initial + 1 retry
