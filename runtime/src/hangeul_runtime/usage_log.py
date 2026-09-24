"""누적 사용 기록 — 이 로봇이 얼마나 일했는가.

지금까지 이 저장소는 **한 줄도 쌓지 않았다.** 껐다 켜면 다 사라졌다. 그래서
"이 관절을 얼마나 썼나", "어느 관절이 제일 고생했나"를 물어볼 데가 없었다.

자동차 계기판과 같은 자리다. 주행거리계가 없으면 정비 주기를 말할 수 없다.
서보에는 주행거리계가 없으므로 **우리가 센다.**

    쌓는 것   움직인 각도의 합 · 움직인 횟수 · 움직인 시간 · 최고 온도
    쓰는 곳   상태점검 결과 · (나중에) 예상 교체 시기

**각도로 쌓는다.** 로봇 단위(틱·밀리도)는 부품을 바꾸면 뜻이 달라진다.
도(°)는 부품이 바뀌어도 같은 뜻이라 누적이 이어진다.

이 기록은 **그 컴퓨터의 그 로봇** 것이다. 출하물에 넣지 않는다.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

FORMAT = "hangeul_robot.usage.v1"


class UsageLog:
    """관절별 누적. 지우지 않는다 — 지우면 주행거리계를 0으로 되돌리는 일이다."""

    def __init__(self, path: "str | Path | None" = None):
        self.path = Path(path) if path else None
        self.data: dict[str, Any] = {"format": FORMAT, "joints": {},
                                     "started_at": "", "updated_at": "",
                                     "moving_seconds": 0.0, "move_count": 0}
        self._load()

    # ── 저장 ────────────────────────────────────────────────────
    def _load(self) -> None:
        if not self.path or not self.path.exists():
            return
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:                          # noqa: BLE001
            return                                  # 못 읽으면 새로 센다. 옛 값을 지어내지 않는다
        if loaded.get("format") == FORMAT:
            self.data = loaded

    def save(self) -> None:
        if not self.path:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), prefix=".usage.")
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(self.data, handle, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        except Exception:                          # noqa: BLE001
            pass                                    # 기록 실패가 로봇을 멈추게 하지 않는다

    # ── 쌓기 ────────────────────────────────────────────────────
    def record_move(self, moved_degrees: dict[str, float], *, seconds: float = 0.0,
                    temperatures: dict[str, float] | None = None,
                    label: str = "") -> None:
        """한 번의 움직임을 더한다. `moved_degrees`는 관절별 **이동한 각도의 절댓값**."""
        now = datetime.now().isoformat(timespec="seconds")
        if not self.data.get("started_at"):
            self.data["started_at"] = now
        self.data["updated_at"] = now
        self.data["moving_seconds"] = round(
            float(self.data.get("moving_seconds") or 0.0) + max(0.0, float(seconds)), 1)
        self.data["move_count"] = int(self.data.get("move_count") or 0) + 1

        joints = self.data.setdefault("joints", {})
        temps = temperatures or {}
        for name, degrees in moved_degrees.items():
            amount = abs(float(degrees))
            row = joints.setdefault(str(name), {
                "degrees": 0.0, "moves": 0, "max_temp_c": None, "last_at": "",
            })
            row["degrees"] = round(float(row["degrees"]) + amount, 2)
            row["moves"] = int(row["moves"]) + 1
            row["last_at"] = now
            temp = temps.get(str(name))
            if temp is not None:
                prev = row.get("max_temp_c")
                row["max_temp_c"] = float(temp) if prev is None else max(float(prev), float(temp))
        if label:
            recent = self.data.setdefault("recent_labels", [])
            recent.insert(0, {"at": now, "label": label})
            del recent[20:]
        self.save()

    def note_self_check(self, verdict: str) -> None:
        self.data["last_self_check_at"] = datetime.now().isoformat(timespec="seconds")
        self.data["last_self_check_verdict"] = verdict
        self.save()

    # ── 읽기 ────────────────────────────────────────────────────
    def summary(self) -> dict[str, Any]:
        """사람이 읽을 모양. **없는 것은 없다고 말한다** — 0으로 꾸미지 않는다."""
        joints = self.data.get("joints") or {}
        busiest = ""
        if joints:
            busiest = max(joints, key=lambda name: float(joints[name].get("degrees") or 0.0))
        return {
            "started_at": self.data.get("started_at") or "",
            "updated_at": self.data.get("updated_at") or "",
            "moving_seconds": float(self.data.get("moving_seconds") or 0.0),
            "move_count": int(self.data.get("move_count") or 0),
            "joints": {name: dict(row) for name, row in joints.items()},
            # 제일 많이 움직인 관절. 기록이 없으면 빈 값이다 — 아무나 지목하지 않는다.
            "busiest_joint": busiest,
            "last_self_check_at": self.data.get("last_self_check_at") or "",
            "last_self_check_verdict": self.data.get("last_self_check_verdict") or "",
            "has_history": bool(joints),
        }
