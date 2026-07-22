---
name: pricing_compare
description: Search for pricing information for multiple products
---

# Pricing Compare

## Purpose
搜索多个产品的定价信息。

## When to use
需要对比多个产品的定价时。

## Inputs
- `products`（必填）— JSON 数组，例如 ["Cursor", "Windsurf"]
- 或逗号分隔字符串：`products=Cursor,Windsurf`

## Steps
对每个 product，执行 `search_read "{product} pricing official"`

## Output
- Pricing sources 列表（Product / Title / URL / Source type / Snippet）

## Failure handling
- 单个 product 搜索失败不影响其他 product
- 全部失败时 Error code=no_search_results

## Examples
```
browser workflow_run pricing_compare --input products.json
```

## Do not use for
- 实时价格爬取
- 官方文档搜索（用 research_official）
