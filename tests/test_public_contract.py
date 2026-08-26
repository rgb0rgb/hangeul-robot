from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_public_release_has_no_private_robot_instances():
    robots = sorted((ROOT / "install" / "robots").glob("*.json"))
    assert [p.name for p in robots] == ["arm.example.json"]


def test_public_release_uses_simulated_arm_descriptor():
    arm = json.loads((ROOT / "install" / "modules" / "arm_sim.json").read_text(encoding="utf-8"))
    assert arm["runtime_adapter"] == "simulated_arm_adapter:SimulatedArmAdapter"
    assert arm["hardware_evidence"]["state"] == "simulated"


def test_public_release_includes_supported_physical_adapters():
    hardware = ROOT / "runtime" / "src" / "hangeul_runtime" / "hardware"
    assert (hardware / "openmanipulator_x_arm_adapter.py").exists()
    assert (hardware / "mycobot_280_m5_adapter.py").exists()

    modules = ROOT / "install" / "modules"
    omx = json.loads((modules / "arm_omx.json").read_text(encoding="utf-8"))
    mycobot = json.loads((modules / "arm_mycobot.json").read_text(encoding="utf-8"))
    assert omx["runtime_adapter"] == "openmanipulator_x_arm_adapter:OpenManipulatorXArmAdapter"
    assert mycobot["runtime_adapter"] == "mycobot_280_m5_adapter:MyCobot280M5Adapter"


def test_public_release_does_not_ship_runtime_logs():
    forbidden = [
        *ROOT.glob("data/*.log"),
        *ROOT.glob("data/*.jsonl"),
        *ROOT.glob("data/leases/*"),
    ]
    assert forbidden == []
