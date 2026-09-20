"""막는 상태는 프로세스보다 오래 산다 — 재시작 래치 (2026-09-20).

`safety.py`는 "푸는 것은 사람이 명시해야 한다"고 선언하고 `clear_estop()`은
누가 풀었는지까지 기록한다. 그런데 상태가 메모리에만 있어서, 정지를 걸어 둔 채
프로세스가 죽었다 살아나면 래치가 False로 태어났다. systemd는
`Restart=on-failure`로 5초 뒤 되살린다 — 사람도 기록도 거치지 않고 풀리는 길이다.

이 시험은 **장치가 없어도 돈다.** 어느 어댑터를 쓰든 같은 문제이므로
장치별 실물 시험에 흩어 놓지 않는다.
"""
from __future__ import annotations

import json

import pytest

from hangeul_runtime import safety


def _restart(path):
    """프로세스가 죽었다 살아난 것과 같다 — 새 상태를 같은 파일에 붙인다."""
    fresh = safety.SafetyState()
    fresh.bind_storage(path)
    return fresh


def test_estop_latch_survives_a_restart(tmp_path):
    path = tmp_path / "safety_state_arm_omx.json"
    before = safety.SafetyState()
    before.bind_storage(path)
    before.latch_estop("과부하")

    after = _restart(path)
    assert after.estop_latched is True, "재시작했더니 긴급 정지가 저절로 풀렸습니다"
    assert after.estop_reason == "과부하"


def test_a_restart_does_not_count_as_a_person_clearing_it(tmp_path):
    """해제는 사람이 한 것만 해제다."""
    path = tmp_path / "s.json"
    before = safety.SafetyState()
    before.bind_storage(path)
    before.latch_estop("과부하")

    # 재시작을 몇 번 해도 풀리지 않는다
    for _ in range(3):
        assert _restart(path).estop_latched is True

    # 사람이 풀면 그때 풀린다
    _restart(path).clear_estop("운영자")
    assert _restart(path).estop_latched is False


def test_the_other_blocking_states_survive_too(tmp_path):
    path = tmp_path / "s.json"
    before = safety.SafetyState()
    before.bind_storage(path)
    before.latch_disconnect("포트가 사라졌습니다")
    before.paused = True
    before.away_mode = True

    after = _restart(path)
    assert after.disconnect_latched is True
    assert after.paused is True
    assert after.away_mode is True
    assert after.blocking_summary(), "막고 있는데 아무것도 안 적혀 있습니다"


def test_permission_to_run_is_never_stored_here(tmp_path):
    """**허용하는 증거는 이 기구로 저장하지 않는다.**

    부품 장착 확인 같은 것은 지속 정책이 정반대다 — 꺼져 있는 동안 누가
    무엇을 뗐는지 알 수 없으므로 재시작하면 다시 확인받아야 한다.
    둘을 한 기구로 처리하면 둘 중 하나가 반드시 틀린다.
    """
    for name in safety.PERSISTED_FIELDS:
        assert any(word in name for word in ("latch", "paused", "away", "reason")), \
            f"막는 상태가 아닌 것이 저장 목록에 있습니다: {name}"


def test_a_torn_file_does_not_silently_unlatch(tmp_path):
    """반쪽 파일을 만나면 조용히 넘어가지 않는다."""
    path = tmp_path / "s.json"
    path.write_text('{"format": "hangeul_robot.safety_state.v1", "estop_la',
                    encoding="utf-8")
    after = safety.SafetyState()
    after.bind_storage(path)
    assert after.to_dict()["persist_error"], "깨진 파일을 읽고도 아무 말이 없습니다"


def test_an_unknown_format_is_not_read(tmp_path):
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"format": "무언가 다른 것", "estop_latched": True}),
                    encoding="utf-8")
    after = safety.SafetyState()
    assert after.bind_storage(path) == {}
    assert after.estop_latched is False


def test_writing_is_atomic_enough_to_leave_no_half_file(tmp_path):
    path = tmp_path / "s.json"
    state = safety.SafetyState()
    state.bind_storage(path)
    for i in range(20):
        state.latch_estop(f"{i}")
    # 임시 파일이 남아 있으면 다음 기동에서 무엇을 읽을지 알 수 없다
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.startswith(".safety_state.")]
    assert not leftovers, f"임시 파일이 남았습니다: {leftovers}"
    assert json.loads(path.read_text(encoding="utf-8"))["estop_latched"] is True


def test_the_runtime_actually_binds_the_file(tmp_path, monkeypatch):
    """런타임이 실제로 이 기구를 쓰는가 — 단위 시험만 통과하고 배선이 빠지면 소용없다."""
    from hangeul_runtime import server

    monkeypatch.setattr(server, "state", safety.SafetyState())
    server.build("arm_omx", "", simulate=True,
                 state_path=str(tmp_path / "safety_state_arm_omx.json"))
    assert server.CONFIG.get("state_path"), "런타임이 막는 상태를 파일에 잇지 않습니다"
    server.state.latch_estop("시험")
    saved = json.loads(open(server.CONFIG["state_path"], encoding="utf-8").read())
    assert saved["estop_latched"] is True
