# CDP (Chrome DevTools Protocol) 提取 Cookies 经验

## 核心结论

**获取网站登录 cookies 的首选方案是通过 CDP 连接用户真实 Chrome，直接提取已有的 cookies。**

不要首选自动化登录（Patchright/Playwright），因为：
- 每次启动新浏览器实例都可能触发 CAPTCHA（DataDome、reCAPTCHA 等）
- 反 bot 系统会检测自动化行为，IP 可能被标记
- OAuth/SSO 回调地址可能变化导致登录失败
- 用户真实 Chrome 里**已经登录好了**，直接拿 cookies 就行

## 方案对比

| 方案 | 优点 | 缺点 | 推荐场景 |
|------|------|------|----------|
| **CDP 提取 cookies** | 无 CAPTCHA、不可检测、最快 | 需要用户关闭 Chrome 或用 debug 端口 | **首选**：日常 cookies 更新 |
| Patchright 自动登录 | 全自动、无需用户干预 | CAPTCHA、反 bot 检测、OAuth 变化 | 备选：cookies 过期且 Chrome 未登录 |
| 手动导入 cookies | 最可靠 | 需要用户手动操作 | 兜底：以上方案都失败时 |

## CDP 连接方式

### 方式一：Playwright connect_over_cdp（推荐）

连接到用户已打开的 Chrome（需要带 `--remote-debugging-port` 启动）：

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    # 连接到用户真实 Chrome（端口 9222）
    browser = p.chromium.connect_over_cdp("http://localhost:9222")

    # 获取已有的页面上下文
    context = browser.contexts[0]

    # 提取所有 cookies
    cookies = context.cookies()

    # 或者提取特定域的 cookies
    wsj_cookies = context.cookies(["https://www.wsj.com"])

    # 注意：不要关闭浏览器！这是用户的真实 Chrome
    # browser.close()  ← 千万不要
```

启动 Chrome 带 debug 端口：

```bash
# macOS
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/Library/Application Support/Google/Chrome"

# 如果 Chrome 已经在运行，需要先完全退出再用上面的命令启动
```

### 方式二：直接读 Chrome 的 Cookies SQLite 数据库

不需要启动 Chrome debug 模式，但 cookies 值是加密的（macOS Keychain）：

```python
import sqlite3
import subprocess
from pathlib import Path

CHROME_COOKIES_DB = Path.home() / "Library/Application Support/Google/Chrome/Default/Cookies"

def get_chrome_cookies(domain: str) -> list[dict]:
    """从 Chrome 的 SQLite 数据库读取 cookies（macOS）"""
    # Chrome 锁住数据库时需要复制一份
    import shutil, tempfile
    tmp = Path(tempfile.mktemp(suffix=".db"))
    shutil.copy2(CHROME_COOKIES_DB, tmp)

    conn = sqlite3.connect(str(tmp))
    cursor = conn.execute(
        "SELECT host_key, name, path, is_secure, expires_utc, encrypted_value "
        "FROM cookies WHERE host_key LIKE ?",
        (f"%{domain}%",)
    )

    cookies = []
    for row in cursor:
        host, name, path, secure, expires, encrypted_value = row
        # macOS: 需要从 Keychain 解密 encrypted_value
        value = decrypt_chrome_cookie(encrypted_value)
        cookies.append({
            "domain": host,
            "name": name,
            "value": value,
            "path": path,
            "secure": bool(secure),
            "expires": chrome_timestamp_to_unix(expires),
        })

    conn.close()
    tmp.unlink()
    return cookies

def decrypt_chrome_cookie(encrypted_value: bytes) -> str:
    """macOS: 使用 Keychain 解密 Chrome cookie"""
    # Chrome v10+ 格式: b'v10' + AES-CBC encrypted
    if encrypted_value[:3] == b'v10':
        # 从 Keychain 获取密钥
        password = subprocess.run(
            ["security", "find-generic-password", "-w", "-s", "Chrome Safe Storage"],
            capture_output=True, text=True
        ).stdout.strip()

        import hashlib
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

        key = hashlib.pbkdf2_hmac('sha1', password.encode(), b'saltysalt', 1003, dklen=16)
        iv = b' ' * 16
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
        decryptor = cipher.decryptor()
        decrypted = decryptor.update(encrypted_value[3:]) + decryptor.finalize()
        # 去除 PKCS7 padding
        padding_len = decrypted[-1]
        return decrypted[:-padding_len].decode('utf-8')

    return encrypted_value.decode('utf-8', errors='replace')
```

### 方式三：复制 Chrome Profile 到 MCP Chrome（api-explorer 使用）

用于 chrome-devtools MCP 工具，将用户 Chrome 的 cookies 同步到 MCP 的独立 Chrome 实例：

```bash
MCP_PROFILE="$HOME/.cache/chrome-devtools-mcp/chrome-profile/Default"
USER_PROFILE="$HOME/Library/Application Support/Google/Chrome/Default"
mkdir -p "$MCP_PROFILE"

# 同步 Cookies 和登录数据
for f in Cookies "Login Data" "Web Data"; do
  [ -f "$USER_PROFILE/$f" ] && cp "$USER_PROFILE/$f" "$MCP_PROFILE/$f"
done

# 同步 Local Storage（一些网站用 localStorage 存 token）
[ -d "$USER_PROFILE/Local Storage" ] && \
  cp -r "$USER_PROFILE/Local Storage" "$MCP_PROFILE/"
```

## 项目中的实际用法

### 提取 cookies 并保存为 Netscape 格式

```python
from playwright.sync_api import sync_playwright
from pathlib import Path

def extract_cookies_via_cdp(domain: str, output_path: Path):
    """通过 CDP 提取用户 Chrome 中的 cookies 并保存"""
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp("http://localhost:9222")
        context = browser.contexts[0]

        # 先导航到目标域名确保 cookies 完整
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(f"https://{domain}")
        page.wait_for_load_state("networkidle")

        # 提取 cookies
        all_cookies = context.cookies([f"https://{domain}"])

        # 保存为 Netscape 格式
        lines = ["# Netscape HTTP Cookie File", f"# Extracted via CDP from {domain}"]
        for c in all_cookies:
            d = c.get("domain", "")
            flag = "TRUE" if d.startswith(".") else "FALSE"
            secure = "TRUE" if c.get("secure") else "FALSE"
            expires = str(int(c.get("expires", 0)))
            lines.append(f"{d}\t{flag}\t{c.get('path','/')}\t{secure}\t{expires}\t{c['name']}\t{c['value']}")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("\n".join(lines) + "\n")

        print(f"Saved {len(all_cookies)} cookies to {output_path}")
        # 不关闭浏览器！
```

### 与 scraper import-cookies 配合

```bash
# 1. 启动 Chrome 带 debug 端口（如果还没有）
# 2. 用脚本提取 cookies
python -c "
from extract_cookies import extract_cookies_via_cdp
from pathlib import Path
extract_cookies_via_cdp('www.wsj.com', Path.home() / '.web_scraper/wsj/cookies.txt')
"

# 3. 验证
scraper wsj status
```

## 注意事项

1. **不要关闭用户的 Chrome** — `connect_over_cdp` 连接的是用户正在使用的浏览器
2. **Chrome 必须带 debug 端口启动** — 普通启动的 Chrome 无法通过 CDP 连接
3. **端口冲突** — 确保 9222 端口没有被其他程序占用
4. **Chrome 正在运行** — 如果 Chrome 已经在运行（没有 debug 端口），需要完全退出后重新启动
5. **cookies 加密** — 直接读 SQLite 数据库时，macOS 上的 cookies 是加密的，需要 Keychain 密钥解密
6. **httpOnly cookies** — CDP 方式可以获取所有 cookies（包括 httpOnly），document.cookie 方式不行
