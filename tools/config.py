#!/usr/bin/env python3
"""config.py — v2.6.0 配置体系：加载、校验、查询、preset"""

import os, sys, yaml, json, shutil, re
from pathlib import Path
from datetime import datetime

# 路径
BASE = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_DIR = BASE / "config"
DEFAULTS_FILE = CONFIG_DIR / "defaults.yaml"
PRESETS_DIR = CONFIG_DIR / "presets"

# 用户配置路径
if os.name == "nt":
    USER_CONFIG_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".pi")) / "Pi" / "browser"
else:
    USER_CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "pi" / "browser"

USER_CONFIG_FILE = USER_CONFIG_DIR / "config.yaml"
USER_PRESETS_DIR = USER_CONFIG_DIR / "presets"

# 允许的动作
ALLOWED_ACTIONS = {
    "read_url", "search_read", "diagnose", "diagnose_and_recover",
    "wait_text", "assert_text", "click_expect", "screenshot_ask",
}

VALID_PROVIDERS = {"auto", "browser", "dokobot", "openvl"}

SECRET_KEYS = {"api_key", "token", "password", "secret", "bearer", "authorization"}


def _deep_merge(base, override):
    """深度合并两个 dict，override 覆盖 base"""
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def load_defaults():
    """加载内置默认值"""
    default = {
        "providers": {
            "default": "auto",
            "browser": {"enabled": True},
            "dokobot": {"enabled": True, "base_url": "http://127.0.0.1:2024", "token_env": "DOKOBOT_TOKEN"},
            "openvl": {"enabled": False, "endpoint": "http://127.0.0.1:8766", "api_key_env": "OPENVL_API_KEY", "default_prompt": True},
        },
        "timeouts": {
            "page_load_ms": 30000, "action_ms": 10000, "read_ms": 30000,
            "openvl_ms": 60000, "workflow_step_ms": 60000,
        },
        "trace": {"enabled": True, "retention_days": 7, "sanitize": True},
        "screenshots": {"enabled": True, "retention_count": 50},
        "workflows": {
            "enabled": True, "directory": "workflow_specs",
            "allowed_actions": sorted(ALLOWED_ACTIONS),
        },
        "presets": {"default": "local"},
    }
    if DEFAULTS_FILE.exists():
        with open(DEFAULTS_FILE, encoding="utf-8") as f:
            default = _deep_merge(default, yaml.safe_load(f) or {})
    return default


def load_user_config():
    """加载用户配置，不存在返回空 dict"""
    if USER_CONFIG_FILE.exists():
        with open(USER_CONFIG_FILE, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def load_env_overrides():
    """从环境变量读取覆盖"""
    env = {}
    to_env = {
        "browser": {"token_env": "BROWSER_TOKEN"},
        "dokobot": {"token_env": "DOKOBOT_TOKEN"},
        "openvl": {"api_key_env": "OPENVL_API_KEY", "token_env": "OPENVL_TOKEN"},
    }
    # 通用 timeout 环境变量
    timeout_map = {
        "BROWSER_PAGE_LOAD_MS": ("timeouts", "page_load_ms"),
        "BROWSER_ACTION_MS": ("timeouts", "action_ms"),
        "BROWSER_READ_MS": ("timeouts", "read_ms"),
        "OPENVL_TIMEOUT_MS": ("timeouts", "openvl_ms"),
        "BROWSER_WORKFLOW_STEP_MS": ("timeouts", "workflow_step_ms"),
    }
    for env_key, (section, key) in timeout_map.items():
        val = os.environ.get(env_key)
        if val is not None:
            try:
                env.setdefault(section, {})[key] = int(val)
            except ValueError:
                pass
    return env


def load_effective(default=None, user=None, env=None):
    """按优先级合并：built-in < defaults < user < env"""
    cfg = load_defaults()
    if default:
        cfg = _deep_merge(cfg, default)
    if user is None:
        user = load_user_config()
    if user:
        cfg = _deep_merge(cfg, user)
    if env is None:
        env = load_env_overrides()
    if env:
        cfg = _deep_merge(cfg, env)
    return cfg


def get_sanitized_snapshot(cfg):
    """获取脱敏后的配置快照（供 trace 使用）"""
    p = cfg.get("providers", {})
    t = cfg.get("timeouts", {})
    return {
        "providers": {
            "default": p.get("default", "auto"),
            "browser_enabled": bool(p.get("browser", {}).get("enabled", True)),
            "dokobot_enabled": bool(p.get("dokobot", {}).get("enabled", True)),
            "openvl_enabled": bool(p.get("openvl", {}).get("enabled", False)),
        },
        "timeouts": {
            "page_load_ms": t.get("page_load_ms", 30000),
            "action_ms": t.get("action_ms", 10000),
            "openvl_ms": t.get("openvl_ms", 60000),
        },
        "trace": {"enabled": bool(cfg.get("trace", {}).get("enabled", True))},
        "screenshots": {"enabled": bool(cfg.get("screenshots", {}).get("enabled", True))},
    }


def has_plaintext_secret(cfg, path=""):
    """检查配置中是否包含明文密钥"""
    if isinstance(cfg, str):
        return False
    if isinstance(cfg, dict):
        for k, v in cfg.items():
            k_lower = k.lower()
            current_path = f"{path}.{k}" if path else k
            if k_lower in SECRET_KEYS and isinstance(v, str) and not v.startswith("$") and "_env" not in k_lower:
                return True, current_path
            result = has_plaintext_secret(v, current_path)
            if result:
                return result
    return False


def validate(cfg):
    """校验配置，返回 (ok: bool, errors: [str])"""
    errors = []

    # providers.default
    pd = cfg.get("providers", {}).get("default", "auto")
    if pd not in VALID_PROVIDERS:
        errors.append(f"providers.default 必须是 {', '.join(VALID_PROVIDERS)}，当前值：{pd}")

    # enabled 必须是 boolean
    for pname in ["browser", "dokobot", "openvl"]:
        p = cfg.get("providers", {}).get(pname, {})
        if "enabled" in p and not isinstance(p["enabled"], bool):
            errors.append(f"providers.{pname}.enabled 必须是 boolean")

    # timeout 必须是正整数
    for tname in cfg.get("timeouts", {}):
        val = cfg["timeouts"][tname]
        if not isinstance(val, (int, float)) or val <= 0:
            errors.append(f"timeouts.{tname} 必须是正整数，当前值：{val}")

    # retention_days/count 正整数
    for skey in ["retention_days", "retention_count"]:
        val = cfg.get("trace", {}).get(skey) or cfg.get("screenshots", {}).get(skey)
        # 不强制，有默认值
        if val is not None and (not isinstance(val, int) or val <= 0):
            errors.append(f"{skey} 必须是正整数")

    # allowed_actions
    aa = cfg.get("workflows", {}).get("allowed_actions", [])
    if aa:
        for a in aa:
            if a not in ALLOWED_ACTIONS:
                errors.append(f"workflows.allowed_actions 包含不允许的动作：{a}")
        # 拒绝 shell/python/import
        for bad in ["shell", "python", "import", "exec"]:
            if bad in aa:
                errors.append(f"workflows.allowed_actions 禁止包含：{bad}")

    # endpoint/base_url 格式检查
    for pname in ["dokobot", "openvl"]:
        p = cfg.get("providers", {}).get(pname, {})
        for url_key in ["base_url", "endpoint"]:
            val = p.get(url_key, "")
            if val and not re.match(r"^https?://(localhost|127\.0\.0\.1|\[\:\:1\]|\[::1\]|[\w\-\.]+)", val):
                errors.append(f"providers.{pname}.{url_key} 必须是 http/https URL：{val}")

    # 明文密钥检查
    secret_result = has_plaintext_secret(cfg)
    if secret_result:
        errors.append(f"配置中包含明文密钥：{secret_result[1]}")

    return len(errors) == 0, errors


def get_user_config_path():
    """返回用户配置路径"""
    return str(USER_CONFIG_FILE)


def get_presets():
    """返回可用 preset 列表"""
    presets = set()
    if PRESETS_DIR.exists():
        for f in sorted(PRESETS_DIR.glob("*.yaml")):
            presets.add(f.stem)
    if USER_PRESETS_DIR.exists():
        for f in sorted(USER_PRESETS_DIR.glob("*.yaml")):
            presets.add(f.stem)
    return sorted(presets)


def load_preset(name):
    """加载指定 preset"""
    # 先检查用户 presets
    up = USER_PRESETS_DIR / f"{name}.yaml"
    if up.exists():
        with open(up, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    # 再检查内置 presets
    bp = PRESETS_DIR / f"{name}.yaml"
    if bp.exists():
        with open(bp, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return None


def validate_workflow_spec(spec):
    """校验 workflow spec，返回 (ok, errors)"""
    errors = []
    if not isinstance(spec, dict):
        return False, ["workflow spec 必须是 YAML dict"]
    if "name" not in spec:
        errors.append("缺少 name")
    if "steps" not in spec or not isinstance(spec["steps"], list):
        errors.append("缺少 steps 或 steps 不是数组")
    else:
        variables = set()
        # 收集 inputs 作为可用变量
        for inp in spec.get("inputs", []):
            if isinstance(inp, dict) and "name" in inp:
                variables.add(inp["name"])
        for step in spec["steps"]:
            if not isinstance(step, dict):
                errors.append("step 必须是 dict")
                continue
            action = step.get("action", "")
            if not action:
                errors.append(f"step {step.get('id','?')} 缺少 action")
                continue
            if action not in ALLOWED_ACTIONS:
                errors.append(f"不允许的 action：{action}（step {step.get('id','?')}）")
            if action in ("shell", "python", "import", "exec"):
                errors.append(f"禁止的 action：{action}")
            # foreach 格式
            if "foreach" in step:
                foreach_val = step.get("foreach", "")
                as_val = step.get("as", "")
                if not as_val:
                    errors.append(f"foreach 缺少 as（step {step.get('id','?')}）")
                if not foreach_val:
                    errors.append(f"foreach 缺少列表变量（step {step.get('id','?')}）")
                # foreach 变量不在 inputs 中不报错（可能是 JSON 输入）
            # on_error
            oe = step.get("on_error", "stop")
            if oe not in ("continue", "stop"):
                errors.append(f"on_error 只能是 continue/stop（step {step.get('id','?')} 当前值：{oe}）")
            # 变量引用检查
            for arg_key, arg_val in step.get("args", {}).items():
                if isinstance(arg_val, str):
                    for var_ref in re.findall(r"\{(\w+)\}", arg_val):
                        if var_ref != "item_index" and "item" not in step.get("as", "") and var_ref not in variables:
                            # 检查是否在 save_as 中
                            save_keys = [s.get("save_as", "") for s in spec["steps"][:spec["steps"].index(step)]]
                            if not any(var_ref in sk for sk in save_keys):
                                pass  # lenient - 可能是外部变量
    return len(errors) == 0, errors
