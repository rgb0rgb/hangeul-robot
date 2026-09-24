"""Real Gazebo effort simulation; synthetic torque cases, no physical hardware.

source /opt/ros/jazzy/setup.bash
python3 tools/verify_actuator_physics.py --report docs/ACTUATOR_PHYSICS_VALIDATION.json
"""
import argparse
import csv
from concurrent.futures import ThreadPoolExecutor
import json
import hashlib
import math
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime

from actuator_bench import DEFAULT_PROFILE, JOINT, generate
from verify_ros2_connection import api, port

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime/src"))


def stop(proc):
    if proc.poll() is None:
        os.killpg(proc.pid, signal.SIGINT)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=5)


def run_case(folder, profile, case):
    from hangeul_runtime.hardware.ros2_transport import Ros2Transport
    from sensor_msgs.msg import JointState
    from control_msgs.msg import JointTrajectoryControllerState
    from rclpy.qos import qos_profile_sensor_data
    _, model = generate(folder, profile, case)
    env = dict(os.environ, BENCH_FOLDER=str(folder), GZ_PARTITION="hangeul_bench_" + folder.name)
    rows, commands = [], []
    log = (folder / "gazebo.log").open("w")
    proc = subprocess.Popen(["ros2", "launch", str(ROOT / "tools/gazebo_actuator_bench.launch.py")],
                            env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    transport = None
    children, logs = [], []
    def service(name, listen_port):
        stream = (folder / (name + ".log")).open("w")
        logs.append(stream)
        child = subprocess.Popen([sys.executable, str(ROOT / "tools/verify_ros2_connection.py"),
                                  "--child", name, "--folder", str(folder), "--port", str(listen_port)],
                                 env=env, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        children.append(child)
        url = f"http://127.0.0.1:{listen_port}"
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                api(url, "/api/status" if name == "console" else "/api/estop-status", timeout=1)
                return url
            except Exception:
                if child.poll() is not None:
                    break
                time.sleep(0.2)
        raise RuntimeError(f"{name} failed to start; inspect {folder}")
    try:
        transport = Ros2Transport("/joint_trajectory_controller", [JOINT],
                                  {"connect_timeout_s": 65, "goal_timeout_margin_s": 12, "state_timeout_s": 2})
        def sample(msg):
            if JOINT in msg.name:
                i = msg.name.index(JOINT)
                rows.append([msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9,
                             msg.position[i], msg.velocity[i] if i < len(msg.velocity) else None,
                             msg.effort[i] if i < len(msg.effort) else None])
        subscription = transport.node.create_subscription(JointState, "/joint_states", sample, qos_profile_sensor_data)
        def controller_sample(msg):
            if JOINT in msg.joint_names:
                i = msg.joint_names.index(JOINT)
                if i < len(msg.output.effort):
                    commands.append([msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9,
                                     msg.output.effort[i], msg.reference.positions[i], msg.feedback.positions[i]])
        controller_subscription = transport.node.create_subscription(
            JointTrajectoryControllerState, "/joint_trajectory_controller/controller_state",
            controller_sample, qos_profile_sensor_data)
        (folder / "modules").mkdir()
        (folder / "robots").mkdir()
        shutil.copy2(ROOT / "install/modules/core_a.json", folder / "modules")
        descriptor = json.loads((ROOT / "install/modules/arm_ros2.json").read_text())
        descriptor["joints"] = [{"id": JOINT, "role": "joint"}]
        descriptor["ros2"].update(evidence_kind="virtual", min_duration_s=2.0, goal_timeout_margin_s=12.0)
        (folder / "modules/arm_ros2.json").write_text(json.dumps(descriptor))
        (folder / "limits.json").write_text(json.dumps({JOINT: [-85, 95]}))
        rt = service("runtime", port())
        co = service("console", port())
        registered = api(co, "/api/robots/add", {"instance_id": "physics_bench", "modules": ["core_a", "arm_ros2"],
                                                "display_name": "Gazebo effort bench", "runtime_url": rt})
        saved = api(co, "/api/save-pose", {"skill_id": "loaded_pose", "name_en": "Loaded pose", "targets": {JOINT: -10000}})
        inputs = {k: True for k in ("operator_present", "workspace_clear", "manual_stop_available", "estop_ready")}
        time.sleep(0.5)
        rows.clear()
        commands.clear()
        result = api(co, "/api/execute-actual", {"skill_id": "loaded_pose", "speed": "slow", "safety_inputs": inputs}, timeout=45)
        time.sleep(0.3)
        transport.node.destroy_subscription(subscription)
        transport.node.destroy_subscription(controller_subscription)
        cap = model["parameters"]["torque_limit_nm"]
        # Broadcaster maps the plugin's post-clamp applied_effort to JointState.effort.
        # Controller output remains the request BEFORE the hardware boundary clamp.
        efforts = [abs(r[3]) for r in rows if r[3] is not None]
        error = abs(math.degrees(transport.joint_positions()[JOINT]) + 10)
        checks = {"state_samples": len(rows) > 50,
                  "simulation_clock_advances": len(rows) > 1 and rows[-1][0] > rows[0][0],
                  "console_registration": bool(registered.get("success")), "pose_saved": bool(saved.get("success")),
                  "virtual_evidence": result.get("evidence_kind") == "virtual" and result.get("actual_hardware_called") is False,
                  "effort_within_limit": bool(efforts) and max(efforts) <= cap + 0.01,
                  "expected_outcome": bool(result.get("success")) == (case == "adequate"),
                  "position_outcome": error < 0.5 if case == "adequate" else error > 5}
        if case == "insufficient":
            checks["saturation_observed"] = bool(efforts) and max(efforts) >= 0.98 * cap
            checks["action_aborted_for_goal_tolerance"] = result.get("trajectory", {}).get("error_code") == -5
        integration = {}
        last = [r for r in rows if r[0] >= rows[-1][0] - 0.2] if rows else []
        mean_hold_torque = sum(abs(r[3]) for r in last) / len(last) if last else 0.0
        expected_hold_torque = (sum(model["horizontal_gravity_torque_nm"] * math.cos(r[1]) for r in last)
                                / len(last)) if last else 0.0
        if case == "adequate":
            checks["static_gravity_consistency"] = abs(mean_hold_torque - expected_hold_torque) < 0.3
            api(co, "/api/save-pose", {"skill_id": "second_pose", "name_en": "Second pose", "targets": {JOINT: -20000}})
            api(co, "/api/save-sequence", {"name": "Physics two poses", "skill_ids": ["loaded_pose", "second_pose"]})
            started = api(co, "/api/hangeul/multi-execute", {"robot_ids": ["physics_bench"], "safety_inputs": inputs})
            deadline = time.monotonic() + 35
            while time.monotonic() < deadline:
                row = api(co, "/api/robots")["robots"][0]
                if row["multi_run"]["state"] in ("완료", "실패", "취소"):
                    break
                time.sleep(0.2)
            checks["saved_sequence_completed"] = bool(started.get("success")) and row["multi_run"]["state"] == "완료"
            integration["sequence"] = row["multi_run"]
            with ThreadPoolExecutor(max_workers=1) as pool:
                move = pool.submit(api, rt, "/api/move-to", {"joint_id": JOINT, "target": 20000, "velocity": 10})
                time.sleep(0.5)
                stopped = api(co, "/api/estop", {"robot_id": "physics_bench"})
                ended = move.result(timeout=15)
                checks["moving_action_canceled"] = ended.get("verdict") == "CANCELED" and not ended.get("success")
                integration["cancel"] = {"stop": stopped, "move": ended}
            blocked = api(rt, "/api/move-to", {"joint_id": JOINT, "target": 0})
            checks["new_move_blocked_after_stop"] = blocked.get("reason_code") == "estop_latched"
        return {"model": model, "result": result, "final_error_deg": error,
                "integration": integration,
                "mean_final_applied_torque_nm": mean_hold_torque,
                "analytic_final_gravity_torque_nm": expected_hold_torque,
                "peak_applied_effort_nm": max(efforts, default=0),
                "peak_requested_effort_nm": max((abs(r[1]) for r in commands), default=0), "samples": len(rows),
                "saturation_fraction": sum(v >= 0.98 * cap for v in efforts) / max(1, len(efforts)),
                "checks": checks, "passed": all(checks.values())}
    finally:
        for child in reversed(children):
            stop(child)
        for stream in logs:
            stream.close()
        if transport is not None:
            transport.close()
        stop(proc)
        log.close()
        with (folder / "samples.csv").open("w") as f:
            writer = csv.writer(f)
            writer.writerow(["simulation_seconds", "position_rad", "velocity_rad_s", "applied_effort_nm"])
            writer.writerows(rows)
        with (folder / "commands.csv").open("w") as f:
            writer = csv.writer(f)
            writer.writerow(["simulation_seconds", "commanded_effort_nm", "reference_rad", "feedback_rad"])
            writer.writerows(commands)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--report", type=Path, default=Path("/tmp/actuator_physics_report.json"))
    args = parser.parse_args()
    os.environ.update(ROS_DOMAIN_ID="174", ROS_AUTOMATIC_DISCOVERY_RANGE="LOCALHOST")
    folder = Path(tempfile.mkdtemp(prefix="hangeul_physics_"))
    report = {"evidence_kind": "gazebo_physics", "physical_hardware_tested": False,
              "artifact_directory": str(folder), "cases": {}, "passed": False,
              "generated_at": datetime.now().astimezone().isoformat(), "ros_distro": os.environ.get("ROS_DISTRO")}
    sources = [ROOT / "tools/actuator_bench.py", ROOT / "tools/verify_actuator_physics.py",
               ROOT / "tools/gazebo_actuator_bench.launch.py", ROOT / "simulation/hangeul_effort_limit/src/effort_limit.cpp"]
    report["source_sha256"] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    print("Artifacts:", folder, flush=True)
    try:
        build = folder / "plugin_build"
        with (folder / "build.log").open("w") as log:
            subprocess.run(["colcon", "--log-base", str(build / "log"), "build", "--base-paths",
                            str(ROOT / "simulation/hangeul_effort_limit"), "--build-base", str(build / "build"),
                            "--install-base", str(build / "install")], stdout=log, stderr=subprocess.STDOUT,
                           check=True, timeout=180)
        prefix = build / "install/hangeul_effort_limit"
        os.environ["AMENT_PREFIX_PATH"] = str(prefix) + os.pathsep + os.environ.get("AMENT_PREFIX_PATH", "")
        os.environ["LD_LIBRARY_PATH"] = str(prefix / "lib") + os.pathsep + os.environ.get("LD_LIBRARY_PATH", "")
        for case in ("adequate", "insufficient"):
            report["cases"][case] = run_case(folder / case, args.profile, case)
            c = report["cases"][case]
            print(case, "PASS" if c["passed"] else "FAIL", "error_deg=", round(c["final_error_deg"], 3),
                  "failed_checks=", [k for k, v in c["checks"].items() if not v], flush=True)
        report["passed"] = all(c["passed"] for c in report["cases"].values())
    finally:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        archive = args.report.resolve().with_suffix("")
        archive.mkdir(parents=True, exist_ok=True)
        shutil.copy2(args.profile, archive / "profile.json")
        if (folder / "build.log").exists():
            shutil.copy2(folder / "build.log", archive / "build.log")
        for case in ("adequate", "insufficient"):
            if (folder / case).exists():
                dest = archive / case
                dest.mkdir(exist_ok=True)
                for name in ("model.json", "bench.urdf", "controllers.yaml", "world.sdf", "samples.csv", "commands.csv", "gazebo.log", "runtime.log", "console.log"):
                    if (folder / case / name).exists():
                        shutil.copy2(folder / case / name, dest / name)
        report["artifact_directory"] = str(archive)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    if not report["passed"]:
        raise SystemExit("Physics validation failed; inspect report/logs")


if __name__ == "__main__":
    main()
