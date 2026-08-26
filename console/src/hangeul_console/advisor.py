"""도우미 — C13. 지금 몸으로 가능한 것만 제안한다.

할 수 있는 것: 사람 말과 저장된 작업을 맞춰 후보를 고르고, 왜 안 되는지 설명한다.
할 수 없는 것: 부품을 만들거나, 관절값을 지어내거나, 검증을 올리거나, 실행하는 것.

모델을 쓰지 않는다. 지금 구성과 저장된 작업 이름만으로 결정론적으로 고른다.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from . import task as task_mod


def normalize(text: str) -> str:
    raw = unicodedata.normalize("NFKC", str(text or "")).lower()
    return " ".join(re.sub(r"[^\w가-힣]+", " ", raw).split())


def _score(query: str, label: str) -> float:
    q, l = normalize(query), normalize(label)
    if not q or not l:
        return 0.0
    if q == l:
        return 1.0
    if q in l or l in q:
        return 0.8
    qs, ls = set(q.replace(" ", "")), set(l.replace(" ", ""))
    return len(qs & ls) / max(1, len(qs | ls)) * 0.6


# 화면의 도우미 설정이 보여 주는 기본값. 바꾸면 화면에도 그대로 보인다.
MIN_SCORE = 0.2
MAX_CANDIDATES = 5


def suggest(query: str, config, tasks: task_mod.TaskStore, capability_states,
            *, limit: int = MAX_CANDIDATES, min_score: float = MIN_SCORE) -> dict[str, Any]:
    """후보만 돌려준다. 실행하지 않는다."""
    candidates = []
    for meaning_id, meaning in tasks.meanings.items():
        score = _score(query, meaning["label"])
        if score <= min_score:
            continue
        resolved = tasks.resolve(meaning_id, config)
        gate = task_mod.check_runnable(resolved["steps"], config, capability_states)
        candidates.append({
            "meaning_id": meaning_id,
            "label": meaning["label"],
            "score": round(score, 3),
            "runnable": gate["runnable"],
            "blockers": gate["blockers"],
            "advice": _advice(gate, resolved),
            "execution_forbidden": True,      # 제안은 실행이 아니다
        })
    candidates.sort(key=lambda c: (-c["score"], c["label"]))
    return {
        "ok": True,
        "query": query,
        "instance_id": config.instance_id,
        "candidates": candidates[:limit],
        "execution_forbidden": True,
        "no_match_reason": "" if candidates else "저장된 작업에서 찾지 못했습니다",
    }


def _advice(gate: dict[str, Any], resolved: dict[str, Any]) -> str:
    if gate["runnable"]:
        return "지금 이 로봇으로 할 수 있습니다"
    for blocker in gate["blockers"]:
        if "부품이 없어" in blocker:
            return "필요한 부품이 없습니다. 부품을 꽂고 다시 시도하세요"
        if "가르치지 않았" in blocker:
            return "이 로봇에서 한 번 가르치면 쓸 수 있습니다"
    return gate["blockers"][0] if gate["blockers"] else ""
