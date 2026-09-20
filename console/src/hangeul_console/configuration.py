"""구성 그래프와 구성 지문 — C3·C4·C5.

부품을 꽂아 만든 "지금 이 로봇이 누구인가"를 다룬다.

    구성 그래프  무엇이 어디에 붙어 있는가
    결합 검사    꽂히기 **전에** 막는다 (자리·클래스·하중·전력·중복)
    구성 지문    부품이 바뀌면 값이 바뀐다
    능력         꽂힌 부품의 provides를 모은 것 — 사람이 적지 않는다

한 줄로: **부품을 바꾸면 다른 글자가 된다.**
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from . import module as module_mod
from .module import MODULE_CLASSES, Module


class ConfigurationError(ValueError):
    def __init__(self, reason_code: str, message: str):
        super().__init__(message)
        self.reason_code = reason_code


@dataclass
class MountedModule:
    module: Module
    slot: str                       # 부모의 어느 자리에 꽂혔나
    children: list["MountedModule"] = field(default_factory=list)

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()

    def subtree_mass_g(self) -> float:
        return sum(node.module.mass_g() for node in self.walk())


def check_mount(parent: Module, child: Module, slot: str) -> list[str]:
    """꽂히기 전에 보는 것. 하나라도 걸리면 꽂지 않는다."""
    problems = []
    parent_spec = MODULE_CLASSES.get(parent.module_class, {})
    child_spec = MODULE_CLASSES.get(child.module_class, {})

    if slot not in (parent_spec.get("provides_slots") or ()):
        problems.append(
            f"{parent.display_name}에는 '{slot}' 자리가 없습니다 "
            f"(있는 자리: {', '.join(parent_spec.get('provides_slots') or ()) or '없음'})")
    expected_parent = child_spec.get("mounts_into")
    if expected_parent and expected_parent != parent.module_class:
        problems.append(
            f"{child.display_name}({child.module_class})은(는) "
            f"{expected_parent}에만 꽂힙니다. {parent.module_class}에는 꽂을 수 없습니다")
    payload = parent.limits.get("payload_g")
    if payload is not None and child.mass_g() > float(payload):
        problems.append(
            f"{child.display_name}({child.mass_g():.0f}g)이 "
            f"{parent.display_name}의 허용 하중 {float(payload):.0f}g을 넘습니다")
    return problems


@dataclass
class Configuration:
    """한 대의 로봇 = Core 하나와 거기 붙은 부품들."""

    instance_id: str
    display_name: str
    root: MountedModule
    problems: list[str] = field(default_factory=list)
    runtime_url_value: str = ""
    shares_runtime_with: str = ""   # 같은 런타임을 보는 다른 로봇 (임대가 순서를 정한다)

    # ── 구성 지문 ────────────────────────────────────────────────
    #
    # 지문은 "가르친 값을 지금 몸에 그대로 써도 되는가"를 가른다. 그러려면
    # **실행값의 의미를 바꾸는 것이 전부 들어가야 한다.**
    #
    # v1은 부품 ID·자리·관절 ID·command만 해시했다. 그래서 `unit.per_degree`를
    # 바꿔도 지문이 같았다(2026-09-20 재현: same fingerprint: True). 단위가
    # 달라지면 같은 숫자가 다른 각도를 뜻하는데도 옛 값이 그대로 실행됐다.
    #
    # v2는 `unit`과 교정을 넣는다. 그래서 **기존 지문은 전부 바뀐다.** ID 표기를
    # 어떻게 정규화하든 마찬가지다. 그것을 숨기지 않고, v1 값을 따로 계산해
    # "같은 부품인데 단위 기준만 달라진 것"을 알아볼 수 있게 둔다 — 그 판단은
    # task 쪽 이행 정책이 한다(task.realization 참고).
    FORMAT = "v2"

    def _part_rows(self, *, legacy: bool) -> list[dict[str, Any]]:
        rows = []
        for node in sorted(self.root.walk(), key=lambda n: n.module.module_id):
            row = {
                "id": node.module.module_id,
                "slot": node.slot,
                "joints": node.module.joint_ids(),
                "command": node.module.command,
            }
            if not legacy:
                # 실행값의 뜻을 바꾸는 것들. 표시 이름처럼 뜻과 무관한 것은 넣지 않는다.
                row["unit"] = node.module.unit or {}
                row["limits"] = node.module.limits or {}
            rows.append(row)
        return rows

    def fingerprint(self) -> str:
        """부품·자리·관절·command·**단위·교정**이 바뀌면 값이 바뀐다."""
        blob = json.dumps(self._part_rows(legacy=False), sort_keys=True, ensure_ascii=False)
        return f"{self.FORMAT}:sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]

    def legacy_fingerprint(self) -> str:
        """v1이 계산하던 값. **이행 판단에만 쓴다.**

        이 값이 같다는 것은 "부품 구성은 그대로인데 단위·교정 기준이 새로
        지문에 들어왔다"는 뜻이다. 그것만으로 옛 실행값을 승인하지는 않는다 —
        단위가 실제로 바뀌었는지는 따로 봐야 한다.
        """
        blob = json.dumps(self._part_rows(legacy=True), sort_keys=True, ensure_ascii=False)
        return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]

    def part_fingerprint(self, module_class: str) -> str:
        """부품 한 종류만의 지문 — 손을 바꿨을 때 손 검증만 내리기 위함."""
        parts = [{"id": n.module.module_id, "command": n.module.command,
                  "joints": n.module.joint_ids(),
                  "unit": n.module.unit or {}, "limits": n.module.limits or {}}
                 for n in self.root.walk() if n.module.module_class == module_class]
        blob = json.dumps(sorted(parts, key=lambda p: p["id"]), sort_keys=True, ensure_ascii=False)
        return f"{self.FORMAT}:sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:12]

    # ── 부품 조회 ────────────────────────────────────────────────
    def modules(self) -> list[Module]:
        return [n.module for n in self.root.walk()]

    def of_class(self, module_class: str) -> list[Module]:
        return [m for m in self.modules() if m.module_class == module_class]

    def arm(self) -> Module | None:
        arms = self.of_class("arm")
        return arms[0] if arms else None

    def hand(self) -> Module | None:
        hands = self.of_class("hand")
        return hands[0] if hands else None

    # ── 능력: 꽂힌 부품에서 계산한다 ─────────────────────────────
    def provided(self) -> dict[str, str]:
        """능력 → 그것을 주는 부품 ID. 사람이 적는 목록이 아니다."""
        out: dict[str, str] = {}
        for module in self.modules():
            for name in module.provides:
                out.setdefault(name, module.module_id)
        return out

    def missing_requirements(self) -> list[str]:
        """요구했는데 아무도 주지 않는 것."""
        given = set(self.provided())
        needed: list[str] = []
        for module in self.modules():
            for want in module.requires:
                if want.startswith("mount."):
                    continue                    # 결합 검사에서 이미 봤다
                if want not in given:
                    needed.append(f"{module.display_name}: {want} 필요")
        return needed

    # ── 화면용 관절 목록 ─────────────────────────────────────────
    def active_joints(self) -> list[dict[str, Any]]:
        """지금 쓰는 관절. 부품 기술서의 disabled가 그대로 반영된다."""
        arm = self.arm()
        if not arm:
            return []
        return [j for j in arm.joints if not j.get("disabled")]

    def value_unit(self) -> str:
        arm = self.arm()
        return arm.value_unit if arm else ""

    @property
    def runtime_url(self) -> str:
        return self.runtime_url_value

    def unit(self) -> dict:
        """이 몸이 쓰는 값의 단위. 화면이 도(°)로 보여줄지 틱으로 보여줄지 여기서 갈린다."""
        arm = self.arm()
        return dict(arm.unit) if arm else {}

    def runtime_model(self) -> str:
        """로봇 런타임에 '어느 로봇인지' 알려줄 이름. 부품 기술서가 갖고 있다."""
        arm = self.arm()
        return (arm.runtime_model if arm else "") or ""

    def device_name(self, platform: str = "linux") -> str:
        arm = self.arm()
        return (arm.device.get(platform, "") if arm else "") or ""

    def joint_view(self, lang: str = "ko") -> list[dict[str, Any]]:
        """화면용 관절 목록. 표시 이름은 용어 소스에서만 나온다.

        **고장 나서 꺼둔 관절도 목록에 남긴다.** 빼버리면 뒤 관절들의 번호가
        하나씩 당겨져, 사람이 보는 번호와 실제 팔의 마디가 어긋난다.
        꺼둔 관절은 `disabled`로 표시해 화면이 흐리게 그리고 움직이지 못하게 한다.
        """
        from . import terms
        arm = self.arm()
        view = []
        for index, joint in enumerate(arm.joints if arm else []):
            view.append({
                # 식별자는 숫자일 수도 이름일 수도 있다(ROS 2는 이름을 쓴다)
                "joint_id": module_mod.normalize_joint_id(joint["id"]),
                "label": terms.joint_label(index, lang=lang),
                "role": joint.get("role", "joint"),
                "disabled": bool(joint.get("disabled")),
                "reason": joint.get("reason", ""),
            })
        hand = self.hand()
        if hand and hand.command:
            view.append({
                "joint_id": int(hand.command["joint"]),
                "label": terms.joint_label(0, is_hand=True, lang=lang),
                "role": "hand",
                "disabled": False,
                "reason": "",
            })
        return view


def build(instance_id: str, display_name: str, modules: dict[str, Module],
          wanted: list[str]) -> Configuration:
    """부품 목록으로 구성을 조립한다. 잘못된 결합은 트리에 넣지 않는다."""
    chosen = {}
    problems: list[str] = []
    for module_id in wanted:
        module = modules.get(module_id)
        if module is None:
            problems.append(f"없는 부품: {module_id}")
            continue
        chosen[module_id] = module

    cores = [m for m in chosen.values() if m.module_class == "core"]
    if not cores:
        raise ConfigurationError("no_core", "몸통(core)이 없습니다. 구성을 만들 수 없습니다")
    if len(cores) > 1:
        raise ConfigurationError("multi_core", "몸통은 하나여야 합니다")

    root = MountedModule(module=cores[0], slot="")
    nodes = {cores[0].module_id: root}
    occupied: set[tuple[str, str]] = set()

    # 부모가 먼저 붙어야 자식이 붙는다 — 몇 번 돌면서 붙일 수 있는 것부터 붙인다
    pending = [m for m in chosen.values() if m.module_class != "core"]
    for _ in range(len(pending) + 1):
        if not pending:
            break
        still: list[Module] = []
        for module in pending:
            parent_node = nodes.get(module.mount_parent)
            if parent_node is None:
                still.append(module)
                continue
            slot = module.mount_slot
            key = (parent_node.module.module_id, slot)
            if key in occupied:
                problems.append(
                    f"{parent_node.module.display_name}의 '{slot}' 자리에 이미 다른 부품이 있습니다")
                continue
            issues = check_mount(parent_node.module, module, slot)
            if issues:
                problems.extend(issues)
                continue
            node = MountedModule(module=module, slot=slot)
            parent_node.children.append(node)
            nodes[module.module_id] = node
            occupied.add(key)
        if len(still) == len(pending):
            for module in still:
                problems.append(f"{module.display_name}: 꽂을 자리({module.mount})를 찾지 못했습니다")
            break
        pending = still

    config = Configuration(instance_id=instance_id, display_name=display_name,
                           root=root, problems=problems)
    config.problems.extend(config.missing_requirements())
    return config
