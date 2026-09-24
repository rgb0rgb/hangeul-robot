"""Bounded-memory A/B repetition; no expanded saved sequence and no auto-resume."""
from copy import deepcopy
import math
import threading
import time
import uuid

ACTIVE = {"running", "pausing", "paused", "canceling"}


def validate(payload):
    joint = str(payload.get("joint_id") or "").strip()
    if not joint:
        raise ValueError("관절을 선택하세요")
    count = payload.get("count", 1)
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 9007199254740991:
        raise ValueError("횟수는 1 이상의 정수여야 합니다")
    targets = []
    for key in ("a", "b"):
        value = payload.get(key)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("A와 B 위치를 입력하세요")
        targets.append(value)
    if targets[0] == targets[1]:
        raise ValueError("A와 B는 서로 다른 위치여야 합니다")
    waits = []
    for key in ("wait_a", "wait_b"):
        value = payload.get(key, 0)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError("대기 시간은 0 이상의 유한한 초 단위 값이어야 합니다")
        waits.append(float(value))
    return {"joint_id": joint, "count": count, "targets": targets, "waits": waits}


class RepeatWork:
    def __init__(self):
        self.cv = threading.Condition(threading.RLock())
        self.jobs = {}

    def busy(self, resource, owner=""):
        with self.cv:
            return any(j["resource"] == resource and j["state"] in ACTIVE and j["id"] != owner
                       for j in self.jobs.values())

    def status(self, robot):
        with self.cv:
            return deepcopy(self.jobs.get(robot, {"robot_id": robot, "state": "idle", "completed": 0}))

    def start(self, robot, resource, plan, move):
        with self.cv:
            if self.busy(resource):
                raise ValueError("이 장치에서 반복 작업이 이미 실행 중입니다")
            job = {"id": uuid.uuid4().hex, "robot_id": robot, "resource": resource,
                   "state": "running", "completed": 0, "cycle": 1, "phase": "A",
                   "error": "", **deepcopy(plan)}
            self.jobs[robot] = job
            threading.Thread(target=self._run, args=(job, move), daemon=True).start()
            return deepcopy(job)

    def control(self, robot, action):
        with self.cv:
            job = self.jobs.get(robot)
            if not job or job["state"] not in ACTIVE:
                raise ValueError("진행 중인 반복 작업이 없습니다")
            if action == "cancel":
                job["state"] = "canceling"
            elif action == "pause" and job["state"] == "running":
                job["state"] = "pausing"
            elif action == "resume" and job["state"] in ("paused", "pausing"):
                job["state"] = "running"
            elif action not in ("pause", "resume"):
                raise ValueError("알 수 없는 명령입니다")
            self.cv.notify_all()
            return deepcopy(job)

    def _wait(self, job, seconds=0):
        # Pausing freezes dwell time and takes effect after any in-flight move.
        with self.cv:
            remaining = seconds
            while True:
                if job["state"] == "canceling":
                    return False
                if job["state"] in ("pausing", "paused"):
                    job["state"] = "paused"
                    self.cv.wait()
                    continue
                if remaining <= 0:
                    return True
                start = time.monotonic()
                self.cv.wait(min(remaining, 0.2))
                remaining -= time.monotonic() - start

    def _run(self, job, move):
        try:
            for cycle in range(1, job["count"] + 1):
                for index, phase in enumerate(("A", "B")):
                    if not self._wait(job):
                        return
                    with self.cv:
                        job.update(cycle=cycle, phase=phase)
                    answer = move(job["id"], job["joint_id"], job["targets"][index])
                    with self.cv:
                        if job["state"] == "canceling":
                            return
                    if answer.get("success") is not True:
                        raise RuntimeError(answer.get("error") or "; ".join(answer.get("blocked_reasons") or [])
                                           or answer.get("verdict") or "이동 실패")
                    if not self._wait(job, job["waits"][index]):
                        return
                with self.cv:
                    job["completed"] = cycle
            with self.cv:
                if job["state"] != "canceling":
                    job["state"] = "completed"
        except Exception as exc:
            with self.cv:
                if job["state"] != "canceling":
                    job.update(state="failed", error=str(exc))
        finally:
            with self.cv:
                if job["state"] == "canceling":
                    job["state"] = "canceled"
                self.cv.notify_all()
