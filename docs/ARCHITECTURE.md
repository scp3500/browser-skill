# Architecture (v2.5.1)

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
