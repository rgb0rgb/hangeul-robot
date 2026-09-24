"""ROS 2 계약 반증 — 1차 (2026-09-20).

**목적은 연동 제품화가 아니라 지금 계약의 가정을 깨 보는 것이다.**
범위는 `ros2_control`의 `JointTrajectoryController` 하나, `FollowJointTrajectory`
하나다. MoveIt · Nav2 · 다중 컨트롤러 · 독립 그리퍼는 이번에 다루지 않는다.

**1차의 통과 기준은 "핵심 코드 변경 0"이 아니다.** 1차의 목적이 그 가정을
찾는 것이기 때문이다. 필요한 변경을 이유와 함께 남기고, **수정이 필요했다면
"부품만 바꾸면 붙는다"는 주장은 그 사례에서 실패한 것**으로 적는다.
"변경 0"은 고친 계약으로 **다른** 장치를 붙이는 2차의 기준이다.

여기서 확인하는 것은 **SDK에 무엇이 넘어갔는가**다. 실물도 가상 팔도 아직
붙이지 않았다 — 이것은 코드 수준 증거이고, 실물 증거와 같이 취급하지 않는다.
"""
from __future__ import annotations

import math

import pytest

from hangeul_runtime.hardware.ros2_arm_adapter import Ros2ArmAdapter

DESCRIPTOR = {
    "joints": [
        {"id": "shoulder_pan_joint", "role": "base"},
        {"id": "shoulder_lift_joint", "role": "joint"},
    ],
    "unit": {"kind": "millidegree", "per_degree": 1000},
}


class _FakeNode:
    """넘어간 인자를 받아 적는 기록계. 실물 대신이 아니다."""

    def __init__(self, *, accept=True, result_ok=True):
        self.goals = []
        self.cancels = 0
        self.accept = accept
        self.result_ok = result_ok
        self.positions = {"shoulder_pan_joint": 0.0, "shoulder_lift_joint": 0.0}

    def joint_positions(self):
        return dict(self.positions)

    def server_ready(self):
        return True

    def send_trajectory(self, *, joint_names, positions, time_from_start_s, label):
        self.goals.append({"joint_names": list(joint_names),
                           "positions": list(positions),
                           "time_from_start_s": time_from_start_s,
                           "label": label})
        if self.accept and self.result_ok:
            self.positions.update(dict(zip(joint_names, positions)))
        return {"accepted": self.accept, "result_ok": self.result_ok}

    def cancel_all(self):
        self.cancels += 1


def _arm(node):
    return Ros2ArmAdapter(device="/jtc", descriptor=DESCRIPTOR, node=node)


# ── 깨려던 가정들 ───────────────────────────────────────────────
def test_joint_names_are_strings_and_come_from_the_descriptor():
    """관절이 숫자라는 가정. 이름은 **코드가 아니라 기술서**가 들고 있어야 한다."""
    arm = _arm(_FakeNode())
    assert arm.joint_names == ["shoulder_pan_joint", "shoulder_lift_joint"]


def test_the_console_can_build_a_robot_whose_joints_have_names():
    """`int(joint_id)`가 곳곳에 있었다 — 이름이 오면 막히는 게 아니라 깨졌다."""
    from pathlib import Path

    from hangeul_console import configuration, module as module_mod

    mods, problems = module_mod.load_all(Path(__file__).resolve().parents[1]
                                         / "install" / "modules")
    assert not problems, problems
    config = configuration.build("ros2", "ros2", mods, ["core_a", "arm_ros2"])
    assert not config.problems, config.problems
    assert "shoulder_pan_joint" in config.arm().joint_ids()
    assert config.fingerprint()            # 지문도 나와야 한다
    view = config.joint_view()
    assert any(v["joint_id"] == "shoulder_pan_joint" for v in view)


def test_numeric_joint_ids_still_fold_to_numbers():
    """**기존 지문을 지키기 위해서다.** 11과 "11"은 같은 관절이다."""
    from hangeul_console.module import normalize_joint_id

    assert normalize_joint_id(11) == 11
    assert normalize_joint_id("11") == 11
    # 되돌릴 수 없는 것은 모으지 않는다 — "011"과 "11"이 같아지면 충돌한다
    assert normalize_joint_id("011") == "011"
    assert normalize_joint_id("shoulder_pan_joint") == "shoulder_pan_joint"


def test_degrees_go_out_as_radians():
    """SDK 단위가 도가 아니라 라디안 실수라는 가정."""
    node = _FakeNode()
    with _arm(node) as arm:
        arm.move_joints({"shoulder_pan_joint": 90_000},   # 밀리도 = 90.000°
                        velocity=100, acceleration=20, label="시험")
    sent = node.goals[0]["positions"][0]
    assert math.isclose(sent, math.radians(90.0), rel_tol=1e-9), sent


def test_reading_comes_back_in_robot_units():
    node = _FakeNode()
    node.positions["shoulder_pan_joint"] = math.radians(45.0)
    with _arm(node) as arm:
        assert arm.read_joint_positions()["shoulder_pan_joint"] == 45_000


# ── 접수와 완료는 다르다 ────────────────────────────────────────
def test_a_rejected_goal_is_not_reported_as_success():
    node = _FakeNode(accept=False)
    with _arm(node) as arm:
        answer = arm.move_joints({"shoulder_pan_joint": 1000},
                                 velocity=100, acceleration=20, label="시험")
    assert answer["success"] is False
    assert answer["accepted"] is False
    assert answer["error"]


def test_accepted_but_unfinished_is_not_success():
    """**접수는 완료가 아니다.** 접수를 완료로 적으면 화면은 갔다고 하고 팔은 안 간다."""
    node = _FakeNode(accept=True, result_ok=False)
    with _arm(node) as arm:
        answer = arm.move_joints({"shoulder_pan_joint": 1000},
                                 velocity=100, acceleration=20, label="시험")
    assert answer["accepted"] is True
    assert answer["success"] is False


def test_stop_cancels_the_goal():
    node = _FakeNode()
    with _arm(node) as arm:
        arm.stop()
    assert node.cancels == 1


def test_partial_goal_holds_other_joints_at_measured_position():
    node = _FakeNode()
    node.positions["shoulder_lift_joint"] = 0.4
    with _arm(node) as arm:
        arm.move_joints({"shoulder_pan_joint": 10000}, velocity=20,
                        acceleration=20, label="partial")
    sent = dict(zip(node.goals[0]["joint_names"], node.goals[0]["positions"]))
    # The existing integer contract quantizes positions to 0.001 degrees.
    assert sent["shoulder_lift_joint"] == pytest.approx(0.4, abs=math.radians(0.0005))


def test_result_arriving_before_final_state_does_not_falsely_fail():
    class DelayedState(_FakeNode):
        old_sample = None

        def send_trajectory(self, **kwargs):
            self.old_sample = dict(self.positions)
            return super().send_trajectory(**kwargs)

        def joint_positions(self):
            if self.old_sample is not None:
                sample, self.old_sample = self.old_sample, None
                return sample
            return super().joint_positions()

    with _arm(DelayedState()) as arm:
        result = arm.move_joints({"shoulder_pan_joint": 10000}, velocity=20,
                                 acceleration=20, label="late-state")
    assert result["success"]


@pytest.mark.parametrize("invalid", [None, float("nan"), float("inf")])
def test_invalid_measurement_never_becomes_a_zero_position_goal(invalid):
    node = _FakeNode()
    if invalid is None:
        del node.positions["shoulder_lift_joint"]
    else:
        node.positions["shoulder_lift_joint"] = invalid
    with _arm(node) as arm, pytest.raises(RuntimeError):
        arm.move_joints({"shoulder_pan_joint": 10000}, velocity=20,
                        acceleration=20, label="invalid-state")
    assert not node.goals


# ── 속도 계약은 여기에도 걸린다 ─────────────────────────────────
def test_the_strictest_limit_shapes_the_trajectory_time():
    """속도 눈금이 없는 SDK다. 한계는 **시간**으로 나타난다 — 느릴수록 길게."""
    slow, fast = _FakeNode(), _FakeNode()
    with _arm(slow) as arm:
        arm.move_joints({"shoulder_pan_joint": 30000, "shoulder_lift_joint": 30000},
                        velocity=200, acceleration=20, label="느리게",
                        velocity_per_joint={"shoulder_pan_joint": 10})
    with _arm(fast) as arm:
        arm.move_joints({"shoulder_pan_joint": 30000, "shoulder_lift_joint": 30000},
                        velocity=200, acceleration=20, label="빠르게")
    assert slow.goals[0]["time_from_start_s"] > fast.goals[0]["time_from_start_s"], \
        "가장 엄한 한계가 궤적 시간에 반영되지 않았습니다"


# ── 없는 능력을 약속하지 않는다 ─────────────────────────────────
def test_the_hand_is_refused_with_a_reason_not_faked():
    """독립 그리퍼는 이번 범위가 아니다. 조용히 성공을 돌려주지 않는다."""
    with _arm(_FakeNode()) as arm:
        with pytest.raises(RuntimeError) as exc:
            arm.move_gripper(100, velocity=50, acceleration=20, label="시험")
    assert "손" in str(exc.value)


def test_the_adapter_says_what_it_cannot_attest():
    with _arm(_FakeNode()) as arm:
        parts = arm.attest_parts()
    assert parts["arm"]["responding"] is True
    assert parts["hand"]["responding"] is None


# ── 첫 공통 작업: 두 자세 순서 재생 ─────────────────────────────
def test_the_first_common_task_is_two_taught_poses_in_order():
    """집기가 아니다 — 독립 그리퍼가 없는데 집기를 시연하면 없는 능력을 약속한다."""
    node = _FakeNode()
    pose_a = {"shoulder_pan_joint": 10_000, "shoulder_lift_joint": 0}
    pose_b = {"shoulder_pan_joint": 30_000, "shoulder_lift_joint": 20_000}
    with _arm(node) as arm:
        first = arm.move_joints(pose_a, velocity=80, acceleration=20, label="자세 A")
        second = arm.move_joints(pose_b, velocity=80, acceleration=20, label="자세 B")
        ended_at = arm.read_joint_positions()
    assert first["success"] and second["success"]
    assert [g["label"] for g in node.goals] == ["자세 A", "자세 B"], "순서가 지켜지지 않았습니다"
    assert ended_at["shoulder_pan_joint"] == 30_000
