#!/usr/bin/env python3
"""v2.7 server helpers — profile_dir / frames without real Playwright."""
import os
import sys
from unittest.mock import MagicMock, patch
from io import StringIO
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import browser_server as bs


class FakeFrame:
    def __init__(self, name="inner"):
        self.name = name

    def query_selector(self, sel):
        return None


class FakeHandle:
    def __init__(self, frame=None):
        self._frame = frame

    def content_frame(self):
        return self._frame


class FakePage:
    def __init__(self):
        self.url = "about:blank"
        self._frames = {}

    def title(self):
        return ""

    def query_selector(self, sel):
        if sel in self._frames:
            return FakeHandle(self._frames[sel])
        return None

    def set_input_files(self, sel, files):
        self.last_upload = (sel, files)

    def set_extra_http_headers(self, h):
        pass

    def add_init_script(self, s):
        pass


def _reset():
    bs.P = None
    bs.BROWSER = None
    bs.CONTEXT = None
    bs.PAGE = None
    bs.TABS = {}
    bs.ACTIVE_ID = "0"
    bs._TAB_SEQ = 0
    bs.PERSISTENT = False
    bs.FRAMES = {}
    bs.DOWNLOAD_DIR = None


def test_profile_dir_from_env(monkeypatch):
    monkeypatch.setenv("BROWSER_PROFILE_DIR", "C:/tmp/browser-profile-test")
    assert bs._profile_dir().replace("\\", "/").endswith("browser-profile-test")
    monkeypatch.delenv("BROWSER_PROFILE_DIR", raising=False)
    monkeypatch.delenv("BROWSER_USER_DATA_DIR", raising=False)
    assert bs._profile_dir() is None


def test_frame_enter_exit_chain():
    _reset()
    page = FakePage()
    inner = FakeFrame()
    page._frames["iframe#a"] = inner
    bs.TABS = {"0": page}
    bs.ACTIVE_ID = "0"
    bs.PAGE = page
    bs.FRAMES = {"0": []}
    bs.BROWSER = MagicMock()
    bs.P = MagicMock()

    with patch("sys.stdout", new_callable=StringIO) as out:
        bs.handle({"id": "1", "cmd": "frame_enter", "args": {"selector": "iframe#a"}})
        resp = json.loads(out.getvalue().strip().splitlines()[-1])
        assert resp["ok"] is True
        assert resp["result"]["depth"] == 1
        assert bs.FRAMES["0"] == ["iframe#a"]

    with patch("sys.stdout", new_callable=StringIO) as out:
        bs.handle({"id": "2", "cmd": "frame_exit", "args": {}})
        resp = json.loads(out.getvalue().strip().splitlines()[-1])
        assert resp["ok"] is True
        assert resp["result"]["depth"] == 0


def test_frame_enter_not_found():
    _reset()
    page = FakePage()
    bs.TABS = {"0": page}
    bs.ACTIVE_ID = "0"
    bs.PAGE = page
    bs.FRAMES = {"0": []}
    bs.BROWSER = MagicMock()
    bs.P = MagicMock()
    with patch("sys.stdout", new_callable=StringIO) as out:
        bs.handle({"id": "1", "cmd": "frame_enter", "args": {"selector": "iframe#missing"}})
        resp = json.loads(out.getvalue().strip().splitlines()[-1])
        assert resp["ok"] is False


def test_upload_missing_file():
    _reset()
    page = FakePage()
    bs.TABS = {"0": page}
    bs.ACTIVE_ID = "0"
    bs.PAGE = page
    bs.FRAMES = {"0": []}
    bs.BROWSER = MagicMock()
    bs.P = MagicMock()
    with patch("sys.stdout", new_callable=StringIO) as out:
        bs.handle({"id": "1", "cmd": "upload", "args": {
            "selector": "input[type=file]", "files": "Z:/no/such/file.txt",
        }})
        resp = json.loads(out.getvalue().strip().splitlines()[-1])
        assert resp["ok"] is False
        assert "not found" in resp["error"]["message"].lower()
