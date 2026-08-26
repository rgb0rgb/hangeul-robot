"""부품 기술서 — C2. 부품이 자기를 밝힌다.

이전 구조의 문제: 콘솔이 "팔에는 관절 11~14가 있고 손은 15번이며 단위는 틱"이라고
알고 있었다. 그러면 부품을 바꿀 수 없다. 콘솔을 고쳐야 하기 때문이다.

여기서는 그 지식을 전부 부품 기술서로 옮긴다. 콘솔은 다음만 안다.

    - 부품이 어디에 꽂히는가 (mount)
    - 무엇을 주는가 (provides)
    - 무엇을 요구하는가 (requires)
    - 어떤 위험 등급인가 (safety_class)

관절 번호·단위·교정값은 **부품이 들고 다닌다.**
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MODULE_FORMAT = "hangeul_robot.module.v1"

# 부품 종류와 꽂히는 자리의 규칙
MODULE_CLASSES = {
    "core": {"mounts_into": None, "provides_slots": ("arm_a", "arm_b", "sensor", "mobility")},
    "arm": {"mounts_into": "core", "provides_slots": ("tool",)},
    "hand": {"mounts_into": "arm", "provides_slots": ()},
    "eye": {"mounts_into": "core", "provides_slots": ()},
    "ear": {"mounts_into": "core", "provides_slots": ()},
    "mobility": {"mounts_into": "core", "provides_slots": ()},
}

SAFETY_CLASSES = {
    "none": {"hazard": "low", "needs_stop_path": False},
    "motion": {"hazard": "medium", "needs_stop_path": False},   # 팔 정지로 함께 멈춘다
    "pinch": {"hazard": "low", "needs_stop_path": False},
    "vacuum": {"hazard": "medium", "needs_stop_path": True},
    "rotating": {"hazard": "high", "needs_stop_path": True},
    "thermal": {"hazard": "high", "needs_stop_path": True},
    "observe": {"hazard": "low", "needs_stop_path": False},
}


class ModuleError(ValueError):
    def __init__(self, reason_code: str, message: str):
        super().__init__(message)
        self.reason_code = reason_code


@dataclass(frozen=True)
class Module:
    module_id: str
    module_class: str
    display_name: str
    mount: str                      # 어디에 꽂히는가 ("core.arm_a", "arm_omx.tool")
    provides: tuple[str, ...]
    requires: tuple[str, ...]
    safety_class: str
    joints: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    command: dict[str, Any] | None = None
    limits: dict[str, Any] = field(default_factory=dict)
    value_unit: str = ""
    stop_path: str | None = None
    unit: dict[str, Any] = field(default_factory=dict)   # 사람 단위(도)↔로봇 단위 변환
    runtime_model: str = ""          # 로봇 런타임이 아는 모델 이름
    model_aliases: tuple[str, ...] = ()   # 사람이 부르는 다른 이름들 (콘솔은 이걸 코드에 두지 않는다)
    device: dict[str, str] = field(default_factory=dict)   # 운영체제별 장치 이름
    source_path: str = ""

    @property
    def hazard(self) -> str:
        return SAFETY_CLASSES.get(self.safety_class, {}).get("hazard", "unknown")

    @property
    def needs_stop_path(self) -> bool:
        return bool(SAFETY_CLASSES.get(self.safety_class, {}).get("needs_stop_path"))

    @property
    def mount_parent(self) -> str:
        return self.mount.split(".")[0] if "." in self.mount else self.mount

    @property
    def mount_slot(self) -> str:
        return self.mount.split(".")[1] if "." in self.mount else ""

    def joint_ids(self) -> list[int]:
        """지금 쓰는 관절만. 꺼진 축은 세지 않는다 — 축이 줄면 다른 몸이기 때문이다."""
        return [int(j["id"]) for j in self.joints if not j.get("disabled")]

    def all_joint_ids(self) -> list[int]:
        return [int(j["id"]) for j in self.joints]

    def mass_g(self) -> float:
        return float(self.limits.get("mass_g") or 0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "module_id": self.module_id,
            "module_class": self.module_class,
            "display_name": self.display_name,
            "mount": self.mount,
            "provides": list(self.provides),
            "requires": list(self.requires),
            "safety_class": self.safety_class,
            "hazard": self.hazard,
            "joint_count": len(self.joints),
            "limits": dict(self.limits),
        }


def validate(data: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    for key in ("module_id", "module_class", "display_name", "provides"):
        if not data.get(key):
            problems.append(f"필수 항목 없음: {key}")
    klass = data.get("module_class")
    if klass and klass not in MODULE_CLASSES:
        problems.append(f"알 수 없는 부품 종류: {klass}")
    if klass and klass != "core" and not data.get("mount"):
        problems.append("mount(꽂히는 자리)가 없습니다")
    safety = data.get("safety_class", "none")
    if safety not in SAFETY_CLASSES:
        problems.append(f"알 수 없는 안전 등급: {safety}")
    elif SAFETY_CLASSES[safety]["needs_stop_path"] and not data.get("stop_path"):
        problems.append(
            f"안전 등급 {safety}은(는) 전용 정지 경로(stop_path)를 선언해야 합니다")
    for joint in data.get("joints") or []:
        if "id" not in joint or "role" not in joint:
            problems.append("관절 항목에는 id와 role이 있어야 합니다")
    if klass == "hand" and not data.get("command"):
        problems.append("손은 자기 명령 방식(command)을 선언해야 합니다")
    return problems


def load(path: Path) -> Module:
    data = json.loads(path.read_text(encoding="utf-8"))
    problems = validate(data)
    if problems:
        raise ModuleError("invalid_module", f"{path.name}: " + " / ".join(problems))
    return Module(
        module_id=data["module_id"],
        module_class=data["module_class"],
        display_name=data["display_name"],
        mount=data.get("mount", ""),
        provides=tuple(data.get("provides") or ()),
        requires=tuple(data.get("requires") or ()),
        safety_class=data.get("safety_class", "none"),
        joints=tuple(data.get("joints") or ()),
        command=data.get("command"),
        limits=data.get("limits") or {},
        value_unit=data.get("value_unit", ""),
        stop_path=data.get("stop_path"),
        unit=data.get("unit") or {},
        runtime_model=data.get("runtime_model", ""),
        model_aliases=tuple(data.get("model_aliases") or ()),
        device=data.get("device") or {},
        source_path=str(path),
    )


def load_all(directory: Path) -> tuple[dict[str, Module], list[str]]:
    modules: dict[str, Module] = {}
    problems: list[str] = []
    if not Path(directory).is_dir():
        return modules, problems
    for path in sorted(Path(directory).glob("*.json")):
        try:
            module = load(path)
        except (ModuleError, json.JSONDecodeError) as exc:
            problems.append(str(exc))
            continue
        if module.module_id in modules:
            problems.append(f"부품 ID 중복: {module.module_id}")
            continue
        modules[module.module_id] = module
    return modules, problems
