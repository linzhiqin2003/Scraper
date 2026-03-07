# 抖音 (Douyin) API 接口文档

## 概述

- **网站地址**: https://www.douyin.com/jingxuan
- **API 域名**:
  - `www.douyin.com` — 主要业务 API
  - `www-hj.douyin.com` — 香港节点，用于个人资料/收藏等需要登录的接口
  - `mcs.zijieapi.com` — 埋点数据上报（字节跳动内部）
  - `mssdk.bytedance.com` — msToken 令牌管理
  - `security.zijieapi.com` — 安全指标上报
  - `verify.zijieapi.com` — 验证码服务
  - `mon.zijieapi.com` — 监控上报
  - `imapi.douyin.com` — IM 消息服务
- **认证方式**: Cookie 认证（`sessionid` / `sid_tt` 为核心登录凭证）
- **CORS**: 同源请求（`sec-fetch-site: same-origin` 或 `same-site`），`Access-Control-Allow-Credentials: true`

---

### 公共请求头

所有业务 API 均携带以下请求头：

| Header | 示例值 | 说明 |
|--------|--------|------|
| `uifid` | `749b770aa6a177ba...` | 设备指纹 ID，128 位十六进制，来自 Cookie `UIFID` |
| `x-secsdk-csrf-token` | `DOWNGRADE` | CSRF Token（POST 请求），部分接口降级为字符串 `DOWNGRADE` |
| `bd-ticket-guard-web-version` | `2` | bd-ticket 防护版本（部分接口携带） |
| `bd-ticket-guard-ree-public-key` | `BBgq6vCwgf9BFK...` | ECDH 公钥（部分接口携带） |
| `bd-ticket-guard-web-sign-type` | `0` | 签名类型 |
| `Referer` | `https://www.douyin.com/jingxuan` | 来源页面 |

### 通用公共查询参数（几乎所有 API 都携带）

| 参数 | 示例值 | 说明 |
|------|--------|------|
| `device_platform` | `webapp` | 设备平台，固定值 |
| `aid` | `6383` | 应用 ID，抖音 Web 固定为 `6383` |
| `channel` | `channel_pc_web` | 渠道，固定值 |
| `update_version_code` | `170400` | 版本码 |
| `version_code` | `170400` | 版本码 |
| `version_name` | `17.4.0` | 版本名 |
| `pc_client_type` | `1` | PC 客户端类型 |
| `pc_libra_divert` | `Mac` | 系统类型 |
| `webid` | `7614283898361005587` | Web 设备 ID，由 `www-hj.douyin.com/aweme/v1/web/query/user/` 接口返回 |
| `uifid` | `749b770aa6...` | 用户设备指纹，同请求头 |
| `msToken` | `cwuckOpMcc...` | 短期令牌，由 `mssdk.bytedance.com/web/r/token` 接口定时刷新 |
| `a_bogus` | `Ojsnk7SwE25bKd...` | 请求签名（防篡改），由前端 JS 对请求参数计算生成 |
| `verifyFp` | `verify_mmfhp8mn_8UMj3rxN_...` | 设备指纹验证值，来自 Cookie `s_v_web_id` |
| `fp` | `verify_mmfhp8mn_8UMj3rxN_...` | 同 `verifyFp` |
| `support_h265` | `1` | 是否支持 H.265 编码 |
| `support_dash` | `0` | 是否支持 DASH 流 |

### 响应格式

```json
{
  "status_code": 0,
  "status_msg": "",
  "extra": {
    "logid": "20260307071203B33DCE5C0EF84E53F19F",
    "now": 1772838723000,
    "fatal_item_ids": []
  },
  "log_pb": {
    "impr_id": "20260307071203B33DCE5C0EF84E53F19F"
  }
}
```

`status_code=0` 表示成功，业务数据在其他字段中返回。

---

## 一、精选页 (Jingxuan) 核心接口

### 1.1 精选视频流 (模块推荐流) POST [重要度: ⭐⭐⭐]

```
POST https://www.douyin.com/aweme/v2/web/module/feed/
```

**用途**: 获取精选页 (jingxuan) 的视频推荐流，是页面主体内容来源，支持分页加载。

**Query 参数（关键部分）**:

| 参数 | 类型 | 必填 | 示例值 | 说明 |
|------|------|------|--------|------|
| `module_id` | int | 是 | `3003101` | 模块 ID，精选页固定值 |
| `count` | int | 是 | `20` | 每次请求视频数量 |
| `refresh_index` | int | 是 | `1` | 刷新次序，首次=1，翻页递增 |
| `pull_type` | int | 是 | `0` | 加载类型：`0`=首次/刷新，`2`=加载更多 |
| `filterGids` | string | 否 | `` | 过滤的 GID 列表 |
| `presented_ids` | string | 否 | `` | 已展示的视频 ID |
| `tag_id` | string | 否 | `` | 标签 ID（切换分类 Tab 时填入） |
| `pre_item_ids` | string | 否 | `7613328220456226089,...` | 上一批视频的 ID（逗号分隔，用于去重） |
| `pre_item_from` | string | 否 | `sati` | 上一批来源标识 |
| `refer_type` | int | 否 | `10` | 来源类型 |
| `use_lite_type` | int | 否 | `2`/`0` | 精简类型：首次=`2`，加载更多=`0` |
| `active_id` | string | 否 | `` | 当前激活分类 ID（切换分类时填入） |
| `is_active_tab` | bool | 否 | `false` | 是否激活 Tab |

**Request Body (POST, application/x-www-form-urlencoded)**:

```
encoded_pre_item_ids=MDUEDJ8UffLw%2Bv9B4PW...&encoded_pre_room_ids=
```

`encoded_pre_item_ids` 为对 `pre_item_ids` 加密后的值（防篡改）。

**响应关键字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `aweme_list` | array | 视频列表 |
| `aweme_list[].aweme_id` | string | 视频唯一 ID |
| `aweme_list[].desc` | string | 视频描述/标题 |
| `aweme_list[].author` | object | 作者信息 |
| `aweme_list[].author.uid` | string | 作者 UID |
| `aweme_list[].author.nickname` | string | 作者昵称 |
| `aweme_list[].author.sec_uid` | string | 作者加密 UID，用于个人主页请求 |
| `aweme_list[].video` | object | 视频信息 |
| `aweme_list[].video.play_addr` | object | 播放地址 |
| `aweme_list[].video.cover` | object | 封面图 |
| `aweme_list[].video.duration` | int | 时长（毫秒） |
| `aweme_list[].statistics` | object | 统计数据 |
| `aweme_list[].statistics.digg_count` | int | 点赞数 |
| `aweme_list[].statistics.comment_count` | int | 评论数 |
| `aweme_list[].statistics.share_count` | int | 分享数 |
| `aweme_list[].video_tag` | array | 视频标签（分类信息） |
| `aweme_list[].cha_list` | array | 话题列表 |
| `aweme_list[].is_ads` | bool | 是否广告 |
| `aweme_list[].media_type` | int | 媒体类型：`4`=视频 |
| `has_more` | int | 是否还有更多：`1`=有，`0`=无 |
| `max_cursor` | int | 最大游标（当前为 `0`，翻页通过 `pre_item_ids` 实现去重） |
| `log_pb.impr_id` | string | 曝光日志 ID，下次请求可传 `pre_log_id` |

**响应示例（精简）**:

```json
{
  "has_more": 1,
  "status_code": 0,
  "aweme_list": [
    {
      "aweme_id": "7613328220456226089",
      "desc": "【抖音独家】伊朗用导弹炸碎中东半个世纪战争潜规则...",
      "author": {
        "uid": "123456",
        "nickname": "凯撒的羊皮卷",
        "sec_uid": "MS4wLjABAAAA..."
      },
      "video": {
        "duration": 608000,
        "cover": {"url_list": ["https://p3-pc-sign.douyinpic.com/..."]},
        "play_addr": {"url_list": ["https://v..."]}
      },
      "statistics": {"digg_count": 294000, "comment_count": 1200},
      "video_tag": [{"tag_id": 2018, "tag_name": "时政社会", "level": 1}],
      "is_ads": false,
      "media_type": 4
    }
  ],
  "extra": {"logid": "20260307071203B33DCE5C0EF84E53F19F", "now": 1772838723000}
}
```

---

### 1.2 精选分类 Tab 列表 GET [重要度: ⭐⭐⭐]

```
GET https://www.douyin.com/aweme/v1/web/douyin/select/tab/course/catagory/tag/
```

**用途**: 获取精选页顶部分类 Tab 的标签树（公开课/游戏/影视/音乐 等），用于筛选视频流。

**Query 参数（关键部分）**:

| 参数 | 类型 | 必填 | 示例值 | 说明 |
|------|------|------|--------|------|
| `tab_id` | string | 是 | `screen_course_page` | Tab 页面 ID，固定值 |

**响应关键字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `tag_list` | array | 顶级分类列表 |
| `tag_list[].tag_id` | int | 分类 ID |
| `tag_list[].tag_title` | string | 分类名称 |
| `tag_list[].tag_level` | int | 层级（1=一级，2=二级，3=三级） |
| `tag_list[].children` | array | 子分类列表（结构相同） |

**响应示例（精简）**:

```json
{
  "status_code": 0,
  "tag_list": [
    {
      "tag_id": 1000,
      "tag_level": 1,
      "tag_title": "硬核AI课",
      "children": [
        {"tag_id": 1001, "tag_level": 2, "tag_title": "专业理论"},
        {"tag_id": 1002, "tag_level": 2, "tag_title": "前沿应用"},
        {"tag_id": 1003, "tag_level": 2, "tag_title": "AI工具"}
      ]
    },
    {
      "tag_id": 1004,
      "tag_level": 1,
      "tag_title": "高校公开课",
      "children": [...]
    }
  ]
}
```

---

## 二、热搜榜单接口

### 2.1 热搜列表 GET [重要度: ⭐⭐⭐]

```
GET https://www.douyin.com/aweme/v1/web/hot/search/list/
```

**用途**: 获取抖音热搜榜单（词条列表+热度值+话题封面）。

**Query 参数（关键部分）**:

| 参数 | 类型 | 必填 | 示例值 | 说明 |
|------|------|------|--------|------|
| `detail_list` | int | 否 | `1` | 是否返回详细列表 |
| `source` | int | 否 | `6` | 来源标识 |
| `main_billboard_count` | int | 否 | `5` | 主榜单条数 |

**响应关键字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `data.word_list` | array | 热搜词条列表（完整榜单） |
| `data.word_list[].word` | string | 热搜词 |
| `data.word_list[].hot_value` | int | 热度值 |
| `data.word_list[].view_count` | int | 查看次数 |
| `data.word_list[].position` | int | 排名 |
| `data.word_list[].sentence_id` | string | 词条 ID |
| `data.word_list[].word_type` | int | 词条类型：`1`=普通，`3`=热点，`14`=置顶 |
| `data.word_list[].label` | int | 标签：`0`=无，`3`=🔥热 |
| `data.word_list[].word_cover` | object | 话题封面图 |
| `data.trending_list` | array | 实时上升热点（trending）列表 |
| `data.trending_list[].word` | string | 热词 |
| `data.trending_list[].sentence_tag` | int | 热词标签类型 |

**响应示例（精简）**:

```json
{
  "data": {
    "active_time": "2026-03-07 07:11:19",
    "trending_desc": "实时上升热点",
    "trending_list": [
      {"word": "回到纯真年代", "sentence_id": "2420203", "word_type": 3}
    ],
    "word_list": [
      {
        "word": "全国人大举行经济主题记者会",
        "hot_value": 11262079,
        "view_count": 70183517,
        "position": 1,
        "max_rank": 1,
        "label": 0,
        "word_type": 1
      },
      {
        "word": "成都蓉城5:1深圳新鹏城",
        "hot_value": 10826035,
        "position": 2,
        "label": 3
      }
    ]
  }
}
```

---

## 三、用户相关接口

### 3.1 用户社交计数 GET [重要度: ⭐⭐]

```
GET https://www.douyin.com/aweme/v1/web/social/count
```

**用途**: 获取当前登录用户的关注 Tab 未读数、直播提示等社交状态信息。

**Query 参数**:

| 参数 | 类型 | 示例值 | 说明 |
|------|------|--------|------|
| `source` | int | `6` | 来源 |

**响应关键字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `notice_count` | array | 各类通知计数 |
| `notice_count[].group` | int | 通知分组（38=直播，41=关注新动态，50=互动，52=好友） |
| `notice_count[].count` | int | 未读数量 |
| `notice_count[].notice_name` | string | 通知类型名称 |
| `follow_tab_channel_count` | array | 关注 Tab 各频道计数 |

**响应示例（精简）**:

```json
{
  "status_code": 0,
  "notice_count": [
    {"group": 38, "count": 1, "notice_name": "live"},
    {"group": 41, "count": 147, "notice_name": "number_dot"}
  ],
  "follow_tab_channel_count": [
    {"channel": 1, "count": 1},
    {"channel": 2, "count": 147}
  ]
}
```

---

### 3.2 消息通知计数 GET [重要度: ⭐⭐]

```
GET https://www.douyin.com/aweme/v1/web/notice/count/
```

**用途**: 获取通知中心各类未读消息数（评论/点赞/私信/系统通知等）。

**Query 参数**:

| 参数 | 类型 | 示例值 | 说明 |
|------|------|--------|------|
| `is_new_notice` | int | `1` | 是否只获取新通知 |
| `need_social_count` | int | `1` | 是否需要社交计数 |

**响应关键字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `notice_count` | array | 各类通知计数 |
| `notice_count[].group` | int | 通知组：`2`=评论/互动，`3`=粉丝，`401`=点赞，`601`=私信，`700`=系统 |
| `notice_count[].count` | int | 未读数量 |
| `interactive_group` | array | 互动通知分组映射 |

---

### 3.3 用户设置获取 GET [重要度: ⭐]

```
GET https://www.douyin.com/aweme/v1/web/get/user/settings
```

**用途**: 获取当前用户的首页展示偏好设置（推荐/精选模式）。

**响应示例**:

```json
{
  "status_code": 0,
  "set_info": "{\"landing_mode\":2}",
  "landing_reason": "new_user_landing_select_libra",
  "extra": {"is_new": "1", "is_show_today": "0"}
}
```

`landing_mode`: `1`=推荐页，`2`=精选页（jingxuan）

---

### 3.4 用户收藏视频列表 GET [重要度: ⭐⭐]

```
GET https://www-hj.douyin.com/aweme/v1/web/aweme/favorite/
```

**用途**: 获取用户收藏的视频列表（需登录，使用香港节点）。

**Query 参数**:

| 参数 | 类型 | 必填 | 示例值 | 说明 |
|------|------|------|--------|------|
| `sec_user_id` | string | 是 | `MS4wLjABAAAARnauB_qt...` | 用户加密 UID，从个人信息接口获取 |
| `max_cursor` | int | 是 | `0` | 分页游标，首次为 0 |
| `min_cursor` | int | 是 | `0` | 最小游标 |
| `count` | int | 是 | `18` | 每页数量 |
| `cut_version` | int | 否 | `1` | 截断版本 |

**注意**: 此接口需额外请求头 `bd-ticket-guard-web-version: 2` 和 `bd-ticket-guard-ree-public-key`。

---

### 3.5 个人主页 Web 设备注册 GET [重要度: ⭐]

```
GET https://www-hj.douyin.com/aweme/v1/web/query/user/
```

**用途**: 注册当前浏览器的 Web 设备 ID（webid），并关联当前登录用户。

**响应示例**:

```json
{
  "id": "7614283898361005587",
  "create_time": "1772838642",
  "user_uid": "4267662945564535",
  "user_uid_type": 0,
  "browser_name": "Chrome"
}
```

`id` 即为全局使用的 `webid`。

---

### 3.6 收藏合集列表 GET [重要度: ⭐]

```
GET https://www.douyin.com/aweme/v1/web/mix/listcollection/
```

**用途**: 获取当前登录用户创建的合集列表。

**Query 参数**:

| 参数 | 类型 | 示例值 | 说明 |
|------|------|--------|------|
| `cursor` | int | `0` | 分页游标 |
| `count` | int | `20` | 每页数量 |

**响应示例**:

```json
{
  "status_code": 0,
  "has_more": 0,
  "cursor": 0,
  "mix_infos": []
}
```

---

## 四、广播/多播查询接口

### 4.1 多播查询 GET [重要度: ⭐]

```
GET https://www.douyin.com/aweme/v1/web/multicast/query/
```

**用途**: 查询当前用户是否有多播推送任务（如活动通知等）。

**响应示例**:

```json
{
  "status_code": 0,
  "multicast_list": null
}
```

---

## 五、页面状态接口

### 5.1 页面离线切换上报 POST [重要度: ⭐]

```
POST https://www.douyin.com/aweme/v1/web/page/turn/offline
```

**用途**: 上报页面切换为离线/后台状态，服务端返回用户在线开关状态。

**Request Body**: 空（`content-length: 0`）

**响应示例**:

```json
{
  "status_code": 0,
  "user_switch": 0
}
```

---

## 六、运营位/资源接口

### 6.1 解决方案资源列表 GET [重要度: ⭐]

```
GET https://www.douyin.com/aweme/v1/web/solution/resource/list/
```

**用途**: 获取运营位资源（广告位、Banner 配置），用于 Tab 区域和页面 Banner 展示。

**Query 参数**:

| 参数 | 类型 | 示例值 | 说明 |
|------|------|--------|------|
| `spot_keys` | string | `7359502129541449780_douyin_pc_tab` | 位置键，不同位置不同值 |
| `app_id` | int | `6383` | 应用 ID |

**已发现的 spot_keys 值**:
- `7359502129541449780_douyin_pc_tab` — Tab 区域
- `7359502129541449780_douyin_pc_discover_subtab` — 发现页子 Tab
- `7359502129541449780_douyin_pc_banner` — 页面 Banner

---

### 6.2 站外通知 GET [重要度: ⭐]

```
GET https://www.douyin.com/aweme/v1/web/external/notification/
```

**用途**: 获取平台推送的站外运营通知（如 PC 管理后台推送）。

**Query 参数**:

| 参数 | 类型 | 示例值 | 说明 |
|------|------|--------|------|
| `os` | int | `1` | 操作系统类型 |
| `user_id` | string | `70067744428` | 用户 ID |
| `client_type` | int | `1` | 客户端类型 |
| `scene` | string | `admin_pc_push` | 场景 |

---

## 七、安全/Token 接口

### 7.1 msToken 刷新 POST [重要度: ⭐⭐⭐]

```
POST https://mssdk.bytedance.com/web/r/token
```

**用途**: 刷新/获取新的 `msToken`，是所有业务 API 请求的必要参数，定时自动刷新。

**Query 参数**:

| 参数 | 类型 | 示例值 | 说明 |
|------|------|--------|------|
| `ms_appid` | int | `6383` | 应用 ID |
| `msToken` | string | `cwuckOpMcc...` | 当前 msToken（用于续期） |

**响应**: 返回新的 msToken 字符串，写入 Cookie。

---

### 7.2 Token 心跳 GET [重要度: ⭐]

```
GET https://www.douyin.com/passport/token/beat/web/
```

**用途**: 刷新 passport session 令牌，保持登录态。

---

## 八、认证接口

**登录方式**: 导入 Cookies 文件（Netscape 格式）

**Cookies 注入方式**（逐条通过 `document.cookie` 注入）:

```javascript
// 关键登录态 Cookies：
document.cookie = "sessionid=7c8370a94075076b65a965f49cf7f39f; domain=.douyin.com; path=/; SameSite=None; Secure";
document.cookie = "sid_tt=7c8370a94075076b65a965f49cf7f39f; domain=.douyin.com; path=/; SameSite=None; Secure";
document.cookie = "uid_tt=c8b7e9056d56301b8b0d4a330d374a17; domain=.douyin.com; path=/; SameSite=None; Secure";
document.cookie = "ttwid=1%7CZ78-uzg7Fh35BJ49...; domain=.douyin.com; path=/";
document.cookie = "s_v_web_id=verify_mmfhp8mn_...; domain=www.douyin.com; path=/";
```

**核心登录 Cookies**:

| Cookie 名 | 域 | 说明 |
|-----------|-----|------|
| `sessionid` / `sessionid_ss` | `.douyin.com` | 会话 ID，最核心的登录凭证 |
| `sid_tt` | `.douyin.com` | 同 sessionid 的别名 |
| `uid_tt` / `uid_tt_ss` | `.douyin.com` | 用户 UID |
| `ttwid` | `.douyin.com` | TikTok Web ID，跨设备标识 |
| `odin_tt` | `.douyin.com` | Odin 设备 Token，动态更新 |
| `s_v_web_id` | `www.douyin.com` | 设备指纹（`verifyFp`/`fp` 参数来源） |
| `passport_csrf_token` | `.douyin.com` | CSRF Token |
| `UIFID` | `.douyin.com` | 用户设备指纹 ID（请求头 `uifid` 来源） |
| `sid_guard` | `.douyin.com` | Session 有效期守护值 |

**登录状态检测**: 页面顶部右侧显示用户头像而非「Log in」按钮；或调用 `/aweme/v1/web/social/count` 接口返回 `status_code: 0` 且含用户数据。

---

## 九、接口调用链路

```
页面加载 (https://www.douyin.com/jingxuan)
│
├─► [设备注册] www-hj.douyin.com/aweme/v1/web/query/user/
│       └─ 返回 webid → 后续所有请求携带此 webid
│
├─► [Token 获取] mssdk.bytedance.com/web/r/token
│       └─ 返回 msToken → 后续所有请求携带此 msToken
│
├─► [页面初始化并行请求]
│   ├─ [分类 Tab] /aweme/v1/web/douyin/select/tab/course/catagory/tag/
│   │       └─ 返回 tag_id → 切换分类时传入 module/feed 的 tag_id 参数
│   │
│   ├─ [视频推荐流] /aweme/v2/web/module/feed/ (refresh_index=1, pull_type=0)
│   │       └─ 返回 aweme_list[].aweme_id → 详情页 URL: /video/{aweme_id}
│   │       └─ 返回 aweme_list[].author.sec_uid → 个人主页 /user/{sec_uid}
│   │       └─ 返回 log_pb.impr_id → 下次请求的 pre_log_id 参数
│   │
│   ├─ [热搜榜单] /aweme/v1/web/hot/search/list/
│   │
│   ├─ [用户通知] /aweme/v1/web/social/count
│   │
│   └─ [消息计数] /aweme/v1/web/notice/count/
│
└─► [用户交互触发]
    ├─ 切换分类 Tab → /aweme/v2/web/module/feed/ (tag_id=选中标签ID, pull_type=2)
    └─ 滚动加载更多 → /aweme/v2/web/module/feed/ (refresh_index递增, pull_type=2,
                        pre_item_ids=上一批视频ID)
```

---

## 十、关键发现

1. **签名机制 (`a_bogus`)**: 每个请求都包含 `a_bogus` 参数，由前端 JS 对完整请求 URL（含所有 Query 参数）进行哈希签名生成，不同请求的 `a_bogus` 均不同。无法直接构造，需要在浏览器环境中执行签名 JS，或使用 CDP 注入页面计算。

2. **双层 Token 机制**:
   - `msToken`: 短期令牌，由 `mssdk.bytedance.com/web/r/token` 定时刷新（约每 5 分钟），所有 API 必须携带有效 msToken。
   - `verifyFp`/`fp`: 长期设备指纹，来自 Cookie `s_v_web_id`，值为 `verify_` 前缀的字符串。

3. **分页机制**: 精选视频流不使用传统 `page`/`cursor` 分页，而是将上一批视频 ID 列表作为 `pre_item_ids` 参数传递，服务端基于此进行去重过滤。`refresh_index` 随每次加载递增（首次=1，后续递增）。

4. **双 API 域名架构**:
   - `www.douyin.com`：内容发现类接口（推荐流、热搜、通知等），经国内 CDN 加速
   - `www-hj.douyin.com`：用户私密数据类接口（收藏、个人资料等），经香港节点路由（`via: n62-197-024.CN-HKG3`）

5. **验证码机制**: 首次访问或触发风控时，会弹出 `verify.zijieapi.com` 的滑块验证码（CAPTCHA），验证后才能正常使用 API。验证码参数通过 `x-vc-bdturing-parameters` 响应头返回。

6. **`odin_tt` Cookie 动态刷新**: 每个业务 API 响应均通过 `Set-Cookie` 刷新 `odin_tt` Cookie 值，用于设备绑定和安全校验，请求前需确保 Cookie 最新。

7. **bd-ticket-guard 防护**: 部分接口（尤其是 `www-hj.douyin.com` 上的用户数据接口）需要携带 `bd-ticket-guard-*` 请求头，这是字节跳动的 ECDH 加密防护机制。

8. **视频 URL 拼接规则**: 视频详情页 URL 格式为 `https://www.douyin.com/video/{aweme_id}`，`aweme_id` 从推荐流响应中 `aweme_list[].aweme_id` 字段获取。个人主页 URL 格式为 `https://www.douyin.com/user/{sec_uid}`，`sec_uid` 从作者信息中获取。

9. **`x-secsdk-csrf-token` 降级**: 大部分 POST 请求该头值为 `DOWNGRADE`（即降级，不做严格校验），但少数敏感接口可能需要真实 CSRF Token。

10. **免登录可访问内容**: 精选页（jingxuan）的视频列表在未登录状态下仍可访问，但个性化推荐质量会降低。收藏、点赞等交互类接口必须登录。

---

## 十一、评论接口

> 以下接口均通过对视频 `7613328220456226089` 实测抓包所得，抓包时间 2026-03-07。

### 11.1 评论列表 GET [重要度: ⭐⭐⭐]

```
GET https://www-hj.douyin.com/aweme/v1/web/comment/list/
```

**用途**: 获取指定视频的一级评论列表，支持游标分页。首屏加载 5 条，后续每页 10 条。

**API 域名说明**: 评论接口走 `www-hj.douyin.com`（香港节点），需携带 `bd-ticket-guard-*` 请求头。

**Query 参数（核心参数）**:

| 参数 | 类型 | 必填 | 示例值 | 说明 |
|------|------|------|--------|------|
| `aweme_id` | string | 是 | `7613328220456226089` | 视频 ID |
| `cursor` | int | 是 | `0` | 分页游标，首次为 0，后续使用响应中的 `cursor` 值 |
| `count` | int | 是 | `5` / `10` | 每页数量，首次 5，后续 10 |
| `item_type` | int | 是 | `0` | 固定为 0（普通视频评论） |
| `cut_version` | int | 是 | `1` | 固定为 1 |
| `whale_cut_token` | string | 否 | `""` | 热门评论置顶 token，首次为空 |
| `rcFT` | string | 否 | `""` | 首次为空，后续可能携带 |
| `device_platform` | string | 是 | `webapp` | 固定值 |
| `aid` | int | 是 | `6383` | 抖音 Web 端 AppID，固定值 |
| `channel` | string | 是 | `channel_pc_web` | 固定值 |
| `msToken` | string | 是 | `ifKIq0wmKz...` | 短期令牌，约 5 分钟刷新一次 |
| `a_bogus` | string | 是 | `EXUnDeUiEx...` | 请求签名（见注意事项） |
| `verifyFp` / `fp` | string | 是 | `verify_mmfj0gof_...` | 设备指纹，来自 Cookie `s_v_web_id` |

**特殊请求头**:

| Header | 示例值 | 说明 |
|--------|--------|------|
| `bd-ticket-guard-version` | `2` | 防护版本 |
| `bd-ticket-guard-web-version` | `2` | Web 防护版本 |
| `bd-ticket-guard-ree-public-key` | `BBgq6vCwgf9BFK...` | ECDH 公钥 |
| `bd-ticket-guard-web-sign-type` | `0` | 签名类型 |
| `uifid` | `749b770aa6a177ba...` | 设备指纹，来自 Cookie `UIFID` |
| `referer` | `https://www.douyin.com/` | 必须携带 |
| `origin` | `https://www.douyin.com` | 必须携带 |

**响应字段（顶层）**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `status_code` | int | 0 表示成功 |
| `comments` | array | 评论列表（本次返回的条数） |
| `cursor` | int | 下一页游标，传入下次请求的 `cursor` 参数 |
| `has_more` | int | 1 表示还有更多，0 表示已全部加载 |
| `total` | int | 该视频评论总数 |
| `reply_style` | int | 回复展示风格，2 = 折叠回复 |
| `user_commented` | int | 当前用户是否已评论，0=否 |
| `folded_comment_count` | int | 被折叠的评论数量 |

**响应字段（comments 数组单条评论对象）**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `cid` | string | 评论 ID（用于查询回复列表时的 `comment_id`） |
| `aweme_id` | string | 所属视频 ID |
| `text` | string | 评论文字内容 |
| `create_time` | int | 评论创建时间（Unix 时间戳，秒） |
| `digg_count` | int | 点赞数 |
| `reply_comment_total` | int | 该评论的回复总数（二级评论数） |
| `item_comment_total` | int | 视频总评论数（与顶层 `total` 一致） |
| `level` | int | 评论层级，1 = 一级评论 |
| `reply_id` | string | 父评论 ID，一级评论固定为 `"0"` |
| `reply_to_reply_id` | string | 回复的具体二级评论 ID，无则为 `"0"` |
| `user_digged` | int | 当前用户是否点赞，0=否 1=是 |
| `is_author_digged` | bool | 视频作者是否点赞该评论 |
| `is_hot` | bool | 是否为热门评论 |
| `is_folded` | bool | 是否被折叠（违规/低质量评论） |
| `ip_label` | string | 评论者 IP 归属地，如 `"辽宁"` `"广东"` |
| `status` | int | 评论状态，1 = 正常 |
| `can_share` | bool | 是否可分享 |
| `content_type` | int | 内容类型，1 = 纯文本 |
| `sort_tags` | string | JSON 字符串，排序标签，如 `{"top_list":1}` |
| `enter_from` | string | 流量来源，如 `homepage_hot` |
| `stick_position` | int | 置顶位置，0 = 不置顶 |
| `user_buried` | bool | 当前用户是否举报/屏蔽 |
| `text_extra` | array | 文本中的 @ 用户、话题等富文本信息 |
| `image_list` | array/null | 评论图片列表 |
| `video_list` | array/null | 评论视频列表 |
| `is_note_comment` | int | 是否为图文笔记评论 |
| `label_text` | string | 评论标签文字 |
| `label_type` | int | 评论标签类型，-1 = 无 |
| `decorated_emoji_info` | object/null | 装饰 emoji 信息 |
| `user` | object | 评论用户信息（见下表） |

**user 对象字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `uid` | string | 用户数字 ID |
| `sec_uid` | string | 用户安全 ID（用于拼接主页 URL） |
| `short_id` | string | 用户短 ID |
| `unique_id` | string | 用户自定义 ID（抖音号） |
| `nickname` | string | 用户昵称 |
| `avatar_thumb` | object | 头像缩略图，含 `uri`、`url_list`、`width`、`height` |
| `follow_status` | int | 当前用户对该用户的关注状态，0=未关注 |
| `follower_status` | int | 该用户是否关注了当前用户 |
| `verification_type` | int | 认证类型，0=无认证 1=个人认证 |
| `enterprise_verify_reason` | string | 企业认证说明 |
| `custom_verify` | string | 自定义认证文字 |
| `region` | string | 注册地区，如 `"CN"` |
| `secret` | int | 是否私密账号，0=否 |
| `user_canceled` | bool | 是否已注销 |
| `status` | int | 账号状态，1=正常 |

**响应示例（精简，第一条评论）**:

```json
{
  "status_code": 0,
  "cursor": 5,
  "has_more": 1,
  "total": 4625,
  "reply_style": 2,
  "comments": [
    {
      "cid": "7613748218882573114",
      "aweme_id": "7613328220456226089",
      "text": "玫瑰宫被毁了，我很难过，感觉见证了当年圆明园变成遗址",
      "create_time": 1772713899,
      "digg_count": 31251,
      "reply_comment_total": 108,
      "item_comment_total": 4625,
      "level": 1,
      "reply_id": "0",
      "ip_label": "辽宁",
      "is_hot": true,
      "is_author_digged": false,
      "sort_tags": "{\"top_list\":1}",
      "user": {
        "uid": "2379781254165180",
        "sec_uid": "MS4wLjABAAAATGiW...",
        "nickname": "三文鱼饭",
        "avatar_thumb": {
          "uri": "100x100/aweme-avatar/tos-cn-avt-0015_...",
          "url_list": ["https://p3-pc.douyinpic.com/..."],
          "width": 720,
          "height": 720
        },
        "region": "CN"
      }
    }
  ]
}
```

---

### 11.2 评论回复列表（二级评论）GET [重要度: ⭐⭐⭐]

```
GET https://www-hj.douyin.com/aweme/v1/web/comment/list/reply/
```

**用途**: 获取指定一级评论下的回复列表（二级评论），支持游标分页。首次加载 3 条。

**Query 参数（核心参数）**:

| 参数 | 类型 | 必填 | 示例值 | 说明 |
|------|------|------|--------|------|
| `item_id` | string | 是 | `7613328220456226089` | 视频 ID（注意字段名是 `item_id` 而非 `aweme_id`） |
| `comment_id` | string | 是 | `7613748218882573114` | 父评论 ID，即一级评论的 `cid` |
| `cursor` | int | 是 | `0` | 分页游标，首次为 0 |
| `count` | int | 是 | `3` | 每页数量，首次 3 条 |
| `item_type` | int | 是 | `0` | 固定为 0 |
| `cut_version` | int | 是 | `1` | 固定为 1 |
| `device_platform` | string | 是 | `webapp` | 固定值 |
| `aid` | int | 是 | `6383` | 固定值 |
| `msToken` | string | 是 | `...` | 短期令牌 |
| `a_bogus` | string | 是 | `...` | 请求签名 |
| `verifyFp` / `fp` | string | 是 | `...` | 设备指纹 |

**响应字段（顶层）**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `status_code` | int | 0 表示成功 |
| `comments` | array | 回复列表 |
| `cursor` | int | 下一页游标 |
| `has_more` | int | 1 表示还有更多 |
| `total` | int | 回复总数（注意：此值可能略大于实际父评论的 `reply_comment_total`，因为包含了合并回复） |
| `merge_cursor` | int | 合并游标（用于跨父评论的回复合并展示） |

**响应字段（comments 数组单条回复对象）**（在评论列表字段基础上新增/差异字段）:

| 字段 | 类型 | 说明 |
|------|------|------|
| `cid` | string | 回复 ID |
| `level` | int | 层级，2 = 二级评论/回复 |
| `reply_id` | string | 所回复的一级评论 ID（即请求参数中的 `comment_id`） |
| `reply_to_reply_id` | string | 所回复的具体二级评论 ID；若直接回复一级评论则为 `"0"` |
| `root_comment_id` | string | 根评论 ID（即顶层一级评论 ID） |
| `comment_reply_total` | int | 该条回复自身的回复数（三级结构，通常为 0） |
| `can_create_item` | bool | 是否可以基于该回复创建视频 |
| `reply_comment` | object/null | 被回复评论的摘要信息（用于展示"回复@xxx"） |

**响应示例（精简）**:

```json
{
  "status_code": 0,
  "cursor": 3,
  "has_more": 1,
  "total": 115,
  "merge_cursor": 0,
  "comments": [
    {
      "cid": "7613823610105086778",
      "text": "是的，第一次了解到这么美丽的文化建筑竟然是通过战争…",
      "level": 2,
      "reply_id": "7613748218882573114",
      "reply_to_reply_id": "0",
      "root_comment_id": "7613748218882573114",
      "digg_count": 8995,
      "ip_label": "湖北",
      "create_time": 1772731459,
      "user": {
        "uid": "101688053962",
        "nickname": "量子电囚"
      }
    },
    {
      "cid": "7613972231609467697",
      "text": "伊朗在很久以前叫波斯[流泪]",
      "level": 2,
      "reply_id": "7613748218882573114",
      "reply_to_reply_id": "7613823610105086778",
      "root_comment_id": "7613748218882573114",
      "ip_label": "河南",
      "user": {
        "nickname": "翊渝"
      }
    }
  ]
}
```

---

### 11.3 视频详情（含评论数）GET [重要度: ⭐⭐⭐]

```
GET https://www.douyin.com/aweme/v1/web/aweme/detail/
```

**用途**: 获取单个视频的完整元数据，包括作者信息、统计数据、评论数等。

**API 域名**: `www.douyin.com`（主域，非香港节点，不需要 `bd-ticket-guard-*` 头）。

**Query 参数（核心参数）**:

| 参数 | 类型 | 必填 | 示例值 | 说明 |
|------|------|------|--------|------|
| `aweme_id` | string | 是 | `7613328220456226089` | 视频 ID |
| `request_source` | int | 否 | `600` | 请求来源标识，视频页为 600 |
| `origin_type` | string | 否 | `video_page` | 来源类型 |
| `device_platform` | string | 是 | `webapp` | 固定值 |
| `aid` | int | 是 | `6383` | 固定值 |
| `version_code` | string | 是 | `190500` | 版本号（注意：此接口版本号为 `190500`/`19.5.0`，与评论接口的 `170400` 不同） |
| `msToken` | string | 是 | `...` | 短期令牌 |
| `a_bogus` | string | 是 | `...` | 请求签名 |

**响应字段（aweme_detail 对象，精选字段）**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `aweme_id` | string | 视频 ID |
| `desc` | string | 视频描述/标题文字 |
| `create_time` | int | 发布时间（Unix 时间戳） |
| `duration` | int | 视频时长（毫秒） |
| `author` | object | 作者信息（uid、nickname、follower_count、avatar_thumb 等） |
| `author_user_id` | int | 作者数字 ID |
| `aweme_type` | int | 视频类型，0=普通视频 |
| `comment_gid` | int | 评论 group ID（通常等于 aweme_id） |
| `danmaku_control.danmaku_cnt` | int | 弹幕数量 |
| `feed_comment_config` | object | 评论配置（是否允许评论、音频评论等） |
| `aweme_control.can_comment` | bool | 是否开放评论 |
| `hot_list` | object | 热搜信息（热搜词、热度分等） |
| `media_type` | int | 媒体类型，4=视频 |
| `is_ads` | bool | 是否为广告 |
| `boost_status` | int | 推广状态 |

**响应示例（精简）**:

```json
{
  "aweme_detail": {
    "aweme_id": "7613328220456226089",
    "desc": "【抖音独家】伊朗用导弹炸碎中东半个世纪战争潜规则...",
    "create_time": 1772616145,
    "duration": 607970,
    "aweme_type": 0,
    "media_type": 4,
    "comment_gid": 7613328220456226089,
    "author": {
      "uid": "303917400327853",
      "sec_uid": "MS4wLjABAAAAHs9TA1-3GiGW9R...",
      "nickname": "凯撒的羊皮卷",
      "follower_count": 131872,
      "verification_type": 1
    },
    "aweme_control": {
      "can_comment": true,
      "can_forward": true,
      "can_share": true
    },
    "hot_list": {
      "sentence": "美称将增加对德黑兰上空的打击",
      "hot_score": 4562948,
      "view_count": 19488390
    }
  }
}
```

---

### 评论接口分页机制

**一级评论分页**:
- 首次请求：`cursor=0&count=5`，返回前 5 条热门评论
- 后续翻页：将响应中的 `cursor` 值作为下一次请求的 `cursor` 参数，每页 `count=10`
- 终止条件：响应 `has_more=0`
- 分页示例：`cursor=0` → 返回 cursor=5；`cursor=5` → 返回 cursor=15；以此类推

**二级评论（回复）分页**:
- 首次请求：`cursor=0&count=3`，返回前 3 条回复
- 后续翻页：`cursor=3`、`cursor=6`...，每页默认 3 条，可调整
- 注意：`total` 字段返回的是包含合并回复的总数，可能略大于一级评论的 `reply_comment_total`
- `merge_cursor` 用于处理多个父评论合并展示的场景

---

### 评论接口注意事项

1. **`a_bogus` 签名**: 每个请求 URL 末尾都携带 `a_bogus` 参数，这是一个基于请求参数、时间戳、设备指纹等生成的防篡改签名。该签名由前端 JavaScript 生成，无法在浏览器外直接复现，需要通过以下方式处理：
   - 使用 Playwright/Selenium 在真实浏览器中执行请求
   - 逆向 JS 算法提取签名逻辑
   - 使用 DevTools 协议拦截并转发浏览器发出的请求

2. **`msToken` 令牌**: 由 `mssdk.bytedance.com/web/r/token` 接口定时下发，有效期约 5 分钟。过期后 API 会返回错误码，需要重新获取。

3. **`bd-ticket-guard` 防护**: 评论接口（`www-hj.douyin.com`）要求携带完整的 `bd-ticket-guard-*` 请求头组合，这是字节跳动的 ECDH 加密防护机制。缺少这些头部时接口会返回错误。

4. **API 域名差异**:
   - 评论列表 / 评论回复：`www-hj.douyin.com`（需要 `bd-ticket-guard-*` 头）
   - 视频详情：`www.douyin.com`（不需要 `bd-ticket-guard-*` 头）

5. **登录要求**: 评论列表接口在未登录状态下也可以访问（因为视频页面公开），但 `user_digged`（是否已点赞）等个人化字段需要登录后才有效。

6. **评论排序**: 接口默认返回热门评论（按点赞数降序），`sort_tags` 字段标识排序标签，`top_list=1` 表示在热门榜中。系统会在热门评论中穿插时间顺序排列的普通评论。

7. **IP 归属地**: 每条评论和回复均携带 `ip_label` 字段（如 `"辽宁"` `"广东"`），这是抖音强制显示的评论者 IP 归属地，不可关闭。

8. **评论接口调用链路**:
   ```
   视频详情页加载
       ↓
   GET /aweme/v1/web/aweme/detail/?aweme_id={id}   → 获取视频元数据
       ↓
   GET /aweme/v1/web/comment/list/?aweme_id={id}&cursor=0&count=5   → 获取首屏评论
       ↓（用户点击"展开X条回复"）
   GET /aweme/v1/web/comment/list/reply/?item_id={id}&comment_id={cid}&cursor=0&count=3   → 获取一级评论的回复
       ↓（用户下滑评论区）
   GET /aweme/v1/web/comment/list/?aweme_id={id}&cursor=5&count=10   → 加载更多评论
   ```
