#!/usr/bin/env python3
"""v2.6 wait / scroll commands — mock _send_cmd."""
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.commands import run_wait_selector, run_wait_url, run_scroll_into_view
from tools.render import render_text


def test_wait_selector_passes_state_default():
    with patch("tools.commands._send_cmd") as m:
        m.return_value = {"ok": True, "observation": "ok"}
        run_wait_selector("#x")
        m.assert_called_once_with("wait_selector", {
            "selector": "#x", "state": "visible", "timeout": 10000,
        })


def test_wait_url_exact_flag_propagates():
    with patch("tools.commands._send_cmd") as m:
        m.return_value = {"ok": True, "observation": "ok"}
        run_wait_url("https://a.com", exact=True)
        args = m.call_args[0][1]
        assert args["exact"] is True
        assert args["pattern"] == "https://a.com"


def test_scroll_into_view_returns_browserresult():
    with patch("tools.commands._send_cmd") as m:
        m.return_value = {"ok": True, "observation": "scrolled"}
        r = run_scroll_into_view("body")
        assert r.status == "ok"
        r.trace_id = "test_scroll_1"
        lines = render_text(r).splitlines()
        assert lines[0].startswith("Status:")


def test_wait_selector_empty_invalid():
    r = run_wait_selector("")
    assert r.status == "error"
    assert r.error_code == "invalid_input"
