# Serper API / 请求说明

## 概述

- **CLI Source**: `serper`
- **当前实现**: 纯外部 API 源
- **主域名**:
  - `google.serper.dev`
- **认证**: `SERPER_API_KEY` 环境变量

## 当前代码实际使用的接口

### 1. Web Search POST

```text
POST https://google.serper.dev/search
```

### 2. News Search POST

```text
POST https://google.serper.dev/news
```

### 3. Image Search POST

```text
POST https://google.serper.dev/images
```

**代码入口**:

- `web_scraper/sources/serper/scrapers/search.py`

**统一请求头**:

```http
X-API-KEY: ${SERPER_API_KEY}
Content-Type: application/json
```

**当前代码使用的请求体字段**:

```json
{
  "q": "OpenAI",
  "num": 10,
  "tbs": "qdr:w",
  "gl": "us",
  "hl": "en"
}
```

**字段说明**:

- `q`: 查询词
- `num`: 最大结果数，代码限制为 `<= 100`
- `tbs`: 时间过滤，如 `qdr:d` / `qdr:w` / `qdr:m` / `qdr:y`
- `gl`: 国家代码
- `hl`: 语言代码

## 当前命令与请求映射

- `scraper serper search ... --type search` -> `/search`
- `scraper serper search ... --type news` -> `/news`
- `scraper serper search ... --type images` -> `/images`

## 响应消费方式

- 普通网页搜索读取 `organic`
- 新闻搜索读取 `news`
- 图片搜索读取 `images`
- 额外透传 `knowledgeGraph`、`answerBox` 和 `credits`
