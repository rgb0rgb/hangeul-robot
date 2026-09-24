"""안전 판정 — 로봇 런타임의 마지막 관문.

콘솔이 아무리 잘 걸러도, 실물에 나가는 마지막 자리에서 다시 본다.
콘솔이 고장 나거나 다른 프로그램이 요청해도 여기는 지나가야 한다.

막는 것
1. 긴급 정지 래치 — 걸려 있으면 새 동작을 받지 않는다. 푸는 것은 사람이 명시해야 한다
2. 관절 범위 — 부품 기술서의 한계를 넘는 목표는 보내지 않는다
3. 단선 래치 — 통신이 끊겼다가 돌아오면 사람이 확인하기 전까지 막는다
4. 속도 상한 — 요청이 무엇이든 상한을 넘겨 보내지 않는다

**정지는 이 판정을 기다리지 않는다.** 정지 경로는 따로 있다.

**막는 상태는 프로세스보다 오래 살아야 한다.**
전에는 이 상태가 메모리에만 있었다. 그래서 정지를 걸어 둔 채 런타임이 죽었다
살아나면 래치가 False로 태어났다 — 사람도, 기록도, 확인 절차도 거치지 않고
풀리는 길이 하나 열려 있었다(systemd는 Restart=on-failure로 5초 뒤 되살린다).
"푸는 것은 사람이 명시해야 한다"는 이 파일의 선언이 거기서 깨졌다.

그래서 **막는 상태만** 파일에 적는다. 무엇을 적고 무엇을 안 적는지가 중요하다.

    적는다    긴급 정지 래치 · 단선 래치 · 일시정지 · 부재 모드
              — 전부 "실행을 막는" 상태다. 꺼졌다 켜졌다고 풀리면 안 된다.

    안 적는다 부품 장착 확인 같은 "실행을 허용하는" 증거
              — 꺼져 있는 동안 누가 무엇을 뗐는지 알 수 없다. 재시작하면
                다시 확인받아야 한다. **지속 정책이 정반대이므로 같은
                기구로 처리하지 않는다.**
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

# 파일로 이어받는 값 — 전부 "실행을 막는" 상태다. 위 머리말 참고.
PERSISTED_FIELDS = ("estop_latched", "estop_reason",
                    "disconnect_latched", "disconnect_reason",
                    "paused", "away_mode")
STATE_FORMAT = "hangeul_robot.safety_state.v1"

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

    # ── 파일로 이어받기 ────────────────────────────────────────
    # 직접 대입(state.paused = True)도 메서드 호출도 모두 잡아야 하므로
    # __setattr__에서 건다. 호출부마다 저장을 기억하게 만들면 언젠가 빠뜨린다.
    def __setattr__(self, name: str, value: Any) -> None:
        # **바뀔 때만 쓴다.** 여러 경로가 `disconnect_latched = False`를 조건 없이
        # 대입한다. 그때마다 파일을 다시 쓰면 디스크를 쉬지 않고 두드리고,
        # 아무 일도 없었는데 저장 시각만 계속 바뀐다
        # (2026-09-24 전수조사에서 발견).
        changed = (name in PERSISTED_FIELDS
                   and getattr(self, name, object()) != value
                   and getattr(self, "_loading", False) is False)
        object.__setattr__(self, name, value)
        if changed:
            self._write_through()

    def bind_storage(self, path: "str | Path") -> dict[str, Any]:
        """이 상태를 파일에 붙인다. 있으면 이어받고, 이후 변화는 그때그때 쓴다.

        돌려주는 값은 **무엇을 이어받았는지**다. 조용히 이어받으면 사람은
        왜 막혀 있는지 모른다 — 호출부가 이걸로 화면에 적는다.
        """
        object.__setattr__(self, "_path", Path(path))
        return self._read_back()

    def _write_through(self) -> None:
        path = getattr(self, "_path", None)
        if path is None:
            return
        payload = {"format": STATE_FORMAT,
                   "saved_at": datetime.now().isoformat(timespec="seconds"),
                   **{name: getattr(self, name) for name in PERSISTED_FIELDS}}
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            # 쓰다 죽어도 반쪽 파일이 남지 않게 — 반쪽이면 다음 기동에서
            # 래치를 못 읽고, 그게 바로 막으려던 일이다.
            fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".safety_state.")
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except Exception as exc:                # noqa: BLE001
            # 저장 실패가 정지를 막아서는 안 된다. 다만 조용히 넘어가지도 않는다.
            object.__setattr__(self, "persist_error", f"{type(exc).__name__}: {exc}")

    def _read_back(self) -> dict[str, Any]:
        path = getattr(self, "_path", None)
        if path is None or not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:                # noqa: BLE001
            object.__setattr__(self, "persist_error", f"이전 상태를 읽지 못했습니다: {exc}")
            return {}
        if data.get("format") != STATE_FORMAT:
            return {}
        object.__setattr__(self, "_loading", True)
        try:
            for name in PERSISTED_FIELDS:
                if name in data:
                    object.__setattr__(self, name, data[name])
        finally:
            object.__setattr__(self, "_loading", False)
        return {name: data[name] for name in PERSISTED_FIELDS if name in data}

    def blocking_summary(self) -> list[str]:
        """지금 실행을 막고 있는 것들. 이어받은 뒤 사람에게 보여주려고 둔다."""
        out = []
        if self.estop_latched:
            out.append(f"긴급 정지({self.estop_reason})" if self.estop_reason else "긴급 정지")
        if self.disconnect_latched:
            out.append(f"단선({self.disconnect_reason})" if self.disconnect_reason else "단선")
        if self.paused:
            out.append("일시정지")
        if self.away_mode:
            out.append("부재 모드")
        return out

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
            # 막는 상태를 파일에 못 적고 있다면 그 사실을 숨기지 않는다.
            "persist_error": getattr(self, "persist_error", ""),
        }


def check_move(state: SafetyState, joint_id: int | str, target: int,
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
