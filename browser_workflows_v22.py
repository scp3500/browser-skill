#!/usr/bin/env python3
"""browser_workflows_v22.py — v2.2 new workflows (read_url, close_popups, etc.)"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from browser_agent import step
from tools.workflow_result import WorkflowResult

# Import helpers from main workflows module
import browser_workflows as bw
_run_dokobot = bw._run_dokobot
_run_openvl = bw._run_openvl
_inject_header = bw._inject_header
wf_diagnose = bw.wf_diagnose


def wf_read_url(args, ctx=None):
    url = args.get("url", "")
    chars = int(args.get("chars", args.get("max_chars", "1000")))
    provider = args.get("provider", "auto")
    attempts = []

    def _dokobot_read(u, ch):
        r = _run_dokobot("read", {"url": u})
        ok = r.get("ok")
        txt = (r.get("result", {}).get("text", "") or "")[:ch] if ok else ""
        return ok, txt

    def _browser_read(u, ch):
        r1 = step("browser", "goto", {"url": u})
        if not r1.get("ok"):
            return False, ""
        r2 = step("browser", "extract_text", {"selector": "body"})
        txt = (r2.get("result", {}).get("text", "") or "")[:ch] if r2.get("ok") else ""
        return r2.get("ok", False) and bool(txt.strip()), txt

    if provider == "dokobot":
        ok, text = _dokobot_read(url, chars)
        attempts.append({"provider": "dokobot", "status": "ok" if ok else "error",
                         "error_code": "ok" if ok else "read_failed"})
        wr = WorkflowResult(status="ok" if ok else "error",
                            error_code="ok" if ok else "read_failed",
                            provider_used="dokobot", url=url, text=text,
                            data={"attempts": attempts})
        return {"ok": ok, "steps": [{"index": 1, "cmd": "read_url", "ok": ok}],
                "_wr": wr, "_url": url, "_text": text}

    if provider == "browser":
        ok, text = _browser_read(url, chars)
        attempts.append({"provider": "browser", "status": "ok" if ok else "error",
                         "error_code": "ok" if ok else "network_error" if not text else "read_failed"})
        wr = WorkflowResult(status="ok" if ok else "error",
                            error_code="ok" if ok else ("read_failed" if text else "network_error"),
                            provider_used="browser", url=url, text=text,
                            data={"attempts": attempts})
        return {"ok": ok, "steps": [{"index": 1, "cmd": "read_url", "ok": ok}],
                "_wr": wr, "_url": url, "_text": text}

    # auto: dokobot first
    ok1, text1 = _dokobot_read(url, chars)
    attempts.append({"provider": "dokobot", "status": "ok" if (ok1 and text1.strip()) else "error",
                     "error_code": "ok" if (ok1 and text1.strip()) else ("read_failed" if ok1 else "provider_failed")})
    if ok1 and text1.strip():
        wr = WorkflowResult(status="ok", error_code="ok", provider_used="dokobot",
                            url=url, text=text1, data={"attempts": attempts})
        return {"ok": True, "steps": [{"index": 1, "cmd": "read_url", "ok": True}],
                "_wr": wr, "_url": url, "_text": text1}

    # fallback to browser
    ok2, text2 = _browser_read(url, chars)
    attempts.append({"provider": "browser", "status": "ok" if ok2 else "error",
                     "error_code": "ok" if ok2 else "network_error" if url else "read_failed"})
    if ok2:
        wr = WorkflowResult(status="ok", error_code="ok", provider_used="mixed",
                            fallback_used=True, url=url, text=text2,
                            data={"attempts": attempts})
        return {"ok": True, "steps": [{"index": 1, "cmd": "read_url", "ok": True}],
                "_wr": wr, "_url": url, "_text": text2}

    wr = WorkflowResult(status="error", error_code="read_failed", provider_used="mixed",
                        fallback_used=True, url=url, data={"attempts": attempts})
    return {"ok": False, "steps": [{"index": 1, "cmd": "read_url", "ok": False}],
            "_wr": wr, "_url": url}


def wf_close_popups(args, ctx=None):
    candidates = ["Close", "No thanks", "Not now", "Got it", "I agree", "Skip", "Dismiss"]
    popup_only = ["Accept", "Accept all"]  # only click inside popup/dialog
    risky = ["Pay", "Purchase", "Delete", "Remove", "Transfer", "Submit order", "Confirm payment"]
    snap = step("browser", "observe", {"snapshot": True, "text": False})
    po = snap.get("post_observe") or snap.get("result", {})
    els = po.get("snapshot", []) if isinstance(po, dict) else []
    clicked = None
    for el in els:
        if not el.get("visible"):
            continue
        txt = (el.get("text") or el.get("placeholder") or "").strip()
        if any(r in txt for r in risky):
            continue
        if txt in popup_only:
            # Check if element is inside a popup/dialog context
            sel = el.get("selector", "")
            if not any(ctx in sel.lower() for ctx in ["popup", "dialog", "modal", "overlay", "banner"]):
                continue
        if txt in candidates or txt.lower() in [c.lower() for c in candidates]:
            cid = el.get("id")
            if cid:
                r = step("browser", "click_id", {"id": cid})
                if r.get("ok"):
                    clicked = txt
                    break
    if clicked:
        step("browser", "wait", {"ms": 1000})
        wr = WorkflowResult(status="ok", error_code="ok", provider_used="browser",
                            data={"clicked": clicked})
        return {"ok": True, "steps": [{"index": 1, "cmd": "close_popups", "ok": True}],
                "_wr": wr}
    wr = WorkflowResult(status="uncertain", error_code="blocked_popup", provider_used="browser",
                        data={"message": "no high-confidence popup found"})
    return {"ok": False, "steps": [{"index": 1, "cmd": "close_popups", "ok": False}],
            "_wr": wr}


def wf_diagnose_and_recover(args, ctx=None):
    r = wf_diagnose(args, ctx)
    wr = r.get("_wr")
    if not wr:
        return r
    ec = wr.error_code if hasattr(wr, "error_code") else (wr.get("error_code", "") if isinstance(wr, dict) else "")
    if ec == "ok":
        return r
    if ec == "blocked_popup":
        r2 = wf_close_popups(args, ctx)
        if r2.get("ok"):
            r3 = wf_diagnose(args, ctx)
            wr3 = r3.get("_wr")
            if wr3:
                ec3 = wr3.error_code if hasattr(wr3, "error_code") else (
                    wr3.get("error_code", "") if isinstance(wr3, dict) else "")
                if ec3 == "ok":
                    if hasattr(wr3, "fallback_used"):
                        wr3.fallback_used = True
                    return r3
        return {"ok": False, "steps": r.get("steps", []), "_wr": wr}
    return {"ok": False, "steps": r.get("steps", []), "_wr": wr}


def wf_wait_text(args, ctx=None):
    text = args.get("text", "")
    timeout = int(args.get("timeout", 10))
    for _ in range(timeout * 2):
        r = step("browser", "extract_text", {"selector": "body"})
        body = (r.get("result", {}).get("text", "") or "") if r.get("ok") else ""
        if text in body:
            wr = WorkflowResult(status="ok", error_code="ok", provider_used="browser")
            return {"ok": True, "steps": [{"index": 1, "cmd": "wait_text", "ok": True}],
                    "_wr": wr}
        step("browser", "wait", {"ms": 500})
    wr = WorkflowResult(status="error", error_code="timeout", provider_used="browser")
    return {"ok": False, "steps": [{"index": 1, "cmd": "wait_text", "ok": False}],
            "_wr": wr}


def wf_assert_text(args, ctx=None):
    text = args.get("text", "")
    r = step("browser", "extract_text", {"selector": "body"})
    body = (r.get("result", {}).get("text", "") or "") if r.get("ok") else ""
    found = text in body
    wr = WorkflowResult(status="ok" if found else "error",
                        error_code="ok" if found else "not_found",
                        provider_used="browser")
    return {"ok": found, "steps": [{"index": 1, "cmd": "assert_text", "ok": found}],
            "_wr": wr}


def wf_click_expect(args, ctx=None):
    click_text = args.get("click_text", "")
    expect_text = args.get("expect", "")
    timeout = int(args.get("timeout", 10))
    risky = ["pay", "purchase", "delete", "remove", "transfer", "submit order", "confirm payment"]
    ct_lower = click_text.lower()
    for r in risky:
        if r in ct_lower:
            wr = WorkflowResult(status="error", error_code="risky_action", provider_used="browser",
                                message="refusing risky click: " + click_text)
            return {"ok": False, "steps": [], "_wr": wr}
    r1 = step("browser", "click_text", {"text": click_text})
    if not r1.get("ok"):
        wr = WorkflowResult(status="error", error_code="not_found", provider_used="browser",
                            message="could not click: " + click_text)
        return {"ok": False, "steps": [{"index": 1, "cmd": "click_text", "ok": False}],
                "_wr": wr}
    for _ in range(timeout * 2):
        r2 = step("browser", "extract_text", {"selector": "body"})
        body = (r2.get("result", {}).get("text", "") or "") if r2.get("ok") else ""
        if expect_text in body:
            wr = WorkflowResult(status="ok", error_code="ok", provider_used="browser")
            return {"ok": True, "steps": [{"index": 1, "cmd": "click_text", "ok": True},
                                           {"index": 2, "cmd": "wait_text", "ok": True}],
                    "_wr": wr}
        step("browser", "wait", {"ms": 500})
    wr = WorkflowResult(status="error", error_code="timeout", provider_used="browser",
                        message="expected text not found: " + expect_text)
    return {"ok": False, "steps": [{"index": 1, "cmd": "click_text", "ok": True},
                                    {"index": 2, "cmd": "wait_text", "ok": False}],
            "_wr": wr}


WORKFLOW_NAMES = {"read_url", "close_popups", "diagnose_and_recover", "wait_text", "assert_text", "click_expect"}

_HANDLERS = {
    "read_url": wf_read_url,
    "close_popups": wf_close_popups,
    "diagnose_and_recover": wf_diagnose_and_recover,
    "wait_text": wf_wait_text,
    "assert_text": wf_assert_text,
    "click_expect": wf_click_expect,
}

def run(name, args, ctx=None):
    fn = _HANDLERS.get(name)
    if fn:
        return fn(args, ctx)
    # Fallback to base workflows
    return bw.run(name, args, ctx)
