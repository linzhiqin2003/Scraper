# Reuters API / 请求说明

## 概述

- **CLI Source**: `reuters`
- **当前实现**: 搜索 / 分栏列表优先走 Reuters Arc JSON API，正文抓取优先走文章 HTML，再按需回退 Playwright
- **主域名**:
  - `www.reuters.com`
- **认证**: 公开内容通常无需登录；命中验证码或风控时会回退浏览器态

## 当前代码实际使用的接口

### 1. 搜索接口 GET

```text
GET https://www.reuters.com/pf/api/v3/content/fetch/articles-by-search-v2?query={json}
```

**代码入口**:

- `web_scraper/sources/reuters/client.py` -> `ReutersClient._search_via_api()`

**关键 query JSON 字段**:

```json
{
  "keyword": "Federal Reserve",
  "offset": 0,
  "size": 20,
  "sort": "relevance",
  "section": "world",
  "date": "past_week",
  "website": "reuters"
}
```

**说明**:

- `sort` 当前代码支持 `relevance` 和 `date:desc`
- `section` 可选，对应 `reuters/config.py` 里的 section slug
- `date` 可选，取值如 `past_24_hours` / `past_week` / `past_month` / `past_year`

### 2. 栏目列表接口 GET

```text
GET https://www.reuters.com/pf/api/v3/content/fetch/articles-by-section-alias-or-id-v1?query={json}
```

**代码入口**:

- `web_scraper/sources/reuters/client.py` -> `ReutersClient._get_section_via_api()`

**关键 query JSON 字段**:

```json
{
  "section_id": "/world/china/",
  "offset": 0,
  "size": 20,
  "website": "reuters"
}
```

**说明**:

- `section_id` 在代码里会被标准化为以 `/` 开头且以 `/` 结尾

### 3. 正文页 HTML GET

```text
GET https://www.reuters.com/{article-path}
```

**代码入口**:

- `web_scraper/sources/reuters/client.py` -> `ReutersClient.fetch_article()`

**说明**:

- 正文内容不是通过单独 JSON 正文接口获取
- 当前实现直接请求文章页 HTML，再用 `BeautifulSoup` 解析标题、作者、时间和正文
- 如果返回验证码页，会回退到 Playwright

## 当前命令与请求映射

- `scraper reuters search ...` -> 搜索 API，失败后回退搜索页 DOM
- `scraper reuters browse ...` -> 分栏 API，失败后回退 section 页面 DOM
- `scraper reuters fetch ...` -> 文章 HTML，必要时回退浏览器

## 鉴权与风控特征

- API 请求统一附带 `Accept: application/json`
- 请求头基于 `build_browser_headers()` 构造，尽量模拟真实浏览器
- 若 API 返回 `401` 且响应内带 captcha URL，代码视为被拦截并回退
- 若文章 HTML 中出现 `Verification Required` / `captcha` / `verify you are human` 等文案，也会触发回退
