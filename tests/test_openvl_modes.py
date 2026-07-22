"""test_openvl_modes.py — OpenVL mode 回归测试
Mock subprocess，不真实调用 openvl。
"""
import sys, os, json, pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from tools.openvl_tool import call, _get_prompt, _clean_prompt, validate_mode, ALLOWED_MODES, PROMPTS


# ===== _clean_prompt =====

def test_clean_prompt_removes_newlines():
    out = _clean_prompt("a\nb\r\nc")
    assert "\n" not in out
    assert "\r" not in out
    assert out == "a b  c"  # \r\n becomes two spaces


# ===== Mode validation =====

def test_screenshot_ask_allowed_modes():
    for m in ["diagnose", "search", "ocr", "describe"]:
        validate_mode("screenshot_ask", m)  # should not raise

def test_screenshot_ask_rejects_image_select():
    with pytest.raises(ValueError, match="invalid mode"):
        validate_mode("screenshot_ask", "image_select")

def test_ask_image_allowed_modes():
    for m in ["describe", "ocr", "image_select"]:
        validate_mode("ask_image", m)

def test_ask_image_rejects_diagnose():
    with pytest.raises(ValueError, match="invalid mode"):
        validate_mode("ask_image", "diagnose")

def test_ask_image_rejects_search():
    with pytest.raises(ValueError, match="invalid mode"):
        validate_mode("ask_image", "search")

def test_image_page_allowed_modes():
    for m in ["image_select", "describe"]:
        validate_mode("image_page", m)

def test_image_page_rejects_diagnose():
    with pytest.raises(ValueError):
        validate_mode("image_page", "diagnose")


# ===== Prompt content =====

def test_diagnose_prompt_has_required_fields():
    p = _get_prompt("diagnose", "")
    for field in ["Status:", "Blocking issue:", "Reason:", "Suggested action:"]:
        assert field in p, f"missing {field}"

def test_search_prompt_has_required_fields():
    p = _get_prompt("search", "find docs")
    for field in ["Page type:", "Relevance:", "Best result:", "Best next action:"]:
        assert field in p, f"missing {field}"

def test_search_prompt_contains_question():
    p = _get_prompt("search", "find docs")
    assert "find docs" in p

def test_image_select_prompt_has_required_fields():
    p = _get_prompt("image_select", "find logo")
    for field in ["Selected:", "Reason:", "Candidates:"]:
        assert field in p, f"missing {field}"

def test_ocr_prompt_has_required_fields():
    p = _get_prompt("ocr", "")
    assert "Text:" in p


# ===== -P flag =====

@patch("subprocess.run")
def test_diagnose_passes_P_flag(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="ok\n")
    call("describe", {"image_path": "test.png", "mode": "diagnose"})
    args = mock_run.call_args[0][0]
    assert "-P" in args, f"diagnose should add -P, got {args}"

@patch("subprocess.run")
def test_search_passes_P_flag(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="ok\n")
    call("describe", {"image_path": "test.png", "mode": "search"})
    args = mock_run.call_args[0][0]
    assert "-P" in args

@patch("subprocess.run")
def test_ocr_passes_P_flag(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="ok\n")
    call("describe", {"image_path": "test.png", "mode": "ocr"})
    args = mock_run.call_args[0][0]
    assert "-P" in args

@patch("subprocess.run")
def test_image_select_passes_P_flag(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="ok\n")
    call("describe", {"image_path": "test.png", "mode": "image_select"})
    args = mock_run.call_args[0][0]
    assert "-P" in args

@patch("subprocess.run")
def test_describe_does_not_pass_P_flag(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="ok\n")
    call("describe", {"image_path": "test.png", "mode": "describe"})
    args = mock_run.call_args[0][0]
    assert "-P" not in args, f"describe should NOT add -P, got {args}"


# ===== Prompt argument passed to subprocess =====

@patch("subprocess.run")
def test_diagnose_prompt_in_cli_args(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="ok\n")
    call("describe", {"image_path": "test.png", "mode": "diagnose"})
    args = mock_run.call_args[0][0]
    cli_text = " ".join(args)
    assert "Status:" in cli_text
    assert "Blocking issue:" in cli_text
    assert "test.png" in cli_text


# ===== Error handling =====

@patch("subprocess.run")
def test_openvl_timeout_returns_error(mock_run):
    from subprocess import TimeoutExpired
    mock_run.side_effect = TimeoutExpired("openvl", 120)
    r = call("describe", {"image_path": "test.png"})
    assert r.get("ok") == False
    assert "TimeoutError" in str(r.get("error", {}))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
