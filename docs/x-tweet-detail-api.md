# X (Twitter) Tweet Detail API 接口文档

## 概述

- 网站地址: https://x.com
- API 域名: `https://x.com/i/api/graphql/` (主), `https://api.x.com/` (部分设置接口)
- 认证方式: Bearer Token (静态固定值) + CSRF Token (ct0 cookie)
- 响应格式: JSON，GraphQL timeline 架构

## 公共请求头

| Header | 值 | 说明 |
|--------|-----|------|
| `authorization` | `Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA` | 固定 Bearer Token，所有接口通用 |
| `x-csrf-token` | `{ct0 cookie 值}` | CSRF 防护，值等于 `ct0` cookie |
| `x-twitter-auth-type` | `OAuth2Session` | 认证类型标识 |
| `x-twitter-active-user` | `yes` | 标识活跃用户 |
| `x-twitter-client-language` | `en` | 客户端语言 |
| `content-type` | `application/json` | 内容类型 |
| `cookie` | `auth_token=...; ct0=...` | 登录态 cookie，关键字段为 `auth_token` 和 `ct0` |

**速率限制响应头：**
- `x-rate-limit-limit`: 窗口内最大请求数（TweetDetail 为 150，TweetResultByRestId 为 500）
- `x-rate-limit-remaining`: 剩余请求数
- `x-rate-limit-reset`: 窗口重置 Unix 时间戳

---

## 接口清单

### 1. TweetDetail（推文详情 + 回复） GET [重要度: ⭐⭐⭐]

- **URL**: `GET https://x.com/i/api/graphql/9rs110LSoPARDs61WOBZ7A/TweetDetail`
- **queryId**: `9rs110LSoPARDs61WOBZ7A`（可能随版本变化，需从页面 JS bundle 提取）
- **速率限制**: 150次/15min

#### 请求参数（全部 URL query string，JSON 编码）

**variables（必填）：**

```json
{
  "focalTweetId": "2032398902683705408",
  "with_rux_injections": false,
  "rankingMode": "Relevance",
  "includePromotedContent": true,
  "withCommunity": true,
  "withQuickPromoteEligibilityTweetFields": true,
  "withBirdwatchNotes": true,
  "withVoice": true
}
```

**分页时追加 cursor 字段：**

```json
{
  "focalTweetId": "2032398902683705408",
  "cursor": "<bottomCursorValue 或 showMoreCursorValue>",
  "with_rux_injections": false,
  "rankingMode": "Relevance",
  "includePromotedContent": true,
  "withCommunity": true,
  "withQuickPromoteEligibilityTweetFields": true,
  "withBirdwatchNotes": true,
  "withVoice": true
}
```

**features（功能开关，完整版）：**

```json
{
  "rweb_video_screen_enabled": false,
  "profile_label_improvements_pcf_label_in_post_enabled": true,
  "responsive_web_profile_redirect_enabled": false,
  "rweb_tipjar_consumption_enabled": false,
  "verified_phone_label_enabled": false,
  "creator_subscriptions_tweet_preview_api_enabled": true,
  "responsive_web_graphql_timeline_navigation_enabled": true,
  "responsive_web_graphql_skip_user_profile_image_extensions_enabled": false,
  "premium_content_api_read_enabled": false,
  "communities_web_enable_tweet_community_results_fetch": true,
  "c9s_tweet_anatomy_moderator_badge_enabled": true,
  "responsive_web_grok_analyze_button_fetch_trends_enabled": false,
  "responsive_web_grok_analyze_post_followups_enabled": true,
  "responsive_web_jetfuel_frame": true,
  "responsive_web_grok_share_attachment_enabled": true,
  "responsive_web_grok_annotations_enabled": true,
  "articles_preview_enabled": true,
  "responsive_web_edit_tweet_api_enabled": true,
  "graphql_is_translatable_rweb_tweet_is_translatable_enabled": true,
  "view_counts_everywhere_api_enabled": true,
  "longform_notetweets_consumption_enabled": true,
  "responsive_web_twitter_article_tweet_consumption_enabled": true,
  "tweet_awards_web_tipping_enabled": false,
  "content_disclosure_indicator_enabled": true,
  "content_disclosure_ai_generated_indicator_enabled": true,
  "responsive_web_grok_show_grok_translated_post": false,
  "responsive_web_grok_analysis_button_from_backend": true,
  "post_ctas_fetch_enabled": true,
  "freedom_of_speech_not_reach_fetch_enabled": true,
  "standardized_nudges_misinfo": true,
  "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": true,
  "longform_notetweets_rich_text_read_enabled": true,
  "longform_notetweets_inline_media_enabled": false,
  "responsive_web_grok_image_annotation_enabled": true,
  "responsive_web_grok_imagine_annotation_enabled": true,
  "responsive_web_grok_community_note_auto_translation_is_enabled": false,
  "responsive_web_enhance_cards_enabled": false
}
```

**fieldToggles：**

```json
{
  "withArticleRichContentState": true,
  "withArticlePlainText": false,
  "withArticleSummaryText": false,
  "withArticleVoiceOver": false,
  "withGrokAnalyze": false,
  "withDisallowedReplyControls": false
}
```

#### 响应数据路径

```
data.threaded_conversation_with_injections_v2.instructions[]
  ├── TimelineClearCache          (首次加载，无数据)
  ├── TimelineAddEntries          (核心数据，含推文和回复)
  │   └── entries[]
  │       ├── [0] TimelineTimelineItem   → 主推文（focal tweet）
  │       ├── [1..N-1] TimelineTimelineModule → 对话线程（回复）
  │       └── [N] TimelineTimelineCursor → 分页游标 (Bottom)
  └── TimelineTerminateTimeline   (首次加载，标记结束方向)
```

#### entries 条目结构

**主推文条目（TimelineTimelineItem）：**

```json
{
  "entryId": "tweet-2032398902683705408",
  "sortIndex": "2032647619422977999",
  "content": {
    "entryType": "TimelineTimelineItem",
    "__typename": "TimelineTimelineItem",
    "itemContent": {
      "itemType": "TimelineTweet",
      "__typename": "TimelineTweet",
      "tweet_results": {
        "result": { }
      }
    }
  }
}
```

**对话线程条目（TimelineTimelineModule）：**

```json
{
  "entryId": "conversationthread-2032423160067530950",
  "sortIndex": "...",
  "content": {
    "entryType": "TimelineTimelineModule",
    "__typename": "TimelineTimelineModule",
    "displayType": "VerticalConversation",
    "items": [
      {
        "entryId": "conversationthread-{threadId}-tweet-{tweetId}",
        "treeIndex": 0,
        "item": {
          "itemContent": {
            "itemType": "TimelineTweet",
            "tweet_results": { "result": { } }
          }
        }
      },
      {
        "entryId": "conversationthread-{threadId}-tweet-{replyId}",
        "treeIndex": 1,
        "item": { }
      },
      {
        "entryId": "conversationthread-{threadId}-cursor-showmore-{sortIndex}",
        "treeIndex": 2,
        "item": {
          "itemContent": {
            "itemType": "TimelineTimelineCursor",
            "cursorType": "ShowMore",
            "value": "<showMoreCursorValue>"
          }
        }
      }
    ]
  }
}
```

**分页游标条目（Bottom Cursor）：**

注意：Bottom Cursor 的 value 在 `content` 层（不是 `itemContent`）。

```json
{
  "entryId": "cursor-bottom-2032647619422977767",
  "content": {
    "__typename": "TimelineTimelineCursor",
    "entryType": "TimelineTimelineCursor",
    "cursorType": "Bottom",
    "value": "DAAKCgABHDVqPY0__uU..."
  }
}
```

#### Tweet 对象结构（核心字段）

```json
{
  "__typename": "Tweet",
  "rest_id": "2032398902683705408",
  "core": {
    "user_results": {
      "result": {
        "__typename": "User",
        "rest_id": "1461305890892570628",
        "id": "VXNlcjoxNDYxMzA1ODkwODkyNTcwNjI4",
        "is_blue_verified": true,
        "legacy": {
          "screen_name": "slow_developer",
          "name": "Haider.",
          "description": "together, we build an intelligent future.",
          "followers_count": 64295,
          "friends_count": 3566,
          "statuses_count": 32464,
          "profile_image_url_https": "https://pbs.twimg.com/profile_images/.../normal.jpg",
          "profile_banner_url": "https://pbs.twimg.com/profile_banners/..."
        }
      }
    }
  },
  "legacy": {
    "id_str": "2032398902683705408",
    "full_text": "推文正文（完整，含 @mention 和 t.co 短链）",
    "created_at": "Fri Mar 13 10:10:33 +0000 2026",
    "conversation_id_str": "2032398902683705408",
    "in_reply_to_status_id_str": null,
    "in_reply_to_user_id_str": null,
    "user_id_str": "1461305890892570628",
    "lang": "en",
    "reply_count": 178,
    "retweet_count": 386,
    "favorite_count": 1932,
    "quote_count": 11,
    "bookmark_count": 96,
    "is_quote_status": false,
    "favorited": false,
    "retweeted": false,
    "bookmarked": false,
    "entities": {
      "hashtags": [],
      "user_mentions": [
        { "id_str": "44196397", "screen_name": "elonmusk", "name": "Elon Musk", "indices": [0, 10] }
      ],
      "urls": [
        { "url": "https://t.co/xxx", "expanded_url": "https://...", "display_url": "example.com" }
      ],
      "symbols": [],
      "timestamps": []
    },
    "extended_entities": {
      "media": [ ]
    },
    "display_text_range": [0, 266],
    "possibly_sensitive": false
  },
  "views": {
    "count": "490348",
    "state": "EnabledWithCount"
  },
  "edit_control": {
    "edit_tweet_ids": ["2032398902683705408"],
    "editable_until_msecs": "1773400233000",
    "edits_remaining": "5",
    "is_edit_eligible": true
  },
  "has_birdwatch_notes": false,
  "is_translatable": false,
  "source": "<a href=\"http://twitter.com/download/android\">Twitter for Android</a>"
}
```

#### 关键字段说明

| 字段路径 | 类型 | 说明 |
|---------|------|------|
| `legacy.full_text` | string | 推文正文，含 @mention 和 t.co 短链 |
| `legacy.conversation_id_str` | string | 对话线索根推文 ID |
| `legacy.in_reply_to_status_id_str` | string\|null | 回复的目标推文 ID |
| `legacy.in_reply_to_user_id_str` | string\|null | 回复的目标用户 ID |
| `legacy.entities.urls[]` | array | t.co 短链列表，含 expanded_url |
| `legacy.extended_entities.media[]` | array | 媒体附件（图片/视频/GIF） |
| `views.count` | string | 浏览量（字符串格式） |
| `core.user_results.result` | object | 作者完整用户对象 |

---

### 2. TweetResultByRestId（单推文快速获取） GET [重要度: ⭐⭐]

- **URL**: `GET https://x.com/i/api/graphql/-pZk1GFMnSjUsrsS2vyXNA/TweetResultByRestId`
- **queryId**: `-pZk1GFMnSjUsrsS2vyXNA`
- **速率限制**: 500次/15min（比 TweetDetail 宽松得多）
- **用途**: 快速获取单条推文的完整元数据，不含回复/对话线程

**variables：**

```json
{
  "tweetId": "2032398902683705408",
  "includePromotedContent": true,
  "withBirdwatchNotes": true,
  "withVoice": true,
  "withCommunity": true
}
```

**响应结构：**

```json
{
  "data": {
    "tweetResult": {
      "result": { }
    }
  }
}
```

区别于 TweetDetail：返回路径为 `data.tweetResult.result`（而非 timeline entries）。用户对象包含更多字段（`professional`、`affiliates_highlighted_label`、`relationship_perspectives` 等）。

---

### 3. 分页机制

#### 3.1 底部分页（Bottom Cursor）— 加载更多回复

对话页面每次返回约 28-29 个对话线程，共约 3 页（178 条回复）。

游标位置：最后一个 entry 的 `content` 层（注意不是 `itemContent`）：

```python
entries = instructions["TimelineAddEntries"].entries
cursor_entry = entries[-1]
# cursor_entry.content.cursorType == "Bottom"
cursor_value = cursor_entry["content"]["value"]
```

继续分页时，在 variables 中追加 `"cursor": cursor_value`，重新发送相同请求。

**各页响应的 instruction 类型：**

| 页码 | instruction 类型列表 |
|------|---------------------|
| 第1页 | `["TimelineClearCache", "TimelineAddEntries", "TimelineTerminateTimeline"]` |
| 第2页+ | `["TimelineAddEntries"]` |

第2页约返回 40 个条目。

#### 3.2 线程展开（ShowMore Cursor）— 展开嵌套回复

当一个对话线程中嵌套超过 2 条连续回复时，第3个 item 为 ShowMore cursor：

```python
# ShowMore cursor 位于 item.itemContent 层
show_more_item = thread_entry["content"]["items"][-1]
cursor_value = show_more_item["item"]["itemContent"]["value"]
cursor_type  = show_more_item["item"]["itemContent"]["cursorType"]  # "ShowMore"
```

使用 ShowMore cursor 请求（variables 中加 `cursor`）时，响应 instruction 类型为 **`TimelineAddToModule`**（区别于普通分页的 `TimelineAddEntries`）：

```json
{
  "type": "TimelineAddToModule",
  "moduleEntryId": "conversationthread-2032423160067530950",
  "moduleItems": [
    {
      "entryId": "conversationthread-...-tweet-{tweetId}",
      "treeIndex": 2,
      "item": {
        "itemContent": {
          "itemType": "TimelineTweet",
          "tweet_results": { "result": { } }
        }
      }
    }
  ]
}
```

`moduleEntryId` 指向要追加新 items 的线程条目 entryId。

---

### 4. 媒体结构

媒体数据位于 `legacy.extended_entities.media[]`，同时 `legacy.entities.urls[]` 中有对应的 t.co 短链。

#### 4.1 图片（photo）

```json
{
  "type": "photo",
  "id_str": "2032413522349494272",
  "media_key": "3_2032413522349494272",
  "media_url_https": "https://pbs.twimg.com/media/HDSVVJRXkAAsO7m.jpg",
  "url": "https://t.co/P9W5iQAknz",
  "display_url": "pic.x.com/P9W5iQAknz",
  "expanded_url": "https://x.com/OpulentByte/status/2032413533518836146/photo/1",
  "indices": [100, 123],
  "sizes": {
    "thumb":  { "w": 150,  "h": 150,  "resize": "crop" },
    "small":  { "w": 680,  "h": 302,  "resize": "fit" },
    "medium": { "w": 1200, "h": 532,  "resize": "fit" },
    "large":  { "w": 2047, "h": 908,  "resize": "fit" }
  }
}
```

**图片 URL 拼接规则：**
- 默认（medium）：`{media_url_https}`
- 指定尺寸：`{media_url_https}?name=large`（small/medium/large/orig）
- 格式转换：`{media_url_https}?format=webp&name=medium`

#### 4.2 视频（video）

```json
{
  "type": "video",
  "id_str": "2032412240339664896",
  "media_key": "13_2032412240339664896",
  "media_url_https": "https://pbs.twimg.com/amplify_video_thumb/2032412240339664896/img/Smd7HNT3nrSEMJ3o.jpg",
  "url": "https://t.co/...",
  "display_url": "pic.x.com/...",
  "expanded_url": "https://x.com/.../video/1",
  "sizes": { },
  "video_info": {
    "aspect_ratio": [1, 1],
    "duration_millis": 70938,
    "variants": [
      {
        "content_type": "application/x-mpegURL",
        "url": "https://video.twimg.com/amplify_video/2032412240339664896/pl/yC7edfa0rlmpHdDa.m3u8"
      },
      {
        "content_type": "video/mp4",
        "bitrate": 432000,
        "url": "https://video.twimg.com/amplify_video/2032412240339664896/vid/avc1/320x320/iRamYWhNlnbiWSye.mp4"
      },
      {
        "content_type": "video/mp4",
        "bitrate": 832000,
        "url": "https://video.twimg.com/amplify_video/2032412240339664896/vid/avc1/540x540/ViRW8TGrZD6Wz4aY.mp4"
      },
      {
        "content_type": "video/mp4",
        "bitrate": 1280000,
        "url": "https://video.twimg.com/amplify_video/2032412240339664896/vid/avc1/720x720/8Gk9kuxwWSdwkHhg.mp4"
      },
      {
        "content_type": "video/mp4",
        "bitrate": 8768000,
        "url": "https://video.twimg.com/amplify_video/2032412240339664896/vid/avc1/1080x1080/raNRHXt5XZgnUXzB.mp4"
      }
    ]
  }
}
```

**视频 URL 说明：**
- `media_url_https`：视频封面缩略图（JPG），域名为 `pbs.twimg.com/amplify_video_thumb/`
- `video_info.variants`：多码率版本列表
  - HLS 流（m3u8）：`content_type = "application/x-mpegURL"`，无 `bitrate` 字段
  - MP4 直链：`content_type = "video/mp4"`，含 `bitrate`（单位 bps）
  - URL 域名：`video.twimg.com`
- **提取最高质量**：过滤 `video/mp4`，按 `bitrate` 降序取第一个

#### 4.3 GIF（animated_gif）

结构与视频相同，但：
- `type`: `"animated_gif"`
- `video_info.variants`：只有一个 MP4 变体，无 `bitrate` 字段，无 HLS
- `video_info.duration_millis`: 不存在（GIF 循环播放）

---

## 接口调用链路

```
用户访问 /username/status/{tweetId}
    │
    ├── TweetResultByRestId (快速获取推文元数据，不含回复)
    │   └── data.tweetResult.result → Tweet 对象
    │
    └── TweetDetail (主接口，推文 + 完整对话线程)
        └── data.threaded_conversation_with_injections_v2.instructions
            ├── entries[0] → focal tweet (主推文)
            ├── entries[1..N-1] → conversationthread-xxx (回复线程)
            │   ├── items[0] → 直接回复（in_reply_to = focalTweetId）
            │   ├── items[1] → 嵌套回复（in_reply_to = items[0].id）
            │   └── items[2] → ShowMore cursor (如有更多嵌套回复)
            │       └── → TweetDetail (cursor=showMoreValue)
            │           └── TimelineAddToModule → 追加到 moduleEntryId 线程
            └── entries[-1] → Bottom cursor (content.value, 非 itemContent.value)
                └── → TweetDetail (cursor=bottomCursorValue)
                    └── 加载更多对话线程（第2页起无 ClearCache 指令）
```

---

## 关键发现

1. **queryId 随版本变化**：`9rs110LSoPARDs61WOBZ7A`（TweetDetail）和 `-pZk1GFMnSjUsrsS2vyXNA`（TweetResultByRestId）为当前版本值，X 定期更新 JS bundle 时会改变。提取方式：搜索 `https://abs.twimg.com/responsive-web/client-web/main.*.js` 中的 `queryId` 字段。

2. **两种游标的 value 路径不同**：
   - Bottom Cursor：`entries[-1].content.value`（在顶层 `content` 下）
   - ShowMore Cursor：`items[-1].item.itemContent.value`（在 `itemContent` 下）

3. **ShowMore 响应使用 TimelineAddToModule**：区别于普通分页的 `TimelineAddEntries`。响应含 `moduleEntryId` 字段，指向要追加新 items 的线程 entryId。

4. **Bearer Token 全局固定**：值 `AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA` 是 X Web 客户端的公开 token，所有 X.com 网页版请求均使用此固定值。但调用 API 仍需有效的 `auth_token` + `ct0` cookie。

5. **速率限制差异**：TweetDetail 为 150次/15min（严格），TweetResultByRestId 为 500次/15min（宽松）。仅需推文元数据时优先使用后者。

6. **视频 URL 域名**：视频文件在 `video.twimg.com`，封面缩略图在 `pbs.twimg.com/amplify_video_thumb/`。原生推文视频路径含 `tweet_video`，转载视频（amplify）路径含 `amplify_video`。

7. **in_reply_to 关系链**：`legacy.in_reply_to_status_id_str` 和 `legacy.in_reply_to_user_id_str` 可重建完整回复树。`conversation_id_str` 始终指向根推文 ID（对话入口点）。

8. **rankingMode 参数**：首次加载用 `"Relevance"`（相关度排序），可改为 `"Recency"` 获取最新回复。
