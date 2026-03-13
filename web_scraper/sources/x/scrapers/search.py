"""X (Twitter) GraphQL search scraper."""
import json
import logging
from typing import List, Optional

from ....core.http_client import HttpClient
from ..config import (
    BEARER_TOKEN,
    FEATURES,
    GRAPHQL_BASE,
    QUERY_IDS,
    get_cookies_from_file,
)
from ..models import XSearchResponse, XTweet, XUser

logger = logging.getLogger(__name__)


def build_query(
    query: str = "",
    *,
    exact_phrase: Optional[str] = None,
    any_words: Optional[str] = None,
    exclude_words: Optional[str] = None,
    hashtags: Optional[str] = None,
    from_user: Optional[str] = None,
    to_user: Optional[str] = None,
    mention: Optional[str] = None,
    min_likes: Optional[int] = None,
    min_retweets: Optional[int] = None,
    min_replies: Optional[int] = None,
    since: Optional[str] = None,
    until: Optional[str] = None,
    lang: Optional[str] = None,
    filter: Optional[str] = None,
    exclude_filter: Optional[str] = None,
) -> str:
    """Build a rawQuery string from advanced search parameters.

    Args:
        query: Base query (all of these words).
        exact_phrase: Exact phrase match (wrapped in quotes).
        any_words: Space-separated words joined with OR.
        exclude_words: Space-separated words to exclude (prefixed with -).
        hashtags: Space-separated hashtags (# prefix added if missing).
        from_user: Tweets from this user.
        to_user: Replies to this user.
        mention: Tweets mentioning this user.
        min_likes: Minimum likes (min_faves).
        min_retweets: Minimum retweets.
        min_replies: Minimum replies.
        since: Start date (YYYY-MM-DD).
        until: End date (YYYY-MM-DD).
        lang: Language code (ISO 639-1, e.g. "en", "zh").
        filter: Include filter (links, images, videos, media, replies).
        exclude_filter: Exclude filter (e.g. "replies" → -filter:replies).

    Returns:
        Assembled rawQuery string.
    """
    parts: list[str] = []

    if query:
        parts.append(query)
    if exact_phrase:
        parts.append(f'"{exact_phrase}"')
    if any_words:
        words = any_words.split()
        if len(words) > 1:
            parts.append(" OR ".join(words))
        elif words:
            parts.append(words[0])
    if exclude_words:
        for word in exclude_words.split():
            parts.append(f"-{word}" if not word.startswith("-") else word)
    if hashtags:
        for tag in hashtags.split():
            parts.append(tag if tag.startswith("#") else f"#{tag}")
    if from_user:
        parts.append(f"from:{from_user.lstrip('@')}")
    if to_user:
        parts.append(f"to:{to_user.lstrip('@')}")
    if mention:
        handle = mention.lstrip("@")
        parts.append(f"@{handle}")
    if min_likes is not None:
        parts.append(f"min_faves:{min_likes}")
    if min_retweets is not None:
        parts.append(f"min_retweets:{min_retweets}")
    if min_replies is not None:
        parts.append(f"min_replies:{min_replies}")
    if since:
        parts.append(f"since:{since}")
    if until:
        parts.append(f"until:{until}")
    if lang:
        parts.append(f"lang:{lang}")
    if filter:
        parts.append(f"filter:{filter}")
    if exclude_filter:
        parts.append(f"-filter:{exclude_filter}")

    return " ".join(parts)


class SearchScraper:
    """Search tweets via X GraphQL API."""

    def __init__(self, cookies: Optional[dict[str, str]] = None):
        self.cookies = cookies or get_cookies_from_file()
        ct0 = self.cookies.get("ct0", "")
        self._client = HttpClient(
            cookies=self.cookies,
            headers={
                "authorization": f"Bearer {BEARER_TOKEN}",
                "x-csrf-token": ct0,
                "x-twitter-auth-type": "OAuth2Session",
                "x-twitter-active-user": "yes",
                "x-twitter-client-language": "en",
                "content-type": "application/json",
            },
        )

    def is_configured(self) -> bool:
        """Check if auth cookies are available."""
        return bool(self.cookies.get("auth_token") and self.cookies.get("ct0"))

    def search(
        self,
        query: str,
        count: int = 20,
        product: str = "Top",
        cursor: Optional[str] = None,
        *,
        exact_phrase: Optional[str] = None,
        any_words: Optional[str] = None,
        exclude_words: Optional[str] = None,
        hashtags: Optional[str] = None,
        from_user: Optional[str] = None,
        to_user: Optional[str] = None,
        mention: Optional[str] = None,
        min_likes: Optional[int] = None,
        min_retweets: Optional[int] = None,
        min_replies: Optional[int] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        lang: Optional[str] = None,
        filter: Optional[str] = None,
        exclude_filter: Optional[str] = None,
    ) -> XSearchResponse:
        """Search tweets with optional advanced search filters.

        Args:
            query: Search query (all of these words).
            count: Results per page (max ~20).
            product: Top, Latest, People, Photos, Videos.
            cursor: Pagination cursor from previous response.
            exact_phrase: Exact phrase match.
            any_words: Any of these words (OR logic).
            exclude_words: None of these words.
            hashtags: Hashtags to include.
            from_user: Tweets from this user.
            to_user: Replies to this user.
            mention: Tweets mentioning this user.
            min_likes: Minimum likes.
            min_retweets: Minimum retweets.
            min_replies: Minimum replies.
            since: Start date (YYYY-MM-DD).
            until: End date (YYYY-MM-DD).
            lang: Language code (e.g. "en").
            filter: Include filter (links, images, videos, media).
            exclude_filter: Exclude filter (e.g. "replies").

        Returns:
            XSearchResponse with tweets and cursors.
        """
        raw_query = build_query(
            query,
            exact_phrase=exact_phrase,
            any_words=any_words,
            exclude_words=exclude_words,
            hashtags=hashtags,
            from_user=from_user,
            to_user=to_user,
            mention=mention,
            min_likes=min_likes,
            min_retweets=min_retweets,
            min_replies=min_replies,
            since=since,
            until=until,
            lang=lang,
            filter=filter,
            exclude_filter=exclude_filter,
        )

        variables: dict = {
            "rawQuery": raw_query,
            "count": count,
            "querySource": "typed_query",
            "product": product,
        }
        if cursor:
            variables["cursor"] = cursor

        data = self._graphql_post("SearchTimeline", variables)
        return self._parse_search_response(raw_query, product, data)

    def _graphql_post(self, operation: str, variables: dict) -> dict:
        """Make authenticated GraphQL POST request."""
        query_id = QUERY_IDS[operation]
        url = f"{GRAPHQL_BASE}/{query_id}/{operation}"

        body = {
            "variables": variables,
            "features": FEATURES,
            "queryId": query_id,
        }

        resp = self._client.post(url, json=body)
        self._client.raise_for_status(resp, context="X API")

        return resp.json()

    def _parse_search_response(
        self, query: str, product: str, data: dict
    ) -> XSearchResponse:
        """Parse GraphQL search response into model."""
        tweets: List[XTweet] = []
        cursor_top = None
        cursor_bottom = None

        try:
            instructions = (
                data["data"]["search_by_raw_query"]["search_timeline"]
                ["timeline"]["instructions"]
            )
        except (KeyError, TypeError):
            logger.warning("Unexpected response structure: %s", json.dumps(data)[:300])
            return XSearchResponse(query=query, product=product)

        for instruction in instructions:
            entries = instruction.get("entries", [])
            if not entries:
                add_entries = instruction.get("addEntries", {})
                entries = add_entries.get("entries", [])

            for entry in entries:
                entry_id = entry.get("entryId", "")

                # Cursor entries
                if entry_id.startswith("cursor-top"):
                    cursor_top = entry.get("content", {}).get("value")
                    continue
                if entry_id.startswith("cursor-bottom"):
                    cursor_bottom = entry.get("content", {}).get("value")
                    continue

                # Tweet entries
                if entry_id.startswith("tweet-"):
                    tweet = self._extract_tweet(entry)
                    if tweet:
                        tweets.append(tweet)
                    continue

                # Module entries (e.g. People module in Top results)
                content = entry.get("content", {})
                if content.get("__typename") == "TimelineTimelineModule":
                    items = content.get("items", [])
                    for item in items:
                        item_entry = item.get("item", item)
                        tweet = self._extract_tweet_from_content(
                            item_entry.get("itemContent", {})
                        )
                        if tweet:
                            tweets.append(tweet)

        return XSearchResponse(
            query=query,
            product=product,
            tweets=tweets,
            cursor_top=cursor_top,
            cursor_bottom=cursor_bottom,
        )

    def _extract_tweet(self, entry: dict) -> Optional[XTweet]:
        """Extract tweet from a timeline entry."""
        try:
            content = entry["content"]
            item_content = content.get("itemContent", content)
            return self._extract_tweet_from_content(item_content)
        except (KeyError, TypeError):
            return None

    def _extract_tweet_from_content(self, item_content: dict) -> Optional[XTweet]:
        """Extract tweet from itemContent dict."""
        try:
            tweet_results = item_content.get("tweet_results", {})
            result = tweet_results.get("result", {})

            # Handle tombstone / unavailable tweets
            typename = result.get("__typename", "")
            if typename == "TweetWithVisibilityResults":
                result = result.get("tweet", {})
            elif typename not in ("Tweet", ""):
                return None

            legacy = result.get("legacy", {})
            if not legacy:
                return None

            tweet_id = legacy.get("id_str", result.get("rest_id", ""))
            full_text = legacy.get("full_text", "")
            if not tweet_id:
                return None

            # Author
            author = None
            core = result.get("core", {})
            user_result = core.get("user_results", {}).get("result", {})
            user_legacy = user_result.get("legacy", {})
            if user_legacy:
                author = XUser(
                    id=user_result.get("rest_id", user_legacy.get("id_str", "")),
                    screen_name=user_legacy.get("screen_name", ""),
                    name=user_legacy.get("name", ""),
                    followers_count=user_legacy.get("followers_count", 0),
                    following_count=user_legacy.get("friends_count", 0),
                    is_blue_verified=user_result.get("is_blue_verified", False),
                    profile_image_url=user_legacy.get("profile_image_url_https"),
                )

            # Media
            media_urls = []
            media_entities = legacy.get("extended_entities", {}).get("media", [])
            for m in media_entities:
                if m.get("type") == "video":
                    variants = m.get("video_info", {}).get("variants", [])
                    mp4s = [v for v in variants if v.get("content_type") == "video/mp4"]
                    if mp4s:
                        best = max(mp4s, key=lambda v: v.get("bitrate", 0))
                        media_urls.append(best["url"])
                elif m.get("type") in ("photo", "animated_gif"):
                    media_urls.append(m.get("media_url_https", ""))

            # View count
            views = result.get("views", {})
            view_count = views.get("count") if views else None

            # Quote tweet
            quoted_tweet = None
            is_quote = bool(legacy.get("is_quote_status"))
            if is_quote:
                qt_result = result.get("quoted_status_result", {}).get("result", {})
                if qt_result:
                    qt_legacy = qt_result.get("legacy", {})
                    if qt_legacy:
                        qt_author = None
                        qt_core = qt_result.get("core", {})
                        qt_user = (
                            qt_core.get("user_results", {})
                            .get("result", {})
                            .get("legacy", {})
                        )
                        if qt_user:
                            qt_author = XUser(
                                id=qt_user.get("id_str", ""),
                                screen_name=qt_user.get("screen_name", ""),
                                name=qt_user.get("name", ""),
                                followers_count=qt_user.get("followers_count", 0),
                                following_count=qt_user.get("friends_count", 0),
                            )
                        quoted_tweet = XTweet(
                            id=qt_legacy.get("id_str", ""),
                            full_text=qt_legacy.get("full_text", ""),
                            created_at=qt_legacy.get("created_at"),
                            author=qt_author,
                            favorite_count=qt_legacy.get("favorite_count", 0),
                            retweet_count=qt_legacy.get("retweet_count", 0),
                            reply_count=qt_legacy.get("reply_count", 0),
                        )

            permalink = None
            if author and author.screen_name:
                permalink = f"https://x.com/{author.screen_name}/status/{tweet_id}"

            return XTweet(
                id=tweet_id,
                full_text=full_text,
                created_at=legacy.get("created_at"),
                author=author,
                favorite_count=legacy.get("favorite_count", 0),
                retweet_count=legacy.get("retweet_count", 0),
                reply_count=legacy.get("reply_count", 0),
                bookmark_count=legacy.get("bookmark_count", 0),
                view_count=view_count,
                lang=legacy.get("lang"),
                url=permalink,
                media_urls=media_urls,
                is_retweet=full_text.startswith("RT @"),
                is_quote=is_quote,
                quoted_tweet=quoted_tweet,
            )
        except (KeyError, TypeError) as e:
            logger.debug("Failed to extract tweet: %s", e)
            return None
