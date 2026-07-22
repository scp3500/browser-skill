#!/usr/bin/env python3
"""sanitize.py — v2.5.1 全局脱敏"""
import re
from typing import Any

SECRET_KEYS = {"api_key", "token", "password", "secret", "bearer", "authorization"}
_REDACTED = "***REDACTED***"


def sanitize(obj: Any) -> Any:
    """递归脱敏：替换敏感 key 的值为 ***REDACTED***"""
    if isinstance(obj, str):
        return _redact_inline(obj)
    elif isinstance(obj, dict):
        return {k: _REDACTED if k.lower() in SECRET_KEYS else sanitize(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize(item) for item in obj]
    elif isinstance(obj, (int, float, bool)) or obj is None:
        return obj
    return obj


def _redact_inline(text: str) -> str:
    """替换行内密钥模式"""
    for prefix in ["sk-", "tok_", "ghp_", "gho_", "ghu_", "ghs_"]:
        if prefix in text:
            text = re.sub(re.escape(prefix) + r"\S+", _REDACTED, text)
    # Bearer token
    text = re.sub(r"Bearer\s+\S+", "Bearer ***REDACTED***", text)
    # API key in query
    text = re.sub(r"(api[_-]?key|token|secret)=\S+", r"\1=" + _REDACTED, text, flags=re.IGNORECASE)
    return text


def sanitize_config_snapshot(cfg: dict) -> dict:
    """配置快照脱敏（供 trace 使用）"""
    p = cfg.get("providers", {})
    t = cfg.get("timeouts", {})
    result = {
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
    return sanitize(result)


def has_plaintext_secret(cfg: Any, path: str = "") -> tuple:
    """检查配置中是否包含明文密钥。返回 (found: bool, key_path: str)"""
    if not isinstance(cfg, dict):
        return False, ""
    for k, v in cfg.items():
        k_lower = k.lower()
        cur = f"{path}.{k}" if path else k
        if k_lower in SECRET_KEYS and isinstance(v, str) and not v.startswith("$") and "_env" not in k_lower:
            return True, cur
        if isinstance(v, dict):
            found, sub = has_plaintext_secret(v, cur)
            if found:
                return found, sub
    return False, ""
