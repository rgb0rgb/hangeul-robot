#!/usr/bin/env bash
# FR5 rviz 화면 열기 — 윈도우 시작 메뉴의 'FR5 rviz (hangeul)'이 이것을 부른다.
#
# rviz2만 단독으로 띄우면 FR5 모델 정보를 못 받아 빈 화면이 된다. FAIRINO 패키지의
# 실행 파일로 연다. 화면 설정(창 크기·주황 팔 끔)은 같은 폴더의 fairino5.rviz.
#
#   시뮬레이터가 떠 있으면  → rviz 화면만 다시 연다 (rviz만 닫았을 때)
#   떠 있지 않으면          → 시뮬레이터를 rviz와 함께 띄운다
#
# 뒤의 경우 이 시뮬레이터는 실행기(stop.sh)가 띄운 것이 아니라서 stop.sh로 꺼지지 않는다.
# rviz 창을 닫으면 함께 꺼진다. 평소에는 run.sh / run_wsl.bat으로 띄우는 것이 정본이다.
set -eo pipefail      # -u는 쓰지 않는다: ROS setup.bash가 정의 안 된 변수를 읽다 멈춘다
cd "$(dirname "$0")"
source /opt/ros/jazzy/setup.bash
source "$HOME/fairino_ws/install/setup.bash"
CONFIG="$PWD/fairino5.rviz"
if pgrep -f "ros2_control_node.*fairino5_v6_moveit2_config" >/dev/null; then
  exec ros2 launch fairino5_v6_moveit2_config moveit_rviz.launch.py rviz_config:="$CONFIG"
fi
exec ros2 launch fairino5_v6_moveit2_config demo.launch.py rviz_config:="$CONFIG"
