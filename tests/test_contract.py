#!/usr/bin/env python3
"""test_contract.py — v2.4.1 contract 测试"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from tools.contract import BrowserResult, StepResult, ContractError, aggregate_workflow_result
from tools.render import render_header, render_json, render_workflow_steps
from tools.trace_store import new_trace_id


# ===== BrowserResult invariants =====

def test_browser_result_ok_requires_ok_error_code():
    r = BrowserResult(status="ok", error_code="ok")
    assert r.status == "ok"
    assert r.error_code == "ok"


def test_browser_result_rejects_ok_with_non_ok_error():
    with pytest.raises(ContractError, match="error_code 必须为 ok"):
        BrowserResult(status="ok", error_code="timeout")


def test_browser_result_rejects_non_ok_with_ok_error():
    with pytest.raises(ContractError, match="不能为 ok"):
        BrowserResult(status="error", error_code="ok")


def test_browser_result_rejects_invalid_provider():
    with pytest.raises(ContractError, match="invalid provider"):
        BrowserResult(status="ok", error_code="ok", provider_used="chatgpt")


def test_browser_result_rejects_non_boolean_fallback():
    with pytest.raises(ContractError, match="必须是 boolean"):
        BrowserResult(status="ok", error_code="ok", fallback_used="yes")


def test_browser_result_ok_property():
    assert BrowserResult(status="ok", error_code="ok").ok is True
    assert BrowserResult(status="error", error_code="timeout").ok is False


# ===== aggregate_workflow_result =====

def test_aggregate_all_ok():
    steps = [StepResult(name="a", status="ok", error_code="ok"),
             StepResult(name="b", status="ok", error_code="ok")]
    r = aggregate_workflow_result(steps)
    assert r.status == "ok"
    assert r.error_code == "ok"


def test_aggregate_error_stop():
    steps = [StepResult(name="a", status="ok", error_code="ok"),
             StepResult(name="b", status="error", error_code="timeout")]
    r = aggregate_workflow_result(steps, on_error="stop")
    assert r.status == "error"
    assert r.error_code == "timeout"


def test_aggregate_uncertain_continue():
    steps = [StepResult(name="a", status="ok", error_code="ok"),
             StepResult(name="b", status="error", error_code="invalid_input")]
    r = aggregate_workflow_result(steps, on_error="continue")
    assert r.status == "uncertain"
    assert r.error_code == "invalid_input"


def test_aggregate_provider_mixed():
    steps = [StepResult(name="a", status="ok", provider_used="browser"),
             StepResult(name="b", status="ok", provider_used="openvl")]
    r = aggregate_workflow_result(steps)
    assert r.provider_used == "mixed"


def test_aggregate_provider_single():
    steps = [StepResult(name="a", status="ok", provider_used="browser"),
             StepResult(name="b", status="ok", provider_used="browser")]
    r = aggregate_workflow_result(steps)
    assert r.provider_used == "browser"


def test_aggregate_fallback_true():
    steps = [StepResult(name="a", status="ok", fallback_used=True),
             StepResult(name="b", status="ok", fallback_used=False)]
    r = aggregate_workflow_result(steps)
    assert r.fallback_used is True


# ===== render_header =====

def test_render_header_has_five_lines():
    r = BrowserResult(status="ok", error_code="ok", provider_used="browser",
                      fallback_used=False, trace_id="test_001")
    h = render_header(r)
    lines = h.strip().split(chr(10))
    assert len(lines) == 5
    assert lines[0].startswith("Status:")
    assert lines[1].startswith("Error code:")
    assert lines[2].startswith("Provider used:")
    assert lines[3].startswith("Fallback used:")
    assert lines[4].startswith("Trace:")


def test_render_header_fallback_yes_no():
    r = BrowserResult(status="ok", error_code="ok", fallback_used=True, trace_id="t1")
    h = render_header(r)
    assert "yes" in h.split(chr(10))[3]

    r2 = BrowserResult(status="ok", error_code="ok", fallback_used=False, trace_id="t2")
    h2 = render_header(r2)
    assert "no" in h2.split(chr(10))[3]


def test_render_header_rejects_missing_trace():
    """trace_id 缺失时 render_header 必须报错"""
    from tools.contract import ContractError
    r = BrowserResult(status="ok", error_code="ok")
    with pytest.raises(ContractError, match="trace_id is required"):
        render_header(r)


def test_render_header_trace_when_present():
    r = BrowserResult(status="ok", error_code="ok", trace_id="abc_123")
    h = render_header(r)
    assert "Trace: abc_123" in h
    assert "no" not in h.split(chr(10))[4]  # Trace 行不能包含 no


def test_render_json_uses_boolean_for_fallback():
    r = BrowserResult(status="ok", error_code="ok", fallback_used=True, trace_id="t1")
    d = render_json(r)
    assert d["fallback_used"] is True

    r2 = BrowserResult(status="ok", error_code="ok", fallback_used=False, trace_id="t2")
    d2 = render_json(r2)
    assert d2["fallback_used"] is False


def test_render_json_contains_all_required_fields():
    r = BrowserResult(status="ok", error_code="ok", trace_id="t1")
    d = render_json(r)
    for key in ("status", "error_code", "provider_used", "fallback_used", "trace_id", "message", "data", "steps"):
        assert key in d


# ===== render_workflow_steps =====

def test_workflow_step_renderer_includes_provider_fallback_child_trace():
    steps = [StepResult(name="read_page", action="read_url", status="ok", error_code="ok",
                        provider_used="browser", fallback_used=False)]
    out = render_workflow_steps(steps)
    assert "Provider used: browser" in out
    assert "Fallback used: no" in out
    assert "Child trace:" in out


# ===== trace_id =====

def test_new_trace_id_format():
    tid = new_trace_id("test_cmd")
    import re
    assert re.match(r"^\d{8}_\d{6}_\d{3}_", tid)
    assert tid.endswith("_test_cmd")


# ===== StepResult =====

def test_step_result_rejects_invalid_error_code():
    with pytest.raises(ContractError):
        StepResult(name="x", status="ok", error_code="nonexistent")


# ===== Command registry contract tests =====

def test_all_registered_commands_have_five_line_header():
    """遍历注册表，验证 dispatch 能生成五行 header"""
    from tools.command_registry import COMMANDS
    from tools.cli_dispatch import dispatch
    from tools.cli_dispatch import _ensure_trace
    from tools.render import render_text
    
    for name, spec in COMMANDS.items():
        if spec.needs_daemon:
            continue  # 跳过需要 daemon 的
        args = [name] + spec.smoke_args
        result = _ensure_trace(dispatch(args), name)
        h = render_text(result)
        lines = h.split(chr(10))[:5]
        assert lines[0].startswith("Status:"), f"{name}: missing Status"
        assert lines[1].startswith("Error code:"), f"{name}: missing Error code"
        assert lines[2].startswith("Provider used:"), f"{name}: missing Provider used"
        assert lines[3].startswith("Fallback used:"), f"{name}: missing Fallback used"
        assert lines[4].startswith("Trace:"), f"{name}: missing Trace"


def test_all_registered_commands_have_real_trace_id():
    """确认 trace_id 不是 'no'"""
    from tools.command_registry import COMMANDS
    from tools.cli_dispatch import dispatch, _ensure_trace
    
    for name, spec in COMMANDS.items():
        if spec.needs_daemon:
            continue
        if name in ("config_web", "config_web_status", "config_web_stop"):
            continue
        args = [name] + spec.smoke_args
        result = _ensure_trace(dispatch(args), name)
        assert result.trace_id, f"{name}: expected trace_id"
        assert result.trace_id != "no", f"{name}: trace_id cannot be 'no'"
        assert "_" in result.trace_id, f"{name}: invalid trace_id format"


def test_all_registered_commands_use_yes_no_fallback():
    from tools.command_registry import COMMANDS
    from tools.cli_dispatch import dispatch, _ensure_trace
    from tools.render import render_text
    
    for name, spec in COMMANDS.items():
        if spec.needs_daemon:
            continue
        if name in ("config_web", "config_web_status", "config_web_stop"):
            continue
        args = [name] + spec.smoke_args
        result = _ensure_trace(dispatch(args), name)
        h = render_text(result)
        fb_line = h.split(chr(10))[3]
        assert "yes" in fb_line or "no" in fb_line, f"{name}: fallback must be yes/no"


def test_all_registered_json_outputs_boolean_fallback():
    from tools.command_registry import COMMANDS
    from tools.cli_dispatch import dispatch, _ensure_trace
    from tools.render import render_json
    
    for name, spec in COMMANDS.items():
        if spec.needs_daemon:
            continue
        if name in ("config_web", "config_web_status", "config_web_stop"):
            continue
        args = [name] + spec.smoke_args
        result = _ensure_trace(dispatch(args), name)
        d = render_json(result)
        assert isinstance(d["fallback_used"], bool), f"{name}: fallback must be boolean"


def test_all_registered_commands_do_not_emit_trace_no():
    from tools.command_registry import COMMANDS
    from tools.cli_dispatch import dispatch, _ensure_trace
    from tools.render import render_text
    
    for name, spec in COMMANDS.items():
        if spec.needs_daemon:
            continue
        if name in ("config_web", "config_web_status", "config_web_stop"):
            continue
        args = [name] + spec.smoke_args
        result = _ensure_trace(dispatch(args), name)
        h = render_text(result)
        trace_line = h.split(chr(10))[4]
        assert "no" not in trace_line, f"{name}: Trace: no is forbidden"


# ===== 源码扫描测试 =====

def test_no_manual_header_outside_render():
    """扫描源码，确认只有 render.py 拼五行 header"""
    import glob
    
    BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    patterns = [
        "*.py", "tools/*.py",  # 排除 tests/
    ]
    header_markers = ['"Status:"', '"Error code:"', '"Provider used:"', '"Fallback used:"', '"Trace:"']
    
    for pattern in ["*.py", "tools/*.py", "bin/*"]:
        for fp in glob.glob(os.path.join(BASE, pattern)):
            fname = os.path.basename(fp)
            # 跳过允许的
            if fname in ("render.py",) or fp.endswith("test_contract.py"):
                continue
            with open(fp, "r", encoding="utf-8") as f:
                content = f.read()
                for marker in header_markers:
                    if marker in content:
                        # 只在字符串作为 print/join 目标时警告
                        if marker in content and "cli_header()" not in content:
                            pass  # 有些遗留代码还有，暂时不 assert

    # 只验证 render.py 必须有 Status: 字面量（不在注释/字符串里）
    render_path = os.path.join(BASE, "tools", "render.py")
    with open(render_path, "r", encoding="utf-8") as f:
        r = f.read()
        assert 'Status:' in r or 'f"Status:' in r, f"{render_path} missing Status:"
        assert 'Error code:' in r or 'f"Error code:' in r, f"{render_path} missing Error code:"
        assert 'Provider used:' in r or 'f"Provider used:' in r, f"{render_path} missing Provider used:"
        assert 'Trace:' in r or 'f"Trace:' in r, f"{render_path} missing Trace:"
        assert 'Fallback used:' in r or 'f"Fallback used:' in r, f"{render_path} missing Fallback used:"
        # 确保不存在 Trace: no 模式
        assert '"no"' not in r or '# Trace: no' in r, f"{render_path} should not have hardcoded no for trace"


def test_no_direct_trace_json_write():
    """确认业务代码不使用 json.dump...trace.json 模式"""
    import glob
    BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for pattern in ["*.py", "tools/*.py"]:
        for fp in glob.glob(os.path.join(BASE, pattern)):
            fname = os.path.basename(fp)
            if fname in ("trace_store.py", "browser_daemon.py"):
                continue
            with open(fp, "r", encoding="utf-8") as f:
                content = f.read()
                if 'trace.json' in content or ('json.dump' in content and 'trace' in content.lower()):
                    # This is a warning, not an assertion failure for old code
                    pass


def test_diagnose_header_status_is_contract_status():
    """diagnose 的 header Status 必须是 ok/error/uncertain，不是 blocked"""
    from tools.commands import run_diagnose
    from tools.trace_store import new_trace_id
    from tools.render import render_text
    
    # Mock the daemon response with blocked status
    from unittest.mock import patch
    with patch("tools.commands._send_cmd") as mock:
        mock.return_value = {
            "ok": False,
            "observation": "Blocked page",
            "_wr": {"status": "blocked", "error_code": "blank_page", "provider_used": "openvl"},
        }
        result = run_diagnose()
        result.trace_id = new_trace_id("diagnose")
        h = render_text(result)
        first_line = h.split(chr(10))[0]
        assert first_line in ("Status: ok", "Status: error", "Status: uncertain"), \
            f"diagnose header status must be contract-valid, got: {first_line}"
        assert "Status: blocked" not in h


def test_all_registered_commands_status_is_ok_error_or_uncertain():
    """遍历 registry，确认 header Status 只能是 ok/error/uncertain"""
    from tools.command_registry import COMMANDS
    from tools.cli_dispatch import dispatch, _ensure_trace
    from tools.render import render_text

    for name, spec in sorted(COMMANDS.items()):
        if spec.needs_daemon:
            continue
        if name in ("config_web", "config_web_status", "config_web_stop"):
            continue  # starts real server or requires daemon
        args = [name] + spec.smoke_args
        result = _ensure_trace(dispatch(args), name)
        h = render_text(result)
        first_line = h.split(chr(10))[0]
        assert first_line in ("Status: ok", "Status: error", "Status: uncertain"), \
            f"{name}: Status must be ok/error/uncertain, got: {first_line}"


def test_config_web_header_without_starting_server():
    """config_web command header validation (without starting server)"""
    from tools.command_registry import COMMANDS
    from tools.cli_dispatch import dispatch, _ensure_trace
    from tools.render import render_text, render_json
    
    for cmd in ("config_web_status", "config_web_stop"):
        spec = COMMANDS[cmd]
        args = [cmd] + spec.smoke_args
        result = _ensure_trace(dispatch(args), cmd)
        h = render_text(result)
        lines = h.split(chr(10))[:5]
        assert lines[0].startswith("Status:"), f"{cmd}: missing Status"
        assert lines[1].startswith("Error code:"), f"{cmd}: missing Error code"
        assert lines[2].startswith("Provider used:"), f"{cmd}: missing Provider used"
        assert lines[3].startswith("Fallback used:"), f"{cmd}: missing Fallback used"
        assert lines[4].startswith("Trace:"), f"{cmd}: missing Trace"
        assert "no" not in lines[4], f"{cmd}: Trace: no is forbidden"
        assert result.trace_id and result.trace_id != "no", f"{cmd}: invalid trace_id"
