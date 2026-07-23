#!/usr/bin/env python3
"""v2.6 tab commands — mock _send_cmd, offline."""
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.commands import run_tabs, run_new_tab, run_switch_tab, run_close_tab
from tools.contract import BrowserResult
from tools.render import render_text
from tools.command_registry import COMMANDS


def test_tabs_returns_browserresult():
    with patch("tools.commands._send_cmd") as m:
        m.return_value = {"ok": True, "observation": "2 tabs"}
        r = run_tabs()
        assert isinstance(r, BrowserResult)
        assert r.status == "ok"
        assert r.provider_used == "browser"
        m.assert_called_once_with("tabs")
        r.trace_id = "test_tabs_1"
        header = render_text(r).splitlines()[:5]
        assert header[0].startswith("Status:")
        assert header[1].startswith("Error code:")


def test_new_tab_url_and_id_passed_through():
    with patch("tools.commands._send_cmd") as m:
        m.return_value = {"ok": True, "observation": "ok"}
        run_new_tab("https://example.com", "t9")
        m.assert_called_once_with("new_tab", {"url": "https://example.com", "id": "t9"})


def test_switch_tab_missing_id_errors():
    r = run_switch_tab("")
    assert r.status == "error"
    assert r.error_code == "invalid_input"


def test_close_tab_falls_back_to_active():
    with patch("tools.commands._send_cmd") as m:
        m.return_value = {"ok": True, "observation": "ok"}
        run_close_tab()
        m.assert_called_once_with("close_tab", {})


def test_tabs_daemon_error_propagates():
    with patch("tools.commands._send_cmd") as m:
        m.return_value = {"ok": False, "observation": "daemon error: down"}
        r = run_tabs()
        assert r.status == "error"
        assert "daemon" in (r.message or "").lower()


def test_tab_commands_in_registry():
    for name in ("tabs", "new_tab", "switch_tab", "close_tab"):
        assert name in COMMANDS
        assert COMMANDS[name].needs_daemon is True
