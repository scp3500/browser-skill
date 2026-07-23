#!/usr/bin/env python3
"""
browser_server.py — 常驻浏览器进程，stdin/stdout JSON 通信

启动：
  python browser_server.py

协议：
  → {"id":"1","cmd":"goto","args":{"url":"https://example.com"}}
  ← {"id":"1","ok":true,"result":{"url":"...","title":"..."}}

命令：goto, click, click_text, fill, fill_label, press, screenshot,
  get_text, get_html, wait, wait_for_selector, hover, select,
  scroll, evaluate, get_url, get_title, extract_text, snapshot,
  observe, close
"""

import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
import json
import base64
import os
import io
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# Only rewrap stdio when running as daemon process (breaks pytest capture if done on import)
if __name__ == "__main__" or os.environ.get("BROWSER_SERVER_REWRAP_STDIO") == "1":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

P = None
BROWSER = None
PAGE = None  # always mirrors TABS[ACTIVE_ID]
TABS = {}
ACTIVE_ID = "0"
_TAB_SEQ = 0
CONTEXT = None          # BrowserContext when using persistent profile
PERSISTENT = False
FRAMES = {}             # tab_id -> list of frame selectors (outer→inner)
DOWNLOAD_DIR = None


def log(*args):
    print(*args, file=sys.stderr, flush=True)


def _apply_init(page):
    page.set_extra_http_headers({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    })
    page.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
        " window.chrome = { runtime: {} };"
    )


def _sync_page():
    global PAGE
    PAGE = TABS.get(ACTIVE_ID)


def _next_tab_id():
    global _TAB_SEQ
    _TAB_SEQ += 1
    return f"t{_TAB_SEQ}"


def _tab_info(tid, page):
    try:
        url = page.url
    except Exception:
        url = ""
    try:
        title = page.title()
    except Exception:
        title = ""
    return {"id": tid, "url": url, "title": title}



def _profile_dir():
    """Optional persistent profile from env (empty = ephemeral)."""
    d = (os.environ.get("BROWSER_PROFILE_DIR")
         or os.environ.get("BROWSER_USER_DATA_DIR")
         or "").strip()
    return d or None


def _download_dir():
    global DOWNLOAD_DIR
    if DOWNLOAD_DIR:
        return Path(DOWNLOAD_DIR)
    d = (os.environ.get("BROWSER_DOWNLOAD_DIR") or "").strip()
    if d:
        p = Path(d)
    else:
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".pi")) / "Pi" / "browser" / "downloads"
        p = base
    p.mkdir(parents=True, exist_ok=True)
    DOWNLOAD_DIR = str(p)
    return p


def _new_page():
    """Create a page on the active browser/context."""
    if PERSISTENT:
        return CONTEXT.new_page()
    return BROWSER.new_page()


def _target(page):
    """Resolve frame chain for current tab; returns Page or Frame."""
    chain = FRAMES.get(ACTIVE_ID) or []
    cur = page
    for sel in chain:
        # Prefer element content_frame (works for Page and Frame).
        handle = cur.query_selector(sel)
        if handle is None:
            # Optional Playwright fallback when available
            fl = getattr(cur, "frame_locator", None)
            if fl is None:
                raise RuntimeError(f"frame selector not found: {sel}")
            cur = fl(sel).first
            continue
        fr = handle.content_frame()
        if fr is None:
            raise RuntimeError(f"not a frame element: {sel}")
        cur = fr
    return cur



def ensure_page():
    global P, BROWSER, CONTEXT, PAGE, TABS, ACTIVE_ID, PERSISTENT
    if BROWSER is None and CONTEXT is None:
        P = sync_playwright().start()
        profile = _profile_dir()
        launch_args = [
            '--disable-blink-features=AutomationControlled',
            '--no-sandbox',
        ]
        if profile:
            Path(profile).mkdir(parents=True, exist_ok=True)
            PERSISTENT = True
            CONTEXT = P.chromium.launch_persistent_context(
                user_data_dir=profile,
                headless=True,
                accept_downloads=True,
                args=launch_args,
            )
            BROWSER = CONTEXT  # so callers can still check truthiness
            pages = list(CONTEXT.pages)
            page = pages[0] if pages else CONTEXT.new_page()
            _apply_init(page)
        else:
            PERSISTENT = False
            BROWSER = P.chromium.launch(headless=True, args=launch_args)
            CONTEXT = None
            page = BROWSER.new_page()
            _apply_init(page)
        TABS = {"0": page}
        ACTIVE_ID = "0"
        FRAMES["0"] = []
        PAGE = page
    elif not TABS or ACTIVE_ID not in TABS:
        page = _new_page()
        _apply_init(page)
        tid = ACTIVE_ID if ACTIVE_ID else "0"
        TABS[tid] = page
        ACTIVE_ID = tid
        FRAMES.setdefault(tid, [])
        PAGE = page
    else:
        PAGE = TABS[ACTIVE_ID]
    return TABS[ACTIVE_ID]


def _smart_click(page, locator, args):
    timeout = int(args.get("timeout", 10000))
    try:
        locator.wait_for(state="visible", timeout=timeout)
    except Exception:
        pass
    try:
        locator.click(timeout=timeout)
    except Exception:
        try:
            locator.scroll_into_view_if_needed(timeout=timeout)
        except Exception:
            pass
        locator.click(timeout=timeout, force=True)
    _wait_stable(page)


def ok(req_id, result):
    print(json.dumps({"id": req_id, "ok": True, "result": result}, ensure_ascii=False), flush=True)


def fail(req_id, err_type, message, cmd=None):
    err = {"type": err_type, "message": str(message)}
    if cmd:
        err["cmd"] = cmd
    print(json.dumps({"id": req_id, "ok": False, "error": err}, ensure_ascii=False), flush=True)



def new_page_for_url(url, chars=3000, timeout_ms=30000):
    """Create a new page, navigate to URL, read text, close page"""
    global BROWSER, PAGE
    import traceback as _tb
    try:
        ensure_page()
        np = _new_page()
        try:
            np.set_viewport_size({"width": 1280, "height": 720})
            np.goto(url, timeout=int(timeout_ms))
            for state in ("domcontentloaded", "networkidle"):
                try: np.wait_for_load_state(state, timeout=5000)
                except Exception: pass
            np.wait_for_timeout(500)
            title = np.title()
            text = np.inner_text("body") or ""
            if len(text) > chars:
                text = text[:chars] + "[Truncated: yes]"
            np_url = np.url
            return {"url": np_url, "title": title, "text": text}
        finally:
            try: np.close()
            except Exception: pass
    except Exception as ex:
        _tb.print_exc(file=sys.stderr)
        raise

def handle(req):
    global ACTIVE_ID, TABS, PAGE, P, BROWSER, CONTEXT, PERSISTENT, FRAMES, DOWNLOAD_DIR
    cmd = req.get("cmd", "")
    args = req.get("args", {})
    req_id = req.get("id", "")

    try:
        page = ensure_page()
    except Exception as e:
        fail(req_id, type(e).__name__, str(e), "launch")
        return

    try:
        target = _target(page)
        if cmd == "goto":
            url = args["url"]
            page.goto(url, timeout=args.get("timeout", 30000))
            _wait_stable(page)
            ok(req_id, {"url": page.url, "title": page.title()})

        elif cmd == "click":
            sel = args["selector"]
            timeout = args.get("timeout", 10000)
            # wait defaults False so click_id path stays stable
            if args.get("wait"):
                target.wait_for_selector(sel, state="visible", timeout=timeout)
            target.click(sel, timeout=timeout)
            _wait_stable(page)
            ok(req_id, {"url": page.url})

        elif cmd == "click_text":
            text = args.get("text", args.get("args", ""))
            page.get_by_text(text, exact=args.get("exact", False)).first.click(timeout=args.get("timeout", 10000))
            _wait_stable(page)
            ok(req_id, {"url": page.url})

        elif cmd == "click_id":
            click_id = args.get("id", 0)
            items = _collect_snapshot(page, args.get("max_items", 200))
            target = next((x for x in items if x["id"] == click_id), None)
            if not target:
                fail(req_id, "NotFound", f"element id={click_id} not found", cmd)
                return
            sel = target["selector"]
            page.click(sel, timeout=args.get("timeout", 10000))
            _wait_stable(page)
            ok(req_id, {"url": page.url, "element": target})

        elif cmd == "fill":
            page.fill(args["selector"], args["text"])
            ok(req_id, {})

        elif cmd == "fill_id":
            fill_id = args.get("id", 0)
            text = args.get("text", args.get("value", ""))
            items = _collect_snapshot(page, args.get("max_items", 200))
            target = next((x for x in items if x["id"] == fill_id), None)
            if not target:
                fail(req_id, "NotFound", f"element id={fill_id} not found", cmd)
                return
            page.fill(target["selector"], text)
            ok(req_id, {"element": target})

        elif cmd == "fill_label":
            label = args.get("label", "")
            text = args.get("text", "")
            page.get_by_label(label).fill(text)
            ok(req_id, {})

        elif cmd == "press":
            key = args.get("key", args.get("args", ""))
            page.keyboard.press(key)
            _wait_stable(page)
            ok(req_id, {})

        elif cmd == "screenshot":
            path = args.get("path", "")
            if path:
                os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
                page.screenshot(path=path)
                ok(req_id, {"path": path})
            else:
                b64 = base64.b64encode(page.screenshot()).decode()
                ok(req_id, {"base64": b64})

        elif cmd == "get_text":
            sel = args["selector"]
            els = page.query_selector_all(sel)
            texts = [el.inner_text() for el in els] if els else []
            ok(req_id, {"texts": texts, "count": len(texts)})

        elif cmd == "get_html":
            sel = args["selector"]
            el = page.query_selector(sel)
            html = el.inner_html() if el else ""
            ok(req_id, {"html": html})

        elif cmd == "wait":
            ms = args.get("ms", 1000)
            page.wait_for_timeout(ms)
            ok(req_id, {"waited": ms})

        elif cmd == "wait_for_selector":
            sel = args["selector"]
            state = args.get("state", "visible")
            page.wait_for_selector(sel, state=state, timeout=args.get("timeout", 10000))
            ok(req_id, {"selector": sel, "state": state})

        elif cmd == "hover":
            sel = args.get("selector", args.get("args", ""))
            page.hover(sel)
            ok(req_id, {})

        elif cmd == "select":
            page.select_option(args["selector"], args["value"])
            ok(req_id, {})

        elif cmd == "scroll":
            dx = args.get("x", 0)
            dy = args.get("y", 300)
            page.evaluate(f"window.scrollBy({dx}, {dy})")
            ok(req_id, {"scrolled": {"x": dx, "y": dy}})

        elif cmd == "evaluate":
            expr = args.get("expression", args.get("args", ""))
            result = page.evaluate(expr)
            ok(req_id, {"result": result})

        elif cmd == "get_url":
            ok(req_id, {"url": page.url})

        elif cmd == "get_title":
            ok(req_id, {"title": page.title()})

        elif cmd == "extract_text":
            sel = args.get("selector", "body")
            el = page.query_selector(sel)
            text = el.inner_text() if el else ""
            ok(req_id, {"text": text, "length": len(text)})

        elif cmd == "snapshot":
            max_items = args.get("max_items", 80)
            items = _collect_snapshot(page, max_items)
            ok(req_id, {
                "url": page.url,
                "title": page.title(),
                "items": items,
                "count": len(items),
            })

        elif cmd == "observe":
            do_screenshot = args.get("screenshot", False)
            do_snapshot = args.get("snapshot", True)
            do_text = args.get("text", True)
            max_text = args.get("max_text_chars", 6000)
            max_items = args.get("max_snapshot_items", 80)
            result = {
                "url": page.url,
                "title": page.title(),
            }
            for attempt in range(2):
                try:
                    if do_text:
                        el = page.query_selector("body")
                        raw = el.inner_text() if el else ""
                        result["text"] = raw[:max_text]
                    if do_snapshot:
                        result["snapshot"] = _collect_snapshot(page, max_items)
                    break
                except Exception as e:
                    err_msg = str(e)
                    if "Execution context was destroyed" in err_msg and attempt == 0:
                        page.wait_for_timeout(1000)
                        continue
                    raise
            if do_screenshot:
                spath = args.get("screenshot_path", "")
                if spath:
                    os.makedirs(os.path.dirname(spath) or ".", exist_ok=True)
                    page.screenshot(path=spath)
                    result["screenshot_path"] = spath
                else:
                    b64 = base64.b64encode(page.screenshot()).decode()
                    result["screenshot_base64"] = b64[:200] + "..." if len(b64) > 200 else b64
            ok(req_id, result)

        elif cmd == "tabs":
            items = [_tab_info(tid, p) for tid, p in TABS.items()]
            ok(req_id, {"tabs": items, "active": ACTIVE_ID, "count": len(items)})

        elif cmd == "new_tab":
            ensure_page()
            tid = args.get("id") or _next_tab_id()
            if tid in TABS:
                fail(req_id, "InputError", f"tab id already exists: {tid}", cmd); return
            np = _new_page()
            _apply_init(np)
            TABS[tid] = np
            FRAMES[tid] = []
            ACTIVE_ID = tid
            _sync_page()
            url = args.get("url") or ""
            if url:
                np.goto(url, timeout=args.get("timeout", 30000))
                _wait_stable(np)
            info = _tab_info(tid, np)
            info["tab_id"] = tid
            ok(req_id, info)

        elif cmd == "switch_tab":
            tid = str(args.get("id", ""))
            if not tid or tid not in TABS:
                fail(req_id, "NotFound", f"tab not found: {tid}", cmd); return
            ACTIVE_ID = tid
            _sync_page()
            page = TABS[tid]
            info = _tab_info(tid, page)
            info["tab_id"] = tid
            ok(req_id, info)

        elif cmd == "close_tab":
            ensure_page()
            tid = str(args.get("id") or ACTIVE_ID)
            if tid not in TABS:
                fail(req_id, "NotFound", f"tab not found: {tid}", cmd); return
            try:
                TABS[tid].close()
            except Exception:
                pass
            del TABS[tid]
            FRAMES.pop(tid, None)
            if not TABS:
                page0 = _new_page()
                _apply_init(page0)
                TABS["0"] = page0
                ACTIVE_ID = "0"
                FRAMES["0"] = []
            elif ACTIVE_ID == tid:
                ACTIVE_ID = next(iter(TABS.keys()))
            _sync_page()
            remaining = list(TABS.keys())
            ok(req_id, {"closed": tid, "remaining": remaining, "active": ACTIVE_ID})

        elif cmd == "wait_selector":
            sel = args.get("selector", "")
            state = args.get("state", "visible")
            if state not in ("visible", "attached", "hidden", "detached"):
                fail(req_id, "InputError", f"invalid state: {state}", cmd); return
            timeout = int(args.get("timeout", 10000))
            target.wait_for_selector(sel, state=state, timeout=timeout)
            ok(req_id, {"selector": sel, "state": state})

        elif cmd == "wait_url":
            pattern = args.get("pattern", "")
            timeout = int(args.get("timeout", 10000))
            exact = bool(args.get("exact", False))
            if exact:
                page.wait_for_url(lambda u: u == pattern, timeout=timeout)
            else:
                page.wait_for_url(pattern, timeout=timeout)
            ok(req_id, {"url": page.url, "pattern": pattern})

        elif cmd == "scroll_into_view":
            sel = args.get("selector", "")
            timeout = int(args.get("timeout", 10000))
            el = target.wait_for_selector(sel, state="visible", timeout=timeout)
            el.scroll_into_view_if_needed(timeout=timeout)
            box = el.bounding_box()
            ok(req_id, {"selector": sel, "bbox": box})

        elif cmd == "click_role":
            role = args.get("role", "")
            name = args.get("name") or None
            exact = bool(args.get("exact", False))
            kwargs = {"exact": exact}
            if name:
                kwargs["name"] = name
            loc = target.get_by_role(role, **kwargs).first
            _smart_click(page, loc, args)
            ok(req_id, {"url": page.url, "role": role, "name": name or ""})

        elif cmd == "click_label":
            label = args.get("label", "")
            exact = bool(args.get("exact", False))
            loc = target.get_by_label(label, exact=exact).first
            _smart_click(page, loc, args)
            ok(req_id, {"url": page.url, "label": label})

        elif cmd == "upload":
            sel = args.get("selector", "")
            files = args.get("files") or args.get("path") or args.get("file") or ""
            if isinstance(files, str):
                files = [f.strip() for f in files.split(";") if f.strip()] if ";" in files else ([files] if files else [])
            if not sel or not files:
                fail(req_id, "InputError", "upload requires selector and file path(s)", cmd); return
            for f in files:
                if not Path(f).exists():
                    fail(req_id, "InputError", f"file not found: {f}", cmd); return
            target.set_input_files(sel, files if len(files) > 1 else files[0])
            ok(req_id, {"selector": sel, "files": files})

        elif cmd == "download":
            # Click something (or wait) and save the next download
            sel = args.get("selector") or args.get("click") or ""
            out = args.get("path") or args.get("save_as") or ""
            timeout = int(args.get("timeout", 30000))
            ddir = _download_dir()
            try:
                with page.expect_download(timeout=timeout) as di:
                    if sel:
                        target.click(sel, timeout=min(timeout, 10000))
                    # if no selector, caller already triggered download
                download = di.value
                suggested = download.suggested_filename or "download.bin"
                dest = Path(out) if out else (ddir / suggested)
                dest.parent.mkdir(parents=True, exist_ok=True)
                download.save_as(str(dest))
                ok(req_id, {
                    "path": str(dest),
                    "suggested_filename": suggested,
                    "url": download.url,
                })
            except Exception as ex:
                fail(req_id, type(ex).__name__, str(ex), cmd)

        elif cmd == "frame_enter":
            sel = args.get("selector", "")
            if not sel:
                fail(req_id, "InputError", "frame_enter requires selector", cmd); return
            # validate frame exists on current target
            handle = target.query_selector(sel)
            if handle is None:
                fail(req_id, "NotFound", f"frame selector not found: {sel}", cmd); return
            if handle.content_frame() is None:
                fail(req_id, "InputError", f"element is not a frame: {sel}", cmd); return
            chain = list(FRAMES.get(ACTIVE_ID) or [])
            chain.append(sel)
            FRAMES[ACTIVE_ID] = chain
            ok(req_id, {"frame": sel, "depth": len(chain), "chain": chain})

        elif cmd == "frame_exit":
            chain = list(FRAMES.get(ACTIVE_ID) or [])
            left = chain.pop() if chain else None
            FRAMES[ACTIVE_ID] = chain
            ok(req_id, {"exited": left, "depth": len(chain), "chain": chain})

        elif cmd == "frame_main":
            FRAMES[ACTIVE_ID] = []
            ok(req_id, {"depth": 0, "chain": []})

        elif cmd == "frame_status":
            chain = list(FRAMES.get(ACTIVE_ID) or [])
            ok(req_id, {"depth": len(chain), "chain": chain, "tab_id": ACTIVE_ID})

        elif cmd == "profile_status":
            ok(req_id, {
                "persistent": PERSISTENT,
                "profile_dir": _profile_dir() or "",
                "download_dir": str(_download_dir()),
            })

        elif cmd == "read_url_new_page":


            url = args.get("url", "")
            if not url:
                fail(req_id, "InputError", "url required", cmd); return
            try:
                raw_chars = args.get("chars", "3000")
                if isinstance(raw_chars, str) and raw_chars.strip().startswith("--"):
                    chars = 3000
                else:
                    chars = int(raw_chars)
            except (TypeError, ValueError):
                chars = 3000
            try:
                timeout_ms = int(args.get("timeout", "30000"))
            except (TypeError, ValueError):
                timeout_ms = 30000
            try:
                result = new_page_for_url(url, chars, timeout_ms)
                ok(req_id, result)
            except Exception as ex:
                fail(req_id, type(ex).__name__, str(ex), cmd)
        elif cmd == "close":
            try:
                for p in list(TABS.values()):
                    try:
                        p.close()
                    except Exception:
                        pass
                TABS = {}
                FRAMES.clear()
                if PERSISTENT and CONTEXT:
                    CONTEXT.close()
                elif BROWSER and not PERSISTENT:
                    BROWSER.close()
                if P:
                    P.stop()
            except Exception:
                pass
            PAGE = None
            BROWSER = None
            CONTEXT = None
            PERSISTENT = False
            P = None
            ACTIVE_ID = "0"
            ok(req_id, {"closed": True})

        else:
            fail(req_id, "UnknownCommand", f"unknown command: {cmd}")

    except PWTimeout as e:
        fail(req_id, "TimeoutError", str(e), cmd)
    except Exception as e:
        fail(req_id, type(e).__name__, str(e), cmd)


def _wait_stable(page):
    """等待页面导航稳定，不抛出异常"""
    for state in ("domcontentloaded", "networkidle"):
        try:
            page.wait_for_load_state(state, timeout=5000)
        except Exception:
            pass
    page.wait_for_timeout(500)


def _collect_snapshot(page, max_items):
    items = []
    elem_id = 0
    tags = ["input", "textarea", "select", "button", "a", "h1", "h2", "h3", "img", "label"]
    for tag in tags:
        els = page.query_selector_all(tag)
        for el in els:
            if len(items) >= max_items:
                break
            try:
                elem_id += 1
                box = el.bounding_box()
                roled = page.evaluate("el => el.getAttribute('role') || ''", el) if tag in ("a", "button", "input") else ""
                item = {
                    "id": elem_id,
                    "tag": tag,
                    "text": (el.inner_text() or "").strip()[:120],
                    "selector": _gen_selector(el),
                    "visible": box is not None,
                    "disabled": el.is_disabled() if box else None,
                }
                if roled:
                    item["role"] = roled
                if tag == "input":
                    item["type"] = el.get_attribute("type") or "text"
                    item["placeholder"] = el.get_attribute("placeholder") or ""
                    item["value"] = el.input_value() if box else ""
                if tag == "textarea":
                    item["placeholder"] = el.get_attribute("placeholder") or ""
                    item["value"] = el.input_value() if box else ""
                if tag == "a":
                    item["href"] = el.get_attribute("href") or ""
                if tag == "img":
                    item["alt"] = el.get_attribute("alt") or ""
                    item["src"] = el.get_attribute("src") or ""
                if box:
                    item["bbox"] = {"x": round(box["x"], 1), "y": round(box["y"], 1),
                                    "width": round(box["width"], 1), "height": round(box["height"], 1)}
                items.append(item)
            except Exception:
                pass
        if len(items) >= max_items:
            break
    return items


def _gen_selector(el):
    tag = el.evaluate("el => el.tagName.toLowerCase()")
    el_id = el.get_attribute("id")
    if el_id:
        return f"#{el_id}"
    name = el.get_attribute("name")
    if name:
        return f'{tag}[name="{name}"]'
    cls = el.get_attribute("class")
    if cls:
        classes = ".".join(c for c in cls.split() if c.isalpha() and not c.startswith("_"))[:60]
        if classes:
            return f"{tag}.{classes}"
    text = (el.inner_text() or "").strip()[:30]
    if text and len(text) > 2:
        return f'{tag}:has-text("{text}")'
    return tag


if __name__ == "__main__":
    log("browser_server ready, reading stdin...")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            handle(req)
        except json.JSONDecodeError as e:
            fail("", "ParseError", str(e))
