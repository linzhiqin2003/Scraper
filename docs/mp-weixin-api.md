# 微信公众平台 API 接口文档

## 概述

- **网站地址**: https://mp.weixin.qq.com
- **API 域名**:
  - `mp.weixin.qq.com` — 主要后台接口（`/cgi-bin/`、`/merchant/`、`/wxamp/`、`/advanced/`、`/misc/`）
  - `badjs.weixinbridge.com` — 前端错误上报（低价值）
- **认证方式**: Cookie 会话 + URL `token` 参数双重验证
- **CORS**: `sec-fetch-site: same-origin`，仅同源请求，需带完整 Cookie

---

### 公共请求头

| Header | 值示例 | 说明 |
|--------|--------|------|
| `x-requested-with` | `XMLHttpRequest` | 标识 Ajax 请求，必填 |
| `referer` | `https://mp.weixin.qq.com/cgi-bin/appmsg?...` | 来源页面 |
| `cookie` | 见下方 Cookie 说明 | 会话认证，必填 |
| `content-type` | `application/x-www-form-urlencoded; charset=UTF-8` | POST 请求必填 |

### 关键 Cookie 字段

| Cookie 名 | 说明 | 有效期 |
|-----------|------|--------|
| `slave_sid` | 主会话 ID（Base64 编码），最核心的认证凭据 | 约 4 天 |
| `slave_user` | 当前登录账号的 username，如 `gh_904a8405fa0b` | 约 4 天 |
| `bizuin` | 公众号唯一标识（数字），如 `3925403212` | 约 4 天 |
| `data_ticket` | 数据访问票据 | 约 4 天 |
| `slave_bizuin` | 同 bizuin | 约 4 天 |
| `data_bizuin` | 同 bizuin | 约 4 天 |
| `rand_info` | 随机安全信息（proto 编码） | 约 4 天 |
| `cert` | 证书令牌 | Session |
| `uuid` | 设备唯一 ID | Session |
| `wxuin` | 微信用户 ID | 约 1 年 |
| `mm_lang` | 语言设置，`zh_CN` | 约 1 年 |
| `xid` | 扩展 ID | 约 1 年 |

### 公共查询参数（多数接口共用）

| 参数 | 说明 | 示例值 |
|------|------|--------|
| `token` | 登录会话 Token，每次登录重新生成 | `1122555813` |
| `lang` | 语言 | `zh_CN` |
| `f` | 响应格式 | `json` |
| `ajax` | 标识 Ajax 请求 | `1` |
| `fingerprint` | 浏览器指纹（32位十六进制） | `20ba7f46c6f68be7859019d5bb91037e` |
| `random` | 防缓存随机数 | `0.123456789` |

### 通用响应格式

所有接口均返回 JSON，顶层结构包含：

```json
{
  "base_resp": {
    "ret": 0,
    "err_msg": "ok"
  },
  "...": "业务数据字段"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `base_resp.ret` | int | 0 = 成功，非 0 = 错误 |
| `base_resp.err_msg` | string | 错误描述，成功时为 `"ok"` 或 `""` |

响应头中有额外信息：
- `logicret`: 业务逻辑返回码，`0` 表示成功
- `retkey`: 内部键值，`14` 表示正常鉴权通过

---

## 一、账号管理

### 1.1 获取关联账号列表 GET [重要度: ⭐⭐⭐]

```
GET /cgi-bin/switchacct?action=get_acct_list&token={token}&lang=zh_CN&f=json
```

**用途**: 获取当前登录用户关联的所有公众号、小程序账号列表，用于账号切换。

**参数说明**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `action` | string | 是 | 固定值 `get_acct_list` |
| `token` | string | 是 | 会话 Token |
| `fingerprint` | string | 否 | 浏览器指纹（带 fingerprint 时额外传） |

**响应关键字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `biz_list.list` | array | 公众号账号列表 |
| `biz_list.list[].bizuin` | int | 公众号唯一 ID |
| `biz_list.list[].nickname` | string | 公众号名称 |
| `biz_list.list[].username` | string | 公众号 username，如 `gh_xxx` |
| `biz_list.list[].acct_type` | int | 账号类型：1=公众号，2=小程序，3=测试号 |
| `biz_list.list[].is_admin` | int | 是否管理员：1=是 |
| `biz_list.list[].headimgurl` | string | 头像 URL |
| `biz_list.list[].last_login_time` | int | 最后登录时间戳 |
| `wxa_list.list` | array | 关联小程序列表（结构同 biz_list） |
| `status` | int | 状态：1=正常 |

**响应示例**:

```json
{
  "base_resp": {"ret": 0, "err_msg": "ok"},
  "biz_list": {
    "length": 2,
    "list": [
      {
        "bizuin": 3925403212,
        "nickname": "小林闲话屋",
        "username": "gh_904a8405fa0b",
        "acct_type": 1,
        "is_admin": 1,
        "headimgurl": "https://mmbiz.qpic.cn/...",
        "last_login_time": 1773421034
      }
    ]
  },
  "wxa_list": {"length": 3, "list": [...]}
}
```

---

## 二、文章编辑

### 2.1 获取文章历史版本 POST [重要度: ⭐⭐⭐]

```
POST /cgi-bin/appmsg?action=get_appmsg_update_history&appmsgid={appmsgid}&offset=0&limit=8
```

**用途**: 获取某篇图文消息的历史编辑版本列表（历史版本功能）。

**请求 Body** (form-urlencoded):

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `token` | string | 是 | 会话 Token |
| `lang` | string | 是 | `zh_CN` |
| `f` | string | 是 | `json` |
| `ajax` | string | 是 | `1` |
| `fingerprint` | string | 是 | 浏览器指纹 |
| `random` | string | 是 | 随机数 |

**URL 参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `appmsgid` | string/int | 图文消息 ID，新建时为 `undefined` |
| `offset` | int | 分页偏移，默认 `0` |
| `limit` | int | 每页数量，默认 `8` |

**响应关键字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `list` | array | 历史版本列表（空数组表示无历史） |

---

### 2.2 获取最近文章类型 GET [重要度: ⭐⭐]

```
GET /cgi-bin/operate_appmsg?t=ajax-response&sub=get_recently_article_type&token={token}&lang=zh_CN&f=json&ajax=1&fingerprint={fp}&random={r}
```

**用途**: 获取该账号最近使用的文章类型偏好（用于编辑器初始化）。

**响应关键字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `items` | array | 最近文章类型列表（通常为空） |

---

### 2.3 预加载文章句子（AI 辅助写作） POST [重要度: ⭐⭐]

```
POST /cgi-bin/operate_appmsg?t=ajax-response&sub=pre_load_sentence
```

**用途**: 编辑器打开时预加载 AI 写作辅助内容（根据正文片段预测推荐）。

**请求 Body** (form-urlencoded):

| 参数 | 类型 | 说明 |
|------|------|------|
| `token` | string | 会话 Token |
| `appmsgid` | int | 文章 ID，新建为 `0` |
| `index` | int | 文章段落索引，从 `0` 开始 |
| `title` | string | 文章标题（可为空） |
| `sentence` | string | URL 编码的正文片段 |

**响应**: `{"base_resp": {"ret": 0, "err_msg": "ok"}}`

---

### 2.4 保存草稿 POST [重要度: ⭐⭐⭐⭐⭐]

根据页面结构推断，保存草稿调用以下接口（需标题或正文非空才触发）：

```
POST /cgi-bin/appmsg?action=draft
```

**请求 Body** (form-urlencoded，关键字段):

| 参数 | 类型 | 说明 |
|------|------|------|
| `token` | string | 会话 Token |
| `lang` | string | `zh_CN` |
| `f` | string | `json` |
| `ajax` | string | `1` |
| `AppMsgId` | int | 文章 ID，新建为 `0` |
| `item_list` | string | JSON 字符串，包含文章内容数组 |

`item_list` 结构示例：
```json
{
  "list": [{
    "title": "文章标题",
    "author": "作者",
    "content": "<section>正文 HTML</section>",
    "digest": "摘要",
    "fileid": 0,
    "cover": "封面图片 URL"
  }]
}
```

---

### 2.5 发表前内容检查 POST [重要度: ⭐⭐⭐]

```
POST /cgi-bin/masssend?action=check_music
```

**用途**: 发表前检查文章内容中是否包含音乐版权受限内容。

**请求 Body** (form-urlencoded):

| 参数 | 类型 | 说明 |
|------|------|------|
| `token` | string | 会话 Token |
| `appmsgid` | string | 文章临时 ID（随机字符串） |
| `item_list` | string | JSON 字符串，包含待检查的文章内容 |

`item_list` JSON 结构：
```json
{
  "list": [{
    "title": "文章标题",
    "content": "<section>...</section>"
  }]
}
```

**响应关键字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `list` | array | 受版权保护的音乐列表（空数组=无问题） |

---

## 三、文章列表 & 草稿箱

### 3.1 获取草稿箱/文章列表 GET [重要度: ⭐⭐⭐⭐⭐]

```
GET /cgi-bin/appmsg?action=list_card&begin=0&count=10&type={type}&token={token}&lang=zh_CN&f=json&ajax=1
```

**用途**: 获取草稿箱或已发表文章列表，支持搜索。

**参数说明**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `action` | string | 是 | 固定值 `list_card` |
| `type` | int | 是 | 内容类型：`77`=草稿，`10`=图文，`15`=视频 |
| `begin` | int | 是 | 分页起始位，从 `0` 开始 |
| `count` | int | 是 | 每页数量，建议 `10` |
| `query` | string | 否 | 搜索关键词（标题搜索） |
| `token` | string | 是 | 会话 Token |

**响应关键字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `app_msg_info.item` | array | 文章/草稿列表 |
| `app_msg_info.item[].appmsgid` | int | 文章 ID（用于后续编辑/详情接口） |
| `app_msg_info.item[].title` | string | 文章标题 |
| `app_msg_info.item[].cover` | string | 封面图 URL |
| `app_msg_info.item[].create_time` | int | 创建时间戳 |
| `app_msg_info.item[].update_time` | int | 更新时间戳 |
| `app_msg_info.file_cnt` | object | 各类型内容数量统计 |
| `app_msg_info.file_cnt.draft_count` | int | 草稿数量 |
| `app_msg_info.file_cnt.app_msg_cnt` | int | 图文数量 |
| `app_msg_info.file_cnt.video_cnt` | int | 视频数量 |
| `app_msg_info.search_cnt` | int | 搜索结果总数（搜索时有效） |

**响应示例**:

```json
{
  "base_resp": {"ret": 0, "err_msg": ""},
  "app_msg_info": {
    "file_cnt": {
      "draft_count": 3,
      "app_msg_cnt": 10,
      "video_cnt": 2,
      "total": 15
    },
    "item": [
      {
        "appmsgid": 2247483647,
        "title": "文章标题",
        "cover": "https://mmbiz.qpic.cn/...",
        "create_time": 1773000000,
        "update_time": 1773400000
      }
    ],
    "search_cnt": 1
  }
}
```

**type 枚举值**:

| type | 含义 |
|------|------|
| `10` | 图文消息 |
| `15` | 视频消息 |
| `77` | 草稿箱 |

---

### 3.2 获取发表记录 GET [重要度: ⭐⭐⭐]

```
GET /cgi-bin/appmsgpublish?sub=list&begin=0&count=10&token={token}&lang=zh_CN&f=json&ajax=1
```

**用途**: 获取历史发表记录列表（已群发的消息记录）。

**参数说明**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `sub` | string | 固定值 `list` |
| `begin` | int | 分页起始位 |
| `count` | int | 每页数量 |

**响应关键字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `is_admin` | bool | 当前用户是否为管理员 |
| `publish_page` | string | JSON 字符串（需再次解析） |
| `publish_page.total_count` | int | 总发表次数 |
| `publish_page.publish_count` | int | 普通发表数 |
| `publish_page.masssend_count` | int | 群发数 |
| `publish_page.publish_list` | array | 发表记录列表 |

**注意**: `publish_page` 字段值为 JSON 字符串，需二次 `JSON.parse()`。

---

### 3.3 获取视频列表 GET [重要度: ⭐⭐⭐]

```
GET /cgi-bin/appmsg?action=list&count=8&type=15&begin=0&f=json&fingerprint={fp}&token={token}&lang=zh_CN&f=json&ajax=1
```

**用途**: 在编辑器"选择视频"对话框中获取素材库中的视频列表。

**参数说明**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `action` | string | 固定值 `list` |
| `type` | int | `15` = 视频类型 |
| `count` | int | 每次获取数量，默认 `8` |
| `begin` | int | 分页偏移 |

**响应关键字段**: 同 3.1（`app_msg_info.item` 为视频列表）

---

## 四、素材库

### 4.1 获取素材库列表（管理页） GET [重要度: ⭐⭐⭐⭐]

```
GET /cgi-bin/filepage?type={type}&begin=0&count=12&token={token}&lang=zh_CN&f=json&ajax=1
```

**用途**: 获取素材库（图片/音频/视频）文件列表，用于素材管理页面展示。

**参数说明**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | int | 是 | 素材类型：`2`=图片，`3`=音频，`15`=视频 |
| `begin` | int | 是 | 分页起始位 |
| `count` | int | 是 | 每页数量 |

**响应关键字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `can_use_voice` | int | 是否可使用语音功能：1=是 |
| `page_info.type` | int | 当前素材类型 |
| `page_info.file_item` | array | 素材文件列表 |
| `page_info.file_cnt` | object | 各类型数量统计 |
| `page_info.file_group_list` | object | 图片分组列表（仅 type=2 时有） |
| `page_info.file_group_list.biz_uin` | int | 当前公众号 bizuin |
| `page_info.file_group_list.file_group` | array | 分组列表 |
| `page_info.file_group_list.file_group[].id` | int | 分组 ID：`4`=最近使用，`0`=我的图片，`1`=未分组 |
| `page_info.file_group_list.file_group[].name` | string | 分组名称 |
| `page_info.file_group_list.file_group[].count` | int | 分组内文件数 |
| `page_info.watermark_status` | int | 水印状态：`2`=已设置 |
| `page_info.material_status` | int | 素材状态 |

**响应示例**:

```json
{
  "base_resp": {"ret": 0, "err_msg": ""},
  "can_use_voice": 1,
  "page_info": {
    "type": 2,
    "file_item": [],
    "file_cnt": {"img_cnt": 0, "voice_cnt": 0, "video_cnt": 0, "total": 0},
    "file_group_list": {
      "biz_uin": 3925403212,
      "file_group": [
        {"id": 4, "name": "最近使用", "count": 0, "files": []},
        {"id": 0, "name": "我的图片", "count": 0, "files": []},
        {"id": 1, "name": "未分组", "count": 0, "files": []}
      ]
    },
    "watermark_status": 2
  }
}
```

---

### 4.2 在编辑器中选择图片素材 GET [重要度: ⭐⭐⭐⭐]

```
GET /cgi-bin/filepage?action=select&token={token}&lang=zh_CN&group_id={gid}&begin=0&count=12&type=2&fingerprint={fp}&token={token}&lang=zh_CN&f=json&ajax=1
```

**用途**: 在文章编辑器"从图片库选择"弹窗中加载图片列表，支持按分组筛选。

**参数说明**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `action` | string | 固定值 `select`（区别于管理页的无 action） |
| `type` | int | `2`=图片 |
| `group_id` | int | 分组 ID：`0`=我的图片，`1`=未分组，`4`=最近使用 |
| `begin` | int | 分页偏移 |
| `count` | int | 每次获取数量，默认 `12` |

**响应结构**: 同 4.1，但无 `file_group_list`（分组已通过 `group_id` 筛选）

---

### 4.3 在编辑器中选择音频素材 GET [重要度: ⭐⭐⭐]

```
GET /cgi-bin/filepage?action=select&type=3&begin=0&count=9&query={keyword}&fingerprint={fp}&token={token}&lang=zh_CN&f=json&ajax=1
```

**用途**: 在文章编辑器"插入音频"弹窗中搜索和加载音频素材。

**参数说明**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `type` | int | `3` = 音频 |
| `query` | string | 搜索关键词（可为空，表示获取全部） |
| `count` | int | 每次获取数量，默认 `9` |
| `begin` | int | 分页偏移 |

**响应关键字段**: 同 4.1（`page_info.file_item` 包含音频列表，`page_info.type=3`）

---

### 4.4 搜索图片素材（公共图片库） GET [重要度: ⭐⭐]

```
GET /cgi-bin/photogallery?action=search&query={keyword}&type=0&limit=12&last_seq=0&fingerprint={fp}&token={token}&lang=zh_CN&f=json&ajax=1
```

**用途**: 在"从图片库选择"中搜索公共图片库（注：该公共图片库已下线，接口返回 730001 错误）。

**参数说明**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `action` | string | `search` |
| `query` | string | 搜索关键词 |
| `type` | int | `0`=全部类型 |
| `limit` | int | 每页数量，默认 `12` |
| `last_seq` | int | 翻页游标，首页为 `0` |

**响应**: `{"base_resp": {"ret": 730001, "err_msg": "default"}}` — 公共图片库已下线，官方提示使用 AI 配图。

---

## 五、合集管理

### 5.1 获取合集列表 GET [重要度: ⭐⭐⭐]

```
GET /cgi-bin/appmsgalbummgr?action=list&token={token}&lang=zh_CN&f=json&ajax=1
```

**用途**: 获取当前公众号创建的所有合集（专栏）列表。

**响应关键字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `list_resp.items` | array | 合集列表 |
| `list_resp.total` | int | 合集总数 |
| `list_resp.recommend_items` | array | 推荐合集列表 |
| `list_resp.selected_albums` | array | 已选中的合集 |
| `comm_resp.pay_album_gray` | int | 付费合集灰度状态 |
| `comm_resp.is_in_continous_read_whitelist` | int | 是否在连载白名单 |

**响应示例**:

```json
{
  "base_resp": {"ret": 0, "err_msg": "ok"},
  "comm_resp": {
    "is_in_continous_read_whitelist": 1,
    "pay_album_gray": 1,
    "pay_album_mgr_ban_status": 0
  },
  "list_resp": {
    "items": [],
    "total": 0,
    "recommend_items": [],
    "selected_albums": []
  }
}
```

---

## 六、搜索组件

### 6.1 获取文章内嵌搜索关键词 POST [重要度: ⭐⭐⭐]

```
POST /cgi-bin/searchplugin?action=getwords
```

**用途**: 获取已为当前文章设置的"插入搜索组件"关键词列表（帮助读者快捷搜索公众号内关联内容）。

**请求 Body** (form-urlencoded):

| 参数 | 类型 | 说明 |
|------|------|------|
| `fingerprint` | string | 浏览器指纹 |
| `token` | string | 会话 Token |
| `lang` | string | `zh_CN` |
| `f` | string | `json` |
| `ajax` | string | `1` |

**响应关键字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `result` | array | 已保存的搜索关键词列表 |
| `word_list` | array | 推荐关键词列表 |

---

## 七、AI 功能

### 7.1 检查 AI 配图使用条款同意状态 GET [重要度: ⭐⭐]

```
GET /cgi-bin/mpaigenpic?action=process_terms_of_use&token={token}&lang=zh_CN&f=json&ajax=1&fingerprint={fp}&random={r}
```

**用途**: 检查用户是否已同意 AI 配图功能使用条款。

**响应关键字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `agree` | int | `0`=未同意，`1`=已同意 |

---

### 7.2 获取 AI 配图使用条款内容 GET [重要度: ⭐]

```
GET /cgi-bin/announce?action=getannouncement&key=11724642113HBz0R&version=1&lang=zh_CN&platform=2&token={token}&lang=zh_CN&f=json&ajax=1
```

**用途**: 获取 AI 配图功能使用条款的完整 HTML 内容。

**参数说明**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `key` | string | 公告唯一标识，`11724642113HBz0R`=AI配图条款 |
| `version` | int | 版本号，`1` |
| `platform` | int | 平台标识，`2`=PC 端 |

**响应关键字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `getannouncement_resp.title` | string | 条款标题 |
| `getannouncement_resp.content` | string | 条款 HTML 内容（HTML 实体编码） |
| `getannouncement_resp.author` | string | 发布方 |
| `getannouncement_resp.online_time` | int | 发布时间戳 |
| `getannouncement_resp.status` | int | `1`=有效 |

---

## 八、广告与变现

### 8.1 获取广告协议状态 GET [重要度: ⭐⭐]

```
GET /merchant/ad_seller_manager?action=get_agreetment_ad&token={token}&lang=zh_CN&f=json&ajax=1&random={r}&begin=0&count=1&msg_type=1
```

**用途**: 检查当前公众号的广告投放协议签署状态及广告素材配置。

**响应关键字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `total_num` | int | 广告总数 |
| `ad_info_list` | array | 广告信息列表 |
| `category_list` | array | 广告分类列表 |

---

### 8.2 检查橱窗商品更新 GET [重要度: ⭐]

```
GET /cgi-bin/windowproduct?action=check_update_aff&fingerprint={fp}&token={token}&lang=zh_CN&f=json&ajax=1
```

**用途**: 检查橱窗商品（带货）的更新状态。

**响应关键字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `open_detail.already_open` | int | 是否已开通 |
| `open_detail.can_update` | int | 是否可更新 |
| `open_detail.agree_talent` | int | 是否已同意达人协议 |
| `open_detail.is_realname` | int | 是否已实名认证 |

---

### 8.3 获取橱窗商品信息 POST [重要度: ⭐⭐]

```
POST /cgi-bin/windowproduct?action=get_windowproduct
```

**用途**: 获取橱窗商品详情（达人带货功能）。

**请求 Body** (form-urlencoded):

| 参数 | 类型 | 说明 |
|------|------|------|
| `data` | string | JSON 字符串：`{"base_req":{"action":"MpGetTalentInfo"},"ext_info":"{}"}` |
| `fingerprint` | string | 浏览器指纹 |
| `token` | string | 会话 Token |

**响应关键字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `ext_info` | string | JSON 字符串（需二次解析） |
| `ext_info.has_talent` | bool | 是否已成为达人 |
| `ext_info.can_open_talent` | bool | 是否可开通达人功能 |
| `ext_info.fans_num_cond_ok` | bool | 粉丝数量是否达标 |
| `ext_info.qrcode_url` | string | 开通二维码 URL |

---

## 九、前端配置存储

### 9.1 获取前端服务配置 GET [重要度: ⭐⭐]

```
GET /cgi-bin/mmbizfrontendcommstore?operate_type=GetServiceData&service_name={name}&service_option=1&fingerprint={fp}&token={token}&lang=zh_CN&f=json&ajax=1
```

**用途**: 通用前端配置读取接口，通过 `service_name` 区分不同功能的配置项（用户级别的持久化设置）。

**已知 service_name 枚举**:

| service_name | 说明 |
|--------------|------|
| `recentlycolor_forecolor` | 最近使用的前景色 |
| `recentlycolor_backcolor` | 最近使用的背景色 |
| `recent_use_emotions` | 最近使用的表情 |
| `comment_option_version` | 留言功能版本配置 |
| `showFastReprintRedDot` | 是否显示快速转载红点 |
| `fastReprintValue` | 快速转载设置值 |
| `mpeditor_channel_product_cardtype` | 编辑器视频号商品卡片类型 |
| `mp_education_dialog` | 教育引导弹窗状态 |
| `editor_product_advice_is_closed` | 商品建议提示是否关闭 |
| `showUpgradeStore` | 是否显示升级商店提示 |
| `mpeditor_ailayout_reddot` | AI 排版红点提示 |
| `mpeditor_new_ailayout_is_edu_show` | AI 排版教育引导是否显示 |
| `editor_chat_red_dot` | 编辑器 AI 对话红点 |
| `mpeditor_new_btmcard_reddot` | 底部卡片红点提示 |
| `mpeditor_new_btmpoi_reddot` | 底部 POI 红点提示 |
| `claim_source_first_exposure_tips` | 创作来源首次展示提示 |

**响应**: 各接口返回 `err_code` 或具体配置值（结构因 service_name 而异）

---

## 十、小程序模板

### 10.1 获取私有模板列表 GET [重要度: ⭐⭐]

```
GET /wxamp/cgi/newtmpl/get_pritmpllist?random={r}&fingerprint={fp}&token={token}&lang=zh_CN&f=json&ajax=1
```

**用途**: 获取关联小程序的订阅消息私有模板列表（用于编辑器中插入小程序卡片）。

**响应关键字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `ret` | int | `1`=无权限/无数据，`0`=成功 |
| `list` | array | 模板列表 |
| `success` | bool | 是否成功 |

---

## 十一、AI 智能问答（知识库）

### 11.1 获取 AI 问答列表 GET [重要度: ⭐⭐]

```
GET /cgi-bin/zhuge_mp?action=get_user_qa_list&token={token}&lang=zh_CN&f=json&ajax=1&count=10&username=&type=99&context_buf=
```

**用途**: 获取知智能客服/AI 知识库的问答条目列表。

**参数说明**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `action` | string | `get_user_qa_list` |
| `count` | int | 每次获取数量，默认 `10` |
| `username` | string | 筛选用户名（空=全部） |
| `type` | int | 问答类型，`99`=全部 |
| `context_buf` | string | 分页上下文（首页为空） |

**响应关键字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `user_qa_list` | array | 问答列表 |

---

### 11.2 获取 AI 用户问题列表 GET [重要度: ⭐]

```
GET /cgi-bin/zhuge_mp?action=get_user_question_list&token={token}&lang=zh_CN&f=json&ajax=1&count=10&username=&type=99&context_buf=
```

**用途**: 获取用户提问的问题列表（用于 AI 回复训练）。结构与 11.1 相同，`action` 不同。

---

## 十二、编辑超链接 — 搜索公众号与获取文章列表

这三个接口是在文章编辑器的"**编辑超链接 > 选择账号文章**"功能中触发的，可用于抓取任意公众号的文章列表。

### 12.1 搜索公众号 GET [重要度: ⭐⭐⭐⭐⭐]

```
GET /cgi-bin/searchbiz?action=search_biz&begin=0&count=5&query={keyword}&fingerprint={fp}&token={token}&lang=zh_CN&f=json&ajax=1
```

**用途**: 按公众号名称或 WeChat ID 搜索公众号，返回账号列表（含 fakeid，用于后续获取文章列表）。

**参数说明**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `action` | string | 是 | 固定值 `search_biz` |
| `query` | string | 是 | 搜索关键词（公众号名称或微信ID），URL 编码 |
| `begin` | int | 是 | 分页起始位，从 `0` 开始 |
| `count` | int | 是 | 每页数量，默认 `5` |
| `fingerprint` | string | 是 | 浏览器指纹 |
| `token` | string | 是 | 会话 Token |

**响应关键字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `list` | array | 搜索结果公众号列表 |
| `list[].fakeid` | string | **关键字段**：Base64 编码的公众号 bizuin，用于后续接口 |
| `list[].nickname` | string | 公众号名称 |
| `list[].alias` | string | 微信号（英文 ID） |
| `list[].round_head_img` | string | 公众号头像 URL |
| `list[].service_type` | int | 账号类型：`1`=订阅号，`2`=服务号 |
| `list[].signature` | string | 公众号简介 |
| `list[].verify_status` | int | 认证状态：`2`=已认证 |
| `total` | int | 搜索结果总数 |

**响应示例**:

```json
{
  "base_resp": {"ret": 0, "err_msg": "ok"},
  "list": [
    {
      "fakeid": "MzA3MzI4MjgzMw==",
      "nickname": "机器之心",
      "alias": "almosthuman2014",
      "round_head_img": "http://mmbiz.qpic.cn/mmbiz_png/.../0?wx_fmt=png",
      "service_type": 1,
      "signature": "专业的人工智能媒体和产业服务平台",
      "verify_status": 2
    },
    {
      "fakeid": "MzI3MTA0MTk1MA==",
      "nickname": "新智元",
      "alias": "AI_era",
      "service_type": 1,
      "verify_status": 2
    }
  ],
  "total": 5
}
```

**fakeid 解码**: `MzA3MzI4MjgzMw==` Base64 解码 → `3073282833`（即该公众号的数字 bizuin）

---

### 12.2 获取指定公众号的文章列表 GET [重要度: ⭐⭐⭐⭐⭐]

```
GET /cgi-bin/appmsgpublish?sub=list&search_field=null&begin=0&count=5&query=&fakeid={fakeid}&type=101_1&free_publish_type=1&sub_action=list_ex&fingerprint={fp}&token={token}&lang=zh_CN&f=json&ajax=1
```

**用途**: 获取任意公众号的已发表文章列表（按时间倒序）。`fakeid` 从接口 12.1 的响应中获取。

**参数说明**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `sub` | string | 是 | 固定值 `list` |
| `fakeid` | string | 是 | 公众号 fakeid（Base64 编码），URL 编码传入 |
| `begin` | int | 是 | 分页起始位，从 `0` 开始，步长为 `count` |
| `count` | int | 是 | 每页数量，默认 `5` |
| `query` | string | 否 | 标题搜索关键词（空字符串=不过滤） |
| `search_field` | string | 否 | 搜索字段，不搜索时为 `null` |
| `type` | string | 是 | 固定值 `101_1`（启用外部账号文章列表） |
| `free_publish_type` | int | 是 | 固定值 `1` |
| `sub_action` | string | 是 | 固定值 `list_ex` |
| `fingerprint` | string | 是 | 浏览器指纹 |
| `token` | string | 是 | 会话 Token |

**响应关键字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `is_admin` | bool | 当前用户是否为管理员 |
| `publish_page` | string | **JSON 字符串**，需二次 `JSON.parse()` |
| `publish_page.total_count` | int | 文章总数（包含所有类型） |
| `publish_page.publish_count` | int | 普通发表数（包含本次分页数据的来源） |
| `publish_page.masssend_count` | int | 群发数 |
| `publish_page.publish_list` | array | 发表记录列表，每条为一次群发批次 |
| `publish_page.publish_list[].publish_type` | int | 发表类型：`1`=正常发表，`101`=转载/群发 |
| `publish_page.publish_list[].publish_info` | string | **JSON 字符串**，需三次解析，含 `appmsgex[]` |

**publish_info 内层字段（三层嵌套 JSON）**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `appmsgex` | array | 文章列表（一次群发可含多篇文章） |
| `appmsgex[].aid` | string | 文章唯一 ID，格式 `{appmsgid}_{itemidx}` |
| `appmsgex[].title` | string | 文章标题（搜索结果中含 `<em class="highlight">` 标签） |
| `appmsgex[].cover` | string | 封面图 URL（mmbiz.qpic.cn） |
| `appmsgex[].link` | string | 文章 URL，格式 `https://mp.weixin.qq.com/s/{path}` |
| `appmsgex[].digest` | string | 文章摘要 |
| `appmsgex[].update_time` | int | 更新时间戳（Unix） |
| `appmsgex[].appmsgid` | int | 图文消息 ID |
| `appmsgex[].itemidx` | int | 文章在群发中的位置索引（从 `1` 开始） |
| `appmsgex[].author_name` | string | 作者名 |
| `appmsgex[].album_id` | string | 所属合集 ID |
| `appmsgex[].appmsg_album_infos` | array | 合集信息（含 `id`、`title`） |
| `appmsgex[].copyright_type` | int | 版权类型：`0`=无，`1`=原创 |
| `appmsgex[].is_pay_subscribe` | int | 是否付费阅读：`0`=否 |
| `appmsgex[].ban_flag` | int | 是否违规：`0`=正常 |
| `publish_info.bizuin` | int | 所属公众号 bizuin（数字格式） |
| `publish_info.publish_status` | int | 发表状态：`200`=已发表 |
| `publish_info.create_time` | int | 发表时间戳 |

**分页说明**:

- 分页参数为 `begin`（偏移量），每次递增 `count`（默认 5）
- 总页数 = `ceil(publish_count / count)`
- `total_count = publish_count + masssend_count`
- 例：`total_count=5479, publish_count=1090` → 共 `ceil(1090/5)=218` 页

**响应示例（精简）**:

```json
{
  "base_resp": {"ret": 0, "err_msg": "ok"},
  "is_admin": true,
  "publish_page": "{\"total_count\":5479,\"publish_count\":1090,\"masssend_count\":4389,\"publish_list\":[{\"publish_type\":1,\"publish_info\":\"{\\\"appmsgex\\\":[{\\\"aid\\\":\\\"2651021419_1\\\",\\\"title\\\":\\\"文章标题\\\",\\\"link\\\":\\\"https://mp.weixin.qq.com/s/rbigQZU5XyoCWNd2P6sJ9Q\\\",\\\"digest\\\":\\\"摘要\\\",\\\"update_time\\\":1773398445,\\\"appmsgid\\\":2651021419,\\\"itemidx\\\":1,\\\"copyright_type\\\":1}]}\"}]}"
}
```

**解析代码示例（Python）**:

```python
import json, base64

resp = json.loads(response_text)
publish_page = json.loads(resp["publish_page"])
total_count = publish_page["total_count"]
publish_count = publish_page["publish_count"]

articles = []
for item in publish_page["publish_list"]:
    publish_info = json.loads(item["publish_info"])
    for article in publish_info.get("appmsgex", []):
        articles.append({
            "title": article["title"],
            "link": article["link"],
            "update_time": article["update_time"],
            "digest": article["digest"],
            "cover": article["cover"],
        })
```

---

### 12.3 搜索指定公众号的文章标题 GET [重要度: ⭐⭐⭐⭐⭐]

```
GET /cgi-bin/appmsgpublish?sub=search&search_field=7&begin=0&count=5&query={keyword}&fakeid={fakeid}&type=101_1&free_publish_type=1&sub_action=list_ex&fingerprint={fp}&token={token}&lang=zh_CN&f=json&ajax=1
```

**用途**: 在某公众号文章列表中按标题关键词搜索，支持分页。与 12.2 的区别：`sub=search`、`search_field=7`、`query` 非空。

**与 12.2 的参数差异**:

| 参数 | 接口 12.2 (列表) | 接口 12.3 (搜索) |
|------|-----------------|-----------------|
| `sub` | `list` | `search` |
| `search_field` | `null` | `7`（标题字段） |
| `query` | `""`（空） | 搜索关键词，如 `GPT` |

**搜索结果特点**:
- 匹配到的关键词在 `title` 字段中用 `<em class="highlight">关键词</em>` 包裹
- `total_count` 字段反映的是搜索命中总数（例：查"GPT"返回 833 条）
- 分页逻辑与 12.2 相同，`begin` 每次递增 `count`

**响应示例（精简）**:

```json
{
  "base_resp": {"ret": 0, "err_msg": "ok"},
  "publish_page": "{\"total_count\":833,\"publish_list\":[{\"publish_type\":1,\"publish_info\":\"{\\\"appmsgex\\\":[{\\\"aid\\\":\\\"2651021300_3\\\",\\\"title\\\":\\\"4B模型幻觉抑制能力超越<em class=\\\\\\\"highlight\\\\\\\">GPT<\\\\/em>-5\\\",\\\"link\\\":\\\"https://mp.weixin.qq.com/s/NGlyeDzbwnrLsPbvsfZTVg\\\"}]}\"}]}"
}
```

---

## 接口调用链路

### 文章编辑完整流程

```
1. 打开编辑器页面
   ├── GET /cgi-bin/switchacct          → 获取账号列表
   ├── POST /cgi-bin/appmsg (get_appmsg_update_history) → 获取历史版本
   ├── GET /cgi-bin/mpaigenpic (process_terms_of_use)   → 检查 AI 条款
   ├── GET /cgi-bin/operate_appmsg (get_recently_article_type) → 获取最近类型
   ├── POST /cgi-bin/operate_appmsg (pre_load_sentence) → 预加载 AI 辅助
   └── GET /cgi-bin/mmbizfrontendcommstore (多个)        → 加载编辑器配置

2. 插入图片
   ├── GET /cgi-bin/filepage?action=select&type=2       → 加载图片素材列表
   └── GET /cgi-bin/photogallery?action=search          → 搜索图片（已下线）

3. 插入音频
   └── GET /cgi-bin/filepage?action=select&type=3       → 加载音频素材列表

4. 插入视频
   └── GET /cgi-bin/appmsg?action=list&type=15          → 加载视频列表

5. 保存草稿
   └── POST /cgi-bin/appmsg?action=draft                → 保存草稿

6. 发表前检查
   └── POST /cgi-bin/masssend?action=check_music        → 检查音乐版权

7. 发表
   └── POST /cgi-bin/appmsg?action=publish (推断)       → 发表文章
```

### 素材库管理流程

```
进入素材库页面
├── GET /cgi-bin/filepage?type=2         → 获取图片列表
├── GET /cgi-bin/filepage?type=3         → 获取音频列表
└── GET /cgi-bin/filepage?type=15        → 获取视频列表
```

### 超链接对话框 — 抓取任意公众号文章流程（爬虫核心路径）

```
1. 搜索公众号
   └── GET /cgi-bin/searchbiz?action=search_biz&query={名称}
         → 返回 list[].fakeid（如 "MzA3MzI4MjgzMw=="）
               ↓
2. 获取该公众号文章列表（按时间倒序，分页）
   └── GET /cgi-bin/appmsgpublish?sub=list&fakeid={fakeid}&type=101_1
                                 &begin=0&count=5&sub_action=list_ex
         → 返回 publish_page（JSON字符串）
           → publish_page.total_count  — 总文章数
           → publish_page.publish_list[].publish_info（JSON字符串）
             → appmsgex[].title / link / cover / digest / update_time
               ↓
   翻页：begin += 5，直到 begin >= publish_count
               ↓
3. 按标题关键词过滤（可选）
   └── GET /cgi-bin/appmsgpublish?sub=search&search_field=7&query={词}
                                 &fakeid={fakeid}&type=101_1
                                 &begin=0&count=5&sub_action=list_ex
         → 同上结构，title 中命中词用 <em class="highlight"> 包裹
```

---

## 关键发现

1. **双重认证机制**: 所有接口同时需要 URL 中的 `token` 参数和 Cookie 中的 `slave_sid`/`bizuin` 等字段，缺一不可。`token` 约4小时过期，Cookie 约4天过期。

2. **fingerprint 参数**: 浏览器指纹（32位十六进制），固定生成后在本次会话中保持不变，用于防止 CSRF，多数接口必填。

3. **响应头 logicret**: 值为 `0` 表示业务逻辑通过，`730001` 表示功能已下线（如公共图片库）。

4. **公共图片库已下线**: `/cgi-bin/photogallery` 接口返回 `ret:730001`，官方改为 AI 配图功能，入口位于 `图片 > AI 配图`。

5. **mmbizfrontendcommstore 通用配置接口**: 通过 `service_name` 参数区分了十多种不同的前端配置，用于存储用户级别的编辑器偏好（颜色、表情等）。

6. **publish_page 双重 JSON**: `appmsgpublish` 接口的 `publish_page` 字段是 JSON 字符串形式（被字符串化了一次），使用时需要额外 `JSON.parse()`。

7. **接口路径规律**:
   - `/cgi-bin/appmsg` — 图文消息 CRUD（通过 `action` 区分操作）
   - `/cgi-bin/filepage` — 素材库（通过 `type` 区分媒体类型，`action=select` 用于编辑器内选择）
   - `/cgi-bin/operate_appmsg` — 编辑器辅助操作（通过 `sub` 区分）
   - `/cgi-bin/mmbizfrontendcommstore` — 通用前端配置存储
   - `/merchant/` — 商业化相关（广告、带货）

8. **bizuin 贯穿全程**: 公众号唯一标识 `bizuin`（数字格式）存于 Cookie，部分接口响应中也会返回，是串联各接口的核心数据。

9. **fakeid 与 bizuin 的关系**: `fakeid` 是 `bizuin` 的 Base64 编码形式。例：`MzA3MzI4MjgzMw==` Base64 解码为字符串 `3073282833`，即该账号的数字 bizuin。URL 传递时需 URL 编码（`=` → `%3D`）。

10. **`type=101_1` 是关键魔法参数**: `appmsgpublish` 接口在携带 `type=101_1&free_publish_type=1&sub_action=list_ex` 时，可通过 `fakeid` 参数获取**任意**公众号的文章列表，不限于当前登录账号。这是在编辑器"超链接选择文章"功能中实现的，且无需账号间关注关系。

11. **三层嵌套 JSON**: `appmsgpublish` 响应的数据经历三层包装：`response body (JSON)` → `publish_page (JSON string)` → `publish_list[].publish_info (JSON string)`。解析时需调用三次 `JSON.parse()`（或等效操作）。

12. **搜索接口的 `sub` 与 `search_field` 差异**: 无关键词时用 `sub=list&search_field=null`；按标题搜索时用 `sub=search&search_field=7&query={词}`。`search_field=7` 对应标题字段。

13. **`appmsgpublish` 分页基于 `publish_count` 而非 `total_count`**: `total_count` 包含群发和普通发表两种总数，实际可通过 `begin` 翻页的是 `publish_count` 的部分。翻页条件：`begin < publish_count`，步长为 `count`（默认 5）。
