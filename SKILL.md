---
name: browser
description: 浏览器自动化工具集：打开网页、搜索、读取、诊断、安全点击、预设工作流、配置面板、并行读取
version: 2.5.1
---

# Browser Skill

> Daemon: 127.0.0.1:8765 | Web UI: 127.0.0.1:8767（默认）
> 阅读优先 dokobot → fallback browser → 视觉诊断 openvl

## 1. Basic Browser Actions
| Command | Description |
|---------|-------------|
| `goto <url>` | 打开 URL |
| `click_id <id>` | 按编号点击 |
| `click_text <text>` | 按文本点击 |
| `fill <id> <text>` | 填写输入框 |
| `press [key]` | 按键（默认 Enter） |
| `screenshot [path]` | 截图 |
| `observe` | 观察当前页面 |

## 2. Reading and Search
| Command | Description |
|---------|-------------|
| `read_url <url> [--provider auto\|browser\|dokobot] [--chars N]` | 读取 URL（支持 fallback）|
| `read_urls_parallel --input urls.json [--provider browser] [--max-concurrency N] [--timeout-ms N] [--chars N]` | 并行读取多个 URL（独立 page，不冲突）|
| `search_candidates --query <q> --allowed-domain <d> [--limit N] [--provider dokobot]` | 搜索候选来源，返回 URL/title/source_type |
| `search_official --query <q> --allowed-domain <d> [--limit N] [--provider dokobot]` | 搜索官方文档（同 search_candidates）|
| `doko_read <url> [chars]` | 用 dokobot 读取 |
| `search_read <query> --result N --chars N [--fallback]` | 搜索并读取结果 |
| `read [chars]` | 读取当前页正文 |

## 3. Diagnosis and Recovery
| Command | Description |
|---------|-------------|
| `diagnose` | 截图诊断，检查弹窗/验证码/错误 |
| `diagnose_and_recover` | 诊断 → 发现 popup → 关闭 → 再诊断 |
| `close_popups` | 保守关闭弹窗（只点 Close/No thanks 等，跳过 Pay/Delete）|

自动恢复：失败 URL 后 daemon 自动重置 page，无需 `browser kill`。

## 4. Safe Interaction
| Command | Description |
|---------|-------------|
| `wait_text <text> [--timeout N]` | 等待文字出现 |
| `assert_text <text>` | 检查当前页是否有文字 |
| `click_expect <text> --expect <expected> [--timeout N]` | 点击后等待预期文字（拒绝高风险按钮）|

## 5. Config & Control Panel
| Command | Description |
|---------|-------------|
| `config_path` | 显示用户配置路径 |
| `config_show [--json]` | 显示有效配置（YAML/JSON）|
| `config_validate` | 校验配置合法性 |
| `config_set key=value` | 设置配置项 |
| `preset_list` | 列出可用 presets |
| `preset_show <name>` | 显示 preset（脱敏）|
| `preset_use <name> [--dry-run\|--write]` | 应用 preset |
| `config_web [--port N]` | 启动 Web UI 控制面板（默认 8767，daemon 用 8765）|
| `config_web_status` | 查询 Web UI 状态 |
| `config_web_stop` | 停止 Web UI |

## 6. Trace
| Command | Description |
|---------|-------------|
| `trace_list` | 最近 20 个 trace |
| `trace_show <run_id>` | 查看 trace 详情（含 workflow steps、Provider used、Child trace）|

## 7. Workflows
| Command | Description |
|---------|-------------|
| `workflow_list` | 列出可用工作流 |
| `workflow_show <name>` | 查看工作流说明 |
| `workflow_run <name> [--input file.json] [--var k=v]` | 执行工作流 |
| `workflow_validate <name>` | 校验 workflow spec |

## 8. Built-in Workflows

| Workflow | Purpose | Inputs |
|----------|---------|--------|
| `research_official` | 搜索官方文档 | topic |
| `troubleshoot_error` | 搜索报错解决方案 | error |
| `pricing_compare` | 搜索多个产品定价 | products (json list) |
| `web_qa` | 检查页面是否正确加载 | url, expected_text |

## 9. Provider Architecture（三层）

| Layer | Primary | Fallback | Use case |
|-------|---------|----------|----------|
| **Reading** | dokobot | browser | 公网网页、文档、博客、长文批量读取 |
| **Interaction** | browser | — | localhost/click/fill/screenshot/UI 验收 |
| **Vision** | OpenVL | — | 空白诊断、OCR、截图理解 |

- `read_url` 默认 auto：公网 → dokobot，dokobot 失败 → browser fallback
- `read_urls_parallel` 使用独立 browser page，不干扰主页面导航
- config_web UI 必须用 browser 读取（localhost）
- OpenVL 不作默认阅读工具

## 10. Contract Rules

所有 public CLI 命令输出五行 header：

```
Status: ok|error|uncertain
Error code: ok|...
Provider used: browser|dokobot|openvl|mixed|none
Fallback used: yes|no
Trace: YYYYMMDD_HHMMSS_mmm_<command>
```

- `status=ok` 时 `error_code` 必须为 `ok`
- `status≠ok` 时 `error_code` 不能为 `ok`
- trace_id 只取命令名，不含 URL/参数
- 所有输出经过 `sanitize`，不泄露 api_key/token

## 11. Safety Rules

- Do NOT bypass captcha or bot detection
- Do NOT click high-risk buttons (Pay/Delete/Confirm/Transfer/Submit order)
- `click_expect` rejects risky actions with error_code=risky_action
- `close_popups` only clicks Close/No thanks/Accept(in popup) — never Pay/Delete
- OpenVL is a verifier, not an actuator
- Prefer `workflow_run` over manual command composition when a matching workflow exists
- When workflow fails, check error_code and trace_show for details
