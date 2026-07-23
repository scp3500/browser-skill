#!/usr/bin/env python3
"""commands.py — v2.5.1 统一命令实现。所有函数返回 BrowserResult"""
import os, sys, json, yaml, time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.contract import BrowserResult, StepResult
from tools.render import render_text, render_json
from tools.trace_store import new_trace_id, write_trace
from tools.sanitize import sanitize, has_plaintext_secret


# ===== Config commands =====

def run_config_path() -> BrowserResult:
    from tools.config import get_user_config_path
    return BrowserResult(
        status="ok", error_code="ok", provider_used="none",
        message=f"Config path: {get_user_config_path()}",
    )


def run_config_show(is_json: bool = False) -> BrowserResult:
    from tools.config import load_effective
    cfg = load_effective()
    if is_json:
        return BrowserResult(
            status="ok", error_code="ok", provider_used="none",
            data={"config": cfg},
        )
    import yaml
    return BrowserResult(
        status="ok", error_code="ok", provider_used="none",
        message=yaml.dump(cfg, default_flow_style=False, allow_unicode=True).strip(),
    )


def run_config_validate() -> BrowserResult:
    from tools.config import load_effective, validate as validate_config
    cfg = load_effective()
    try:
        validate_config(cfg)
        return BrowserResult(
            status="ok", error_code="ok", provider_used="none",
            message="Config is valid",
        )
    except (ValueError, yaml.YAMLError) as e:
        return BrowserResult(
            status="error", error_code="invalid_config", provider_used="none",
            message=str(e),
        )


def run_config_set(kv_str: str) -> BrowserResult:
    from tools.config import USER_CONFIG_FILE, load_user_config
    if "=" not in kv_str:
        return BrowserResult(
            status="error", error_code="invalid_input",
            provider_used="none", message="Usage: config_set key=value",
        )
    key, val_str = kv_str.split("=", 1)
    keys = key.split(".")
    # Parse value
    try:
        val = int(val_str)
    except ValueError:
        val_str_lower = val_str.lower()
        if val_str_lower in ("true", "yes"):
            val = True
        elif val_str_lower in ("false", "no"):
            val = False
        else:
            val = val_str
    old = load_user_config()
    d = old
    for k in keys[:-1]:
        d = d.setdefault(k, {})
    d[keys[-1]] = val
    USER_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(USER_CONFIG_FILE, "w", encoding="utf-8") as f:
        yaml.dump(old, f, default_flow_style=False, allow_unicode=True)
    return BrowserResult(
        status="ok", error_code="ok", provider_used="none",
        message=f"{key} = {val}",
    )


# ===== Preset commands =====

def run_preset_list() -> BrowserResult:
    from tools.config import get_presets
    presets = get_presets()
    lines = [f"  {name}" for name in presets]
    return BrowserResult(
        status="ok", error_code="ok", provider_used="none",
        message="Presets:\n" + "\n".join(lines) if lines else "No presets found",
    )


def run_preset_show(name: str) -> BrowserResult:
    from tools.config import load_preset
    p = load_preset(name)
    if p is None:
        return BrowserResult(
            status="error", error_code="not_found",
            provider_used="none", message=f"preset not found: {name}",
        )
    s = yaml.dump(p, default_flow_style=False, allow_unicode=True).strip()
    return BrowserResult(
        status="ok", error_code="ok", provider_used="none",
        message=s,
    )


def run_preset_use(name: str, mode: str = "dry-run") -> BrowserResult:
    from tools.config import load_preset, USER_CONFIG_FILE
    p = load_preset(name)
    if p is None:
        return BrowserResult(
            status="error", error_code="not_found",
            provider_used="none", message=f"preset not found: {name}",
        )
    if mode == "dry-run":
        s = yaml.dump(p, default_flow_style=False, allow_unicode=True).strip()
        return BrowserResult(
            status="ok", error_code="ok", provider_used="none",
            message=f"Would write:\n{s}\nTo: {USER_CONFIG_FILE}",
        )
    # mode == "write"
    USER_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(USER_CONFIG_FILE, "w", encoding="utf-8") as f:
        yaml.dump(p, f, default_flow_style=False, allow_unicode=True)
    return BrowserResult(
        status="ok", error_code="ok", provider_used="none",
        message=f"preset applied: {name}\nTo: {USER_CONFIG_FILE}",
    )


# ===== Workflow commands =====

def run_workflow_list() -> BrowserResult:
    from tools.workflow_runner import SPECS_DIR, WORKFLOWS_DIR
    names = sorted(f.stem for f in SPECS_DIR.glob("*.yaml")) if SPECS_DIR.exists() else []
    lines = []
    for name in names:
        spec_path = SPECS_DIR / f"{name}.yaml"
        if spec_path.exists():
            spec = yaml.safe_load(spec_path.read_text(encoding="utf-8")) or {}
            desc = (spec.get("description", "").split('.')[0][:60] if spec else "")
            inputs = ", ".join(i.get("name", "") for i in (spec.get("inputs", []) if spec else []))
            lines.append(f"  {name}")
            if desc:
                lines.append(f"    Purpose: {desc}")
            if inputs:
                lines.append(f"    Inputs: {inputs}")
            ex_input = inputs.split(',')[0].strip() if inputs else ""
            lines.append(f"    Example: browser workflow_run {name}" + (f" --var {ex_input}=..." if ex_input else ""))
    return BrowserResult(
        status="ok", error_code="ok", provider_used="none",
        message="\n".join(lines) if lines else "No workflows found",
    )


def run_workflow_show(name: str) -> BrowserResult:
    from tools.workflow_runner import WORKFLOWS_DIR, SPECS_DIR
    md = WORKFLOWS_DIR / f"{name}.md"
    if md.exists():
        content = md.read_text(encoding="utf-8")
        # Extract name, purpose, inputs, steps, example
        return BrowserResult(
            status="ok", error_code="ok", provider_used="none",
            message=content,
        )
    spec_path = SPECS_DIR / f"{name}.yaml"
    if spec_path.exists():
        return BrowserResult(
            status="ok", error_code="ok", provider_used="none",
            message=spec_path.read_text(encoding="utf-8"),
        )
    return BrowserResult(
        status="error", error_code="not_found",
        provider_used="none", message=f"workflow not found: {name}",
    )


def run_workflow_run(name: str, inputs: dict) -> BrowserResult:
    from tools.workflow_runner import run
    result = run(name, inputs)
    wr_obj = result.get("_wr")
    if wr_obj:
        if hasattr(wr_obj, "status"):
            br = BrowserResult(
                status=wr_obj.status,
                error_code=wr_obj.error_code,
                provider_used=getattr(wr_obj, "provider_used", "none"),
                fallback_used=bool(getattr(wr_obj, "fallback_used", False)),
                trace_id=getattr(wr_obj, "trace_id", None) or result.get("trace_id"),
                message=result.get("observation", ""),
                data=result.get("data", {}),
            )
            return br
        elif isinstance(wr_obj, dict):
            return BrowserResult(
                status=wr_obj.get("status", "error"),
                error_code=wr_obj.get("error_code", "unknown"),
                provider_used=wr_obj.get("provider_used", "none"),
                fallback_used=bool(wr_obj.get("fallback_used", False)),
                trace_id=wr_obj.get("trace_id") or result.get("trace_id"),
                message=result.get("observation", ""),
            )
    return BrowserResult(
        status="ok", error_code="ok",
        provider_used="none",
        message=result.get("observation", ""),
    )


def run_workflow_validate(name: str) -> BrowserResult:
    from tools.config import validate_workflow_spec
    from tools.workflow_runner import SPECS_DIR
    spec_path = SPECS_DIR / f"{name}.yaml"
    if not spec_path.exists():
        return BrowserResult(
            status="error", error_code="not_found",
            provider_used="none", message=f"workflow not found: {name}",
        )
    import yaml
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    if not spec:
        return BrowserResult(
            status="error", error_code="invalid_config",
            provider_used="none", message=f"empty or invalid workflow spec: {name}",
        )
    try:
        validate_workflow_spec(spec)
        return BrowserResult(
            status="ok", error_code="ok", provider_used="none",
            message="Workflow spec is valid",
        )
    except ValueError as e:
        return BrowserResult(
            status="error", error_code="invalid_config",
            provider_used="none", message=str(e),
        )


# ===== Trace commands =====

def run_trace_list() -> BrowserResult:
    from tools.trace_store import list_traces
    traces = list_traces()
    if not traces:
        return BrowserResult(
            status="ok", error_code="ok", provider_used="none",
            message="No traces found",
        )
    lines = []
    for t in traces[:20]:
        tid = t.get("trace_id", "?")
        st = t.get("status", "?")
        ec = t.get("error_code", "?")
        lines.append(f"  {tid}  [{st}] {ec}")
    return BrowserResult(
        status="ok", error_code="ok", provider_used="none",
        message="\n".join(lines),
    )


def run_trace_show(run_id: str) -> BrowserResult:
    from tools.trace_store import read_trace, trace_step_to_step_result
    from tools.render import render_workflow_steps
    data = read_trace(run_id)
    if data is None:
        return BrowserResult(
            status="error", error_code="not_found",
            provider_used="none", message=f"trace not found: {run_id}",
        )
    s = data.get("summary", {})
    wf = data.get("workflow", {})
    wf_steps = wf.get("steps", []) if wf else []
    steps = []
    for st in wf_steps:
        steps.append(trace_step_to_step_result(st))

    lines = [
        f"Run ID: {run_id}",
        f"Command: {data.get('command', '?')}",
        f"Status: {s.get('status','?')}  Error code: {s.get('error_code','?')}",
        f"Provider used: {s.get('provider_used','?')}  Fallback used: {'yes' if s.get('fallback_used') else 'no'}",
        f"Started: {data.get('started_at','?')}  Ended: {data.get('ended_at','?')}  Duration: {data.get('duration_ms',0)}ms",
        f"URL: {s.get('url','')}  Title: {s.get('title','')}",
    ]
    if steps:
        lines.append(f"Workflow: {wf.get('name','?')}")
        lines.append("Steps:")
        for idx, st in enumerate(steps, 1):
            lines.append(f"  {idx}. {st.name}")
            lines.append(f"     Action: {st.action}")
            lines.append(f"     Status: {st.status}")
            lines.append(f"     Error code: {st.error_code}")
            lines.append(f"     Provider used: {st.provider_used or 'none'}")
            lines.append(f"     Fallback used: {'yes' if st.fallback_used else 'no'}")
            lines.append(f"     Child trace: {st.child_trace or ''}")
    else:
        raw_steps = data.get("steps", [])
        if raw_steps:
            lines.append(f"Steps: {len(raw_steps)}")
            for st in raw_steps[:5]:
                lines.append(f"  {st.get('index','')}. {st.get('cmd','?')} -> {'OK' if st.get('ok') else 'FAIL'}")
    err = data.get("error")
    if err:
        lines.append(f"Error: {err}")

    return BrowserResult(
        status="ok" if s.get("status") == "ok" else "error",
        error_code=s.get("error_code", "ok"),
        provider_used="none",
        message="\n".join(lines),
    )


# ===== Action commands (daemon-mediated) =====

def _send_cmd(cmd: str, args: dict = None) -> dict:
    """Send command to daemon and get response dict"""
    import socket, json
    s = socket.socket()
    s.settimeout(30)
    try:
        s.connect(("127.0.0.1", 8765))
        payload = {"type": "cmd", "cmd": cmd, "args": args or {}}
        s.sendall((json.dumps(payload) + "\n").encode("utf-8"))
        f = s.makefile("r", encoding="utf-8")
        resp = json.loads(f.readline())
        s.close()
        return resp
    except Exception as e:
        if s: s.close()
        return {"ok": False, "observation": f"daemon error: {e}"}


def _result_from_daemon(resp: dict, provider: str = "browser") -> BrowserResult:
    """Convert daemon JSON response to BrowserResult"""
    ok = resp.get("ok", False)
    if ok:
        return BrowserResult(
            status="ok", error_code="ok", provider_used=provider,
            message=resp.get("observation", ""),
            data={k: resp[k] for k in ("_url", "_title", "_text") if k in resp},
        )
    wr = resp.get("_wr", {})
    if isinstance(wr, dict):
        raw_status = wr.get("status", "error")
        # 映射旧 status 到 contract 合法值
        if raw_status == "blocked":
            raw_status = "error"
        return BrowserResult(
            status=raw_status,
            error_code=wr.get("error_code", "unknown"),
            provider_used=wr.get("provider_used", provider),
            fallback_used=bool(wr.get("fallback_used", False)),
            trace_id=wr.get("trace_id"),
            message=resp.get("observation", ""),
        )
    if isinstance(wr, str):
        return BrowserResult(
            status="error", error_code="unknown", provider_used=provider,
            message=wr or resp.get("observation", ""),
        )
    return BrowserResult(
        status="error", error_code="unknown", provider_used=provider,
        message=resp.get("observation", ""),
    )


def run_read_url(url: str, provider: str = "auto", chars: str = "1000") -> BrowserResult:
    from tools.v2_workflow_runner import run_workflow
    # We need to call read_url through the workflow system
    # fallback to direct daemon call
    resp = _send_cmd("read_url", {"url": url, "provider": provider, "chars": chars})
    return _result_from_daemon(resp)


def run_search_read(query: str, chars: str = "1000", fallback: bool = True) -> BrowserResult:
    resp = _send_cmd("search_read", {"query": query, "chars": chars, "fallback": fallback})
    return _result_from_daemon(resp)


def run_diagnose() -> BrowserResult:
    resp = _send_cmd("diagnose")
    return _result_from_daemon(resp)


def run_diagnose_and_recover() -> BrowserResult:
    resp = _send_cmd("diagnose_and_recover")
    return _result_from_daemon(resp)


def run_screenshot_ask(query: str = "", mode: str = "diagnose") -> BrowserResult:
    resp = _send_cmd("screenshot_ask", {"query": query, "mode": mode})
    return _result_from_daemon(resp, provider="openvl")


def run_wait_text(text: str, timeout: str = "10") -> BrowserResult:
    resp = _send_cmd("wait_text", {"text": text, "timeout": timeout})
    return _result_from_daemon(resp)


def run_assert_text(text: str) -> BrowserResult:
    resp = _send_cmd("assert_text", {"text": text})
    return _result_from_daemon(resp)


def run_click_expect(click_text: str, expect: str = "", timeout: str = "10") -> BrowserResult:
    resp = _send_cmd("click_expect", {"click_text": click_text, "expect": expect, "timeout": timeout})
    return _result_from_daemon(resp)


# ===== Web UI commands =====

def run_config_web(args: list[str]) -> BrowserResult:
    """Start web control panel"""
    port = 8767
    host = "127.0.0.1"
    import re
    for i, a in enumerate(args):
        if a == "--port" and i+1 < len(args):
            try:
                port = int(args[i+1])
            except ValueError:
                return BrowserResult(status="error", error_code="invalid_input", provider_used="none",
                                     message=f"invalid port: {args[i+1]}")
        if a == "--host" and i+1 < len(args):
            host = args[i+1]
    if host != "127.0.0.1":
        return BrowserResult(status="error", error_code="invalid_config", provider_used="none",
                             message="config_web only supports 127.0.0.1")
    
    # Check if port is available
    import socket
    try:
        test_sock = socket.socket()
        test_sock.settimeout(1)
        test_sock.bind((host, port))
        test_sock.close()
    except OSError:
        return BrowserResult(status="error", error_code="invalid_config",
                             provider_used="none",
                             message=f"port {port} is already in use (daemon uses 8765, config_web needs a different port)")

    from tools.web_app import create_server, _TOKEN
    server = create_server(port=port, host=host)
    import threading
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    url = f"http://{host}:{port}/?token={_TOKEN}"
    return BrowserResult(
        status="ok", error_code="ok", provider_used="none",
        message=f"Browser Skill Control Panel\nURL: {url}",
    )


def run_config_web_status() -> BrowserResult:
    from tools.web_server import status as svr_status
    ok, info = svr_status()
    if ok:
        return BrowserResult(status="ok", error_code="ok", provider_used="none",
                             message=f"Web server running (pid {info.get('pid','?')})")
    return BrowserResult(status="ok", error_code="ok", provider_used="none",
                         message="Web server not running")


def run_config_web_stop() -> BrowserResult:
    from tools.web_server import stop as svr_stop
    ok, msg = svr_stop()
    return BrowserResult(
        status="ok" if ok else "error",
        error_code="ok" if ok else "not_found",
        provider_used="none",
        message=msg,
    )


# ===== Parallel read commands =====

def _execute_read_url_parallel_task(url: str, idx: int, provider: str, timeout_ms: int) -> dict:
    """Execute read_url in independent page, does not interfere with main page"""
    import json, socket, time
    from tools.trace_store import new_trace_id, write_trace
    from tools.contract import BrowserResult
    
    child_trace_id = new_trace_id(f"read_url_{idx}")
    
    try:
        s = socket.socket()
        s.settimeout(timeout_ms / 1000.0 + 5)
        s.connect(("127.0.0.1", 8765))
        payload = {"type": "cmd", "cmd": "read_url_new_page", "args": {"url": url, "chars": 3000, "timeout": timeout_ms}}
        s.sendall((json.dumps(payload) + chr(10)).encode("utf-8"))
        f = s.makefile("r", encoding="utf-8")
        resp = json.loads(f.readline())
        s.close()
        
        ok = resp.get("ok", False)
        status = "ok" if ok else "error"
        ec = "ok" if ok else "read_failed"
        title = resp.get("title", "") if ok else ""
        text = resp.get("text", "") if ok else ""
        obs = resp.get("observation", "") if not ok else ""
        
        # Real excerpt from text, not "Read OK"
        excerpt = (text[:1000] if text else "") if ok else (obs[:200] if obs else "")
        
        child_r = BrowserResult(
            status=status, error_code=ec, provider_used=provider,
            fallback_used=False, trace_id=child_trace_id,
            message=excerpt[:500] if excerpt else "",
        )
        write_trace(child_r, f"read_url_{idx}")
        
        # Determine truncation
        requested_chars = 3000
        text_len = len(text) if text else 0
        truncated = text_len > 200 if text else False
        extraction_incomplete = False
        if text and text_len >= 200 and text_len < 100:
            extraction_incomplete = True
        
        return {
            "url": str(url), "status": str(status), "error_code": str(ec),
            "provider_used": str(provider), "fallback_used": False,
            "child_trace": str(child_trace_id),
            "title": str(title), "excerpt": excerpt[:1000],
            "truncated": truncated,
            "extraction_incomplete": extraction_incomplete,
            "requested_chars": requested_chars,
            "returned_chars": text_len,
            "ok": ok,
        }
    except Exception as e:
        child_r = BrowserResult(
            status="error", error_code="timeout", provider_used=provider,
            fallback_used=False, trace_id=child_trace_id,
            message=str(e)[:200],
        )
        write_trace(child_r, f"read_url_{idx}")
        return {
            "url": str(url), "status": "error", "error_code": "timeout",
            "provider_used": str(provider), "fallback_used": False,
            "child_trace": str(child_trace_id),
            "title": "", "excerpt": str(e)[:200],
            "truncated": False,
            "ok": False,
        }




def run_read_urls_parallel(args: list[str]) -> BrowserResult:
    """Parallel read multiple URLs"""
    import json, concurrent.futures, os
    
    # Parse args
    input_file = ""
    provider = "browser"
    max_concurrency = 3
    timeout_ms = 30000
    
    i = 0
    while i < len(args):
        if args[i] in ("--input", "-i") and i+1 < len(args):
            input_file = args[i+1]; i += 2; continue
        if args[i] == "--provider" and i+1 < len(args):
            provider = args[i+1]; i += 2; continue
        if args[i] == "--max-concurrency" and i+1 < len(args):
            try:
                val = int(args[i+1])
                if val < 1 or val > 10:
                    return BrowserResult(status="error", error_code="invalid_input", provider_used="none",
                                         message="max-concurrency must be 1-10")
                max_concurrency = val
            except ValueError:
                return BrowserResult(status="error", error_code="invalid_input", provider_used="none",
                                     message=f"invalid max-concurrency: {args[i+1]}")
            i += 2; continue
        if args[i] == "--timeout-ms" and i+1 < len(args):
            try:
                timeout_ms = int(args[i+1])
                if timeout_ms < 1000 or timeout_ms > 120000:
                    return BrowserResult(status="error", error_code="invalid_input", provider_used="none",
                                         message="timeout-ms must be 1000-120000")
            except ValueError:
                return BrowserResult(status="error", error_code="invalid_input", provider_used="none",
                                     message=f"invalid timeout-ms: {args[i+1]}")
            i += 2; continue
        i += 1
    
    if not input_file:
        return BrowserResult(status="error", error_code="invalid_input", provider_used="none",
                             message="--input urls.json is required")
    
    try:
        with open(input_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return BrowserResult(status="error", error_code="invalid_input", provider_used="none",
                             message=f"read input failed: {e}")
    
    urls = data if isinstance(data, list) else data.get("urls", [])
    if not urls:
        return BrowserResult(status="error", error_code="invalid_input", provider_used="none",
                             message="No URLs found in input")
    
    # Run parallel tasks
    from tools.trace_store import write_trace, new_trace_id
    from tools.contract import StepResult, aggregate_workflow_result
    from tools.sanitize import sanitize
    
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_concurrency) as executor:
        futures = {
            executor.submit(_execute_read_url_parallel_task, url, idx, provider, timeout_ms): idx
            for idx, url in enumerate(urls)
        }
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())
    
    # Sort by original order
    results.sort(key=lambda r: urls.index(str(r.get("url",""))) if str(r.get("url","")) in urls else 0)
    
    # Build StepResults for parent trace
    steps = []
    for r in results:
        steps.append(StepResult(
            name=f"read_url_{urls.index(r['url']) if r['url'] in urls else 0}",
            action="read_url",
            status=r["status"],
            error_code=r["error_code"],
            provider_used=r.get("provider_used", provider),
            fallback_used=r.get("fallback_used", False),
            child_trace=r.get("child_trace", ""),
        ))
    
    # Aggregate
    all_ok = all(r["ok"] for r in results)
    all_providers = {r.get("provider_used", provider) for r in results if r.get("provider_used") and r["provider_used"] != "none"}
    any_fallback = any(r.get("fallback_used", False) for r in results)
    
    if all_ok:
        wf_status, wf_ec = "ok", "ok"
    elif any(r["ok"] for r in results):
        wf_status, wf_ec = "uncertain", next((r["error_code"] for r in results if not r["ok"]), "partial_failure")
    else:
        wf_status, wf_ec = "error", next((r["error_code"] for r in results if not r["ok"]), "unknown")
    
    provider_used = "mixed" if len(all_providers) > 1 else (next(iter(all_providers)) if all_providers else provider)
    fallback_used = any_fallback
    
    # Build output lines
    obs_lines = ["Results:"]
    for r in results:
        url = str(r.get("url", "") or "")[:200]
        status = str(r.get("status", "?") or "?")
        ec = str(r.get("error_code", "?") or "?")
        pu = str(r.get("provider_used", provider) or provider)
        fb = bool(r.get("fallback_used", False))
        ct = str(r.get("child_trace", "") or "")
        truncated = bool(r.get("truncated", False))
        title = str(r.get("title", "") or "")[:100]
        excerpt = str(r.get("excerpt", "") or "")[:200]
        
        obs_lines.append(f"  URL: {url}")
        obs_lines.append(f"    Status: {status}")
        obs_lines.append(f"    Error code: {ec}")
        obs_lines.append(f"    Provider used: {pu}")
        obs_lines.append(f"    Fallback used: {'yes' if fb else 'no'}")
        obs_lines.append(f"    Child trace: {ct}")
        obs_lines.append(f"    Truncated: {'yes' if truncated else 'no'}")
        extraction_incomplete = bool(r.get("extraction_incomplete", False))
        obs_lines.append(f"    Extraction incomplete: {'yes' if extraction_incomplete else 'no'}")
        if title: obs_lines.append(f"    Title: {title}")
        if excerpt: obs_lines.append(f"    Excerpt: {excerpt}")
    
    br = BrowserResult(
        status=wf_status,
        error_code=wf_ec,
        provider_used=provider_used,
        fallback_used=fallback_used,
        message="\n".join(obs_lines),
        steps=steps,
        data={"results": sanitize(results)},
    )
    
    # Write parent trace
    write_trace(br, "read_urls_parallel")
    
    return br


# ===== Search / Official commands =====

def _classify_source_type(url: str, allowed_domains: list[str]) -> str:
    """Classify source type based on URL and allowed domains"""
    import re
    if not url:
        return "unknown"
    try:
        from urllib.parse import urlparse
        hostname = urlparse(url).hostname or ""
    except Exception:
        hostname = ""
    for domain in allowed_domains:
        if hostname == domain or hostname.endswith("." + domain):
            return "official"
    return "third_party"


def run_search_candidates(args: list[str]) -> BrowserResult:
    """Search for candidates using dokobot, return URL/title/source_type"""
    query = ""
    allowed_domains = []
    provider = "dokobot"
    limit = 10

    i = 0
    while i < len(args):
        if args[i] == "--query" and i+1 < len(args):
            query = args[i+1]; i += 2; continue
        if args[i] == "--allowed-domain" and i+1 < len(args):
            allowed_domains.append(args[i+1]); i += 2; continue
        if args[i] == "--provider" and i+1 < len(args):
            provider = args[i+1]; i += 2; continue
        if args[i] == "--limit" and i+1 < len(args):
            try: limit = int(args[i+1])
            except (TypeError, ValueError): pass
            i += 2; continue
        i += 1

    if not query:
        return BrowserResult(status="error", error_code="invalid_input", provider_used="none",
                              message="--query is required")
    if not allowed_domains:
        return BrowserResult(status="error", error_code="invalid_input", provider_used="none",
                              message="--allowed-domain is required")

    # Use dokobot to search
    candidates = []
    search_provider = "dokobot"
    search_results = []

    try:
        from tools.dokobot_tool import search as _dokobot_search
        search_results = _dokobot_search(query, limit=limit)
        if isinstance(search_results, dict):
            results_list = search_results.get("results", [])
        elif isinstance(search_results, list):
            results_list = search_results
        else:
            results_list = []
        
        for item in results_list[:limit]:
            url = item.get("url", "") if isinstance(item, dict) else str(item)
            title = item.get("title", "") if isinstance(item, dict) else ""
            st = _classify_source_type(url, allowed_domains)
            candidates.append({
                "url": url,
                "title": title,
                "source_type": st,
                "provider_used": search_provider,
                "reason": f"matched domain {allowed_domains[0]}" if st == "official" else "third_party source",
            })
    except Exception as e:
        return BrowserResult(status="error", error_code="provider_failed", provider_used=search_provider,
                              message=f"search failed: {e}")

    if not candidates:
        return BrowserResult(status="error", error_code="no_search_results", provider_used=search_provider,
                              message="No candidates found")

    # Build output
    official = [c for c in candidates if c["source_type"] == "official"]
    obs_lines = ["Candidates:"]
    for c in candidates:
        obs_lines.append(f"  URL: {c['url'][:120]}")
        obs_lines.append(f"    Title: {c.get('title','')[:80]}")
        obs_lines.append(f"    Source type: {c['source_type']}")
        obs_lines.append(f"    Provider used: {c['provider_used']}")
        obs_lines.append(f"    Reason: {c.get('reason','')}")

    if official:
        wr_status, wr_ec = "ok", "ok"
    else:
        wr_status, wr_ec = "uncertain", "unverified_source"
        obs_lines.append("")
        obs_lines.append("Note: No official candidates found. Results may be third-party.")

    return BrowserResult(
        status=wr_status, error_code=wr_ec, provider_used=search_provider,
        message="\n".join(obs_lines),
        data={"candidates": candidates},
    )


def run_search_official(args: list[str]) -> BrowserResult:
    """Search for official documentation/website of a topic"""
    if "--query" not in " ".join(args[:3]):
        # Prepend the query if it's a simple string
        pass
    return run_search_candidates(args)


