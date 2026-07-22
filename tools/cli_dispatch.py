#!/usr/bin/env python3
"""cli_dispatch.py — v2.5.1 CLI 调度层。统一路由到 commands.run_*"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tools.commands import *
from tools.render import render_text, render_json
from tools.contract import BrowserResult
from tools.trace_store import new_trace_id


def _ensure_trace(result: BrowserResult, cmd: str = "") -> BrowserResult:
    """渲染前确保 trace_id 存在"""
    if not result.trace_id:
        result.trace_id = new_trace_id(cmd or "unknown")
    return result


def dispatch(args: list[str]) -> BrowserResult:
    """根据 CLI args 路由到对应命令"""
    if not args:
        return BrowserResult(status="error", error_code="invalid_input", provider_used="none",
                              message="No command provided")

    cmd = args[0]
    rest = args[1:]

    result = None

    # Config commands
    if cmd == "config_path":
        result = run_config_path()
    elif cmd == "config_show":
        result = run_config_show(is_json="--json" in rest)
    elif cmd == "config_validate":
        result = run_config_validate()
    elif cmd == "config_set":
        result = run_config_set(rest[0] if rest else "")
    # Preset commands
    elif cmd == "preset_list":
        result = run_preset_list()
    elif cmd == "preset_show":
        name = rest[0] if rest else ""
        result = run_preset_show(name)
    elif cmd == "preset_use":
        name = rest[0] if rest else ""
        mode = "write" if "--write" in rest else "dry-run"
        result = run_preset_use(name, mode)
    # Workflow commands
    elif cmd == "workflow_list":
        result = run_workflow_list()
    elif cmd == "workflow_show":
        name = rest[0] if rest else ""
        result = run_workflow_show(name)
    elif cmd == "workflow_validate":
        name = rest[0] if rest else ""
        result = run_workflow_validate(name)
    elif cmd == "workflow_run":
        name = rest[0] if len(rest) > 0 else ""
        inputs = _parse_inputs(rest[1:])
        result = run_workflow_run(name, inputs)
    # Trace commands
    elif cmd == "trace_list":
        result = run_trace_list()
    elif cmd == "trace_show":
        run_id = rest[0] if rest else ""
        result = run_trace_show(run_id)
    # Search commands
    elif cmd == "search_candidates":
        result = run_search_candidates(rest)
    elif cmd == "search_official":
        result = run_search_official(rest)
    # Parallel commands
    elif cmd == "read_urls_parallel":
        result = run_read_urls_parallel(rest)
    # Web UI commands
    elif cmd == "config_web":
        result = run_config_web(rest)
    elif cmd == "config_web_status":
        result = run_config_web_status()
    elif cmd == "config_web_stop":
        result = run_config_web_stop()
    # Action commands
    elif cmd == "read_url":
        url = rest[0] if rest else ""
        provider = "auto"
        chars = "3000"
        i = 1
        while i < len(rest):
            if rest[i] == "--provider": provider = rest[i+1] if i+1 < len(rest) else "auto"; i += 2; continue
            if rest[i] == "--chars": chars = rest[i+1] if i+1 < len(rest) else "3000"; i += 2; continue
            i += 1
        result = run_read_url(url, provider, chars)
    elif cmd == "search_read":
        query = " ".join(rest) if rest else ""
        result = run_search_read(query)
    elif cmd == "diagnose":
        result = run_diagnose()
    elif cmd == "diagnose_and_recover":
        result = run_diagnose_and_recover()
    elif cmd == "screenshot_ask":
        query = " ".join(rest) if rest else ""
        mode = "diagnose"
        if "--mode" in rest:
            idx = rest.index("--mode")
            mode = rest[idx+1] if idx+1 < len(rest) else "diagnose"
        result = run_screenshot_ask(query, mode)
    elif cmd == "wait_text":
        text = " ".join(rest) if rest else ""
        result = run_wait_text(text)
    elif cmd == "assert_text":
        text = " ".join(rest) if rest else ""
        result = run_assert_text(text)
    elif cmd == "click_expect":
        click_text = ""; expect = ""; timeout = "10"
        remaining = list(rest)
        i = 0
        while i < len(remaining):
            if remaining[i] == "--expect": expect = " ".join(remaining[i+1:]); break
            if remaining[i] == "--timeout": timeout = remaining[i+1] if i+1 < len(remaining) else "10"; i += 2; continue
            click_text += " " + remaining[i]; i += 1
        result = run_click_expect(click_text.strip(), expect, timeout)
    else:
        return BrowserResult(status="error", error_code="invalid_mode", provider_used="none",
                              message=f"unknown command: {cmd}")

    return _ensure_trace(result, cmd)


def _parse_inputs(args: list[str]) -> dict:
    """解析 --var/--input 参数"""
    inputs = {}
    i = 0
    while i < len(args):
        if args[i] in ("--input", "-i"):
            try:
                fp = args[i+1] if i+1 < len(args) else ""
                with open(fp, "r", encoding="utf-8") as f:
                    inputs.update(json.load(f))
            except Exception as e:
                pass
            i += 2
            continue
        if args[i] in ("--var", "-v"):
            if i+1 < len(args) and "=" in args[i+1]:
                k, v = args[i+1].split("=", 1)
                inputs[k] = v
            i += 2
            continue
        i += 1
    return inputs
