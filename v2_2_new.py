"""v2.2 new workflows — appended to browser_workflows.py"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from browser_agent import step
from tools.workflow_result import WorkflowResult

# These functions are appended to browser_workflows.py manually
# They use the same helpers (_run_openvl, _run_dokobot, _inject_header) defined above

def wf_read_url(args, ctx):
    url = args.get("url",""); chars = int(args.get("chars",args.get("max_chars","1000"))); provider = args.get("provider","auto")
    from browser_workflows import _run_dokobot, step, WorkflowResult, _inject_header
    attempts = []
    if provider == "dokobot":
        r = _run_dokobot("read",{"url":url}); ok = r.get("ok")
        text = (r.get("result",{}).get("text","") or "")[:chars] if ok else ""
        attempts.append({"provider":"dokobot","status":"ok" if ok else "error","error_code":"ok" if ok else "provider_failed"})
        ec = "ok" if ok else "provider_failed"
        wr = WorkflowResult(status="ok" if ok else "error",error_code=ec,provider_used="dokobot",url=url,text=text,data={"attempts":attempts})
        return {"ok":ok,"steps":[{"index":1,"cmd":"read_url","ok":ok}],"_wr":wr,"_url":url,"_text":text}
    if provider == "browser":
        r1 = step("browser","goto",{"url":url})
        if not r1.get("ok"):
            wr = WorkflowResult(status="error",error_code="network_error",provider_used="browser",url=url,data={"attempts":[{"provider":"browser","status":"error","error_code":"network_error"}]})
            return {"ok":False,"steps":[{"index":1,"cmd":"goto","ok":False}],"_wr":wr}
        r2 = step("browser","extract_text",{"selector":"body"})
        text = (r2.get("result",{}).get("text","") or "")[:chars] if r2.get("ok") else ""
        ok = r2.get("ok") and bool(text.strip())
        attempts.append({"provider":"browser","status":"ok" if ok else "error","error_code":"ok" if ok else "read_failed"})
        wr = WorkflowResult(status="ok" if ok else "error",error_code="ok" if ok else "read_failed",provider_used="browser",url=url,text=text,data={"attempts":attempts})
        return {"ok":ok,"steps":[{"index":1,"cmd":"goto","ok":r1.get("ok")},{"index":2,"cmd":"read","ok":r2.get("ok")}],"_wr":wr,"_url":url,"_text":text}
    # auto
    r1 = _run_dokobot("read",{"url":url}); ok1 = r1.get("ok")
    text1 = (r1.get("result",{}).get("text","") or "")[:chars] if ok1 else ""
    attempts.append({"provider":"dokobot","status":"ok" if (ok1 and text1.strip()) else "error","error_code":"ok" if (ok1 and text1.strip()) else ("read_failed" if ok1 else "provider_failed")})
    if ok1 and text1.strip():
        wr = WorkflowResult(status="ok",error_code="ok",provider_used="dokobot",url=url,text=text1,data={"attempts":attempts})
        return {"ok":True,"steps":[{"index":1,"cmd":"read_url","ok":True}],"_wr":wr,"_url":url,"_text":text1}
    attempts.append({"provider":"browser","status":"attempting","error_code":"unknown"})
    r2 = step("browser","goto",{"url":url})
    if not r2.get("ok"):
        attempts[-1] = {"provider":"browser","status":"error","error_code":"network_error"}
        wr = WorkflowResult(status="error",error_code="read_failed",provider_used="mixed",fallback_used=True,url=url,data={"attempts":attempts})
        return {"ok":False,"steps":[{"index":1,"cmd":"dokobot","ok":ok1},{"index":2,"cmd":"goto","ok":False}],"_wr":wr}
    r3 = step("browser","extract_text",{"selector":"body"})
    text2 = (r3.get("result",{}).get("text","") or "")[:chars] if r3.get("ok") else ""
    ok2 = r3.get("ok") and bool(text2.strip())
    attempts[-1] = {"provider":"browser","status":"ok" if ok2 else "error","error_code":"ok" if ok2 else "read_failed"}
    if ok2:
        wr = WorkflowResult(status="ok",error_code="ok",provider_used="mixed",fallback_used=True,url=url,text=text2,data={"attempts":attempts})
        return {"ok":True,"steps":[{"index":1,"cmd":"dokobot","ok":ok1},{"index":2,"cmd":"goto","ok":True},{"index":3,"cmd":"read","ok":True}],"_wr":wr,"_url":url,"_text":text2}
    wr = WorkflowResult(status="error",error_code="read_failed",provider_used="mixed",fallback_used=True,url=url,data={"attempts":attempts})
    return {"ok":False,"steps":[{"index":1,"cmd":"dokobot","ok":ok1},{"index":2,"cmd":"goto","ok":True},{"index":3,"cmd":"read","ok":False}],"_wr":wr}
