#!/usr/bin/env python3
"""workflow_result.py — v2.7.0 统一 workflow result contract"""
from dataclasses import dataclass, field
from typing import Optional

NL = chr(10)
STATUSES = {"ok", "error", "blocked", "uncertain"}
ERROR_CODES = {
    "ok", "blocked_captcha", "blocked_login", "blocked_popup",
    "blank_page", "network_error", "timeout", "not_found",
    "no_search_results", "irrelevant_results",
    "read_failed", "provider_failed", "invalid_mode", "unknown", "blocked_bot_detection", "risky_action", "unverified_source", "invalid_input", "invalid_config",
}
PROVIDERS = {"browser", "dokobot", "openvl", "mixed", "none"}


def validate_status(s):
    if s not in STATUSES:
        raise ValueError(f"invalid status '{s}', allowed: {', '.join(sorted(STATUSES))}")
    return s


def validate_error_code(e):
    if e not in ERROR_CODES:
        raise ValueError(f"invalid error_code '{e}', allowed: {', '.join(sorted(ERROR_CODES))}")
    return e


def validate_provider(p):
    if p not in PROVIDERS:
        raise ValueError(f"invalid provider '{p}', allowed: {', '.join(sorted(PROVIDERS))}")
    return p


@dataclass
class WorkflowResult:
    status: str = "ok"
    error_code: str = "ok"
    provider_used: str = "none"
    fallback_used: bool = False
    trace_id: Optional[str] = None
    message: Optional[str] = None
    url: Optional[str] = None
    title: Optional[str] = None
    text: Optional[str] = None
    data: dict = field(default_factory=dict)

    def __post_init__(self):
        validate_status(self.status)
        validate_error_code(self.error_code)
        validate_provider(self.provider_used)

    def to_dict(self):
        return {
            "status": self.status,
            "error_code": self.error_code,
            "provider_used": self.provider_used,
            "fallback_used": self.fallback_used,
            "trace_id": self.trace_id,
            "message": self.message,
            "url": self.url,
            "title": self.title,
            "text": (self.text or "")[:500],
            "data": self.data,
        }

    def summary(self):
        """Short summary dict for trace.json"""
        return {
            "status": self.status,
            "error_code": self.error_code,
            "provider_used": self.provider_used,
            "fallback_used": self.fallback_used,
            "trace_id": self.trace_id,
            "url": self.url,
            "title": self.title,
        }

    def cli_header(self):
        """5-line standardized CLI header"""
        lines = [f"Status: {self.status}"]
        lines.append(f"Error code: {self.error_code}")
        lines.append(f"Provider used: {self.provider_used}")
        lines.append(f"Fallback used: {'yes' if self.fallback_used else 'no'}")
        if self.trace_id:
            lines.append(f"Trace: {self.trace_id}")
        return NL.join(lines)


# ===== Error code mapping =====
BLOCKING_ISSUE_MAP = {
    "none": "ok", "captcha": "blocked_captcha", "login": "blocked_login",
    "popup": "blocked_popup", "network_error": "network_error",
    "blank_page": "blank_page", "bot_detection": "blocked_bot_detection", "other": "unknown",
}


def error_code_from_diagnose(vision_text):
    for line in vision_text.split(NL):
        line = line.strip()
        if line.startswith("Status:"):
            vl = line.split(":", 1)[1].strip().lower()
            if vl == "ok":
                return "ok"
            if vl == "uncertain":
                return "unknown"
        if line.startswith("Blocking issue:"):
            issue = line.split(":", 1)[1].strip().strip("[]").lower()
            return BLOCKING_ISSUE_MAP.get(issue, "unknown")
    return "unknown"
