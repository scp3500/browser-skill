# browser-skill

Pi Coding Agent 的 **Browser Skill**：用 Playwright 做本地浏览器自动化，配合 dokobot 读网页、OpenVL 看图。

**版本：2.5.1**

> **定位**：这是 Pi skill 后端，不是通用 Selenium/Playwright 框架。  
> **状态**：个人维护，Issue 不保证回复。  
> **密钥**：只通过环境变量引用（如 `OPENVL_API_KEY` / `DOKOBOT_TOKEN`），仓库内无明文凭据。

## 功能概览

- 打开网页、点击、填表、截图、观察页面
- `read_url`：公网优先 dokobot，失败 fallback 到 browser
- 诊断弹窗/空白页，安全关闭弹窗；`screenshot_ask` 视觉诊断
- 预设工作流：`research_official` / `troubleshoot_error` / `pricing_compare` / `web_qa`
- 配置系统 + Web UI 控制面板（仅 `127.0.0.1:8767`）
- 统一五行 CLI contract + trace 脱敏

## 依赖

- Python 3.10+
- 本机可选：
  - [dokobot](https://github.com/scp3500/dokobot-mcp-server)（读公网，`127.0.0.1:2024`）
  - [openvl](https://github.com/scp3500/openvl)（视觉诊断）

## 安装

### Windows

```powershell
git clone https://github.com/scp3500/browser-skill.git
cd browser-skill
powershell -ExecutionPolicy Bypass -File install.ps1
```

### Git Bash / Linux / macOS

```bash
git clone https://github.com/scp3500/browser-skill.git
cd browser-skill
bash install.sh
```

手动：

```bash
pip install -r requirements.txt
python -m playwright install chromium
# 复制或 clone 到 ~/.pi/agent/skills/browser
# CLI: python browser_daemon.py … 或 bin/browser
```

确保 `~/bin`（或你放 shim 的目录）在 `PATH` 里。

## 快速开始

```bash
browser status
browser read_url https://example.com
browser search_read "playwright docs" --chars 2000
browser workflow_list
browser config_web          # 默认 http://127.0.0.1:8767
browser config_show
```

端口约定：

| 服务 | 默认端口 |
|------|----------|
| browser daemon | `8765` |
| config Web UI | `8767` |
| openvl endpoint（独立项目） | `8766` |

## 配置

- 用户配置：`%LOCALAPPDATA%\Pi\browser\config.yaml`（Windows）或 `~/.config/pi/browser/config.yaml`
- 内置 defaults：`config/defaults.yaml`
- 详细说明：`SKILL.md`、`CONFIG.md`、`WEB_UI.md`、`docs/ARCHITECTURE.md`

密钥只用环境变量引用，不要写明文。

## 测试

```bash
pytest tests/ -q
```

离线单测为主，不依赖真实外网。

## 仓库结构（简）

```
browser_daemon.py      # CLI + daemon 入口
browser_server.py      # Playwright 常驻服务
browser_workflows.py   # 复合工作流（单轨）
tools/                 # config / contract / web UI / sanitize
workflow_specs/        # YAML 工作流
config/presets/        # 场景预设
bin/browser            # 跨平台 CLI wrapper
install.ps1 / install.sh
docs/ARCHITECTURE.md
tests/
```

## 已知限制

- 强依赖本机浏览器 profile / 可选 dokobot·openvl，不是无头通用爬虫库
- 高风险按钮（Pay/Delete 等）会被拒绝点击
- 不绕过验证码 / bot 检测
- Web UI 仅绑定 `127.0.0.1`，无远程服务

## License

MIT — 见 `LICENSE`。
