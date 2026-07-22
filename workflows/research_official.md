---
name: research_official
description: Search for official documentation or website of a topic
---

# Research Official

## Purpose
找到指定主题的官方文档或官网。

## When to use
需要确认某技术/产品的官方资料时。

## Inputs
- `topic`（必填）— 要搜索的主题，例如 "Playwright"

## Steps
1. `search_read "{topic} official docs"` — 搜索官方文档
2. `search_read "{topic} official website"` — 搜索官网

## Output
- Sources 列表（Title / URL / Source type / Snippet）
- 如果没有找到官方来源，Status=uncertain，Error code=unverified_source

## Failure handling
- `unverified_source`：搜索结果可能是第三方教程，需人工确认
- 其他：参考各步骤的 error_code

## Examples
```
browser workflow_run research_official --var topic=Playwright
```

## Do not use for
- 需要实时/最新价格信息（用 pricing_compare）
- 需要解决具体报错（用 troubleshoot_error）
