# OpenCode 用量查阅（本机配方）

> 跨 session 备忘：给 AI / 自己快速复用。完整上下文见  
> `E:\pi_agent\memory\projects\2026-07-23-browser-skill.md`

## 前提

- 已用**可见窗口**登录过一次，登录态在：

```text
%LOCALAPPDATA%\Pi\browser\opencode-profile
```

- 无头即可读；只有掉登录时再 `BROWSER_HEADLESS=0`。

## 命令

```bash
export BROWSER_HEADLESS=1
export BROWSER_PROFILE_DIR="C:/Users/33795/AppData/Local/Pi/browser/opencode-profile"

# 换环境变量后
browser kill

# Go 配额百分比
browser goto "https://opencode.ai/workspace/wrk_01KRZ1QRGZGK4QDCJG4QT4AVNT/go"
browser read 5000

# 使用历史列表（含 Go ($x)，用于加总「今天花了多少」）
browser goto "https://opencode.ai/workspace/wrk_01KRZ1QRGZGK4QDCJG4QT4AVNT/usage"
browser read 15000
```

## 页面区别

| URL 后缀 | 看什么 |
|----------|--------|
| `/go` | 滚动/周/月额度 **%** |
| `/usage` | 明细表：日期、模型、token、**美元成本** |

柱状图：`browser read` 抽不出可靠数字；需要时再 `browser screenshot` + openvl。

## 与 dokobot / Edge

- dokobot：公开页可以，**不一定**有此 workspace 登录态。  
- 日常 Edge：给人看可以；**browser 默认不控制 Edge**。  
- 本配方用 skill 自己的 profile，与 Edge 分离。
