#!/usr/bin/env python3
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from browser_server import _ms
from tools.commands import _timeout_arg, run_wait_selector
from unittest.mock import patch

def test_ms_string():
    assert _ms({"timeout": "8000"}) == 8000
    assert _ms({"timeout": 8000}) == 8000
    assert _ms({"timeout": "nope"}, default=10000) == 10000

def test_timeout_arg():
    assert _timeout_arg("5000") == 5000
    assert _timeout_arg(None) == 10000

def test_run_wait_selector_sends_int():
    with patch("tools.commands._send_cmd") as m:
        m.return_value = {"ok": True, "observation": "ok"}
        run_wait_selector("body", "visible", "8000")
        assert m.call_args[0][1]["timeout"] == 8000
        assert isinstance(m.call_args[0][1]["timeout"], int)
