"""실행기(tools/launcher.py) — 시작 · 완전 초기화가 조용히 실패하지 않는다.

2026-09-24 실측. USB가 다시 붙으며 장치 번호가 바뀌자, 화면의 서버 재시작은
런타임을 "건너뜀"으로 빠뜨리고 아무 말도 하지 않았다. 사람은 재시작을 계속
눌렀지만 아무것도 되지 않았다. 윈도우에서는 (1) 콘솔을 자식째 끄다 실행기
자신도 죽었고 (2) 한글 폴더 이름에서 출력 해독이 깨져 실행기가 죽었다.
"""
from __future__ import annotations

import importlib.util
import json
import signal
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1] / "tools"


@pytest.fixture
def launcher(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("hangeul_launcher_under_test", TOOLS / "launcher.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    root = tmp_path / "root"
    (root / "install" / "modules").mkdir(parents=True)
    (root / "install" / "robots").mkdir(parents=True)
    (root / "data").mkdir()
    monkeypatch.setattr(mod, "ROOT", root)
    monkeypatch.setattr(mod, "RUN_DIR", root / "data" / "run")
    monkeypatch.setattr(mod, "REPORT", root / "data" / "run" / "last_report.json")
    monkeypatch.setattr(mod, "MODULE_DIR", root / "install" / "modules")
    monkeypatch.setattr(mod, "ROBOT_DIR", root / "install" / "robots")
    return mod


def _write(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _arm(launcher, module_id, **extra):
    _write(launcher.MODULE_DIR / f"{module_id}.json",
           {"module_id": module_id, "module_class": "arm", **extra})


def _robot(launcher, rid, modules, port, name=None):
    _write(launcher.ROBOT_DIR / f"{rid}.json",
           {"instance_id": rid, "display_name": name or rid, "modules": modules,
            "runtime_url": f"http://127.0.0.1:{port}"})


def test_robots_are_grouped_by_runtime_and_examples_are_skipped(launcher):
    _arm(launcher, "arm_omx")
    _arm(launcher, "arm_mycobot")
    _robot(launcher, "a", ["arm_omx"], 8601, "로봇1")
    _robot(launcher, "b", ["arm_omx"], 8601, "로봇1-별칭")
    _robot(launcher, "c", ["arm_mycobot"], 8601, "잘못 묶인 로봇")
    _write(launcher.ROBOT_DIR / "arm.example.json",
           {"instance_id": "example", "modules": ["arm_omx"], "runtime_url": "http://127.0.0.1:8609"})
    groups, problems = launcher.plan()
    assert [(g["port"], g["module"], g["robots"]) for g in groups] == [(8601, "arm_omx", ["로봇1", "로봇1-별칭"])]
    assert any("잘못 묶인 로봇" in p for p in problems)          # 같은 포트에 다른 팔은 말한다


def test_device_is_found_by_usb_identity_not_by_number(launcher, monkeypatch):
    desc = {"usb_ids": [{"vid": "0403", "pid": "6014"}], "device": {"linux": "/dev/ttyUSB0", "windows": "COM3"}}
    monkeypatch.setattr(launcher, "_stable", lambda d: d)
    monkeypatch.setattr(launcher, "_serial_ports", lambda: [("/dev/ttyUSB0", 0x10C4, 0xEA60),
                                                            ("/dev/ttyUSB1", 0x0403, 0x6014)])
    assert launcher.find_device(desc) == "/dev/ttyUSB1"
    # 신원을 아는 부품이 안 보이면 번호로 짐작하지 않는다 — 남의 장치를 열 수 있다
    monkeypatch.setattr(launcher, "_serial_ports", lambda: [("/dev/ttyUSB0", 0x10C4, 0xEA60)])
    assert launcher.find_device(desc) == ""


def test_missing_device_is_reported_with_a_reason(launcher, monkeypatch):
    _arm(launcher, "arm_omx", usb_ids=[{"vid": "0403", "pid": "6014"}])
    _robot(launcher, "a", ["core_a", "arm_omx"], 8601, "로봇1")
    monkeypatch.setattr(launcher, "_serial_ports", lambda: [])
    monkeypatch.setattr(launcher, "_get", lambda url, timeout=2.0: None)
    monkeypatch.setattr(launcher, "wsl_attach", lambda desc: "USB 장치가 보이지 않습니다 — 케이블")
    spawned = []
    monkeypatch.setattr(launcher, "_spawn", lambda *a, **k: spawned.append(a))
    monkeypatch.setattr(launcher, "start_console", lambda: {"state": "started", "url": "x"})
    report = launcher.up("start")
    assert not spawned                               # 없는 장치로 띄우지 않는다
    assert report["ok"] is False
    assert report["runtimes"][0]["state"] == "no_device"
    assert "케이블" in report["runtimes"][0]["message"]
    assert json.loads(launcher.REPORT.read_text(encoding="utf-8"))["runtimes"][0]["state"] == "no_device"


def test_reset_keeps_the_emergency_stop_but_clears_what_dead_processes_left(launcher, monkeypatch):
    state = launcher.ROOT / "data" / "safety_state_arm_omx.json"
    _write(state, {"estop_latched": True, "estop_reason": "사람이 누름", "disconnect_latched": True,
                   "disconnect_reason": "USB", "paused": True, "away_mode": True})
    leases = launcher.ROOT / "data" / "leases"
    leases.mkdir()
    _write(leases / "lease_x.json", {"holder": "console"})
    launcher.clear_stuck_state()
    after = json.loads(state.read_text(encoding="utf-8"))
    assert after["estop_latched"] is True and after["estop_reason"] == "사람이 누름"
    assert after["away_mode"] is True                # 사람이 켠 설정은 그대로
    assert after["disconnect_latched"] is False and after["paused"] is False
    assert not list(leases.glob("*.json"))


def test_kill_waits_and_then_forces(launcher, monkeypatch):
    if launcher.IS_WINDOWS:
        pytest.skip("POSIX 신호 경로")
    sent = []
    monkeypatch.setattr(launcher.os, "kill", lambda pid, sig: sent.append(sig))
    monkeypatch.setattr(launcher, "_alive", lambda pid: True)       # TERM 에도 안 죽는다
    monkeypatch.setattr(launcher.time, "sleep", lambda s: None)
    launcher._kill(1234)
    assert sent == [signal.SIGTERM, signal.SIGKILL]


def test_windows_kill_does_not_take_the_launcher_down_with_the_console(launcher, monkeypatch):
    # 화면이 띄운 실행기는 콘솔의 자식이다. /T 로 콘솔을 끄면 실행기도 죽었다.
    calls = []
    monkeypatch.setattr(launcher, "IS_WINDOWS", True)
    monkeypatch.setattr(launcher, "_run_text", lambda args, timeout=15: calls.append(args) or "")
    launcher._kill(42)
    assert calls == [["taskkill", "/PID", "42", "/F"]]


def test_command_output_in_a_non_utf8_encoding_does_not_crash(launcher, monkeypatch):
    # 한국어 윈도우는 CP949 로 답한다. 한글 폴더 이름에서 실행기가 죽었었다.
    class Done:
        stdout = "C:\\Users\\홍길동\\한글 로봇\\python.exe".encode("cp949")
    monkeypatch.setattr(launcher.subprocess, "run", lambda *a, **k: Done())
    text = launcher._run_text(["powershell"])
    assert isinstance(text, str) and "python.exe" in text


def test_a_crash_still_leaves_a_report(launcher, monkeypatch):
    def boom(action):
        raise RuntimeError("터짐")
    monkeypatch.setattr(launcher, "up", boom)
    with pytest.raises(RuntimeError):
        launcher.main(["start", "--no-browser"])
    report = json.loads(launcher.REPORT.read_text(encoding="utf-8"))
    assert report["ok"] is False and "터짐" in report["problems"][0]


def test_console_restart_hands_off_to_the_launcher(client, monkeypatch):
    """화면의 '완전 초기화'는 Reset.bat · run.sh 와 같은 실행기를 부른다."""
    import os
    import subprocess
    from hangeul_console import app as app_mod

    launched = {}
    monkeypatch.setattr(subprocess, "Popen",
                        lambda args, **kw: launched.update(args=args, kw=kw) or object())
    answer = client.post("/api/server-restart", json={"confirmed": True}).json()
    assert answer["success"], answer
    assert launched["args"][1:3] == [str(app_mod.LAUNCHER), "reset"]
    # 부모(콘솔)를 끄는 일이므로 떨어져 나간 자식이어야 한다
    if os.name == "nt":
        assert launched["kw"]["creationflags"] & subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        assert launched["kw"].get("start_new_session") is True
    assert launched["kw"]["stdout"] is not subprocess.DEVNULL   # 출력은 버리지 않는다


def test_adding_a_robot_starts_its_runtime(client, monkeypatch, tmp_path):
    from hangeul_console import app as app_mod
    try:
        from conftest import install_fixture_robots
        install_fixture_robots(monkeypatch, tmp_path)
    except ImportError:
        pass
    called = []
    monkeypatch.setattr(app_mod, "_ensure_runtimes", lambda: called.append(True))
    answer = client.post("/api/robots/add", json={"model": "arm_omx", "display_name": "새 팔"}).json()
    assert answer["success"], answer
    assert called == [True]
    client.delete(f"/api/robots/{answer['robot_id']}")


def test_serial_open_failure_is_not_ready(launcher, monkeypatch):
    _arm(launcher, "arm_omx")
    monkeypatch.setattr(launcher, "_get", lambda *a, **kw: None)
    monkeypatch.setattr(launcher, "find_device", lambda d: "/dev/fake")
    monkeypatch.setattr(launcher, "_spawn", lambda *a, **kw: 0)
    monkeypatch.setattr(launcher, "_wait_json", lambda *a: {"simulated": True, "simulate_reason": "open failed"})
    row = launcher.start_runtime({"port": 8601, "module": "arm_omx", "robots": ["a"]})
    assert row["state"] == "started" and row["readiness"] == "disconnected" and not row["ready"]
    assert not launcher.recover_runtime(row)["ready"]


def test_reset_calls_hardware_recovery_and_reports_failed_readiness(launcher, monkeypatch):
    import io
    calls = []
    def response(request, timeout):
        calls.append((request.full_url, json.loads(request.data)))
        return io.BytesIO(json.dumps({"success": False, "ready": False, "readiness": "fault_remaining", "error": "J12 error 32"}).encode())
    monkeypatch.setattr(launcher.urllib.request, "urlopen", response)
    row = launcher.recover_runtime({"port": 8601, "state": "started", "readiness": "not_checked", "message": "connected"})
    assert calls[0][0].endswith('/api/recover-after-restart') and calls[0][1]["confirmed"]
    assert not row["ready"] and row["readiness"] == "fault_remaining"
    assert "J12" in row["message"]


def test_reset_report_separates_process_start_and_hardware_ready(launcher, monkeypatch):
    monkeypatch.setattr(launcher, "stop_all", lambda: [])
    monkeypatch.setattr(launcher, "plan", lambda: ([{}], []))
    monkeypatch.setattr(launcher, "start_runtime", lambda g: {"state": "started", "ready": False})
    monkeypatch.setattr(launcher, "recover_runtime", lambda r: r)
    monkeypatch.setattr(launcher, "start_console", lambda: {"state": "started"})
    report = launcher.up("reset")
    assert report["processes_started"] and not report["robots_ready"] and not report["ok"]


def test_start_and_ensure_never_reboot_motors(launcher, monkeypatch):
    monkeypatch.setattr(launcher, "plan", lambda: ([{}], []))
    monkeypatch.setattr(launcher, "start_runtime", lambda g: {"state": "started", "ready": False})
    monkeypatch.setattr(launcher, "start_console", lambda: {"state": "started"})
    def forbidden(row):
        raise AssertionError("start/ensure must not reboot hardware")
    monkeypatch.setattr(launcher, "recover_runtime", forbidden)
    assert launcher.up("start")["ok"]
    assert launcher.up("ensure")["ok"]


def test_restart_requires_confirmation(client, monkeypatch):
    import subprocess
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: pytest.fail("must not launch"))
    assert not client.post("/api/server-restart", json={}).json()["success"]


# ── ROS 2 부품 (FAIRINO 시뮬레이션 20261108) ──────────────────────
# 장치가 USB가 아니라 컨트롤러 이름이라 USB 찾기로는 늘 '장치 없음'이었다.
# 윈도우의 run_wsl.bat은 비대화형 셸이라 ~/.bashrc의 ROS source도 닿지 않는다.
def _ros2_arm(launcher, tmp_path, *, simulator=True, setup_exists=True):
    setup = tmp_path / "setup.bash"
    if setup_exists:
        setup.write_text("", encoding="utf-8")
    ros2 = {"setup": [str(setup)]}
    if simulator:
        ros2["simulator"] = {"command": "ros2 launch fake demo.launch.py", "ready_timeout_s": 2}
    _arm(launcher, "arm_fr", device={"linux": "/fr_controller"}, ros2=ros2)
    _robot(launcher, "fr", ["core_a", "arm_fr"], 8606, "FR5")
    return str(setup)


@pytest.fixture
def ros2_env(launcher, monkeypatch):
    monkeypatch.setattr(launcher, "IS_WINDOWS", False)
    monkeypatch.setattr(launcher, "start_console", lambda: {"state": "started", "url": "x"})
    monkeypatch.setattr(launcher, "time", type("T", (), {"monotonic": staticmethod(__import__("time").monotonic),
                                                          "sleep": staticmethod(lambda s: None)}))
    spawned = []
    monkeypatch.setattr(launcher, "_spawn", lambda name, args, log, pp: spawned.append((name, args)) or 1)
    return spawned


def test_ros2_arm_without_its_environment_is_reported_not_spawned(launcher, tmp_path, monkeypatch, ros2_env):
    _ros2_arm(launcher, tmp_path, setup_exists=False)
    monkeypatch.setattr(launcher, "_get", lambda url, timeout=2.0: None)
    row = launcher.up("start")["runtimes"][0]
    assert row["state"] == "no_device"
    assert "ROS 2 환경" in row["message"]
    assert ros2_env == []


def test_ros2_arm_starts_its_simulator_then_a_runtime_inside_ros(launcher, tmp_path, monkeypatch, ros2_env):
    setup = _ros2_arm(launcher, tmp_path)
    answers = iter([False, False, True])           # 처음엔 없음 → 시뮬레이터가 뜨며 생김
    monkeypatch.setattr(launcher, "_ros2_action_ready", lambda files, device: next(answers))
    up = {"simulated": False, "device": "/fr_controller"}
    monkeypatch.setattr(launcher, "_get", lambda url, timeout=2.0: None)
    monkeypatch.setattr(launcher, "_wait_json", lambda url, s: up)
    row = launcher.up("start")["runtimes"][0]
    assert row["state"] == "started" and row["simulator"] == "started"
    (sim_name, sim_args), (rt_name, rt_args) = ros2_env
    assert sim_name == "ros2_sim_8606" and "ros2 launch fake demo.launch.py" in sim_args[-1]
    assert rt_name == "runtime_8606"
    assert rt_args[:2] == ["bash", "-c"] and f"source {setup}" in rt_args[2]
    assert "--device /fr_controller" in rt_args[2]


def test_ros2_arm_uses_a_controller_that_is_already_up(launcher, tmp_path, monkeypatch, ros2_env):
    _ros2_arm(launcher, tmp_path)
    monkeypatch.setattr(launcher, "_ros2_action_ready", lambda files, device: True)
    monkeypatch.setattr(launcher, "_get", lambda url, timeout=2.0: None)
    monkeypatch.setattr(launcher, "_wait_json", lambda url, s: {"simulated": False})
    launcher.up("start")
    assert [name for name, _ in ros2_env] == ["runtime_8606"]   # 시뮬레이터를 겹쳐 띄우지 않는다


def test_ros2_arm_without_a_simulator_does_not_invent_one(launcher, tmp_path, monkeypatch, ros2_env):
    _ros2_arm(launcher, tmp_path, simulator=False)
    monkeypatch.setattr(launcher, "_ros2_action_ready", lambda files, device: False)
    monkeypatch.setattr(launcher, "_get", lambda url, timeout=2.0: None)
    row = launcher.up("start")["runtimes"][0]
    assert row["state"] == "no_device" and "/fr_controller" in row["message"]
    assert ros2_env == []


def test_a_simulator_that_never_answers_fails_with_its_log(launcher, tmp_path, monkeypatch, ros2_env):
    _ros2_arm(launcher, tmp_path)
    monkeypatch.setattr(launcher, "_ros2_action_ready", lambda files, device: False)
    monkeypatch.setattr(launcher, "_get", lambda url, timeout=2.0: None)
    row = launcher.up("start")["runtimes"][0]
    assert row["state"] == "failed" and "ros2_sim_arm_fr.log" in row["message"]
    assert [name for name, _ in ros2_env] == ["ros2_sim_8606"]   # 런타임은 띄우지 않는다


def test_stop_takes_down_only_the_simulator_it_started(launcher, monkeypatch):
    launcher.RUN_DIR.mkdir(parents=True)
    (launcher.RUN_DIR / "ros2_sim_8606.pid").write_text(json.dumps({"pid": 4242}))
    (launcher.RUN_DIR / "ros2_sim_8607.pid").write_text(json.dumps({"pid": 4343}))
    cmds = {4242: "/usr/bin/python3 /opt/ros/jazzy/bin/ros2 launch x demo.launch.py",
            4343: "vim notes.txt"}                     # pid가 재사용돼 남의 프로그램이 됐다
    monkeypatch.setattr(launcher, "_cmdline", lambda pid: cmds.get(pid, ""))
    alive = {4242, 4343}
    monkeypatch.setattr(launcher, "_alive", lambda pid: pid in alive)
    sent = []
    monkeypatch.setattr(launcher.os, "killpg", lambda pid, sig: (sent.append((pid, sig)), alive.discard(pid)))
    assert launcher.stop_ros2_simulators() == [4242]
    assert sent == [(4242, signal.SIGINT)]
    assert not list(launcher.RUN_DIR.glob("ros2_sim_*.pid"))
