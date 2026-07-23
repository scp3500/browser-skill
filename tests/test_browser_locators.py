#!/usr/bin/env python3
"""v2.6 locator commands — mock _send_cmd."""
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.commands import run_click_role, run_click_label, run_click_css
from browser_agent import AUTO_OBSERVE_CMDS


def test_click_role_args_shape():
    with patch("tools.commands._send_cmd") as m:
        m.return_value = {"ok": True, "observation": "ok"}
        run_click_role("button", name="登录")
        m.assert_called_once_with("click_role", {
            "role": "button", "name": "登录", "exact": False, "timeout": 10000,
        })


def test_click_label_args_shape():
    with patch("tools.commands._send_cmd") as m:
        m.return_value = {"ok": True, "observation": "ok"}
        run_click_label("密码")
        m.assert_called_once_with("click_label", {
            "label": "密码", "exact": False, "timeout": 10000,
        })


def test_click_css_no_wait_flag():
    with patch("tools.commands._send_cmd") as m:
        m.return_value = {"ok": True, "observation": "ok"}
        run_click_css("#a", wait=False)
        args = m.call_args[0][1]
        assert args["wait"] is False
        assert args["selector"] == "#a"


def test_click_css_aliases_click_cmd():
    with patch("tools.commands._send_cmd") as m:
        m.return_value = {"ok": True, "observation": "ok"}
        run_click_css("#btn")
        assert m.call_args[0][0] == "click"
        assert m.call_args[0][1].get("wait") is True


def test_locator_commands_auto_observe():
    assert "click_role" in AUTO_OBSERVE_CMDS
    assert "click_label" in AUTO_OBSERVE_CMDS
    assert "new_tab" in AUTO_OBSERVE_CMDS
    assert "wait_selector" not in AUTO_OBSERVE_CMDS
