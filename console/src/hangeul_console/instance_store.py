"""운영자 자산 보관 — 사람이 가르친 것만 여기 있다.

이전 구조의 문제: 로봇 구성(축·포트·모델)과 운영자 자산(자세·순서)과 런타임 상태
(실행 중·마지막 오류)가 한 폴더에 섞여 있었다. 그래서 백업 대상이 무엇인지
불분명했고, 설정을 고치면 자산이 함께 흔들렸다.

여기서는 셋을 나눈다.

    install/robots/*.json   로봇 구성   — 사람이 정하는 설계값, git 대상
    data/instances/<id>/    운영자 자산 — 가르친 자세·순서, 백업 대상
    data/instances/<id>/runtime.json  런타임 상태 — 언제든 버려도 되는 값

이 모듈은 가운데(운영자 자산)만 다룬다.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

POSES_FILE = "poses.json"
SEQUENCE_FILE = "sequence.json"
LIBRARY_FILE = "sequence_library.json"
RUNTIME_FILE = "runtime.json"

EMPTY = {
    POSES_FILE: {"format": "hangeul_robot.poses.v1", "poses": {}},
    SEQUENCE_FILE: {"sequence_name": "", "steps": []},
    LIBRARY_FILE: {"sequences": {}},
    RUNTIME_FILE: {"run_state": "대기", "attached_robot": None, "last_result": "",
                   "last_error": "", "selected_in_ui": False},
}


class InstanceStore:
    """인스턴스 하나의 자산 폴더."""

    def __init__(self, root: Path, instance_id: str):
        self.dir = Path(root) / instance_id
        self.instance_id = instance_id

    def _read(self, name: str) -> dict[str, Any]:
        path = self.dir / name
        if not path.exists():
            return json.loads(json.dumps(EMPTY[name]))
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            # 깨진 파일을 조용히 덮어쓰지 않는다. 빈 값으로 읽되 원본은 남긴다.
            return json.loads(json.dumps(EMPTY[name]))

    def _write(self, name: str, data: dict[str, Any]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / name).write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # 자세
    def poses(self) -> dict[str, Any]:
        return self._read(POSES_FILE)

    def save_poses(self, data: dict[str, Any]) -> None:
        self._write(POSES_FILE, data)

    def movements(self) -> list[dict[str, Any]]:
        """화면 계약(동작 카드) 형태로 변환."""
        out = []
        for pose_id, pose in (self.poses().get("poses") or {}).items():
            if pose.get("deleted"):
                continue
            out.append({
                "skill_id": pose_id,
                "display_name_kr": pose.get("display_name_kr") or pose_id,
                "display_name_en": pose.get("display_name_en") or pose_id,
                "description_kr": pose.get("description_kr") or "",
                "description_en": pose.get("description_en") or "",
                "targets": pose.get("targets") or {},
                "icon": pose.get("icon") or "🤖",
                "color": pose.get("color") or "#0ea5e9",
                "delay_sec": pose.get("delay_sec", 0.0),
                "motion_type": pose.get("motion_type") or "absolute",
                "micro_move_steps": pose.get("micro_move_steps") or [],
            })
        return out

    # 실행 순서
    def sequence(self) -> dict[str, Any]:
        return self._read(SEQUENCE_FILE)

    def save_sequence(self, data: dict[str, Any]) -> None:
        self._write(SEQUENCE_FILE, data)

    def library(self) -> dict[str, Any]:
        return self._read(LIBRARY_FILE)

    def save_library(self, data: dict[str, Any]) -> None:
        self._write(LIBRARY_FILE, data)

    # 런타임 상태 — 버려도 되는 값
    def runtime(self) -> dict[str, Any]:
        return self._read(RUNTIME_FILE)

    def update_runtime(self, **fields: Any) -> dict[str, Any]:
        data = self.runtime()
        data.update(fields)
        self._write(RUNTIME_FILE, data)
        return data
