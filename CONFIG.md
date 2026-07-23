# Browser Skill — Config System (v2.7.0)

## 配置路径

| 平台 | 用户配置 | Presets |
|------|---------|---------|
| Windows | `%LOCALAPPDATA%\Pi\browser\config.yaml` | `%LOCALAPPDATA%\Pi\browser\presets\` |
| Pi/Linux | `~/.pi/browser/config.yaml` | `~/.pi/browser/presets/` |

内置 presets 目录：`<skill>/config/presets/`

## 优先级

```
built-in defaults  (最底层)
< config/defaults.yaml
< 用户 config.yaml
< 环境变量
< CLI flags          (最高优先级)
```

### 环境变量

| 变量 | 对应配置 |
|------|---------|
| `BROWSER_PAGE_LOAD_MS` | `timeouts.page_load_ms` |
| `BROWSER_ACTION_MS` | `timeouts.action_ms` |
| `BROWSER_READ_MS` | `timeouts.read_ms` |
| `OPENVL_TIMEOUT_MS` | `timeouts.openvl_ms` |
| `BROWSER_WORKFLOW_STEP_MS` | `timeouts.workflow_step_ms` |

## Schema

```yaml
providers:
  default: auto            # auto | browser | dokobot | openvl
  browser:
    enabled: true
  dokobot:
    enabled: true
    base_url: "http://127.0.0.1:2024"
    token_env: DOKOBOT_TOKEN
  openvl:
    enabled: false
    endpoint: "http://127.0.0.1:8766"
    api_key_env: OPENVL_API_KEY
    default_prompt: true

timeouts:
  page_load_ms: 30000
  action_ms: 10000
  read_ms: 30000
  openvl_ms: 60000
  workflow_step_ms: 60000

trace:
  enabled: true
  retention_days: 7
  sanitize: true

screenshots:
  enabled: true
  retention_count: 50

workflows:
  enabled: true
  directory: workflow_specs
  allowed_actions:
    - read_url
    - search_read
    - diagnose
    - diagnose_and_recover
    - wait_text
    - assert_text
    - click_expect
    - screenshot_ask

presets:
  default: local
```

## CLI 命令

### config_path
显示用户配置路径。
```
$ browser config_path
C:\Users\<user>\AppData\Local\Pi\browser\config.yaml
```

### config_show
显示有效配置（已合并 defaults + user + env）。
```
$ browser config_show
providers:
  default: auto
  browser:
    enabled: true
  dokobot:
    enabled: true
...

$ browser config_show --json
{"providers": {"default": "auto", ...}}
```

### config_validate
校验配置合法性。
```
$ browser config_validate
Status: ok
Error code: ok
Provider used: none
Fallback used: no
Trace: no

Config is valid
```
非法时：
```
Status: error
Error code: invalid_config
Provider used: none
Fallback used: no
Trace: no

Message: providers.default 必须是 auto/browser/dokobot/openvl
```

### config_set
设置单个配置项。
```
browser config_set providers.default=dokobot
browser config_set timeouts.page_load_ms=50000
```

### preset_list
列出可用 presets。
```
$ browser preset_list
  browser-only
  ci
  dokobot-first
  local
  openvl
```

### preset_show
显示 preset 内容（脱敏）。
```
$ browser preset_show browser-only
providers:
  default: browser
  dokobot:
    enabled: false
  openvl:
    enabled: false
```

### preset_use
应用 preset 到用户配置。
```
$ browser preset_use browser-only --dry-run
Would write:
providers:
  default: browser
  dokobot:
    enabled: false
  openvl:
    enabled: false
To: C:\Users\<user>\AppData\Local\Pi\browser\config.yaml

$ browser preset_use browser-only --write
preset applied: browser-only
To: C:\Users\<user>\AppData\Local\Pi\browser\config.yaml
```

### workflow_validate
校验 workflow spec 合法性。
```
$ browser workflow_validate web_qa
Status: ok
Error code: ok
Provider used: none
Fallback used: no
Trace: no

Workflow spec is valid

$ browser workflow_validate nonexistent
Status: error
Error code: not_found
Provider used: none
Fallback used: no

workflow not found: nonexistent
```

## 密钥规则

不要把 API key/token 明文写入配置。只允许通过环境变量引用：

```yaml
api_key_env: OPENVL_API_KEY
token_env: DOKOBOT_TOKEN
```

`config_show` 显示：
```
OPENVL_API_KEY: configured
OPENVL_API_KEY: missing
```

不显示真实值。`sanitize` 覆盖配置快照写入 trace。

## Disabled provider

配置禁用 provider 后，显式使用返回 `invalid_config`：
```
browser read_url https://example.com --provider dokobot
Status: error
Error code: invalid_config
Message: provider disabled: dokobot
```

`auto` 模式下跳过 disabled provider。

## Trace 集成

trace summary 包含脱敏配置快照：
```json
"config": {
  "providers": {
    "default": "auto",
    "browser_enabled": true,
    "dokobot_enabled": true,
    "openvl_enabled": false
  },
  "timeouts": {
    "page_load_ms": 30000,
    "action_ms": 10000,
    "openvl_ms": 60000
  }
}
```

不含密钥。

## Workflow Validate 校验内容

- workflow 是否存在
- YAML 是否可解析
- `name/inputs/steps/output` 是否合法
- required inputs 是否声明
- action 是否在 allowed_actions
- 变量引用是否合法
- foreach 格式是否正确
- on_error 只能是 continue/stop
- 拒绝 shell/python/import/未知 action

## 后续计划

Web UI 已提供基础控制面板；workflow designer / benchmark 仍为后续项。
