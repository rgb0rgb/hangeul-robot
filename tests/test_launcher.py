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
    answer = client.post("/api/server-restart", json={}).json()
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
