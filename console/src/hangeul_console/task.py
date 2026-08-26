"""작업 — C6·C7. 뜻과 발음을 나눈다.

이전 구조에서 작업은 관절 숫자 묶음이었다. 그래서 부품이 바뀌면 뜻까지 잃었다.

    뜻(meaning)      "물건을 집는다" — 부품과 무관하다. 지워지지 않는다.
    발음(realization) 이 구성에서의 실제 관절값 — 구성 지문과 함께 보관한다.

부품을 바꾸면 발음은 무효가 되지만 **뜻은 남는다.** 다시 가르치면 새 발음이 붙는다.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

# 각 단계가 요구하는 능력
STEP_REQUIREMENTS = {
    "pose": "motion.move_pose",
    "hand_open": "hand.open",
    "hand_close": "hand.close",
    "wait": "",
}

# 관측 부품(눈·귀)은 **작업 단계가 될 수 없다.** 보는 것과 듣는 것은 움직임이 아니다.
# 관측 결과를 쓰고 싶으면 사람이 보고 판단해 자세를 고른다.
OBSERVE_ONLY = ("observe.", "listen.")


class TaskError(ValueError):
    def __init__(self, reason_code: str, message: str):
        super().__init__(message)
        self.reason_code = reason_code


def is_observe_only(capability_id: str) -> bool:
    return capability_id.startswith(OBSERVE_ONLY)


def required_capabilities(steps: list[dict[str, Any]]) -> list[str]:
    out = []
    for step in steps:
        need = STEP_REQUIREMENTS.get(step.get("kind", ""), "")
        if need and need not in out:
            out.append(need)
    return out


def check_runnable(steps: list[dict[str, Any]], config, capability_states) -> dict[str, Any]:
    """지금 이 몸으로 이 작업을 할 수 있는가. 없는 능력은 실행 요청 자체를 막는다."""
    provided = config.provided()
    states = {c.capability_id: c for c in capability_states}
    blockers: list[str] = []

    for need in required_capabilities(steps):
        if need not in provided:
            klass = need.split(".")[0]
            blockers.append(f"이 로봇에는 {klass} 부품이 없어 '{need}'를 할 수 없습니다")
            continue
        state = states.get(need)
        if state and state.health != "AVAILABLE":
            blockers.append(f"'{need}'을(를) 지금 쓸 수 없습니다: {state.reason or state.health}")

    # 자세 단계는 그 구성에서 발음이 있어야 한다
    for step in steps:
        if step.get("kind") != "pose":
            continue
        if not step.get("targets"):
            blockers.append(f"'{step.get('label') or step.get('meaning_id')}'은(는) "
                            f"이 로봇에서 아직 가르치지 않았습니다")
    return {"runnable": not blockers, "blockers": blockers}


class TaskStore:
    """작업 = 뜻 + 구성별 발음."""

    def __init__(self, data: dict[str, Any] | None = None):
        data = data or {}
        self.meanings: dict[str, Any] = data.get("meanings") or {}
        self.realizations: dict[str, Any] = data.get("realizations") or {}

    def to_dict(self) -> dict[str, Any]:
        return {"format": "hangeul_robot.tasks.v1",
                "meanings": self.meanings, "realizations": self.realizations}

    # ── 뜻 ──────────────────────────────────────────────────────
    def save_meaning(self, meaning_id: str, *, label: str, steps: list[dict[str, Any]],
                     icon: str = "🤖") -> dict[str, Any]:
        if not meaning_id or not label:
            raise TaskError("bad_input", "작업 ID와 이름이 필요합니다")
        if not steps:
            raise TaskError("empty", "단계가 하나도 없습니다")
        for step in steps:
            if step.get("kind") not in STEP_REQUIREMENTS:
                raise TaskError("bad_step", f"알 수 없는 단계: {step.get('kind')}")
        record = {"meaning_id": meaning_id, "label": label, "icon": icon,
                  "steps": steps, "updated_at": datetime.now().isoformat(timespec="seconds")}
        self.meanings[meaning_id] = record
        return record

    # ── 발음 ────────────────────────────────────────────────────
    def save_realization(self, meaning_id: str, config, step_targets: list[dict[str, Any]],
                         *, operator: str) -> dict[str, Any]:
        """이 구성에서 그 뜻이 어떤 관절값인지 기록한다. 항상 미검증에서 시작한다."""
        if meaning_id not in self.meanings:
            raise TaskError("unknown_meaning", f"없는 작업: {meaning_id}")
        key = f"{config.instance_id}::{meaning_id}"
        record = {
            "meaning_id": meaning_id,
            "instance_id": config.instance_id,
            "configuration_fingerprint": config.fingerprint(),
            "step_targets": step_targets,
            "verification": "UNVERIFIED",
            "operator": operator,
            "taught_at": datetime.now().isoformat(timespec="seconds"),
        }
        self.realizations[key] = record
        return record

    def realization(self, meaning_id: str, config) -> dict[str, Any] | None:
        record = self.realizations.get(f"{config.instance_id}::{meaning_id}")
        if not record:
            return None
        if record.get("configuration_fingerprint") != config.fingerprint():
            # 뜻은 남고 발음만 무효가 된다
            return {**record, "verification": "REVOKED",
                    "reason": "부품이 바뀌어 이전에 가르친 값은 쓸 수 없습니다"}
        return record

    # ── 해석 ────────────────────────────────────────────────────
    def resolve(self, meaning_id: str, config) -> dict[str, Any]:
        """뜻 → 이 몸에서의 실행 단계. 없으면 이유를 돌려준다."""
        meaning = self.meanings.get(meaning_id)
        if not meaning:
            raise TaskError("unknown_meaning", f"없는 작업: {meaning_id}")
        record = self.realization(meaning_id, config)
        steps = []
        for index, step in enumerate(meaning["steps"]):
            item = dict(step)
            if step.get("kind") == "pose":
                targets = None
                if record and record.get("verification") != "REVOKED":
                    found = [t for t in record["step_targets"] if t.get("index") == index]
                    targets = found[0].get("targets") if found else None
                item["targets"] = targets
            steps.append(item)
        return {
            "meaning_id": meaning_id,
            "label": meaning["label"],
            "icon": meaning.get("icon", "🤖"),
            "steps": steps,
            "taught": bool(record and record.get("verification") != "REVOKED"),
            "verification": (record or {}).get("verification", "UNTAUGHT"),
            "reason": (record or {}).get("reason", ""),
            "required": required_capabilities(meaning["steps"]),
        }
