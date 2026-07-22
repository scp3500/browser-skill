"""test_timeouts.py — TIMEOUTS 和环境变量测试"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from browser_daemon import get_timeout, TIMEOUTS


def test_default_timeout():
    assert get_timeout("default") == 30


def test_dokobot_timeout():
    assert get_timeout("dokobot") == 90


def test_openvl_timeout():
    assert get_timeout("openvl") == 120


def test_images_timeout():
    assert get_timeout("images") == 180


def test_unknown_name_falls_back_to_default():
    assert get_timeout("nonexistent") == 30


def test_environment_variable_overrides(monkeypatch):
    monkeypatch.setenv("BROWSER_TIMEOUT_OPENVL", "5")
    assert get_timeout("openvl") == 5


def test_environment_variable_default(monkeypatch):
    monkeypatch.setenv("BROWSER_TIMEOUT_DEFAULT", "60")
    assert get_timeout("default") == 60
