"""안전 판정 — 로봇 런타임의 마지막 관문.

콘솔이 아무리 잘 걸러도, 실물에 나가는 마지막 자리에서 다시 본다.
콘솔이 고장 나거나 다른 프로그램이 요청해도 여기는 지나가야 한다.

막는 것
1. 긴급 정지 래치 — 걸려 있으면 새 동작을 받지 않는다. 푸는 것은 사람이 명시해야 한다
2. 관절 범위 — 부품 기술서의 한계를 넘는 목표는 보내지 않는다
3. 단선 래치 — 통신이 끊겼다가 돌아오면 사람이 확인하기 전까지 막는다
4. 속도 상한 — 요청이 무엇이든 상한을 넘겨 보내지 않는다

**정지는 이 판정을 기다리지 않는다.** 정지 경로는 따로 있다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

MAX_VELOCITY = 200
DEFAULT_VELOCITY = 40


class SafetyBlocked(Exception):
    def __init__(self, reason_code: str, message: str):
        super().__init__(message)
        self.reason_code = reason_code


@dataclass
class SafetyState:
    estop_latched: bool = False
    estop_reason: str = ""
    disconnect_latched: bool = False
    disconnect_reason: str = ""
    paused: bool = False
    away_mode: bool = False
    history: list[dict[str, Any]] = field(default_factory=list)

    def note(self, message: str, kind: str = "info") -> None:
        self.history.insert(0, {"at": datetime.now().strftime("%H:%M:%S"),
                                "message": message, "kind": kind})
        del self.history[60:]

    def latch_estop(self, reason: str) -> None:
        self.estop_latched = True
        self.estop_reason = reason
        self.note(f"긴급 정지: {reason}", "stop")

    def clear_estop(self, operator: str) -> None:
        """푸는 것은 거는 것보다 어렵다 — 누가 풀었는지 남긴다."""
        self.estop_latched = False
        self.estop_reason = ""
        self.note(f"긴급 정지 해제 (확인: {operator})", "info")

    def latch_disconnect(self, reason: str) -> None:
        self.disconnect_latched = True
        self.disconnect_reason = reason
        self.note(f"연결 끊김: {reason}", "stop")

    def to_dict(self) -> dict[str, Any]:
        return {
            "estop_active": self.estop_latched,
            "estop_reason": self.estop_reason,
            "disconnect_latched": self.disconnect_latched,
            "disconnect_reason": self.disconnect_reason,
            "paused": self.paused,
            "away_mode": self.away_mode,
        }


def check_move(state: SafetyState, joint_id: int, target: int,
               limits: dict[str, list[int]] | None, velocity: int | None) -> int:
    """이동 요청을 검사하고 안전한 속도를 돌려준다. 막히면 예외를 올린다."""
    if state.estop_latched:
        raise SafetyBlocked("estop_latched",
                            f"긴급 정지가 걸려 있습니다 ({state.estop_reason}). 해제 후 다시 시도하세요")
    if state.disconnect_latched:
        # 무엇을 눌러야 다시 움직이는지까지 적는다. 이유만 적으면 사람은 멈춰 선다.
        raise SafetyBlocked("disconnect_latched",
                            f"로봇이 오류로 멈췄습니다 ({state.disconnect_reason}). "
                            f"화면의 '정지 해제'를 누르면 서보 오류를 풀고 다시 움직입니다")
    if state.paused:
        raise SafetyBlocked("paused", "일시정지 상태입니다")
    if state.away_mode:
        raise SafetyBlocked("away_mode", "부재 모드라서 실행하지 않습니다")

    band = (limits or {}).get(str(joint_id))
    if band and not (band[0] <= target <= band[1]):
        raise SafetyBlocked(
            "out_of_range",
            f"관절 {joint_id} 목표 {target}이 허용 범위 {band[0]}~{band[1]} 밖입니다")

    speed = int(velocity or DEFAULT_VELOCITY)
    return max(1, min(MAX_VELOCITY, speed))
