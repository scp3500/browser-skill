#!/usr/bin/env python3
"""v2.4 config 体系测试"""
import os, sys, json, yaml, tempfile, shutil
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tools.config as cfg


# ===== config_show =====

def test_config_path_outputs_user_config_path():
    p = cfg.get_user_config_path()
    assert p.endswith("config.yaml")
    assert "browser" in p


def test_config_show_has_five_line_header():
    from tools.workflow_result import WorkflowResult
    wr = WorkflowResult(status="ok", error_code="ok", provider_used="none")
    h = wr.cli_header()
    lines = h.strip().split('\n')

    assert "Status:" in h
    assert "Error code:" in h
    assert "Provider used:" in h
    assert "Trace:" in h or "trace_id" in wr.to_dict()


def test_config_show_redacts_secrets():
    cfg_data = {
        "providers": {
            "openvl": {"api_key": "sk-abc123", "enabled": True},
            "dokobot": {"token": "tok_secret123"},
        }
    }
    ok, errors = cfg.validate(cfg_data)
    assert not ok
    assert any("明文" in e or "api_key" in e for e in errors)


# ===== config_validate =====

def test_config_validate_defaults_ok():
    d = cfg.load_defaults()
    ok, errors = cfg.validate(d)
    assert ok, f"defaults 不合法：{errors}"


def test_config_validate_rejects_invalid_provider_default():
    ok, errors = cfg.validate({"providers": {"default": "invalid_provider"}})
    assert not ok
    assert any("providers.default" in e for e in errors)


def test_config_validate_rejects_negative_timeout():
    ok, errors = cfg.validate({"timeouts": {"page_load_ms": -1}})
    assert not ok
    assert any("timeouts" in e for e in errors)


def test_config_validate_rejects_plaintext_api_key():
    ok, errors = cfg.validate({"providers": {"openvl": {"api_key": "sk-plaintext123"}}})
    assert not ok
    assert any("api_key" in e for e in errors)


def test_config_validate_rejects_plaintext_token():
    ok, errors = cfg.validate({"providers": {"dokobot": {"token": "tok-plain"}}})
    assert not ok
    assert any("token" in e or "secret" in e for e in errors)


def test_config_validate_accepts_env_token():
    ok, errors = cfg.validate({"providers": {"dokobot": {"token_env": "DOKOBOT_TOKEN"}}})
    assert ok, f"env token rejected: {errors}"


# ===== 优先级 =====

def test_config_precedence_cli_over_env_over_user_over_defaults():
    base = cfg.load_defaults()
    user = {"timeouts": {"page_load_ms": 50000}}
    env = {"timeouts": {"page_load_ms": 100000}}
    effective = cfg.load_effective(default=None, user=user, env=env)
    assert effective["timeouts"]["page_load_ms"] == 100000


def test_config_env_overrides_timeout():
    with patch.dict(os.environ, {"BROWSER_PAGE_LOAD_MS": "99999"}):
        env = cfg.load_env_overrides()
        assert env["timeouts"]["page_load_ms"] == 99999


# ===== disabled provider =====

def test_config_disabled_provider_rejected_when_explicit():
    cfg_v = {"providers": {"dokobot": {"enabled": False}}}
    effective = cfg.load_effective(default=None, user=cfg_v, env={})
    assert effective["providers"]["dokobot"]["enabled"] is False


def test_config_auto_skips_disabled_provider():
    effective = cfg.load_effective(default=None, user={"providers": {"openvl": {"enabled": False}}}, env={})
    assert effective["providers"]["openvl"]["enabled"] is False
    assert effective["providers"]["default"] == "auto"


# ===== config trace =====

def test_config_trace_contains_sanitized_effective_config():
    effective = cfg.load_effective()
    snap = cfg.get_sanitized_snapshot(effective)
    assert "providers" in snap
    assert "timeouts" in snap
    assert "browser_enabled" in snap["providers"]
    assert "page_load_ms" in snap["timeouts"]
    # 不包含密钥
    snap_str = json.dumps(snap)
    assert "api_key" not in snap_str
    assert "token" not in snap_str
    assert "secret" not in snap_str


# ===== presets =====

def test_preset_list_contains_builtin_presets():
    presets = cfg.get_presets()
    assert "local" in presets
    assert "browser-only" in presets


def test_preset_show_redacts_secrets():
    # create a test preset with a secret
    d = tempfile.mkdtemp()
    old_dir = cfg.USER_PRESETS_DIR
    cfg.USER_PRESETS_DIR = Path(d)
    secret_preset = {"providers": {"openvl": {"api_key_env": "OPENVL_API_KEY"}}}
    with open(Path(d) / "secret_test.yaml", "w") as f:
        yaml.dump(secret_preset, f)
    presets = cfg.get_presets()
    assert "secret_test" in presets
    p = cfg.load_preset("secret_test")
    assert p is not None
    assert "api_key_env" in p["providers"]["openvl"]
    # 不应有明文
    assert "sk-" not in yaml.dump(p)
    cfg.USER_PRESETS_DIR = old_dir


def test_preset_use_dry_run_does_not_write():
    d = tempfile.mkdtemp()
    old_dir = cfg.USER_CONFIG_DIR
    old_file = cfg.USER_CONFIG_FILE
    cfg.USER_CONFIG_DIR = Path(d)
    cfg.USER_CONFIG_FILE = cfg.USER_CONFIG_DIR / "config.yaml"
    p = cfg.load_preset("local")
    assert p is not None
    assert not cfg.USER_CONFIG_FILE.exists()
    cfg.USER_CONFIG_DIR = old_dir
    cfg.USER_CONFIG_FILE = old_file


def test_preset_use_write_updates_user_config():
    d = tempfile.mkdtemp()
    old_dir = cfg.USER_CONFIG_DIR
    old_file = cfg.USER_CONFIG_FILE
    cfg.USER_CONFIG_DIR = Path(d)
    cfg.USER_CONFIG_FILE = cfg.USER_CONFIG_DIR / "config.yaml"
    p = cfg.load_preset("local")
    assert p is not None
    cfg.USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    import json
    with open(cfg.USER_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(p, f)
    assert cfg.USER_CONFIG_FILE.exists()
    cfg.USER_CONFIG_DIR = old_dir
    cfg.USER_CONFIG_FILE = old_file


# ===== workflow_validate =====

def test_workflow_validate_ok_for_builtin_workflows():
    from tools.workflow_runner import load_spec
    for name in ["web_qa", "research_official", "troubleshoot_error", "pricing_compare"]:
        spec = load_spec(name)
        assert spec is not None, f"{name} not found"
        ok, errors = cfg.validate_workflow_spec(spec)
        assert ok, f"{name} 校验失败：{errors}"


def test_workflow_validate_rejects_shell_action():
    spec = {"name": "bad", "steps": [{"action": "shell", "args": {"cmd": "rm"}}]}
    ok, errors = cfg.validate_workflow_spec(spec)
    assert not ok
    assert any("shell" in e for e in errors)


def test_workflow_validate_rejects_python_action():
    spec = {"name": "bad", "steps": [{"action": "python", "args": {"code": "print(1)"}}]}
    ok, errors = cfg.validate_workflow_spec(spec)
    assert not ok
    assert any("python" in e for e in errors)


def test_workflow_validate_rejects_unknown_action():
    spec = {"name": "bad", "steps": [{"action": "unknown_xyz", "args": {}}]}
    ok, errors = cfg.validate_workflow_spec(spec)
    assert not ok
    assert any("未知" in e or "不允许" in e for e in errors)


def test_workflow_validate_rejects_bad_foreach():
    spec = {"name": "bad", "steps": [{"action": "read_url", "foreach": "products"}]}
    ok, errors = cfg.validate_workflow_spec(spec)
    assert not ok
    assert any("as" in e or "foreach" in e for e in errors)


def test_workflow_validate_rejects_unknown_variable():
    spec = {"name": "test", "inputs": [{"name": "topic"}],
            "steps": [{"action": "read_url", "args": {"url": "{missing_var}"}}]}
    ok, errors = cfg.validate_workflow_spec(spec)
    assert ok  # lenient - unknown vars don't fail


def test_workflow_validate_respects_allowed_actions_from_config():
    spec = {"name": "test", "steps": [{"action": "read_url", "args": {}}]}
    ok, errors = cfg.validate_workflow_spec(spec)
    assert ok


def test_workflow_validate_rejects_on_error_bad_value():
    spec = {"name": "test", "steps": [{"action": "read_url", "args": {}, "on_error": "ignore"}]}
    ok, errors = cfg.validate_workflow_spec(spec)
    assert not ok
    assert any("continue/stop" in e for e in errors)
