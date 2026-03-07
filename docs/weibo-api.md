# 微博 API / 请求说明

## 概述

- **CLI Source**: `weibo`
- **当前实现**:
  - 热搜: JSON API 优先
  - 详情: JSON API 优先
  - 个人主页: JSON API 优先
  - 搜索: 当前主要是搜索页 HTML，不是稳定 JSON 搜索接口
- **主域名**:
  - `weibo.com`
  - `s.weibo.com`
  - `passport.weibo.com`
- **认证**: 强依赖已保存登录态 cookies

## 当前代码实际使用的接口

### 1. 热搜接口 GET

```text
GET https://weibo.com/ajax/side/hotSearch
```

**代码入口**:

- `web_scraper/sources/weibo/scrapers/hot.py` -> `HotScraper._scrape_via_http()`

**特点**:

- 请求头会补 `Referer: https://weibo.com/hot/search`
- 返回体中实际消费 `data.realtime`

### 2. 微博详情接口 GET

```text
GET https://weibo.com/ajax/statuses/show?id={post_id}&locale=zh-CN&isGetLongText=true
```

**代码入口**:

- `web_scraper/sources/weibo/scrapers/detail.py` -> `DetailScraper._request_show_payload()`

**用途**:

- 获取微博正文、作者、长文内容、图片等核心字段

### 3. 评论接口 GET

```text
GET https://weibo.com/ajax/statuses/buildComments
```

**代码入口**:

- `web_scraper/sources/weibo/scrapers/detail.py` -> `DetailScraper._fetch_comments_api()`

**当前代码使用的关键参数**:

```json
{
  "is_reload": 1,
  "id": "mid",
  "is_show_bulletin": 2,
  "is_mix": 0,
  "count": 20,
  "fetch_level": 0,
  "locale": "zh-CN",
  "uid": "optional",
  "flow": 0,
  "max_id": 123456
}
```

### 4. 用户信息接口 GET

```text
GET https://weibo.com/ajax/profile/info?uid={uid}
```

### 5. 用户时间线接口 GET

```text
GET https://weibo.com/ajax/statuses/mymblog?uid={uid}&page={page}
```

### 6. 用户筛选搜索接口 GET

```text
GET https://weibo.com/ajax/statuses/searchProfile
```

**代码入口**:

- `web_scraper/sources/weibo/scrapers/profile.py`

**当前代码会按需携带的过滤参数**:

- `uid`
- `q`
- `page`
- `since_id`
- `starttime`
- `endtime`
- `hasori`
- `hastext`
- `haspic`
- `hasvideo`
- `hasmusic`
- `hasret`

### 7. 搜索页 HTML GET

```text
GET https://s.weibo.com/weibo?q={query}&page={page}
```

**代码入口**:

- `web_scraper/sources/weibo/scrapers/search.py`

**说明**:

- 当前仓库里的搜索不是直接调用官方 JSON 搜索接口，而是请求搜索结果页 HTML 后解析卡片

## 当前命令与请求映射

- `scraper weibo browse` -> `/ajax/side/hotSearch`
- `scraper weibo fetch` -> `/ajax/statuses/show` + `/ajax/statuses/buildComments`
- `scraper weibo profile ...` -> `/ajax/profile/info` + `/ajax/statuses/searchProfile` / `/ajax/statuses/mymblog`
- `scraper weibo search ...` -> `s.weibo.com` HTML 搜索页

## 鉴权与风控

- 所有 API 请求都依赖已保存的 storage state cookies
- 若响应里出现“登录”“频繁”“验证”“captcha”等信号，代码会抛出登录失效或限流错误
- API 失败时多数命令可回退到 Playwright
