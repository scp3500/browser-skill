"""test_sanitize.py — 脱敏测试"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from browser_daemon import sanitize


def test_redact_sk_prefix_in_string():
    out = sanitize("failed with sk-abc123")
    assert "sk-abc123" not in out
    assert "[REDACTED]" in out


def test_redact_bearer_in_string():
    out = sanitize("Authorization: Bearer xyz789")
    assert "Bearer xyz789" not in out


def test_redact_url_query_api_key():
    out = sanitize("https://x.com/?api_key=secret&q=ok")
    assert "secret" not in out
    assert "q=ok" in out


def test_redact_url_query_token():
    out = sanitize("https://x.com/?token=raw&a=1")
    assert "raw" not in out
    assert "a=1" in out


def test_redact_url_query_access_token():
    out = sanitize("https://x.com/?access_token=abc&b=2")
    assert "abc" not in out
    assert "b=2" in out


def test_redact_nested_dict():
    d = {"headers": {"authorization": "Bearer abc"}, "api_key": "sk-xyz"}
    out = str(sanitize(d))
    assert "Bearer abc" not in out
    assert "sk-xyz" not in out


def test_redact_case_insensitive_keys():
    d = {"ApiKey": "x", "AUTHORIZATION": "Bearer y", "api-key": "z"}
    out = str(sanitize(d))
    assert "x" not in out
    assert "Bearer y" not in out
    assert "z" not in out


def test_redact_camelcase_key():
    d = {"apiKey": "secret123"}
    out = str(sanitize(d))
    assert "secret123" not in out


def test_normal_text_passes_through():
    out = sanitize("hello world")
    assert out == "hello world"


def test_list_redaction():
    data = ["sk-abc", {"password": "123"}]
    out = str(sanitize(data))
    assert "sk-abc" not in out
    assert "123" not in out


def test_none_values_not_redacted():
    d = {"api_key": None}
    out = sanitize(d)
    assert out["api_key"] is None
