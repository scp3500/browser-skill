#!/usr/bin/env python3
"""browser_tool.py — 封装 browser skill，返回统一格式"""

import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from skill import browser


def call(cmd, args=None):
    """统一调用入口。

    Args:
        cmd: browser 命令（goto, click_id, fill_id, observe 等）
        args: 参数字典

    Returns:
        {"ok": True, "result": {...}}
        {"ok": False, "error": {"type": "...", "message": "...", "tool": "browser", "cmd": "..."}}
    """
    try:
        resp = browser(cmd, args or {})
        if resp.get("ok"):
            return {"ok": True, "result": resp.get("result", {})}
        else:
            err = resp.get("error", {})
            return {"ok": False, "error": {
                "type": err.get("type", "ToolError"),
                "message": err.get("message", str(resp)),
                "tool": "browser",
                "cmd": cmd,
            }}
    except Exception as e:
        return {"ok": False, "error": {
            "type": type(e).__name__,
            "message": str(e),
            "tool": "browser",
            "cmd": cmd,
        }}
