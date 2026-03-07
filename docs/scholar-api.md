# Google Scholar API / 请求说明

## 概述

- **CLI Source**: `scholar`
- **当前实现**: 无官方可用 JSON API；走 Scholar 搜索页 HTML，再按结果 URL 抓正文或 PDF
- **主域名**:
  - `scholar.google.com`
  - 论文原站点域名（按结果而定）
- **认证**: 无固定登录要求，但非常容易触发 CAPTCHA / rate limit

## 当前代码实际使用的请求

### 1. Scholar 搜索页 GET

```text
GET https://scholar.google.com/scholar?q={query}&hl=en&start={offset}&scisbd=1&as_ylo={year_lo}&as_yhi={year_hi}&lr={lang}
```

**代码入口**:

- `web_scraper/sources/scholar/scrapers/search.py` -> `SearchScraper.search()`

**当前代码使用的主要参数**:

- `q`: 搜索词
- `hl=en`: UI 语言
- `start`: 分页偏移，按 `0, 10, 20...`
- `scisbd=1`: 按日期排序
- `as_ylo` / `as_yhi`: 年份范围
- `lr`: 语言过滤，如 `lang_en` / `lang_zh-CN`

**说明**:

- 返回的是 HTML 页面，代码通过 `BeautifulSoup` 解析结果项

### 2. 论文正文 / 落地页 GET

```text
GET {publisher_article_url}
```

**代码入口**:

- `web_scraper/sources/scholar/scrapers/article.py`

**说明**:

- Scholar 只提供跳转入口，正文由原始站点提供
- 当前实现会根据结果 URL 直接请求 publisher 页，或识别 PDF 内容类型后转文本

### 3. PDF 直链 GET

```text
GET {pdf_url}
```

**说明**:

- 当返回内容类型为 PDF 时，代码走 PDF 抽取逻辑

## 当前命令与请求映射

- `scraper scholar search ...` -> Scholar 搜索页 HTML
- `scraper scholar fetch ...` -> 落地页 HTML 或 PDF

## 结论

- `scholar` 当前不是私有 API 源
- 文档里保留请求说明，主要是为了统一说明它的查询参数和抓取链路
