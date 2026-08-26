"""화면 용어의 단일 소스 — 2단계 "쉬운 화면".

지난 시스템의 문제: 같은 낱말이 세 곳(hangeul·grid·Beom)에 따로 하드코딩돼 있어서
"그리퍼"를 "손"으로 바꾸는 데 3개 트리 7개 파일을 고쳐야 했다.

여기서는 **낱말이 이 파일에만 있다.** 화면·API·문서는 키로만 참조한다.

규칙
1. 코드와 저장 데이터는 내부 ID를 쓴다(`joint_11`). 사람이 읽는 말은 여기서만 만든다.
2. 사용자 모드에서는 관절 번호·틱·포트·프로세스 용어를 쓰지 않는다.
3. 한국어가 먼저다. 영어는 같은 키에 1:1로 붙인다.
"""
from __future__ import annotations

from typing import Any

# 사용자 모드 / 엔지니어 모드
MODE_USER = "user"
MODE_ENGINEER = "engineer"

TERMS: dict[str, dict[str, str]] = {
    # 큰 이름
    "product.name": {"ko": "Hangeul Robot", "en": "Hangeul Robot"},
    "product.tagline": {"ko": "로봇 고르기 → 할 일 고르기 → 실행", "en": "Pick a robot → Pick a task → Run"},

    # 자원
    "resource.robot": {"ko": "로봇", "en": "Robot"},
    "resource.hand": {"ko": "손", "en": "Hand"},
    "resource.camera": {"ko": "눈(카메라)", "en": "Camera"},
    "resource.microphone": {"ko": "귀(마이크)", "en": "Microphone"},

    # 관절 — 2026-08-15 확정 명칭
    "joint.base": {"ko": "고정대", "en": "Base"},
    "joint.n": {"ko": "관절 {n}", "en": "Joint {n}"},
    "joint.hand": {"ko": "손", "en": "Hand"},

    # 동작
    "action.move_to_pose": {"ko": "자세로 가기", "en": "Go to pose"},
    "action.move_relative": {"ko": "미세 이동", "en": "Fine move"},
    "action.hand_open": {"ko": "손 열기", "en": "Open hand"},
    "action.hand_close": {"ko": "손 닫기", "en": "Close hand"},
    "action.run_sequence": {"ko": "순서 실행", "en": "Run sequence"},
    "action.stop": {"ko": "멈춤", "en": "Stop"},
    "action.teach": {"ko": "자세 저장", "en": "Save pose"},
    "action.track": {"ko": "목표물 추적", "en": "Track a target"},

    # 상태 3축 — 4단계 "기능 신호등"
    "state.lifecycle.NOT_INSTALLED": {"ko": "없음", "en": "Not installed"},
    "state.lifecycle.INSTALLED": {"ko": "달림", "en": "Installed"},
    "state.lifecycle.CONFIGURED": {"ko": "설정됨", "en": "Configured"},
    "state.lifecycle.DISABLED": {"ko": "꺼둠", "en": "Disabled"},
    "state.health.AVAILABLE": {"ko": "정상", "en": "Available"},
    "state.health.DEGRADED": {"ko": "일부만", "en": "Degraded"},
    "state.health.UNAVAILABLE": {"ko": "쓸 수 없음", "en": "Unavailable"},

    # 로봇이 지금 무엇을 하고 있는가 — 로봇 목록의 '상태' 칸.
    # 이 값들은 저장 파일에도 한글로 들어가 있다(옛 자료와 맞추기 위함).
    # 화면에 보일 말은 여기서만 만든다 — 화면이 제 사전을 따로 두면 낱말이 둘이 된다.
    "state.run.대기": {"ko": "대기", "en": "Idle"},
    "state.run.실행": {"ko": "실행", "en": "Running"},
    "state.run.완료": {"ko": "완료", "en": "Done"},
    "state.run.실패": {"ko": "실패", "en": "Failed"},
    "state.run.예약": {"ko": "예약", "en": "Scheduled"},
    "state.run.취소": {"ko": "취소", "en": "Cancelled"},
    "state.verification.UNVERIFIED": {"ko": "해보지 않음", "en": "Not tried"},
    "state.verification.VERIFIED": {"ko": "해봤음", "en": "Verified"},
    "state.verification.REVOKED": {"ko": "다시 확인 필요", "en": "Needs recheck"},

    # 화면 문구
    "ui.mode.user": {"ko": "사용자 모드", "en": "User mode"},
    "ui.mode.engineer": {"ko": "엔지니어 모드", "en": "Engineer mode"},
    "ui.q1": {"ko": "어떤 로봇이 준비됐나?", "en": "Which robot is ready?"},
    "ui.q2": {"ko": "무엇을 시킬까?", "en": "What should it do?"},
    "ui.q3": {"ko": "지금 안전한가?", "en": "Is it safe now?"},
    "ui.not_taught": {"ko": "이 로봇에서는 아직 안 가르쳤습니다", "en": "Not taught on this robot yet"},
    "ui.no_robot": {"ko": "연결된 로봇이 없습니다", "en": "No robot connected"},
    "ui.confirm_line": {"ko": "{robot}이(가) {task}을(를) {speed}(으)로 {count}회 실행합니다",
                        "en": "{robot} will run {task} at {speed} × {count}"},

    # 엔지니어 모드 전용 (사용자 모드에서는 절대 노출하지 않는다)
    "eng.joint_id": {"ko": "관절 번호", "en": "Joint ID"},
    "eng.raw_unit": {"ko": "원시 단위", "en": "Raw unit"},
    "eng.port": {"ko": "장치 포트", "en": "Device port"},
    "eng.runtime_url": {"ko": "런타임 주소", "en": "Runtime URL"},
    "eng.restart": {"ko": "서버 재시작", "en": "Restart server"},
}

# 사용자 모드에서 화면에 나오면 안 되는 키 (검사로 강제한다)
ENGINEER_ONLY_PREFIX = "eng."


def text(key: str, lang: str = "ko", **fmt: Any) -> str:
    entry = TERMS.get(key)
    if entry is None:
        raise KeyError(f"용어 키가 없습니다: {key}")
    value = entry.get(lang) or entry["ko"]
    return value.format(**fmt) if fmt else value


def joint_label(index: int, is_hand: bool = False, lang: str = "ko") -> str:
    """관절 표시 이름. 첫 축은 고정대, 그다음부터 관절 1..n, 손은 손."""
    if is_hand:
        return text("joint.hand", lang)
    if index == 0:
        return text("joint.base", lang)
    return text("joint.n", lang, n=index)


def bundle(lang: str = "ko", mode: str = MODE_USER) -> dict[str, str]:
    """화면에 내려보낼 용어 묶음. 사용자 모드에는 엔지니어 용어를 넣지 않는다."""
    out = {}
    for key, entry in TERMS.items():
        if mode == MODE_USER and key.startswith(ENGINEER_ONLY_PREFIX):
            continue
        out[key] = entry.get(lang) or entry["ko"]
    return out
