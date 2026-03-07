# Google CSE API / 请求说明

## 概述

- **CLI Source**: `google`
- **当前实现**: 纯外部 API 源
- **主域名**:
  - `www.googleapis.com`
- **认证**:
  - `GOOGLE_CSE_API_KEY`
  - `GOOGLE_CSE_CX`

## 当前代码实际使用的接口

### 1. Custom Search GET

```text
GET https://www.googleapis.com/customsearch/v1
```

**代码入口**:

- `web_scraper/sources/google/scrapers/search.py`

**当前代码使用的关键 query 参数**:

```text
key={GOOGLE_CSE_API_KEY}
cx={GOOGLE_CSE_CX}
q=OpenAI
num=10
start=1
dateRestrict=w1
sort=date
hl=zh-CN
safe=off
searchType=image
```

**字段说明**:

- `key`: Google API Key
- `cx`: Custom Search Engine ID
- `q`: 查询词
- `num`: 单页结果数，代码限制为 `<= 10`
- `start`: 1-based 起始位置
- `dateRestrict`: 如 `d1` / `w1` / `m1` / `y1`
- `sort`: 当前只显式支持 `date`
- `hl`: 结果语言
- `safe`: `off` / `medium` / `high`
- `searchType=image`: 图片搜索

## 当前命令与请求映射

- `scraper google search ...` -> `customsearch/v1`
- 需要超过 10 条时，代码会自动分页拼接多个请求

## 响应消费方式

- 主要读取 `items`
- 总量和耗时来自 `searchInformation.totalResults` / `searchInformation.searchTime`
- 图片缩略图从 `pagemap.cse_thumbnail` 提取
