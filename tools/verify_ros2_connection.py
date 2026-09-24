"""Run a real DDS/JTC integration test using only mock hardware.

Usage after sourcing ROS Jazzy: python3 tools/verify_ros2_connection.py
All console assets, safety state, logs, and module overrides live in a new temp folder.
No serial device is opened. Processes started here are the only processes stopped here.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
for part in ("console/src", "runtime/src"):
    sys.path.insert(0, str(ROOT / part))


def api(base, path, payload=None, timeout=30):
    req = urllib.request.Request(base + path, data=None if payload is None else json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def child(mode, folder, listen_port):
    import uvicorn
    if mode == "console":
        from hangeul_console import app as c
        from hangeul_console.registry import Registry
        from hangeul_console.device_lease import LeaseBook
        c.MODULE_DIR = folder / "modules"
        c.ROBOT_CONFIG_DIR = folder / "robots"
        c.INSTANCE_DIR = folder / "instances"
        c.CONSOLE_STATE = folder / "console.json"
        c.TASK_PATH = folder / "tasks.json"
        c.leases = LeaseBook(folder / "leases")
        c.registry = Registry(c.MODULE_DIR, c.ROBOT_CONFIG_DIR)
        app = c.app
    else:
        from hangeul_runtime import server as r
        r.build("arm_ros2", "/joint_trajectory_controller", str(folder / "limits.json"),
                modules_dir=str(folder / "modules"), state_path=str(folder / "safety.json"))
        if r.CONFIG["adapter"] is None:
            raise RuntimeError(r.CONFIG["simulate_reason"])
        app = r.app
    uvicorn.run(app, host="127.0.0.1", port=listen_port, log_level="warning")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--child", choices=["console", "runtime"])
    parser.add_argument("--folder", type=Path)
    parser.add_argument("--port", type=int)
    parser.add_argument("--reuse-ros", action="store_true", help="Use domain 173 already launched by this task")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.child:
        child(args.child, args.folder, args.port)
        return
    folder = Path(tempfile.mkdtemp(prefix="hangeul_ros2_validation_"))
    print("Artifacts:", folder, flush=True)
    env = dict(os.environ, ROS_DOMAIN_ID="173", ROS_AUTOMATIC_DISCOVERY_RANGE="LOCALHOST",
               PYTHONPATH=os.pathsep.join([str(ROOT / "console/src"), str(ROOT / "runtime/src"),
                                         os.environ.get("PYTHONPATH", "")]))
    os.environ.update({k: env[k] for k in ("ROS_DOMAIN_ID", "ROS_AUTOMATIC_DISCOVERY_RANGE")})
    processes, logs = [], []
    report = {"evidence_kind": "virtual_ros2_control", "physical_hardware_tested": False,
              "artifact_directory": str(folder), "checks": {}}

    def launch(name, command):
        log = (folder / (name + ".log")).open("w")
        logs.append(log)
        proc = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                                start_new_session=True)
        processes.append(proc)
        return proc

    def stop(proc):
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGINT)
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=3)

    def ready(base, path):
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            try:
                return api(base, path, timeout=1)
            except Exception:
                time.sleep(0.2)
        raise RuntimeError(f"Service unavailable: {base}{path}; inspect {folder}")

    def check(name, condition, evidence):
        report["checks"][name] = {"passed": bool(condition), "evidence": evidence}
        print(name + ": " + ("PASS" if condition else "FAIL"), flush=True)
        assert condition, (name, evidence)

    try:
        ros = None if args.reuse_ros else launch("ros", ["ros2", "launch", str(ROOT / "tools/ros2_mock_arm.launch.py")])
        (folder / "modules").mkdir()
        (folder / "robots").mkdir()
        for name in ("core_a", "arm_ros2"):
            shutil.copy2(ROOT / "install/modules" / (name + ".json"), folder / "modules")
        descriptor = json.loads((folder / "modules/arm_ros2.json").read_text())
        names = [j["id"] for j in descriptor["joints"]]
        descriptor["ros2"] = {"joint_states_topic": "/joint_states", "evidence_kind": "virtual",
                              "connect_timeout_s": 20, "state_timeout_s": 1.0,
                              "goal_timeout_margin_s": 2.0, "max_velocity_rad_s": 1.0}
        descriptor["safety"] = {"limits": {j: [-90000, 90000] for j in names}}
        runtime_port, console_port = port(), port()
        rt, co = f"http://127.0.0.1:{runtime_port}", f"http://127.0.0.1:{console_port}"
        descriptor["runtime_url"] = rt
        (folder / "modules/arm_ros2.json").write_text(json.dumps(descriptor))
        (folder / "limits.json").write_text(json.dumps({j: [-90, 90] for j in names}))
        runtime_cmd = [sys.executable, str(Path(__file__).resolve()), "--child", "runtime",
                       "--folder", str(folder), "--port", str(runtime_port)]
        runtime_proc = launch("runtime", runtime_cmd)
        ready(rt, "/api/estop-status")
        launch("console", [sys.executable, str(Path(__file__).resolve()), "--child", "console",
                           "--folder", str(folder), "--port", str(console_port)])
        ready(co, "/api/status")
        result = api(co, "/api/robots/add", {"instance_id": "ros_probe", "display_name": "ROS virtual arm",
                                       "modules": ["core_a", "arm_ros2"], "runtime_url": rt})
        check("console_registration", result.get("success"), result)
        observed = api(rt, "/api/read-pose")
        check("fresh_named_joint_state", observed.get("success") and bool(observed.get("present")), observed)
        for key, values in [("pose_a", [10000, -5000, 0, 0]), ("pose_b", [20000, 10000, -10000, 5000])]:
            result = api(co, "/api/save-pose", {"skill_id": key, "name_en": key, "targets": dict(zip(names, values))})
            check("save_" + key, result.get("success"), result)
        inputs = {k: True for k in ("operator_present", "workspace_clear", "manual_stop_available", "estop_ready")}
        for key in ("pose_a", "pose_b"):
            result = api(co, "/api/execute-actual", {"skill_id": key, "speed": "slow", "safety_inputs": inputs})
            check("console_execute_" + key, result.get("success") and result.get("trajectory", {}).get("result_ok"), result)
        result = api(co, "/api/save-sequence", {"name": "virtual_two_poses", "skill_ids": ["pose_a", "pose_b"]})
        check("save_sequence", result.get("success"), result)
        result = api(co, "/api/hangeul/multi-execute", {"robot_ids": ["ros_probe"], "safety_inputs": inputs})
        check("start_sequence", result.get("success"), result)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            row = api(co, "/api/robots")["robots"][0]
            if row["multi_run"]["state"] in ("완료", "실패", "취소"):
                break
            time.sleep(0.2)
        check("complete_sequence", row["multi_run"]["state"] == "완료", row["multi_run"])
        result = api(rt, "/api/move-to", {"joint_id": names[0], "target": 120000, "velocity": 20})
        check("range_blocked", result.get("reason_code") == "out_of_range", result)
        result = api(rt, "/api/move-to", {"joint_id": "missing_joint", "target": 1})
        check("unknown_joint_blocked", result.get("reason_code") == "unknown_joint", result)

        with ThreadPoolExecutor(max_workers=1) as pool:
            moving = pool.submit(api, rt, "/api/move-to", {"joint_id": names[0], "target": -70000, "velocity": 10})
            time.sleep(0.8)
            started = time.monotonic()
            stopped = api(co, "/api/estop", {"robot_id": "ros_probe"}, timeout=6)
            elapsed = time.monotonic() - started
            ended = moving.result(timeout=8)
            check("cancel_inflight", elapsed < 5 and not ended.get("success") and ended.get("verdict") == "CANCELED",
                  {"stop_seconds": elapsed, "stop": stopped, "move": ended})
        result = api(rt, "/api/move-to", {"joint_id": names[0], "target": 0})
        check("estop_blocks_new_move", result.get("reason_code") == "estop_latched", result)
        stop(runtime_proc)
        runtime_proc = launch("runtime_restart", runtime_cmd)
        result = ready(rt, "/api/estop-status")
        check("restart_preserves_estop", result.get("estop_active"), result)
        result = api(rt, "/api/estop-reset", {"operator": "virtual-test", "confirmed": True})
        check("explicit_recovery", result.get("success"), result)
        result = api(co, "/api/execute-actual", {"skill_id": "pose_a", "safety_inputs": inputs})
        check("execute_after_recovery", result.get("success"), result)

        # Exercise actual ROS action rejection, not just a fake-node policy test.
        from hangeul_runtime.hardware.ros2_transport import Ros2Transport
        transport = Ros2Transport("/joint_trajectory_controller", names, descriptor["ros2"])
        try:
            result = transport.send_trajectory(joint_names=["missing_joint"], positions=[0.0],
                                               time_from_start_s=0.2, label="invalid")
            check("ros_goal_rejected", not result.get("accepted"), result)
            # Inject a client result-wait timeout while a real JTC action is active.
            # This tests cancellation/inhibition, not a measured network-delay limit.
            normal_wait = transport._wait
            calls = 0
            def timeout_on_result(future, timeout):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise TimeoutError("Injected result timeout")
                return normal_wait(future, timeout)
            transport._wait = timeout_on_result
            result = transport.send_trajectory(joint_names=names, positions=[0.0] * len(names),
                                               time_from_start_s=2.0, label="timeout_probe")
            transport._wait = normal_wait
            check("injected_timeout_cancels", result.get("timed_out") and not result.get("result_ok"), result)
            result = transport.send_trajectory(joint_names=names, positions=[0.0] * len(names),
                                               time_from_start_s=0.2, label="must_not_restart")
            check("timeout_requires_recovery", result.get("canceled") and not result.get("accepted"), result)
            deadline = time.monotonic() + 5
            while transport._active is not None and time.monotonic() < deadline:
                time.sleep(0.02)
            check("timeout_cancel_completed", transport._active is None,
                  {"active_goal_cleared": transport._active is None})
            if ros is not None:
                stop(ros)
                time.sleep(1.3)
                try:
                    transport.joint_positions()
                    stale = "incorrectly accepted stale data"
                except RuntimeError as exc:
                    stale = str(exc)
                check("stale_state_rejected", "stale" in stale and "incorrectly" not in stale, stale)
        finally:
            transport.close()
        report["passed"] = True
    finally:
        for proc in reversed(processes):
            stop(proc)
        for log in logs:
            log.close()
        target = args.report or folder / "report.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print("Report:", target, flush=True)


if __name__ == "__main__":
    main()
