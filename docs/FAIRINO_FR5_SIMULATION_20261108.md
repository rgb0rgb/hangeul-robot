# FAIRINO FR5 — ROS 2 시뮬레이션 연결 (2026-11-08)

**시뮬레이션만이다.** 실물 FR5, 실물 제어기(`fairino_hardware`), IP 연결은 해 보지 않았다.
여기 적힌 "됨"은 전부 ros2_control의 `mock_components/GenericSystem` 위에서다.

## 준비 (한 번)

ROS 2 Jazzy(Ubuntu 24.04)가 있어야 한다. FAIRINO 저장소는 **이 저장소 밖에** 받는다.

    mkdir -p ~/fairino_ws/src && cd ~/fairino_ws/src
    git clone -b V3.0_ubuntu24.04 https://github.com/FAIR-INNOVATION/frcobot_ros2.git
    cd ~/fairino_ws && source /opt/ros/jazzy/setup.bash
    colcon build --packages-select fairino_description fairino5_v6_moveit2_config

검증한 판: `frcobot_ros2` 63b2583. 두 패키지만 빌드한다(`fairino_hardware`는 실물용이라 빼었다).

## 실행

화면에서 **＋ (로봇 추가)** → `FAIRINO FR5 (ROS 2 시뮬레이션)`. 그 뒤로는

    ./run.sh                                리눅스/WSL
    install\windows\run_wsl.bat            윈도우에서 두 번 누르기

실행기가 다음 순서로 띄운다.

1. 기술서의 `ros2.setup`(`/opt/ros/jazzy/setup.bash`, `~/fairino_ws/install/setup.bash`)을 확인한다
2. `/fairino5_controller/follow_joint_trajectory`가 답하는지 본다
3. 답하지 않으면 기술서의 `ros2.simulator.command`(demo.launch.py — rviz2 포함)를 띄우고 최대 60초 기다린다
4. 같은 ROS 환경 안에서 런타임(:8606)을 띄운다

`./stop.sh`는 런타임·콘솔과 함께 **실행기가 띄운 시뮬레이터만** 끈다. 손으로 띄운 시뮬레이터는 두고 간다.

손으로 띄우려면:

    # 터미널 A
    source /opt/ros/jazzy/setup.bash && source ~/fairino_ws/install/setup.bash
    ros2 launch fairino5_v6_moveit2_config demo.launch.py
    # 터미널 B
    source /opt/ros/jazzy/setup.bash
    ./install/run_runtime.sh fairino5

MoveIt의 Plan/Execute는 쓰지 않는다. 명령 경로가 둘이 되면 화면이 아는 자세와 팔이 어긋난다.
rviz2는 팔을 **보는** 용도다.

## 연결 판정

`/api/estop-status`의 `simulated`가 `false`여야 붙은 것이다. `true`면 `simulate_reason`에 이유가 있다.

| 이유 | 원인 |
|---|---|
| `No module named 'rclpy'` | ROS 2 환경 없이 런타임을 띄웠다 |
| `ROS trajectory action server is unavailable` | 시뮬레이터가 아직 안 떴거나 꺼졌다 |

## 기술서와 범위

| 관절 | URDF (°) | 이 저장소의 범위 (°) |
|---|---|---|
| j1 · j5 · j6 | ±175 | ±170 |
| j2 · j4 | −265 ~ 85 | −260 ~ 80 |
| j3 | ±162 | ±157 |

단위는 밀리도(0.001°). 최대 속도 0.5 rad/s — "느리게"(50°/s)도 이 상한에 걸려 약 28.6°/s로 간다.
`runtime_model`은 `fairino5_ros2_jtc`다. 일반 ROS 2 팔(`ros2_control_jtc`)과 같은 값을 쓰면
콘솔이 두 로봇을 같은 종류로 보고 섞는다.

## 검증 기록 (2026-11-08, WSL2 Ubuntu 24.04 · ROS 2 Jazzy)

| 항목 | 결과 |
|---|---|
| `list_controllers` | `fairino5_controller` · `joint_state_broadcaster` active |
| 연결 | `simulated=false` |
| j1 → 200000 (200°) | `out_of_range`로 거절, goal 나가지 않음 |
| j1 → 10000 (10°) | `MOVED`, `/joint_states` j1 = 0.174533 rad |
| 정지 → 이동 | `estop_latched`로 막힘 |
| 정지 해제 → 이동 | 해제 `ready`, 다시 이동됨 (수정 전에는 해제가 늘 실패 — CHANGELOG) |
| 화면: 관절 표 | j1~j6 · 도 단위 · 범위가 위 표와 같음 |
| 화면: 직접 이동 4회 | 화면 값과 `/joint_states` 일치 |
| 화면: 자세 2개 저장 · 순서 3단계 실행 | 왼쪽(30°, −20°) → 오른쪽(−30°, j3 25°) → 왼쪽. 화면 로그 시각과 `/joint_states` 궤적이 일치 |
| 윈도우 `run_wsl.bat` 경로 | 빈 상태에서 한 번에 시뮬레이터 · rviz2 · 런타임 · 화면이 뜸(약 18초), `simulated=false` |

## 아직 안 된 것

- rviz2 창이 떠 있는 것은 X 창 목록으로만 확인했다. WSLg는 화면 캡처를 막아, 3D 모델이
  보이는지는 사람이 봐야 한다.
- 실물 FR5. 실물에 붙일 때는 기술서의 `ros2.simulator`를 지우고(시뮬레이터를 대신 띄우지 않게)
  관절 범위를 실측으로 다시 정해야 한다.
- 손(그리퍼). 기술서가 없다.
- 관절 온도·전류를 읽는 길이 없다. 런타임은 "온도를 확인하지 않았다"고 결과에 적는다.
