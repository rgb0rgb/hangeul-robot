"""ROS 2 adapter for one ros2_control JointTrajectoryController.

실제 DDS 가상 장치 연결을 검증한다. 실물 액추에이터 검증과 구분한다.
앞의 세 로봇(OMX · MyCobot · xArm)이 공유하던 가정을 한 번에 때린다.

    시리얼/이더넷이 아니라 **DDS**              — 장치 이름이 포트도 IP도 아니다
    관절 번호가 숫자가 아니라 **문자열 이름**   — "shoulder_pan_joint"
    SDK 단위가 도가 아니라 **라디안 실수**
    명령 접수와 완료가 **따로**                 — goal / feedback / result / cancel
    손이 팔과 **다른 action server**            — 이번 범위에서는 제외한다

**범위를 좁게 못 박는다.** JointTrajectoryController 하나, FollowJointTrajectory
하나다. MoveIt · Nav2 · 다중 컨트롤러 · 이동로봇은 이번에 다루지 않는다.
클래스가 로딩된다는 사실과 연동이 완성됐다는 것은 다르다.

임포트 시점에 rclpy를 부르지 않는다. ROS 2가 없는 곳에서도 어댑터 선택과
계약 시험은 돌아야 한다.
"""
from __future__ import annotations

import math
import threading
import time
from typing import Any

from hangeul_runtime.abstraction.robot_arm_adapter import (
    RobotArmAdapter,
    batch_velocity,
)

# 기술서의 unit.per_degree와 같아야 한다. 밀리도(0.001°)로 정수 파이프라인을 지킨다.
MILLIDEGREE_PER_DEGREE = 1000
GOAL_TIMEOUT_S = 10.0
SETTLE_TOLERANCE_DEG = 0.5


def _to_radian(millideg: int) -> float:
    return math.radians(float(millideg) / MILLIDEGREE_PER_DEGREE)


def _to_millidegree(radian: float) -> int:
    return int(round(math.degrees(radian) * MILLIDEGREE_PER_DEGREE))


class Ros2ArmAdapter(RobotArmAdapter):
    """ros2_control의 JointTrajectoryController 하나를 팔로 본다.

    `device`는 포트도 IP도 아니라 **컨트롤러 이름**이다
    (예: `/joint_trajectory_controller`).
    """

    robot_model = "ros2_control_jtc"

    def __init__(
        self,
        device: str | None = None,
        *,
        joint_count: int = 0,
        excluded_joint_ids: list[str] | None = None,
        descriptor: dict[str, Any] | None = None,
        node: Any | None = None,
    ) -> None:
        self.device = device or "/joint_trajectory_controller"
        self.descriptor = descriptor or {}
        # **관절 이름은 기술서가 들고 있다.** 코드에 박지 않는다 —
        # 그게 이 어댑터가 깨려는 가정이다.
        joints = self.descriptor.get("joints") or []
        self.joint_names = [str(j["id"]) for j in joints if not j.get("disabled")]
        if joint_count and not self.joint_names:
            raise ValueError("기술서에 관절이 없습니다. ROS 2 어댑터는 이름이 필요합니다")
        self.excluded_joints = set(excluded_joint_ids or [])
        self.gripper_joint_name = ""      # 손은 이번 범위가 아니다
        self._node = node                 # 시험에서는 가짜를 넣는다
        self._own_node = False
        self._last: dict[str, int] = {name: 0 for name in self.joint_names}
        self._move_lock = threading.Lock()
        self._stop_generation = 0
        self._stop_lock = threading.Lock()
        self._options = self.descriptor.get("ros2") or {}
        self._per_degree = float((self.descriptor.get("unit") or {}).get("per_degree", 1000))
        self._center = float((self.descriptor.get("unit") or {}).get("center", 0))
        if not math.isfinite(self._per_degree) or self._per_degree <= 0:
            raise ValueError("unit.per_degree must be finite and positive")
        if not math.isfinite(self._center):
            raise ValueError("unit.center must be finite")
        # Explicit evidence label, independent of transport connectivity.
        self.evidence_kind = self._options.get("evidence_kind", "physical_unverified")

    def _radians(self, value):
        return math.radians((float(value) - self._center) / self._per_degree)

    def _raw(self, value):
        return int(round(math.degrees(value) * self._per_degree + self._center))

    # ── 연결 ────────────────────────────────────────────────────
    def __enter__(self) -> "Ros2ArmAdapter":
        if self._node is None:
            from .ros2_transport import Ros2Transport
            self._node = Ros2Transport(self.device, self.joint_names, self._options)
            self._own_node = True
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self._own_node and self._node is not None:
            try:
                self._node.close()
            except Exception:                              # noqa: BLE001
                pass
        self._node = None
        self._own_node = False

    def _require_open(self) -> None:
        if self._node is None:
            raise RuntimeError("Ros2ArmAdapter는 컨텍스트 매니저로 써야 합니다")

    # ── 읽기 ────────────────────────────────────────────────────
    def read_joint_positions(self) -> dict[str, int]:
        """지금 각도. **로봇 단위(밀리도) 그대로** 돌려준다."""
        self._require_open()
        radians = self._node.joint_positions()             # 가짜/실물 공통 계약
        missing = [n for n in self.joint_names if n not in radians or not math.isfinite(radians[n])]
        if missing:
            raise RuntimeError("Missing or invalid joint positions: " + ", ".join(missing))
        return {name: self._raw(radians[name]) for name in self.joint_names}

    def clamp(self, joint_name: str, target: int) -> int:
        if joint_name not in self.joint_names:
            raise KeyError(f"알 수 없는 관절: {joint_name}")
        band = ((self.descriptor.get("safety") or {}).get("limits") or {}).get(joint_name)
        if not band:
            return int(target)
        return max(int(band[0]), min(int(band[1]), int(target)))

    # ── 이동 ────────────────────────────────────────────────────
    def move_joints(
        self,
        targets: dict[str, int],
        *,
        velocity: int,
        acceleration: int,
        label: str,
        bypass_temperature_check: bool = False,
        temperature_limits_c: dict[str, float] | None = None,
        velocity_per_joint: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        """goal을 보내고 **result까지 기다린다.**

        접수(accepted)와 완료(result)는 다르다. 접수를 완료로 적으면 화면은
        갔다고 하고 팔은 안 간 상태가 된다 — 앞의 로봇들에서 겪은 일이다.
        """
        self._require_open()
        # Never queue movement behind another action: a stop must not release queued work.
        if not self._move_lock.acquire(blocking=False):
            return {"success": False, "settled": False, "error": "ROS trajectory already active"}
        try:
            speed = batch_velocity(velocity, velocity_per_joint, self.joint_names)
            answer = self._move(targets, velocity=speed, label=label)
            # **온도를 못 본다는 사실을 숨기지 않는다.**
            # 이 컨트롤러에는 관절 온도를 읽는 길이 없다. 인자를 조용히 버리면
            # 운영자가 한계를 걸어 두고 걸린 줄 안다 — 걸어도 아무 일이
            # 일어나지 않는데도(2026-09-24 전수조사).
            #
            # bypass는 정지 뒤 그 자리에 세울 때만 온다. 여기서는 어차피
            # 온도를 보지 않으므로 막을 일이 없고, 받았다는 것만 남긴다.
            answer.setdefault("temperature_check_supported", False)
            if temperature_limits_c and not bypass_temperature_check:
                answer.setdefault(
                    "temperature_note",
                    "이 로봇은 관절 온도를 읽지 못해 한계를 확인하지 않았습니다")
            return answer
        finally:
            self._move_lock.release()

    def _move(self, targets, *, velocity, label):
        unknown = sorted(set(targets) - set(self.joint_names))
        if unknown:
            raise ValueError(f"알 수 없는 관절: {', '.join(unknown)}")
        blocked = sorted(set(targets) & self.excluded_joints)
        if blocked:
            raise ValueError(f"꺼둔 관절에는 명령하지 않습니다: {', '.join(blocked)}")

        with self._stop_lock:
            generation = self._stop_generation
        present = self.read_joint_positions()
        # JTC normally requires every joint. Hold unrequested joints at fresh measured values.
        clamped = {name: self.clamp(name, targets.get(name, present[name])) for name in self.joint_names}
        # 배치 하나에 시간이 하나 실린다 — 가장 엄한 한계를 따른다.
        speed = velocity
        # Velocity is an explicit degree/s scale. Linear interpolation with zero endpoint
        # velocities omitted; duration also respects each joint's rad/s ceiling.
        scale = float(self._options.get("velocity_deg_s_per_unit", 1.0))
        if not math.isfinite(scale) or scale <= 0:
            raise ValueError("velocity_deg_s_per_unit must be positive")
        max_rad = self._options.get("max_velocity_rad_s", 1.0)
        duration = float(self._options.get("min_duration_s", 0.2))
        maximum = float(self._options.get("max_duration_s", 120.0))
        if any(not math.isfinite(t) or t <= 0 for t in (duration, maximum)):
            raise ValueError("Trajectory duration limits must be finite and positive")
        for name, value in clamped.items():
            cap = float(max_rad.get(name, 1.0) if isinstance(max_rad, dict) else max_rad)
            if not math.isfinite(cap) or cap <= 0:
                raise ValueError("max_velocity_rad_s must be positive")
            rate = min(math.radians(speed * scale), cap)
            duration = max(duration, abs(self._radians(value) - self._radians(present[name])) / rate)
        seconds = duration
        if seconds > maximum:
            return {"success": False, "settled": False, "error": "Trajectory exceeds duration limit"}
        with self._stop_lock:
            if generation != self._stop_generation:
                return {"success": False, "settled": False, "canceled": True}

        names = list(clamped)
        outcome = self._node.send_trajectory(
            joint_names=names,
            positions=[self._radians(clamped[n]) for n in names],
            time_from_start_s=seconds,
            label=label,
        )
        if not outcome.get("accepted"):
            return {"success": False, "accepted": False,
                    "error": outcome.get("error") or "컨트롤러가 goal을 받지 않았습니다",
                    "settled": False, **outcome}
        self._last.update(clamped)
        # Action result and JointState use separate DDS streams. A success can arrive
        # before the final state sample; allow a bounded read-only settling window.
        deadline = time.monotonic() + 0.5
        while True:
            present = self.read_joint_positions()
            errors_deg = {n: abs(present[n] - clamped[n]) / self._per_degree
                          for n in clamped}
            settled = all(v <= SETTLE_TOLERANCE_DEG for v in errors_deg.values())
            if settled or not outcome.get("result_ok") or time.monotonic() >= deadline:
                break
            time.sleep(0.01)
        return {**outcome, "success": bool(outcome.get("result_ok")) and settled,
                "accepted": True,
                "result_ok": bool(outcome.get("result_ok")),
                "settled": settled,
                "actual_positions": present,
                "errors_deg": errors_deg,
                "label": label, "duration_s": seconds, "evidence_kind": self.evidence_kind}

    def move_gripper(
        self,
        target: int,
        *,
        velocity: int,
        acceleration: int,
        label: str,
        bypass_temperature_check: bool = False,
        temperature_limit_c: float | None = None,
    ) -> dict[str, Any]:
        raise RuntimeError(
            "이번 ROS 2 범위에는 손이 없습니다. 독립 그리퍼는 별도 action server이고 "
            "다음 단계(장치 조합)에서 다룹니다")

    # ── 정지 ────────────────────────────────────────────────────
    def stop(self) -> None:
        """진행 중인 goal을 취소한다. **정지는 판정을 기다리지 않는다.**"""
        self._require_open()
        with self._stop_lock:
            self._stop_generation += 1
        self._node.cancel_all()

    # JTC cancellation already holds position. The runtime must not replace it with a
    # second trajectory while the first result is still being delivered.
    stop_holds_position = True

    def attest_parts(self) -> dict[str, dict[str, Any]]:
        """컨트롤러가 응답하는지만 말한다. 관절 하나하나를 묻는 수단은 없다."""
        try:
            self._require_open()
            alive = bool(self._node.server_ready())
        except Exception as exc:                            # noqa: BLE001
            return {"arm": {"responding": False, "evidence": "action_server",
                            "reason": f"{type(exc).__name__}: {exc}"}}
        return {"arm": {"responding": alive, "evidence": "action_server"},
                "hand": {"responding": None, "evidence": "none",
                         "reason": "이번 ROS 2 범위에는 손이 없습니다"}}

    def preflight(self) -> dict[str, Any]:
        """읽기만 한다. 움직이지 않는다."""
        try:
            self._require_open()
            ready = bool(self._node.server_ready())
            present = self.read_joint_positions()
        except Exception as exc:                            # noqa: BLE001
            return {"robot_model": self.robot_model, "device": self.device,
                    "read_only": True, "passed": False,
                    "error": f"{type(exc).__name__}: {exc}"}
        return {"robot_model": self.robot_model, "device": self.device,
                "read_only": True, "passed": ready,
                "action_server_ready": ready,
                "joint_names": list(self.joint_names),
                "present": present}

    def recover_from_fault(self, *, may_reopen_link: bool = False) -> dict[str, Any]:
        if self._own_node:
            self._node.resume()
            return {"attempted": True, "resumed": True}
        return {"attempted": False,
                "reason": "컨트롤러가 goal을 거절한 이유는 사람이 봐야 합니다"}
