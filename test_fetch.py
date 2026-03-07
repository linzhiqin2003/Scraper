#!/usr/bin/env python3
"""Test crawl4ai and Jina Reader fetch on a given URL."""

import sys
import time


def test_crawl4ai(url: str):
    print("\n" + "=" * 60)
    print("  crawl4ai")
    print("=" * 60)
    t0 = time.time()
    try:
        import asyncio
        import concurrent.futures
        from crawl4ai import AsyncWebCrawler, BrowserConfig

        async def _crawl():
            cfg = BrowserConfig(headless=True, verbose=False, browser_type="webkit")
            async with AsyncWebCrawler(config=cfg) as crawler:
                return await crawler.arun(url=url)

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(asyncio.run, _crawl()).result(timeout=45)

        elapsed = time.time() - t0
        if not result.success:
            print(f"[FAIL] success=False  ({elapsed:.1f}s)")
            return

        content = result.markdown
        if hasattr(content, "fit_markdown"):
            content = content.fit_markdown or content.raw_markdown or str(content)
        content = str(content).strip()

        title = result.metadata.get("title") if result.metadata else None
        print(f"[OK]  elapsed={elapsed:.1f}s  chars={len(content)}")
        print(f"  title : {title}")
        print(f"  preview:\n{content[:5000]}")

    except Exception as e:
        elapsed = time.time() - t0
        print(f"[ERROR] {elapsed:.1f}s — {e}")


def test_jina(url: str):
    print("\n" + "=" * 60)
    print("  Jina Reader")
    print("=" * 60)
    t0 = time.time()
    try:
        import httpx
        response = httpx.get(
            f"https://r.jina.ai/{url}",
            headers={
                "Accept": "text/markdown",
                "X-Return-Format": "markdown",
                "X-Remove-Selector": "nav,footer,aside,.ads,.cookie-banner",
            },
            timeout=30.0,
            follow_redirects=True,
        )
        elapsed = time.time() - t0
        if response.status_code != 200:
            print(f"[FAIL] HTTP {response.status_code}  ({elapsed:.1f}s)")
            return

        text = response.text.strip()
        title = None
        for line in text.splitlines():
            if line.strip().startswith("# "):
                title = line.strip()[2:].strip()
                break

        print(f"[OK]  elapsed={elapsed:.1f}s  chars={len(text)}")
        print(f"  title : {title}")
        print(f"  preview:\n{text[:5000]}")

    except Exception as e:
        elapsed = time.time() - t0
        print(f"[ERROR] {elapsed:.1f}s — {e}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_fetch.py <url>")
        sys.exit(1)

    url = sys.argv[1]
    print(f"Target: {url}")

    test_crawl4ai(url)
    test_jina(url)
