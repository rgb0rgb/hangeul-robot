"""로봇 런타임 연결 — 콘솔과 실물 사이의 유일한 통로.

콘솔은 시리얼을 직접 열지 않는다. 실물 제어와 안전 판정은 로봇 런타임이 한다.
여기서는 그 런타임에 묻고 넘길 뿐이다.

지키는 것
1. 런타임이 죽어 있어도 콘솔은 계속 뜬다. 그 로봇만 "쓸 수 없음"이 된다.
2. 멈춤은 다른 요청과 같은 줄에 서지 않는다. 짧은 제한시간으로 먼저 나간다.
3. 응답이 없으면 성공으로 기록하지 않는다.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

HEALTH_TIMEOUT_SEC = 2.0
# 같은 런타임을 보는 로봇이 여럿이면 살아있음 확인이 그 수만큼 곱해진다.
# 로봇 4대면 3초마다 4번 — 시리얼 한 줄에 그만큼이 얹히면 답이 -1로 돌아오기
# 시작한다(실측). 같은 주소는 이 시간 안에 한 번만 묻는다.
HEALTH_CACHE_SEC = 1.5
RUN_TIMEOUT_SEC = 180.0
STOP_TIMEOUT_SEC = 5.0


class RuntimeLink:
    """콘솔과 로봇 런타임 사이에는 접근 키가 없다(2026-08-21에 없앴다).

    둘 다 127.0.0.1에만 열려 있어 키는 같은 컴퓨터 안에서 자기 자신에게 문을
    잠그는 일이었다. 사람이 키를 만들어 넣어야 하는 단계만 남고, 키를 못 찾으면
    실행이 BLOCKED_NO_RUNTIME_KEY로 막혔다. 밖에 열게 되는 날에는 키가 아니라
    제대로 된 인증을 새로 놓아야 한다.
    """

    @staticmethod
    def _identify(instance, payload: dict | None) -> dict | None:
        """어느 로봇인지 요청마다 붙인다. 런타임 한 대가 여러 로봇을 다루기 때문이다.
        (이걸 빠뜨리면 MyCobot을 눌러도 OMX가 응답한다 — 실제로 그랬다.)"""
        model, device = instance.runtime_model(), instance.device_name()
        if payload is None:
            return None
        out = dict(payload)
        # 화면이 보낸 값보다 콘솔이 고른 로봇이 우선이다. 화면의 값은 예전
        # 단일 로봇 시절의 브라우저 저장값이라 'mock'이나 다른 로봇으로 남아
        # 있을 수 있고, 그대로 두면 MyCobot에 OMX 관절 번호가 날아간다.
        if model:
            out["robot_model"] = model
        if device:
            out["device"] = device
        return out

    def _query(self, instance) -> str:
        import urllib.parse
        params = {}
        if instance.runtime_model():
            params["robot_model"] = instance.runtime_model()
        if instance.device_name():
            params["device"] = instance.device_name()
        return ("?" + urllib.parse.urlencode(params)) if params else ""

    def _call(self, instance, path: str, payload: dict | None = None,
              timeout: float = HEALTH_TIMEOUT_SEC, method: str = "GET") -> dict[str, Any]:
        payload = self._identify(instance, payload)
        url = instance.runtime_url.rstrip("/") + path
        if method == "GET":
            url += self._query(instance)
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read().decode("utf-8")
            return {"ok": True, "data": json.loads(body) if body else {}}
        except urllib.error.HTTPError as exc:
            # 런타임은 막을 때도 이유를 본문에 담아 보낸다(409 등).
            # 그 이유를 버리면 화면에는 "연결 안 됨"만 남는다 — 실제로 그랬다.
            detail: dict[str, Any] = {}
            try:
                raw = exc.read().decode("utf-8")
                parsed = json.loads(raw) if raw else {}
                if isinstance(parsed, dict):
                    detail = parsed
            except (ValueError, OSError):
                detail = {}
            return {"ok": False, "status": exc.code, "data": detail,
                    "reason": f"런타임 응답 오류 {exc.code}"}
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
            return {"ok": False, "reason": f"런타임에 연결하지 못했습니다 ({exc.__class__.__name__})"}

    # 로봇 런타임(Grid)에는 종합 status 엔드포인트가 없다. 실제로 있는 것 중
    # 부작용 없는 읽기 전용 경로를 살아있음 확인에 쓴다.
    HEALTH_PATH = "/api/estop-status"

    _health_cache: dict[str, tuple[float, dict[str, Any]]] = {}

    def health(self, instance) -> dict[str, Any]:
        """이 로봇이 지금 쓸 수 있는지. 런타임이 없으면 그 로봇만 못 쓴다."""
        import time as _time
        key = f"{instance.runtime_url}|{instance.runtime_model()}|{instance.device_name()}"
        hit = self._health_cache.get(key)
        if hit and _time.monotonic() - hit[0] < HEALTH_CACHE_SEC:
            return dict(hit[1])
        answer = self._health(instance)
        self._health_cache[key] = (_time.monotonic(), dict(answer))
        return answer

    def _health(self, instance) -> dict[str, Any]:
        result = self._call(instance, self.HEALTH_PATH)
        if not result["ok"]:
            return {
                "connected": False,
                "reason": result.get("reason", "연결 없음"),
                "capability_health": {"_default": "UNAVAILABLE", "_reason": result.get("reason", "")},
            }
        data = result["data"] or {}
        # 런타임은 살아 있는데 실물에 안 붙은 상태(시늉)를 "연결됨"으로만 보여주면,
        # 사람은 로봇이 움직일 거라고 믿는다. 시늉이면 시늉이라고 그 자리에 적는다.
        if data.get("simulated"):
            why = data.get("simulate_reason") or "실물에 연결되지 않았습니다"
            return {
                "connected": True,
                "simulated": True,
                "reason": f"시늉 모드 — {why}",
                "capability_health": {"_default": "AVAILABLE", "_reason": why},
                "runtime": data,
            }
        return {
            "connected": True,
            "simulated": False,
            "reason": "",
            "capability_health": {"_default": "AVAILABLE"},
            "runtime": data,
        }

    def tasks(self, instance) -> list[dict[str, Any]]:
        """이 로봇에 저장된 할 일 목록. 런타임이 없으면 빈 목록이다."""
        result = self._call(instance, "/api/simple-catalog")
        if not result["ok"]:
            return []
        movements = (result["data"] or {}).get("movements") or []
        return [{
            "task_id": m.get("skill_id"),
            "label": m.get("display_name_kr") or m.get("skill_id"),
            "icon": m.get("icon") or "🤖",
        } for m in movements]

    def run(self, instance, task_id: str, speed: str = "slow",
            targets: dict[str, Any] | None = None,
            extra: dict[str, Any] | None = None) -> dict[str, Any]:
        """자세의 관절 목표는 콘솔이 보낸다 — 런타임은 자세를 알지 않는다.
        (skill_id도 함께 보낸다. 옛 런타임은 그것으로 찾고, 새 런타임은 targets를 쓴다.)"""
        # 화면이 보낸 안전 확인 항목(operator_present 등)을 그대로 넘긴다.
        # 이걸 버리면 런타임의 안전 게이트가 '운영자 없음'으로 막는다 — 실제로 그랬다.
        body = dict(extra or {})
        body.update({"skill_id": task_id, "operator": "console", "speed": speed,
                     "targets": targets or {}})
        result = self._call(instance, "/api/execute-actual", body,
                            timeout=RUN_TIMEOUT_SEC, method="POST")
        if not result["ok"]:
            blocked = result.get("data") or {}
            if blocked.get("verdict"):
                return {"ok": False, "verdict": blocked["verdict"],
                        "reason": "; ".join(blocked.get("blocked_reasons") or []),
                        "detail": blocked}
            return {"ok": False, "verdict": "RUNTIME_UNREACHABLE", "reason": result.get("reason")}
        data = result["data"] or {}
        verdict = data.get("verdict", "")
        return {"ok": "BLOCKED" not in verdict, "verdict": verdict, "detail": data}

    # 런타임이 "그 자세를 모른다"고 막을 때 쓰는 판정어들.
    # 자세의 주인은 콘솔이다 — 런타임이 모르면 알려주고 다시 시킨다.
    UNKNOWN_TASK_VERDICTS = ("POSE_REQUIRED", "UNKNOWN_SKILL", "NOT_FOUND")

    def sync_task(self, instance, task: dict[str, Any]) -> dict[str, Any]:
        """콘솔이 가진 자세 카드를 런타임 쪽에도 심는다. 하드웨어는 건드리지 않는다
        (targets를 직접 주면 런타임은 로봇을 읽지 않는다)."""
        targets = {str(k): int(v) for k, v in (task.get("targets") or {}).items()}
        if not targets:
            return {"success": False, "reason": "관절 목표가 없는 자세는 보낼 수 없습니다"}
        payload = {
            "skill_id": task.get("skill_id"),
            "name_kr": task.get("display_name_kr") or task.get("skill_id"),
            "name_en": task.get("display_name_en") or task.get("skill_id"),
            "description_kr": task.get("description_kr") or "",
            "description_en": task.get("description_en") or "",
            "targets": targets,
            "icon": task.get("icon") or "🤖",
            "delay_sec": float(task.get("delay_sec") or 0.0),
            "micro_move_steps": task.get("micro_move_steps") or [],
        }
        result = self._call(instance, "/api/save-pose", payload,
                            timeout=RUN_TIMEOUT_SEC, method="POST")
        if not result["ok"]:
            return {"success": False, "reason": result.get("reason"),
                    "detail": result.get("data") or {}}
        return result["data"] or {"success": True}

    def read_pose(self, instance) -> dict[str, Any]:
        """현재 관절값 읽기 — 읽기 전용."""
        result = self._call(instance, "/api/read-pose")
        if not result["ok"]:
            return {"success": False, "reason": result.get("reason"), "present": {}}
        return result["data"]

    def forward(self, instance, path: str, payload: dict | None,
                method: str = "POST") -> dict[str, Any]:
        """화면 요청을 런타임으로 그대로 넘긴다. 안전 판정은 런타임이 한다."""
        result = self._call(instance, path, payload,
                            timeout=RUN_TIMEOUT_SEC if method == "POST" else HEALTH_TIMEOUT_SEC,
                            method=method)
        if not result["ok"]:
            blocked = result.get("data") or {}
            if blocked:
                return blocked
            return {"success": False, "verdict": "RUNTIME_UNREACHABLE",
                    "reason": result.get("reason")}
        return result["data"]

    def stop(self, instance) -> dict[str, Any]:
        result = self._call(instance, "/api/estop", {"operator": "console"},
                            timeout=STOP_TIMEOUT_SEC, method="POST")
        if not result["ok"]:
            return {"stopped": False, "reason": result.get("reason")}
        return {"stopped": True, "detail": result["data"]}
