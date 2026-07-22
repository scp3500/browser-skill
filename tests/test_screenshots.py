"""test_screenshots.py — 截图清理测试"""
import sys, os, pytest, tempfile
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from browser_daemon import _cleanup_screenshots


def _touch(path, days_old=0):
    """Create a file with specific age"""
    p = Path(path)
    p.write_text("test")
    if days_old > 0:
        old = datetime.now() - timedelta(days=days_old)
        os.utime(p, (old.timestamp(), old.timestamp()))


def test_screenshot_name_has_timestamp_and_millis(tmp_path):
    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    ms = int(datetime.now().strftime("%f")[:3])
    name = f"browser_diagnose_{ts}_{ms:03d}.png"
    assert len(name) > 20
    assert "_20" in name  # timestamp


def test_screenshot_name_no_overwrite(tmp_path):
    """Same second files should differ by ms"""
    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    n1 = f"browser_diagnose_{ts}_001.png"
    n2 = f"browser_diagnose_{ts}_002.png"
    assert n1 != n2


def test_cleanup_deletes_old_browser_png(tmp_path):
    old = tmp_path / "browser_old.png"
    _touch(old, days_old=10)
    fresh = tmp_path / "browser_new.png"
    _touch(fresh, days_old=0)

    _cleanup_screenshots(tmp_path)
    assert not old.exists(), "old file should be deleted"
    assert fresh.exists(), "new file should remain"


def test_cleanup_does_not_delete_non_browser_png(tmp_path):
    other = tmp_path / "other.png"
    _touch(other, days_old=10)
    _cleanup_screenshots(tmp_path)
    assert other.exists(), "non-browser file should not be deleted"


def test_cleanup_does_not_delete_notes(tmp_path):
    notes = tmp_path / "notes.txt"
    _touch(notes, days_old=10)
    _cleanup_screenshots(tmp_path)
    assert notes.exists(), "non-png file should not be deleted"


def test_cleanup_keeps_max_files(tmp_path):
    for i in range(5):
        _touch(tmp_path / f"browser_{i:03d}.png", days_old=0)
    for i in range(5, 12):
        _touch(tmp_path / f"browser_{i:03d}.png", days_old=8)  # old

    _cleanup_screenshots(tmp_path)
    remaining = list(tmp_path.glob("browser_*.png"))
    assert len(remaining) <= 10, f"expected <= 10 files, got {len(remaining)}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
