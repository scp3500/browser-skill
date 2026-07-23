#!/usr/bin/env python3
"""v2.6 browser_server tab model — mock Playwright, no real browser."""
import os
import sys
import json
from unittest.mock import MagicMock, patch
from io import StringIO

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import browser_server as bs


class FakePage:
    def __init__(self, url="about:blank", title=""):
        self.url = url
        self._title = title
        self.closed = False
        self.gotos = []

    def title(self):
        return self._title

    def goto(self, url, timeout=30000):
        self.gotos.append(url)
        self.url = url
        self._title = "Example"

    def close(self):
        self.closed = True

    def set_extra_http_headers(self, h):
        pass

    def add_init_script(self, s):
        pass

    def wait_for_load_state(self, *a, **k):
        pass

    def wait_for_timeout(self, ms):
        pass


def _reset_state():
    bs.P = None
    bs.BROWSER = None
    bs.PAGE = None
    bs.TABS = {}
    bs.ACTIVE_ID = "0"
    bs._TAB_SEQ = 0


def _fake_browser():
    browser = MagicMock()
    pages = []

    def new_page():
        p = FakePage()
        pages.append(p)
        return p

    browser.new_page.side_effect = new_page
    browser._pages = pages
    return browser


def test_new_tab_creates_entry_and_switches():
    _reset_state()
    browser = _fake_browser()
    with patch.object(bs, "sync_playwright") as sp, patch("sys.stdout", new_callable=StringIO) as out:
        pw = MagicMock()
        sp.return_value = pw
        pw.start.return_value = pw  # sync_playwright().start()
        pw.chromium.launch.return_value = browser
        bs.ensure_page()
        assert "0" in bs.TABS
        bs.handle({"id": "1", "cmd": "new_tab", "args": {"url": "https://x"}})
        raw = out.getvalue().strip().splitlines()[-1]
        resp = json.loads(raw)
        assert resp["ok"] is True, resp
        assert resp["result"]["tab_id"] in bs.TABS
        assert bs.ACTIVE_ID == resp["result"]["tab_id"]
        # last created page received goto
        assert browser._pages[-1].gotos == ["https://x"]


def test_close_tab_recreates_zero_when_last():
    _reset_state()
    browser = _fake_browser()
    with patch.object(bs, "sync_playwright") as sp, patch("sys.stdout", new_callable=StringIO) as out:
        pw = MagicMock()
        sp.return_value = pw
        pw.start.return_value = pw
        pw.chromium.launch.return_value = browser
        bs.ensure_page()
        bs.handle({"id": "1", "cmd": "close_tab", "args": {"id": "0"}})
        raw = out.getvalue().strip().splitlines()[-1]
        resp = json.loads(raw)
        assert resp["ok"] is True, resp
        assert resp["result"]["closed"] == "0"
        assert "0" in bs.TABS
        assert bs.ACTIVE_ID == "0"


def test_switch_tab_not_found():
    _reset_state()
    browser = _fake_browser()
    with patch.object(bs, "sync_playwright") as sp, patch("sys.stdout", new_callable=StringIO) as out:
        pw = MagicMock()
        sp.return_value = pw
        pw.start.return_value = pw
        pw.chromium.launch.return_value = browser
        bs.ensure_page()
        bs.handle({"id": "1", "cmd": "switch_tab", "args": {"id": "nope"}})
        raw = out.getvalue().strip().splitlines()[-1]
        resp = json.loads(raw)
        assert resp["ok"] is False
