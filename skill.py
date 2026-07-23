#!/usr/bin/env python3
"""
browser_skill.py — Pi 浏览器 skill

统一入口：
  browser(cmd: str, args: dict = {}) -> dict

返回格式：
  {"ok": True, "result": {...}}
  {"ok": False, "error": {"type": "...", "message": "...", "cmd": "..."}}

自动管理 browser_server 生命周期：
  - 首次调用启动常驻进程
  - 后续复用
  - 崩溃自动重启一次
  - 超时 kill + restart
  - close 清理
"""

import subprocess
import json
import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
import os
import atexit
import time
import threading

_SERVER_SCRIPT = os.path.join(os.path.dirname(__file__), "browser_server.py")
_proc = None
_lock = threading.Lock()
_req_id = 0
_debug = os.environ.get("BROWSER_DEBUG", "").lower() in ("1", "true", "yes")

# 存储线程读取的响应
_read_buf = []
_read_thread = None
_read_stop = False


def _log(*args):
    if _debug:
        print("[browser_skill]", *args, file=sys.stderr, flush=True)


def _reader():
    """后台线程：持续从 stdout 读行"""
    global _read_buf
    while not _read_stop:
        if _proc and _proc.stdout:
            try:
                line = _proc.stdout.readline()
                if line:
                    _read_buf.append(line.strip())
            except (OSError, ValueError):
                break
        else:
            time.sleep(0.1)


def _start():
    global _proc, _read_thread, _read_stop, _read_buf
    if _proc and _proc.poll() is None:
        return True

    _log("starting browser_server...")
    _proc = subprocess.Popen(
        [sys.executable, _SERVER_SCRIPT],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=None,
        text=True,
        encoding="utf-8",
        bufsize=1,
        env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
    )
    # 等待就绪
    _read_buf = []
    _read_stop = False
    _read_thread = threading.Thread(target=_reader, daemon=True)
    _read_thread.start()

    deadline = time.time() + 5
    while time.time() < deadline:
        for line in _read_buf:
            if "ready" in line:
                _read_buf.remove(line)
                return True
        if _proc.poll() is not None:
            _proc = None
            return False
        time.sleep(0.1)

    # 超时但进程还在，就当能用
    if _proc and _proc.poll() is None:
        return True
    _proc = None
    return False


def _restart():
    _log("restarting...")
    _stop()
    time.sleep(0.5)
    return _start()


def _stop():
    global _proc, _read_stop
    if _proc:
        try:
            _proc.stdin.write(json.dumps({"id": "stop", "cmd": "close", "args": {}}) + "\n")
            _proc.stdin.flush()
            _proc.wait(timeout=3)
        except Exception:
            try:
                _proc.kill()
            except OSError:
                pass
        _proc = None
    _read_stop = True


def browser(cmd, args=None):
    """统一入口。

    browser("goto", {"url": "https://example.com"})
    browser("snapshot")
    browser("observe", {"screenshot": True, "snapshot": True})
    browser("click_text", {"text": "登录"})
    browser("close")
    """
    global _req_id
    if args is None:
        args = {}

    with _lock:
        if not _start():
            return {"ok": False, "error": {"type": "LaunchError", "message": "启动失败", "cmd": cmd}}

        _req_id += 1
        req = {"id": f"r{_req_id}", "cmd": cmd, "args": args}
        _log(">>>", json.dumps(req, ensure_ascii=False)[:300])

        # 发送
        try:
            _proc.stdin.write(json.dumps(req, ensure_ascii=False) + "\n")
            _proc.stdin.flush()
        except BrokenPipeError:
            # 崩溃恢复一次
            _log("broken pipe, restarting...")
            if not _restart():
                return {"ok": False, "error": {"type": "LaunchError", "message": "重启失败", "cmd": cmd}}
            _req_id += 1
            req["id"] = f"r{_req_id}"
            try:
                _proc.stdin.write(json.dumps(req, ensure_ascii=False) + "\n")
                _proc.stdin.flush()
            except Exception as e:
                return {"ok": False, "error": {"type": type(e).__name__, "message": str(e), "cmd": cmd}}

        # 等待响应（带超时）
        timeout = args.get("timeout", 60000) if cmd not in ("close",) else 5000
        deadline = time.time() + timeout / 1000

        while time.time() < deadline:
            if _read_buf:
                raw = _read_buf.pop(0)
                try:
                    resp = json.loads(raw)
                    _log("<<<", "ok" if resp.get("ok") else "fail")
                    return resp
                except json.JSONDecodeError:
                    # 可能不是 JSON（如调试日志），继续等
                    _log("skip non-json:", raw[:100])
                    continue
            if _proc.poll() is not None:
                break
            time.sleep(0.05)

        # 超时
        _log("timeout, restarting...")
        _stop()
        return {"ok": False, "error": {"type": "TimeoutError", "message": f"{timeout/1000}秒无响应", "cmd": cmd}}


atexit.register(_stop)
