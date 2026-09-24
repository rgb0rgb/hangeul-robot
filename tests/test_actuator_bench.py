"""Model consistency checks independent of ROS/Gazebo installation."""
import importlib.util
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("actuator_bench", ROOT / "tools/actuator_bench.py")
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


def test_mass_distribution_matches_static_gravity_and_pivot_inertia(tmp_path):
    xml, model = bench.generate(tmp_path, plugin_path="/test/plugin.so")
    body = ET.fromstring(xml).find("link[@name='lever']/inertial")
    mass = float(body.find("mass").get("value"))
    center = float(body.find("origin").get("xyz").split()[0])
    inertia = float(body.find("inertia").get("iyy"))
    assert mass == 2
    assert center == pytest.approx(0.3)
    assert mass * center * 9.81 == pytest.approx(5.886)
    assert inertia + mass * center**2 == pytest.approx(model["inertia_at_pivot_kg_m2"])


def test_torque_limit_agrees_across_physics_interface_and_pid(tmp_path):
    xml, model = bench.generate(tmp_path, case="insufficient", plugin_path="/test/plugin.so")
    root = ET.fromstring(xml)
    assert float(root.find("joint[@name='bench_joint']/limit").get("effort")) == 2
    assert float(root.find("ros2_control/joint/command_interface/param[@name='max']").text) == 2
    config = yaml.safe_load((tmp_path / "controllers.yaml").read_text())
    gains = config["joint_trajectory_controller"]["ros__parameters"]["gains"]["bench_joint"]
    assert gains["u_clamp_max"] == 2 and gains["u_clamp_min"] == -2
    assert gains["ff_velocity_scale"] == 0
    assert "assumed" in model["provenance"]


@pytest.mark.parametrize("key,value", [("length_m", 0), ("payload_mass_kg", -1), ("damping_nms_rad", float("nan"))])
def test_invalid_physical_parameters_rejected(tmp_path, key, value):
    profile = json.loads(bench.DEFAULT_PROFILE.read_text())
    profile["plant"][key] = value
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(profile))
    with pytest.raises(ValueError):
        bench.generate(tmp_path / "model", path, plugin_path="/test/plugin.so")
