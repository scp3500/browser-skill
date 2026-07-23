#!/usr/bin/env python3
"""v2.7 upload/download/frame/profile — mock _send_cmd."""
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.commands import (
    run_upload, run_download, run_frame_enter, run_frame_exit,
    run_frame_main, run_frame_status, run_profile_status,
)
from tools.command_registry import COMMANDS
from browser_agent import AUTO_OBSERVE_CMDS


def test_upload_args():
    with patch("tools.commands._send_cmd") as m:
        m.return_value = {"ok": True, "observation": "ok"}
        run_upload("input[type=file]", "C:/tmp/a.txt")
        m.assert_called_once_with("upload", {
            "selector": "input[type=file]", "files": "C:/tmp/a.txt",
        })


def test_upload_requires_args():
    r = run_upload("", "")
    assert r.status == "error"
    assert r.error_code == "invalid_input"


def test_download_optional_selector():
    with patch("tools.commands._send_cmd") as m:
        m.return_value = {"ok": True, "observation": "ok"}
        run_download(selector="#dl", path="out.bin", timeout="15000")
        m.assert_called_once_with("download", {
            "timeout": 15000, "selector": "#dl", "path": "out.bin",
        })


def test_frame_enter_exit_main():
    with patch("tools.commands._send_cmd") as m:
        m.return_value = {"ok": True, "observation": "ok"}
        run_frame_enter("iframe#app")
        m.assert_called_with("frame_enter", {"selector": "iframe#app"})
        run_frame_exit()
        m.assert_called_with("frame_exit")
        run_frame_main()
        m.assert_called_with("frame_main")
        run_frame_status()
        m.assert_called_with("frame_status")


def test_frame_enter_empty_invalid():
    r = run_frame_enter("")
    assert r.status == "error"


def test_profile_status_cmd():
    with patch("tools.commands._send_cmd") as m:
        m.return_value = {"ok": True, "observation": "ok"}
        run_profile_status()
        m.assert_called_once_with("profile_status")


def test_registry_has_v27_commands():
    for name in ("upload", "download", "frame_enter", "frame_exit",
                 "frame_main", "frame_status", "profile_status"):
        assert name in COMMANDS
        assert COMMANDS[name].needs_daemon is True


def test_auto_observe_includes_upload_frame_enter():
    assert "upload" in AUTO_OBSERVE_CMDS
    assert "frame_enter" in AUTO_OBSERVE_CMDS
