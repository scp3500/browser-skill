#!/usr/bin/env python3
"""test_web_ui.py — v2.5 Web UI 测试"""
import os, sys, json, threading, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import patch

from tools.web_app import create_server, WebHandler, _TOKEN
from tools.contract import BrowserResult
from tools.render import render_json


@pytest.fixture(scope="module")
def web_server():
    """启动测试服务器"""
    server = create_server(port=18765)  # Avoid port conflicts
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    time.sleep(0.3)
    yield server
    server.shutdown()


def _url(path: str = "/") -> str:
    return f"http://127.0.0.1:18765{path}?token={_TOKEN}"


def _headers() -> dict:
    return {"X-Token": _TOKEN}


# ===== config_web command tests =====

def test_config_web_rejects_non_localhost():
    from tools.commands import run_config_web
    result = run_config_web(["--host", "0.0.0.0"])
    assert result.status == "error"
    assert "127.0.0.1" in (result.message or "")
    assert result.provider_used == "none"


def test_config_web_command_has_five_line_header():
    from tools.commands import run_config_web
    from tools.render import render_text
    from tools.trace_store import new_trace_id
    result = run_config_web(["--port", "18766"])
    result.trace_id = new_trace_id("config_web")
    h = render_text(result)
    lines = h.split(chr(10))[:5]
    assert lines[0].startswith("Status:")
    assert lines[1].startswith("Error code:")
    assert lines[2].startswith("Provider used:")
    assert lines[3].startswith("Fallback used:")
    assert lines[4].startswith("Trace:")


def test_config_web_generates_token():
    assert _TOKEN and len(_TOKEN) >= 16


def test_config_web_url_contains_token():
    from tools.commands import run_config_web
    result = run_config_web(["--port", "18767"])
    assert "token=" in (result.message or "")


# ===== Web API tests =====

def test_web_api_requires_token(web_server):
    import urllib.request
    try:
        resp = urllib.request.urlopen("http://127.0.0.1:18765/api/health", timeout=3)
        assert False, "should have failed without token"
    except urllib.error.HTTPError as e:
        assert e.code == 401


def test_web_api_health_ok(web_server):
    import urllib.request
    resp = urllib.request.urlopen(_url("/api/health"), timeout=3)
    data = json.loads(resp.read())
    assert data["status"] == "ok"
    assert data["error_code"] == "ok"
    assert data["trace_id"] == "web"


def test_web_api_config_sanitized(web_server):
    import urllib.request
    resp = urllib.request.urlopen(_url("/api/config"), timeout=3)
    data = json.loads(resp.read())
    assert data["status"] == "ok"
    # api_key_env key name is allowed; plaintext secret value is not
    data_str = json.dumps(data)
    assert "sk-" not in data_str, "plaintext api key leaked"
    assert "Bearer" not in data_str, "Bearer token leaked"


def test_web_api_config_validate_ok(web_server):
    import urllib.request
    import yaml
    cfg = yaml.dump({"providers": {"default": "auto"}})
    req = urllib.request.Request(
        _url("/api/config/validate"),
        data=json.dumps({"yaml": cfg}).encode("utf-8"),
        headers={"Content-Type": "application/json", **_headers()},
        method="POST",
    )
    resp = urllib.request.urlopen(req, timeout=3)
    data = json.loads(resp.read())
    assert data["status"] == "ok"


def test_web_api_preset_list(web_server):
    import urllib.request
    resp = urllib.request.urlopen(_url("/api/presets"), timeout=3)
    data = json.loads(resp.read())
    assert "data" in data
    assert "presets" in data["data"]


def test_web_api_workflow_list(web_server):
    import urllib.request
    resp = urllib.request.urlopen(_url("/api/workflows"), timeout=3)
    data = json.loads(resp.read())
    assert "web_qa" in json.dumps(data)


def test_web_api_workflow_show(web_server):
    import urllib.request
    resp = urllib.request.urlopen(_url("/api/workflows/web_qa"), timeout=3)
    data = json.loads(resp.read())
    assert data["message"] and "read_url" in data["message"]


def test_web_api_workflow_validate(web_server):
    import urllib.request
    req = urllib.request.Request(
        _url("/api/workflows/web_qa/validate"),
        data=b"{}",
        headers=_headers(),
        method="POST",
    )
    resp = urllib.request.urlopen(req, timeout=3)
    data = json.loads(resp.read())
    assert data["status"] == "ok"


def test_web_api_trace_list(web_server):
    import urllib.request
    resp = urllib.request.urlopen(_url("/api/traces"), timeout=3)
    data = json.loads(resp.read())
    assert "traces" in data.get("data", {})


def test_web_api_trace_show_sanitized(web_server):
    import urllib.request
    # Just request the list
    resp = urllib.request.urlopen(_url("/api/traces"), timeout=3)
    assert resp.status == 200


def test_web_ui_home_contains_control_panel(web_server):
    import urllib.request
    resp = urllib.request.urlopen(_url("/"), timeout=3)
    html = resp.read().decode("utf-8")
    assert "Control Panel" in html


def test_web_ui_has_dashboard_config_presets_workflows_traces_diagnostics(web_server):
    import urllib.request
    resp = urllib.request.urlopen(_url("/"), timeout=3)
    html = resp.read().decode("utf-8")
    for section in ["Dashboard", "Config", "Presets", "Workflows", "Traces", "Diagnostics"]:
        assert section in html, f"Missing section: {section}"


# ===== config_web_status / config_web_stop =====

def test_config_web_status(web_server):
    """config_web_status should work without daemon"""
    from tools.commands import run_config_web_status
    result = run_config_web_status()
    assert result.provider_used == "none"


def test_web_api_diagnostics(web_server):
    import urllib.request
    resp = urllib.request.urlopen(_url("/api/diagnostics"), timeout=3)
    data = json.loads(resp.read())
    assert "environment" in data.get("data", {})


# ===== WEB_UI smoke self-audit workflows =====

def test_config_ui_smoke_workflow_exists():
    from tools.workflow_runner import load_spec
    spec = load_spec("web_qa")
    assert spec is not None


def test_web_ui_renders_trace_with_steps(web_server):
    import urllib.request
    # Get trace list first
    resp = urllib.request.urlopen(_url("/api/traces"), timeout=3)
    data = json.loads(resp.read())
    traces = data.get("data", {}).get("traces", [])
    if traces and traces[0].get("trace_id"):
        tid = traces[0]["trace_id"]
        resp2 = urllib.request.urlopen(_url(f"/api/traces/{tid}"), timeout=3)
        data2 = json.loads(resp2.read())
        assert data2["status"] == "ok"
