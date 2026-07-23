# Architecture (v2.6.0)

## Layers

```
CLI (browser_daemon.py)
  ├─ config / workflow / trace  → tools/* (no browser needed for some)
  └─ TCP daemon :8765
        └─ browser_server.py (Playwright page)
              └─ browser_workflows.py (compound actions)
                    ├─ dokobot (optional, public read)
                    └─ openvl (optional, vision)
```

## Ports

| Service | Default | Notes |
|---------|---------|--------|
| browser daemon | 8765 | Playwright control |
| config Web UI | 8767 | localhost + token only |
| openvl (external) | 8766 | independent project |

## Providers

| Layer | Primary | Fallback |
|-------|---------|----------|
| Reading | dokobot | browser |
| Interaction | browser | — |
| Vision | openvl | — |

## CLI contract

Every public command prints five header lines:

```
Status: ok|error|uncertain
Error code: ...
Provider used: browser|dokobot|openvl|mixed|none
Fallback used: yes|no
Trace: <id>
```

Outputs go through `tools/sanitize.py` (no raw secrets).

## Config priority

```
built-in defaults < config/defaults.yaml < user config.yaml < env < CLI flags
```

User config (Windows): `%LOCALAPPDATA%\Pi\browser\config.yaml`

## Workflows

- Specs: `workflow_specs/*.yaml`
- Runner: `tools/workflow_runner.py`
- Actions: allowlisted in config / runner (`read_url`, `search_read`, `diagnose`, …)

## Related docs

- `SKILL.md` — command reference for Pi agents
- `CONFIG.md` — config schema & presets
- `WEB_UI.md` — control panel API

## Browser profile & login state

- Daemon uses `chromium.launch(headless=True)` with an **ephemeral** in-memory profile for the process lifetime.
- `browser kill` / `restart` / crash **drops cookies and login state**.
- All tabs share one browser context (same cookie jar).
- `read_urls_parallel` / `new_page_for_url` open temporary pages on the same browser, outside the tab map, and close them after read.
- Long-lived login is not supported yet (future: `launch_persistent_context`). For real Chrome login state, prefer dokobot/`--local` against your everyday browser.
