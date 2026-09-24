import threading
import time

import pytest

from hangeul_console.repeat_work import RepeatWork, validate


def wait_for(fn, timeout=3):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if fn():
            return
        time.sleep(0.01)
    assert fn()


def plan(**kw):
    return validate({"joint_id": "12", "a": 1300, "b": 2000, "count": 50, **kw})


def test_fifty_cycles_are_a_hundred_alternating_moves():
    runner, calls = RepeatWork(), []
    def move(_, joint, target):
        calls.append((joint, target))
        return {"success": True}
    runner.start("r", "device", plan(), move)
    wait_for(lambda: runner.status("r")["state"] == "completed")
    assert calls == [("12", 1300), ("12", 2000)] * 50
    assert runner.status("r")["completed"] == 50


def test_failure_never_runs_the_next_position():
    runner, calls = RepeatWork(), []
    def move(*args):
        calls.append(args)
        return {"success": False, "verdict": "TARGET_NOT_REACHED"}
    runner.start("r", "device", plan(), move)
    wait_for(lambda: runner.status("r")["state"] == "failed")
    assert len(calls) == 1
    assert runner.status("r")["completed"] == 0


def test_pause_after_inflight_move_and_cancel_during_long_dwell():
    runner, entered, release = RepeatWork(), threading.Event(), threading.Event()
    calls = []
    def move(*args):
        calls.append(args)
        entered.set()
        release.wait(2)
        return {"success": True}
    runner.start("r", "device", plan(wait_a=600), move)
    assert entered.wait(1)
    runner.control("r", "pause")
    release.set()
    wait_for(lambda: runner.status("r")["state"] == "paused")
    assert len(calls) == 1
    with pytest.raises(ValueError):
        runner.start("other_robot", "device", plan(), move)
    runner.control("r", "resume")
    runner.control("r", "cancel")
    wait_for(lambda: runner.status("r")["state"] == "canceled")
    assert len(calls) == 1


@pytest.mark.parametrize("kw", [{"count": 0}, {"count": 1.5}, {"count": True},
                                {"wait_a": -1}, {"wait_b": float("nan")}, {"a": 2000}])
def test_invalid_plan_rejected(kw):
    with pytest.raises(ValueError):
        plan(**kw)


@pytest.fixture
def repeat_api(client, monkeypatch, tmp_path):
    from conftest import install_fixture_robots
    from hangeul_console import app as a
    install_fixture_robots(monkeypatch, tmp_path)
    monkeypatch.setattr(a, "repeat_work", RepeatWork())
    monkeypatch.setattr(a, "_RUN_FLAGS", {})
    monkeypatch.setattr(a.runtime, "forward", lambda *args, **kwargs: {"joint_tick_limits": {"12": [1000, 2200], "15": [500, 1963]}})
    monkeypatch.setattr(a.runtime, "health", lambda i: {"connected": True, "capability_health": {"_default": "AVAILABLE"}, "parts": {}})
    moves = []
    def run(instance, skill_id, **kwargs):
        moves.append((instance.instance_id, kwargs["targets"]))
        return {"ok": True, "verdict": "DONE", "detail": {"success": True}}
    monkeypatch.setattr(a.runtime, "run", run)
    monkeypatch.setattr(a.runtime, "stop", lambda i: {"stopped": True})
    return client, a, moves


def body(**kw):
    return {"robot_id": "young_omx", "joint_id": "12", "a": 1300, "b": 2000, "count": 2,
            "safety_inputs": {k: True for k in ("operator_present", "workspace_clear", "manual_stop_available", "estop_ready")}, **kw}


def test_api_runs_without_creating_or_expanding_saved_sequence(repeat_api):
    client, a, calls = repeat_api
    before = a._store("young_omx").sequence()
    assert client.post("/api/repeat-work/start", json=body()).json()["success"]
    wait_for(lambda: a.repeat_work.status("young_omx")["state"] not in ("running", "pausing"))
    assert a.repeat_work.status("young_omx")["state"] == "completed"
    assert calls == [("young_omx", {"12": 1300}), ("young_omx", {"12": 2000})] * 2
    assert a._store("young_omx").sequence() == before


def test_b_is_validated_before_a_can_move(repeat_api):
    client, a, calls = repeat_api
    assert not client.post("/api/repeat-work/start", json=body(b=9999)).json()["success"]
    assert not calls


def test_gripper_and_cancel_prevent_further_cycles(repeat_api):
    client, a, calls = repeat_api
    assert client.post("/api/repeat-work/start", json=body(joint_id="15", a=1963, b=500, wait_a=30)).json()["success"]
    wait_for(lambda: bool(calls))
    assert calls[0] == ("young_omx", {"15": 1963})
    assert not client.post("/api/repeat-work/start", json=body()).json()["success"]
    assert client.post("/api/repeat-work/control", json={"robot_id": "young_omx", "action": "cancel"}).json()["stop_result"]["stopped"]
    wait_for(lambda: a.repeat_work.status("young_omx")["state"] == "canceled")
    assert len(calls) == 1


def test_busy_blocks_other_console_motion_and_missing_confirmation(repeat_api):
    client, a, calls = repeat_api
    assert not client.post("/api/repeat-work/start", json=body(safety_inputs={})).json()["success"]
    assert not calls
    assert client.post("/api/repeat-work/start", json=body(wait_a=60)).json()["success"]
    wait_for(lambda: bool(calls))
    try:
        instance = a._instance("young_omx")
        assert a._execute_pose(instance, {"targets": {"12": 1500}})["verdict"] == "BLOCKED_REPEAT_BUSY"
        assert client.post("/api/self-check", json={"robot_id": "young_omx"}).json()["verdict"] == "BLOCKED_REPEAT_BUSY"
    finally:
        client.post("/api/repeat-work/control", json={"robot_id": "young_omx", "action": "cancel"})
    wait_for(lambda: a.repeat_work.status("young_omx")["state"] == "canceled")
    assert len(calls) == 1


def test_changed_configuration_stops_before_next_move(repeat_api, monkeypatch):
    client, a, calls = repeat_api
    assert client.post("/api/repeat-work/start", json=body(wait_a=0.2)).json()["success"]
    wait_for(lambda: bool(calls))
    instance = a._instance("young_omx")
    monkeypatch.setattr(type(instance), "fingerprint", lambda self: "changed")
    wait_for(lambda: a.repeat_work.status("young_omx")["state"] == "failed")
    assert len(calls) == 1


def test_cancel_stops_original_endpoint_after_connection_edit(repeat_api, monkeypatch):
    client, a, calls = repeat_api
    instance = a._instance("young_omx")
    original = instance.runtime_url
    assert client.post("/api/repeat-work/start", json=body(wait_a=60)).json()["success"]
    wait_for(lambda: bool(calls))
    monkeypatch.setattr(instance, "runtime_url_value", "http://changed.invalid")
    stopped = []
    monkeypatch.setattr(a.runtime, "stop", lambda target: stopped.append(target.runtime_url) or {"stopped": True})
    assert client.post("/api/repeat-work/control", json={"robot_id": "young_omx", "action": "cancel"}).json()["success"]
    wait_for(lambda: a.repeat_work.status("young_omx")["state"] == "canceled")
    assert stopped == [original]
    assert instance.runtime_url == "http://changed.invalid"


def saved_repeat(client, **changes):
    repeat = {"joint_id": "12", "a": 1300, "b": 2000, "count": 3, "wait_a": 0, "wait_b": 0, **changes}
    answer = client.post("/api/save-pose", json={"instance_id": "young_omx", "name_kr": "왕복",
                                               "motion_type": "repeat", "repeat_work": repeat}).json()
    assert answer["success"], answer
    return answer["skill_id"], repeat


def test_saved_repeat_round_trip_and_single_card_executes_all_cycles(repeat_api):
    client, a, calls = repeat_api
    skill, plan = saved_repeat(client)
    assert not calls  # Saving must not move hardware.
    card = next(c for c in a._poses("young_omx").movements() if c["skill_id"] == skill)
    assert card["motion_type"] == "repeat" and card["repeat_work"] == plan
    answer = a._execute_pose(a._instance("young_omx"), {"skill_id": skill, "safety_inputs": body()["safety_inputs"]})
    assert answer["success"] and answer["repeat_work"]["completed"] == 3
    assert calls == [("young_omx", {"12": 1300}), ("young_omx", {"12": 2000})] * 3
    assert skill not in a._poses("young_mycobot").poses().get("poses", {})


def test_saved_sequence_waits_for_repeat_before_next_card(repeat_api):
    client, a, calls = repeat_api
    skill, _ = saved_repeat(client)
    next_card = client.post("/api/save-pose", json={"instance_id": "young_omx", "name_kr": "다음", "targets": {"12": 1500}}).json()["skill_id"]
    a._store("young_omx").save_sequence({"steps": [{"pose_id": skill}, {"pose_id": next_card}]})
    a._run_sequence("young_omx", body()["safety_inputs"], "")
    assert calls == [("young_omx", {"12": 1300}), ("young_omx", {"12": 2000})] * 3 + [("young_omx", {"12": 1500})]
    assert a._store("young_omx").runtime()["run_state"] == "완료"


def test_edit_repeat_count_and_invalid_edit_does_not_overwrite(repeat_api):
    client, a, calls = repeat_api
    skill, plan = saved_repeat(client)
    payload = {"instance_id": "young_omx", "skill_id": skill, "name_kr": "왕복 수정",
               "motion_type": "repeat", "repeat_work": {**plan, "count": 10, "wait_a": 0.5, "wait_b": 1}}
    assert client.post("/api/save-pose", json=payload).json()["success"]
    stored = a._poses("young_omx").poses()["poses"][skill]
    assert stored["repeat_work"] == payload["repeat_work"]
    payload["repeat_work"]["count"] = 0
    assert not client.post("/api/save-pose", json=payload).json()["success"]
    assert a._poses("young_omx").poses()["poses"][skill] == stored
    assert not calls


def test_saved_repeat_failure_stops_sequence(repeat_api, monkeypatch):
    client, a, calls = repeat_api
    skill, _ = saved_repeat(client)
    a._store("young_omx").save_sequence({"steps": [{"pose_id": skill}, {"pose_id": skill}]})
    failures = []
    monkeypatch.setattr(a.runtime, "run", lambda *args, **kw: failures.append(kw) or {"ok": False, "detail": {"success": False, "error": "not reached"}})
    a._run_sequence("young_omx", body()["safety_inputs"], "")
    assert len(failures) == 1
    assert a._store("young_omx").runtime()["run_state"] == "실패"


def _sequence_with_gated_repeat(client, a, monkeypatch):
    """저장한 반복 한 장을 순서에 넣고, 이동마다 문을 열어 줘야 넘어가게 한다."""
    skill, _ = saved_repeat(client)
    a._store("young_omx").save_sequence({"steps": [{"pose_id": skill}]})
    moved, gate = [], threading.Semaphore(0)
    def run(instance, skill_id, **kwargs):
        moved.append(kwargs["targets"])
        gate.acquire(timeout=3)
        return {"ok": True, "verdict": "DONE", "detail": {"success": True}}
    monkeypatch.setattr(a.runtime, "run", run)
    a._RUN_FLAGS["young_omx"] = {"cancel": False, "paused": False}
    thread = threading.Thread(target=a._run_sequence, args=("young_omx", body()["safety_inputs"], ""))
    thread.start()
    wait_for(lambda: len(moved) == 1)
    return moved, gate, thread


def test_sequence_cancel_reaches_the_running_repeat(repeat_api, monkeypatch):
    # 전에는 취소가 화면 표시만 바꿔, "취소"가 뜬 채 반복이 끝까지 돌았다.
    client, a, _ = repeat_api
    moved, gate, thread = _sequence_with_gated_repeat(client, a, monkeypatch)
    assert client.post("/api/hangeul/multi-cancel").json()["cancelled"] == ["young_omx"]
    gate.release()
    thread.join(3)
    assert not thread.is_alive()
    assert len(moved) == 1                      # 진행 중이던 이동 뒤로는 하나도 안 나간다
    assert a.repeat_work.status("young_omx")["state"] == "canceled"
    assert a._store("young_omx").runtime()["run_state"] == "취소"


def test_sequence_pause_and_resume_reach_the_running_repeat(repeat_api, monkeypatch):
    client, a, _ = repeat_api
    moved, gate, thread = _sequence_with_gated_repeat(client, a, monkeypatch)
    assert client.post("/api/hangeul/multi-pause-hold").json()["paused"]
    gate.release()
    wait_for(lambda: a.repeat_work.status("young_omx")["state"] == "paused")
    time.sleep(0.3)
    assert len(moved) == 1                      # 멈춘 동안 다음 이동이 없다
    assert client.post("/api/hangeul/multi-resume").json()["resumed"]
    for _ in range(5):
        gate.release()
    thread.join(3)
    assert len(moved) == 6                      # 3회 = 6번 이동, 끝까지 간다
    assert a._store("young_omx").runtime()["run_state"] == "완료"


def test_multi_resume_does_not_unpause_a_panel_repeat(repeat_api, monkeypatch):
    # 패널에서 사람이 멈춘 반복은 사람이 푼다. 순서 재개가 대신 풀지 않는다.
    client, a, _ = repeat_api
    release = threading.Event()
    monkeypatch.setattr(a.runtime, "run", lambda *x, **k: release.wait(3) and {"ok": True, "verdict": "DONE", "detail": {"success": True}})
    assert client.post("/api/repeat-work/start", json=body()).json()["success"]
    client.post("/api/repeat-work/control", json={"robot_id": "young_omx", "action": "pause"})
    release.set()
    wait_for(lambda: a.repeat_work.status("young_omx")["state"] == "paused")
    client.post("/api/hangeul/multi-resume")
    time.sleep(0.3)
    assert a.repeat_work.status("young_omx")["state"] == "paused"
    client.post("/api/repeat-work/control", json={"robot_id": "young_omx", "action": "cancel"})
