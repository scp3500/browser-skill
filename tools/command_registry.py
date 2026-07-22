#!/usr/bin/env python3
"""command_registry.py — v2.4.1 命令注册表（用于 contract 测试）"""
from dataclasses import dataclass, field


@dataclass
class CommandSpec:
    """命令元信息"""
    name: str
    needs_daemon: bool = False
    needs_provider: bool = True
    trace_required: bool = True
    smoke_args: list[str] = field(default_factory=list)
    expect_status: str = "ok"
    config_command: bool = False  # config 类命令固定 Provider used: none, Fallback used: no


# 所有 CLI 命令
COMMANDS: dict[str, CommandSpec] = {
    # 管理命令
    "status": CommandSpec(name="status", needs_daemon=True, trace_required=False),
    "kill": CommandSpec(name="kill", needs_daemon=True, trace_required=False),
    "logs": CommandSpec(name="logs", needs_daemon=True, trace_required=False),

    # config 命令
    "config_path": CommandSpec(name="config_path", needs_provider=False, config_command=True),
    "config_show": CommandSpec(name="config_show", needs_provider=False, config_command=True),
    "config_validate": CommandSpec(name="config_validate", needs_provider=False, config_command=True),
    "config_set": CommandSpec(name="config_set", needs_provider=False, config_command=True),

    # preset 命令
    "preset_list": CommandSpec(name="preset_list", needs_provider=False, config_command=True),
    "preset_show": CommandSpec(name="preset_show", needs_provider=False, config_command=True, smoke_args=["browser-only"]),
    "preset_use": CommandSpec(name="preset_use", needs_provider=False, config_command=True),

    # workflow 命令
    "workflow_list": CommandSpec(name="workflow_list", needs_provider=False, config_command=True),
    "workflow_show": CommandSpec(name="workflow_show", needs_provider=False, config_command=True),
    "workflow_run": CommandSpec(name="workflow_run", needs_provider=True),
    "workflow_validate": CommandSpec(name="workflow_validate", needs_provider=False, config_command=True, smoke_args=["web_qa"]),

    # 原子命令（需要 daemon）
    "goto": CommandSpec(name="goto", needs_daemon=True, smoke_args=["https://example.com"]),
    "reset": CommandSpec(name="reset", needs_daemon=True),
    "observe": CommandSpec(name="observe", needs_daemon=True),

    # workflow 动作（需要 daemon）
    "read_url": CommandSpec(name="read_url", needs_daemon=True, smoke_args=["https://example.com"]),
    "search_read": CommandSpec(name="search_read", needs_daemon=True),
    "diagnose": CommandSpec(name="diagnose", needs_daemon=True),
    "diagnose_and_recover": CommandSpec(name="diagnose_and_recover", needs_daemon=True),
    "screenshot_ask": CommandSpec(name="screenshot_ask", needs_daemon=True),
    "wait_text": CommandSpec(name="wait_text", needs_daemon=True),
    "assert_text": CommandSpec(name="assert_text", needs_daemon=True),
    "click_expect": CommandSpec(name="click_expect", needs_daemon=True),

    # trace 命令
    "trace_list": CommandSpec(name="trace_list", needs_provider=False, config_command=True),
    "trace_show": CommandSpec(name="trace_show", needs_provider=False, config_command=True),

    # parallel 命令
    "read_urls_parallel": CommandSpec(name="read_urls_parallel", needs_daemon=True, smoke_args=["--input", "nonexistent.json"]),

    # search 命令
    "search_candidates": CommandSpec(name="search_candidates", needs_provider=False, config_command=True, smoke_args=["--query", "test", "--allowed-domain", "example.com"]),
    "search_official": CommandSpec(name="search_official", needs_provider=False, config_command=True, smoke_args=["--query", "test", "--allowed-domain", "example.com"]),
    # web UI 命令
    "config_web": CommandSpec(name="config_web", needs_provider=False, config_command=True, smoke_args=["--port", "8766"]),
    "config_web_status": CommandSpec(name="config_web_status", needs_provider=False, config_command=True),
    "config_web_stop": CommandSpec(name="config_web_stop", needs_provider=False, config_command=True),
}
