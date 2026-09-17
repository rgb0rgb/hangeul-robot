"""Transport failures must remain visible in motion controls."""
import pytest
from hangeul_console.runtime_link import RuntimeLink

@pytest.mark.parametrize("path", ["/api/jog", "/api/move-to"])
def test_unreachable_motion_has_display_error(monkeypatch, path):
    link = RuntimeLink()
    monkeypatch.setattr(link, "_call", lambda *a, **k: {
        "ok": False, "reason": "runtime connection refused"})
    result = link.forward(None, path, {"joint_id": 11})
    assert result["success"] is False
    assert result["error"] == "runtime connection refused"
    assert result["verdict"] == "RUNTIME_UNREACHABLE"


def test_http_failure_preserves_block_reason(monkeypatch):
    link = RuntimeLink()
    monkeypatch.setattr(link, "_call", lambda *a, **k: {
        "ok": False, "reason": "HTTP 409", "data": {
            "verdict": "BLOCKED", "blocked_reasons": ["stop active"]}})
    result = link.forward(None, "/api/jog", {})
    assert result["success"] is False
    assert result["blocked_reasons"] == ["stop active"]
    assert result["error"] == ["stop active"]


def test_read_pose_failure_has_display_error(monkeypatch):
    link = RuntimeLink()
    monkeypatch.setattr(link, "_call", lambda *a, **k: {
        "ok": False, "reason": "connection refused"})
    assert link.read_pose(None)["error"] == "connection refused"
