"""전류 한계 — 정상 동작을 막지 않고, 진짜 과부하는 막는다.

실제로 겪은 일(2026-08-19). OMX가 자세를 실행하다 긴급 정지에 걸렸다.

    J13 전류 144가 한계 140 초과

J13은 팔에서 **정적 부하를 가장 많이 받는 관절**인데 한계가 140으로 여섯 중
가장 낮게 잡혀 있었다(나머지는 250). 그래서 아무 이상 없는 자세에서도 141~150이
나왔고, 3연속이면 정지가 걸려 그 뒤 모든 동작이 막혔다. 방향이 거꾸로였다.

한계값은 **부품 기술서가 정한다.** 코드에 박아 두면 팔마다 다른 값을 줄 수 없고,
값 하나 바꾸는 데 코드를 고쳐야 한다.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from hangeul_runtime.hardware.openmanipulator_x_arm_adapter import (
    classify_joint_current_limit,
)

ROOT = Path(__file__).resolve().parents[1]
OMX = json.loads((ROOT / "install" / "modules" / "arm_omx.json").read_text(encoding="utf-8"))
LIMITS = OMX.get("current_limits") or {}


def test_the_descriptor_carries_the_limits_not_the_code():
    assert LIMITS, "기술서에 전류 한계가 없다 — 값이 코드에 숨으면 팔마다 다르게 줄 수 없다"
    assert LIMITS.get("reason"), "왜 이 값인지 적혀 있지 않으면 다음 사람이 되돌린다"


@pytest.mark.parametrize("current", [120, 144, 150, 205])
def test_a_normal_pose_does_not_trip_the_stop(current):
    """실측된 정상값(141~150)에서 멈추면 안 된다 — 그 뒤 모든 동작이 막힌다."""
    blocked, _, _ = classify_joint_current_limit(13, current, 0, LIMITS)
    assert not blocked
    blocked_after, _, _ = classify_joint_current_limit(13, current, 2, LIMITS)
    assert not blocked_after, f"J13 {current}는 정상 범위인데 연속 표본에서 막혔다"


def test_a_sustained_overload_still_stops():
    """넘긴 것이 계속 이어지면 막는다. 순간의 튐과 계속되는 과부하는 다르다."""
    first, count, _ = classify_joint_current_limit(13, 215, 0, LIMITS)
    assert not first, "한 번 튄 것으로 멈추면 정상 동작이 자주 끊긴다"
    blocked, _, _ = classify_joint_current_limit(13, 215, 2, LIMITS)
    assert blocked, "계속 넘기는데도 안 막으면 서보가 탄다"


@pytest.mark.parametrize("current", [245, 400, 802])
def test_a_real_fault_stops_on_the_first_reading(current):
    """실제 고장 때 나온 값(J14에서 802 관측)은 그 자리에서 막는다."""
    blocked, _, _ = classify_joint_current_limit(13, current, 0, LIMITS)
    assert blocked


def test_other_joints_keep_their_own_limit():
    assert classify_joint_current_limit(12, 260, 0, LIMITS)[0] is True
    assert classify_joint_current_limit(12, 240, 0, LIMITS)[0] is False


def test_j13_is_not_stricter_than_the_rest_of_the_arm():
    """가장 무거운 짐을 지는 관절에 가장 낮은 한계를 주면 그 관절만 늘 걸린다."""
    default = int(LIMITS.get("default_raw", 250))
    j13 = (LIMITS.get("per_joint_raw") or {}).get("13") or {}
    assert int(j13.get("strict", default)) > 150, \
        "실측된 정상값(141~150)보다 낮은 한계는 정상 동작을 막는다"
