"""한 번에 한 가지 일만 시킨다 (2026-09-24 전수조사).

`SERIAL_LOCK`은 **명령 한 건씩**만 줄 세운다. 그래서 순서 실행이 도는 중에
상태점검을 누르면 둘이 번갈아 나가고, 팔이 두 목표 사이를 오간다.
콘솔도 런타임도 막고 있지 않았다.

**정지 계열은 이 문을 쓰지 않는다.** 멈추는 일이 무언가 끝나기를 기다리면
그것은 멈춤이 아니다.
"""
from __future__ import annotations

import pytest

from hangeul_runtime import safety, server


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setattr(server, "_pace", lambda *a, **k: None)
    monkeypatch.setattr(server, "state", safety.SafetyState())
    server._JOB.update({"name": "", "since": 0.0})
    yield
    server._JOB.update({"name": "", "since": 0.0})


def test_a_second_job_is_refused_with_a_reason():
    with server._exclusive("순서 실행"):
        answer = server.move_to({"joint_id": "11", "target_ticks": 2048})
    assert answer["verdict"] == "BLOCKED_BUSY"
    assert "순서 실행" in answer["running_job"]
    assert answer["blocked_reasons"], "막아놓고 이유를 안 적었습니다"
    assert answer["actual_hardware_called"] is False


@pytest.mark.parametrize("call", [
    lambda: server.move_to({"joint_id": "11", "target_ticks": 2048}),
    lambda: server.jog({"joint_id": "11", "delta_ticks": 10}),
    lambda: server.execute_actual({"targets": {"11": 2048}}),
])
def test_every_motion_request_checks_the_door(call):
    with server._exclusive("상태점검"):
        assert call()["verdict"] == "BLOCKED_BUSY"


def test_the_door_opens_again_when_the_job_ends():
    with server._exclusive("상태점검"):
        pass
    assert server._JOB["name"] == "", "일이 끝났는데 문이 잠긴 채입니다"


def test_the_door_opens_even_if_the_job_blows_up():
    with pytest.raises(RuntimeError):
        with server._exclusive("상태점검"):
            raise RuntimeError("도중에 터짐")
    assert server._JOB["name"] == "", "터진 뒤 문이 잠긴 채 남았습니다"


def test_two_jobs_cannot_hold_it_at_once():
    with server._exclusive("상태점검"):
        with pytest.raises(server._Busy):
            with server._exclusive("순서 실행"):
                pass


# ── 정지는 기다리지 않는다 ──────────────────────────────────────
def test_stopping_never_waits_for_the_running_job():
    """**멈춤이 무언가 끝나기를 기다리면 그것은 멈춤이 아니다.**"""
    with server._exclusive("상태점검"):
        answer = server.estop({"reason": "시험"})
    assert answer.get("estop_active") or server.state.estop_latched, \
        "일이 도는 중이라고 정지가 막혔습니다"


def test_pausing_and_away_mode_are_not_blocked_either():
    with server._exclusive("상태점검"):
        server.pause_hold({"paused": True})
        server.away_mode({"away_mode": True})
    assert server.state.paused is True
    assert server.state.away_mode is True


def test_the_stop_paths_do_not_consult_the_door():
    """글자로도 확인한다 — 나중에 누가 정지 경로에 문을 달지 못하게."""
    import inspect

    for fn in (server.estop, server.pause_hold, server.away_mode):
        body = inspect.getsource(fn)
        assert "_JOB[" not in body, f"{fn.__name__}이 문을 봅니다 — 정지는 기다리지 않습니다"
