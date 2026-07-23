# Browser Skill — Web UI (v2.7.0)

## 启动

```bash
browser config_web --port 8767
```

输出五行 header + URL（含 token）：
```
Status: ok
Error code: ok
Provider used: none
Fallback used: no
Trace: 20260522_135500_123_config_web

Browser Skill Control Panel
URL: http://127.0.0.1:8767/?token=<random_token>
```

端口约定：daemon 使用 8765，config_web 默认使用 8767（避开 openvl 默认 8766）。如果端口被占用，config_web 返回 `Status: error / Error code: invalid_config`。

## 安全

- **只监听 127.0.0.1** — 不允许 `--host 0.0.0.0`
- **随机 token** — 每次启动生成新 token，URL 中携带
- **Header token** 也支持：`X-Token: <token>`
- **明文 secret** 禁止 — api_key/token/password/secret/bearer/authorization 不能明文出现在 config 编辑
- **Trace sanitize** — 所有 API 返回经过 sanitize
- **不开放远程服务**

## 页面

| 页面 | URL | 功能 |
|------|-----|------|
| Dashboard | `/` | 版本、provider、workflow/trace 统计 |
| Config | `/config` | 查看/编辑/验证配置 |
| Presets | `/presets` | 查看和应用 presets |
| Workflows | `/workflows` | 查看和验证 workflow spec |
| Traces | `/traces` | 查看 trace 和 workflow steps |
| Diagnostics | `/diagnostics` | 环境变量、daemon 状态 |

## API

所有 API 返回 JSON，基于 `render_json(BrowserResult)`：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| GET | `/api/config` | 有效配置（脱敏） |
| POST | `/api/config/validate` | 校验 YAML 配置 |
| POST | `/api/config/save` | 保存配置 |
| GET | `/api/presets` | Preset 列表 |
| GET | `/api/presets/<name>` | Preset 详情 |
| POST | `/api/presets/<name>/apply` | 应用 preset |
| GET | `/api/workflows` | Workflow 列表 |
| GET | `/api/workflows/<name>` | Workflow 详情 |
| POST | `/api/workflows/<name>/validate` | 校验 workflow spec |
| GET | `/api/traces` | Trace 列表 |
| GET | `/api/traces/<run_id>` | Trace 详情 |
| GET | `/api/diagnostics` | 环境诊断 |

## Secret 规则

- `config_show`、API、Web UI 不显示真实 api_key/token
- 只显示 `configured` / `missing`
- `config_validate` 拒绝明文 secret
- `sanitize` 覆盖所有 trace/API 输出

## 自审 Workflows

三个内置 workflow 用于自动检查 Web UI：

- `config_ui_smoke` — 检查 Dashboard/Config/Presets/Workflows/Traces/Diagnostics 页面可访问
- `config_ui_security_check` — 检查无 sk-/Bearer/明文 api_key 泄露
- `config_ui_trace_viewer_check` — 检查 Traces 页面和 API

```bash
browser workflow_run config_ui_smoke --var url=http://127.0.0.1:8767/?token=<token>
browser workflow_run config_ui_security_check --var url=http://127.0.0.1:8767/?token=<token>
browser workflow_run config_ui_trace_viewer_check --var url=http://127.0.0.1:8767/?token=<token>
```

## 已知限制

- 无拖拽 workflow designer
- 无 benchmark
- 无 LLM judge
- 无远程开放服务
- 仅支持 127.0.0.1
- 无 HTTPS（localhost only，不需要）
- 无持久化 session（纯 stateless token）

## v2.6 计划

- benchmark dashboard
- workflow 执行历史图表
- 可配置 alert
