"""Generate a manufacturer-neutral, effort-controlled Gazebo pendulum bench."""
import json
import math
from pathlib import Path

import yaml

JOINT = "bench_joint"
DEFAULT_PROFILE = Path(__file__).resolve().parents[1] / "simulation/actuator_bench.json"


def generate(folder, profile_path=DEFAULT_PROFILE, case="adequate", *, plugin_path=None):
    if plugin_path is None:
        from ament_index_python.packages import get_package_prefix
        plugin_path = Path(get_package_prefix("gz_ros2_control")) / "lib/libgz_ros2_control-system.so"
    plugin = Path(plugin_path)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    profile = json.loads(Path(profile_path).read_text())
    p = {**profile["plant"], **profile["cases"][case]}
    for key in ("length_m", "link_mass_kg", "torque_limit_nm"):
        if not math.isfinite(p[key]) or p[key] <= 0:
            raise ValueError(f"{key} must be finite and positive")
    for key in ("payload_mass_kg", "damping_nms_rad"):
        if not math.isfinite(p[key]) or p[key] < 0:
            raise ValueError(f"{key} must be finite and nonnegative")
    if profile["controller"].get("ff_velocity_scale") != 0.0:
        raise ValueError("This torque-capped bench requires ff_velocity_scale=0; feedforward bypasses PID clipping")
    if not math.isfinite(p["initial_position_rad"]) or not -1.5 < p["initial_position_rad"] < 1.7:
        raise ValueError("Initial position must be inside the joint limits")
    length, mass, payload, torque = (p[k] for k in
        ("length_m", "link_mass_kg", "payload_mass_kg", "torque_limit_nm"))
    # Uniform slender link plus compact payload, reduced to one equivalent rigid body.
    total = mass + payload
    center = (mass * length / 2 + payload * length) / total
    inertia_pivot = mass * length**2 / 3 + payload * length**2 + total * 0.04**2 / 12
    inertia_com = inertia_pivot - total * center**2
    gains = {**profile["controller"], "u_clamp_min": -torque, "u_clamp_max": torque}
    config = folder / "controllers.yaml"
    config.write_text(yaml.safe_dump({
        "controller_manager": {"ros__parameters": {
            "update_rate": 200,
            "joint_state_broadcaster": {"type": "joint_state_broadcaster/JointStateBroadcaster"},
            "joint_trajectory_controller": {"type": "joint_trajectory_controller/JointTrajectoryController"}}},
        "joint_state_broadcaster": {"ros__parameters": {
            "map_interface_to_joint_state": {"effort": "applied_effort"}}},
        "joint_trajectory_controller": {"ros__parameters": {
            "joints": [JOINT], "command_interfaces": ["effort"],
            "state_interfaces": ["position", "velocity"], "gains": {JOINT: gains},
            "constraints": {"goal_time": 8.0, "stopped_velocity_tolerance": 0.02,
                            JOINT: {"trajectory": 0.0, "goal": 0.006}}}}
    }))
    urdf = f'''<robot name="actuator_bench">
      <link name="world"/><link name="base"><inertial><mass value="1"/>
        <inertia ixx="0.01" iyy="0.01" izz="0.01" ixy="0" ixz="0" iyz="0"/></inertial></link>
      <joint name="anchor" type="fixed"><parent link="world"/><child link="base"/></joint>
      <link name="lever">
        <inertial><origin xyz="{center} 0 0"/><mass value="{total}"/>
          <inertia ixx="0.001" iyy="{inertia_com}" izz="{inertia_com}" ixy="0" ixz="0" iyz="0"/></inertial>
        <visual><origin xyz="{length/2} 0 0"/><geometry><box size="{length} 0.04 0.04"/></geometry></visual>
        <collision><origin xyz="{length/2} 0 0"/><geometry><box size="{length} 0.04 0.04"/></geometry></collision>
      </link>
      <joint name="{JOINT}" type="revolute">
        <parent link="base"/><child link="lever"/><origin xyz="0 0 1"/><axis xyz="0 1 0"/>
        <limit lower="-1.5" upper="1.7" effort="{torque}" velocity="2"/>
        <dynamics damping="{p['damping_nms_rad']}" friction="0.0"/>
      </joint>
      <ros2_control name="PhysicsBench" type="system">
        <hardware><plugin>hangeul_effort_limit/EffortLimitSystem</plugin></hardware>
        <joint name="{JOINT}">
          <command_interface name="effort"><param name="min">{-torque}</param><param name="max">{torque}</param></command_interface>
          <state_interface name="position"><param name="initial_value">{p['initial_position_rad']}</param></state_interface>
          <state_interface name="velocity"/><state_interface name="effort"/>
        </joint>
      </ros2_control>
      <gazebo><plugin filename="{plugin}" name="gz_ros2_control::GazeboSimROS2ControlPlugin">
        <parameters>{config}</parameters>
      </plugin></gazebo>
    </robot>'''
    (folder / "bench.urdf").write_text(urdf)
    (folder / "world.sdf").write_text('''<sdf version="1.9"><world name="actuator_bench">
      <gravity>0 0 -9.81</gravity><physics name="physics" type="ignored">
        <max_step_size>0.001</max_step_size><real_time_factor>1.0</real_time_factor></physics>
      <plugin filename="gz-sim-physics-system" name="gz::sim::systems::Physics"/>
      <plugin filename="gz-sim-user-commands-system" name="gz::sim::systems::UserCommands"/>
      <plugin filename="gz-sim-scene-broadcaster-system" name="gz::sim::systems::SceneBroadcaster"/>
    </world></sdf>''')
    metadata = {"case": case, "provenance": profile["provenance"], "parameters": p,
                "horizontal_gravity_torque_nm": 9.81 * (mass * length / 2 + payload * length),
                "inertia_at_pivot_kg_m2": inertia_pivot, "controller": gains}
    (folder / "model.json").write_text(json.dumps(metadata, indent=2) + "\n")
    return urdf, metadata
