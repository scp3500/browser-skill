#!/usr/bin/env python3
"""web_server.py — v2.7.0 Web 服务器管理"""
import os, sys, subprocess, signal, time, json
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PID_FILE = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".pi")) / "Pi" / "browser" / "web_server.pid"
LOG_FILE = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".pi")) / "Pi" / "browser" / "web_server.log"


def start(port: int = 8765, host: str = "127.0.0.1") -> tuple[bool, str]:
    """后台启动 Web 服务器"""
    if host != "127.0.0.1":
        return False, "config_web only supports 127.0.0.1"
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
            os.kill(pid, 0)
            return False, f"server already running (pid {pid})"
        except (OSError, ValueError):
            PID_FILE.unlink(missing_ok=True)

    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web_app.py")
    # Start with pythonw on Windows to hide console
    python = sys.executable
    cmd = [python, "-c", f"""
import sys, os
sys.path.insert(0, '{os.path.dirname(os.path.dirname(os.path.abspath(__file__)))}')
from tools.web_app import create_server
server = create_server(port={port}, host='{host}')
import json
# Write token to stdout for parsing
server.serve_forever()
"""]
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=open(LOG_FILE, "w") if LOG_FILE else subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        PID_FILE.write_text(str(proc.pid))
        time.sleep(0.5)
        return True, f"Web UI started on http://{host}:{port}/"
    except Exception as e:
        return False, str(e)


def stop() -> tuple[bool, str]:
    """停止 Web 服务器"""
    if not PID_FILE.exists():
        return False, "server not running"
    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, signal.SIGTERM)
        PID_FILE.unlink(missing_ok=True)
        return True, "server stopped"
    except (OSError, ValueError) as e:
        PID_FILE.unlink(missing_ok=True)
        return False, str(e)


def status() -> tuple[bool, dict]:
    """查询服务器状态"""
    if not PID_FILE.exists():
        return False, {"running": False}
    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, 0)
        return True, {"running": True, "pid": pid}
    except (OSError, ValueError):
        PID_FILE.unlink(missing_ok=True)
        return False, {"running": False}
