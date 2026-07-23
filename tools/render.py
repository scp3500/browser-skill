#!/usr/bin/env python3
"""render.py — v2.6.0 统一输出渲染。唯一的 5 行 header 实现。"""
from tools.contract import BrowserResult, StepResult, NL


def render_header(result: BrowserResult) -> str:
    """生成五行 header。trace_id 为必填"""
    if not result.trace_id:
        from tools.contract import ContractError
        raise ContractError("trace_id is required before rendering")
    return NL.join([
        f"Status: {result.status}",
        f"Error code: {result.error_code}",
        f"Provider used: {result.provider_used}",
        f"Fallback used: {'yes' if result.fallback_used else 'no'}",
        f"Trace: {result.trace_id}",
    ])


def render_body(result: BrowserResult) -> str:
    """生成 body（message + workflow steps）"""
    parts = []
    if result.message:
        parts.append(result.message)
    if result.steps:
        parts.append(render_workflow_steps(result.steps))
    return NL.join(parts)


def render_text(result: BrowserResult) -> str:
    """完整文本输出"""
    header = render_header(result)
    body = render_body(result)
    if body:
        return header + NL + NL + body
    return header


def render_json(result: BrowserResult) -> dict:
    """JSON 输出"""
    return {
        "status": result.status,
        "error_code": result.error_code,
        "provider_used": result.provider_used,
        "fallback_used": result.fallback_used,
        "trace_id": result.trace_id,
        "message": result.message,
        "data": result.data,
        "steps": [{
            "name": s.name,
            "action": s.action,
            "status": s.status,
            "error_code": s.error_code,
            "provider_used": s.provider_used,
            "fallback_used": s.fallback_used,
            "child_trace": s.child_trace,
        } for s in result.steps],
    }


def render_workflow_steps(steps: list[StepResult]) -> str:
    """渲染 workflow step"""
    lines = []
    for idx, s in enumerate(steps, 1):
        lines.append(f"  {idx}. {s.name or s.action}")
        lines.append(f"     Action: {s.action}")
        lines.append(f"     Status: {s.status}")
        lines.append(f"     Error code: {s.error_code}")
        lines.append(f"     Provider used: {s.provider_used or 'none'}")
        lines.append(f"     Fallback used: {'yes' if s.fallback_used else 'no'}")
        lines.append(f"     Child trace: {s.child_trace or ''}")
    return NL.join(lines)
