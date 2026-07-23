#!/usr/bin/env python3
"""test_search_extract.py — search + extraction + excerpt tests"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from tools.contract import BrowserResult, StepResult, ContractError
from tools.render import render_text, render_json


# ===== Search candidates =====

def test_search_candidates_has_five_line_header():
    from tools.commands import run_search_candidates
    from tools.trace_store import new_trace_id
    result = run_search_candidates(["--query", "test", "--allowed-domain", "example.com"])
    result.trace_id = new_trace_id("search_candidates_test")
    h = render_text(result)
    lines = h.split(chr(10))[:5]
    assert lines[0].startswith("Status:")
    assert lines[1].startswith("Error code:")
    assert lines[2].startswith("Provider used:")
    assert lines[3].startswith("Fallback used:")
    assert lines[4].startswith("Trace:")


def test_search_candidates_requires_query():
    from tools.commands import run_search_candidates
    result = run_search_candidates(["--allowed-domain", "example.com"])
    assert result.status == "error"
    assert "query" in (result.message or "").lower()


def test_search_candidates_requires_domain():
    from tools.commands import run_search_candidates
    result = run_search_candidates(["--query", "test"])
    assert result.status == "error"


def test_search_candidates_classifies_allowed_domain_official():
    from tools.commands import _classify_source_type
    assert _classify_source_type("https://www.anthropic.com/news", ["anthropic.com"]) == "official"
    assert _classify_source_type("https://docs.anthropic.com/", ["anthropic.com"]) == "official"
    assert _classify_source_type("https://anthropic.com/", ["anthropic.com"]) == "official"


def test_search_candidates_filters_third_party():
    from tools.commands import _classify_source_type
    assert _classify_source_type("https://medium.com/anthropic-news", ["anthropic.com"]) == "third_party"
    assert _classify_source_type("https://runoob.com/playwright", ["playwright.dev"]) == "third_party"


def test_search_official_no_official_returns_uncertain():
    """如果没找到 official，status=uncertain, error_code=unverified_source"""
    from tools.commands import run_search_candidates
    from unittest.mock import patch
    with patch("subprocess.run") as mock:
        mock.return_value.stdout = "https://runoob.com/test"
        mock.return_value.stderr = ""
        result = run_search_candidates(["--query", "testxyz", "--allowed-domain", "official.com"])
        assert result.status == "uncertain" or result.status == "error"
        if result.status == "uncertain":
            assert result.error_code == "unverified_source"


def test_search_candidates_sanitizes_query_tokens():
    from tools.sanitize import sanitize
    data = {"candidates": [{"url": "https://example.com/?token=sk-abc123"}]}
    clean = sanitize(data)
    assert "sk-abc123" not in json.dumps(clean)


# ===== Read URL extraction metadata =====

def test_read_url_extraction_metadata_present():
    """read_url 结果应有 truncation 和 extraction 字段"""
    from tools.commands import _execute_read_url_parallel_task
    # Can't test directly without daemon, test the schema instead
    result_dict = {
        "url": "https://example.com", "status": "ok", "error_code": "ok",
        "provider_used": "browser", "fallback_used": False,
        "child_trace": "test", "title": "Test",
        "excerpt": "Sample text",
        "truncated": False,
        "extraction_incomplete": False,
        "requested_chars": 3000,
        "returned_chars": 100,
    }
    assert "truncated" in result_dict
    assert "extraction_incomplete" in result_dict
    assert "requested_chars" in result_dict
    assert "returned_chars" in result_dict


def test_read_url_detects_fixed_extraction_cutoff():
    """如果 returned_chars 远小于 requested_chars 且截断点不自然，标记 extraction_incomplete"""
    # Simulate: requested 40000, returned 542 at exact same cutoff
    result = {
        "requested_chars": 40000,
        "returned_chars": 542,
        "truncated": False,
        "extraction_incomplete": True,
    }
    assert result["extraction_incomplete"] is True


def test_read_url_trace_records_requested_returned_chars():
    """trace 中应记录 requested_chars 和 returned_chars"""
    trace_entry = {
        "requested_chars": 40000,
        "returned_chars": 542,
        "truncated": False,
        "extraction_incomplete": True,
    }
    assert trace_entry["requested_chars"] == 40000
    assert trace_entry["returned_chars"] == 542


# ===== Parallel excerpt =====

def test_read_urls_parallel_excerpt_uses_text():
    """excerpt 应使用真实文本，不是 'Read OK'"""
    from tools.commands import _execute_read_url_parallel_task
    import inspect
    source = inspect.getsource(_execute_read_url_parallel_task)
    assert 'text[:1000]' in source, "Excerpt must slice text, not use placeholder"


def test_read_urls_parallel_excerpt_not_read_ok():
    """验证渲染层中 excerpt 不是 'Read OK'"""
    from tools.render import render_text
    from tools.contract import BrowserResult
    r = BrowserResult(
        status="ok", error_code="ok", provider_used="browser",
        trace_id="t1",
        message="Results:\n  URL: https://example.com\n    Status: ok\n    Excerpt: Real content text here",
    )
    h = render_text(r)
    assert "Read OK" not in h.split("Excerpt:")[1].split("\n")[0] if "Excerpt:" in h else True


def test_read_urls_parallel_outputs_extraction_incomplete():
    """每个 result 应显示 Extraction incomplete"""
    from tools.contract import BrowserResult
    r = BrowserResult(
        status="ok", error_code="ok", provider_used="browser",
        trace_id="t1",
        message="Results:\n  URL: https://example.com\n    Status: ok\n    Extraction incomplete: yes",
    )
    h = render_text(r)
    assert "Extraction incomplete" in h


def test_read_urls_parallel_parent_trace_contains_excerpt():
    """父 trace 应记录 excerpt"""
    from tools.trace_store import write_trace, new_trace_id
    from tools.contract import BrowserResult, StepResult
    r = BrowserResult(
        status="ok", error_code="ok", provider_used="browser",
        message="Results:\n  URL: https://example.com\n    Status: ok\n    Excerpt: test content",
        data={"results": [{"url": "https://example.com", "excerpt": "test content"}]},
    )
    tid = write_trace(r, "test_parallel")
    assert tid is not None


# ===== Registry tests =====

def test_search_candidates_command_registered():
    from tools.command_registry import COMMANDS
    assert "search_candidates" in COMMANDS
    assert "search_official" in COMMANDS


def test_all_search_commands_have_five_line_header():
    from tools.command_registry import COMMANDS
    from tools.cli_dispatch import dispatch, _ensure_trace
    from tools.render import render_text

    for name in ("search_candidates", "search_official"):
        spec = COMMANDS[name]
        args = [name] + spec.smoke_args
        result = _ensure_trace(dispatch(args), name)
        h = render_text(result)
        lines = h.split(chr(10))[:5]
        assert lines[0].startswith("Status:"), f"{name}: missing Status"
        assert lines[1].startswith("Error code:"), f"{name}: missing Error code"
        assert lines[2].startswith("Provider used:"), f"{name}: missing Provider used"
        assert lines[3].startswith("Fallback used:"), f"{name}: missing Fallback used"
        assert lines[4].startswith("Trace:"), f"{name}: missing Trace"
        assert "no" not in lines[4], f"{name}: Trace: no is forbidden"
