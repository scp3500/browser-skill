#!/usr/bin/env python3
"""
browser_agent.py — 浏览器 agent 工具（Pi 决策版）

Pi 的接口：
  execute(tool, cmd, args) → {ok, result, observation, error}
  format_observation(result) → str
"""

import sys
import os

# Windows 终端编码修复
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import json

sys.path.insert(0, os.path.dirname(__file__))
from tools.browser_tool import call as bt
from tools.dokobot_tool import call as dt
from tools.openvl_tool import call as vt

TOOLS = {"browser": bt, "dokobot": dt, "openvl": vt}

# 自动 observe 的命令列表（导航/交互类）
AUTO_OBSERVE_CMDS = {
    "goto", "click", "click_id", "click_text",
    "fill", "fill_id", "fill_label",
    "press", "scroll", "select",
}

DEFAULT_OBSERVE_ARGS = {
    "text": True,
    "snapshot": True,
    "screenshot": False,
    "max_text_chars": 6000,
    "max_snapshot_items": 80,
}

# 步骤计数器 & trace 日志
_step_counter = 0
_trace = []


def _log_trace(entry):
    _trace.append(entry)
    # 只保留最近 100 步
    if len(_trace) > 100:
        _trace[:] = _trace[-100:]


def get_trace():
    """返回当前 trace 日志"""
    return list(_trace)


def reset_trace():
    """清空 trace"""
    global _step_counter, _trace
    _step_counter = 0
    _trace = []


def execute(tool, cmd, args=None):
    """执行动作，返回 {ok, result, observation, error}。"""
    if tool not in TOOLS:
        return {"ok": False, "error": {"type": "UnknownTool", "message": f"tool '{tool}' not available"}}

    result = TOOLS[tool](cmd, args or {})

    # 导航/点击后自动等稳定
    if tool == "browser" and cmd in ("goto", "click", "click_id", "click_text", "press"):
        TOOLS["browser"]("wait", {"ms": 1500})

    # 添加 observation 文本字段（给 Pi 看简短摘要）
    obs = _summarize(result, tool, cmd)
    result["observation"] = obs
    return result


def _summarize(result, tool, cmd):
    """从工具返回中生成简短 observation 文本。"""
    if not result.get("ok"):
        err = result.get("error", {})
        return f"[{tool}.{cmd}] FAIL: {err.get('type')}: {err.get('message', '')[:100]}"

    r = result.get("result", {})
    if tool == "browser":
        if cmd == "observe":
            url = r.get("url", "")
            title = r.get("title", "")
            visible = sum(1 for x in r.get("snapshot", []) if x.get("visible"))
            text_len = len(r.get("text", ""))
            return f"[browser.observe] {title} | {visible} visible elements | {text_len} chars text | {url}"
        elif cmd in ("goto", "click", "click_id", "click_text"):
            return f"[browser.{cmd}] OK | url: {r.get('url', '')[:80]}"
        elif cmd in ("fill", "fill_id"):
            return f"[browser.{cmd}] OK"
        elif cmd == "press":
            return f"[browser.press] OK"
        elif cmd == "screenshot":
            return f"[browser.screenshot] saved: {r.get('path', r.get('base64','')[:20]+'...')}"
        elif cmd == "read_url_new_page":
            return f"[browser.read_url_new_page] OK | url: {r.get('url', '')[:80]} | text: {len(r.get('text',''))} chars"
        elif cmd == "extract_text":
            return f"[browser.extract_text] {len(r.get('text',''))} chars"
        elif cmd == "scroll":
            return f"[browser.scroll] OK"
        elif cmd == "close":
            return f"[browser.close] browser closed"
        return f"[browser.{cmd}] OK"
    elif tool == "dokobot":
        text = r.get("text", "")
        return f"[dokobot.{cmd}] {len(text)} chars returned"
    elif tool == "openvl":
        desc = r.get("description", "")
        return f"[openvl.{cmd}] {desc[:150]}"
    return f"[{tool}.{cmd}] OK"


def format_observation(result, title="Current Page"):
    """将 observe 结果格式化为可读文本。"""
    if not result.get("ok"):
        return f"[Error] {result.get('error', {}).get('message', 'unknown')}"

    r = result.get("result", {})
    url = r.get("url", "")
    title_text = r.get("title", "")
    text = r.get("text", "")
    snap = r.get("snapshot", [])

    lines = [f"=== {title} ==="]
    lines.append(f"URL: {url}")
    lines.append(f"Title: {title_text}")
    lines.append("")

    visible = [x for x in snap if x.get("visible")]
    if visible:
        lines.append(f"--- Interactive elements ({len(visible)}) ---")
        for el in visible[:50]:
            txt = el.get("placeholder", "") or el.get("text", "") or ""
            role = el.get("role", el["tag"])
            lines.append(f"  [{el['id']}] <{role}> {txt[:60]}")
        lines.append("")

    if text:
        lines.append(f"--- Page text ({len(text)} chars) ---")
        lines.append(text[:2000])
        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: python browser_agent.py <tool> <cmd> [args_json]")
        sys.exit(1)
    tool, cmd = sys.argv[1], sys.argv[2]
    args = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
    result = execute(tool, cmd, args)
    print(json.dumps(result, ensure_ascii=False, indent=2))


# ===== Pi 交互接口 =====


def step(tool, cmd, args=None):
    """Pi 交互动作：执行 + 自动 observe + 记录 trace。

    用法：
      result = step("browser", "goto", {"url": "https://www.wikipedia.org"})
      result = step("browser", "observe")
      result = step("browser", "click_id", {"id": 5})

    返回：
      {
        "ok": bool,
        "step": int,
        "action": {"tool": ..., "cmd": ..., "args": ...},
        "result": ...,
        "post_observe": ...,
        "observation": "摘要文本",
      }
    """
    global _step_counter
    _step_counter += 1
    args = args or {}
    action = {"tool": tool, "cmd": cmd, "args": args}

    action_result = execute(tool, cmd, args)

    post_observe = None
    if tool == "browser" and cmd in AUTO_OBSERVE_CMDS and action_result.get("ok"):
        post_observe = execute("browser", "observe", DEFAULT_OBSERVE_ARGS)

    obs = [f"Step {_step_counter}: {tool}.{cmd} -> {'OK' if action_result.get('ok') else 'FAILED'}"]
    if post_observe and post_observe.get("ok"):
        po = post_observe.get("result", {})
        obs.append(f"  URL: {po.get('url','')}")
        obs.append(f"  Title: {po.get('title','')}")
        obs.append(f"  Elements: {sum(1 for x in po.get('snapshot',[]) if x.get('visible'))} visible")
        obs.append(f"  {post_observe.get('observation','')}")
    elif action_result.get("observation"):
        obs.append(f"  {action_result['observation']}")

    _log_trace({"step": _step_counter, "action": action, "ok": action_result.get("ok", False)})

    return {
        "ok": action_result.get("ok", False),
        "step": _step_counter,
        "action": action,
        "result": action_result.get("result"),
        "error": action_result.get("error"),
        "post_observe": post_observe.get("result") if post_observe else None,
        "observation": "\n".join(obs),
    }
