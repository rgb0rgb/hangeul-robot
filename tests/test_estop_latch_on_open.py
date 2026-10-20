"""처음 연 화면이 이어받은 긴급 정지를 안다.

실제로 겪은 일(2026-10-20). 런타임의 정지 래치는 파일에 남아 재시작 뒤에도
유지되는데, 화면은 늘 '정지 안 됨'으로 태어났다. 실행은 막히는데 버튼은
'긴급 정지'로만 보여, 정지를 한 번 더 눌렀다 풀어야만 움직였다.
"""
from __future__ import annotations

from types import SimpleNamespace


def _robots(app_mod, monkeypatch):
    robots = [SimpleNamespace(instance_id="omx", display_name="로봇1"),
              SimpleNamespace(instance_id="robot_6", display_name="로봇2")]
    monkeypatch.setattr(app_mod.registry, "all", lambda: robots)
    return robots


def test_screen_learns_a_latch_left_over_from_before(client, monkeypatch):
    from hangeul_console import app as app_mod
    _robots(app_mod, monkeypatch)
    latched = {"omx"}
    monkeypatch.setattr(app_mod.runtime, "health", lambda i: {
        "connected": True,
        "runtime": {"estop_active": i.instance_id in latched, "estop_reason": "운영자 요청"}})
    body = client.get("/api/estop-status").json()
    assert body["estop_active"] is True
    assert body["latched"] == [{"robot_id": "omx", "robot_label": "로봇1", "reason": "운영자 요청"}]

    latched.clear()
    assert client.get("/api/estop-status").json()["estop_active"] is False


def test_unreachable_runtime_is_not_reported_as_latched(client, monkeypatch):
    from hangeul_console import app as app_mod
    _robots(app_mod, monkeypatch)
    monkeypatch.setattr(app_mod.runtime, "health", lambda i: {"connected": False})
    assert client.get("/api/estop-status").json()["estop_active"] is False


def test_screen_syncs_the_latch_on_open():
    from pathlib import Path
    js = (Path(__file__).resolve().parents[1] / "console" / "web" / "simple.js").read_text(encoding="utf-8")
    assert "fetch(BACKEND + '/api/estop-status')" in js
    assert "syncEstopFromServer();" in js
