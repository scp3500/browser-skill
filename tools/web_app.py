#!/usr/bin/env python3
"""web_app.py — v2.5.1 Web UI 控制面板（stdlib http.server，零依赖）"""
import os, sys, json, html, secrets, urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.contract import BrowserResult
from tools.render import render_json
from tools.trace_store import read_trace, list_traces, trace_step_to_step_result
from tools.sanitize import sanitize, sanitize_config_snapshot
from tools.config import get_user_config_path, load_effective, validate, load_preset, get_presets, validate_workflow_spec
from tools.config import USER_CONFIG_FILE, load_user_config
from tools.workflow_runner import list_workflows, load_spec, WORKFLOWS_DIR

try:
    import yaml
except ImportError:
    yaml = None


_TOKEN = secrets.token_hex(16)
_VERSION = "v2.5.1"


# ===== HTML templates (inline, 零模板引擎) =====

HTML_HEAD = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Browser Skill Control Panel</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; color: #333; }
  .nav { background: #1a1a2e; color: #fff; padding: 1rem 2rem; display: flex; gap: 2rem; align-items: center; }
  .nav a { color: #a8d8ea; text-decoration: none; font-size: 0.95rem; }
  .nav a:hover { color: #fff; }
  .nav h1 { font-size: 1.2rem; margin-right: auto; }
  .container { max-width: 1000px; margin: 2rem auto; padding: 0 1rem; }
  .card { background: #fff; border-radius: 8px; padding: 1.5rem; margin-bottom: 1rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
  .card h2 { font-size: 1.1rem; margin-bottom: 0.75rem; color: #1a1a2e; }
  .card pre { background: #f8f9fa; padding: 1rem; border-radius: 4px; overflow-x: auto; font-size: 0.85rem; }
  .badge { display: inline-block; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 0.8rem; font-weight: 600; }
  .badge-ok { background: #d4edda; color: #155724; }
  .badge-error { background: #f8d7da; color: #721c24; }
  .badge-uncertain { background: #fff3cd; color: #856404; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 1rem; }
  .stat { text-align: center; padding: 1rem; }
  .stat-value { font-size: 2rem; font-weight: 700; color: #1a1a2e; }
  .stat-label { font-size: 0.85rem; color: #666; margin-top: 0.25rem; }
  .msg-info { background: #d1ecf1; padding: 0.75rem; border-radius: 4px; margin-bottom: 1rem; font-size: 0.9rem; }
  .msg-error { background: #f8d7da; padding: 0.75rem; border-radius: 4px; margin-bottom: 1rem; font-size: 0.9rem; }
  .msg-ok { background: #d4edda; padding: 0.75rem; border-radius: 4px; margin-bottom: 1rem; font-size: 0.9rem; }
  button { background: #1a1a2e; color: #fff; border: none; padding: 0.5rem 1rem; border-radius: 4px; cursor: pointer; }
  button:hover { background: #16213e; }
  textarea { width: 100%; min-height: 200px; font-family: monospace; font-size: 0.85rem; padding: 0.75rem; border: 1px solid #ddd; border-radius: 4px; }
  .step { border-left: 3px solid #1a1a2e; padding-left: 1rem; margin-bottom: 0.75rem; }
  .step-line { font-size: 0.85rem; margin: 0.15rem 0; }
  table { width: 100%; border-collapse: collapse; }
  td, th { padding: 0.5rem; text-align: left; border-bottom: 1px solid #eee; font-size: 0.85rem; }
  th { font-weight: 600; color: #666; }
  .secret { color: #999; font-style: italic; }
</style>
</head>
<body>
<div class="nav">
  <h1>Browser Skill Control Panel</h1>
  <a href="/">Dashboard</a>
  <a href="/config">Config</a>
  <a href="/presets">Presets</a>
  <a href="/workflows">Workflows</a>
  <a href="/traces">Traces</a>
  <a href="/diagnostics">Diagnostics</a>
</div>
<div class="container">
"""

HTML_FOOT = """</div></body></html>"""


def _badge(status: str) -> str:
    cls = {"ok": "badge-ok", "error": "badge-error", "blocked": "badge-error", "uncertain": "badge-uncertain"}
    return f'<span class="badge {cls.get(status, "badge-uncertain")}">{status}</span>'


def _nav_token(query: str) -> str:
    """从 query string 提取 token"""
    params = urllib.parse.parse_qs(query)
    return params.get("token", [""])[0]


def _check_token(query: str) -> bool:
    return _nav_token(query) == _TOKEN


def _serve_file(path: str, content_type: str = "text/html; charset=utf-8"):
    """读取静态文件"""
    fp = Path(path)
    if fp.exists():
        return fp.read_bytes(), content_type
    return b"404", "text/plain"


class WebHandler(BaseHTTPRequestHandler):
    """HTTP 请求处理器"""

    def _send_json(self, data: dict, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def _send_html(self, html: str, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def _send_error(self, msg: str, status: int = 400):
        r = render_json(BrowserResult(status="error", error_code="invalid_input", provider_used="none",
                                       message=msg, trace_id="web"))
        self._send_json(r, status)

    def _check_auth(self):
        q = urllib.parse.urlparse(self.path).query
        if not _check_token(q):
            # Also check header
            token = self.headers.get("X-Token", "")
            if token != _TOKEN:
                self._send_error("unauthorized", 401)
                return False
        return True

    def log_message(self, format, *args):
        if "/api/" not in self.path:
            super().log_message(format, *args)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = parsed.query

        # API routes
        if path.startswith("/api/"):
            if not self._check_auth():
                return
            self._handle_api(path, query)
            return

        # Web UI pages
        if not _check_token(query):
            self._send_html(self._page_login())
            return

        page = self._page_for_path(path)
        self._send_html(page)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = parsed.query

        if not path.startswith("/api/"):
            self._send_error("POST only supported on API routes", 405)
            return
        if not _check_token(query):
            token = self.headers.get("X-Token", "")
            if token != _TOKEN:
                self._send_error("unauthorized", 401)
                return

        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len).decode("utf-8") if content_len else "{}"
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self._send_error("invalid JSON", 400)
            return

        self._handle_api_post(path, data)

    def _page_login(self):
        return HTML_HEAD + f'''
<div class="card">
  <h2>Browser Skill Control Panel</h2>
  <p style="margin-bottom:1rem">Token required. Use:</p>
  <pre>http://127.0.0.1:{self.server.server_port}/?token={_TOKEN}</pre>
</div>
''' + HTML_FOOT

    def _page_for_path(self, path: str) -> str:
        pages = {
            "/": self._page_dashboard,
            "/config": self._page_config,
            "/presets": self._page_presets,
            "/workflows": self._page_workflows,
            "/traces": self._page_traces,
            "/diagnostics": self._page_diagnostics,
        }
        page_fn = pages.get(path, self._page_dashboard)
        return page_fn()

    def _page_dashboard(self) -> str:
        cfg = load_effective()
        p = cfg.get("providers", {})
        wf_count = len(list_workflows())
        traces = list_traces(limit=5)
        return HTML_HEAD + f'''
<div class="card">
  <h2>Dashboard</h2>
  <div class="grid">
    <div class="stat"><div class="stat-value">{_VERSION}</div><div class="stat-label">Version</div></div>
    <div class="stat"><div class="stat-value">{p.get("default","auto")}</div><div class="stat-label">Default Provider</div></div>
    <div class="stat"><div class="stat-value">{wf_count}</div><div class="stat-label">Workflows</div></div>
    <div class="stat"><div class="stat-value">{len(traces)}</div><div class="stat-label">Recent Traces</div></div>
  </div>
</div>
<div class="card">
  <h2>Config Path</h2>
  <pre>{get_user_config_path()}</pre>
</div>
<div class="card">
  <h2>Provider Status</h2>
  <table>
    <tr><th>Provider</th><th>Status</th></tr>
    <tr><td>Browser</td><td>{"Enabled" if p.get("browser",{}).get("enabled",True) else "Disabled"}</td></tr>
    <tr><td>Dokobot</td><td>{"Enabled" if p.get("dokobot",{}).get("enabled",True) else "Disabled"}</td></tr>
    <tr><td>OpenVL</td><td>{"Enabled" if p.get("openvl",{}).get("enabled",False) else "Disabled"}</td></tr>
  </table>
</div>
''' + HTML_FOOT

    def _page_config(self) -> str:
        cfg = load_effective()
        yaml_str = yaml.dump(cfg, default_flow_style=False, allow_unicode=True) if yaml else json.dumps(cfg, indent=2, ensure_ascii=False)
        return HTML_HEAD + f'''
<div class="card">
  <h2>Effective Config</h2>
  <p style="font-size:0.85rem;color:#666;margin-bottom:0.5rem">
    Path: {get_user_config_path()}
  </p>
  <pre>{html.escape(yaml_str)}</pre>
</div>
<div class="card">
  <h2>Edit Config</h2>
  <p class="msg-info">
    Secret values (api_key, token, password, secret, bearer, authorization) must use _env variables, not plaintext.
    Config saved to: {USER_CONFIG_FILE}
  </p>
  <textarea id="config-yaml" oninput="document.getElementById('save-btn').style.display='inline-block'">{html.escape(yaml_str)}</textarea>
  <div style="margin-top:0.5rem">
    <button onclick="validateConfig()">Validate</button>
    <button id="save-btn" onclick="saveConfig()" style="display:none">Save</button>
  </div>
  <div id="config-result" style="margin-top:0.5rem"></div>
</div>
<script>
async function validateConfig() {{
  const r = await fetch('/api/config/validate?token={_TOKEN}', {{method:'POST', body:document.getElementById('config-yaml').value, headers:{{'Content-Type':'application/json'}}}}).then(r=>r.json());
  document.getElementById('config-result').innerHTML = '<div class="msg-'+(r.status==='ok'?'ok':'error')+'">'+(r.message||r.error_code||'')+'</div>';
}}
async function saveConfig() {{
  const r = await fetch('/api/config/save?token={_TOKEN}', {{method:'POST', body:JSON.stringify({{yaml:document.getElementById('config-yaml').value}}), headers:{{'Content-Type':'application/json'}}}}).then(r=>r.json());
  document.getElementById('config-result').innerHTML = '<div class="msg-'+(r.status==='ok'?'ok':'error')+'">'+(r.message||r.error_code||'')+'</div>';
  if(r.status==='ok') document.getElementById('save-btn').style.display='none';
}}
</script>
''' + HTML_FOOT

    def _page_presets(self) -> str:
        presets = get_presets()
        presets_list = "".join(f'<tr><td><a href="#" onclick="showPreset(\'{p}\')">{p}</a></td>'
                               f'<td><button onclick="applyPreset(\'{p}\')">Apply</button></td></tr>'
                               for p in presets)
        return HTML_HEAD + f'''
<div class="card">
  <h2>Presets</h2>
  <table>
    <tr><th>Name</th><th>Action</th></tr>
    {presets_list}
  </table>
  <div id="preset-result" style="margin-top:0.5rem"></div>
  <div id="preset-content" style="margin-top:0.5rem"></div>
</div>
<script>
async function showPreset(name) {{
  const r = await fetch('/api/presets/'+encodeURIComponent(name)+'?token={_TOKEN}').then(r=>r.json());
  if(r.message) document.getElementById('preset-content').innerHTML = '<pre>'+(r.message||'')+'</pre>';
}}
async function applyPreset(name) {{
  if(!confirm('Apply preset '+name+'?')) return;
  const r = await fetch('/api/presets/'+encodeURIComponent(name)+'/apply?token={_TOKEN}', {{method:'POST'}}).then(r=>r.json());
  document.getElementById('preset-result').innerHTML = '<div class="msg-'+(r.status==='ok'?'ok':'error')+'">'+(r.message||'')+'</div>';
}}
</script>
''' + HTML_FOOT

    def _page_workflows(self) -> str:
        wfs = list_workflows()
        wf_rows = "".join(f'<tr><td>{w}</td>'
                          f'<td><a href="#" onclick="showWorkflow(\'{w}\')">Show</a></td>'
                          f'<td><a href="#" onclick="validateWorkflow(\'{w}\')">Validate</a></td></tr>'
                          for w in wfs)
        return HTML_HEAD + f'''
<div class="card">
  <h2>Workflows</h2>
  <table>
    <tr><th>Name</th><th>Show</th><th>Validate</th></tr>
    {wf_rows}
  </table>
  <div id="wf-content" style="margin-top:0.5rem"></div>
  <div id="wf-result" style="margin-top:0.5rem"></div>
</div>
<script>
async function showWorkflow(name) {{
  const r = await fetch('/api/workflows/'+encodeURIComponent(name)+'?token={_TOKEN}').then(r=>r.json());
  document.getElementById('wf-content').innerHTML = r.message ? '<pre>'+r.message+'</pre>' : '';
}}
async function validateWorkflow(name) {{
  const r = await fetch('/api/workflows/'+encodeURIComponent(name)+'/validate?token={_TOKEN}', {{method:'POST'}}).then(r=>r.json());
  document.getElementById('wf-result').innerHTML = '<div class="msg-'+(r.status==='ok'?'ok':'error')+'">'+(r.message||r.error_code||'')+'</div>';
}}
</script>
''' + HTML_FOOT

    def _page_traces(self) -> str:
        traces = list_traces(limit=20)
        trace_rows = "".join(f'<tr><td><a href="#" onclick="showTrace(\'{t.get("trace_id","")}\')">{t.get("trace_id","?")[:30]}</a></td>'
                             f'<td>{_badge(t.get("status","?"))}</td>'
                             f'<td>{t.get("error_code","")}</td></tr>'
                             for t in traces if t.get("trace_id"))
        return HTML_HEAD + f'''
<div class="card">
  <h2>Traces</h2>
  <table>
    <tr><th>ID</th><th>Status</th><th>Error</th></tr>
    {trace_rows}
  </table>
  <div id="trace-result" style="margin-top:0.5rem"></div>
</div>
<script>
async function showTrace(id) {{
  const r = await fetch('/api/traces/'+encodeURIComponent(id)+'?token={_TOKEN}').then(r=>r.json());
  let html = '';
  if(r.message) html += '<div class="card"><pre>'+r.message+'</pre></div>';
  if(r.steps && r.steps.length) {{
    html += '<div class="card"><h2>Steps</h2>';
    r.steps.forEach((s,i) => {{
      html += '<div class="step">';
      html += '<div class="step-line"><strong>'+(i+1)+'. '+(s.name||s.action||'')+'</strong></div>';
      html += '<div class="step-line">Action: '+s.action+'</div>';
      html += '<div class="step-line">Status: '+_badge(s.status)+'</div>';
      html += '<div class="step-line">Error code: '+s.error_code+'</div>';
      html += '<div class="step-line">Provider: '+(s.provider_used||'none')+'</div>';
      html += '<div class="step-line">Fallback: '+(s.fallback_used?'yes':'no')+'</div>';
      html += '<div class="step-line">Child trace: '+(s.child_trace||'')+'</div>';
      html += '</div>';
    }});
    html += '</div>';
  }}
  document.getElementById('trace-result').innerHTML = html;
}}
const _badge = (s) => '{{"ok":"badge-ok","error":"badge-error","blocked":"badge-error","uncertain":"badge-uncertain"}}'[s]||'';
</script>
''' + HTML_FOOT

    def _page_diagnostics(self) -> str:
        env_vars = ["OPENVL_API_KEY", "DOKOBOT_TOKEN", "BROWSER_TOKEN", "BROWSER_PAGE_LOAD_MS"]
        env_rows = "".join(f'<tr><td>{v}</td><td>{"Configured" if os.environ.get(v) else "Missing"}</td></tr>'
                           for v in env_vars)
        return HTML_HEAD + f'''
<div class="card">
  <h2>Diagnostics</h2>
  <table>
    <tr><th>Environment Variable</th><th>Status</th></tr>
    {env_rows}
  </table>
  <div style="margin-top:1rem">
    <button onclick="testBrowser()">Test Browser</button>
    <div id="diag-result" style="margin-top:0.5rem"></div>
  </div>
</div>
<script>
async function testBrowser() {{
  document.getElementById('diag-result').innerHTML = '<div class="msg-info">Testing...</div>';
  try {{
    const r = await fetch('/api/diagnostics?token={_TOKEN}').then(r=>r.json());
    const html = '<div class="card"><pre>'+JSON.stringify(r,null,2)+'</pre></div>';
    document.getElementById('diag-result').innerHTML = html;
  }} catch(e) {{
    document.getElementById('diag-result').innerHTML = '<div class="msg-error">Error: '+e.message+'</div>';
  }}
}}
</script>
''' + HTML_FOOT

    # ===== API handlers =====

    def _handle_api(self, path: str, query: str):
        if path == "/api/health":
            r = BrowserResult(status="ok", error_code="ok", provider_used="none",
                              message=f"Browser Skill Control Panel {_VERSION}", trace_id="web")
            self._send_json(render_json(r))
        elif path == "/api/config":
            cfg = load_effective()
            sanitized = sanitize(cfg)
            r = BrowserResult(status="ok", error_code="ok", provider_used="none",
                              message="Effective config (sanitized)",
                              data={"config": sanitized}, trace_id="web")
            self._send_json(render_json(r))
        elif path == "/api/presets":
            presets = get_presets()
            r = BrowserResult(status="ok", error_code="ok", provider_used="none",
                              data={"presets": presets}, trace_id="web")
            self._send_json(render_json(r))
        elif path.startswith("/api/presets/"):
            name = path.split("/")[3]
            if path.endswith("/dry-run"):
                p = load_preset(name)
                if not p:
                    self._send_error(f"preset not found: {name}", 404)
                    return
                r = BrowserResult(status="ok", error_code="ok", provider_used="none",
                                  message=yaml.dump(p, default_flow_style=False, allow_unicode=True).strip() if yaml else json.dumps(p, indent=2),
                                  trace_id="web")
                self._send_json(render_json(r))
            else:
                p = load_preset(name)
                if not p:
                    self._send_error(f"preset not found: {name}", 404)
                    return
                r = BrowserResult(status="ok", error_code="ok", provider_used="none",
                                  message=yaml.dump(p, default_flow_style=False, allow_unicode=True).strip() if yaml else json.dumps(p, indent=2),
                                  trace_id="web")
                self._send_json(render_json(r))
        elif path == "/api/workflows":
            wfs = list_workflows()
            r = BrowserResult(status="ok", error_code="ok", provider_used="none",
                              data={"workflows": wfs}, trace_id="web")
            self._send_json(render_json(r))
        elif path.startswith("/api/workflows/"):
            name = path.split("/")[3]
            if path.endswith("/validate"):
                spec = load_spec(name)
                if not spec:
                    self._send_error(f"workflow not found: {name}", 404)
                    return
                try:
                    validate_workflow_spec(spec)
                    r = BrowserResult(status="ok", error_code="ok", provider_used="none",
                                      message="Workflow spec is valid", trace_id="web")
                except ValueError as e:
                    r = BrowserResult(status="error", error_code="invalid_config", provider_used="none",
                                      message=str(e), trace_id="web")
                self._send_json(render_json(r))
            else:
                spec = load_spec(name)
                if not spec:
                    self._send_error(f"workflow not found: {name}", 404)
                    return
                md_path = WORKFLOWS_DIR / f"{name}.md"
                content = md_path.read_text(encoding="utf-8") if md_path.exists() else yaml.dump(spec, default_flow_style=False, allow_unicode=True)
                r = BrowserResult(status="ok", error_code="ok", provider_used="none",
                                  message=content, trace_id="web")
                self._send_json(render_json(r))
        elif path == "/api/traces":
            traces = list_traces(limit=20)
            r = BrowserResult(status="ok", error_code="ok", provider_used="none",
                              data={"traces": sanitize(traces)}, trace_id="web")
            self._send_json(render_json(r))
        elif path.startswith("/api/traces/"):
            run_id = path.split("/")[3]
            data = read_trace(run_id)
            if not data:
                self._send_error(f"trace not found: {run_id}", 404)
                return
            # Extract steps for display
            wf = data.get("workflow", {})
            steps_raw = wf.get("steps", []) if wf else []
            steps = []
            for st in steps_raw:
                from tools.contract import StepResult as _SR
                steps.append(_SR(
                    name=st.get("id", ""),
                    action=st.get("action", ""),
                    status="ok" if st.get("ok") else "error",
                    error_code=st.get("error_code", "unknown"),
                    provider_used=st.get("provider_used", ""),
                    fallback_used=bool(st.get("fallback_used", False)),
                    child_trace=st.get("child_trace", ""),
                ))
            r = BrowserResult(status="ok", error_code="ok", provider_used="none",
                              data={"trace": sanitize(data)}, steps=steps, trace_id="web")
            self._send_json(render_json(r))
        elif path == "/api/diagnostics":
            import subprocess
            browser_ok = False
            dokobot_ok = False
            openvl_ok = False
            try:
                s = __import__("socket").socket()
                s.settimeout(2)
                s.connect(("127.0.0.1", 8765))
                s.close()
                browser_ok = True
            except:
                pass
            env_status = {}
            for v in ["OPENVL_API_KEY", "DOKOBOT_TOKEN", "BROWSER_TOKEN"]:
                env_status[v] = "configured" if os.environ.get(v) else "missing"
            r = BrowserResult(status="ok", error_code="ok", provider_used="none",
                              message="Diagnostics complete",
                              data={
                                  "browser_daemon": "running" if browser_ok else "not running",
                                  "dokobot": "check environment",
                                  "openvl": "check environment",
                                  "environment": env_status,
                              }, trace_id="web")
            self._send_json(render_json(r))
        else:
            self._send_error("not found", 404)

    def _handle_api_post(self, path: str, data: dict):
        if path == "/api/config/validate":
            try:
                cfg = None
                if isinstance(data, dict):
                    yaml_str = data.get("yaml", "")
                    if yaml_str:
                        cfg = yaml.safe_load(yaml_str) if yaml else json.loads(yaml_str)
                    else:
                        cfg = data  # treat raw dict as config
                else:
                    cfg = yaml.safe_load(data) if yaml else data
                if not isinstance(cfg, dict):
                    cfg = {}
            except Exception as e:
                self._send_error(f"YAML parse error: {e}")
                return
            ok, errors = validate(cfg)
            if ok:
                r = BrowserResult(status="ok", error_code="ok", provider_used="none",
                                  message="Config is valid", trace_id="web")
            else:
                r = BrowserResult(status="error", error_code="invalid_config", provider_used="none",
                                  message=errors[0], trace_id="web")
            self._send_json(render_json(r))
        elif path == "/api/config/save":
            try:
                yaml_str = data.get("yaml", "")
                cfg = yaml.safe_load(yaml_str) if yaml else json.loads(yaml_str)
            except Exception as e:
                self._send_error(f"YAML parse error: {e}")
                return
            ok, errors = validate(cfg)
            if not ok:
                r = BrowserResult(status="error", error_code="invalid_config", provider_used="none",
                                  message=errors[0], trace_id="web")
                self._send_json(render_json(r))
                return
            USER_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            if yaml:
                with open(USER_CONFIG_FILE, "w", encoding="utf-8") as f:
                    yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True)
            else:
                with open(USER_CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, indent=2, ensure_ascii=False)
            r = BrowserResult(status="ok", error_code="ok", provider_used="none",
                              message=f"Config saved to {USER_CONFIG_FILE}", trace_id="web")
            self._send_json(render_json(r))
        elif path.startswith("/api/presets/") and path.endswith("/apply"):
            name = path.split("/")[3]
            p = load_preset(name)
            if not p:
                self._send_error(f"preset not found: {name}", 404)
                return
            USER_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            if yaml:
                with open(USER_CONFIG_FILE, "w", encoding="utf-8") as f:
                    yaml.dump(p, f, default_flow_style=False, allow_unicode=True)
            else:
                with open(USER_CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump(p, f, indent=2, ensure_ascii=False)
            r = BrowserResult(status="ok", error_code="ok", provider_used="none",
                              message=f"Preset '{name}' applied", trace_id="web")
            self._send_json(render_json(r))
        elif path.startswith("/api/workflows/") and path.endswith("/validate"):
            name = path.split("/")[3]
            spec = load_spec(name)
            if not spec:
                self._send_error(f"workflow not found: {name}", 404)
                return
            try:
                validate_workflow_spec(spec)
                r = BrowserResult(status="ok", error_code="ok", provider_used="none",
                                  message="Workflow spec is valid", trace_id="web")
            except ValueError as e:
                r = BrowserResult(status="error", error_code="invalid_config", provider_used="none",
                                  message=str(e), trace_id="web")
            self._send_json(render_json(r))
        else:
            self._send_error("not found", 404)


def create_server(port: int = 8765, host: str = "127.0.0.1") -> HTTPServer:
    """创建 Web 服务器实例"""
    if host != "127.0.0.1":
        raise ValueError("config_web only supports 127.0.0.1")
    server = HTTPServer((host, port), WebHandler)
    return server
