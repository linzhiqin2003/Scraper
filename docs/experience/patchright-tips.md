# Patchright 使用技巧

## 什么是 Patchright

Patchright 是 Playwright 的反检测分支，主要改动：
- `navigator.webdriver` 返回 `false`（Playwright 返回 `true`）
- 不设置 Chrome automation flags
- 不显示 "Chrome is being controlled by automated test software" 横幅
- API 与 Playwright 完全兼容

## 安装

```bash
poetry add patchright
# 自带 Chromium，无需额外安装
```

## 与 Playwright 的 API 差异

### evaluate() 必须用箭头函数

Patchright 的 `page.evaluate()` 和 `frame.evaluate()` 不支持裸 return：

```python
# ❌ Playwright 可以，Patchright 不行
page.evaluate("return document.title")
# SyntaxError: Illegal return statement

# ✅ 正确写法
page.evaluate("() => document.title")
page.evaluate("() => { const el = document.querySelector('h1'); return el?.textContent; }")
page.evaluate("(arg) => arg * 2", 21)
```

这是因为 Patchright 在内部包装 evaluate 表达式的方式与 Playwright 不同。

### 其他 API 完全兼容

```python
from patchright.sync_api import sync_playwright  # 替换 playwright 导入即可

# 以下 API 与 Playwright 完全一致
page.goto(url)
page.locator(selector).click()
page.fill(selector, value)
page.wait_for_selector(selector)
ctx.cookies()
# ...
```

## 常见场景

### 处理 iframe 中的 CAPTCHA

```python
# 找到 CAPTCHA iframe
captcha_frame = None
for f in page.frames:
    if "captcha" in f.url:
        captcha_frame = f
        break

# 在 iframe 中执行 JS（注意箭头函数）
result = captcha_frame.evaluate("""() => {
    const el = document.querySelector('.slider');
    if (!el) return null;
    const rect = el.getBoundingClientRect();
    return { x: rect.x, y: rect.y, width: rect.width };
}""")

# iframe 内坐标 → 主页面坐标
iframe_rect = page.evaluate("""() => {
    const iframe = document.querySelector('iframe[src*="captcha"]');
    const r = iframe.getBoundingClientRect();
    return { x: r.x, y: r.y };
}""")

# 在主页面坐标系中操作鼠标
page.mouse.move(iframe_rect["x"] + result["x"], iframe_rect["y"] + result["y"])
page.mouse.down()
# ... 拖动 ...
page.mouse.up()
```

### headless 模式注意事项

```python
# 需要过 CAPTCHA 时，建议 headless=False
browser = p.chromium.launch(headless=False)

# 无 CAPTCHA 场景可用 headless=True
browser = p.chromium.launch(headless=True)
```

headless 模式下的限制：
- 无法看到 CAPTCHA 进行人工干预
- 某些 bot 检测会额外检查 headless 标志（Patchright 已处理大部分）

### Cookie 提取

```python
# 提取所有 cookies
all_cookies = ctx.cookies()

# 每个 cookie 的结构
# {
#   "name": "DJSESSION",
#   "value": "...",
#   "domain": ".wsj.com",
#   "path": "/",
#   "expires": 1234567890,
#   "httpOnly": True,
#   "secure": True,
#   "sameSite": "None"
# }

# 按域名过滤
wsj_cookies = [c for c in all_cookies if "wsj.com" in c.get("domain", "")]
```

### 模拟人类输入

```python
import random, time

# 逐字输入（避免一次性 fill 被检测）
input_el = page.locator("#email")
input_el.click()
time.sleep(0.2)
input_el.fill("")  # 清空
for ch in "user@example.com":
    input_el.press(ch)
    time.sleep(random.uniform(0.03, 0.08))

# 点击前的自然停顿
time.sleep(0.5 + random.random() * 0.3)
page.locator("#submit").click()
```

## 性能考虑

- Patchright 启动时间与 Playwright 相同
- 每次 `sync_playwright()` 上下文管理器会启动/关闭浏览器进程
- 如果需要多次登录，考虑复用浏览器实例
- Cookie 持久化后，后续请求应使用 httpx 而非浏览器（更快）
