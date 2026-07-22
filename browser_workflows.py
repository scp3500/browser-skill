#!/usr/bin/env python3
"""browser_workflows.py — 网页任务确定性封装 (v1)"""

import sys, os, json, re
sys.path.insert(0, os.path.dirname(__file__))
from browser_agent import step
from urllib.parse import quote
from datetime import datetime
from tools.workflow_result import WorkflowResult, error_code_from_diagnose

last_search_results = []


def parse_chars(args, default=3000):
    """Parse chars/max_chars safely; flags like '--chars' fall back to default."""
    raw = args.get("chars", args.get("max_chars", default))
    if raw is None:
        return int(default)
    if isinstance(raw, (int, float)):
        return int(raw)
    s = str(raw).strip()
    if not s or s.startswith("--"):
        return int(default)
    try:
        return int(s)
    except (TypeError, ValueError):
        return int(default)


def _inject_header(obs, wr):
    header = wr.cli_header()
    if obs:
        return header + chr(10) + obs
    return header
def run(name, args, ctx=None):
    fn = {
        "read": wf_read, "open": wf_open, "current": wf_current,
        "article": wf_article, "search": wf_search,
        "open_result": wf_open_result, "search_read": wf_search_read,
        "wiki_read": wf_wiki_read, "wiki_click_read": wf_wiki_read,
        "doko_read": wf_doko_read, "images": wf_images,
        "image_page": wf_image_page, "diagnose": wf_diagnose, "visual_search_check": wf_visual_search_check,
        "ask_image": wf_ask_image, "screenshot_ask": wf_screenshot_ask,
    }.get(name)
    if not fn: return {"ok": False, "observation": f"unknown: {name}"}
    return fn(args, ctx)

def _result(ok, steps, url="", title="", text="", snap=None, results=None):
    obs = "\n".join(f"  {s.get('index')}. {s.get('observation','') or s.get('cmd','?') + ' -> ' + ('OK' if s.get('ok') else 'FAIL')}" for s in steps)
    r = {"ok": ok, "steps": steps, "observation": obs, "_url": url, "_title": title, "_text": text}
    if results: r["_search_results"] = results
    els = []
    for e in (snap or []):
        if not e.get("visible"): continue
        txt = (e.get("placeholder") or e.get("text") or "").strip()
        if txt: els.append(f"  [{e['id']}] {txt[:50]}")
    if els: r["_elements"] = els[:5]
    return r

def wf_read(args, ctx):
    chars = parse_chars(args, 3000)
    r = step("browser", "extract_text", {"selector": "body"})
    text = (r.get("result",{}).get("text","") or "")[:chars] if r.get("ok") else ""
    po = r.get("post_observe") or r.get("result", {})
    u = po.get("url","") if isinstance(po,dict) else ""
    t = po.get("title","") if isinstance(po,dict) else ""
    return _result(r.get("ok"), [{"index":1,"cmd":"read","ok":r.get("ok")}], url=u, title=t, text=text)

def wf_open(args, ctx):
    url = args.get("url", "")
    r = step("browser", "goto", {"url": url}) if url else step("browser", "observe", {"snapshot":True,"text":True})
    po = r.get("post_observe") or r.get("result", {})
    u = po.get("url","") if isinstance(po,dict) else ""
    t = po.get("title","") if isinstance(po,dict) else ""
    return _result(r.get("ok"), [{"index":1,"cmd":"open","ok":r.get("ok")}], url=u, title=t, snap=po.get("snapshot",[]) if isinstance(po,dict) else [])

def wf_current(args, ctx):
    return wf_open({"url": ""}, ctx)

def wf_article(args, ctx):
    url, chars = args.get("url",""), parse_chars(args, 3000)
    r1 = step("browser", "goto", {"url": url})
    s1 = {"index":1,"cmd":"open","ok":r1.get("ok")}
    if not r1.get("ok"): return _result(False, [s1])
    r2 = step("browser", "extract_text", {"selector": "body"})
    text = (r2.get("result",{}).get("text","") or "")[:chars] if r2.get("ok") else ""
    po = r1.get("post_observe") or r1.get("result", {})
    u = po.get("url","") if isinstance(po,dict) else ""
    t = po.get("title","") if isinstance(po,dict) else ""
    return _result(r2.get("ok"), [s1,{"index":2,"cmd":"read","ok":r2.get("ok")}], url=u, title=t, text=text)

def wf_search(args, ctx):
    global last_search_results
    query = args.get("query", "")
    url = f"https://www.bing.com/search?q={quote(query)}"
    r = step("browser", "goto", {"url": url})
    s1 = {"index":1,"cmd":"search","ok":r.get("ok")}
    if not r.get("ok"): return _result(False, [s1], text="search page failed")

    po = r.get("post_observe") or r.get("result", {})
    snap = po.get("snapshot", []) if isinstance(po, dict) else []
    results = []
    seen = set()
    for el in snap:
        if el.get("visible") and el["tag"] == "a" and el.get("href","").startswith("http") and el.get("text","").strip():
            txt = el["text"].strip()
            if txt not in seen and len(txt) > 3:
                seen.add(txt); results.append({"title": txt[:80], "url": el["href"], "snippet": ""})
                if len(results) >= 5: break

    # fallback: 用 extract_text 读全文
    if not results:
        r2 = step("browser", "extract_text", {"selector": "body"})
        raw = r2.get("result",{}).get("text","")[:3000] if r2.get("ok") else ""
        for line in raw.split("\n"):
            line = line.strip()
            if line and len(line) > 10 and not line.startswith("http"):
                results.append({"title": line[:80], "url": "", "snippet": ""})
                if len(results) >= 5: break

    last_search_results = results
    lines = []
    for i, res in enumerate(results, 1):
        lines.append(f"  [{i}] {res['title']}")
        if res['url']: lines.append(f"       {res['url']}")
    return _result(bool(results), [s1], text="\n".join(lines), results=results)

def wf_open_result(args, ctx):
    global last_search_results
    n = int(args.get("result", args.get("n", 1)))
    if not last_search_results or n < 1 or n > len(last_search_results):
        return _result(False, [{"index":1,"cmd":"open_result","ok":False}])
    url = last_search_results[n-1].get("url","")
    if not url: return _result(False, [{"index":1,"cmd":"open_result","ok":False}])
    return wf_open({"url": url}, ctx)

def wf_search_read(args, ctx):
    query = args.get("query","")
    n = int(args.get("result",args.get("n",1)))
    chars = parse_chars(args, 3000)
    steps_data = []
    r1 = wf_search({"query": query}, ctx)
    steps_data.append({"name":"search","ok":r1.get("ok")})
    if not r1.get("ok"):
        wr = WorkflowResult(status="error", error_code="no_search_results", provider_used="browser", url="", data={"query":query,"steps":steps_data})
        return {"ok":False,"steps":[{"index":1,"cmd":"search","ok":False}],"observation":_inject_header("",wr),"_wr":wr}
    r2 = wf_open_result({"result": n, "n": n}, ctx)
    steps_data.append({"name":"open_result","ok":r2.get("ok")})
    if not r2.get("ok"):
        wr = WorkflowResult(status="error", error_code="network_error", provider_used="browser", url="", data={"query":query,"steps":steps_data})
        return {"ok":False,"steps":[{"index":1,"cmd":"search","ok":True},{"index":2,"cmd":"open_result","ok":False}],"observation":_inject_header("",wr),"_wr":wr}
    r3 = wf_read({"chars": chars}, ctx)
    steps_data.append({"name":"read","ok":r3.get("ok")})
    text = r3.get("_text","") or ""
    if not text.strip():
        wr = WorkflowResult(status="error", error_code="read_failed", provider_used="browser", url=r2.get("_url",""), title=r2.get("_title",""), text=text, data={"query":query,"steps":steps_data})
        return {"ok":False,"steps":[{"index":1,"cmd":"search","ok":True},{"index":2,"cmd":"open_result","ok":True},{"index":3,"cmd":"read","ok":False}],"observation":_inject_header("",wr),"_wr":wr,"_url":r2.get("_url",""),"_title":r2.get("_title",""),"_text":text}
    url = r2.get("_url","") or r3.get("_url","")
    title = r2.get("_title","") or r3.get("_title","")
    wr = WorkflowResult(status="ok", error_code="ok", provider_used="browser", url=url, title=title, text=text, data={"query":query,"result_index":n,"steps":steps_data})
    obs_body = f"URL: {url}" + (chr(10) + f"Title: {title}" if title else "")
    return {"ok":True,"steps":[{"index":1,"cmd":"search","ok":True},{"index":2,"cmd":"open_result","ok":True},{"index":3,"cmd":"read","ok":True}],"observation":_inject_header(obs_body,wr),"_wr":wr,"_url":url,"_title":title,"_text":text}

def wf_wiki_read(args, ctx):
    query, chars, click = args.get("query",""), parse_chars(args, 3000), args.get("click","")
    url = f"https://en.wikipedia.org/w/index.php?search={quote(query)}"
    steps = []
    r1 = step("browser", "goto", {"url": url})
    steps.append({"index":1,"cmd":"wiki","ok":r1.get("ok")})
    if click:
        r1b = step("browser", "click_text", {"text": click})
        steps.append({"index":"1b","cmd":"click_text","ok":r1b.get("ok")})
    r2 = step("browser", "extract_text", {"selector": "body"})
    text = (r2.get("result",{}).get("text","") or "")[:chars] if r2.get("ok") else ""
    steps.append({"index":2,"cmd":"read","ok":r2.get("ok")})
    po = r1.get("post_observe") or r1.get("result", {})
    u = po.get("url","") if isinstance(po,dict) else ""
    t = po.get("title","") if isinstance(po,dict) else ""
    return _result(r2.get("ok"), steps, url=u, title=t, text=text)


# ===== Provider workflows (dokobot + openvl) =====

def _run_dokobot(cmd, args):
    """调 dokobot 并返回统一格式"""
    from tools.dokobot_tool import call as dokobot
    return dokobot(cmd, args)

def _run_openvl(cmd, args):
    """调 openvl 并返回统一格式"""
    from tools.openvl_tool import call as openvl
    return openvl(cmd, args)

def wf_doko_read(args, ctx):
    url = args.get("url", "")
    chars = parse_chars(args, 3000)
    r = _run_dokobot("read", {"url": url})
    ok = r.get("ok")
    text = ""
    err_code = "ok"
    message = None
    if ok:
        text = (r["result"].get("text", "") or "")[:chars]
        if not text.strip():
            err_code = "read_failed"; ok = False; message = "empty text"
    else:
        err = r.get("error", {})
        et = err.get("type", "")
        err_code = "timeout" if "timeout" in et.lower() else "provider_failed"
        message = err.get("message", "")[:100]

    wr = WorkflowResult(status="ok" if ok else "error", error_code=err_code, provider_used="dokobot",
                        url=url, text=text, message=message)
    steps = [{"index": 1, "cmd": "doko_read", "ok": ok}]
    obs_body = f"URL: {url} " + chr(10) + f"Text: {text[:300]}" if ok else f"failed: {message}" + chr(10)
    return {"ok": ok, "steps": steps, "observation": _inject_header(obs_body, wr), "_wr": wr, "_text": text, "_url": url}

def wf_images(args, ctx):
    """images: dokobot download images"""
    url = args.get("url", "")
    r = _run_dokobot("download_images", {"url": url})
    steps = [{"index": 1, "cmd": "download_images", "ok": r.get("ok")}]
    if not r.get("ok"):
        return _result(False, steps)
    out = r["result"].get("text", "")
    # 提取图片路径
    import re
    paths = re.findall(r'"filename":\s*"([^"]+)"', out)
    if not paths:
        paths = re.findall(r'([A-Z]:\\(?:[^\\"]+\\)*[^\\"]+\.(?:png|jpg|jpeg|webp))', out)
    lines = [f"Downloaded {len(paths)} images"] if paths else []
    for i, p in enumerate(paths[:10], 1):
        lines.append(f"  [{i}] {p}")
    return _result(True, steps, text="\n".join(lines))

def wf_image_page(args, ctx):
    """image_page: download + optional describe"""
    url = args.get("url", "")
    limit = int(args.get("limit", args.get("max_chars", "3")))
    do_describe = args.get("describe", False)

    r = _run_dokobot("download_images", {"url": url})
    steps = [{"index": 1, "cmd": "download_images", "ok": r.get("ok")}]
    if not r.get("ok"):
        return _result(False, steps)

    out = r["result"].get("text", "")
    import re
    paths = re.findall(r'"filename":\s*"([^"]+)"', out)
    if not paths:
        paths = re.findall(r'"url":\s*"file:///([^"]+)"', out)
    if not paths:
        paths = re.findall(r'([A-Z]:\(?:[^\\"]+\\)*[^\\"]+\.(?:png|jpg|jpeg|webp))', out)

    selected = [p for p in paths if os.path.exists(p)][:limit] if paths else []
    lines = [f"Downloaded {len(paths)} images, selected {len(selected)}"]
    for i, p in enumerate(selected, 1):
        lines.append(f"  [{i}] {p}")

    if do_describe and selected:
        for i, img_path in enumerate(selected, 1):
            q = args.get("question", f"Image {i}: describe what this image contains")
            rv = _run_openvl("describe", {"image_path": img_path, "question": q, "mode": "image_select"})
            desc = rv.get("result", {}).get("text", "") if rv.get("ok") else "describe failed"
            steps.append({"index": len(steps)+1, "cmd": "describe", "ok": rv.get("ok")})
            lines.append(f"  [{i}] Describe: {desc[:200]}")

    return _result(True, steps, text="\n".join(lines))

def wf_diagnose(args, ctx):
    q = args.get("question", "Is there any popup, captcha, cookie banner, login wall, or layout issue on this page?")
    from browser_daemon import _cleanup_screenshots; _cleanup_screenshots(); ts = datetime.now().strftime("%Y%m%d_%H%M%S"); ms = int(datetime.now().strftime("%f")[:3]); spath = os.path.join(os.environ.get("TEMP", "/tmp"), f"browser_diagnose_{ts}_{ms:03d}.png")
    r1 = step("browser", "screenshot", {"path": spath})
    steps = [{"index": 1, "cmd": "screenshot", "ok": r1.get("ok")}]
    if not r1.get("ok"):
        wr = WorkflowResult(status="error", error_code="provider_failed", provider_used="openvl", data={"error": "screenshot failed"})
        obs = _inject_header("screenshot failed", wr)
        return {"ok": False, "steps": steps, "observation": obs, "_wr": wr}
    r2 = _run_openvl("describe", {"image_path": spath, "question": q, "mode": "diagnose"})
    desc = r2.get("result", {}).get("text", "") if r2.get("ok") else ""
    steps.append({"index": 2, "cmd": "openvl.describe", "ok": r2.get("ok")})
    ok = r2.get("ok") and bool(desc)
    err_code = error_code_from_diagnose(desc) if ok else "provider_failed"
    status = "ok" if err_code == "ok" else ("blocked" if ok else "error")
    data = {"blocking_issue": err_code.replace("blocked_", "") if "blocked" in err_code else err_code}
    wr = WorkflowResult(status=status, error_code=err_code, provider_used="openvl", data=data)
    # Parse structured fields from vision text
    bi = ""
    reason = ""
    action = ""
    for line in (desc or "").split(chr(10)):
        ls = line.strip()
        if ls.startswith("Blocking issue:"): bi = ls.split(":", 1)[1].strip()
        if ls.startswith("Reason:"): reason = ls.split(":", 1)[1].strip()
        if ls.startswith("Suggested action:"): action = ls.split(":", 1)[1].strip()
    obs = f"Screenshot: {spath}"
    obs += chr(10) + f"Blocking issue: {bi}" if bi else ""
    obs += chr(10) + f"Reason: {reason}" if reason else ""
    obs += chr(10) + f"Suggested action: {action}" if action else ""
    return {"ok": ok, "steps": steps, "observation": obs, "_wr": wr, "_text": obs}

def wf_ask_image(args, ctx):
    """ask_image: openvl describe 指定图片"""
    img = args.get("path", args.get("image_path", ""))
    q = args.get("question", args.get("query", "Describe this image"))
    r = _run_openvl("describe", {"image_path": img, "question": q, "mode": args.get("mode","describe")})
    desc = r.get("result", {}).get("text", "") if r.get("ok") else ""
    steps = [{"index": 1, "cmd": "openvl.describe", "ok": r.get("ok")}]
    return _result(r.get("ok"), steps, text=f"Image: {img}\nVision: {desc[:500]}")

def wf_screenshot_ask(args, ctx):
    """screenshot_ask: screenshot + openvl describe"""
    q = args.get("question", args.get("query", "What is shown on this page?"))
    from browser_daemon import _cleanup_screenshots; _cleanup_screenshots(); ts = datetime.now().strftime("%Y%m%d_%H%M%S"); ms = int(datetime.now().strftime("%f")[:3]); spath = os.path.join(os.environ.get("TEMP", "/tmp"), f"browser_screenshot_ask_{ts}_{ms:03d}.png")
    r1 = step("browser", "screenshot", {"path": spath})
    if not r1.get("ok"):
        return _result(False, [{"index":1,"cmd":"screenshot","ok":False}], text="screenshot failed")
    r2 = _run_openvl("describe", {"image_path": spath, "question": q, "mode": args.get("mode","diagnose")})
    desc = r2.get("result", {}).get("text", "") if r2.get("ok") else ""
    steps = [
        {"index":1,"cmd":"screenshot","ok":r1.get("ok")},
        {"index":2,"cmd":"openvl.describe","ok":r2.get("ok")},
    ]
    return _result(r2.get("ok"), steps, text=f"Screenshot: {spath}\nVision: {desc[:500]}")


def wf_visual_search_check(args, ctx):
    """visual_search_check: screenshot + openvl mode=search"""
    goal = args.get("goal", args.get("query", ""))
    q = args.get("question", goal)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    spath = os.path.join(os.environ.get("TEMP", "/tmp"), f"browser_visual_check_{ts}.png")
    r1 = step("browser", "screenshot", {"path": spath})
    steps = [{"index": 1, "cmd": "screenshot", "ok": r1.get("ok")}]
    if not r1.get("ok"): return _result(False, steps, text="screenshot failed")
    r2 = _run_openvl("describe", {"image_path": spath, "question": q, "mode": "search"})
    desc = r2.get("result", {}).get("text", "") if r2.get("ok") else ""
    steps.append({"index": 2, "cmd": "openvl.search", "ok": r2.get("ok")})
    return _result(r2.get("ok"), steps, text=f"Screenshot: {spath}\nVision:\n{desc[:600]}")

