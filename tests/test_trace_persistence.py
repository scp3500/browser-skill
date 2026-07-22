"""test_trace_persistence.py — trace 写入 + 脱敏测试"""
import sys, os, json, tempfile
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from browser_daemon import _write_trace as wt


def test_trace_persistence_sanitizes_before_write(tmp_path):
    # monkeypatch RUNS_DIR
    import browser_daemon as bd
    bd.RUNS_DIR = tmp_path

    trace_args = {"apiKey": "sk-secret", "token": "raw_token", "q": "ok"}
    trace_error = "failed with Bearer abc and sk-xyz"
    trace_url = "https://x.com/?token=raw&q=ok"

    started = datetime.now()
    run_dir = wt(started, "diagnose", trace_args,
                 [{"index": 1, "cmd": "test", "ok": True}],
                 "error", trace_error)

    text = Path(run_dir).joinpath("trace.json").read_text(encoding="utf-8")

    assert "sk-secret" not in text, "apiKey value leaked"
    assert "Bearer abc" not in text, "Bearer value leaked"
    assert "sk-xyz" not in text, "sk- value leaked"
    assert "raw_token" not in text, "token value leaked"
    assert '"q": "ok"' in text, "innocent query param removed"
    assert "[REDACTED]" in text, "no redaction occurred"


def test_trace_has_required_fields(tmp_path):
    import browser_daemon as bd
    bd.RUNS_DIR = tmp_path

    run_dir = wt(datetime.now(), "test_cmd", {"a": 1},
                 [], "ok")
    data = json.loads(Path(run_dir).joinpath("trace.json").read_text(encoding="utf-8"))

    assert "started_at" in data
    assert "ended_at" in data
    assert "duration_ms" in data
    assert data["command"] == "test_cmd"
    assert data["status"] == "ok"
    assert data["steps"] == []


def test_trace_error_status_has_error_field(tmp_path):
    import browser_daemon as bd
    bd.RUNS_DIR = tmp_path

    run_dir = wt(datetime.now(), "fail_cmd", {},
                 [], "error", "something went wrong")
    data = json.loads(Path(run_dir).joinpath("trace.json").read_text(encoding="utf-8"))

    assert data["status"] == "error"
    assert data["error"] is not None
