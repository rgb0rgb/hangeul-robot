"""FAIRINO FR5 — 문자열 관절(j1~j6)이 HTTP 경로에서 500 없이 판정된다 (2026-11-08).

공개판 0.4.4의 `_check_all()`은 `int(joint)`를 불러, "j1"로 /api/move-to를
부르면 ValueError가 HTTP 500으로 새어 나갔다. 화면에서는 '접속 끊김'으로 보인다.
범위 밖은 **이유와 함께 거절**, 범위 안은 **어댑터까지 간다** — 둘 다 500이 아니다.

여기서 쓰는 것은 실제 기술서와 실제 안전 범위 파일이다. ROS 노드만 가짜다
(넘어간 goal을 적는 기록계). 실물도, 시뮬레이터 연결도 이 시험의 증거가 아니다.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hangeul_runtime import safety, server
from hangeul_runtime.hardware.ros2_arm_adapter import Ros2ArmAdapter
from hangeul_runtime.hardware.ros2_transport import result_answer
from hangeul_runtime.recovery import hold_verified

ROOT = Path(__file__).resolve().parents[1]
MODULE = "arm_fairino5"
JOINTS = [f"j{i}" for i in range(1, 7)]
# FR5 URDF(fairino5_v6.urdf) 관절 범위, 도
URDF_DEG = {"j1": (-175, 175), "j2": (-265, 85), "j3": (-162, 162),
            "j4": (-265, 85), "j5": (-175, 175), "j6": (-175, 175)}


# JTC가 성공에 실어 보내는 문자열 그대로 (시뮬레이터 실측 20261108)
JTC_SUCCESS = "Goal successfully reached!"


class _FakeNode:
    """실제 전송층과 같은 모양으로 답한다 — 성공에도 error_string이 찬다."""

    def __init__(self):
        self.goals = []
        self.positions = {name: 0.0 for name in JOINTS}

    def joint_positions(self):
        return dict(self.positions)

    def server_ready(self):
        return True

    def send_trajectory(self, *, joint_names, positions, time_from_start_s, label):
        self.goals.append(dict(zip(joint_names, positions)))
        self.positions.update(dict(zip(joint_names, positions)))
        return result_answer(succeeded=True, canceled=False, status=4, error_code=0,
                             error_string=JTC_SUCCESS, feedback_count=1)

    def cancel_all(self):
        pass

    def close(self):
        pass


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "state", safety.SafetyState())
    monkeypatch.setattr(server, "_pace", lambda *a, **k: None)
    server._JOB.update({"name": "", "since": 0.0})
    server.build(MODULE, "", simulate=True,
                 state_path=str(tmp_path / "state.json"),
                 usage_path=str(tmp_path / "usage.json"))
    node = _FakeNode()
    adapter = Ros2ArmAdapter("/fairino5_controller", joint_count=6,
                             descriptor=server.CONFIG["descriptor"], node=node)
    server.CONFIG["adapter"] = adapter
    server.CONFIG["simulate_reason"] = ""
    with TestClient(server.app, raise_server_exceptions=False) as c:
        c.node = node
        yield c
    server.CONFIG["adapter"] = None
    server._JOB.update({"name": "", "since": 0.0})


def test_every_joint_has_a_band_inside_the_urdf():
    """범위가 없는 관절은 검사 없이 통과한다(safety.check_move). 빠짐이 곧 구멍이다."""
    descriptor = json.loads((ROOT / "install/modules" / f"{MODULE}.json").read_text("utf-8"))
    limits = json.loads((ROOT / "data" / f"safety_limits_{MODULE}.json").read_text("utf-8"))
    assert [j["id"] for j in descriptor["joints"]] == JOINTS
    for joint, (lo, hi) in URDF_DEG.items():
        band = limits[joint]
        assert lo + 5 <= band[0] < band[1] <= hi - 5, f"{joint} 범위가 URDF 5° 안쪽이 아닙니다"


def test_string_joint_out_of_range_is_refused_not_500(client):
    answer = client.post("/api/move-to", json={"joint_id": "j1", "target_ticks": 200000})
    assert answer.status_code == 200
    body = answer.json()
    assert body["success"] is False
    assert body.get("actual_hardware_called") is False
    assert "j1" in json.dumps(body, ensure_ascii=False)
    assert client.node.goals == [], "범위 밖인데 goal이 나갔습니다"


def test_string_joint_in_range_reaches_the_controller(client):
    answer = client.post("/api/move-to",
                         json={"joint_id": "j1", "target_ticks": 10000, "speed": "slow"})
    assert answer.status_code == 200, answer.text
    assert answer.json()["success"] is True, answer.json()
    assert client.node.goals, "범위 안인데 goal이 나가지 않았습니다"
    assert math.isclose(client.node.goals[-1]["j1"], math.radians(10.0), abs_tol=1e-9)


def test_unknown_string_joint_is_refused_not_500(client):
    answer = client.post("/api/move-to", json={"joint_id": "j7", "target_ticks": 0})
    assert answer.status_code == 200
    assert answer.json()["success"] is False
    # 다른 거절 안내와 같이 한국어로 — 이것만 영어였다(공개본 검토 지적 20261110)
    assert "알 수 없거나 꺼 둔 관절입니다: j7" in answer.json()["blocked_reasons"][0]
    assert client.node.goals == []


def test_string_joint_jog_is_judged_not_500(client):
    answer = client.post("/api/jog", json={"joint_id": "j3", "delta_ticks": 500000})
    assert answer.status_code == 200, answer.text
    assert answer.json()["success"] is False
    assert client.node.goals == []


# ── 정지 해제 (2026-11-08 시뮬레이터에서 드러남) ───────────────────
def test_a_succeeded_ros_result_is_not_an_error():
    """성공한 goal의 error_string을 error로 올리면 복구 검증이 늘 실패한다."""
    answer = result_answer(succeeded=True, canceled=False, status=4, error_code=0,
                           error_string=JTC_SUCCESS, feedback_count=3)
    assert answer["error"] == ""
    assert answer["error_string"] == JTC_SUCCESS
    assert hold_verified({**answer, "success": True, "settled": True})


@pytest.mark.parametrize("status,code,text", [
    (6, 0, "aborted"),                          # STATUS_ABORTED
    (4, -1, "INVALID_GOAL"),                    # 상태는 성공인데 error_code가 실패
    (6, 0, ""),                                 # 이유 없이 실패해도 error는 빈칸이 아니다
])
def test_a_failed_ros_result_still_reads_as_failure(status, code, text):
    answer = result_answer(succeeded=status == 4, canceled=False, status=status,
                           error_code=code, error_string=text, feedback_count=0)
    assert answer["result_ok"] is False
    assert answer["error"]
    assert not hold_verified(answer)


def test_estop_then_reset_lets_a_string_joint_move_again(client):
    client.post("/api/estop", json={"reason": "시험"})
    blocked = client.post("/api/move-to", json={"joint_id": "j1", "target_ticks": 5000}).json()
    assert blocked["success"] is False and blocked["reason_code"] == "estop_latched"

    reset = client.post("/api/estop-reset", json={"operator": "rgb", "confirmed": True}).json()
    assert reset["success"] is True, reset
    assert reset["estop_active"] is False and reset["disconnect_latched"] is False

    moved = client.post("/api/move-to", json={"joint_id": "j1", "target_ticks": 5000}).json()
    assert moved["success"] is True, moved
