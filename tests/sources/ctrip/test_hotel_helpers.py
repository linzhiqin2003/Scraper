"""Tests for Ctrip hotel helpers and filter building."""

from web_scraper.sources.ctrip.scrapers.hotel import HotelApiScraper
from web_scraper.sources.ctrip.models import HotelCard


def test_build_filters_default() -> None:
    filters = HotelApiScraper._build_filters("popular", None, False, False, None, None)
    assert len(filters) == 1
    assert filters[0]["type"] == "17"  # sort filter
    assert filters[0]["value"] == "1"  # popular


def test_build_filters_with_sort() -> None:
    filters = HotelApiScraper._build_filters("score", None, False, False, None, None)
    assert filters[0]["value"] == "6"


def test_build_filters_with_stars() -> None:
    filters = HotelApiScraper._build_filters("popular", [4, 5], False, False, None, None)
    assert len(filters) == 3  # sort + 2 star filters
    star_filters = [f for f in filters if f["type"] == "16"]
    assert len(star_filters) == 2
    star_values = {f["value"] for f in star_filters}
    assert star_values == {"4", "5"}


def test_build_filters_with_breakfast() -> None:
    filters = HotelApiScraper._build_filters("popular", None, True, False, None, None)
    breakfast = [f for f in filters if f["type"] == "5"]
    assert len(breakfast) == 1


def test_build_filters_with_free_cancel() -> None:
    filters = HotelApiScraper._build_filters("popular", None, False, True, None, None)
    cancel = [f for f in filters if f["type"] == "23"]
    assert len(cancel) == 1


def test_build_filters_predefined_price_range() -> None:
    filters = HotelApiScraper._build_filters("popular", None, False, False, 150, 300)
    price = [f for f in filters if f["type"] == "15"]
    assert len(price) == 1
    assert price[0]["value"] == "150|300"


def test_build_filters_custom_price_range() -> None:
    filters = HotelApiScraper._build_filters("popular", None, False, False, 200, 500)
    price = [f for f in filters if f["type"] == "15"]
    assert len(price) == 1
    assert price[0]["value"] == "200|500"


def test_build_filters_with_brands() -> None:
    filters = HotelApiScraper._build_filters(
        "popular", None, False, False, None, None, brands=["亚朵", "全季"]
    )
    brand_filters = [f for f in filters if f["type"] == "4"]
    assert len(brand_filters) == 2


def test_build_filters_unknown_brand_skipped() -> None:
    filters = HotelApiScraper._build_filters(
        "popular", None, False, False, None, None, brands=["不存在的品牌"]
    )
    brand_filters = [f for f in filters if f["type"] == "4"]
    assert len(brand_filters) == 0


def test_build_filters_combined() -> None:
    filters = HotelApiScraper._build_filters(
        "price_asc", [5], True, True, 300, 450, brands=["希尔顿"]
    )
    # sort + star + breakfast + free_cancel + price + brand = 6
    assert len(filters) == 6


def test_parse_hotel_basic() -> None:
    item = {
        "hotelInfo": {
            "summary": {"hotelId": 12345},
            "nameInfo": {"name": "测试酒店"},
            "hotelStar": {"star": 5},
            "commentInfo": {
                "commentScore": "4.8",
                "commentDescription": "超棒",
                "commenterNumber": "3000条",
            },
            "positionInfo": {"positionDesc": "南京路附近"},
        },
        "roomInfo": [
            {
                "summary": {"saleRoomName": "豪华大床房"},
                "priceInfo": {"displayPrice": "¥888"},
                "roomTags": [
                    {"tagContent": "免费取消"},
                    {"text": "含双早"},
                ],
            }
        ],
    }
    card = HotelApiScraper._parse_hotel(item, 2, "2026-03-10", "2026-03-12")
    assert card is not None
    assert card.hotel_id == "12345"
    assert card.name == "测试酒店"
    assert card.star == 5
    assert card.score == "4.8"
    assert card.room_name == "豪华大床房"
    assert card.price == "¥888"
    assert card.free_cancel is True
    assert card.promotion == "含双早"
    assert "hotelId=12345" in card.detail_url


def test_parse_hotel_no_id_returns_none() -> None:
    item = {"hotelInfo": {"summary": {}}}
    assert HotelApiScraper._parse_hotel(item, 2, "2026-03-10", "2026-03-12") is None


def test_parse_hotel_no_rooms() -> None:
    item = {
        "hotelInfo": {
            "summary": {"hotelId": 99},
            "nameInfo": {"name": "简洁酒店"},
        },
        "roomInfo": [],
    }
    card = HotelApiScraper._parse_hotel(item, 2, "2026-03-10", "2026-03-12")
    assert card is not None
    assert card.room_name is None
    assert card.price is None
    assert card.free_cancel is False
