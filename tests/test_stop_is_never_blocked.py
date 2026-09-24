"""정지는 어떤 검사에도 막히지 않는다 (2026-09-24 전수조사).

`bypass_temperature_check`는 두 곳에서만 온다.

    estop_freeze    긴급 정지 뒤 **그 자리에 세우기**
    recover_hold    복구 뒤 세우기

둘 다 새 동작이 아니라 지금 자리를 그대로 다시 쓰는 일이다. 그래서 온도가
한계를 넘었어도 이 호출은 나가야 한다 — **정확히 그때 필요한 일**이기 때문이다.

MyCobot은 이 인자를 `del`로 버리고 무조건 검사했다. 관절이 뜨거울 때 정지를
누르면 세우는 호출이 예외로 떨어졌다. xArm은 지키고 있었다. 계약이 뜻을
정해 두지 않으면 어댑터마다 갈린다 — 속도에서 이미 겪은 것과 같은 모양이다.
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

HW = Path(__file__).resolve().parents[1] / "runtime" / "src" / "hangeul_runtime" / "hardware"


def _arm_adapters():
    found = []
    for path in sorted(HW.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for cls in [n for n in tree.body if isinstance(n, ast.ClassDef)]:
            bases = [b.id if isinstance(b, ast.Name) else getattr(b, "attr", "")
                     for b in cls.bases]
            if "RobotArmAdapter" in bases:
                found.append((path.name, cls))
    return found


@pytest.mark.parametrize("name,cls", _arm_adapters(), ids=[n for n, _ in _arm_adapters()])
def test_no_adapter_throws_away_the_bypass(name, cls):
    """**받아놓고 버리지 않는다.** 버리면 정지가 그때 막힌다."""
    for fn in [n for n in cls.body if isinstance(n, ast.FunctionDef)]:
        if fn.name != "move_joints":
            continue
        args = {a.arg for a in fn.args.kwonlyargs}
        if "bypass_temperature_check" not in args:
            continue
        deleted = {t.id for d in ast.walk(fn) if isinstance(d, ast.Delete)
                   for t in d.targets if isinstance(t, ast.Name)}
        assert "bypass_temperature_check" not in deleted, (
            f"{name}: 정지용 bypass를 버립니다. 과열이면 정지가 팔을 못 세웁니다")
        used = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)}
        assert "bypass_temperature_check" in used, \
            f"{name}: bypass를 받아놓고 쓰지 않습니다"


def test_the_discovery_is_not_silently_empty():
    assert len(_arm_adapters()) >= 3, "어댑터를 못 찾고 통과하고 있습니다"


class _HotMyCobot:
    """관절 하나가 한계를 넘은 상태."""

    def __init__(self):
        self.sent = []

    def get_angles(self):
        return [0.0] * 6

    def get_servo_temps(self):
        return [90.0, 40.0, 40.0, 40.0, 40.0, 40.0]

    def send_angles(self, angles, speed):
        self.sent.append(("batch", list(angles), speed))

    def send_angle(self, joint_id, degree, speed):
        self.sent.append((joint_id, degree, speed))

    def get_gripper_value(self):
        return 1800

    def is_controller_connected(self):
        return 1

    def get_error_information(self):
        return 0


def test_a_hot_joint_does_not_block_holding_position():
    """과열이어도 **그 자리에 세우는 호출**은 나가야 한다."""
    from hangeul_runtime.hardware.mycobot_280_m5_adapter import MyCobot280M5Adapter

    sdk = _HotMyCobot()
    limits = {"1": 60.0}
    with MyCobot280M5Adapter(device="fake", sdk=sdk) as arm:
        # 새 동작은 막힌다 — 뜨거운데 더 움직이라는 것이므로
        with pytest.raises(RuntimeError):
            arm.move_joints({"1": 0}, velocity=40, acceleration=20, label="새 동작",
                            temperature_limits_c=limits)
        # 정지 뒤 세우기는 나간다
        arm.move_joints({"1": 0}, velocity=40, acceleration=20, label="estop_freeze",
                        temperature_limits_c=limits, bypass_temperature_check=True)
    assert sdk.sent, "과열 때문에 정지가 팔을 세우지 못했습니다"
