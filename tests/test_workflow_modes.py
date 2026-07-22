"""test_workflow_modes.py — workflow 层 mode 透传测试"""
import sys, os, json
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_screenshot_ask_passes_mode_to_openvl():
    """wf_screenshot_ask 必须把 mode 透传给 _run_openvl"""
    with patch("browser_workflows._run_openvl") as mock_openvl:
        mock_openvl.return_value = {"ok": True, "result": {"text": "ocr result"}}
        with patch("browser_workflows.step") as mock_step:
            mock_step.return_value = {"ok": True, "result": {"path": "/tmp/test.png"}}

            import browser_workflows as wf
            wf.run("screenshot_ask", {"question": "extract text", "mode": "ocr"})

            call_args = mock_openvl.call_args
            assert call_args is not None, "_run_openvl was not called"
            args, kwargs = call_args
            assert args[0] == "describe"
            actual = args[1].get("mode")
            assert actual == "ocr", f"expected mode=ocr, got {actual}"


def test_screenshot_ask_default_mode_is_diagnose():
    with patch("browser_workflows._run_openvl") as mock_openvl:
        mock_openvl.return_value = {"ok": True, "result": {"text": "diag"}}
        with patch("browser_workflows.step") as mock_step:
            mock_step.return_value = {"ok": True, "result": {"path": "/tmp/test.png"}}

            import browser_workflows as wf
            wf.run("screenshot_ask", {"question": "test"})

            call_args = mock_openvl.call_args
            assert call_args is not None
            args, kwargs = call_args
            actual = args[1].get("mode")
            assert actual == "diagnose", f"expected default diagnose, got {actual}"


def test_screenshot_ask_passes_search_mode():
    with patch("browser_workflows._run_openvl") as mock_openvl:
        mock_openvl.return_value = {"ok": True, "result": {"text": "search"}}
        with patch("browser_workflows.step") as mock_step:
            mock_step.return_value = {"ok": True, "result": {"path": "/tmp/test.png"}}

            import browser_workflows as wf
            wf.run("screenshot_ask", {"question": "test", "mode": "search"})

            args, kwargs = mock_openvl.call_args
            assert args[1].get("mode") == "search"
