#!/usr/bin/env python3
"""test_chars_flag.py — --chars / invalid chars values must not crash int()."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from browser_workflows import parse_chars
import browser_daemon as daemon


def test_parse_chars_normal():
    assert parse_chars({"chars": "1500"}, 3000) == 1500
    assert parse_chars({"max_chars": 2000}, 3000) == 2000
    assert parse_chars({}, 1234) == 1234


def test_parse_chars_flag_like_value():
    assert parse_chars({"chars": "--chars"}, 3000) == 3000
    assert parse_chars({"chars": "--result"}, 1000) == 1000
    assert parse_chars({"chars": ""}, 3000) == 3000
    assert parse_chars({"chars": "nope"}, 3000) == 3000


def test_positional_or_default_skips_flags():
    assert daemon._positional_or_default(["https://x.com", "--chars", "1000"], 1, "3000") == "3000"
    assert daemon._positional_or_default(["https://x.com", "2500"], 1, "3000") == "2500"
    assert daemon._positional_or_default(["--chars", "1000"], 0, "3000") == "3000"
    assert daemon._positional_or_default([], 0, "3000") == "3000"


def test_article_cli_accepts_chars_flag(monkeypatch):
    captured = {}

    def fake_send(name, args):
        captured["name"] = name
        captured["args"] = args
        return {"ok": True, "observation": "ok"}

    monkeypatch.setattr(daemon, "_send_workflow", fake_send)
    monkeypatch.setattr(daemon, "print_result", lambda r: None)
    monkeypatch.setattr(sys, "argv", ["browser", "article", "https://example.com", "--chars", "1200"])
    daemon.main()
    assert captured["name"] == "article"
    assert captured["args"]["url"] == "https://example.com"
    assert captured["args"]["chars"] == "1200"


def test_article_cli_positional_chars(monkeypatch):
    captured = {}

    def fake_send(name, args):
        captured["name"] = name
        captured["args"] = args
        return {"ok": True, "observation": "ok"}

    monkeypatch.setattr(daemon, "_send_workflow", fake_send)
    monkeypatch.setattr(daemon, "print_result", lambda r: None)
    monkeypatch.setattr(sys, "argv", ["browser", "article", "https://example.com", "800"])
    daemon.main()
    assert captured["args"]["chars"] == "800"


def test_doko_read_cli_flag(monkeypatch):
    captured = {}

    def fake_send(name, args):
        captured["name"] = name
        captured["args"] = args
        return {"ok": True, "observation": "ok"}

    monkeypatch.setattr(daemon, "_send_workflow", fake_send)
    monkeypatch.setattr(daemon, "print_result", lambda r: None)
    monkeypatch.setattr(sys, "argv", ["browser", "doko_read", "https://example.com", "--chars", "500"])
    daemon.main()
    assert captured["name"] == "doko_read"
    assert captured["args"]["chars"] == "500"
