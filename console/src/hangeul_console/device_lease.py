"""장치 임대 — C10. 한 장치에 한 주인.

같은 로봇을 두 프로세스가 동시에 쓰면 서로의 명령이 섞인다. 실물에서는 사고다.
그래서 쓰기 전에 **임대**를 받아야 하고, 임대에는 세대 번호가 붙는다.

    임대 없음        → 쓰기 거부
    남이 쥐고 있음   → 쓰기 거부 (누가 쥐고 있는지 알려준다)
    임대 만료        → 자동 해제. 그 로봇만 멈춘다
    세대 번호가 낮음 → 오래된 명령이므로 거부

파일 잠금으로 구현한다. 같은 컴퓨터 안에서 증명할 수 있고, 여러 대로 늘릴 때
같은 계약을 유지한 채 구현만 바꾸면 된다.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

LEASE_TTL_SEC = 30.0


class LeaseError(ValueError):
    def __init__(self, reason_code: str, message: str):
        super().__init__(message)
        self.reason_code = reason_code


@dataclass
class Lease:
    resource_id: str
    holder: str
    generation: int
    expires_at: float

    def alive(self, now: float | None = None) -> bool:
        return (now or time.time()) < self.expires_at

    def to_dict(self) -> dict[str, Any]:
        return {"resource_id": self.resource_id, "holder": self.holder,
                "generation": self.generation, "expires_at": self.expires_at}


class LeaseBook:
    """장치별 임대 장부."""

    def __init__(self, directory: Path, ttl_sec: float = LEASE_TTL_SEC):
        self.dir = Path(directory)
        self.ttl = ttl_sec

    def _path(self, resource_id: str) -> Path:
        safe = "".join(ch if ch.isalnum() else "_" for ch in resource_id)
        return self.dir / f"lease_{safe}.json"

    def read(self, resource_id: str) -> Lease | None:
        path = self._path(resource_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return Lease(**data)
        except (json.JSONDecodeError, TypeError):
            return None

    def acquire(self, resource_id: str, holder: str, *, now: float | None = None) -> Lease:
        """임대를 받는다. 남이 살아 있는 임대를 쥐고 있으면 거절한다."""
        now = now or time.time()
        current = self.read(resource_id)
        if current and current.alive(now) and current.holder != holder:
            raise LeaseError(
                "held_by_other",
                f"{resource_id}는 {current.holder}가 쓰고 있습니다 "
                f"(남은 시간 {current.expires_at - now:.0f}초)")
        generation = (current.generation + 1) if current else 1
        lease = Lease(resource_id, holder, generation, now + self.ttl)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._path(resource_id).write_text(
            json.dumps(lease.to_dict(), ensure_ascii=False), encoding="utf-8")
        return lease

    def renew(self, lease: Lease, *, now: float | None = None) -> Lease:
        return self.acquire(lease.resource_id, lease.holder, now=now)

    def release(self, resource_id: str, holder: str) -> bool:
        current = self.read(resource_id)
        if current and current.holder != holder:
            return False
        self._path(resource_id).unlink(missing_ok=True)
        return True

    def check_write(self, resource_id: str, holder: str, generation: int,
                    *, now: float | None = None) -> None:
        """쓰기 직전 검사. 통과하지 못하면 명령을 보내지 않는다."""
        now = now or time.time()
        current = self.read(resource_id)
        if current is None:
            raise LeaseError("no_lease", f"{resource_id}에 대한 임대가 없습니다")
        if not current.alive(now):
            raise LeaseError("expired", f"{resource_id} 임대가 만료됐습니다")
        if current.holder != holder:
            raise LeaseError("held_by_other", f"{resource_id}는 {current.holder}가 쓰고 있습니다")
        if generation < current.generation:
            raise LeaseError("stale_generation",
                             f"오래된 명령입니다 (세대 {generation} < {current.generation})")
