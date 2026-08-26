"""능력과 검증 — C4·C5. 할 수 있는 일은 꽂힌 부품에서 계산한다.

사람이 "이 로봇은 이걸 할 수 있다"고 적지 않는다. 부품의 `provides`를 모으면
그것이 곧 능력이다. 부품을 빼면 그 능력이 사라진다.

세 축으로 적는다.

    lifecycle     부품이 있는가        INSTALLED / NOT_INSTALLED / DISABLED
    health        지금 정상인가        AVAILABLE / DEGRADED / UNAVAILABLE
    verification  이 몸으로 해봤는가   UNVERIFIED / VERIFIED / REVOKED

**부품을 바꾸면 그 부품의 검증만 내려간다.** 손을 바꿨다고 팔 검증까지 버리지 않는다.
그러려고 부품별 지문을 따로 둔다.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

# 사람에게 보이는 이름 — 낱말은 terms.py에서만 나온다
CAPABILITY_LABELS = {
    "motion.move_pose": "action.move_to_pose",
    "motion.move_joint": "action.move_relative",
    "motion.fine_move": "action.move_relative",
    "motion.read_pose": "action.teach",
    "hand.open": "action.hand_open",
    "hand.close": "action.hand_close",
    "observe.frame": "resource.camera",
    "observe.color": "resource.camera",
    "observe.track": "action.track",
    "listen.voice": "resource.microphone",
    "listen.stop_word": "action.stop",
}

# 그 능력이 어느 부품 종류에 매여 있는가 — 검증을 부품 단위로 내리기 위함
CAPABILITY_OWNER_CLASS = {
    "motion.": "arm",
    "hand.": "hand",
    "observe.": "eye",
    "listen.": "ear",
    "mobility.": "mobility",
}

# 화면에 보여줄 능력 (전원·버스 같은 내부 자원은 숨긴다)
USER_VISIBLE_PREFIX = ("motion.", "hand.", "observe.", "listen.", "mobility.")


class CapabilityError(ValueError):
    def __init__(self, reason_code: str, message: str):
        super().__init__(message)
        self.reason_code = reason_code


def owner_class(capability_id: str) -> str:
    for prefix, klass in CAPABILITY_OWNER_CLASS.items():
        if capability_id.startswith(prefix):
            return klass
    return ""


@dataclass
class CapabilityState:
    capability_id: str
    instance_id: str
    lifecycle: str
    health: str
    verification: str
    provider: str
    owner_class: str
    part_fingerprint: str
    reason: str = ""
    checked_at: str = ""
    evidence_ref: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "instance_id": self.instance_id,
            "label_key": CAPABILITY_LABELS.get(self.capability_id, self.capability_id),
            "lifecycle": self.lifecycle,
            "health": self.health,
            "verification": self.verification,
            "provider": self.provider,
            "owner_class": self.owner_class,
            "part_fingerprint": self.part_fingerprint,
            "reason": self.reason,
            "checked_at": self.checked_at,
            "evidence_ref": self.evidence_ref,
            "usable_now": self.lifecycle == "INSTALLED" and self.health == "AVAILABLE",
        }


# 몸에 있을 수 있는 능력의 전체 목록 — 없으면 "부품 없음"으로 보여주기 위해 필요하다
KNOWN_CAPABILITIES = tuple(CAPABILITY_LABELS)


class CapabilityStore:
    """검증 기록. 부품 지문이 달라지면 그 부품의 능력만 REVOKED로 읽힌다."""

    def __init__(self, records: dict[str, Any] | None = None):
        self.records: dict[str, dict[str, Any]] = dict(records or {})

    @staticmethod
    def _key(capability_id: str, instance_id: str) -> str:
        return f"{instance_id}::{capability_id}"

    def snapshot(self, config, health: dict[str, str] | None = None) -> list[CapabilityState]:
        provided = config.provided()
        health_map = health or {}
        default_health = health_map.get("_default", "UNAVAILABLE")
        out: list[CapabilityState] = []

        for capability_id in KNOWN_CAPABILITIES:
            klass = owner_class(capability_id)
            provider = provided.get(capability_id, "")
            part_fp = config.part_fingerprint(klass) if klass else config.fingerprint()

            if not provider:
                out.append(CapabilityState(
                    capability_id, config.instance_id, "NOT_INSTALLED", "UNAVAILABLE",
                    "UNVERIFIED", "", klass, part_fp,
                    reason=f"이 로봇에는 {klass or '해당'} 부품이 없습니다"))
                continue

            record = self.records.get(self._key(capability_id, config.instance_id))
            verification, evidence, checked = "UNVERIFIED", "", ""
            reason = ""
            if record:
                if record.get("part_fingerprint") != part_fp:
                    verification = "REVOKED"
                    reason = "부품이 바뀌었습니다. 다시 확인해야 합니다"
                    evidence = record.get("evidence_ref", "")
                else:
                    verification = record.get("verification", "UNVERIFIED")
                    evidence = record.get("evidence_ref", "")
                    checked = record.get("checked_at", "")

            item_health = health_map.get(capability_id, default_health)
            if item_health != "AVAILABLE" and not reason:
                reason = health_map.get("_reason", "로봇 런타임에 연결되지 않았습니다")

            out.append(CapabilityState(
                capability_id, config.instance_id, "INSTALLED", item_health,
                verification, provider, klass, part_fp,
                reason=reason, checked_at=checked, evidence_ref=evidence))
        return out

    def visible(self, config, health: dict[str, str] | None = None) -> list[CapabilityState]:
        return [c for c in self.snapshot(config, health)
                if c.capability_id.startswith(USER_VISIBLE_PREFIX)]

    def mark_verified(self, capability_id: str, config, *, evidence_ref: str,
                      operator: str) -> dict[str, Any]:
        """실제로 해본 것만 기록한다. 증거 없이는 올라가지 않는다."""
        if not evidence_ref:
            raise CapabilityError("no_evidence", "검증에는 증거 참조가 필요합니다")
        if capability_id not in config.provided():
            raise CapabilityError("not_provided",
                                  f"이 구성에 없는 능력은 검증할 수 없습니다: {capability_id}")
        klass = owner_class(capability_id)
        record = {
            "capability_id": capability_id,
            "instance_id": config.instance_id,
            "verification": "VERIFIED",
            "part_fingerprint": config.part_fingerprint(klass) if klass else config.fingerprint(),
            "configuration_fingerprint": config.fingerprint(),
            "evidence_ref": evidence_ref,
            "operator": operator,
            "checked_at": datetime.now().isoformat(timespec="seconds"),
        }
        self.records[self._key(capability_id, config.instance_id)] = record
        return record

    def export(self) -> dict[str, Any]:
        return dict(self.records)
