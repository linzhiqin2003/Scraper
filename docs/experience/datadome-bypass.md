# DataDome 反 Bot 绕过经验

## DataDome 简介

DataDome 是一种商业反 bot 服务，被 WSJ、Dow Jones 等网站使用。其检测域名为 `captcha-delivery.com` / `geo.captcha-delivery.com`。

## 检测机制

| 检测项 | 说明 | 被检测时的表现 |
|--------|------|----------------|
| `navigator.webdriver` | 自动化浏览器标志 | 值为 `true` 时直接 block |
| Chrome automation flags | `--enable-automation` 等 | 黄色横幅 "Chrome is being controlled by automated test software" |
| TLS fingerprint | HTTP 客户端的 TLS 握手特征 | 纯 httpx/requests 请求被拒 |
| IP 信誉 | IP 历史行为评分 | 被标记后即使真实浏览器也需过 CAPTCHA |
| 请求频率/模式 | 异常的请求模式 | 触发频率限制 |

## 绕过方案对比

| 方案 | 可行性 | 说明 |
|------|--------|------|
| 纯 HTTP (httpx/requests) | ❌ | TLS fingerprint 被识别 |
| curl-cffi | ⚠️ | 可模拟 TLS fingerprint，但无法过 CAPTCHA |
| Playwright (标准) | ❌ | `navigator.webdriver=true`，被立即检测 |
| Playwright + stealth | ⚠️ | 部分隐藏但不完全 |
| **Patchright** | ✅ | webdriver=false，无 automation flags |
| CDP 接管真实 Chrome | ✅ | 完全不可检测，但需要用户先启动 Chrome |

## Patchright 使用要点

### 安装

```bash
poetry add patchright
# Patchright 自带 Chromium，不需要额外安装浏览器
```

### 基本用法

```python
from patchright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    # headless=False 对 CAPTCHA 场景更可靠
    ctx = browser.new_context()
    page = ctx.new_page()
```

### headless 模式

- `headless=False`：推荐用于需要过 CAPTCHA 的场景
- `headless=True`：IP 未被标记时可用，但遇到 CAPTCHA 无法人工介入

## DataDome Slider CAPTCHA 自动解决

### 识别 CAPTCHA

DataDome 的 CAPTCHA 在独立的 iframe 中加载，URL 包含 `captcha` 或 `geo.captcha`：

```python
def find_captcha_frame(page):
    for f in page.frames:
        if "captcha" in f.url or "geo.captcha" in f.url:
            return f
    return None
```

### 触发场景

- 首次访问被 DataDome 保护的页面（HTTP 412 → CAPTCHA 页面）
- IP 被标记后的每次访问
- 登录表单提交后
- 页面间跳转时

### 滑块元素

```
.slider       - 可拖动的滑块（起点）
.sliderTarget - 目标位置（终点）
```

### 坐标计算

CAPTCHA 在 iframe 中，需要转换坐标到主页面：

```python
# 1. 获取 iframe 中滑块的相对坐标
slider_info = captcha_frame.evaluate("""() => {
    const slider = document.querySelector('.slider');
    const target = document.querySelector('.sliderTarget');
    const sr = slider.getBoundingClientRect();
    const tr = target.getBoundingClientRect();
    return {
        sx: sr.x + sr.width / 2,
        sy: sr.y + sr.height / 2,
        distance: tr.x - sr.x
    };
}""")

# 2. 获取 iframe 在主页面中的偏移
iframe_offset = page.evaluate("""() => {
    const iframe = document.querySelector('iframe[src*="captcha"]');
    if (iframe) {
        const r = iframe.getBoundingClientRect();
        return {x: r.x, y: r.y};
    }
    return {x: 0, y: 0};
}""")

# 3. 计算主页面坐标
start_x = iframe_offset["x"] + slider_info["sx"]
start_y = iframe_offset["y"] + slider_info["sy"]
end_x = start_x + slider_info["distance"]
```

### 拟人化拖动

DataDome 检测鼠标轨迹，直线匀速拖动会失败：

```python
import random, time

page.mouse.move(start_x, start_y)
time.sleep(0.2 + random.random() * 0.3)  # 停顿
page.mouse.down()
time.sleep(0.05 + random.random() * 0.1)

steps = random.randint(20, 30)
for i in range(steps + 1):
    t = i / steps
    ease = 1 - (1 - t) ** 3  # cubic ease-out（先快后慢）
    cx = start_x + (end_x - start_x) * ease
    cy = start_y + random.uniform(-2, 2)  # Y 轴随机抖动
    page.mouse.move(cx, cy)
    time.sleep(random.uniform(0.01, 0.04))

time.sleep(0.1 + random.random() * 0.15)
page.mouse.up()
```

关键特征：
- **ease-out 曲线**：起点加速，终点减速，符合人类手指运动特征
- **Y 轴抖动**：±2px 随机偏移，人不可能完美水平拖动
- **随机步数**：20-30 步，不要固定
- **随机延迟**：每步 10-40ms，总时间约 0.5-1.2s

### 失败重试

CAPTCHA 可能一次不成功，需要支持重试：

```python
# 点击刷新按钮获取新的 CAPTCHA
captcha_frame.click("#captcha__reload__button", timeout=3000)
time.sleep(2)
# 重新尝试拖动
```

## IP 被标记的处理

一旦 IP 被 DataDome 标记：
1. 所有后续请求都会触发 CAPTCHA
2. 即使真实浏览器也需要手动过验证
3. 需要等待一段时间或更换 IP

建议：
- 避免短时间内大量请求
- 使用代理池轮换 IP
- 失败时自动降速（exponential backoff）
