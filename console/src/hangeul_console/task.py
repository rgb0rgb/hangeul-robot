"""작업 — C6·C7. 뜻과 발음을 나눈다.

이전 구조에서 작업은 관절 숫자 묶음이었다. 그래서 부품이 바뀌면 뜻까지 잃었다.

    뜻(meaning)      "물건을 집는다" — 부품과 무관하다. 지워지지 않는다.
    발음(realization) 이 구성에서의 실제 관절값 — 구성 지문과 함께 보관한다.

부품을 바꾸면 발음은 무효가 되지만 **뜻은 남는다.** 다시 가르치면 새 발음이 붙는다.
"""
from __future__ import annotations

import hashlib
import json
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


# 실행을 막는 판정들. "발음이 있다"와 "그 발음을 지금 써도 된다"는 다르다.
BLOCKING_VERIFICATIONS = ("REVOKED", "COMPAT_CHECK_REQUIRED", "NEEDS_RETEACH")

# 뜻 해시에서 빼는 것 — 표시용이라 바뀌어도 동작의 의미는 그대로다.
DISPLAY_ONLY_STEP_KEYS = ("icon", "note")

# **자세 단계에서는 label을 빼지 않는다.**
# 발음은 단계 번호(index)로만 맞춰진다. 그래서 "A로 간다"와 "B로 간다"를
# 가르는 것이 label뿐이다 — 그걸 표시용으로 치우면 A에 가르친 관절값이
# B에 조용히 실린다(2026-09-20 재현). 다른 단계(손 열기·닫기·대기)는
# 하는 일이 이름과 무관하므로 label이 뜻에 들어가지 않는다.
#
# 이것은 **임시 방편이다.** 바른 해법은 자세 단계에 이름과 별개인 고정
# 식별자를 두고 발음을 거기에 매는 것이다. 그러면 이름을 고쳐도 뜻은
# 그대로고, 가리키는 자세가 바뀌면 그때만 다시 묻는다.
NAME_IS_MEANING_KINDS = ("pose",)


def meaning_digest(steps: list[dict[str, Any]]) -> str:
    """이 작업이 **무엇을 하는지**의 해시. 이름만 바꾼 것과 동작이 바뀐 것을 가른다.

    전에는 이게 없었다. 그래서 작업 ID는 그대로 두고 자세 단계를 A에서 B로
    바꿔도, 옛 단계 0의 관절값이 새 단계 B에 그대로 붙었다(2026-09-20 재현:
    taught=True). 새 작업에 옛 몸값이 실렸다.
    """
    rows = []
    for index, step in enumerate(steps or []):
        drop = set(DISPLAY_ONLY_STEP_KEYS)
        if step.get("kind") not in NAME_IS_MEANING_KINDS:
            drop.add("label")
        row = {k: v for k, v in step.items() if k not in drop}
        row["_index"] = index
        rows.append(row)
    blob = json.dumps(rows, sort_keys=True, ensure_ascii=False)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


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
                  "steps": steps, "meaning_digest": meaning_digest(steps),
                  "updated_at": datetime.now().isoformat(timespec="seconds")}
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
            # 가르칠 당시의 **작업 정의**. 정의가 개정되면 이 값이 달라진다.
            "meaning_digest": meaning_digest(self.meanings[meaning_id].get("steps") or []),
            "step_targets": step_targets,
            "verification": "UNVERIFIED",
            "operator": operator,
            "taught_at": datetime.now().isoformat(timespec="seconds"),
        }
        self.realizations[key] = record
        return record

    def realization(self, meaning_id: str, config) -> dict[str, Any] | None:
        """이 몸에서의 발음. **쓸 수 있는지까지 판정해서 돌려준다.**

        판정은 근거별로 갈린다. "자세를 잃지 않는다"와 "바로 실행해도 된다"는
        다르다 — 근거가 없으면 원본은 보존하되 실행은 막는다.

            같은 지문 · 같은 정의          그대로 쓴다
            같은 지문 · 정의가 개정됨      NEEDS_RETEACH      다시 가르친다
            옛 지문(v1)이 지금 것과 맞음   COMPAT_CHECK_REQUIRED
                                           단위·교정이 지문에 없던 때 저장됐다.
                                           보존하되 확인 전에는 쓰지 않는다
            그 밖                          REVOKED            부품이 바뀌었다
        """
        record = self.realizations.get(f"{config.instance_id}::{meaning_id}")
        if not record:
            return None
        stored = record.get("configuration_fingerprint")
        current = config.fingerprint()

        if stored == current:
            saved_digest = record.get("meaning_digest")
            now_digest = meaning_digest((self.meanings.get(meaning_id) or {}).get("steps") or [])
            if not saved_digest:
                # 뜻 해시가 없던 때 저장된 기록이다. 정의가 그때와 같은지
                # 판단할 근거가 없으므로 추정해서 승인하지 않는다.
                return {**record, "verification": "COMPAT_CHECK_REQUIRED",
                        "reason": "작업 정의가 그때와 같은지 확인할 근거가 없습니다. "
                                  "확인하거나 다시 가르쳐야 합니다"}
            if saved_digest != now_digest:
                return {**record, "verification": "NEEDS_RETEACH",
                        "reason": "작업 단계가 바뀌었습니다. 이전에 가르친 값은 "
                                  "새 단계의 값이 아닙니다"}
            return record

        if stored and stored == config.legacy_fingerprint():
            # 부품 구성은 그대로인데, 단위·교정이 지문에 없던 때 저장된 값이다.
            # 단위가 실제로 바뀌었는지는 이 값만으로 알 수 없다 — 그래서 묻는다.
            return {**record, "verification": "COMPAT_CHECK_REQUIRED",
                    "reason": "단위·교정이 지문에 들어가기 전에 저장된 값입니다. "
                              "그대로 써도 되는지 확인이 필요합니다"}

        # 뜻은 남고 발음만 무효가 된다
        return {**record, "verification": "REVOKED",
                "reason": "부품이 바뀌어 이전에 가르친 값은 쓸 수 없습니다"}

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
                if record and record.get("verification") not in BLOCKING_VERIFICATIONS:
                    found = [t for t in record["step_targets"] if t.get("index") == index]
                    targets = found[0].get("targets") if found else None
                item["targets"] = targets
            steps.append(item)
        return {
            "meaning_id": meaning_id,
            "label": meaning["label"],
            "icon": meaning.get("icon", "🤖"),
            "steps": steps,
            "taught": bool(record and record.get("verification") not in BLOCKING_VERIFICATIONS),
            "verification": (record or {}).get("verification", "UNTAUGHT"),
            "reason": (record or {}).get("reason", ""),
            "required": required_capabilities(meaning["steps"]),
        }
