#!/usr/bin/env python3
"""test_browser_skill.py — 回归测试

测试目标：Wikipedia 搜索 Playwright → 进入结果页 → 提取标题和正文摘录 → 截图
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
from skill import browser


def check(step, resp):
    if not resp.get("ok"):
        err = resp.get("error", {})
        print(f"  FAIL: {step} — {err.get('type')}: {err.get('message')[:80]}")
        return False
    print(f"  OK: {step}")
    return True


def test():
    print("=== 1. goto Wikipedia ===")
    r = browser("goto", {"url": "https://en.wikipedia.org/wiki/Playwright_(software)"})
    if not check("goto", r):
        return
    print(f"     title: {r['result'].get('title', '')[:80]}")
    print(f"     url:   {r['result'].get('url', '')}")

    print("\n=== 2. observe (screenshot + snapshot + text) ===")
    os.makedirs("/tmp", exist_ok=True)
    r = browser("observe", {
        "screenshot": True,
        "screenshot_path": "/tmp/browser_test_wiki.png",
        "snapshot": True,
        "max_items": 30,
        "text": True,
    })
    if not check("observe", r):
        return
    res = r["result"]
    print(f"     url:   {res.get('url', '')[:60]}")
    print(f"     title: {res.get('title', '')[:60]}")
    print(f"     text:  {len(res.get('text', ''))} chars")
    print(f"     snapshot: {len(res.get('snapshot', []))} items")

    print("\n=== 3. extract_text ===")
    r = browser("extract_text", {"selector": "#mw-content-text"})
    if check("extract_text", r):
        text = r["result"].get("text", "")[:300]
        print(f"     First para: {text[:120]}...")

    print("\n=== 4. snapshot interactive elements ===")
    r = browser("snapshot", {"max_items": 20})
    if check("snapshot", r):
        items = r["result"].get("items", [])
        print(f"     {len(items)} items found")
        for item in items[:8]:
            bbox = item.get("bbox")
            pos = f" @{bbox['x']:.0f},{bbox['y']:.0f}" if bbox else ""
            print(f"       <{item['tag']}> {item.get('text','')[:50]}{pos}")

    print("\n=== 5. get_url + get_title ===")
    r = browser("get_url")
    url = r.get("result", {}).get("url", "")
    print(f"     URL: {url}")
    r = browser("get_title")
    title = r.get("result", {}).get("title", "")
    print(f"     Title: {title[:80]}")

    print("\n=== 6. scroll + wait ===")
    browser("scroll", {"y": 500})
    browser("wait", {"ms": 500})
    print("     scrolled down")

    print("\n=== 7. close ===")
    r = browser("close")
    check("close", r)

    print("\n===== ALL TESTS PASSED =====")


if __name__ == "__main__":
    # 清理旧截图
    for f in ["/tmp/browser_test_wiki.png", "/tmp/browser.*.png"]:
        try:
            os.remove(f)
        except:
            pass
    test()
