#!/usr/bin/env python3
"""
browser — 浏览器常驻 TCP 服务 + CLI + 复合指令

用法（常用）:
  browser status|kill|restart|logs
  browser goto <url>
  browser click <id> | click_text <text> | fill <id> <text> | press [key]
  browser observe | screenshot [path] | read [--chars N]
  browser read_url <url> [--provider auto|browser|dokobot] [--chars N]
  browser search_read <query> [--result N] [--chars N]
  browser diagnose | diagnose_and_recover | close_popups
  browser wait_text <text> | assert_text <text> | click_expect <text> --expect <text>
  browser tabs | new_tab [url] | switch_tab <id> | close_tab [id]
  browser wait_selector <css> | wait_url <pattern> | scroll_into_view <css>
  browser click_role <role> [--name n] | click_label <label> | click_css <css>
  browser workflow_list|workflow_show|workflow_run|workflow_validate
  browser config_show|config_set|config_web|preset_list
  browser trace_list|trace_show <run_id>
"""

import sys, os, json, socket, time, threading, subprocess, re, atexit
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(__file__))
from browser_agent import step, reset_trace, get_trace
import browser_workflows as workflows



# timeout config
TIMEOUTS = {"default":30,"dokobot":90,"openvl":120,"images":180}

def get_timeout(name):
    env_key = f"BROWSER_TIMEOUT_{name.upper()}"
    if env_key in os.environ:
        return int(os.environ[env_key])
    return TIMEOUTS.get(name, TIMEOUTS["default"])

# Screenshot retention
_SCREENSHOT_DIR = Path(os.environ.get("TEMP", "/tmp"))
_SCREENSHOT_RETENTION_DAYS = int(os.environ.get("BROWSER_SCREENSHOT_RETENTION_DAYS", "7"))
_SCREENSHOT_MAX_FILES = int(os.environ.get("BROWSER_SCREENSHOT_MAX_FILES", "200"))

def _cleanup_screenshots(screenshot_dir=None):
    from datetime import datetime, timedelta
    now = datetime.now()
    cutoff = now - timedelta(days=_SCREENSHOT_RETENTION_DAYS)
    sdir = Path(screenshot_dir) if screenshot_dir else _SCREENSHOT_DIR
    files = sorted(sdir.glob("browser_*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
    # Remove old files
    for f in files:
        if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
            try: f.unlink()
            except OSError: pass
    # Enforce max files
    files = sorted(sdir.glob("browser_*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
    for f in files[_SCREENSHOT_MAX_FILES:]:
        try: f.unlink()
        except OSError: pass


# ===== Trace persistence =====

RUNS_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".pi")) / "Pi" / "browser" / "runs"
RUNS_DIR.mkdir(parents=True, exist_ok=True)

def _sanitize_run_id_part(s: str) -> str:
    """替换非法 Windows 路径字符，确保 run_id 安全"""
    import re
    # Windows 不允许: ? : / \ # & % = space
    # Unix 不允许: / NULL
    return re.sub(r'[?<>:*|"/\#&%= \t\n\r\x00]+', '_', str(s).strip())[:80]


def _write_trace(started_at, command, args, steps, status, error=None, summary=None, duration_ms=None):
    from datetime import datetime
    import time as _time
    monostart = _time.monotonic()
    run_id = f"{started_at.strftime('%Y%m%d_%H%M%S')}_{started_at.strftime('%f')[:3]}_{_sanitize_run_id_part(command)}"
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    ended_at = datetime.now()
    duration_ms = int((_time.monotonic() - monostart) * 1000)

    trace = sanitize({
        "started_at": started_at.isoformat(),
        "ended_at": ended_at.isoformat(),
        "duration_ms": duration_ms,
        "command": command,
        "args": args,
        "status": status,
        "steps": steps,
        "error": str(error) if error else None,
    })
    if duration_ms is not None:
        trace["duration_ms"] = duration_ms
    if summary:
        trace["summary"] = summary

    try:
        with open(run_dir / "trace.json", "w", encoding="utf-8") as f:
            json.dump(trace, f, ensure_ascii=False, indent=2)
    except Exception as _te:
        # Log but don't mask original error
        import sys as _sys
        print(f"trace_write_error: {_te}", file=_sys.stderr)

    return str(run_dir)

VALID_MODES = {"diagnose", "search", "ocr", "describe", "image_select"}
MODE_RESTRICTIONS = {
    "screenshot_ask": {"diagnose", "search", "ocr", "describe"},
    "ask_image": {"describe", "ocr", "image_select"},
    "image_page": {"image_select", "describe"},
}

def check_mode(cmd_name, mode):
    allowed = MODE_RESTRICTIONS.get(cmd_name)
    if allowed and mode not in allowed:
        print(f"invalid mode '{mode}' for {cmd_name}, allowed: {', '.join(sorted(allowed))}")
        sys.exit(1)


# api key redaction
_SENSITIVE_KEY_NAMES = {
    "api_key", "apikey", "api-key",
    "token", "access_token", "refresh_token",
    "secret", "password", "authorization", "auth",
}
_REDACT_PREFIXES = ["sk-", "Bearer "]

def _normalize_key(k):
    s = str(k)
    s = re.sub(r"(?<!^)(?=[A-Z])", "_", s).lower()  # camelCase to snake_case
    s = s.replace("-", "_").replace(" ", "_")
    return s

def _redact_str(s):
    if not isinstance(s, str):
        return s
    for p in _REDACT_PREFIXES:
        idx = s.find(p)
        while idx >= 0:
            end = s.find(" ", idx + len(p))
            if end < 0:
                end = len(s)
            s = s[:idx + len(p)] + "[REDACTED]" + s[end:]
            idx = s.find(p, idx + len(p) + len("[REDACTED]"))
    # URL query param redaction
    qpat = r"([?&])(" + "|".join(sorted(_SENSITIVE_KEY_NAMES, key=len, reverse=True)) + r")=([^&]+)"
    s = re.sub(qpat, r"\1\2=[REDACTED]", s, flags=re.IGNORECASE)
    return s

def _redact_obj(obj, depth=0):
    if depth > 20:
        return obj
    if isinstance(obj, dict):
        return {k: _redact_obj(v, depth+1) if _normalize_key(k) not in _SENSITIVE_KEY_NAMES else ("[REDACTED]" if v else v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact_obj(i, depth+1) for i in obj]
    if isinstance(obj, str):
        return _redact_str(obj)
    return obj

def sanitize(obj):
    """Unified entry: call before any output"""
    return _redact_obj(obj)

def _write_final_trace():
    global _last_trace
    if _last_trace and hasattr(print_result, "_trace_started"):
        _duration = _last_trace.get("_duration_ms", 0)
        from datetime import datetime
        started = print_result._trace_started
        steps = _last_trace.get("steps", []) or []
        wf = _last_trace.get("_wf_name", "") or _last_trace.get("recipe", "")
        args = _last_trace.get("action", {}).get("args", _last_trace.get("args", {}))
        cmd = _last_trace.get("action", {}).get("cmd", wf or "?")
        wr = _last_trace.get("_wr")
        summary = None
        if wr and isinstance(wr, dict):
            from tools.workflow_result import WorkflowResult
            try: summary = WorkflowResult(**wr).summary()
            except (TypeError, ValueError, KeyError): pass
        status = summary.get("status", "error") if summary else ("ok" if _last_trace.get("ok") else "error")
        _write_trace(started, cmd, args, steps, status=status,
                     error=_last_trace.get("error"), summary=summary,
                     duration_ms=_duration)

HOST, PORT = "127.0.0.1", 8765
BASE = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Pi" / "browser"
BASE.mkdir(parents=True, exist_ok=True)
LOG_PATH = BASE / "browser_daemon.log"
PID_PATH = BASE / "browser_daemon.pid"
DAEMON_SCRIPT = Path(__file__).resolve()


# ============ 工具 ============

def log(msg):
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")


def can_connect():
    try:
        s = socket.create_connection((HOST, PORT), timeout=1)
        s.close(); return True
    except OSError: return False


def _connect(timeout=30):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try: s.connect((HOST, PORT)); return s
    except OSError: return None


# ============ 服务端 ============

_step_lock = threading.Lock()

def serve():
    log("starting...")
    reset_trace()

    # 预热浏览器
    w = step("browser", "goto", {"url": "about:blank"})
    log(f"warmup: {'ok' if w.get('ok') else 'FAIL'}")

    PID_PATH.write_text(str(os.getpid()), encoding="utf-8")

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PORT))
    srv.listen(5)
    srv.settimeout(1)
    log(f"listening on {HOST}:{PORT}")

    while True:
        try:
            conn, _ = srv.accept()
            threading.Thread(target=_handle, args=(conn,), daemon=True).start()
        except socket.timeout: continue


def _handle(conn):
    with conn:
        data = b""
        while b"\n" not in data:
            b = conn.recv(4096)
            if not b: break
            data += b
        if not data: return
        try: req = json.loads(data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            conn.sendall(b'{"ok":false,"observation":"bad json"}\n'); return

        t = req.get("type", "cmd")
        if t == "ping":
            conn.sendall(b'{"ok":true,"type":"pong"}\n'); return
        if t == "kill":
            conn.sendall(b'{"ok":true}\n'); os._exit(0)
        if t == "trace":
            conn.sendall(json.dumps(get_trace(), ensure_ascii=False).encode() + b"\n"); return

        with _step_lock:
            wf = req.get("workflow", "")
            # Generate trace_id upfront
            from datetime import datetime as _dt
            _ts = _dt.now()
            _cmd_for_id = _sanitize_run_id_part(wf or req.get("cmd","unknown"))
            _run_id = f"{_ts.strftime('%Y%m%d_%H%M%S')}_{_ts.strftime('%f')[:3]}_{_cmd_for_id}"
            _t0 = time.monotonic()
            
            if wf:
                result = workflows.run(wf, req.get("args", {}))
                result["_wf_name"] = wf
                # Inject trace_id into _wr
                wr = result.get("_wr")
                if wr and hasattr(wr, "trace_id"):
                    wr.trace_id = _run_id
            else:
                result = _dispatch(req.get("recipe", ""), req.get("tool", "browser"),
                                   req.get("cmd", ""), req.get("args", {}))

        reply = _make_reply(result)
        conn.sendall(json.dumps(reply, ensure_ascii=False).encode() + b"\n")


def _dispatch(recipe, tool, cmd, args):
    if recipe:
        return _run_recipe(recipe, args)
    return step(tool, cmd, args)


def _run_recipe(name, args):
    """复合指令：展开为多个 step，不隐藏子步骤"""
    steps = []

    if name == "type_enter":
        steps.append(step("browser", "fill_id", {"id": int(args.get("id", 0)), "text": args.get("text", "")}))
        steps.append(step("browser", "press", {"key": "Enter"}))
        # press 后自动 observe

    elif name == "search_current":
        steps.append(step("browser", "fill_id", {"id": int(args.get("id", 0)), "text": args.get("query", "")}))
        steps.append(step("browser", "press", {"key": "Enter"}))

    elif name == "wiki":
        query = args.get("query", "")
        url = f"https://en.wikipedia.org/w/index.php?search={quote(query)}"
        steps.append(step("browser", "goto", {"url": url}))
        click = args.get("click", "")
        if click:
            steps.append(step("browser", "click_text", {"text": click}))

    elif name == "page":
        r = step("browser", "observe", {"snapshot": True, "text": True})
        steps.append(r)

    elif name == "read":
        max_chars = int(args.get("max_chars", 3000))
        r = step("browser", "extract_text", {"selector": "body"})
        if r.get("ok") and r.get("result"):
            r["result"]["text"] = (r["result"].get("text", "") or "")[:max_chars]
        steps.append(r)

    else:
        steps.append(step(tool, cmd, args))

    # 构造复合结果
    last = steps[-1] if steps else {}
    # 从 step 结果中提取页面信息（支持各种嵌套层级）
    po = last.get("post_observe") or {}
    if not po:
        r = last.get("result", {}) or {}
        if isinstance(r, dict):
            po = r
    if not po.get("url") and isinstance(last.get("result"), dict):
        r = last["result"]
        if isinstance(r, dict):
            po = r
    obs_lines = [f"Recipe: {name}"]
    # 调试信息
    for i, s in enumerate(steps):
        o = s.get("observation", "")
        obs_lines.append(f"  {i+1}. {o.split(chr(10))[0] if o else '?'}")
    obs_lines.append(f"Result: {'OK' if last.get('ok') else 'FAILED'}")

    return {
        "ok": last.get("ok", False),
        "recipe": name,
        "substeps": [{"cmd": s.get("action", {}).get("cmd", "?"), "ok": s.get("ok", False)} for s in steps],
        "_url": po.get("url", "") if isinstance(po, dict) else "",
        "_title": po.get("title", "") if isinstance(po, dict) else "",
        "_snapshot": po.get("snapshot", []) if isinstance(po, dict) else [],
        "observation": "\n".join(obs_lines),
    }


def _make_reply(result):
    # workflow 结果透传
    if result.get("_wf_name"):
        reply = {"ok": result.get("ok", False), "steps": result.get("steps", []),
                 "observation": result.get("observation", ""),
                 "_wf_name": result.get("_wf_name", ""),
                 "_url": result.get("_url", ""),
                 "_title": result.get("_title", ""),
                 "_text": result.get("_text", "")}
        sr = result.get("_search_results", [])
        if sr: reply["_search_results"] = sr
        els = result.get("_elements", [])
        if els: reply["_elements"] = els
        wr = result.get("_wr")
        if wr: reply["_wr"] = {"status": getattr(wr,"status","?"), "error_code": getattr(wr,"error_code","?"), "provider_used": getattr(wr,"provider_used","?"), "fallback_used": getattr(wr,"fallback_used",False), "trace_id": getattr(wr,"trace_id",None)} if not isinstance(wr, dict) else wr
        return reply

    obs = result.get("observation", "") or ""
    is_recipe = "recipe" in result and result["recipe"]
    po = result if is_recipe else (result.get("post_observe") or result.get("result", {}))

    reply = {"ok": result.get("ok", False)}
    if is_recipe:
        reply["recipe"] = result.get("recipe", "")
        reply["_substeps"] = result.get("substeps", [])
        reply["_recipe_obs"] = obs
        reply["observation"] = obs.split("\n")[0] if obs else ""
    else:
        reply["observation"] = obs.split("\n")[0] if obs else ""

    if isinstance(po, dict):
        u = po.get("_url", "") or po.get("url", "")
        t = po.get("_title", "") or po.get("title", "")
        reply["_url"] = u; reply["_title"] = t
        snap = po.get("_snapshot", []) or po.get("snapshot", [])
        reply["_elements"] = [
            {"id": e["id"], "text": (e.get("placeholder") or e.get("text") or "").strip()[:40]}
            for e in snap if e.get("visible") and (e.get("placeholder") or e.get("text") or "").strip()
        ][:5]
    # 透传 _wr result contract
    wr = result.get("_wr")
    if wr:
        if hasattr(wr, "status"):
            reply["_wr"] = {"status": getattr(wr,"status","?"), "error_code": getattr(wr,"error_code","?"), "provider_used": getattr(wr,"provider_used","?"), "fallback_used": getattr(wr,"fallback_used",False), "trace_id": getattr(wr,"trace_id",None)}
        else:
            reply["_wr"] = wr
    return reply


# ============ 客户端 ============

def _start_daemon():
    flags = subprocess.CREATE_NEW_PROCESS_GROUP
    if hasattr(subprocess, "DETACHED_PROCESS"):
        flags |= subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
    log_file = open(LOG_PATH, "a", encoding="utf-8")
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    # 用 pythonw.exe 避免控制台窗口
    py = sys.executable.replace("python.exe", "pythonw.exe")
    if not os.path.exists(py):
        py = sys.executable  # fallback
    subprocess.Popen(
        [py, str(DAEMON_SCRIPT), "--serve"],
        stdin=subprocess.DEVNULL, stdout=log_file, stderr=log_file,
        env=env, creationflags=flags, close_fds=True,
    )
    for _ in range(20):
        time.sleep(0.5)
        if can_connect(): return True
    return False


def _send(tool, cmd, args):
    s = _connect()
    if not s:
        print("starting daemon...", file=sys.stderr)
        if not _start_daemon(): print("failed"); sys.exit(1)
        s = _connect()
        if not s: print("unreachable"); sys.exit(1)
    req = json.dumps({"type": "cmd", "tool": tool, "cmd": cmd, "args": args}) + "\n"
    s.sendall(req.encode())
    f = s.makefile("r", encoding="utf-8")
    line = f.readline()
    s.close()
    return json.loads(line) if line else None


def _send_recipe(name, args):
    s = _connect()
    if not s:
        print("starting daemon...", file=sys.stderr)
        if not _start_daemon(): print("failed"); sys.exit(1)
        s = _connect()
        if not s: print("unreachable"); sys.exit(1)
    req = json.dumps({"type": "cmd", "recipe": name, "args": args}) + "\n"
    s.sendall(req.encode())
    f = s.makefile("r", encoding="utf-8")
    line = f.readline()
    s.close()
    return json.loads(line) if line else None


def _send_workflow(name, args):
    s = _connect()
    if not s:
        print("starting daemon...", file=sys.stderr)
        if not _start_daemon(): print("failed"); sys.exit(1)
        s = _connect()
        if not s: print("unreachable"); sys.exit(1)
    req = json.dumps({"type": "cmd", "workflow": name, "args": args}) + "\n"
    s.sendall(req.encode())
    f = s.makefile("r", encoding="utf-8")
    line = f.readline()
    s.close()
    return json.loads(line) if line else None


_last_trace = None

def print_result(r):
    global _last_trace
    # Write trace
    if r and isinstance(r, dict):
        from datetime import datetime
        if not hasattr(print_result, "_trace_started"):
            print_result._trace_started = datetime.now()
        _last_trace = r
    if not r: print("no response"); return


    # workflow result contract
    if r.get("_wr"):
        wr = r.get("_wr")
        if isinstance(wr, dict):
            raw_status = wr.get("status","?")
            if raw_status == "blocked":
                raw_status = "error"
            print(f"Status: {raw_status}")
            print(f"Error code: {wr.get('error_code','?')}")
            print(f"Provider used: {wr.get('provider_used','?')}")
            print(f"Fallback used: {'yes' if wr.get('fallback_used') else 'no'}")
            tid = wr.get("trace_id") or ""
            if tid: print(f"Trace: {tid}")
        if r.get("_url"): print(f"URL: {r.get('_url')}")
        if r.get("_title"): print(f"Title: {r.get('_title')}")
        t = r.get("_text", "")
        if t: print(chr(10) + "Text:" + chr(10) + t[:2000])
        return

    if r.get("steps"):
        print(f"Workflow: {r.get('_wf_name','?')}")
        print(r.get("observation", ""))
        u, t = r.get("_url", ""), r.get("_title", "")
        if u: print(f"\nURL: {u}")
        if t: print(f"Title: {t}")
        text = r.get("_text", "")
        if text:
            print(f"\nText:")
            print(text[:2000])
        els = r.get("_elements", [])
        if els:
            for e in els: print(e)
        sr = r.get("_search_results", [])
        if sr:
            text = r.get("_text", "")
            if text: print(text)
        return

    # recipe 结果
    if r.get("recipe"):
        print(r.get("_recipe_obs", r.get("observation", "")))
        u, t = r.get("_url", ""), r.get("_title", "")
        if u: print(f"  {t[:70] if t else ''} @ {u[:90]}")
        for e in r.get("_elements", []):
            print(f"  [{e['id']}] {e['text']}")
        return

    # 原子命令结果
    print(f"  {r.get('observation','')}")
    u, t = r.get("_url", ""), r.get("_title", "")
    if u: print(f"  {t[:70] if t else ''} @ {u[:90]}")
    for e in r.get("_elements", []):
        print(f"  [{e['id']}] {e['text']}")
        print(f"  [{e['id']}] {e['text']}")


# ============ CLI ============


def _cmd_trace_list():
    from pathlib import Path
    import os
    d = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".pi")) / "Pi" / "browser" / "runs"
    if not d.exists() or not any(d.iterdir()):
        print("no traces found"); return
    runs = sorted(d.iterdir(), reverse=True)[:20]
    for r in runs:
        tf = r / "trace.json"
        if tf.exists():
            import json
            data = sanitize(json.loads(tf.read_text(encoding="utf-8")))
            s = data.get("summary", {})
            print(f"  {r.name}")
            print(f"    Status: {s.get('status','?')}  Error: {s.get('error_code','?')}  Provider used: {s.get('provider_used','?')}  Fallback used: {'yes' if s.get('fallback_used') else 'no'}  Duration: {data.get('duration_ms',0)}ms")
            print()


def _cmd_trace_show(run_id):
    from pathlib import Path
    import os
    d = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".pi")) / "Pi" / "browser" / "runs"
    rd = d / run_id
    tf = rd / "trace.json"
    if not tf.exists():
        print(f"trace not found: {run_id}"); return
    import json
    data = sanitize(json.loads(tf.read_text(encoding="utf-8")))
    s = data.get("summary", {})
    print(f"Run ID: {run_id}")
    print(f"Command: {data.get('command','?')}")
    print(f"Status: {s.get('status','?')}  Error code: {s.get('error_code','?')}")
    print(f"Provider used: {s.get('provider_used','?')}  Fallback used: {'yes' if s.get('fallback_used') else 'no'}")
    print(f"Started: {data.get('started_at','?')}  Ended: {data.get('ended_at','?')}  Duration: {data.get('duration_ms',0)}ms")
    print(f"URL: {s.get('url','')}  Title: {s.get('title','')}")
    err = data.get("error")
    if err: print(f"Error: {err}")
    wf = data.get("workflow", {})
    wf_steps = wf.get("steps", []) if wf else []
    child_ids = data.get("child_ids", [])
    if wf_steps:
        print("Workflow: " + str(wf.get("name","?")))
        print("Steps:")
        for idx, st in enumerate(wf_steps, 1):
            print(f"  {idx}. {st.get('id','?')}")
            print("     Action: " + str(st.get("action","?")))
            print("     Status: " + ("OK" if st.get("ok") else "FAIL") + "  Error code: " + str(st.get("error_code","?")))
            pu = st.get("provider_used","")
            fb = st.get("fallback_used",False)
            print("     Provider used: " + (pu if pu else "none"))
            print("     Fallback used: " + ("yes" if fb else "no"))
            print("     Child trace: " + (st.get("child_trace","") or ""))
    else:
        steps = data.get("steps", [])
        if steps: print(f"Steps: {len(steps)}")
        for st in steps[:5]:
            print(f"  {st.get('index','')}. {st.get('cmd','?')} -> {'OK' if st.get('ok') else 'FAIL'}")

    return

def _positional_or_default(rest, index, default="3000"):
    """Return rest[index] only if it is a real value, not a CLI flag like --chars."""
    if len(rest) <= index:
        return default
    val = rest[index]
    if val is None:
        return default
    s = str(val).strip()
    if not s or s.startswith("--"):
        return default
    return s

def _parse(args):
    if not args: return None
    c, r = args[0], args[1:]
    if c == "reset":
        return ("browser", "reset", {})
    if c == "close":
        return ("browser", "close", {})
    if c == "goto":
        return ("browser", "goto", {"url": r[0] if r else ""})
    if c == "click":
        return ("browser", "click_id", {"id": int(r[0]) if r else 0})
    if c == "fill":
        return ("browser", "fill_id", {"id": int(r[0]) if r else 0, "text": " ".join(r[1:])})
    if c == "press":
        return ("browser", "press", {"key": r[0] if r else "Enter"})
    if c == "click_text":
        return ("browser", "click_text", {"text": " ".join(r)})
    if c == "observe":
        return ("browser", "observe", {"snapshot": True, "text": True})
    if c == "screenshot":
        return ("browser", "screenshot", {"path": r[0] if r else "/tmp/browser_screenshot.png"})
    if c == "scroll":
        return ("browser", "scroll", {"y": int(r[0]) if r else 300})
    return None

def main():
    args = sys.argv[1:]


    # 管理命令
    if args[0] == "--serve": serve(); return

    if args[0] == "status":
        s = _connect()
        if s:
            s.sendall(b'{"type":"ping"}\n')
            r = s.makefile("r", encoding="utf-8").readline()
            s.close()
            pid = PID_PATH.read_text(encoding="utf-8").strip() if PID_PATH.exists() else "?"
            print(f"daemon running (pid {pid})")
        else:
            print("daemon not running")
        return

    if args[0] == "kill":
        s = _connect()
        if s:
            s.sendall(b'{"type":"kill"}\n'); s.close()
            time.sleep(0.5)
        try:
            if PID_PATH.exists():
                pid = int(PID_PATH.read_text().strip())
                os.kill(pid, 9)
        except (OSError, ValueError): pass
        PID_PATH.unlink(missing_ok=True)
        print("daemon killed")
        return

    if args[0] == "restart":
        s = _connect()
        if s:
            s.sendall(b'{"type":"kill"}\n'); s.close()
        time.sleep(0.5)
        if _start_daemon():
            print("daemon restarted")
        else:
            print("restart failed")
        return

    if args[0] == "logs":
        if LOG_PATH.exists():
            lines = LOG_PATH.read_text(encoding="utf-8").splitlines()
            print("\n".join(lines[-80:]))
        else:
            print("no logs")
        return

    if args[0] == "trace":
        s = _connect()
        if not s: print("daemon not running"); return
        s.sendall(b'{"type":"trace"}\n')
        f = s.makefile("r", encoding="utf-8")
        print(f.readline() or "empty"); s.close()
        return

    # config commands (via cli_dispatch)
    from tools.cli_dispatch import dispatch, _ensure_trace
    from tools.render import render_text
    handled = {"config_path", "config_show", "config_validate", "config_set",
               "preset_list", "preset_show", "preset_use", "workflow_validate",
               "config_web", "config_web_status", "config_web_stop",
               "search_candidates", "search_official"}
    if args[0] in handled:
        result = _ensure_trace(dispatch(args), args[0])
        print(render_text(result))
        return

    # workflow commands (via cli_dispatch)
    from tools.cli_dispatch import dispatch as _dispatch
    from tools.cli_dispatch import _ensure_trace as _ensure
    from tools.render import render_text as _render
    wf_handled = {"workflow_list", "workflow_show", "workflow_run", "trace_list", "trace_show", "read_urls_parallel",
                  "tabs", "new_tab", "switch_tab", "close_tab",
                  "wait_selector", "wait_url", "scroll_into_view",
                  "click_role", "click_label", "click_css"}
    if args[0] in wf_handled:
        result = _ensure(_dispatch(args), args[0])
        print(_render(result))
        return
        specs = []
        for name in list_workflows():
            spec = load_spec(name)
            desc = (spec.get("description","").split('.')[0][:60] if spec else "")
            inputs = ", ".join(i.get("name","") for i in (spec.get("inputs",[]) if spec else []))
            ex = f"browser workflow_run {name}"
            if inputs: ex += f" --var {inputs.split(',')[0].strip()}=..."
            print(f"  {name}")
            print(f"    Purpose: {desc}")
            if inputs: print(f"    Inputs: {inputs}")
            print(f"    Example: {ex}")
            print()
        return
    if args[0] == "workflow_show":
        from tools.workflow_runner import show_workflow, load_spec, list_workflows
        name = args[1] if len(args) > 1 else ""
        if name not in list_workflows():
            print(f"Status: error")
            print(f"Error code: not_found")
            print(f"Message: workflow not found: {name}")
            return
        content = show_workflow(name)
        if content:
            print(content)
        spec = load_spec(name)
        if spec:
            print("---")
            print(f"Name: {spec.get('name','?')}")
            print(f"Description: {spec.get('description','?')}")
            inputs = spec.get("inputs", [])
            if inputs:
                print(f"Required inputs: {', '.join(i.get('name','?') for i in inputs if i.get('required',True))}")
            print("Steps:")
            ex_inputs = ", ".join(i.get("name","?")+"=..." for i in inputs[:2])
            print(f"Example: browser workflow_run {name} --var {ex_inputs}" if ex_inputs else f"Example: browser workflow_run {name}")
        return
    if args[0] == "workflow_run":
        name = args[1] if len(args) > 1 else ""
        rest = args[2:]
        inputs = {}
        i = 0
        while i < len(rest):
            if rest[i] == "--input" or rest[i] == "-i":
                import json
                try:
                    fp = rest[i+1] if i+1 < len(rest) else ""
                    with open(fp, "r", encoding="utf-8") as f:
                        inputs = json.load(f)
                except Exception as e:
                    print(f"read input failed: {e}")
                    return
                i += 2; continue
            if rest[i] == "--var" or rest[i] == "-v":
                if i+1 < len(rest) and "=" in rest[i+1]:
                    k, v = rest[i+1].split("=", 1)
                    inputs[k] = v
                i += 2; continue
            i += 1
        from tools.workflow_runner import run as run_workflow
        result = run_workflow(name, inputs)
        wr = result.get("_wr")
        tid = result.get("trace_id", "")
        msg = result.get("observation", "")
        if isinstance(wr, dict):
            s = wr.get("status","?")
            ec = wr.get("error_code","?")
            pu = wr.get("provider_used","?")
            fb = wr.get("fallback_used",False)
            print(f"Status: {s}")
            print(f"Error code: {ec}")
            print(f"Provider used: {pu}")
            print(f"Fallback used: {'yes' if fb else 'no'}")
            if tid: print(f"Trace: {tid}")
        elif wr:
            s = wr.status if hasattr(wr,"status") else "?"
            ec = wr.error_code if hasattr(wr,"error_code") else "?"
            pu = wr.provider_used if hasattr(wr,"provider_used") else "?"
            fb = wr.fallback_used if hasattr(wr,"fallback_used") else False
            print(f"Status: {s}")
            print(f"Error code: {ec}")
            print(f"Provider used: {pu}")
            print(f"Fallback used: {'yes' if fb else 'no'}")
            if tid: print(f"Trace: {tid}")
        if msg:
            print()
            if msg.startswith("missing required"):
                print("Message: " + msg)
            else:
                print(msg)
        return

    # workflow 命令
    rest = args[1:]
    if args[0] == "read":
        chars = "3000"
        if rest:
            if rest[0] == "--chars" and len(rest) > 1:
                chars = rest[1]
            else:
                chars = _positional_or_default(rest, 0, "3000")
        r = _send_workflow("read", {"chars": chars})
        print_result(r); return
    if args[0] == "open":
        r = _send_workflow("open", {"url": rest[0] if rest else ""})
        print_result(r); return
    if args[0] == "current":
        r = _send_workflow("current", {})
        print_result(r); return
    if args[0] == "article":
        url = rest[0] if rest else ""
        # support: article <url> --chars N  OR article <url> <chars>
        mc = "3000"
        if len(rest) > 1:
            if rest[1] == "--chars" and len(rest) > 2:
                mc = rest[2]
            else:
                mc = _positional_or_default(rest, 1, "3000")
        r = _send_workflow("article", {"url": url, "chars": mc})
        print_result(r); return
    if args[0] == "search":
        r = _send_workflow("search", {"query": " ".join(rest)})
        print_result(r); return
    if args[0] == "open_result":
        n = rest[0] if rest else "1"
        r = _send_workflow("open_result", {"result": n, "n": n})
        print_result(r); return
    if args[0] == "search_read":
        result_n = 1; chars_n = 3000; query_parts = []
        i = 0
        while i < len(rest):
            if rest[i] == "--result":
                result_n = int(rest[i+1]) if i+1 < len(rest) else 1; i += 2; continue
            if rest[i] == "--chars":
                chars_n = int(rest[i+1]) if i+1 < len(rest) else 3000; i += 2; continue
            query_parts.append(rest[i]); i += 1
        r = _send_workflow("search_read", {"query": " ".join(query_parts), "result": result_n, "n": result_n, "chars": chars_n})
        print_result(r); return
    if args[0] == "wiki_read":
        chars_n = 3000; query_parts = []
        i = 0
        while i < len(rest):
            if rest[i] == "--chars":
                chars_n = int(rest[i+1]) if i+1 < len(rest) else 3000; i += 2; continue
            query_parts.append(rest[i]); i += 1
        r = _send_workflow("wiki_read", {"query": " ".join(query_parts), "chars": chars_n})
        print_result(r); return
    if args[0] == "wiki_click_read":
        click = ""; chars_n = 3000; query_parts = []
        i = 0
        while i < len(rest):
            if rest[i] == "--click":
                click = " ".join(rest[i+1:]); break
            if rest[i] == "--chars":
                chars_n = int(rest[i+1]) if i+1 < len(rest) else 3000; i += 2; continue
            query_parts.append(rest[i]); i += 1
        r = _send_workflow("wiki_click_read", {"query": " ".join(query_parts), "click": click, "chars": chars_n})
        print_result(r); return
    # new provider workflows
    if args[0] == "doko_read":
        url = rest[0] if rest else ""
        chars = "3000"
        if len(rest) > 1:
            if rest[1] == "--chars" and len(rest) > 2:
                chars = rest[2]
            else:
                chars = _positional_or_default(rest, 1, "3000")
        r = _send_workflow("doko_read", {"url": url, "chars": chars})
        print_result(r); return
    if args[0] == "images":
        url = rest[0] if rest else ""
        r = _send_workflow("images", {"url": url})
        print_result(r); return
    if args[0] == "image_page":
        url = rest[0] if rest else ""
        limit = 3; describe = False; question = ""; i = 1
        while i < len(rest):
            if rest[i] == "--limit": limit = int(rest[i+1]) if i+1 < len(rest) else 3; i += 2; continue
            if rest[i] == "--describe": describe = True; i += 1; continue
            if rest[i] == "--question": question = " ".join(rest[i+1:]); break
            i += 1
        r = _send_workflow("image_page", {"url": url, "limit": limit, "describe": describe, "question": question})
        print_result(r); return
    if args[0] == "diagnose":
        q = " ".join(rest) if rest else ""
        r = _send_workflow("diagnose", {"question": q})
        print_result(r); return
    if args[0] == "ask_image":
        img = rest[0] if rest else ""
        q = ""; mode = "describe"; i = 1
        while i < len(rest):
            if rest[i] == "--mode": mode = rest[i+1] if i+1 < len(rest) else "describe"; check_mode("ask_image", mode); i += 2; continue
            q += " " + rest[i]; i += 1
        r = _send_workflow("ask_image", {"path": img, "question": q.strip(), "mode": mode})
        print_result(r); return
    if args[0] == "screenshot_ask":
        q = ""; mode = "diagnose"; i = 0
        while i < len(rest):
            if rest[i] == "--mode": mode = rest[i+1] if i+1 < len(rest) else "diagnose"; check_mode("screenshot_ask", mode); i += 2; continue
            q += " " + rest[i]; i += 1
        r = _send_workflow("screenshot_ask", {"question": q.strip(), "mode": mode})
        print_result(r); return
    if args[0] == "visual_search_check":
        q = " ".join(rest) if rest else ""
        r = _send_workflow("visual_search_check", {"goal": q, "question": q})
        print_result(r); return

    # compound workflow commands
    rest = args[1:]
    if args[0] == "read_url":
        url = rest[0] if rest else ""
        provider = "auto"; chars = "1000"; i = 1
        while i < len(rest):
            if rest[i] == "--provider": provider = rest[i+1] if i+1 < len(rest) else "auto"; i += 2; continue
            if rest[i] == "--chars": chars = rest[i+1] if i+1 < len(rest) else "1000"; i += 2; continue
            i += 1
        r = _send_workflow("read_url", {"url": url, "provider": provider, "chars": chars})
        print_result(r); return
    if args[0] == "close_popups":
        r = _send_workflow("close_popups", {})
        print_result(r); return
    if args[0] == "diagnose_and_recover":
        r = _send_workflow("diagnose_and_recover", {})
        print_result(r); return
    if args[0] == "wait_text":
        text = rest[0] if rest else ""
        timeout = "10"; i = 1
        while i < len(rest):
            if rest[i] == "--timeout": timeout = rest[i+1] if i+1 < len(rest) else "10"; i += 2; continue
            i += 1
        r = _send_workflow("wait_text", {"text": text, "timeout": timeout})
        print_result(r); return
    if args[0] == "assert_text":
        r = _send_workflow("assert_text", {"text": " ".join(rest)})
        print_result(r); return
    if args[0] == "click_expect":
        click_text = ""; expect_text = ""; timeout = "10"; i = 0
        while i < len(rest):
            if rest[i] == "--expect": expect_text = " ".join(rest[i+1:]); break
            if rest[i] == "--timeout": timeout = rest[i+1] if i+1 < len(rest) else "10"; i += 2; continue
            click_text += " " + rest[i]; i += 1
        r = _send_workflow("click_expect", {"click_text": click_text.strip(), "expect": expect_text, "timeout": timeout})
        print_result(r); return
    if args[0] == "trace_list":
        _cmd_trace_list(); return
    if args[0] == "trace_show":
        run_id = rest[0] if rest else ""
        _cmd_trace_show(run_id); return

    # 复合指令
    # 复合指令
    if args[0] == "type_enter":
        r = _send_recipe("type_enter", {"id": rest[0] if rest else "0", "text": " ".join(rest[1:])})
        print_result(r); return
    if args[0] == "search_current":
        r = _send_recipe("search_current", {"id": rest[0] if rest else "0", "query": " ".join(rest[1:])})
        print_result(r); return
    if args[0] == "wiki":
        # 解析 --click <text>
        click = ""
        query_parts = []
        i = 0
        while i < len(rest):
            if rest[i] == "--click":
                click = " ".join(rest[i+1:])
                break
            query_parts.append(rest[i])
            i += 1
        r = _send_recipe("wiki", {"query": " ".join(query_parts), "click": click})
        print_result(r); return
    if args[0] == "read":
        mc = rest[0] if rest else "3000"
        r = _send_recipe("read", {"max_chars": mc})
        print_result(r); return
    if args[0] == "page":
        r = _send_recipe("page", {})
        print_result(r); return

    # 原子命令
    parsed = _parse(args)
    if not parsed: print(__doc__); sys.exit(1)
    r = _send(*parsed)
    # Auto-recovery: if command failed with navigation error, reset page
    if r and isinstance(r, dict) and not r.get("ok"):
        err = r.get("observation", "") or ""
        if any(kw in err.lower() for kw in ["navigation", "timeout", "goto"]):
            _send("browser", "reset", {})
    print_result(r)

atexit.register(_write_final_trace)


if __name__ == "__main__":
    main()
