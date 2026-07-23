#!/usr/bin/env python3
"""trace_store.py — v2.7.0 统一 trace 写入/读取"""
import os, json, time
from pathlib import Path
from datetime import datetime

from tools.contract import BrowserResult, StepResult
from tools.sanitize import sanitize

if os.name == "nt":
    _RUNS_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".pi")) / "Pi" / "browser" / "runs"
else:
    _RUNS_DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "pi" / "browser" / "runs"


def new_trace_id(command: str) -> str:
    """生成统一 trace ID"""
    now = datetime.now()
    return f"{now.strftime('%Y%m%d_%H%M%S')}_{now.strftime('%f')[:3]}_{command}"


def write_trace(result: BrowserResult, command: str = "", run_dir: Path = None) -> str:
    """写入 trace.json，返回 trace_id"""
    if not result.trace_id:
        result.trace_id = new_trace_id(command or "unknown")

    rd = run_dir or (_RUNS_DIR / result.trace_id)
    rd.mkdir(parents=True, exist_ok=True)

    trace = {
        "started_at": datetime.now().isoformat(),
        "ended_at": datetime.now().isoformat(),
        "command": command or result.trace_id,
        "status": result.status,
        "error_code": result.error_code,
        "steps": [{
            "id": s.name or s.action,
            "action": s.action,
            "ok": s.status == "ok",
            "error_code": s.error_code,
            "provider_used": s.provider_used,
            "fallback_used": s.fallback_used,
        } for s in result.steps],
        "summary": {
            "status": result.status,
            "error_code": result.error_code,
            "provider_used": result.provider_used,
            "fallback_used": result.fallback_used,
            "trace_id": result.trace_id,
        },
    }

    # 写入前强制脱敏
    with open(rd / "trace.json", "w", encoding="utf-8") as f:
        json.dump(sanitize(trace), f, ensure_ascii=False, indent=2)

    return result.trace_id


def read_trace(run_id: str, runs_dir: Path = None) -> dict | None:
    """读取 trace.json，返回脱敏后的 dict"""
    rd = (runs_dir or _RUNS_DIR) / run_id
    tf = rd / "trace.json"
    if not tf.exists():
        return None
    with open(tf, encoding="utf-8") as f:
        return sanitize(json.load(f))


def list_traces(runs_dir: Path = None, limit: int = 20) -> list[dict]:
    """列出最近的 trace"""
    rd = runs_dir or _RUNS_DIR
    if not rd.exists():
        return []
    runs = []
    for d in sorted(rd.iterdir(), key=lambda x: x.name, reverse=True)[:limit]:
        if d.is_dir():
            tf = d / "trace.json"
            if tf.exists():
                try:
                    data = json.loads(tf.read_text(encoding="utf-8"))
                    runs.append(data.get("summary", {}))
                except (OSError, json.JSONDecodeError, TypeError, ValueError):
                    pass
    return runs


def trace_step_to_step_result(step: dict) -> StepResult:
    """将 trace 中的 step dict 转换为 StepResult"""
    return StepResult(
        name=step.get("id", ""),
        action=step.get("action", ""),
        status="ok" if step.get("ok") else "error",
        error_code=step.get("error_code", "unknown"),
        provider_used=step.get("provider_used", ""),
        fallback_used=bool(step.get("fallback_used", False)),
        child_trace=step.get("child_trace"),
    )
