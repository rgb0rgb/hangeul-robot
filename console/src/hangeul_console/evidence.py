"""증거 기록 — 무엇으로, 언제, 누가 확인했는가.

이 저장소의 문서들은 내내 **코드 · 가상 · 실물**을 구분했다. 그런데 제품 안에는
그것을 적는 자리가 없었다. 문서에만 있으면 시간이 지나 섞이고, "검증됨" 배지가
다시 근거 없이 붙는다.

`evidence_ref`는 **참조**로 남긴다. 문자열 하나에 여러 뜻을 섞지 않는다.
실제 내용은 여기 기록에 구조적으로 쌓는다.

    kind        code / simulation / hardware   — 무엇으로 확인했는가
    method      통신 응답인가 운영자 점검인가  — **이 둘을 섞지 않는다**
    subject     대상 (능력 · 부품 · 작업)
    versions    구성 지문 · 작업 정의 해시     — 무엇에 대한 확인인가
    scope       확인한 범위와 확인하지 않은 것
    at/operator 시각과 수행자
    outcome     결과

특히 **method**가 중요하다. "통신이 응답했다"와 "사람이 보고 붙어 있다고 했다"는
전혀 다른 증거인데, 둘 다 '확인됨'으로 적으면 구별할 수 없게 된다.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

FORMAT = "hangeul_robot.evidence.v1"

# 무엇으로 확인했는가. 아래 순서가 곧 증거의 세기다 — 코드가 실물을 대신하지 않는다.
KINDS = ("code", "simulation", "hardware")

# 어떻게 확인했는가. 통신 응답과 사람의 눈은 다른 증거다.
METHODS = (
    "communication_response",   # 장치가 응답했다
    "operator_inspection",      # 사람이 보고 확인했다
    "automated_test",           # 시험이 통과했다
    "measurement",              # 실제로 재었다
)


class EvidenceError(ValueError):
    def __init__(self, reason_code: str, message: str):
        super().__init__(message)
        self.reason_code = reason_code


class EvidenceLog:
    """증거를 쌓고 참조를 돌려준다. **지우지 않는다** — 감사용이다."""

    def __init__(self, records: dict[str, Any] | None = None):
        self.records: dict[str, dict[str, Any]] = dict(records or {})

    def to_dict(self) -> dict[str, Any]:
        return {"format": FORMAT, "records": self.records}

    def record(self, *, kind: str, method: str, subject: str, operator: str,
               outcome: str, scope: str = "", not_covered: str = "",
               configuration_fingerprint: str = "", meaning_digest: str = "",
               detail: dict[str, Any] | None = None) -> str:
        """증거를 하나 적고 **참조를 돌려준다.**

        `not_covered`를 일부러 받는다. 무엇을 확인했는지만 적고 무엇을 확인하지
        않았는지 안 적으면, 읽는 사람이 범위를 넓게 읽는다.
        """
        if kind not in KINDS:
            raise EvidenceError("bad_kind",
                                f"증거 종류는 {', '.join(KINDS)} 중 하나입니다: {kind}")
        if method not in METHODS:
            raise EvidenceError("bad_method",
                                f"확인 방법은 {', '.join(METHODS)} 중 하나입니다: {method}")
        if not subject or not operator or not outcome:
            raise EvidenceError("incomplete", "대상·수행자·결과는 비울 수 없습니다")

        row = {
            "kind": kind,
            "method": method,
            "subject": subject,
            "scope": scope,
            "not_covered": not_covered,
            "configuration_fingerprint": configuration_fingerprint,
            "meaning_digest": meaning_digest,
            "operator": operator,
            "outcome": outcome,
            "detail": detail or {},
            "at": datetime.now().isoformat(timespec="seconds"),
        }
        blob = json.dumps(row, sort_keys=True, ensure_ascii=False)
        ref = f"ev:{kind}:{hashlib.sha256(blob.encode()).hexdigest()[:12]}"
        self.records[ref] = {**row, "ref": ref}
        return ref

    def get(self, ref: str) -> dict[str, Any] | None:
        return self.records.get(ref)

    def describe(self, ref: str) -> str:
        """사람이 읽는 한 줄. 증거 세기를 숨기지 않는다."""
        row = self.records.get(ref)
        if not row:
            return "증거 기록을 찾을 수 없습니다"
        label = {"code": "코드", "simulation": "가상", "hardware": "실물"}[row["kind"]]
        how = {"communication_response": "통신 응답",
               "operator_inspection": "운영자 점검",
               "automated_test": "자동 시험",
               "measurement": "실측"}[row["method"]]
        tail = f" · 확인하지 않음: {row['not_covered']}" if row.get("not_covered") else ""
        return f"[{label}/{how}] {row['subject']} — {row['outcome']} ({row['at']}, {row['operator']}){tail}"
