#!/usr/bin/env python3
"""workflow_runner.py — v2.7.0 可配置工作流执行器"""
import sys, os, json, yaml, time
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from browser_workflows import run as run_workflow
from tools.workflow_result import WorkflowResult
from browser_daemon import sanitize

BASE = Path(os.path.dirname(os.path.dirname(__file__)))
SPECS_DIR = BASE / "workflow_specs"
WORKFLOWS_DIR = BASE / "workflows"
RUNS_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".pi")) / "Pi" / "browser" / "runs"

ALLOWED_ACTIONS = {
    "read_url", "search_read", "diagnose", "diagnose_and_recover",
    "wait_text", "assert_text", "click_expect", "screenshot_ask",
}


def list_workflows():
    return sorted(f.stem for f in SPECS_DIR.glob("*.yaml"))


def show_workflow(name):
    md = WORKFLOWS_DIR / f"{name}.md"
    if md.exists():
        return md.read_text(encoding="utf-8")
    spec = SPECS_DIR / f"{name}.yaml"
    if spec.exists():
        return spec.read_text(encoding="utf-8")
    return None


def load_spec(name):
    spec_path = SPECS_DIR / f"{name}.yaml"
    if not spec_path.exists():
        return None
    with open(spec_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _substitute(text, variables):
    if not isinstance(text, str):
        return text
    for k, v in variables.items():
        text = text.replace("{" + k + "}", str(v))
    return text


def _substitute_args(args, variables):
    result = {}
    for k, v in args.items():
        if isinstance(v, str):
            result[k] = _substitute(v, variables)
        elif isinstance(v, dict):
            result[k] = _substitute_args(v, variables)
        elif isinstance(v, list):
            result[k] = [_substitute(i, variables) if isinstance(i, str) else i for i in v]
        else:
            result[k] = v
    return result


def _extract_wr(result):
    """Extract WorkflowResult-like dict from action result"""
    wr = result.get("_wr")
    if isinstance(wr, dict):
        return wr
    if wr and hasattr(wr, "error_code"):
        return {"error_code": wr.error_code, "provider_used": getattr(wr, "provider_used", ""),
                "fallback_used": getattr(wr, "fallback_used", False), "status": getattr(wr, "status", "?")}
    return {}


def _source_type(url, title):
    """Simple source type classification"""
    if not url and not title:
        return "unknown"
    url_lower = (url or "").lower()
    title_lower = (title or "").lower()
    if any(d in url_lower for d in ["github.com", ".docs", "docs.", "playwright.dev",
                                      "react.dev", "angular.io", "vuejs.org",
                                      "python.org", "nodejs.org", "npmjs.com"]):
        return "official"
    if any(k in title_lower for k in ["official", "documentation", "docs"]):
        return "official"
    if any(d in url_lower for d in ["runoob.com", "w3schools", "geeksforgeeks",
                                      "medium.com", "blog.", "tutorial"]):
        return "third_party"
    return "unknown"


def run(name, inputs):
    """Execute a workflow by name. Returns dict with _wr and writes parent trace."""
    started_at = datetime.now()
    t0 = time.monotonic()

    spec = load_spec(name)
    if not spec:
        return {"ok": False, "error": f"workflow not found: {name}"}
    if "steps" not in spec or not spec["steps"]:
        return {"ok": False, "error": "workflow has no steps"}

    variables = dict(inputs)
    # Validate required inputs
    required = [i["name"] for i in spec.get("inputs", []) if i.get("required", True)]
    for r in required:
        if r not in variables or not variables[r]:
            _run_id = f"{started_at.strftime('%Y%m%d_%H%M%S')}_{started_at.strftime('%f')[:3]}_workflow_run_{name}"
            _run_dir = RUNS_DIR / _run_id
            _run_dir.mkdir(parents=True, exist_ok=True)
            _trace = {"started_at": started_at.isoformat(), "ended_at": datetime.now().isoformat(),
                      "duration_ms": int((time.monotonic() - t0) * 1000), "command": f"workflow_run_{name}",
                      "status": "error", "error_code": "invalid_input",
                      "workflow": {"name": name, "steps": []},
                      "summary": {"status": "error", "error_code": "invalid_input",
                                  "provider_used": "none", "fallback_used": False, "trace_id": _run_id}}
            with open(_run_dir / "trace.json", "w", encoding="utf-8") as _f:
                json.dump(sanitize(_trace), _f, ensure_ascii=False, indent=2)
            wr = WorkflowResult(status="error", error_code="invalid_input", provider_used="none", trace_id=_run_id,
                                message=f"missing required input: {r}")
            return {"ok": False, "_wr": wr, "observation": f"missing required input: {r}", "trace_id": _run_id}

    # Expand steps (handle foreach)
    steps = []
    has_foreach = any("foreach" in s for s in spec["steps"])
    if has_foreach:
        for s in spec["steps"]:
            if "foreach" in s:
                foreach_list = variables.get(s["foreach"], [])
                if isinstance(foreach_list, str):
                    foreach_list = [x.strip() for x in foreach_list.split(",")]
                for idx, item in enumerate(foreach_list):
                    loop_vars = dict(variables)
                    loop_vars[s["as"]] = item
                    loop_vars["item_index"] = idx + 1
                    step = dict(s)
                    step.pop("foreach", None); step.pop("as", None)
                    step["args"] = _substitute_args(step.get("args", {}), loop_vars)
                    step["save_as"] = _substitute(step.get("save_as", ""), loop_vars)
                    steps.append(step)
            else:
                s["args"] = _substitute_args(s.get("args", {}), variables)
                steps.append(s)
    else:
        for s in spec["steps"]:
            s["args"] = _substitute_args(s.get("args", {}), variables)
            steps.append(s)

    # Execute steps
    saved = {}
    step_results = []
    all_ok = True
    all_providers = set()
    any_fallback = False

    for s in steps:
        action = s.get("action", "")
        if action not in ALLOWED_ACTIONS:
            step_results.append({"id": s.get("id", action), "action": action, "ok": False, "error_code": "invalid_mode"})
            all_ok = False
            break

        result = run_workflow(action, s.get("args", {}))
        wr = _extract_wr(result)
        ec = wr.get("error_code", "unknown")
        pu = wr.get("provider_used", "")
        fb = wr.get("fallback_used", False)
        if pu: all_providers.add(pu)
        if fb: any_fallback = True

        sr = {"id": s.get("id", action), "action": action, "ok": result.get("ok", False), "error_code": ec, "provider_used": pu, "fallback_used": fb}
        step_results.append(sr)

        if not result.get("ok"):
            all_ok = False
            step_on_error = s.get("on_error", "stop")
            if step_on_error == "stop":
                break

        save_key = s.get("save_as", "")
        if save_key:
            src_type = _source_type(result.get("_url", ""), result.get("_title", ""))
            saved[save_key] = {
                "ok": result.get("ok", False),
                "url": result.get("_url", ""),
                "title": result.get("_title", ""),
                "text": (result.get("_text", "") or "")[:500],
                "error_code": ec,
                "source_type": src_type,
            }
            saved[save_key + ".url"] = result.get("_url", "")
            saved[save_key + ".text"] = (result.get("_text", "") or "")[:500]
            saved[save_key + ".title"] = result.get("_title", "")

    # Aggregate status/error_code
    wf_ok = all(step["ok"] for step in step_results)
    if wf_ok:
        wf_status, wf_ec = "ok", "ok"
    else:
        first_bad = None
        for sr in step_results:
            if not sr["ok"]:
                first_bad = sr.get("error_code", "unknown")
                break
        wf_ec = first_bad or "unknown"
        stopped_early = len(step_results) < len(steps)
        if stopped_early:  # on_error=stop case
            wf_status = "error"
        else:  # on_error=continue case
            wf_status = "uncertain"

    provider_used = "mixed" if len(all_providers) > 1 else (next(iter(all_providers)) if all_providers else "none")
    fallback_used = any_fallback

    # Generate trace_id and write parent trace
    run_id = f"{started_at.strftime('%Y%m%d_%H%M%S')}_{started_at.strftime('%f')[:3]}_workflow_run_{name}"
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    duration_ms = int((time.monotonic() - t0) * 1000)

    trace = {
        "started_at": started_at.isoformat(),
        "ended_at": datetime.now().isoformat(),
        "duration_ms": duration_ms,
        "command": f"workflow_run_{name}",
        "status": wf_status,
        "error_code": wf_ec,
        "workflow": {"name": name, "steps": step_results},
        "summary": {
            "status": wf_status, "error_code": wf_ec,
            "provider_used": provider_used, "fallback_used": fallback_used,
            "trace_id": run_id,
        },
    }
    # Sanitize before writing
    with open(run_dir / "trace.json", "w", encoding="utf-8") as f:
        json.dump(sanitize(trace), f, ensure_ascii=False, indent=2)

    # research_official: downgrade if no official source found
    if name == "research_official" and saved and not any(v.get("source_type") == "official" for v in saved.values() if isinstance(v, dict)):
        wf_status = "uncertain"
        wf_ec = "unverified_source"

    final_fallback = any_fallback
    wr_obj = WorkflowResult(
        status=wf_status, error_code=wf_ec, provider_used=provider_used,
        fallback_used=final_fallback, trace_id=run_id,
        data={"workflow": name, "steps": step_results, "saved": {k: v for k, v in saved.items() if isinstance(v, dict) and not k.endswith(".url") and not k.endswith(".text")}},
    )

    # Build observation with Sources
    obs_lines = [f"Workflow: {name}"]
    for sr in step_results:
        obs_lines.append(f"  {sr['id']}: {sr['action']} -> {'OK' if sr['ok'] else 'FAIL'} [{sr['error_code']}]")
    if saved:
        obs_lines.append("")
        obs_lines.append("Sources:")
        for key, val in saved.items():
            if isinstance(val, dict) and not key.endswith(".url") and not key.endswith(".text"):
                t = val.get("title", "") or ""
                u = val.get("url", "") or ""
                ec = val.get("error_code", "") or ""
                st = val.get("source_type", "") or ""
                snippet = (val.get("text", "") or "")[:300]
                if t: obs_lines.append(f"  Title: {t}")
                if u: obs_lines.append(f"  URL: {u}")
                if ec: obs_lines.append(f"  Error code: {ec}")
                if st: obs_lines.append(f"  Source type: {st}")
                if snippet: obs_lines.append(f"  Snippet: {snippet[:200]}")
                obs_lines.append("")
    obs_lines.append(f"Result: {'All steps completed' if wf_ok else 'Completed with issues'}")

    ok = wf_status == "ok"
    return {"ok": ok, "_wr": wr_obj, "steps": step_results,
            "observation": "\n".join(obs_lines), "_url": "", "_title": "", "_text": "",
            "trace_id": run_id}
