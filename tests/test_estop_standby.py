"""긴급 정지 · 대기 로봇.

실제로 겪은 일(2026-10-05). OMX 한 대만 쓰고 나머지 두 대는 목록에만 있었는데,
정지할 때마다 "2대가 멈춤에 응답하지 않았습니다: robot_6, young_mycobot"이 떴다.
런타임이 안 떠 있는 로봇은 움직일 수단이 없으니 못 멈춘 것이 아니다.
다만 떠 있는데 답이 늦은 것은 진짜 '못 멈춤'이고, 그건 숨기지 않는다.
"""
from __future__ import annotations

import socket
import threading
from types import SimpleNamespace


def _robots(app_mod, monkeypatch):
    robots = [SimpleNamespace(instance_id="omx", display_name="로봇1"),
              SimpleNamespace(instance_id="robot_6", display_name="로봇2")]
    monkeypatch.setattr(app_mod.registry, "all", lambda: robots)
    monkeypatch.setattr(app_mod.repeat_work, "control", lambda *a, **k: None)
    return robots


def test_estop_does_not_count_a_robot_without_a_runtime_as_failed(client, monkeypatch):
    from hangeul_console import app as app_mod
    _robots(app_mod, monkeypatch)
    monkeypatch.setattr(app_mod.runtime, "stop", lambda i: (
        {"stopped": True, "detail": {}} if i.instance_id == "omx"
        else {"stopped": False, "absent": True, "reason": "연결 거부"}))
    answer = client.post("/api/estop", json={}).json()
    assert answer["warning"] == "", answer["warning"]


def test_estop_still_warns_by_display_name_when_a_live_runtime_does_not_answer(client, monkeypatch):
    from hangeul_console import app as app_mod
    _robots(app_mod, monkeypatch)
    monkeypatch.setattr(app_mod.runtime, "stop", lambda i: (
        {"stopped": True, "detail": {}} if i.instance_id == "omx"
        else {"stopped": False, "absent": False, "reason": "TimeoutError"}))
    answer = client.post("/api/estop", json={}).json()
    assert "1대가 멈춤에 응답하지 않았습니다: 로봇2" == answer["warning"], answer["warning"]


def test_only_a_refused_connection_means_nobody_is_there():
    """연결 거부만 '없음'이다. 시간 초과는 떠 있는데 바쁜 것일 수 있다."""
    from hangeul_console.runtime_link import RuntimeLink

    link = RuntimeLink()
    link._identify = lambda instance, payload: payload
    link._query = lambda instance: ""

    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    gone = link._call(SimpleNamespace(runtime_url=f"http://127.0.0.1:{port}"), "/api/estop",
                      {}, timeout=1, method="POST")
    assert gone["refused"] is True

    silent = socket.socket(); silent.bind(("127.0.0.1", 0)); silent.listen(1)
    release = threading.Event()

    def hold():
        conn, _ = silent.accept(); release.wait(3); conn.close()

    threading.Thread(target=hold, daemon=True).start()
    slow = link._call(SimpleNamespace(runtime_url=f"http://127.0.0.1:{silent.getsockname()[1]}"),
                      "/api/estop", {}, timeout=0.5, method="POST")
    release.set(); silent.close()
    assert slow["ok"] is False and slow["refused"] is False


# 2026-10-19: 일시정지/해제에도 같은 일이 있었다 — "2대가 일시정지 해제에 응답하지 않았습니다"
def test_pause_and_release_do_not_count_a_robot_without_a_runtime_as_failed(client, monkeypatch):
    from hangeul_console import app as app_mod
    _robots(app_mod, monkeypatch)
    monkeypatch.setattr(app_mod.runtime, "forward", lambda i, path, payload, method="POST": (
        {"success": True} if i.instance_id == "omx"
        else {"success": False, "verdict": "RUNTIME_UNREACHABLE", "absent": True}))
    for paused in (True, False):
        answer = client.post("/api/pause-hold", json={"paused": paused}).json()
        assert answer["warning"] == "", answer["warning"]


def test_pause_release_still_warns_by_display_name_when_a_live_runtime_fails(client, monkeypatch):
    from hangeul_console import app as app_mod
    _robots(app_mod, monkeypatch)
    monkeypatch.setattr(app_mod.runtime, "forward", lambda i, path, payload, method="POST": (
        {"success": True} if i.instance_id == "omx"
        else {"success": False, "verdict": "RUNTIME_UNREACHABLE", "absent": False}))
    answer = client.post("/api/pause-hold", json={"paused": False}).json()
    assert answer["warning"] == "1대가 일시정지 해제에 응답하지 않았습니다: 로봇2", answer["warning"]
