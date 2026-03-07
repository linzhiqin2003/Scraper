"""Note detail scraper for Dianping."""
from urllib.parse import parse_qs, urlparse

from ..config import NOTE_RECOMMEND_URL, WWW_BASE_URL
from ..models import DianpingAuthor, DianpingNoteDetail, DianpingNoteRecommendation
from .base import DianpingBaseScraper, extract_script_json


class NoteScraper(DianpingBaseScraper):
    """Fetch Dianping notes from SSR __NEXT_DATA__."""

    def fetch(self, target: str, *, rec_limit: int = 3) -> DianpingNoteDetail:
        """Fetch note detail by URL or noteId_feedType."""
        url = self._normalize_target(target)
        html = self.get_text(url, referer=WWW_BASE_URL)
        next_data = extract_script_json(html, "__NEXT_DATA__")

        page_props = next_data.get("props", {}).get("pageProps", {})
        feed_info = page_props.get("feedInfo", {})
        if not feed_info:
            raise RuntimeError("未在 __NEXT_DATA__ 中找到笔记正文")

        note_id = str(feed_info.get("mainId"))
        feed_type = int(feed_info.get("feedType", 29))
        author_info = feed_info.get("feedUser") or {}

        author = None
        if author_info.get("userId") is not None:
            author = DianpingAuthor(
                user_id=str(author_info.get("userId")),
                nickname=author_info.get("nickName") or author_info.get("userNickName") or "",
                avatar_url=author_info.get("avatar") or author_info.get("userImgUrl"),
            )

        recommendations = self._fetch_recommendations(note_id, feed_type, rec_limit)

        return DianpingNoteDetail(
            note_id=note_id,
            feed_type=feed_type,
            url=f"{WWW_BASE_URL}/note/{note_id}_{feed_type}",
            title=feed_info.get("title"),
            content=feed_info.get("content"),
            author=author,
            like_count=feed_info.get("likeCount"),
            comment_count=feed_info.get("commentCount"),
            collect_count=feed_info.get("collectCount"),
            published_at=feed_info.get("addTime"),
            images=[item.get("url") for item in feed_info.get("feedPicList", []) if item.get("url")],
            topics=[item.get("name") for item in feed_info.get("contentTopicList", []) if item.get("name")],
            recommendations=recommendations,
            raw_page=next_data.get("page"),
        )

    def _fetch_recommendations(
        self,
        note_id: str,
        feed_type: int,
        limit: int,
    ) -> list[DianpingNoteRecommendation]:
        if limit <= 0:
            return []

        try:
            data = self.get_json(
                NOTE_RECOMMEND_URL,
                referer=f"{WWW_BASE_URL}/note/{note_id}_{feed_type}",
                params={
                    "feedid": note_id,
                    "feedtype": feed_type,
                    "cityid": -1,
                    "choosecityid": -1,
                    "longitude": 0,
                    "latitude": 0,
                    "start": 0,
                    "limit": limit,
                },
            )
        except Exception:
            return []

        items = []
        for item in data.get("recList", [])[:limit]:
            author = item.get("storyFeedUser") or {}
            images = [pic.get("bigUrl") for pic in item.get("storyFeedPics", []) if pic.get("bigUrl")]
            items.append(DianpingNoteRecommendation(
                title=item.get("storyTitle"),
                content=item.get("storyContent"),
                author_name=author.get("userNickName"),
                like_count=item.get("likeCount"),
                comment_count=item.get("commentCount"),
                image_urls=images,
            ))
        return items

    @staticmethod
    def _normalize_target(target: str) -> str:
        target = target.strip()
        if target.startswith("http://") or target.startswith("https://"):
            return target

        if "_" in target:
            return f"{WWW_BASE_URL}/note/{target}"

        return f"https://m.dianping.com/ugcdetail/{target}?bizType=29"


def parse_note_target(target: str) -> tuple[str, int]:
    """Parse note identifiers from a note or ugcdetail URL."""
    parsed = urlparse(target)
    path = parsed.path.rstrip("/")
    if "/note/" in path:
        slug = path.split("/")[-1]
        note_id, feed_type = slug.split("_", 1)
        return note_id, int(feed_type)
    if "/ugcdetail/" in path:
        note_id = path.split("/")[-1]
        qs = parse_qs(parsed.query)
        feed_type = int(qs.get("bizType", ["29"])[0])
        return note_id, feed_type
    raise ValueError(f"Unsupported note target: {target}")
