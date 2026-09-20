"""속도 계약 — 관절별 한계는 상한이지 덮어쓰기가 아니다 (2026-09-20).

`move_joints(velocity_per_joint=...)`의 뜻이 계약에 적혀 있지 않았다. 그래서
세 어댑터가 **셋 다 다르게** 갔다.

    OMX       min() — 상한.   지켰다
    MyCobot   관절별 값으로 요청을 갈아치움. 출하 기본값이 전 관절 50이라
              "느리게 가라"(10)가 50으로 나갔다

계약이 뜻을 안 정했으므로 둘 다 "맞았다". 그래서 이 시험은 뜻을 고정한다.

    SDK에 실제로 넘어간 값 ≤ 요청값
    SDK에 실제로 넘어간 값 ≤ 한계값

**장치 사이의 숫자를 비교하지 않는다.** MyCobot은 1~100 눈금, OMX는 Dynamixel
프로파일 속도, ROS 2는 rad/s다. 같은 숫자가 같은 물리 속도일 이유가 없다.
각 어댑터가 자기 눈금 안에서 위 두 부등식을 지키는지만 본다.

**실물이 필요 없다.** SDK 자리에 가짜를 두고 넘어간 인자를 본다.
이것은 SDK 인자 확인이지 실물 속도 계측이 아니다 — 둘은 다른 증거다.
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from hangeul_runtime.abstraction.robot_arm_adapter import (
    batch_velocity,
    effective_velocity,
)

ROOT = Path(__file__).resolve().parents[1]
HARDWARE = ROOT / "runtime" / "src" / "hangeul_runtime" / "hardware"


# ── 1. 계약 자체 ────────────────────────────────────────────────
@pytest.mark.parametrize("requested", [1, 10, 40, 120, 200])
@pytest.mark.parametrize("limit", [None, 1, 10, 50, 200, 1000])
def test_the_limit_never_speeds_a_request_up(requested, limit):
    got = effective_velocity(requested, limit)
    assert got <= requested, f"요청 {requested}인데 {got}으로 나갑니다"
    if limit is not None:
        assert got <= limit or got == 1, f"한계 {limit}인데 {got}으로 나갑니다"
    assert got >= 1, "0은 SDK마다 뜻이 달라 그대로 내보내면 안 됩니다"


def test_the_most_restrictive_limit_wins_in_a_batch():
    """배치 하나에 속도가 하나만 실리면 가장 엄한 한계를 따른다."""
    assert batch_velocity(200, {"1": 50, "2": 80}, ["1", "2"]) == 50
    assert batch_velocity(10, {"1": 50, "2": 80}, ["1", "2"]) == 10
    assert batch_velocity(200, {}, ["1"]) == 200


# ── 2. 어느 어댑터도 스스로 계산하지 않는다 ──────────────────────
def _adapters_taking_per_joint():
    """velocity_per_joint를 받는 move_joints를 **스스로 찾는다.**

    새 어댑터를 넣으면 자동으로 이 시험을 받는다 — 사람이 목록을 관리하면
    언젠가 빠뜨리고, 그게 셋이 갈린 이유였다.
    """
    found = []
    for path in sorted(HARDWARE.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef) or node.name != "move_joints":
                continue
            names = {a.arg for a in node.args.kwonlyargs} | {a.arg for a in node.args.args}
            if "velocity_per_joint" in names:
                found.append((path.name, node))
    return found


@pytest.mark.parametrize("name,node", _adapters_taking_per_joint(),
                         ids=[n for n, _ in _adapters_taking_per_joint()])
def test_every_adapter_routes_through_the_contract(name, node):
    called = {n.func.id for n in ast.walk(node)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert called & {"effective_velocity", "batch_velocity"}, (
        f"{name}의 move_joints가 관절별 속도를 스스로 계산합니다. "
        f"계약(effective_velocity/batch_velocity)을 거쳐야 합니다")


def test_the_discovery_is_not_silently_empty():
    assert len(_adapters_taking_per_joint()) >= 2, "어댑터를 못 찾고 통과하고 있습니다"


# ── 3. MyCobot — 실제로 버그가 있던 자리 ────────────────────────
class _FakeMyCobotSDK:
    """넘어온 인자를 받아 적는 가짜. 실물 대신이 아니라 **기록계**다."""

    def __init__(self):
        self.angles = [0.0] * 6
        self.sent = []          # (관절, 각도, 속도)
        self.batch = []         # (각도목록, 속도)

    def get_angles(self):
        return list(self.angles)

    def send_angle(self, joint_id, degree, speed):
        self.sent.append((joint_id, degree, speed))
        self.angles[joint_id - 1] = degree

    def send_angles(self, angles, speed):
        self.batch.append((list(angles), speed))
        self.angles = list(angles)

    def get_gripper_value(self):
        return 50

    def is_controller_connected(self):
        return 1

    def get_error_information(self):
        return 0


def _mycobot(sdk, **kw):
    from hangeul_runtime.hardware.mycobot_280_m5_adapter import MyCobot280M5Adapter
    return MyCobot280M5Adapter(device="fake", sdk=sdk, **kw)


def test_mycobot_slow_request_stays_slow_even_with_a_higher_limit():
    """출하 기본값이 전 관절 50이다. 10으로 가라면 10으로 가야 한다."""
    sdk = _FakeMyCobotSDK()
    with _mycobot(sdk, excluded_joint_ids=["4"]) as arm:
        arm.move_joints({"1": 0, "2": 0}, velocity=10, acceleration=20, label="시험",
                        velocity_per_joint={"1": 50, "2": 50})
    speeds = [s for _, _, s in sdk.sent] + [s for _, s in sdk.batch]
    assert speeds, "SDK에 아무것도 안 보냈습니다"
    assert max(speeds) <= 10, f"요청 10인데 {max(speeds)}로 나갔습니다"


def test_mycobot_limit_still_caps_a_fast_request():
    sdk = _FakeMyCobotSDK()
    with _mycobot(sdk, excluded_joint_ids=["4"]) as arm:
        arm.move_joints({"1": 0, "2": 0}, velocity=200, acceleration=20, label="시험",
                        velocity_per_joint={"1": 30, "2": 30})
    speeds = [s for _, _, s in sdk.sent] + [s for _, s in sdk.batch]
    assert max(speeds) <= 30, f"한계 30인데 {max(speeds)}로 나갔습니다"

# xArm 어댑터는 공개판에 들어 있지 않다. 그쪽에서 같은 결함(인자를 받아놓고
# 버림)을 찾아 고쳤고, 위의 계약 시험이 **어댑터를 스스로 찾으므로**
# 공개판에 들어오는 날 자동으로 같은 시험을 받는다.
