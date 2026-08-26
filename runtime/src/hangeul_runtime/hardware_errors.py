"""하드웨어 연결/안전 위반 예외.

InFlightSafetyViolationError는 HardwareConnectionLostError의 서브클래스이지만
의미가 다르다 — 연결은 살아 있는데 동작 중 안전 검사(과전류/과열/끼임/HW 오류
플래그)에 걸린 경우다. 이 구분이 필요한 이유: 실제 통신 단절에는 재시작 전까지
전체 실행을 막는 래치를 걸어야 하지만, 순간적인 안전 위반 1회로 같은 래치를
걸면 다음 정상 명령까지 막혀버리는 회귀가 생긴다(Dexter 프로젝트 2026-07-12
실측 확인 이력).
"""
from __future__ import annotations


class HardwareConnectionLostError(RuntimeError):
    """USB/시리얼/소켓 연결이 끊어졌을 때 발생."""

    def __init__(self, message: str = "Hardware connection lost"):
        super().__init__(message)


class InFlightSafetyViolationError(HardwareConnectionLostError):
    """동작 중 안전 검사 위반(과전류/과열/끼임/HW 오류 플래그). 연결 단절과는 구분한다."""

    def __init__(self, message: str = "In-flight safety violation"):
        super().__init__(message)
