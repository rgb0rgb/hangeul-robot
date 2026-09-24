# ROS 2 연결 검증과 액추에이터 시뮬레이션 진행안

작성: Codex · 2026-09-21 · 대상: Hangeul Robot 개발 저장소

> 후속 작업: [1축 Gazebo 물리 시뮬레이션 결과](ACTUATOR_PHYSICS_BENCH_20260921_KR.md).
> 아래의 “다음 1축 모델”은 이 문서 최초 작성 시점의 순서이며, 후속 결과에 진행 상태를 기록했다.

## 1. 결론

남은 작업이 모두 하드웨어 실측이라는 해석은 바로잡는다. 실물 도착 전에도 연결, 실행 순서, 취소, 오류 처리, 물리 모델의 부하·토크 비교를 진행할 수 있다.

이번 작업에서는 **콘솔 → HTTP 런타임 → 실제 ROS 2 DDS → JointTrajectoryController → GenericSystem 가상 관절** 연결을 구현하고 실행했다. 이전 가짜 노드 단위시험보다 한 단계 진행한 결과다. GenericSystem은 명령을 상태로 반영하는 모의 장치이므로 모터의 물리 성능 검증으로 간주하지 않는다.

다음 개발 우선순위는 **Gazebo 물리 모델 연결 → 액추에이터 후보별 파라미터 비교 → 독립 그리퍼 조합 → 실물 보정**이다. 첫 물리 모델은 특정 제조사를 정하지 않은 1축 부하 모델로 시작한다. 구매 결정을 기다릴 필요가 없다.

## 2. 연결 코드 변경

- `ros2_transport.py`: 실제 JointState 구독, FollowJointTrajectory action 요청·응답·feedback·result·cancel, 독립 executor, 위치 데이터 유효시간, 유한 대기시간.
- `ros2_arm_adapter.py`: 문자열 관절 이름과 기술서 단위 변환, 일부 관절 이동 시 나머지 관절의 현재 위치 유지, 이동 거리와 속도 상한에 따른 수행시간 계산. 누락·비정상 위치값으로 목표를 만들지 않는다.
- `server.py`: 문자열 관절 안전 검사, 잠금 대기 후 안전 상태 재검사, 취소·실패 결과 전달, JTC 정지 시 추가 이동 명령 방지, 명시적 복구, 종료 시 어댑터 정리, 독립 안전 상태 파일 지정.
- `capability.py`: 런타임의 `_checked_at` 문자열을 부품 응답 사전으로 처리하여 콘솔이 실패하던 오류 수정.
- 가상 시험 결과에는 `evidence_kind=virtual`, `actual_hardware_called=false`를 기록한다. `simulated` 기존 필드는 어댑터 없는 대체 모드 의미를 유지하므로, 물리 증거 판단에는 `evidence_kind`도 확인해야 한다.

기존 계약이 처음부터 모든 장치에 맞았다는 결론은 아니다. 실제 HTTP 연결을 해보니 공통 런타임과 콘솔에도 수정이 필요했다. 다음 다른 장치 연결에서 공통 코드 변경 없이 가능한지를 다시 검증해야 한다.

## 3. 실행 검증과 재현

실행 결과: [검증 JSON](ROS2_CONNECTION_VALIDATION_20260921.json).

전체 자동시험은 375 passed / 20 skipped였다. 이후 DDS 완료·위치 메시지 순서 차이의 회귀시험을 추가했고, ROS 계약시험 17건을 별도로 통과했다. skipped 항목은 통과에 포함하지 않는다.

확인 항목:

1. 콘솔 로봇 등록과 이름 있는 관절의 실제 ROS 상태 수신.
2. 두 자세 저장과 콘솔 실행, 실제 action 결과 성공 확인.
3. 저장된 두 단계 순서의 시작과 완료.
4. 허용 범위 초과와 존재하지 않는 관절의 요청 거절.
5. 이동 중 콘솔 정지로 실제 action 취소, 이후 새 이동 차단.
6. 런타임 재시작 후 정지 유지, 명시적 해제 후 다시 실행.
7. 잘못된 관절 목록을 보낸 실제 ROS action의 거절.
8. 실제 action 실행 중 클라이언트 결과 대기 시간 초과를 **시험 코드에서 주입**하여 취소·재실행 차단 확인. 네트워크 지연 한계를 실측한 시험은 아니다.
9. ROS 프로세스를 종료하고 상태 유효시간이 지난 뒤 오래된 관절값 거부.

```bash
cd hangeul-robot
source /opt/ros/jazzy/setup.bash
python3 tools/verify_ros2_connection.py --report /tmp/hangeul-ros2-report.json
python3 -m pytest -q
```

ROS Jazzy, controller_manager, joint_trajectory_controller, joint_state_broadcaster, mock_components, robot_state_publisher 및 기존 프로젝트 Python 의존성이 필요하다. DDS의 로컬 통신이 허용되는 환경에서 실행한다. 시험은 ROS domain 173을 사용하므로 그 도메인에 다른 제어기를 띄우지 않는다.

시험이 새 임시 폴더에 부품 기술서·로봇 등록·자세·안전 상태를 만들고 자신의 프로세스만 종료한다. 실제 로봇 설정과 직렬 장치는 사용하지 않는다. `/tmp` 로그는 임시 자료이며, 저장소의 JSON이 보관용 결과다. 이 시험은 브라우저 화면 클릭 시험이 아니라 **화면이 사용하는 HTTP API부터 실제 DDS까지**의 통합 시험이다.

## 4. 시뮬레이션 방법 비교

| 방법 | 지금 할 수 있는 일 | 한계와 적용 순서 |
|---|---|---|
| ros2_control GenericSystem | 연결, 이름·단위, 자세·순서, action 취소, 오류 경로 | 이번 실행 완료. 하중·중력·토크·발열 모델이 아님 |
| Gazebo Harmonic + gz_ros2_control | 링크 질량·관성·중력·접촉을 둔 팔을 같은 ROS 인터페이스로 실행 | **다음 우선 작업**. 토크 비교에는 effort 제어와 구동기 제한 모델을 구성해야 함 |
| MuJoCo | 가벼운 반복 실행으로 관절 부하, 감속비, 힘 제한, 제어기 파라미터 비교 | 별도 모델과 Hangeul/ROS 연결이 필요. 이번에는 설치·연동하지 않음 |
| Isaac Lab | DC motor·지연 PD 모델, 다수 환경의 반복 비교 및 학습 | 이후 대량 비교·학습 단계 후보. 이번에는 설치·실행하지 않음 |

Gazebo 공식 문서는 ROS 2 Jazzy와 Harmonic 조합, ros2_control 연결, 사용자 정의 액추에이터 동역학 플러그인을 제공한다. 따라서 현재 연결을 활용하는 다음 경로로 판단했다. 기본 position 명령만으로 움직이는 것을 확인해도 실제 모터의 토크 성능을 입증하지는 못한다. [공식 문서](https://control.ros.org/jazzy/doc/gz_ros2_control/doc/index.html)

MuJoCo는 actuator의 transmission과 force limit 등을 모델에 넣을 수 있다. Isaac Lab에는 DC motor와 지연 PD 등의 모델이 있다. 이 모델에 넣는 수치의 근거와 모델 버전을 보관해야 후보 간 비교가 재현된다. [MuJoCo 모델링](https://mujoco.readthedocs.io/en/latest/modeling.html), [Isaac Lab actuators](https://isaac-sim.github.io/IsaacLab/develop/source/concepts/actuators.html)

## 5. 제조사와 무관하게 비교할 후보군

아래는 구매 추천 순위나 이미 연결된 제품 목록이 아니다. 같은 가상 팔에서 비교할 구동계 유형이다.

| 후보군 | 비교할 이유 | 추가로 확보할 정보 |
|---|---|---|
| CubeMars AK 계열 | 모터·감속기·드라이버 일체형 관절 후보 | 정확한 모델·펌웨어, 제어 모드, 연속/피크 토크, 출력축 속도, 감속비 |
| MyActuator RMD-X 계열 | 다른 일체형 감속 관절과의 비교 | 세대별 프로토콜, 제어 모드, 연속 정격과 피크 허용시간, 기계적 치수 |
| ODrive + BLDC + 감속기 | 모터·감속기·드라이버를 따로 선정하는 자작팔 | 모터 상수·관성·전류 제한, 감속기 효율, 센서 구성, 조합 전체 질량 |
| moteus + BLDC + 감속기 | 제어기와 기구를 분리한 또 다른 자작 구동계 | 제어 모드와 제한값, 모터·감속기 조합, 위치 피드백과 통신 주기 |

공식 확인 자료: [CubeMars 매뉴얼](https://www.cubemars.com/article.php?id=261), [MyActuator 제품군](https://www.myactuator.com/product), [ODrive 모터 파라미터](https://docs.odriverobotics.com/v/latest/articles/motor-parameters.html), [moteus 제어 모드](https://mjbots.github.io/moteus/guides/control-modes/).

상위 연결은 `Hangeul → JTC → ros2_control hardware interface`로 유지하고, 아래쪽을 가상 구동계 또는 실제 CAN/기타 드라이버로 교체하는 방향이다. **제조사별 실제 하드웨어 플러그인은 아직 구현하지 않았다.** 모터를 샀다고 현재 ROS 어댑터만으로 바로 연결되는 것은 아니다.

## 6. 다음 구현의 완료 기준

1. **일반 1축 물리 모델**: 수평 링크와 부하, 중력, 관성, 마찰, 토크 포화를 넣는다. 무부하 성공뿐 아니라 토크 부족 시 목표 실패를 재현한다.
2. **파라미터 분리**: 출력축 기준 Nm·rad/s·kg·kg·m²·초 단위로 정리하고, 감속 전/후 값을 혼용하지 않는다. 연속 토크와 피크 토크를 분리한다. 출처 없는 값은 `assumed`로 표시한다.
3. **후보 비교**: 동일 링크·부하·궤적으로 토크 여유, 추종 오차, 정착시간, 포화시간을 비교한다. 마찰·효율·지연은 한 숫자로 확정하지 않고 범위를 바꿔 반복한다.
4. **다축 연결**: 이번 HTTP 검증의 자세·순서·취소·오류 항목을 Gazebo에도 적용한다. 모델 교체만으로 동작하는지 확인한다.
5. **독립 그리퍼**: 별도 action server의 실패·정지·부품 응답을 팔과 분리하여 검증한다.
6. **실물 도착 후**: 영점·방향·감속비·전류/토크 환산·마찰·백래시·열 특성·정지거리를 측정해 모델을 보정한다.

현재 가상 연결은 가속도·저크 제한, 토크 제어, 통신 단절 시 실제 드라이버의 watchdog/제동, 제조사 고유 CAN 프로토콜, 독립 그리퍼까지 완료했다는 뜻이 아니다. 이동로봇·카메라·MoveIt·Nav2 역시 이번 완료 범위가 아니다. 다만 이들 작업도 하드웨어 대기만 해야 하는 것은 아니다.

## 7. 공개판 적용 범위

이 문서는 개발 저장소에서 작성되었고, 2026-09-24 공개판에 ROS 2 어댑터·검증 도구와 함께 옮겼다.
**실물 액추에이터에서는 아직 검증하지 않았다.** GenericSystem·Gazebo 물리 모델·실물 결과는 각각 구분한다.
