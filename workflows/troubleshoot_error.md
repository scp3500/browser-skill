---
name: troubleshoot_error
description: Search for error solutions across official docs, GitHub, and StackOverflow
---

# Troubleshoot Error

## Purpose
搜索错误信息的解决方案。

## When to use
遇到报错信息需要查官方文档、GitHub Issues 或 StackOverflow 时。

## Inputs
- `error`（必填）— 错误信息，例如 "playwright strict mode violation"

## Steps
1. `search_read "{error} official documentation"`
2. `search_read "{error} github issue"`
3. `search_read "{error} stackoverflow"`

## Output
- Findings 列表（Title / URL / Source type / Snippet）

## Failure handling
- 某个来源搜索失败不影响其他来源
- 全部失败时 Error code=no_search_results

## Examples
```
browser workflow_run troubleshoot_error --var "error=playwright strict mode violation"
```

## Do not use for
- 搜索官方文档（用 research_official）
- 需要验证部署状态（用 web_qa）
