# 小红书 API / 请求说明

## 概述

- **CLI Source**: `xhs`
- **当前实现**:
  - 笔记详情优先从页面 SSR 状态 `__INITIAL_STATE__` 取数
  - 评论通过浏览器上下文内 `fetch()` 调用评论接口
  - 图片直接走 CDN 下载
- **主域名**:
  - `www.xiaohongshu.com`
  - `edith.xiaohongshu.com`
- **认证**: 依赖浏览器真实会话；评论接口签名由浏览器环境和站点自身逻辑兜底

## 当前代码实际使用的请求

### 1. 笔记页 GET

```text
GET https://www.xiaohongshu.com/explore/{note_id}?xsec_token={token}
```

兼容格式:

- `https://www.xiaohongshu.com/explore/{note_id}?xsec_token=...`
- `https://www.xiaohongshu.com/discovery/item/{note_id}?xsec_token=...`
- `https://xhslink.com/...`

**代码入口**:

- `web_scraper/sources/xiaohongshu/scrapers/api.py` -> `XHSApiScraper.fetch_note()`

**说明**:

- 正文核心字段不是从单独 JSON 接口取，而是直接读取页面内的 `window.__INITIAL_STATE__`

### 2. 评论接口 GET

```text
GET https://edith.xiaohongshu.com/api/sns/web/v2/comment/page
```

**代码入口**:

- `web_scraper/sources/xiaohongshu/scrapers/api.py` -> `XHSApiScraper._fetch_comments_api()`

**当前代码使用的关键参数**:

```json
{
  "note_id": "note_id",
  "cursor": "",
  "top_comment_id": "",
  "image_formats": "jpg,webp,avif",
  "xsec_token": "token"
}
```

**请求特点**:

- 在页面上下文里执行 `fetch()`
- `credentials: include`
- 请求头显式带 `Origin: https://www.xiaohongshu.com` 和 `Referer`

### 3. 图片 / 视频资源 GET

**说明**:

- 图片和视频 URL 来自 `__INITIAL_STATE__`
- 下载时直接请求资源 URL，本仓库没有单独封装媒体元数据接口

## 当前命令与请求映射

- `scraper xhs api-fetch ...` -> 笔记页 SSR + 评论 API
- `scraper xhs fetch ...` / `search` / `browse` -> 主要是页面抓取；`api-fetch` 是当前最明确的 API 化路径

## 风控与会话说明

- 若首次进入笔记页被重定向，代码会先访问 `explore` 页做 session warm-up
- 若 `xsec_token` 过期，评论接口和笔记访问都可能失败
- 当前实现把浏览器当作签名和 Cookie 承载环境，而不是在 Python 侧重放签名算法
