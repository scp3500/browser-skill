#!/usr/bin/env python3
"""contract.py — v2.7.0 统一 contract 模型"""
from dataclasses import dataclass, field
from typing import Any, Optional

NL = chr(10)

STATUSES = {"ok", "error", "blocked", "uncertain"}
ERROR_CODES = {
    "ok", "blocked_captcha", "blocked_login", "blocked_popup",
    "blank_page", "network_error", "timeout", "not_found",
    "no_search_results", "irrelevant_results",
    "read_failed", "provider_failed", "invalid_mode", "unknown",
    "blocked_bot_detection", "risky_action", "unverified_source",
    "invalid_input", "invalid_config",
}
PROVIDERS = {"browser", "dokobot", "openvl", "mixed", "none"}


class ContractError(ValueError):
    """违反 contract 时的异常"""
    pass


@dataclass
class StepResult:
    """workflow step 结果模型"""
    name: str = ""
    action: str = ""
    status: str = "ok"
    error_code: str = "ok"
    provider_used: str = "none"
    fallback_used: bool = False
    child_trace: Optional[str] = None

    def __post_init__(self):
        if self.error_code not in ERROR_CODES:
            raise ContractError(f"invalid error_code: {self.error_code}")


@dataclass
class BrowserResult:
    """统一返回结果。所有命令必须返回此类型。"""
    status: str = "ok"
    error_code: str = "ok"
    provider_used: str = "none"
    fallback_used: bool = False
    trace_id: Optional[str] = None  # 渲染前必须赋值
    message: Optional[str] = None
    data: dict[str, Any] = field(default_factory=dict)
    steps: list[StepResult] = field(default_factory=list)
    _raw: Optional[dict] = None  # 原始返回（transition / 回退兼容）

    def __post_init__(self):
        # status/error_code 一致性
        if self.status == "ok" and self.error_code != "ok":
            raise ContractError(f"status=ok 时 error_code 必须为 ok (got {self.error_code})")
        if self.status != "ok" and self.error_code == "ok":
            raise ContractError(f"status!={self.status} 时 error_code 不能为 ok")
        if self.provider_used not in PROVIDERS:
            raise ContractError(f"invalid provider_used: {self.provider_used}")
        if not isinstance(self.fallback_used, bool):
            raise ContractError("fallback_used 必须是 boolean")
        for s in self.steps:
            if not isinstance(s, StepResult):
                raise ContractError("steps 必须包含 StepResult 实例")

    @property
    def ok(self) -> bool:
        return self.status == "ok"


# ===== 聚合规则 =====

def aggregate_workflow_result(steps: list[StepResult], on_error: str = "stop") -> BrowserResult:
    """聚合多个 step 为 workflow-level result"""
    all_ok = all(s.status == "ok" for s in steps)
    all_providers = {s.provider_used for s in steps if s.provider_used and s.provider_used != "none"}
    any_fallback = any(s.fallback_used for s in steps)

    if all_ok:
        wf_status = "ok"
        wf_ec = "ok"
    elif on_error == "stop":
        wf_status = "error"
        first_bad = next((s.error_code for s in steps if s.status != "ok"), "unknown")
        wf_ec = first_bad
    else:  # continue
        wf_status = "uncertain"
        first_bad = next((s.error_code for s in steps if s.status != "ok"), "unknown")
        wf_ec = first_bad

    provider_used = "mixed" if len(all_providers) > 1 else (next(iter(all_providers)) if all_providers else "none")
    fallback_used = any_fallback

    return BrowserResult(
        status=wf_status,
        error_code=wf_ec,
        provider_used=provider_used,
        fallback_used=fallback_used,
        steps=steps,
    )


# ===== WorkflowResult 兼容 =====

def from_legacy_wr(wr) -> BrowserResult:
    """从旧 WorkflowResult / dict 转换。映射 blocked→error"""
    if isinstance(wr, dict):
        raw_status = wr.get("status", "error")
        if raw_status == "blocked":
            raw_status = "error"
        return BrowserResult(
            status=raw_status,
            error_code=wr.get("error_code", "unknown"),
            provider_used=wr.get("provider_used", "none"),
            fallback_used=bool(wr.get("fallback_used", False)),
            trace_id=wr.get("trace_id"),
            message=wr.get("message"),
            data=wr.get("data", {}),
        )
    if hasattr(wr, "status"):
        raw_status = wr.status
        if raw_status == "blocked":
            raw_status = "error"
        return BrowserResult(
            status=raw_status,
            error_code=wr.error_code,
            provider_used=getattr(wr, "provider_used", "none"),
            fallback_used=bool(getattr(wr, "fallback_used", False)),
            trace_id=getattr(wr, "trace_id", None),
            message=getattr(wr, "message", None),
            data=getattr(wr, "data", {}),
        )
    return BrowserResult(status="error", error_code="unknown", message="invalid result")
