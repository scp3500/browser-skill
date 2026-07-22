"""test_workflow_runner.py — workflow spec runner tests"""
import sys, os, pytest, json, tempfile
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

with patch("tools.workflow_runner.run_workflow") as mock_run:
    mock_run.return_value = {"ok": True, "_wr": MagicMock(error_code="ok", provider_used="dokobot", fallback_used=False, status="ok")}
    from tools.workflow_runner import list_workflows, show_workflow, load_spec, run, ALLOWED_ACTIONS


def test_list_workflows():
    names = list_workflows()
    # Should at least have the 4 built-in workflows
    assert len(names) >= 4
    assert "research_official" in names
    assert "troubleshoot_error" in names
    assert "pricing_compare" in names
    assert "web_qa" in names


def test_show_workflow_exists():
    content = show_workflow("research_official")
    assert content is not None
    assert "research_official" in content


def test_show_workflow_not_found():
    assert show_workflow("nonexistent") is None


def test_load_spec():
    from tools.workflow_runner import SPECS_DIR
    # Make sure SPECS_DIR is the real one
    import tools.workflow_runner as wr
    wr.SPECS_DIR = wr.BASE / "workflow_specs"
    spec = load_spec("research_official")
    assert spec is not None
    assert "steps" in spec
    assert spec["name"] == "research_official"


def test_load_spec_not_found():
    assert load_spec("nonexistent") is None


def test_unknown_action_rejected():
    """Rejects actions not in ALLOWED_ACTIONS"""
    import tempfile, yaml, os
    from pathlib import Path
    d = tempfile.mkdtemp()
    spec_path = Path(d) / "test_bad.yaml"
    spec = {
        "name": "test",
        "steps": [{"action": "shell", "args": {"cmd": "rm -rf /"}}]
    }
    with open(spec_path, "w") as f:
        yaml.dump(spec, f)
    
    # Monkeypatch SPECS_DIR
    import tools.workflow_runner as wr
    old_dir = wr.SPECS_DIR
    wr.SPECS_DIR = Path(d)
    
    result = run("test_bad", {})
    assert result.get("ok") == False
    
    wr.SPECS_DIR = old_dir


def test_substitutes_variables():
    with patch("tools.workflow_runner.run_workflow") as mock:
        mock.return_value = {"ok": True, "_wr": MagicMock(error_code="ok", provider_used="browser", fallback_used=False, status="ok")}
        
        import tempfile, yaml
        from pathlib import Path
        d = tempfile.mkdtemp()
        spec = {
            "name": "test_sub",
            "steps": [{
                "id": "search",
                "action": "search_read",
                "args": {"query": "{topic} official docs", "chars": 500},
            }]
        }
        with open(Path(d) / "test_sub.yaml", "w") as f:
            yaml.dump(spec, f)
        
        import tools.workflow_runner as wr
        old_dir = wr.SPECS_DIR
        wr.SPECS_DIR = Path(d)
        
        result = run("test_sub", {"topic": "Playwright"})
        # Verify mock was called with substituted args
        call_args = mock.call_args
        assert call_args is not None
        args = call_args[0][1]
        assert "Playwright" in args.get("query", "")
        
        wr.SPECS_DIR = old_dir


def test_on_error_stop():
    with patch("tools.workflow_runner.run_workflow") as mock:
        # First step fails
        mock.return_value = {"ok": False, "_wr": MagicMock(error_code="read_failed", provider_used="browser", fallback_used=False, status="error")}
        
        import tempfile, yaml
        from pathlib import Path
        d = tempfile.mkdtemp()
        spec = {
            "name": "test_stop",
            "steps": [
                {"id": "s1", "action": "read_url", "args": {"url": "https://x.com"}, "on_error": "stop"},
                {"id": "s2", "action": "read_url", "args": {"url": "https://y.com"}},
            ]
        }
        with open(Path(d) / "test_stop.yaml", "w") as f:
            yaml.dump(spec, f)
        
        import tools.workflow_runner as wr
        old_dir = wr.SPECS_DIR
        wr.SPECS_DIR = Path(d)
        
        result = run("test_stop", {})
        assert result.get("ok") == False
        # s2 should NOT have been executed
        assert mock.call_count == 1
        
        wr.SPECS_DIR = old_dir


def test_foreach_runs_multiple_times():
    with patch("tools.workflow_runner.run_workflow") as mock:
        mock.return_value = {"ok": True, "_wr": MagicMock(error_code="ok", provider_used="browser", fallback_used=False, status="ok")}
        
        import tempfile, yaml
        from pathlib import Path
        d = tempfile.mkdtemp()
        spec = {
            "name": "test_foreach",
            "steps": [{
                "foreach": "products",
                "as": "product",
                "action": "search_read",
                "args": {"query": "{product} pricing", "chars": 500},
            }]
        }
        with open(Path(d) / "test_foreach.yaml", "w") as f:
            yaml.dump(spec, f)
        
        import tools.workflow_runner as wr
        old_dir = wr.SPECS_DIR
        wr.SPECS_DIR = Path(d)
        
        result = run("test_foreach", {"products": ["A", "B", "C"]})
        assert mock.call_count == 3
        
        wr.SPECS_DIR = old_dir
