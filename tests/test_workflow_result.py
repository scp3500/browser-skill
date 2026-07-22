"""test_workflow_result.py — WorkflowResult contract 测试"""
import sys, os, pytest, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
from workflow_result import (
    WorkflowResult, validate_status, validate_error_code, validate_provider,
    error_code_from_diagnose,
)


def test_valid_status():
    for s in ["ok", "error", "blocked", "uncertain"]:
        validate_status(s)


def test_invalid_status():
    with pytest.raises(ValueError, match="invalid status"):
        validate_status("maybe")


def test_valid_error_code():
    for e in ["ok", "blocked_captcha", "blank_page", "timeout", "read_failed", "unknown"]:
        validate_error_code(e)


def test_invalid_error_code():
    with pytest.raises(ValueError, match="invalid error_code"):
        validate_error_code("not_a_real_error")


def test_valid_provider():
    for p in ["browser", "dokobot", "openvl", "mixed", "none"]:
        validate_provider(p)


def test_invalid_provider():
    with pytest.raises(ValueError, match="invalid provider"):
        validate_provider("chatgpt")


def test_workflow_result_defaults():
    r = WorkflowResult()
    assert r.status == "ok"
    assert r.error_code == "ok"
    assert r.provider_used == "none"
    assert r.fallback_used is False


def test_workflow_result_custom():
    r = WorkflowResult(status="error", error_code="blank_page", provider_used="openvl",
                       fallback_used=True, message="page is blank")
    assert r.status == "error"
    assert r.error_code == "blank_page"
    assert r.fallback_used is True


def test_to_dict():
    r = WorkflowResult(status="ok", provider_used="browser", url="https://example.com")
    d = r.to_dict()
    assert d["status"] == "ok"
    assert d["url"] == "https://example.com"
    assert "text" in d


def test_cli_header():
    r = WorkflowResult(status="blocked", error_code="blocked_captcha", provider_used="mixed", fallback_used=True)
    h = r.cli_header()
    assert "Status: blocked" in h
    assert "Error code: blocked_captcha" in h
    assert "Provider used: mixed" in h
    assert "Fallback used: yes" in h


def test_cli_header_ok():
    r = WorkflowResult(status="ok")
    h = r.cli_header()
    assert "Status: ok" in h
    assert "Error code: ok" in h
    assert "Fallback used: no" in h


def test_invalid_status_at_construction():
    with pytest.raises(ValueError):
        WorkflowResult(status="invalid")


def test_invalid_error_code_at_construction():
    with pytest.raises(ValueError):
        WorkflowResult(error_code="foobar")


def test_invalid_provider_at_construction():
    with pytest.raises(ValueError):
        WorkflowResult(provider_used="foo")


def test_workflow_result_accepts_data():
    r = WorkflowResult(status="ok", error_code="ok", provider_used="openvl",
                       data={"blocking_issue": "none", "reason": "all good"})
    assert r.data["blocking_issue"] == "none"
    assert r.data["reason"] == "all good"


def test_to_dict_contains_data():
    r = WorkflowResult(data={"blocking_issue": "none"})
    d = r.to_dict()
    assert "data" in d
    assert d["data"]["blocking_issue"] == "none"


# ===== error_code_from_diagnose =====

def test_diagnose_ok_maps_to_ok():
    text = "Status: ok\nBlocking issue: none\nReason: all good\nSuggested action: none"
    assert error_code_from_diagnose(text) == "ok"


def test_diagnose_captcha_maps_to_blocked_captcha():
    text = "Blocking issue: captcha\nStatus: blocked\nReason: captcha detected"
    assert error_code_from_diagnose(text) == "blocked_captcha"


def test_diagnose_login_maps_to_blocked_login():
    text = "Status: blocked\nBlocking issue: login"
    assert error_code_from_diagnose(text) == "blocked_login"


def test_diagnose_blank_page_maps_to_blank_page():
    text = "Status: blocked\nBlocking issue: blank_page"
    assert error_code_from_diagnose(text) == "blank_page"


def test_diagnose_uncertain_maps_to_unknown():
    text = "Status: uncertain"
    assert error_code_from_diagnose(text) == "unknown"


def test_diagnose_unknown_issue_maps_to_unknown():
    text = "Status: blocked\nBlocking issue: something_strange"
    assert error_code_from_diagnose(text) == "unknown"


def test_diagnose_empty_text_maps_to_unknown():
    assert error_code_from_diagnose("") == "unknown"
