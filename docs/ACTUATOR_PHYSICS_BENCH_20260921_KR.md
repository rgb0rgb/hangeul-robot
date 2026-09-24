# 액추에이터 1축 물리 시뮬레이션 검증

작성: Codex · 2026-09-21 · 개발 저장소

## 이번 단계의 결과

제조사 중립 1축 모델을 **실제 Gazebo 물리 엔진**으로 실행하도록 만들었다. 기존 Hangeul 콘솔과 런타임의 실행 코드는 이번 단계에서 수정하지 않았다. 부품 기술서의 관절과 ROS 설정, 하위 시뮬레이션 플러그인으로 연결했다.

경로는 `콘솔 HTTP → 런타임 → FollowJointTrajectory → effort 제어기 → 최종 토크 제한 → Gazebo 물리 모델`이다. 앞 단계 GenericSystem과 달리 중력·질량·관성·점성 마찰이 움직임에 영향을 준다.

20Nm 상한 모델에서는 목표 도달과 저장 순서 실행을 확인했다. 2Nm 상한 모델에서는 부하를 들지 못하고 action이 목표 시간 초과로 실패하는 것을 확인했다. **실패가 콘솔에 성공으로 표시되지 않는 것까지** 검증한다. 실제 제품 두 개를 비교한 결과는 아니다.

최종 실행의 물리·연결 확인 **22항목이 모두 통과**했다.

| 최종 측정 | 20Nm 상한 | 2Nm 상한 |
|---|---:|---:|
| 목표와 최종 위치 차이 | 0.280° | 81.248° |
| 물리 모델에 적용한 최대 토크 크기 | 13.090Nm | 2.000Nm |
| 관측 표본 중 상한의 98% 이상인 비율 | 0% | 약 95.8% |
| 콘솔 결과 | 성공 | TRAJECTORY_FAILED |

20Nm 모델의 마지막 0.2초 평균 적용 토크는 5.801886Nm, 같은 위치에서 계산한 중력 토크는 5.801856Nm였다. 표의 최종 오차는 응답 뒤 0.3초 시점의 위치이며, action 완료 순간 오차와 구분한다.

그래프에서 부족한 토크 모델의 마지막 reference가 위로 바뀌는 것은 실패 후 제어기가 현재 위치 유지로 전환했기 때문이다. 원래 목표 -10도에 도달한 것이 아니다.

- [최종 검증 JSON](ACTUATOR_PHYSICS_VALIDATION_20260921.json)
- [비교 그래프 PNG](ACTUATOR_PHYSICS_VALIDATION_20260921/comparison.png) · [SVG](ACTUATOR_PHYSICS_VALIDATION_20260921/comparison.svg)
- [실행 시 사용한 파라미터](ACTUATOR_PHYSICS_VALIDATION_20260921/profile.json)
- 원시 위치·토크 기록, 생성한 모델, 제어 설정, 실행 로그는 같은 결과 폴더의 `adequate`, `insufficient`에 보관한다.

## 모델과 판단 기준

| 항목 | 값·뜻 |
|---|---|
| 링크 | 길이 0.4m, 질량 1kg |
| 끝 부하 | 1kg; 링크와 합친 질량·무게중심·관성으로 모델링 |
| 초기 자세 | 두 모델 모두 아래쪽 90도, 목표는 수평보다 위쪽 -10도 |
| 중력 | 9.81m/s² |
| 점성 마찰 | 0.15Nm·s/rad |
| 토크 상한 | 출력축 기준 ±20Nm / ±2Nm |
| 수평 유지에 필요한 중력 토크 | `9.81 × (1 × 0.2 + 1 × 0.4) = 5.886Nm` |
| 물리 계산 / 제어 주기 | 1ms / 5ms |
| 목표 판단 | JTC 위치 허용오차 0.006rad, 목표시간 여유 8초; 어댑터의 도달 확인도 통과해야 성공 |

위 수치는 전부 `assumed`인 시험용 수치다. CubeMars·MyActuator의 특정 제품 사양으로 이름 붙이지 않았다. 정지 중 중력과 적용 토크의 일치도 추가로 확인한다. 2Nm로 약 5.8Nm가 필요한 자세를 유지할 수 없는 결과는 정상적인 실패다.

단위는 길이 m, 질량 kg, 관성 kg·m², 토크 Nm, 관절각 rad로 모델링한다. Hangeul의 밀리도 값은 기존 ROS 어댑터가 변환한다. 관성은 링크와 끝 부하를 합친 강체의 무게중심 기준으로 계산하며, 회전축 기준 값과 혼동하지 않는다.

## 토크 제한을 별도 구현한 이유

PID의 `u_clamp`는 전체 모터 출력의 상한과 같지 않았다. JTC는 PID 출력에 궤적의 보상 성분을 더할 수 있고, 설치된 구현은 궤적 시작 상태에 이전 effort 명령을 사용한다. 따라서 PID를 2Nm로 제한했는데도 제어기 요청이 그보다 커지는 경우가 시험에서 나타났다.

`simulation/hangeul_effort_limit` 플러그인은 기존 GazeboSimSystem을 감싸서 **물리 엔진으로 넘기기 직전 전체 요청을 제한**한다. 이 플러그인은 시뮬레이션 전용이며, 실물의 안전 제어나 브레이크를 대신하지 않는다.

관측값도 구분했다.

- `commands.csv`: JTC가 요청한 토크. 최종 제한 이전 값이다.
- `samples.csv`: Gazebo 위치·속도와 플러그인이 최종 적용한 토크. `applied_effort`를 JointState effort로 매핑했다.
- 원래 Gazebo의 관절 wrench 투영값은 반력을 포함하므로, 모터 명령의 제한을 판정하는 값으로 쓰지 않는다.

검증은 **최종 적용 토크가 설정 상한 이내인지**, 부족한 모델에서 실제 포화가 나타나는지를 확인한다. 단순히 설정 파일의 숫자를 검사하는 것과 다르다.

근거: [gz_ros2_control의 사용자 정의 물리 인터페이스](https://control.ros.org/jazzy/doc/gz_ros2_control/doc/index.html), [JTC 출력 계산 구현](https://github.com/ros-controls/ros2_controllers/blob/jazzy/joint_trajectory_controller/src/joint_trajectory_controller.cpp), [Gazebo 관절 상태·출력 구현](https://github.com/ros-controls/gz_ros2_control/blob/jazzy/gz_ros2_control/src/gz_system.cpp).

## 검증 범위

두 모델 모두 콘솔 등록, 자세 저장, 실제 물리 상태 수신, 가상 증거 표시, 최종 토크 제한, 예상한 도달 또는 실패를 확인한다. 충분한 토크 모델에서는 저장한 두 자세의 순서 실행, 이동 중 취소, 정지 후 새 명령 차단도 확인한다. 부족한 모델은 ROS action의 `GOAL_TOLERANCE_VIOLATED`가 콘솔의 `TRAJECTORY_FAILED`로 전달되어야 한다.

전체 Python 자동시험은 **412 passed / 21 skipped**였다. 모델의 질량·관성 관계, 제한값 일치, 잘못된 파라미터 거부 시험 5건을 포함한다. 마지막 초기 자세 변경 후에도 해당 5건을 다시 통과했다. C++ 플러그인 빌드와 실제 Gazebo 검증은 별도다. Gazebo 플러그인과 호환되는 구 API 사용에 대한 컴파일 경고는 남아 있으며 빌드 실패는 아니다.

이 검증은 화면이 사용하는 HTTP 경로를 실행했다. 브라우저 클릭이나 실제 하드웨어 시험으로 기록하지 않는다. action 취소와 새 명령 차단을 확인했지만, 실물의 비상정지 거리·중력 낙하 방지·정전 브레이크 성능을 입증한 것은 아니다.

## 재현

```bash
cd hangeul-robot
source /opt/ros/jazzy/setup.bash
python3 tools/verify_actuator_physics.py --report /tmp/actuator_physics.json
python3 tools/plot_actuator_physics.py /tmp/actuator_physics.json
```

ROS Jazzy, Gazebo Harmonic, gz_ros2_control, ros_gz_sim, ros_gz_bridge, JTC, joint_state_broadcaster, robot_state_publisher, colcon·C++ 개발 도구와 프로젝트 Python 의존성이 필요하다. 그래프 작성에는 matplotlib이 필요하다. 이번 환경의 설치 항목으로 실행했다.

이 환경은 시스템 matplotlib과 `/usr/local`의 NumPy 버전이 맞지 않아, 그래프만 시스템 패키지를 사용해 생성했다. 전역 패키지를 바꾸지 않았다.

```bash
PYTHONPATH=/usr/lib/python3/dist-packages /usr/bin/python3 -S tools/plot_actuator_physics.py /tmp/actuator_physics.json
```

실행기는 임시 폴더에서 플러그인을 빌드하고 자체 Gazebo·ROS·콘솔·런타임만 시작하고 종료한다. ROS domain 174와 고유 Gazebo partition을 사용한다. 다른 작업은 이 ROS domain을 사용하지 않아야 한다. 직렬 장치와 실제 등록 로봇을 사용하지 않는다.

`--report`의 확장자를 뺀 폴더에 원시 기록과 설정을 보관한다. 생성 URDF/YAML은 실행 당시 경로를 포함한 증거용 사본이므로 직접 재실행하지 말고 생성기를 사용한다. 기본 비교 설정은 `simulation/actuator_bench.json`이며 `--profile`로 같은 형식의 비교 파일을 지정할 수 있다. 현재 자동 판정은 `adequate`는 성공, `insufficient`는 실패해야 하는 기준시험이다. 임의 제품 목록을 자동 순위화하는 도구는 아니다.

## 이어서 할 일

1. 실제 후보 모델·펌웨어와 출력축 정격을 확정하여 출처 있는 파라미터를 추가한다. 모델 미정인 값은 추정이라고 표시한다.
2. 연속/피크 토크와 피크 허용시간, 토크-속도 곡선, 지연, 감속기 효율·마찰 범위를 모델링한다. 현재는 일정 토크 상한이며 전류·전압·발열·백래시 모델이 없다.
3. 같은 조건으로 부하와 궤적을 바꾸는 반복 비교, 이후 다축과 독립 그리퍼로 확장한다.
4. 실물 도착 후 모델의 영점·방향·토크 환산·마찰·열 특성·정지 거동을 보정한다.

지금 완료한 것은 **실물 도착 전에도 실패를 재현할 수 있는 물리 검증 기반**이다. 제조사 CAN 드라이버, 완성 팔의 성능, 다축 충돌 회피는 아직 완료 범위가 아니다. 이번 변경과 결과는 로컬 개발 저장소에만 있으며 공개판 이식·GitHub 푸시는 하지 않았다.
