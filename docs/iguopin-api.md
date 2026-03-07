# 国聘平台 (iguopin.com) API 接口文档

## 概述

- **网站地址**: https://gpxd.iguopin.com/ （国聘行动）、https://www.iguopin.com/ （主站）
- **API 域名**:
  - `gp-api.iguopin.com` — 新版 API（活动、广告、企业、岗位）
  - `api4.iguopin.com` — 旧版 API（文章、通知、导航、埋点）
- **认证方式**: 无需认证，所有接口公开访问
- **CORS**: 按域名限制（`gpxd.iguopin.com` 或 `www.iguopin.com`）

### 公共请求头

| Header | 值 | 说明 |
|--------|-----|------|
| `device` | `pc` | 设备类型（pc/mobile） |
| `subsite` | `iguopin` | 子站标识 |
| `version` | `5.0.0` / `5.2.300` | API 版本（活动页 5.0.0，主站 5.2.300） |
| `content-type` | `application/json` | POST 请求 |

### 响应格式

两套不同的成功码：

```json
// gp-api 新版
{"code": 200, "msg": "OK", "data": {...}, "trace": "..."}

// api4 旧版
{"code": 1, "msg": "获取成功", "time": 1770996975, "data": {...}}
```

---

## 一、国聘行动首页 (gpxd.iguopin.com)

### 1.1 站点信息 GET

```
GET gp-api.iguopin.com/api/base/site/v1/info?alias=iguopin
```

**用途**: 获取站点基础配置

**关键字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | string | 站点名称："国聘" |
| `show_logo` | string | Logo 图片 URL |
| `phone` | string | 客服电话 |
| `email` | string | 联系邮箱 |
| `slogan` | string | 标语 |
| `color` | string | 主题色 `#dd0000` |
| `host_config` | JSON string | 各端域名配置（pc/mobile） |

**host_config 域名映射**:

| 用途 | 域名 |
|------|------|
| 官网 | `www.iguopin.com` |
| 职位 | `www.iguopin.com` |
| 企业端 | `b.iguopin.com` |
| 个人端 | `c.iguopin.com` |
| 校园 | `gxcjy.iguopin.com` |
| IM | `chat.iguopin.com` |

---

### 1.2 活动信息 GET

```
GET gp-api.iguopin.com/api/activity/activity/v1/info?alias=gpxd3s
```

**用途**: 获取当前"国聘行动"活动基本信息

**关键参数**: `alias=gpxd3s` 是当前活动的唯一标识，后续多个接口依赖此值

**关键字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 活动 ID |
| `alias` | string | 活动别名 `gpxd3s` |
| `title` | string | "国聘行动" |
| `show_cover_img` | string | PC 封面图 |
| `show_mobile_cover_img` | string | 移动端封面图 |

---

### 1.3 招聘会列表 POST ⭐

```
POST gp-api.iguopin.com/api/activity/activity/v1/jobfair
```

**Request Body**:

```json
{
  "alias": "gpxd3s",
  "page_size": 6,
  "page": 1
}
```

**用途**: 获取进行中的招聘会列表

**响应** (`total: 10`):

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 招聘会 ID（用于 `hall-list` 接口） |
| `title` | string | 招聘会标题 |
| `short_title` | string | 短标题 |
| `start_time` / `end_time` | string | 起止时间 |
| `show_cover_img` | string | 封面图 |
| `status` | int | 状态（1=进行中） |
| `company_num` | int | 参会企业数 |
| `recruit_num` | int | 招聘人数 |
| `jobs_num` | int | 岗位数 |

**示例数据**:

```json
{
  "id": "182953369155929191",
  "title": "暖心助航，不负冬光——寒假实习招聘专场",
  "company_num": 122,
  "recruit_num": 1389,
  "jobs_num": 265
}
```

---

### 1.4 宣讲会/直播列表 POST

```
POST gp-api.iguopin.com/api/activity/activity/v1/conference
```

**Request Body**:

```json
{
  "alias": "gpxd3s",
  "page_size": 6,
  "page": 1
}
```

**用途**: 获取宣讲会和直播回放列表

**响应** (`total: 22`):

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 宣讲会 ID |
| `title` | string | 标题 |
| `organizer_name` | string | 主办方 |
| `cover_image_url` | string | 封面图（带 OSS 图片处理） |
| `video_view_link` | string | 视频回放链接（腾讯云 VOD） |
| `status` | int | 状态（3=已结束） |
| `show_view_number` | int | 观看人数 |
| `start_time` / `end_time` | string | 起止时间 |

---

### 1.5 参会企业列表 POST ⭐⭐

```
POST gp-api.iguopin.com/api/activity/activity/v1/company
```

**Request Body**:

```json
{
  "alias": "gpxd3s",
  "is_online_jobs": true,
  "page_size": 20,
  "page": 1
}
```

**用途**: 获取"热招单位"企业列表，对应首页的企业网格展示

**响应** (`total: 92`):

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 企业 ID（用于拼接详情页 URL） |
| `name` | string | 企业全称 |
| `short_name` | string | 简称 |
| `nature_cn` | string | 性质："国企" |
| `classify_cn` | string | 分类："央企(集团)" |
| `area_cn` | string | 地区 |
| `address` | string | 详细地址 |
| `industry_cn` | string | 行业 |
| `scale_cn` | string | 规模 |
| `show_logo` | string | Logo URL |
| `introduction` | string | 企业简介（完整文本） |
| `social_job_num` | int | 社招岗位数 |
| `campus_job_num` | int | 校招岗位数 |
| `jobs_num` | int | 总岗位数（页面显示为"X个热招职位"） |
| `recruit_num` | int | 总招聘人数 |

**详情页 URL 拼接规则**:

```
https://www.iguopin.com/company?id={id}
```

---

### 1.6 招聘会企业展厅 POST ⭐

```
POST gp-api.iguopin.com/api/activity/jobfair/company/v1/hall-list
```

**Request Body**:

```json
{
  "jobfair_id": "182953369155929191",
  "page_size": 6,
  "page": 1
}
```

**用途**: 获取特定招聘会下的企业及其岗位详情

**依赖**: `jobfair_id` 来自接口 1.3 的 `id` 字段

**响应**: 每个企业包含 `job_list` 数组，**每条岗位含完整职责和要求文本**

| 字段 (岗位级) | 类型 | 说明 |
|--------------|------|------|
| `job_name` | string | 岗位名称 |
| `recruitment_type_cn` | string | "校园招聘" / "社会招聘" |
| `nature_cn` | string | "实习" / "社招" |
| `min_wage` / `max_wage` | int | 薪资范围 |
| `wage_unit_cn` | string | "元/天" / "元/月" |
| `education_cn` | string | 学历要求 |
| `experience_cn` | string | 经验要求 |
| `district_list` | array | 工作地点列表 |
| `contents` | string | **完整岗位职责和任职要求** |
| `start_time` / `end_time` | string | 有效期 |

---

### 1.7 新闻文章列表 GET

```
GET api4.iguopin.com/api/channel/article/list?alias=gpxd_news&per_page=20
```

**用途**: 获取国聘行动相关新闻

**响应** (`total: 23`):

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | int | 文章 ID |
| `title` | string | 标题 |
| `link_url` | string | 外链（微信公众号、教育部等） |
| `create_time` | string | 发布时间 |

---

### 1.8 招聘通知列表 GET ⭐

```
GET api4.iguopin.com/api/notice/list?type=gpxd&per_page=20
```

**用途**: 获取招聘通知（央企/国企/事业单位招聘汇总）

**响应** (`total: 682`, 支持分页):

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | int | 通知 ID |
| `title` | string | 标题 |
| `click` | int | 点击量 |
| `link_url` | string | 外链 |
| `create_time` | string | 发布时间 |

---

### 1.9 广告/轮播 GET

```
GET gp-api.iguopin.com/api/base/ads/v1/list?page=1&page_size=100&alias={alias}
```

**支持的 alias 值**:

| alias | 用途 |
|-------|------|
| `GP_gpxd_index` | 首页轮播视频（5个） |
| `GP_navigation_QRcode` | 导航二维码 |
| `GP_bottom_nav_service` | 底部导航-服务 |
| `GP_bottom_nav_channel` | 底部导航-频道 |
| `GP_bottom_nav_guide` | 底部导航-指南 |

---

### 1.10 导航链接 GET

```
GET api4.iguopin.com/api/expnav/list?type=7
```

**用途**: 指导单位列表（国资委、教育部、人社部等）

---

## 二、企业详情页 (www.iguopin.com/company)

**页面 URL**: `https://www.iguopin.com/company?id={company_id}`

### 2.1 企业主页信息 GET ⭐

```
GET gp-api.iguopin.com/api/company/index/v1/home?company_id={company_id}
```

**用途**: 获取企业完整档案

**关键字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 企业 ID |
| `name` | string | 全称 |
| `short_name` | string | 简称 |
| `nature_cn` | string | "国企" |
| `classify_cn` | string | "央企(集团)" |
| `area_cn` | string | 地区："中国-北京-北京市-西城区" |
| `address` | string | 详细地址 |
| `industry_cn` | string | 行业 |
| `scale_cn` | string | 规模 |
| `show_logo` | string | Logo URL |
| `introduction` | string | 企业简介 |
| `group_id` | string | 所属集团 ID |
| `group_name` | string | 所属集团名称 |
| `social_code` | string | 统一社会信用代码 |
| `company_credit.score` | string | 信用评分 |

---

### 2.2 职位数量统计 GET

```
GET gp-api.iguopin.com/api/jobs/v1/count?company_id={company_id}
```

**响应示例** (中核集团):

```json
{
  "group_job_count": 71,
  "lower_job_count": 71,
  "company_job_count": 0,
  "all_count": 71,
  "social_count": 57,
  "campus_count": 14
}
```

| 字段 | 说明 |
|------|------|
| `group_job_count` | 集团总岗位数 |
| `lower_job_count` | 下级单位岗位数 |
| `company_job_count` | 本单位直属岗位数 |
| `social_count` | 社招岗位数 |
| `campus_count` | 校招岗位数 |

---

### 2.3 组织架构树 GET

```
GET gp-api.iguopin.com/api/company/organization/v1/tree?company_id={company_id}
```

**用途**: 获取集团下所有子公司的嵌套树形结构

**响应结构**:

```json
{
  "company_id": "10685296726633584",
  "name": "中国核工业集团有限公司",
  "organization_tree": {
    "company_id": "...",
    "name": "...",
    "job_count": 0,
    "children": [
      {
        "company_id": "...",
        "name": "子公司A",
        "job_count": 31,
        "children": [...]
      }
    ]
  }
}
```

每个节点字段：

| 字段 | 说明 |
|------|------|
| `company_id` | 子公司 ID |
| `name` / `short_name` | 名称 |
| `area_cn` | 地区 |
| `job_count` | 本单位岗位数 |
| `all_amount_count` | 含下级的总招聘人数 |
| `children` | 下级单位数组 |

---

### 2.4 本单位职位列表 POST

```
POST gp-api.iguopin.com/api/jobs/v1/list
```

**Request Body**:

```json
{
  "company_id": ["10685296726633584"],
  "order": [{"field": "sort", "sort": "desc"}]
}
```

**用途**: 获取本单位直属发布的岗位（集团本部通常为 0）

---

### 2.5 下级单位列表 GET

```
GET gp-api.iguopin.com/api/company/index/v1/children-list?company_id={company_id}
```

**用途**: 获取所有直属下级单位（扁平数组），用于"下级单位"卡片展示

| 字段 | 说明 |
|------|------|
| `company_id` | 子公司 ID |
| `company_name` | 名称 |
| `show_logo` | Logo |
| `jobs_num` | 在招岗位数 |

---

### 2.6 下级单位岗位列表 POST ⭐⭐⭐（最核心接口）

```
POST gp-api.iguopin.com/api/jobs/v1/home-job
```

**Request Body**:

```json
{
  "page": 1,
  "page_size": 20,
  "company_id_only_sub": "10685296726633584",
  "order": [{"field": "update_time", "sort": "desc"}]
}
```

**用途**: 获取集团下所有子公司的岗位完整详情，**数据最丰富的接口**

**支持的筛选参数** (推测，基于筛选字典接口):

| 参数 | 说明 |
|------|------|
| `company_id_only_sub` | 集团 ID（只查下级） |
| `page` / `page_size` | 分页 |
| `order` | 排序字段和方向 |
| `education` | 学历筛选 |
| `experience` | 经验筛选 |
| `district` | 地区筛选 |
| `nature` | 招聘类型（社招/校招） |

**响应** (每条岗位):

| 字段 | 类型 | 说明 |
|------|------|------|
| `job_id` | string | 岗位 ID |
| `job_name` | string | 岗位名称 |
| `company_id` | string | 所属子公司 ID |
| `company_name` | string | 所属子公司名称 |
| `recruitment_type_cn` | string | "社会招聘" / "校园招聘" |
| `nature_cn` | string | "社招" / "实习" |
| `min_wage` / `max_wage` | int | 薪资范围 |
| `wage_unit_cn` | string | "元/月" / "元/天" |
| `months` | int | 年薪月数（如 15） |
| `is_negotiable` | bool | 是否面议 |
| `education_cn` | string | 学历要求 |
| `experience_cn` | string | 经验要求 |
| `amount` | int | 招聘人数 |
| `district_list` | array | 工作地点（area_cn + address） |
| `contents` | string | **完整岗位职责和任职资格** |
| `start_time` / `end_time` | string | 有效期 |
| `create_time` / `update_time` | string | 创建/更新时间 |
| `company_info` | object | 所属企业信息（名称、行业、规模、Logo） |
| `applied` | int | 申请状态 |

---

### 2.7 筛选项字典 POST

```
POST gp-api.iguopin.com/api/base/category/v1/by-alias
```

**Request Body**:

```json
{
  "alias": ["job_experience", "job_nature", "job_major", "job_education"]
}
```

**用途**: 获取岗位筛选的枚举值

**响应**: 按 alias 分组返回枚举列表

| alias | 内容 |
|-------|------|
| `job_education` | 学历：博士、硕士、本科、大专、高中... |
| `job_experience` | 经验：在校生、应届生、1-3年、3-5年、5-10年... |
| `job_nature` | 招聘性质 |
| `job_major` | 专业分类（树形结构：哲学→哲学类、经济学→金融学类...） |

---

### 2.8 行政区划树 GET

```
GET gp-api.iguopin.com/api/base/districts/v1/tree
```

**用途**: 全国省-市-区三级行政区划，用于地区筛选

---

## 三、职位搜索页 (www.iguopin.com/job)

**页面 URL**: `https://www.iguopin.com/job` 或 `https://www.iguopin.com/job?om=1168Qucp&om_cn=仅看高端`

### 3.1 推荐/搜索职位 POST （核心搜索接口）

```
POST gp-api.iguopin.com/api/jobs/v1/recom-job
```

**用途**: 职位搜索和推荐列表，支持关键词、城市、薪资、经验、招聘性质等多种筛选条件组合

**Request Body (第1页)**:

```json
{
  "search": {
    "page": 1,
    "page_size": 20,
    "keyword": "Python",
    "district": ["000000.110000"],
    "wage": [10000, 20000],
    "nature": ["113Fc6wc"],
    "om": ["1168Qucp"]
  },
  "recom": {
    "update_time": true,
    "company_nature": true,
    "hot_job": true
  }
}
```

**Request Body (第2页及之后)**:

```json
{
  "search": {
    "page": 2,
    "page_size": 20,
    "remove_job_id": ["183843476901725296", "183843477086274672", "..."],
    "om": ["1168Qucp"]
  },
  "recom": {
    "update_time": true,
    "company_nature": true,
    "hot_job": true
  }
}
```

**search 对象参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `page` | int | 是 | 页码，从 1 开始 |
| `page_size` | int | 是 | 每页数量，默认 20 |
| `keyword` | string | 否 | 搜索关键词（匹配岗位名称、内容等） |
| `district` | string[] | 否 | 地区编码数组，格式 `"000000.110000"`（国家.省）或 `"000000.110000.110100"`（国家.省.市） |
| `wage` | int[] | 否 | 薪资范围 `[min, max]`，单位元/月。预设区间：`[0,5000]` `[5000,10000]` `[10000,20000]` `[20000,40000]` `[40000,60000]` `[60000,999999]` |
| `nature` | string[] | 否 | 招聘性质 value 码（来自 category/by-alias 接口），社招=`113Fc6wc`，校招=`115xW5oQ`，实习=`11bTac9`，公职类/见习/兼职等 |
| `experience` | string[] | 否 | 经验要求 value 码，如应届生=`114Mh7Wi`，1-3年=`113aJGtA`，3-5年=`116PfdYT` |
| `education` | string[] | 否 | 学历要求 value 码，如博士=`115VXVUi`，硕士=`116VSUN1`，本科=`116yhC4D` |
| `om` | string[] | 否 | 运营标签，`1168Qucp` = 高端职位，`116NNJgJ` = 热门职位 |
| `remove_job_id` | string[] | 否 | 翻页时排除已展示的 job_id 列表（第2页开始使用） |

**recom 对象参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `update_time` | bool | 按更新时间推荐 |
| `company_nature` | bool | 按企业性质推荐 |
| `hot_job` | bool | 热门岗位推荐 |

**响应格式**:

```json
{
  "code": 200,
  "msg": "OK",
  "data": {
    "total": 400,
    "page": 1,
    "page_size": 20,
    "list": [...]
  }
}
```

**注意**: `total` 最大返回 400，即使实际结果更多也只返回 400

**响应 list 中每条岗位的字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `job_id` | string | 岗位 ID（长整型字符串） |
| `job_name` | string | 岗位名称 |
| `company_id` | string | 企业 ID |
| `company_name` | string | 企业名称 |
| `recruitment_type` | string | 招聘类型 value 码 |
| `recruitment_type_cn` | string | "校园招聘" / "社会招聘" |
| `nature` | string | 性质 value 码 |
| `nature_cn` | string | "社招" / "校招" / "实习" / "见习" / "兼职" |
| `category` | string | 职位类别码（三级，点分格式） |
| `category_cn` | string | 职位类别名称 |
| `amount` | int | 招聘人数（0 表示不限） |
| `min_wage` | int | 最低薪资（0 表示面议） |
| `max_wage` | int | 最高薪资 |
| `wage_unit` | string | 薪资单位 value 码 |
| `wage_unit_cn` | string | "元/月" / "元/天" |
| `months` | int | 年薪月数（12/13/14/15/16 等） |
| `is_negotiable` | bool | 是否面议 |
| `education` | string | 学历 value 码 |
| `education_cn` | string | "博士" / "硕士" / "本科" / "大专" 等 |
| `experience` | string | 经验 value 码 |
| `experience_cn` | string | "应届生" / "1-3年" / "5-10年" 等 |
| `is_graduates` | bool | 是否面向应届生 |
| `major` | string[] | 专业要求 value 码数组 |
| `major_cn` | string[] | 专业要求名称数组 |
| `job_tags` | string[] | 岗位标签 value 码（部分岗位有） |
| `job_tags_cn` | string[] | 岗位标签名称，如 "Java" "Python" "自然语言处理" |
| `industry` | string[] | 行业 value 码 |
| `industry_cn` | string[] | 行业名称 |
| `om` | string[] | 运营标签 value 码 |
| `om_cn` | string[] | 运营标签名称，如 "高端职位" "热门职位" |
| `department` | int | 部门 ID（0 表示公司级别） |
| `department_cn` | string | 部门名称 |
| `start_time` | string | 招聘开始时间 |
| `end_time` | string | 招聘截止时间 |
| `district_list` | array | 工作地点列表 |
| `district_list[].area_code` | string | 地区编码（点分4级） |
| `district_list[].area_cn` | string | 地区名称 "北京-西城区" |
| `district_list[].address` | string | 详细地址 |
| `district_list[].house_number` | string | 门牌号 |
| `district_list[].longitude` | string | 经度 |
| `district_list[].latitude` | string | 纬度 |
| `contents` | string | **完整岗位职责和任职要求**（纯文本） |
| `template` | string | 模板类型 "default" |
| `status` | int | 状态（1=有效） |
| `is_apply` | bool | 是否可投递 |
| `contact_user` | object | 联系人（通常为空，需登录） |
| `user_id` | string | 发布者 ID |
| `subsite` | int | 子站 ID |
| `refresh_time` | string | 最近刷新时间 |
| `create_time` | string | 创建时间 |
| `update_time` | string | 更新时间 |
| `offline_type` | int | 下线类型（0=手动, 1=到期, 2=其他） |
| `company_info` | object | 企业信息（内嵌） |
| `company_info.name` | string | 企业全称 |
| `company_info.nature_cn` | string | 企业性质 "国企" |
| `company_info.industry_cn` | string | 行业 |
| `company_info.scale_cn` | string | 规模 "1000-2000人" |
| `company_info.show_logo` | string | Logo URL |
| `company_info.company_credit` | object | 企业信用（含 score） |
| `is_favorite` | bool | 是否收藏 |
| `applied` | int | 投递状态（2=未投递） |
| `project_config` | object | 项目配置（模板、显示选项） |

**岗位详情页 URL**: `https://www.iguopin.com/job/{job_id}` （SSR 渲染，无独立 API）

---

### 3.2 分页机制

该接口的分页机制比较特殊：

- **第1页**: 正常传 `page: 1, page_size: 20`
- **第2页及之后**: 除了 `page: 2` 外，还需传入 `remove_job_id` 数组，包含第1页所有已展示的 job_id，用于排重
- **总量限制**: `total` 字段最大返回 400，即使满足条件的岗位更多
- **最大页数**: `total / page_size` 即 400/20 = 20 页

---

### 3.3 筛选项字典 POST

```
POST gp-api.iguopin.com/api/base/category/v1/by-alias
```

**Request Body**:

```json
{
  "alias": [
    "job_experience",
    "job_nature",
    "job_major",
    "job_education",
    "company_nature",
    "company_scale",
    "financing_stage",
    "research",
    "zwfl"
  ]
}
```

**用途**: 获取职位搜索页所有筛选项的枚举值列表

**响应各分类及常用 value 码**:

#### job_experience (工作经验)

| label | value |
|-------|-------|
| 在校生 | `112QSAqm` |
| 应届生 | `114Mh7Wi` |
| 经验不限 | `113upZvj` |
| 1年以内 | `11ivfg6` |
| 1-3年 | `113aJGtA` |
| 1-5年 | `112tTY6B` |
| 3-5年 | `116PfdYT` |
| 5-10年 | `112eGWE7` |
| 10-15年 | `113VebCw` |
| 15-20年 | `11PN5Ln` |
| 20年以上 | `114JPLBk` |

#### job_education (学历要求)

| label | value |
|-------|-------|
| 博士 | `115VXVUi` |
| 硕士 | `116VSUN1` |
| 本科 | `116yhC4D` |
| 大专 | `11FRXBG` |
| 高中 | `1129dbjh` |
| 中专/中技 | `117A2ZJK` |
| 初中 | `116CME44` |
| 无学历要求 | `113Auqab` |

#### company_nature (企业性质)

| label | value |
|-------|-------|
| 国企 | `11AzDak` |
| 民营企业 | `1145DorR` |
| 中外合资 | `1178xpmL` |
| 外商独资 | `113yihzr` |
| 事业单位 | `11X9v75` |
| 上市公司 | `1138MxX6` |
| 国家机关 | `117DFgXe` |
| 股份制企业 | `114YphLU` |

#### company_scale (企业规模)

| label | value |
|-------|-------|
| 50人以下 | `113Eqfqy` |
| 50-100人 | `115yq73J` |
| 100-300人 | `117Ng4GL` |
| 300-500人 | `112JjHq4` |
| 500-1000人 | `113vnULY` |
| 1000-2000人 | `112Qy915` |
| 2000-5000人 | `116HQ5Hi` |
| 5000-10000人 | `112v92gk` |
| 10000-30000人 | `112iwT1R` |
| 30000人以上 | `11WdDuZ` |

#### financing_stage (融资阶段)

| label | value |
|-------|-------|
| 未融资 | `117QV6Tc` |
| 天使轮 | `112bJEHZ` |
| A轮 | `115UkqpF` |
| B轮 | `11vRd51` |
| C轮 | `11GY6Ae` |
| D轮以上 | `115NFQWU` |
| 已上市 | `116NUSfx` |

---

### 3.4 行政区划树 GET

```
GET gp-api.iguopin.com/api/base/districts/v1/tree
```

**用途**: 获取全国省-市-区三级行政区划，用于职位搜索的城市筛选

**响应结构**: 四级嵌套树形结构（国家 → 省/直辖市 → 市 → 区/县）

```json
{
  "value": "000000",
  "label": "中国",
  "children": [
    {
      "value": "110000",
      "label": "北京",
      "lat": 39.904989,
      "lng": 116.407387,
      "children": [
        {
          "value": "110100",
          "label": "北京",
          "children": [
            {"value": "110101", "label": "东城区"},
            {"value": "110102", "label": "西城区"},
            {"value": "110105", "label": "朝阳区"}
          ]
        }
      ]
    }
  ]
}
```

**district 参数拼接规则**: 使用点分格式拼接 `国家.省` 或 `国家.省.市`
- 北京全市: `"000000.110000"`
- 北京市: `"000000.110000.110100"`
- 上海: `"000000.310000"`

---

### 3.5 广告/推广位 GET

```
GET api4.iguopin.com/api/spread/list?alias={alias}
```

**支持的 alias**:

| alias | 用途 |
|-------|------|
| `GP_campus_job_list_right` | 职位列表页右侧广告位（上方） |
| `GP_campus_job_list_right_2` | 职位列表页右侧广告位（下方） |
| `GP_recruitment_homepage` | 企业主页推广位 |

---

## 四、企业详情页 (www.iguopin.com/company)

**页面 URL**: `https://www.iguopin.com/company?id={company_id}`

### 4.1 企业主页信息 GET

```
GET gp-api.iguopin.com/api/company/index/v1/home?company_id={company_id}
```

**用途**: 获取企业完整档案

**关键字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string | 企业 ID |
| `name` | string | 全称 |
| `short_name` | string | 简称 |
| `show_name` | string | 显示名称 |
| `nature_cn` | string | 企业性质 "国企" |
| `classify_cn` | string | 分类 "央企(集团)" / "央企(子企)" |
| `area_cn` | string | 地区 "中国-北京-北京市" |
| `address` | string | 详细地址 |
| `industry_cn` | string | 行业 |
| `scale_cn` | string | 规模 |
| `show_logo` | string | Logo URL |
| `introduction` | string | 企业简介（完整文本） |
| `group_id` | string | 所属集团 ID |
| `group_name` | string | 所属集团名称 |
| `group_short_name` | string | 集团简称 |
| `website` | string | 企业官网 |
| `social_code` | string | 统一社会信用代码 |
| `company_credit.score` | string | 企业信用评分 |
| `is_official` | int | 是否官方认证 |

---

### 4.2 职位数量统计 GET

```
GET gp-api.iguopin.com/api/jobs/v1/count?company_id={company_id}
```

**响应示例**:

```json
{
  "group_job_count": 23,
  "lower_job_count": 0,
  "company_job_count": 23,
  "all_count": 23,
  "social_count": 0,
  "campus_count": 23
}
```

| 字段 | 说明 |
|------|------|
| `group_job_count` | 集团总岗位数 |
| `lower_job_count` | 下级单位岗位数 |
| `company_job_count` | 本单位直属岗位数 |
| `social_count` | 社招岗位数 |
| `campus_count` | 校招岗位数 |

---

### 4.3 组织架构树 GET

```
GET gp-api.iguopin.com/api/company/organization/v1/tree?company_id={company_id}
```

**用途**: 获取集团下所有子公司的嵌套树形结构

**响应结构**:

```json
{
  "company_id": "10698197366712845",
  "group_name": "中国能源建设股份有限公司",
  "short_name": "中国能建",
  "organization_tree": {
    "company_id": "10685404587149616",
    "name": "中国电力工程顾问集团华北电力设计院有限公司",
    "job_count": 23,
    "children": [...]
  }
}
```

每个节点字段：

| 字段 | 说明 |
|------|------|
| `company_id` | 子公司 ID |
| `name` / `short_name` | 名称 |
| `area_cn` | 地区 |
| `job_count` | 本单位岗位数 |
| `all_job_count` | 含下级的总岗位数 |
| `targeted_jobs_count` | 定向岗位数 |
| `untargeted_jobs_count` | 非定向岗位数 |
| `children` | 下级单位数组 |

---

### 4.4 企业职位列表 POST

```
POST gp-api.iguopin.com/api/jobs/v1/list
```

**Request Body**:

```json
{
  "company_id": ["10685404587149616"],
  "order": [{"field": "sort", "sort": "desc"}]
}
```

**用途**: 获取指定企业发布的所有岗位列表（默认 page_size=10）

**响应**: 与 recom-job 接口的 list 字段结构完全一致

---

### 4.5 下级单位列表 GET

```
GET gp-api.iguopin.com/api/company/index/v1/children-list?company_id={company_id}
```

**用途**: 获取所有直属下级单位（扁平数组），用于"下级单位"卡片展示

---

### 4.6 下级单位岗位列表 POST

```
POST gp-api.iguopin.com/api/jobs/v1/home-job
```

**Request Body**:

```json
{
  "page": 1,
  "page_size": 20,
  "company_id_only_sub": "10685296726633584",
  "order": [{"field": "update_time", "sort": "desc"}]
}
```

**用途**: 获取集团下所有子公司的岗位完整详情

---

## 五、接口调用链路

### 国聘行动首页

```
site/info (站点配置)
  ↓
activity/info (活动信息, alias=gpxd3s)
  ↓
  ├── activity/jobfair (招聘会列表)
  │     └── jobfair/company/hall-list (招聘会展厅, 需 jobfair_id)
  ├── activity/conference (宣讲会列表)
  ├── activity/company (热招企业列表)
  ├── channel/article/list (新闻)
  ├── notice/list (通知)
  ├── ads/list (轮播)
  └── expnav/list (导航)
```

### 企业详情页

```
company/home (企业信息, 需 company_id)
  ↓
  ├── jobs/count (岗位统计)
  ├── organization/tree (组织架构)
  ├── jobs/list (本单位岗位)
  ├── children-list (下级单位卡片)
  │
  └── [点击"下级单位职位"标签]
        ├── category/by-alias (筛选字典)
        ├── districts/tree (地区筛选)
        └── jobs/home-job (下级岗位列表, 最核心)
```

### ID 关联关系

```
activity/info → alias ("gpxd3s")
  → jobfair → id ("182953369155929191") → hall-list
  → company → id ("10685296726633584") → /company?id={id}
    → company/home → company_id → jobs/count, organization/tree, jobs/list
    → children-list → company_id (子公司)
    → jobs/home-job (company_id_only_sub)
```

---

## 四、关键发现

1. **全部无鉴权**: 所有接口无需登录即可访问，数据完全公开
2. **两套 API 体系**: 新版 `gp-api`（code=200）和旧版 `api4`（code=1）并存
3. **数据最丰富的接口**: `jobs/v1/home-job` 只需传入集团 ID 即可获取所有下级单位的岗位完整详情
4. **活动标识**: `alias=gpxd3s` 是关键参数，贯穿首页多个接口
5. **企业 ID 是长整型**: 如 `10685296726633584`，非 UUID
6. **OSS 图片**: 所有图片托管在阿里云 OSS (`iguopin-*.oss-cn-beijing.aliyuncs.com`)
7. **视频托管**: 宣讲会回放使用腾讯云 VOD
8. **地图服务**: 详情页嵌入高德地图（key: `4bc4d8a5c0dd9de9c33442a3813482e6`）
9. **分页约定**: POST 接口用 `page` + `page_size`，GET 接口用 `per_page`
10. **企业分级**: 央企集团 → 子公司 → 孙公司，组织架构树支持多级嵌套
