---
name: web_qa
description: Open a URL, verify page health, and check for expected text
---

# Web QA

## Purpose
打开 URL，检查页面是否正常加载，验证预期文字是否存在。

## When to use
需要验证网页是否可用、是否包含预期内容时。

## Inputs
- `url`（必填）— 要检查的 URL
- `expected_text`（必填）— 预期出现在页面上的文字

## Steps
1. `read_url "{url}"` — 读取页面内容
2. `diagnose` — 检查是否有弹窗/错误
3. `assert_text "{expected_text}"` — 验证预期文字

## Output
- URL / Title / Diagnose / Result

## Failure handling
- read_url 失败 → network_error
- diagnose 发现弹窗/错误 → 根据具体 error_code 处理
- assert_text 找不到文字 → not_found

## Examples
```
browser workflow_run web_qa --var url=https://playwright.dev/ --var expected_text=Playwright
```

## Do not use for
- 搜索解决方案（用 troubleshoot_error）
- 多页面监控
