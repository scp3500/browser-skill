#!/usr/bin/env python3
"""openvl_tool.py — OpenVL CLI wrapper + scene prompts"""
import subprocess, os, shutil

_OPENVL = shutil.which("openvl") or shutil.which("openvl.cmd") or ""
if not _OPENVL:
    npm = os.environ.get("APPDATA", "") + "/npm"
    for c in [npm + "/openvl.cmd", npm + "/openvl"]:
        if os.path.exists(c): _OPENVL = c; break

NL = "\n"

PROMPTS = {
    "diagnose": (
        "DIAGNOSE this browser screenshot. You MUST fill in ALL lines."
        + NL + "Replace each [value] with the correct answer."
        + NL + "Status: [ok|blocked|uncertain]"
        + NL + "Blocking issue: [none|captcha|login|popup|network_error|blank_page|other]"
        + NL + "Reason: [one sentence]"
        + NL + "Suggested action: [what to click or do next]"
    ),
    "search": (
        "Judge if this page content is relevant to the target."
        + NL + "Target: {question}"
        + NL + "DO NOT describe the page layout."
        + NL + "Answer ONLY with this exact format:"
        + NL + "Page type: [search_results|image_results|detail_page|error_page|unknown]"
        + NL + "Relevance: [high|medium|low|none|uncertain]"
        + NL + "Best result: [title or description]"
        + NL + "Best next action: [what to do]"
    ),
    "image_select": (
        "Select target images from the provided images."
        + NL + "Target: {question}"
        + NL + "Output exactly this format:"
        + NL + "Selected: [1|2|3|none|uncertain]"
        + NL + "Reason: [why this image]"
        + NL + "Candidates:"
        + NL + "[1] relevance: [high|medium|low|decorative]"
        + NL + "[2] relevance: [high|medium|low|decorative]"
        + NL + "[3] relevance: [high|medium|low|decorative]"
    ),
    "ocr": (
        "Extract visible text from this screenshot."
        + NL + "Output exactly this format with no extra text:"
        + NL + "Text:"
        + NL + "<visible text only>"
        + NL + ""
        + NL + "Do NOT describe the image."
        + NL + "Do NOT add explanation."
        + NL + "If no text is visible, output exactly:"
        + NL + "Text:"
        + NL + "NO_TEXT"
    ),
}

ALLOWED_MODES = {
    "screenshot_ask": ["diagnose", "search", "ocr", "describe"],
    "ask_image": ["describe", "ocr", "image_select"],
    "image_page": ["image_select", "describe"],
    "describe": ["describe", "diagnose", "search", "ocr"],
}

def validate_mode(cmd_name, mode):
    allowed = ALLOWED_MODES.get(cmd_name, ["describe"])
    if mode not in allowed:
        raise ValueError(f"invalid mode '{mode}' for {cmd_name}, allowed: {', '.join(allowed)}")

def _get_prompt(mode, question):
    if mode == "describe":
        return question or ""
    p = PROMPTS.get(mode)
    if not p:
        return question or ""
    if "{question}" in p:
        return p.replace("{question}", question or "(no specific target)")
    return p

def _clean_prompt(p):
    """Remove newlines from CLI args (cmd.exe truncates at newline)"""
    return p.replace("\n", " ").replace("\r", " ") if p else p

def call(cmd, args=None):
    if args is None:
        args = {}
    try:
        mode = args.get("mode", "describe")
        question = args.get("question", "")
        if cmd == "describe":
            img = args.get("image_path", args.get("path", ""))
            imgs = args.get("image_paths", [])
            if not img and not imgs:
                return {"ok": False, "error": {"type": "ArgError", "message": "image_path required", "tool": "openvl", "cmd": cmd}}
            no_default = mode != "describe"
            if imgs:
                paths = [p for p in imgs[:10] if os.path.exists(p)]
                if not paths:
                    return {"ok": False, "error": {"type": "ArgError", "message": "no valid images", "tool": "openvl", "cmd": cmd}}
                cli = [_OPENVL or "openvl"] + paths
            else:
                cli = [_OPENVL or "openvl", img]
            if no_default:
                cli.append("-P")
            prompt = _get_prompt(mode, question)
            if prompt:
                cli.append(_clean_prompt(prompt))
            elif question:
                cli.append(question)
            flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
            r = subprocess.run(cli, capture_output=True, text=True, timeout=args.get("timeout", 120), creationflags=flags, encoding="utf-8")
            if r.returncode != 0:
                return {"ok": False, "error": {"type": "SubprocessError", "message": r.stderr[:300] or r.stdout[:300], "tool": "openvl", "cmd": cmd}}
            desc = r.stdout.strip()
            return {"ok": True, "result": {"text": desc, "image": img or paths, "question": question, "mode": mode}, "observation": f"Vision: {desc[:150]}"}
        elif cmd == "clipboard":
            no_default = mode != "describe"
            cli = [_OPENVL or "openvl", "-c"]
            if no_default:
                cli.append("-P")
            prompt = _get_prompt(mode, question)
            if prompt:
                cli.append(_clean_prompt(prompt))
            elif question:
                cli.append(question)
            flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
            r = subprocess.run(cli, capture_output=True, text=True, timeout=120, creationflags=flags, encoding="utf-8")
            if r.returncode != 0:
                return {"ok": False, "error": {"type": "SubprocessError", "message": r.stderr[:300] or r.stdout[:300], "tool": "openvl", "cmd": cmd}}
            desc = r.stdout.strip()
            return {"ok": True, "result": {"text": desc, "question": question, "mode": mode}, "observation": f"Vision: {desc[:150]}"}
        else:
            return {"ok": False, "error": {"type": "UnknownCmd", "message": f"unknown: {cmd}", "tool": "openvl", "cmd": cmd}}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": {"type": "TimeoutError", "message": "openvl timed out", "tool": "openvl", "cmd": cmd}}
    except Exception as e:
        return {"ok": False, "error": {"type": type(e).__name__, "message": str(e), "tool": "openvl", "cmd": cmd}}
