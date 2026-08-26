from __future__ import annotations

from typing import Any

from hangeul_runtime.abstraction.robot_arm_adapter import RobotArmAdapter


class SimulatedArmAdapter(RobotArmAdapter):
    """Public demo adapter. It never opens physical hardware."""

    robot_model = "simulated_arm"

    def __init__(
        self,
        device: str = "",
        *,
        joint_count: int | None = None,
        excluded_joint_ids: list[str] | None = None,
        descriptor: dict[str, Any] | None = None,
    ):
        joints = (descriptor or {}).get("joints") or []
        self.joint_names = [str(j["id"]) for j in joints] or [
            str(i + 1) for i in range(joint_count or 4)
        ]
        self.excluded_joints = set(str(j) for j in (excluded_joint_ids or []))
        command = ((descriptor or {}).get("hand") or {}).get("command") or {}
        self.gripper_joint_name = str(command.get("joint")) if command.get("joint") else None
        unit = (descriptor or {}).get("unit") or {}
        center = int(unit.get("center") or 0)
        self._positions = {name: center for name in self.joint_names}
        if self.gripper_joint_name:
            self._positions[self.gripper_joint_name] = center

    @classmethod
    def from_resolved(cls, profile: dict[str, Any], instance: dict[str, Any]) -> "SimulatedArmAdapter":
        return cls("", descriptor=profile)

    def __enter__(self) -> "SimulatedArmAdapter":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None

    def read_joint_positions(self) -> dict[str, int]:
        return dict(self._positions)

    def clamp(self, joint_name: str, target: int) -> int:
        return int(target)

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
        for joint, target in targets.items():
            if str(joint) not in self.excluded_joints:
                self._positions[str(joint)] = int(target)
        return {"success": True, "simulated": True, "label": label, "targets": dict(targets)}

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
        if self.gripper_joint_name:
            self._positions[self.gripper_joint_name] = int(target)
        return {"success": True, "simulated": True, "label": label, "target": int(target)}

    def preflight(self) -> dict[str, Any]:
        return {"ok": True, "simulated": True, "message": "public demo adapter"}

