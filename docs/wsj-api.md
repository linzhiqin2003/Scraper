# WSJ API / 请求说明

## 概述

- **CLI Source**: `wsj`
- **当前实现**: 不是私有 JSON API 驱动；主要走 RSS + 搜索页 HTML + 文章页 HTML
- **主域名**:
  - `www.wsj.com`
  - `feeds.a.dj.com`
- **认证**: RSS 可公开访问；搜索与正文受 WSJ 登录态和订阅状态影响

## 当前代码实际使用的请求

### 1. RSS Feed GET

当前代码内置的 RSS 源:

- `https://feeds.a.dj.com/rss/RSSWorldNews.xml`
- `https://feeds.a.dj.com/rss/RSSMarketsMain.xml`
- `https://feeds.a.dj.com/rss/RSSWSJD.xml`
- `https://feeds.a.dj.com/rss/WSJcomUSBusiness.xml`
- `https://feeds.a.dj.com/rss/RSSOpinion.xml`
- `https://feeds.a.dj.com/rss/RSSLifestyle.xml`

**代码入口**:

- `web_scraper/sources/wsj/scrapers/feeds.py` -> `fetch_feed()`

**说明**:

- `scraper wsj browse` 实际先拉 RSS，再按需抓正文
- RSS 返回 XML，不是 JSON API

### 2. 搜索页 HTML GET

```text
GET https://www.wsj.com/search?... 
```

**代码入口**:

- `web_scraper/sources/wsj/scrapers/search.py`

**当前代码使用的主要查询参数**:

- `query` / 关键词
- 排序映射: `desc` / `asc` / `relevance`
- 日期范围映射: `1d` / `7d` / `30d` / `1yr` / `all`
- 来源映射: `wsj` / `video` / `audio` / `livecoverage` / `buyside`

**说明**:

- 当前实现解析搜索结果页 HTML，不依赖稳定私有搜索接口

### 3. 文章页 HTML GET

```text
GET https://www.wsj.com/articles/...
```

**代码入口**:

- `web_scraper/sources/wsj/scrapers/article.py`

**说明**:

- 直接抓正文页 HTML，并解析 `article`、`time`、作者链接等元素
- 若订阅墙存在，正文抓取效果依赖登录 cookies

## 当前命令与请求映射

- `scraper wsj browse ...` -> RSS
- `scraper wsj search ...` -> 搜索页 HTML
- `scraper wsj fetch ...` -> 文章页 HTML

## 结论

- `wsj` 当前应视为“页面抓取 / RSS 抓取”，而不是“稳定 JSON API 爬虫”
- 本文件保留在 `docs/` 下，便于统一按 source 查看请求方式
