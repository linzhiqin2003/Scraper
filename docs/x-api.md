# X (Twitter) API 接口文档

## 概述

- **网站地址**: https://x.com/home
- **API 域名**:
  - `https://x.com` — 主 API（GraphQL + REST，通过 `/i/api/` 路径）
  - `https://api.x.com` — 旧版 REST API（account/settings、live_pipeline 等）
  - `https://ads-api.x.com` — 广告 API
  - `https://proxsee.pscp.tv` — Periscope/直播 API
  - `https://video.twimg.com` — 视频 CDN（HLS/DASH 分片）
  - `https://abs.twimg.com` — 静态资源（动画 JSON 等）
- **认证方式**: Bearer Token（公共固定 Token）+ Cookie（`auth_token`）+ CSRF Token（`x-csrf-token` = `ct0` Cookie 值）
- **CORS**: `Access-Control-Allow-Origin: https://x.com`，`Access-Control-Allow-Credentials: true`

### 公共请求头

| Header | 值 | 说明 |
|--------|-----|------|
| `authorization` | `Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA` | 公共 Bearer Token（硬编码，所有请求均使用此 Token） |
| `x-csrf-token` | `{ct0 cookie 值}` | CSRF 防护，值与 `ct0` Cookie 完全相同 |
| `x-twitter-auth-type` | `OAuth2Session` | 登录态标识（未登录时无此头） |
| `x-twitter-active-user` | `yes` | 标识活跃用户 |
| `x-twitter-client-language` | `en` | 客户端语言 |
| `x-client-transaction-id` | `{随机 base64}` | 每次请求唯一事务 ID |
| `content-type` | `application/json` | GET/JSON 请求 |

### 认证 Cookies

| Cookie | 说明 |
|--------|------|
| `auth_token` | 登录身份令牌（核心认证 Cookie） |
| `ct0` | CSRF Token（同时作为 `x-csrf-token` 请求头的值） |
| `twid` | 用户 ID（格式：`u%3D{user_id}`） |
| `kdt` | 设备绑定令牌 |
| `att` | 登录流程令牌（短效） |
| `guest_id` | 访客 ID（未登录也有） |

### 响应格式

GraphQL 接口统一返回：
```json
{
  "data": {
    "{operation_name}": { ... }
  }
}
```
REST 接口直接返回业务对象。所有响应均为 `application/json`，使用 Cloudflare + Envoy 代理，通过 gzip 压缩。

### 限速

通过 `X-Rate-Limit-Limit`、`X-Rate-Limit-Remaining`、`X-Rate-Limit-Reset` 响应头返回。常见限额：
- HomeTimeline：500次/15分钟
- TweetDetail：150次/15分钟
- SearchTimeline：50次/15分钟
- badge_count：180次/15分钟

---

## 一、首页 (https://x.com/home)

### 1.1 首页推荐时间线 (For You) GET [重要度: ⭐⭐⭐]

```
GET https://x.com/i/api/graphql/-HtXlyhboD0-JLXJ-xo9Vg/HomeTimeline
```

**用途**: 获取"For You"（为你推荐）标签页的推文列表，首页加载时触发。

**Query Parameters**:

```json
variables={
  "count": 20,
  "includePromotedContent": true,
  "requestContext": "launch",
  "withCommunity": true
}
features={
  "rweb_video_screen_enabled": false,
  "profile_label_improvements_pcf_label_in_post_enabled": true,
  "responsive_web_graphql_timeline_navigation_enabled": true,
  "articles_preview_enabled": true,
  "responsive_web_edit_tweet_api_enabled": true,
  "view_counts_everywhere_api_enabled": true,
  // ... 约30个 feature flags
}
```

**参数说明**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `count` | number | 是 | 每页推文数量，默认 20 |
| `includePromotedContent` | bool | 是 | 是否包含广告推文 |
| `requestContext` | string | 是 | `launch`（首次加载）或 `pull_to_refresh`（下拉刷新）|
| `withCommunity` | bool | 是 | 是否包含社区内容 |
| `cursor` | string | 否 | 分页游标，下一页时传入 `cursor-bottom` 的值 |
| `seenTweetIds` | string[] | 否 | 已展示过的推文 ID 列表（去重） |

**响应关键字段**:

| 字段路径 | 类型 | 说明 |
|------|------|------|
| `data.home.home_timeline_urt.instructions` | array | 时间线指令列表 |
| `instructions[].entries` | array | 推文条目列表 |
| `entries[].entryId` | string | 条目 ID（如 `tweet-{id}` 或 `cursor-bottom-{sortIndex}`）|
| `entries[].sortIndex` | string | 排序索引（用于游标分页） |
| `entries[].content.itemContent.tweet_results.result` | object | 推文完整数据 |
| `result.legacy.full_text` | string | 推文正文 |
| `result.legacy.favorite_count` | number | 点赞数 |
| `result.legacy.retweet_count` | number | 转推数 |
| `result.legacy.reply_count` | number | 回复数 |
| `result.legacy.bookmark_count` | number | 收藏数 |
| `result.views.count` | string | 浏览量 |
| `result.legacy.created_at` | string | 发布时间（RFC2822 格式）|
| `result.legacy.id_str` | string | 推文 ID |
| `result.legacy.user_id_str` | string | 作者 ID |
| `result.core.user_results.result` | object | 作者完整信息 |
| `result.core.user_results.result.legacy.screen_name` | string | 用户名（@handle）|
| `result.core.user_results.result.legacy.followers_count` | number | 粉丝数 |

**分页机制**: 响应的 `entries` 中会有 `entryId` 为 `cursor-bottom-*` 的条目，其 `content.value` 即为下一页游标，下次请求将其作为 `cursor` 参数传入。

**响应示例**（精简）:
```json
{
  "data": {
    "home": {
      "home_timeline_urt": {
        "instructions": [{
          "entries": [
            {
              "entryId": "tweet-2032278777934582072",
              "sortIndex": "2032413235872792576",
              "content": {
                "__typename": "TimelineTimelineItem",
                "itemContent": {
                  "__typename": "TimelineTweet",
                  "tweet_results": {
                    "result": {
                      "legacy": {
                        "full_text": "距离 OpenAI 发布 GPT-5.4 仅仅过去了几天...",
                        "favorite_count": 155,
                        "retweet_count": 34,
                        "reply_count": 3,
                        "views": {"count": "84076"}
                      },
                      "core": {
                        "user_results": {
                          "result": {
                            "legacy": {"screen_name": "FinanceYF5", "name": "AI Will"}
                          }
                        }
                      }
                    }
                  }
                }
              }
            },
            {
              "entryId": "cursor-bottom-2032413235872792573",
              "content": {"cursorType": "Bottom", "value": "DAABCgAB..."}
            }
          ]
        }]
      }
    }
  }
}
```

---

### 1.2 首页关注时间线 (Following) POST [重要度: ⭐⭐⭐]

```
POST https://x.com/i/api/graphql/ulQKqowrFU94KfUAZqgGvg/HomeLatestTimeline
```

**用途**: 获取"Following"标签页的推文列表（按时间倒序），点击 Following 标签时触发。

**Request Body**:

```json
{
  "variables": {
    "count": 20,
    "enableRanking": false,
    "includePromotedContent": true,
    "requestContext": "launch",
    "seenTweetIds": ["2032347159539191918", "2032278777934582072"]
  },
  "features": { "...同 HomeTimeline 的 features..." },
  "queryId": "ulQKqowrFU94KfUAZqgGvg"
}
```

**参数说明**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `count` | number | 是 | 每页数量 |
| `enableRanking` | bool | 是 | `false` = 时间倒序，`true` = 算法排序 |
| `includePromotedContent` | bool | 是 | 是否包含广告 |
| `seenTweetIds` | string[] | 否 | 已看过的推文 ID，用于去重 |
| `cursor` | string | 否 | 分页游标 |

**响应结构**: 与 HomeTimeline 相同，路径 `data.home.home_timeline_urt`。

---

### 1.3 右侧栏 Explore Sidebar（热点趋势）GET [重要度: ⭐⭐]

```
GET https://x.com/i/api/graphql/bUfCUHvP9Wmuxwur02pbdQ/ExploreSidebar
```

**用途**: 获取右侧栏"What's happening"趋势话题列表。

**Query Parameters**: `variables={}` + `features={...通用 features...}`

**响应关键字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `data.explore_sidebar.timeline.instructions[].entries` | array | 趋势条目 |
| `entry.itemContent.name` | string | 趋势话题名称 |
| `entry.itemContent.trend_metadata.domain_context` | string | 分类（如 "Politics · Trending"）|
| `entry.itemContent.trend_url.url` | string | 点击跳转的 DeepLink URL |

**响应示例**（精简）:
```json
{
  "data": {
    "explore_sidebar": {
      "timeline": {
        "instructions": [{
          "entries": [{
            "itemContent": {
              "__typename": "TimelineTrend",
              "name": "Bank of England",
              "trend_metadata": {
                "domain_context": "Trending in United Kingdom"
              }
            }
          }]
        }]
      }
    }
  }
}
```

---

### 1.4 右侧栏用户推荐 GET [重要度: ⭐⭐]

```
GET https://x.com/i/api/graphql/TDtrShaKKs-vFLCuz2jLdA/SidebarUserRecommendations
```

**用途**: 获取"Who to follow"推荐关注用户列表。

**Query Parameters**:
```
variables={"profileUserId": "1806731991016210436"}
features={...精简版 features...}
```

**参数说明**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `profileUserId` | string | 是 | 当前登录用户 ID |

**响应关键字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `data.sidebar_user_recommendations` | array | 推荐用户列表 |
| `[].token` | string | 分页 token |
| `[].user_results.result.legacy.screen_name` | string | 推荐用户名 |
| `[].user_results.result.legacy.followers_count` | number | 粉丝数 |
| `[].user_results.result.is_blue_verified` | bool | 是否蓝标认证 |

---

### 1.5 已固定时间线列表 GET [重要度: ⭐⭐]

```
GET https://x.com/i/api/graphql/HaJt3PXnvM-jRdih6zRSxw/PinnedTimelines
```

**用途**: 获取首页顶部标签栏（For You、Following 之外）用户自定义固定的时间线（如社区 Community、列表 List）。

**Query Parameters**: `variables={}` + `features={...}`

**响应关键字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `data.pinned_timelines.pinned_timelines` | array | 固定时间线列表 |
| `[0].__typename` | string | `CommunityPinnedTimeline` 或 `ListPinnedTimeline` |
| `[0].community_results.result.id_str` | string | 社区 ID |
| `[0].community_results.result.name` | string | 社区名称 |
| `[0].community_results.result.member_count` | number | 成员数 |
| `[0].community_results.result.is_pinned` | bool | 是否已固定 |

---

### 1.6 AI 趋势故事查询 GET [重要度: ⭐]

```
GET https://x.com/i/api/graphql/I3V_Tt32aTZdw7cBdKUJbg/useStoryTopicQuery
```

**用途**: 获取右侧栏"Today's News"AI 生成的热点话题卡片。

**Query Parameters**:
```
variables={"rest_id": "For You", "limit": 3}
```

**响应关键字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `data.story_topic.stories.items` | array | 热点话题列表（最多 limit 个）|
| `[].trend_results.result.core.name` | string | 话题标题 |
| `[].trend_results.result.core.hook` | string | AI 生成的话题摘要 |
| `[].trend_results.result.core.category` | string | 分类（News/Other/Sports）|
| `[].trend_results.result.post_count` | string | 相关帖子数量 |
| `[].trend_results.result.social_proof` | array | 参与用户头像列表 |

---

### 1.7 未读消息角标数 GET [重要度: ⭐⭐]

```
GET https://x.com/i/api/2/badge_count/badge_count.json?supports_ntab_urt=1&include_xchat_count=1
```

**用途**: 获取通知/消息未读数量，用于导航栏角标显示，轮询接口（每 30 秒）。

**请求头**: 额外包含 `x-twitter-polling: true`

**响应示例**:
```json
{
  "ntab_unread_count": 1,
  "dm_unread_count": 0,
  "total_unread_count": 1,
  "is_from_urt": true,
  "xchat_unread_count": 0
}
```

---

### 1.8 Spaces 直播状态 GET [重要度: ⭐]

```
GET https://x.com/i/api/fleets/v1/fleetline?only_spaces=true
```

**用途**: 检查关注用户是否有进行中的 Spaces 语音直播。

**响应示例**:
```json
{
  "threads": [],
  "hydrated_threads": [],
  "refresh_delay_secs": 30
}
```

---

### 1.9 推送通知权限状态上报 PUT [重要度: ⭐]

```
PUT https://x.com/i/api/1.1/strato/column/None/{userId},{device},{permissionName}/clients/permissionsState
```

**用途**: 上报当前设备的推送通知授权状态。

**Request Body**:
```json
{
  "userId": "1806731991016210436",
  "deviceId": "Mac/Chrome",
  "permissionName": "pushNotifications",
  "clientApplicationId": "3033300",
  "clientVersion": "145",
  "osVersion": "Mac/Chrome",
  "timestampInMs": 1773400050276,
  "systemPermissionState": "Undetermined",
  "inAppPermissionState": "Off",
  "metadata": {}
}
```

---

### 1.10 Data Saver 模式查询 GET [重要度: ⭐]

```
GET https://x.com/i/api/graphql/xF6sXnKJfS2AOylzxRjf6A/DataSaverMode?variables={"device_id":"Mac/Chrome"}
```

**用途**: 查询当前设备的省流量模式设置。

---

### 1.11 Alt Text 提示偏好 GET [重要度: ⭐]

```
GET https://x.com/i/api/graphql/PFIxTk8owMoZgiMccP0r4g/getAltTextPromptPreference?variables={}
```

**用途**: 获取用户是否开启了图片 Alt Text 撰写提示功能。

---

### 1.12 订阅产品详情 GET [重要度: ⭐]

```
GET https://x.com/i/api/graphql/8DJ2_AR5lFiA1BeiPoSzPw/useSubscriptionProductDetailsQuery
```

**Query Parameters**:
```
variables={"stripeId": "V2ViU3Vic2NyaXB0aW9u...", "for_moment": null, "fetchPricesFromStripe": false}
features={"subscriptions_marketing_page_fetch_promotions": true}
```

**用途**: 查询 Premium（蓝V）订阅产品价格和详情，右侧栏 Subscribe 卡片使用。同一页面会并行发起多次（不同 stripeId 对应不同套餐）。

---

### 1.13 用户订阅状态查询 GET [重要度: ⭐]

```
GET https://x.com/i/api/graphql/SPJ9o9QzEK2l1Bh1vcgX6A/useFetchProductSubscriptionsQuery
```

**Query Parameters**:
```
variables={"fetchPrices": false}
features={"subscriptions_management_fetch_next_billing_time": true}
```

**用途**: 查询当前用户是否已订阅 Premium，响应 `data.viewer_v2` 包含订阅信息。

---

### 1.14 Hashflags 配置 GET [重要度: ⭐]

```
GET https://x.com/i/api/1.1/hashflags.json
```

**用途**: 获取话题标签（hashtag）对应的特殊图标配置（如品牌标签带 emoji 图标）。

---

### 1.15 广告曝光上报 POST [重要度: 低]

```
POST https://x.com/i/api/1.1/promoted_content/log.json
Content-Type: application/x-www-form-urlencoded
```

**Request Body**:
```
event=impression&impression_id={ad_impression_id}&epoch_ms={timestamp}
```

**用途**: 上报广告曝光事件，低价值埋点接口。

---

### 1.16 DM 设置查询 GET [重要度: ⭐]

```
GET https://x.com/i/api/graphql/zzeLdGlB0ZN6hiOYUIpDcQ/XChatDmSettingsQuery?variables={}
GET https://x.com/i/api/graphql/zCYojd6h_gVXYjFlaAk4bA/useDirectCallSetupQuery?variables={}
```

**用途**: 查询 DM 和语音通话功能设置。

---

## 二、推文详情页 (https://x.com/{username}/status/{tweetId})

### 2.1 推文线程详情 GET [重要度: ⭐⭐⭐]

```
GET https://x.com/i/api/graphql/9rs110LSoPARDs61WOBZ7A/TweetDetail
```

**用途**: 获取单条推文及其回复线程，打开推文详情页时触发。

**Query Parameters**:
```
variables={
  "focalTweetId": "2032393831879258610",
  "with_rux_injections": false,
  "rankingMode": "Relevance",
  "includePromotedContent": true,
  "withCommunity": true,
  "withQuickPromoteEligibilityTweetFields": true,
  "withBirdwatchNotes": true,
  "withVoice": true
}
fieldToggles={
  "withArticleRichContentState": true,
  "withArticlePlainText": false,
  "withGrokAnalyze": false,
  "withDisallowedReplyControls": false
}
```

**参数说明**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `focalTweetId` | string | 是 | 目标推文 ID |
| `rankingMode` | string | 否 | 回复排序：`Relevance`（相关度）或 `Recency`（最新）|
| `withBirdwatchNotes` | bool | 否 | 是否包含社区笔记（Community Notes）|

**响应关键字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `data.threaded_conversation_with_injections_v2.instructions` | array | 线程指令 |
| `entries[0]` | object | 焦点推文（第一条）|
| `entries[1...]` | object | 回复线程条目 |
| `content.itemContent.tweet_results.result.legacy` | object | 推文详细数据 |
| `result.legacy.video_info.variants` | array | 视频多码率变体（含 mp4 和 m3u8）|
| `result.has_birdwatch_notes` | bool | 是否有社区笔记 |
| `cursor-showmorethreads` 条目的 `value` | string | 加载更多回复的游标 |

**响应示例**（精简）:
```json
{
  "data": {
    "threaded_conversation_with_injections_v2": {
      "instructions": [{
        "entries": [
          {
            "entryId": "tweet-2032393831879258610",
            "content": {
              "itemContent": {
                "tweet_results": {
                  "result": {
                    "legacy": {
                      "full_text": "试用 Claude 的新功能...",
                      "reply_count": 2,
                      "favorite_count": 10,
                      "views": {"count": "2576"}
                    }
                  }
                }
              }
            }
          },
          {
            "entryId": "cursor-showmorethreads-2032413410682994687",
            "content": {
              "cursorType": "ShowMoreThreads",
              "value": "DAAKCgABHDSVOpR___0L..."
            }
          }
        ]
      }]
    }
  }
}
```

---

### 2.2 单条推文查询（by REST ID）GET [重要度: ⭐⭐]

```
GET https://x.com/i/api/graphql/-pZk1GFMnSjUsrsS2vyXNA/TweetResultByRestId
```

**用途**: 通过推文 ID 直接查询单条推文完整信息（不含回复线程），常用于 SSR 预渲染。

**Query Parameters**:
```
variables={
  "tweetId": "2032393831879258610",
  "includePromotedContent": true,
  "withBirdwatchNotes": true,
  "withVoice": true,
  "withCommunity": true
}
```

**响应结构**:
```json
{
  "data": {
    "tweetResult": {
      "result": {
        "__typename": "Tweet",
        "legacy": { "...推文字段..." },
        "core": { "user_results": { "result": { "...作者字段..." } } },
        "views": { "count": "2576", "state": "EnabledWithCount" }
      }
    }
  }
}
```

---

## 三、搜索页 (https://x.com/search)

### 3.1 搜索时间线 GET [重要度: ⭐⭐⭐]

```
GET https://x.com/i/api/graphql/oKkjeoNFNQN7IeK7AHYc0A/SearchTimeline
```

**queryId**: `oKkjeoNFNQN7IeK7AHYc0A`

**用途**: 搜索推文/用户/话题，支持多种产品类型（Top/Latest/People/Photos/Videos）。高级搜索（`/search-advanced`）、搜索结果页标签切换、下拉分页均复用同一接口。

**Query Parameters（完整）**:
```
variables={
  "rawQuery": "artificial intelligence",
  "count": 20,
  "querySource": "typed_query",
  "product": "Top",
  "withGrokTranslatedBio": false,
  "cursor": "<可选，翻页时传入>"
}
features={
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

**variables 参数说明**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `rawQuery` | string | 是 | 搜索查询字符串，支持高级搜索操作符（见下表）|
| `count` | number | 是 | 每页推文数量，默认 20 |
| `product` | string | 是 | 结果类型：`Top`（热门）/ `Latest`（最新）/ `People`（用户）/ `Photos`（图片）/ `Videos`（视频）|
| `querySource` | string | 否 | `typed_query`（手动输入）/ `trend_click`（热点点击）/ `recent_search_click`（最近搜索）|
| `withGrokTranslatedBio` | bool | 否 | 是否对用户简介做 Grok 翻译，默认 `false` |
| `cursor` | string | 否 | 翻页游标，来自上次响应 `cursor-bottom-*` 条目的 `value` |

**高级搜索查询操作符**（全部编码进 `rawQuery` 字段）:

| 操作符 | 示例 | 说明 |
|--------|------|------|
| 关键词 AND | `artificial intelligence` | 包含所有词（空格隔开）|
| 精确短语 | `"artificial intelligence"` | 包含完整短语 |
| OR | `AI OR robot` | 包含任意一词 |
| 排除 | `AI -ChatGPT` | 包含 AI 但不含 ChatGPT |
| `from:` | `from:openai` | 来自指定账号的推文 |
| `to:` | `to:openai` | 回复给指定账号的推文 |
| `@mention` | `@openai` | 提及指定账号 |
| `#hashtag` | `#AI` | 包含指定话题标签 |
| `since:` | `since:2026-01-01` | 发布时间不早于（YYYY-MM-DD）|
| `until:` | `until:2026-03-13` | 发布时间不晚于（YYYY-MM-DD）|
| `min_faves:` | `min_faves:100` | 最少点赞数 |
| `min_retweets:` | `min_retweets:50` | 最少转推数 |
| `min_replies:` | `min_replies:10` | 最少回复数 |
| `filter:links` | `AI filter:links` | 仅含外链的推文 |
| `filter:images` | `AI filter:images` | 仅含图片的推文 |
| `filter:videos` | `AI filter:videos` | 仅含视频的推文 |
| `filter:replies` | `AI filter:replies` | 仅回复类推文 |
| `-filter:replies` | `AI -filter:replies` | 排除回复，仅原创推文 |
| `lang:` | `AI lang:en` | 指定语言（ISO 639-1）|

**高级搜索表单字段与 rawQuery 的对应关系**:

| 表单字段 | rawQuery 编码方式 |
|----------|------------------|
| All of these words | 词间空格拼接（`word1 word2`）|
| This exact phrase | 加引号（`"exact phrase"`）|
| Any of these words | `word1 OR word2` |
| None of these words | `-word1 -word2` |
| These hashtags | `#tag1 #tag2` |
| From these accounts | `from:user1 from:user2` |
| To these accounts | `to:user1` |
| Mentioning these accounts | `@user1` |
| Minimum Likes | `min_faves:N` |
| Minimum reposts | `min_retweets:N` |
| Minimum replies | `min_replies:N` |
| From date | `since:YYYY-MM-DD` |
| To date | `until:YYYY-MM-DD` |
| Language | `lang:XX`（拼接在末尾）|

**复合查询示例**（Advanced Search 触发的实际 rawQuery）:
```
artificial intelligence from:openai min_faves:100 since:2026-01-01 until:2026-03-13
```

**限速**: `x-rate-limit-limit: 50`，`x-rate-limit-reset` 为 Unix 时间戳（约每 15 分钟重置）。实测剩余配额从 41 开始递减，即每次搜索消耗 1 次。

---

#### 响应结构详解

**完整响应路径**:
```
data
  search_by_raw_query
    search_timeline
      timeline
        instructions[]
          type: "TimelineAddEntries"
          entries[]
```

**指令类型**:

| `type` 值 | 说明 |
|-----------|------|
| `TimelineAddEntries` | 首次加载，追加条目列表（含推文、用户模块、游标）|
| `TimelineReplaceEntry` | 翻页时更新游标（`entry_id_to_replace` 指定要替换的游标 entryId）|

**条目 (`entries[]`) 类型**:

| `content.__typename` | `entryId` 前缀 | 说明 |
|----------------------|----------------|------|
| `TimelineTimelineModule` | `toptabsrpusermodule-` | 用户结果卡组（Top 模式首项，含 3 个匹配用户）|
| `TimelineTimelineItem` | `tweet-{id}` | 单条推文 |
| `TimelineTimelineCursor` | `cursor-top-*` | 向上翻页游标（用于刷新最新内容）|
| `TimelineTimelineCursor` | `cursor-bottom-*` | 向下翻页游标（用于加载更多）|

**推文条目完整字段结构**:

```
entries[].content.itemContent
  __typename: "TimelineTweet"
  itemType: "TimelineTweet"
  tweet_results.result
    __typename: "Tweet"
    rest_id: "2032471758855450881"         # 推文 ID（字符串）
    core
      user_results.result
        __typename: "User"
        rest_id: "..."                      # 用户 ID
        is_blue_verified: true/false        # 蓝标认证
        legacy
          screen_name: "openai"            # @handle
          name: "OpenAI"                   # 显示名
          followers_count: 6500000
          friends_count: 50                # 关注数
          statuses_count: 8432             # 发推总数
          profile_image_url_https: "..."
          profile_banner_url: "..."
          description: "..."               # 简介
          verified: false                  # 旧版认证（已弃用）
    legacy
      id_str: "2032471758855450881"
      full_text: "..."                     # 推文正文（含 t.co 短链）
      created_at: "Fri Mar 13 15:00:03 +0000 2026"  # RFC2822 格式
      conversation_id_str: "..."           # 话题串 ID
      in_reply_to_status_id_str: "..."     # 回复目标推文 ID（可能为 null）
      in_reply_to_user_id_str: "..."       # 回复目标用户 ID
      user_id_str: "..."                   # 作者 ID
      lang: "en"                           # 语言
      favorite_count: 15                   # 点赞数
      retweet_count: 3                     # 转推数
      reply_count: 0                       # 回复数
      quote_count: 0                       # 引用数
      bookmark_count: 2                    # 收藏数
      favorited: false                     # 当前用户是否已点赞
      retweeted: false                     # 当前用户是否已转推
      bookmarked: false                    # 当前用户是否已收藏
      is_quote_status: false               # 是否为引用推文
      possibly_sensitive: false
      display_text_range: [0, 280]
      entities
        hashtags: [{text, indices}]
        urls: [{url, expanded_url, display_url, indices}]
        user_mentions: [{id_str, screen_name, name, indices}]
        media: [{...}]                     # 媒体元数据（缩略信息）
      extended_entities
        media: [{
          id_str, media_url_https,
          type: "photo"/"video"/"animated_gif",
          sizes: {thumb, small, medium, large},
          video_info: {               # 仅 video/animated_gif
            aspect_ratio,
            duration_millis,
            variants: [{
              bitrate, content_type,
              url: "https://video.twimg.com/..."
            }]
          }
        }]
    views
      count: "867"                         # 浏览量（字符串）
      state: "EnabledWithCount"
    note_tweet                             # 长推文（超 280 字符）
      is_expandable: true
      note_tweet_results.result
        id: "..."
        text: "..."                        # 完整长文本
        entity_set: {hashtags, urls, ...}
    source: "<a href=\"...\">Twitter Web App</a>"   # 发推客户端
    is_translatable: false
    grok_analysis_button: {...}            # Grok 分析按钮配置
```

**用户模块条目结构**（`Top` 模式下首项，entryId 前缀 `toptabsrpusermodule-`）:

```
entries[0].content
  __typename: "TimelineTimelineModule"
  displayType: "Carousel"
  items[].item.itemContent
    __typename: "TimelineUser"
    itemType: "TimelineUser"
    userDisplayType: "User"
    user_results.result
      # 完整用户结构（同推文中 core.user_results.result）
```

**游标条目结构**:

```json
{
  "entryId": "cursor-bottom-0",
  "sortIndex": "0",
  "content": {
    "entryType": "TimelineTimelineCursor",
    "__typename": "TimelineTimelineCursor",
    "value": "DAADDAABCgABHDUhuefWwF4KAAIcNR80qRYRSQAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUcNSG_vgAnEA==",
    "cursorType": "Bottom"
  }
}
```

**翻页时的 `TimelineReplaceEntry` 指令**:
```json
{
  "type": "TimelineReplaceEntry",
  "entry_id_to_replace": "cursor-bottom-0",
  "entry": {
    "content": {
      "cursorType": "Bottom",
      "value": "DAADDAABCgABHDUhuefWwF4KAAIcNR0rQRYAOQAI..."
    }
  }
}
```

**响应示例**（精简，Top 模式）:
```json
{
  "data": {
    "search_by_raw_query": {
      "search_timeline": {
        "timeline": {
          "instructions": [{
            "type": "TimelineAddEntries",
            "entries": [
              {
                "entryId": "toptabsrpusermodule-2032567851994316800",
                "content": {
                  "__typename": "TimelineTimelineModule",
                  "displayType": "Carousel",
                  "items": [{
                    "item": {
                      "itemContent": {
                        "__typename": "TimelineUser",
                        "user_results": {
                          "result": {
                            "is_blue_verified": true,
                            "legacy": {
                              "screen_name": "OpenAI",
                              "name": "OpenAI",
                              "followers_count": 6500000,
                              "description": "OpenAI is an AI research..."
                            }
                          }
                        }
                      }
                    }
                  }]
                }
              },
              {
                "entryId": "tweet-2032471758855450881",
                "sortIndex": "2032471758855450881",
                "content": {
                  "entryType": "TimelineTimelineItem",
                  "itemContent": {
                    "__typename": "TimelineTweet",
                    "tweet_results": {
                      "result": {
                        "__typename": "Tweet",
                        "rest_id": "2032471758855450881",
                        "core": {
                          "user_results": {
                            "result": {
                              "is_blue_verified": true,
                              "legacy": {
                                "screen_name": "TechInsider",
                                "name": "Tech Insider",
                                "followers_count": 32922
                              }
                            }
                          }
                        },
                        "legacy": {
                          "id_str": "2032471758855450881",
                          "full_text": "Tesla has received U.S. government clearance...",
                          "created_at": "Fri Mar 13 15:00:03 +0000 2026",
                          "favorite_count": 15,
                          "retweet_count": 3,
                          "reply_count": 0,
                          "lang": "en"
                        },
                        "views": {"count": "867", "state": "EnabledWithCount"},
                        "note_tweet": {
                          "is_expandable": true,
                          "note_tweet_results": {
                            "result": {
                              "text": "Tesla has received U.S. government clearance to convert its $2 billion investment in xAI into a direct stake in SpaceX...",
                              "entity_set": {"hashtags": [], "urls": [], "user_mentions": []}
                            }
                          }
                        }
                      }
                    }
                  }
                }
              },
              {
                "entryId": "cursor-top-9223372036854775807",
                "content": {
                  "entryType": "TimelineTimelineCursor",
                  "cursorType": "Top",
                  "value": "DAACCgACHDUhsUAAJxAK..."
                }
              },
              {
                "entryId": "cursor-bottom-0",
                "content": {
                  "entryType": "TimelineTimelineCursor",
                  "cursorType": "Bottom",
                  "value": "DAACCgACHDUhsUAAJxAK..."
                }
              }
            ]
          }]
        }
      }
    }
  }
}
```

---

### 3.2 搜索分页（游标翻页）GET [重要度: ⭐⭐⭐]

**接口与 3.1 相同**，翻页时在 `variables` 中额外传入 `cursor` 字段：

```
GET https://x.com/i/api/graphql/oKkjeoNFNQN7IeK7AHYc0A/SearchTimeline
variables={
  "rawQuery": "artificial intelligence",
  "count": 20,
  "cursor": "DAADDAABCgABHDUhuefWwF4KAAIcNR80qRYRSQAIAAIAAAACCAADAAAAAAgABAAAAAAKAAUcNSG_vgAnEA==",
  "querySource": "typed_query",
  "product": "Latest",
  "withGrokTranslatedBio": false
}
```

**分页逻辑**:
1. 首次请求不含 `cursor`，响应 `entries` 末尾包含 `cursor-top-*` 和 `cursor-bottom-*` 两个游标条目
2. 向下加载更多：取 `cursor-bottom-*` 的 `content.value`，作为下次 `cursor` 参数
3. 翻页响应中 `instructions` 包含两类：`TimelineAddEntries`（新推文）+ `TimelineReplaceEntry`（更新游标）
4. `cursor-top` 用于拉取此后新发布的推文（类似 Twitter 的"Show new tweets"功能）

---

### 3.3 已保存搜索列表 GET [重要度: ⭐]

```
GET https://x.com/i/api/1.1/saved_searches/list.json
```

**用途**: 获取用户保存的搜索词列表，进入搜索页时触发。响应为数组，如无保存则返回 `[]`。

---

## 四、登录流程接口

### 4.1 初始化登录流程 POST [重要度: ⭐⭐⭐]

```
POST https://api.x.com/1.1/onboarding/task.json?redirect_after_login=%2Fhome&flow_name=login
```

**用途**: 启动登录流程，获取初始 `flow_token` 和 JS 指纹任务。

**Request Headers**（登录阶段使用 Guest Token）:

| Header | 值 |
|--------|-----|
| `x-guest-token` | `{guest_token}` |
| `authorization` | `Bearer {公共 Token}` |

**Request Body**:
```json
{
  "input_flow_data": {
    "flow_context": {
      "debug_overrides": {},
      "start_location": {"location": "manual_link"}
    }
  },
  "subtask_versions": {
    "enter_password": 5,
    "enter_username": 2,
    "js_instrumentation": 1,
    "open_home_timeline": 1
    // ... 约30个子任务版本号
  }
}
```

**响应**（Set-Cookie: `att` 令牌）:
```json
{
  "flow_token": "g;{guest_id}:-{timestamp}:{hash}:0",
  "status": "success",
  "subtasks": [{
    "subtask_id": "LoginJsInstrumentationSubtask",
    "js_instrumentation": {
      "url": "https://twitter.com/i/js_inst?c_name=ui_metrics",
      "timeout_ms": 2000
    }
  }]
}
```

---

### 4.2 推进登录步骤 POST [重要度: ⭐⭐⭐]

```
POST https://api.x.com/1.1/onboarding/task.json
```

**用途**: 提交每个登录步骤的数据（JS 指纹、用户名、密码等），推进 flow 状态机。

**Request Body**（JS 指纹步骤示例）:
```json
{
  "flow_token": "g;{guest_id}:-{timestamp}:{hash}:0",
  "subtask_inputs": [{
    "subtask_id": "LoginJsInstrumentationSubtask",
    "js_instrumentation": {
      "response": "{\"rf\":{...}, \"s\":\"...\"}"，
      "link": "next_link"
    }
  }]
}
```

**响应**（返回下一步子任务）:
```json
{
  "flow_token": "g;...:{hash}:1",
  "status": "success",
  "subtasks": [{
    "subtask_id": "LoginEnterUserIdentifierSSO",
    "settings_list": {
      "header": {"primary_text": {"text": "Sign in to X"}},
      "settings": [
        {"value_type": "button", "value_identifier": "google_sso_button", ...},
        {"value_type": "text_field", "value_identifier": "user_identifier", ...},
        {"value_type": "button", "value_identifier": "next_button", ...}
      ]
    }
  }]
}
```

**登录流程状态机**:
```
flow_token:0  →  LoginJsInstrumentationSubtask  （JS 指纹采集）
flow_token:1  →  LoginEnterUserIdentifierSSO     （输入用户名/手机/邮箱）
flow_token:2  →  LoginEnterPassword              （输入密码）
flow_token:3  →  AccountDuplicationCheck         （设备验证）或直接 OpenHomeTimeline
```

---

### 4.3 SSO 初始化 POST [重要度: ⭐⭐]

```
POST https://api.x.com/1.1/onboarding/sso_init.json
```

**用途**: 初始化第三方 SSO 登录（Google/Apple），获取 OAuth state 参数。

**Request Body**:
```json
{"provider": "apple"}
// 或
{"provider": "google"}
```

**响应**:
```json
{"state": "CMhYDKXsDc8JqWkIK03zsrDlfnWAhh-5iLo7MmOw6T1"}
```

---

## 五、Periscope/直播接口

### 5.1 Twitter Token 登录 POST [重要度: ⭐]

```
POST https://proxsee.pscp.tv/api/v2/loginTwitterToken
```

**用途**: 用 Twitter 认证令牌登录 Periscope（Spaces 功能后端）。

### 5.2 Token 授权 POST [重要度: ⭐]

```
POST https://proxsee.pscp.tv/api/v2/authorizeToken
```

**用途**: 授权 Periscope token，用于 Spaces 直播功能。

---

## 六、系统/配置接口

### 6.1 账户设置 GET [重要度: ⭐⭐]

```
GET https://api.x.com/1.1/account/settings.json?include_ext_sharing_audiospaces_listening_data_with_followers=true&include_mention_filter=true&include_nsfw_user_flag=true&include_nsfw_admin_flag=true&include_ranked_timeline=true&include_alt_text_compose=true&include_ext_dm_av_call_settings=true&ext=ssoConnections&include_country_code=true&include_ext_dm_nsfw_media_filter=true
```

**用途**: 获取用户完整账户设置（时区、语言、NSFW 设置、国家代码等）。
**注意**: 当前 Session 未携带旧版 API Cookie 时返回 401，首页加载时均触发但 401 不影响功能。

### 6.2 实时推送管道 GET [重要度: ⭐]

```
GET https://api.x.com/live_pipeline/events?topic=%2Flive_content%2F{userId}
GET https://api.x.com/live_pipeline/events?topic=%2Favcall%2Fcreate%2F{userId},%2Favcall%2Fclear%2F{userId}
GET https://api.x.com/live_pipeline/events?topic=%2Ftweet_engagement%2F{tweetId}
```

**用途**: 订阅 Server-Sent Events（SSE），用于实时推送新推文通知、通话事件、推文互动数据更新。
**注意**: 当前均返回 401，可能需要特定的认证 Cookie。

### 6.3 性能日志上报 POST [重要度: 低]

```
POST https://x.com/i/api/1.1/graphql/user_flow.json
Content-Type: application/x-www-form-urlencoded
```

**Request Body**（示例）:
```
category=perftown&log=[{"description":"rweb:cookiesMetadata:load","product":"rweb","event_value":111428842242}]
```

**用途**: 客户端性能埋点上报，低价值。

---

## 七、接口调用链路

```
用户打开 https://x.com/home
│
├── [并行] GET /1.1/hashflags.json                    获取话题标签图标
├── [并行] GET /graphql/.../DataSaverMode              查询省流量设置
├── [并行] GET /graphql/.../HomeTimeline               首页推荐 Feed（核心）
│   └── 响应包含 tweets[].legacy.id_str               推文 ID
│       tweets[].core.user_results.result.rest_id     作者 ID
│       cursor-bottom.value                           下一页游标
│
├── [并行] GET /graphql/.../PinnedTimelines            获取固定标签（社区/列表）
├── [并行] GET /graphql/.../ExploreSidebar             右侧热点趋势
├── [并行] GET /graphql/.../SidebarUserRecommendations 右侧推荐关注（传入当前 userId）
├── [并行] GET /graphql/.../useStoryTopicQuery         Today's News AI 话题
├── [并行] GET /2/badge_count/badge_count.json         未读数角标
├── [并行] GET /fleets/v1/fleetline?only_spaces=true   Spaces 状态
└── [并行] GET /graphql/.../useFetchProductSubscriptionsQuery  Premium 订阅状态

用户点击 "Following" 标签
└── POST /graphql/.../HomeLatestTimeline              关注人时间线（需传入 seenTweetIds）

用户点击推文标题
└── GET /graphql/.../TweetDetail?focalTweetId={id}   推文+回复线程
    ├── 同时 GET /graphql/.../TweetResultByRestId      推文预加载（SSR）
    └── 推文内媒体 video_info.variants → video.twimg.com HLS/MP4 流

用户进行搜索（普通搜索或高级搜索）
│
├── GET /1.1/saved_searches/list.json                 已保存搜索词
├── GET /graphql/oKkjeoNFNQN7IeK7AHYc0A/SearchTimeline
│       variables.rawQuery = "artificial intelligence"
│       variables.product = "Top"                     搜索热门结果
│   ├── 响应 entries[0] = UserModule（匹配用户卡组）
│   ├── 响应 entries[1..N] = tweet-{id}（推文条目）
│   └── 响应 entries[-2,-1] = cursor-top / cursor-bottom
│
├── 用户切换 Latest 标签
│   └── GET /graphql/oKkjeoNFNQN7IeK7AHYc0A/SearchTimeline
│           variables.product = "Latest"              同接口，换 product 参数
│
└── 用户滚动到底部（触发翻页）
    └── GET /graphql/oKkjeoNFNQN7IeK7AHYc0A/SearchTimeline
            variables.cursor = cursor-bottom.value    传入游标
        ├── 响应 instructions[0].type = TimelineAddEntries（新推文）
        └── 响应 instructions[1,2].type = TimelineReplaceEntry（更新游标）

用户使用高级搜索（https://x.com/search-advanced）
├── 表单字段映射到 rawQuery 操作符（from:/since:/until:/min_faves: 等）
└── 提交后 URL 变为 /search?q={encoded_rawQuery}&src=typed_query
    └── GET /graphql/oKkjeoNFNQN7IeK7AHYc0A/SearchTimeline（同上接口）
```

---

## 八、关键发现

1. **GraphQL 操作 ID 嵌入 URL**: X 的 GraphQL API 将 `queryId`（如 `-HtXlyhboD0-JLXJ-xo9Vg`）嵌入 URL 路径，不在 Body 中传 `query` 字符串，防止随意调用。

2. **公共 Bearer Token**: 所有请求（含未登录）均使用同一个硬编码 Bearer Token `AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA`，这是 Twitter 官方 Web App 的 Token，长期稳定。

3. **双重 CSRF 防护**: 需要 `ct0` Cookie 并将其值同时作为 `x-csrf-token` 请求头发送，防止跨站请求伪造。

4. **分页游标机制**: 时间线分页不用页码，而用 `cursor-bottom-*` 条目的 `value` 字符串作为下次请求的 `cursor` 参数，保证实时性和稳定性。

5. **HomeTimeline vs HomeLatestTimeline**: `For You` 用 GET + variables，而 `Following` 用 POST + body，且 POST 接口需要传入 `seenTweetIds` 实现去重。

6. **推文 ID 即排序索引**: `sortIndex` 字段与 `id_str`（Snowflake ID）保持一致，可从 ID 解析出发布时间戳。

7. **视频多码率 HLS 分发**: 视频通过 `video.twimg.com` CDN 分发，格式为 `.m3u8`（HLS 主播放列表）+ `.m4s`（MPEG-DASH 分片），支持自适应码率（从 320p 到 1440p+）。

8. **Feature Flags 机制**: 每个 GraphQL 请求附带约 30 个 `features` 布尔值，用于控制响应中包含哪些字段，允许服务端 A/B 测试和功能灰度。

9. **`x-client-transaction-id`**: 每次请求生成唯一值（base64 编码），用于服务端追踪和日志，客户端可随机生成任意值。

10. **账户设置 401**: `api.x.com/1.1/account/settings.json` 在当前 Cookie 注入方式下返回 401，推测旧版 API 域名需要不同的 Cookie 作用域（`.api.x.com` vs `.x.com`）。

11. **广告曝光独立上报**: 广告推文（`promotedMetadata` 字段不为空）曝光后会向 `/1.1/promoted_content/log.json` 发送 `impression` 事件，包含 `impression_id`（广告系统 ID）。

12. **高级搜索不调用独立接口**: `/search-advanced` 页面仅是前端表单，提交后将各字段拼装为 Twitter 搜索操作符格式的 `rawQuery` 字符串（如 `word1 word2 from:user since:YYYY-MM-DD min_faves:N`），然后复用同一个 `SearchTimeline` GraphQL 接口。没有专用的高级搜索接口。

13. **SearchTimeline 同一接口服务所有搜索 Tab**: Top/Latest/People/Photos/Videos 五个标签对应同一 `SearchTimeline` 接口，仅 `variables.product` 字段不同（`Top`/`Latest`/`People`/`Photos`/`Videos`），无需切换 endpoint。

14. **搜索结果首条为用户模块**: `product=Top` 时，响应 `entries[0]` 为 `entryId` 前缀为 `toptabsrpusermodule-` 的用户卡组（`TimelineTimelineModule`），含最多 3 个匹配用户。后续条目（`tweet-{id}`）才是推文。

15. **游标更新机制的细节**: 首次加载时两个游标（Top/Bottom）在 `TimelineAddEntries` 中以独立 entry 形式返回；翻页后游标通过 `TimelineReplaceEntry` 指令替换，`entry_id_to_replace` 字段指定要替换的游标 entryId（如 `cursor-bottom-0`），新游标 value 附在 `entry.content.value` 中。

16. **长推文（Note Tweet）**: 超过 280 字符的推文通过 `note_tweet` 字段携带完整内容（`note_tweet.note_tweet_results.result.text`），同时 `legacy.full_text` 会被截断并加 `…` 和展开链接。`note_tweet.is_expandable: true` 表示需要前端展开。

17. **搜索限速较严**: SearchTimeline 接口限速为 **50次/15分钟**（`x-rate-limit-limit: 50`），远低于 HomeTimeline（500次/15分钟）。每次滚动翻页消耗 1 次配额。
