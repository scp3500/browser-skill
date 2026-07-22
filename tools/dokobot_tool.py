#!/usr/bin/env python3
"""dokobot_tool.py — 封装 dokobot 命令，返回统一格式"""

import subprocess
import json
import os
import shutil


# 查找 dokobot 可执行文件路径
_DOKOBOT = shutil.which("dokobot") or shutil.which("dokobot.cmd") or ""
if not _DOKOBOT:
    npm_prefix = os.environ.get("APPDATA", "") + "/npm"
    for candidate in [npm_prefix + "/dokobot.cmd", npm_prefix + "/dokobot"]:
        if os.path.exists(candidate):
            _DOKOBOT = candidate
            break


def _run(args, timeout=30):
    cmd = [_DOKOBOT] + args if _DOKOBOT else ["dokobot"] + args
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, encoding='utf-8', creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess,'CREATE_NO_WINDOW') else 0)
        if r.returncode != 0:
            return {"ok": False, "error": {"type": "SubprocessError", "message": f"exit={r.returncode} {r.stderr[:200]}", "tool": "dokobot"}}
        return {"ok": True, "result": {"text": r.stdout[:8000]}}
    except FileNotFoundError:
        return {"ok": False, "error": {"type": "NotFound", "message": "dokobot not found in PATH", "tool": "dokobot"}}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": {"type": "TimeoutError", "message": "dokobot timed out", "tool": "dokobot"}}


def call(cmd, args=None):
    """统一调用入口。"""
    if args is None:
        args = {}

    try:
        if cmd == "search":
            query = args.get("query", "")
            if not query:
                return {"ok": False, "error": {"type": "ArgError", "message": "query required", "tool": "dokobot", "cmd": cmd}}
            return _run(["search", query])

        elif cmd == "read":
            url = args.get("url", "")
            if not url:
                return {"ok": False, "error": {"type": "ArgError", "message": "url required", "tool": "dokobot", "cmd": cmd}}
            return _run(["read", "--local", url])

        elif cmd == "download_images":
            url = args.get("url", "")
            if not url:
                return {"ok": False, "error": {"type": "ArgError", "message": "url required", "tool": "dokobot", "cmd": cmd}}
            return _run(["download", "images", "--local", url])

        else:
            return {"ok": False, "error": {"type": "UnknownCmd", "message": f"unknown: {cmd}", "tool": "dokobot", "cmd": cmd}}

    except Exception as e:
        return {"ok": False, "error": {"type": type(e).__name__, "message": str(e), "tool": "dokobot", "cmd": cmd}}
