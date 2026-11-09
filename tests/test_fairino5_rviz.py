"""FR5 rviz 화면 — 기술서·화면 설정·시작 메뉴 바로가기가 서로 어긋나지 않는다 (2026-11-09)."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROS2 = ROOT / "install" / "ros2"


def _simulator_command() -> str:
    descriptor = json.loads((ROOT / "install/modules/arm_fairino5.json").read_text("utf-8"))
    return descriptor["ros2"]["simulator"]["command"]


def test_the_simulator_uses_the_hangeul_rviz_screen_that_exists():
    match = re.search(r"rviz_config:=\$PWD/(\S+)", _simulator_command())
    assert match, "실행기가 FAIRINO 원본 화면으로 띄웁니다"
    assert (ROOT / match.group(1)).is_file()


def test_the_screen_hides_the_moveit_goal_arm_and_fixes_the_size():
    text = (ROS2 / "fairino5.rviz").read_text("utf-8")
    assert "Query Goal State: false" in text      # 주황 팔이 실제 팔처럼 보였다
    geometry = text.split("Window Geometry:")[1]
    assert re.search(r"\n  Width: \d+", geometry) and re.search(r"\n  Height: \d+", geometry)


def test_the_start_menu_scripts_run_and_carry_no_fixed_home():
    for name in ("fr5_rviz.sh", "install_fr5_rviz_shortcut.sh"):
        path = ROS2 / name
        assert os.access(path, os.X_OK), f"{name}에 실행 권한이 없습니다"
        text = path.read_text("utf-8")
        assert "/root/hangeul" not in text, f"{name}에 이 컴퓨터의 경로가 박혀 있습니다"
        # ROS setup.bash는 정의 안 된 변수를 읽는다 — set -u면 아무것도 못 띄우고 끝난다
        assert not re.search(r"^set -\w*u", text, flags=re.M), name
