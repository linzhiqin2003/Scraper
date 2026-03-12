"""Tests for Douyin video helper functions."""

from web_scraper.sources.douyin.models import DouyinVideoInfo
from web_scraper.sources.douyin.scrapers.user_profile import _parse_video_item
from web_scraper.sources.douyin.scrapers.video import (
    choose_best_video_url,
    extract_video_info_from_html,
)
from web_scraper.sources.douyin.utils import build_video_url, extract_aweme_id, normalize_video_target


SAMPLE_HTML = """
<html>
  <head>
    <title>Example</title>
  </head>
  <body>
    <script>
      window.__DATA__ = {"awemeId":"7613349187447440817","desc":"17岁没等到的答案","nickname":"Caro赖赖_","video":{"width":1920,"height":1080,"duration":400934,"dataSize":55183858,"playAddr":[{"src":"https://v3-dy-o.zjcdn.com/example.mp4?a=6383\\u0026__vid=7613349187447440817"}],"playAddrSize":55183858,"downloadAddr":[{"src":"https://v3-dy-o.zjcdn.com/example-download.mp4?a=6383\\u0026__vid=7613349187447440817"}],"downloadAddrSize":55183858,"coverUrl":"https://p3.douyinpic.com/cover.jpeg"}};
    </script>
  </body>
</html>
"""


def test_extract_aweme_id_from_modal_url() -> None:
    url = "https://www.douyin.com/jingxuan?modal_id=7613349187447440817"
    assert extract_aweme_id(url) == "7613349187447440817"


def test_extract_aweme_id_from_video_url() -> None:
    url = "https://www.douyin.com/video/7613349187447440817"
    assert extract_aweme_id(url) == "7613349187447440817"


def test_normalize_video_target_from_bare_id() -> None:
    aweme_id, canonical_url = normalize_video_target("7613349187447440817")
    assert aweme_id == "7613349187447440817"
    assert canonical_url == "https://www.douyin.com/video/7613349187447440817"


def test_parse_video_item_adds_canonical_url() -> None:
    item = _parse_video_item(
        {
            "aweme_id": "7613349187447440817",
            "desc": "example",
            "author": {"nickname": "tester", "sec_uid": "secuid"},
            "video": {"cover": {"url_list": ["https://example.com/cover.jpeg"]}},
        }
    )
    assert item.aweme_id == "7613349187447440817"
    assert item.url == build_video_url("7613349187447440817")


def test_extract_video_info_from_html() -> None:
    info = extract_video_info_from_html(SAMPLE_HTML, "7613349187447440817")
    assert info is not None
    assert info.aweme_id == "7613349187447440817"
    assert info.desc == "17岁没等到的答案"
    assert info.author_name == "Caro赖赖_"
    assert info.duration_ms == 400934
    assert info.play_urls[0].endswith("__vid=7613349187447440817")
    assert info.download_urls[0].endswith("__vid=7613349187447440817")
    assert info.cover_url == "https://p3.douyinpic.com/cover.jpeg"


def test_choose_best_video_url_prefers_play_url() -> None:
    info = DouyinVideoInfo(
        aweme_id="7613349187447440817",
        play_urls=["https://cdn.example.com/play.mp4"],
        download_urls=["https://cdn.example.com/download.mp4"],
    )
    assert choose_best_video_url(info) == "https://cdn.example.com/play.mp4"


def test_choose_best_video_url_falls_back_to_download_url() -> None:
    info = DouyinVideoInfo(
        aweme_id="7613349187447440817",
        play_urls=[],
        download_urls=["https://cdn.example.com/download.mp4"],
    )
    assert choose_best_video_url(info) == "https://cdn.example.com/download.mp4"
