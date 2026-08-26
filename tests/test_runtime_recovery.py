"""정지 해제는 상태 표시가 아니라 복구다.

실제로 겪은 일: OMX J12에 과부하 래치가 걸리자 런타임이 단선 래치를 걸고
그 뒤 모든 동작을 막았다. 화면에서 정지를 풀어도 서보의 오류 래치는 그대로여서
로봇은 계속 움직이지 않았다. **해제했는데 안 움직이면 그건 해제가 아니다.**
"""
from __future__ import annotations

import pytest

from hangeul_runtime import safety, server


class FakeArm:
    """실물 대신. 오류 래치가 걸렸다가 REBOOT으로 풀리는 팔."""

    def __init__(self):
        self.faulted = True
        self.rebooted = False
        self.held = None
        self.position = {"11": 2048, "12": 1500, "13": 2600, "14": 2000, "15": 1900}

    def recover_from_fault(self):
        self.rebooted = True
        before = 32 if self.faulted else 0
        self.faulted = False
        return {12: {"hardware_error_before": before, "rebooted": True,
                     "hardware_error_after": 0}}

    def read_joint_positions(self):
        return dict(self.position)

    def move_joints(self, targets, **kwargs):
        if self.faulted:
            raise RuntimeError("과부하 래치가 걸려 있습니다")
        self.held = dict(targets)
        self.position.update(targets)
        return {"success": True}


@pytest.fixture
def runtime(monkeypatch):
    server.build("arm_omx", "", simulate=True)
    arm = FakeArm()
    server.CONFIG["adapter"] = arm
    server.state.estop_latched = False
    server.state.disconnect_latched = False
    yield arm
    server.CONFIG["adapter"] = None


def test_reset_reboots_the_faulted_servo_and_holds_it(runtime):
    server.state.latch_estop("과부하")
    server.state.latch_disconnect("hardware_error=32 overload")

    answer = server.estop_reset({"operator": "운영자", "confirmed": True})

    assert answer["success"] is True
    assert runtime.rebooted, "오류가 걸린 서보를 되살리지 않았다"
    assert runtime.held, "복구 뒤 그 자리에 세우지 않았다 — 토크가 꺼진 채 남으면 팔이 처진다"
    assert server.state.estop_latched is False
    assert server.state.disconnect_latched is False


def test_after_reset_the_robot_moves_again(runtime):
    server.state.latch_disconnect("hardware_error=32 overload")
    blocked = server.jog({"joint_id": 12, "delta_ticks": -30})
    assert blocked["success"] is False
    assert "정지 해제" in blocked["blocked_reasons"][0], "무엇을 눌러야 하는지 알려주지 않는다"

    server.estop_reset({"operator": "운영자", "confirmed": True})
    moved = server.jog({"joint_id": 12, "delta_ticks": -30})
    assert moved["success"] is True
    assert moved["target"] == 1470


def test_reset_without_confirmation_is_refused(runtime):
    server.state.latch_estop("과부하")
    answer = server.estop_reset({"operator": "운영자"})
    assert answer["success"] is False
    assert server.state.estop_latched is True


def test_stop_does_not_cut_torque(runtime):
    """토크를 끊으면 팔이 떨어진다(라운드 472). 지금 자리를 목표로 다시 쓴다."""
    runtime.faulted = False
    server.estop({"reason": "시험"})
    assert runtime.held == {j: v for j, v in runtime.position.items() if j != "15"}
    assert server.state.estop_latched is True


def test_limits_come_from_the_part_descriptor():
    """단위 변환은 부품 기술서의 unit 항목에서만 나온다."""
    server.build("arm_omx", "", simulate=True)
    bands = server._normalize_limits({"11": [-180, 180], "15_min": 1060, "15_max": 2720})
    assert bands["11"] == [0, 4096]          # 도 → 틱
    assert bands["15"] == [1060, 2720]       # 손은 자기 단위 그대로

    server.build("arm_mycobot", "", simulate=True)
    bands = server._normalize_limits({"1": [-84, 84], "7_min": 0, "7_max": 100})
    assert bands["1"] == [-84000, 84000]     # 도 → 밀리도
    assert bands["7"] == [0, 100]
