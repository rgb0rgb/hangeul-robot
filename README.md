# 한글 로봇 공개판

한글 로봇은 로봇을 교체 가능한 부품 조합으로 보고, 현재 구성에서 가능한 일을 계산하며,
검증과 안전 조건을 통과한 동작만 실행하는 경량 Physical AI 운영 계층입니다.

## 실제 로봇 동작 영상

[![Hangeul Robot OpenManipulator-X 실제 동작 영상](https://img.youtube.com/vi/BMN9k5TyPFY/hqdefault.jpg)](https://www.youtube.com/shorts/BMN9k5TyPFY)

OpenManipulator-X에서 Hangeul Robot의 명령과 검증된 동작이 실제로 실행되는 영상입니다.
위 이미지를 클릭하면 YouTube Shorts에서 볼 수 있습니다.

이 공개판은 **시뮬레이션과 지원 하드웨어 직접 연결**을 모두 포함합니다.
OpenManipulator-X와 MyCobot 280 M5 어댑터가 들어 있으므로, 사용자가 자기 장치와
안전 범위를 확인하면 실제 로봇을 움직일 수 있습니다.
고객별 연동 코드와 상업용 운영 도구는 포함하지 않습니다.

Prepared a public release with simulation and supported physical hardware paths.
Included the console UI, runtime contracts, module descriptors, and public tests.
Added simulated arm and camera adapters.
Included OpenManipulator-X and MyCobot 280 M5 adapters with safety limit files.
Excluded logs, private robot instances, customer-specific material, and commercial operation tools.

## 처음 시작하기 — 윈도우 (컴퓨터를 잘 몰라도 됩니다)

1. 이 페이지 위쪽의 초록색 **Code** 단추 → **Download ZIP** 으로 받아 압축을 풉니다.
2. 풀린 폴더에서 **`Setup.bat`** 을 두 번 누릅니다.
   파이썬이 없으면 자동으로 설치하고(인터넷 필요, 몇 분), 필요한 부품을 받은 뒤
   바탕화면에 **[한글 로봇]** 과 **[한글 로봇 초기화]** 바로가기를 만들고 바로 시작합니다.
3. 브라우저가 열리면 **로봇 추가**에서 로봇을 고릅니다. 로봇을 USB로 꽂아 두면
   프로그램이 스스로 찾아 연결합니다(COM 번호를 몰라도 됩니다).

다음부터는 바탕화면의 **[한글 로봇]** 만 두 번 누르면 됩니다.

**오류가 나고 진행이 안 될 때** — 바탕화면의 **[한글 로봇 초기화]** 를 두 번 누르거나,
화면의 **환경 설정 → 완전 초기화 후 재시작** 을 누릅니다. 모든 프로그램을 끄고, 남아 있던
막힘(연결 끊김 기록·일시정지·장치 사용권)을 풀고, 로봇을 다시 찾아 처음부터 시작합니다.
무엇이 켜졌고 무엇이 왜 안 켜졌는지(예: "장치 없음 — 케이블과 전원을 확인하세요")를 알려 줍니다.
**비상 정지는 풀지 않습니다** — 로봇을 확인한 뒤 화면에서 직접 "정지 해제"를 누르세요.

| 파일 | 하는 일 |
|---|---|
| `Setup.bat` | 처음 한 번 — 설치하고 시작 |
| `Start.bat` | 시작 (바탕화면 [한글 로봇]) |
| `Reset.bat` | 완전 초기화 후 다시 시작 (바탕화면 [한글 로봇 초기화]) |
| `Stop.bat` | 모두 끄기 |

## 공개판에 들어 있는 것

| 항목 | 상태 |
|---|---|
| 콘솔 UI | 포함 |
| 부품 기술서 구조 | 포함 |
| 능력 계산 | 포함 |
| 구성/검증/안전 게이트 개념 | 포함 |
| 시뮬레이션 팔/손/눈 예제 | 포함 |
| 테스트 | 포함 |
| OpenManipulator-X 어댑터 | 포함 |
| MyCobot 280 M5 어댑터 | 포함 |
| ROS 2 팔 어댑터 (ros2_control) | 포함 · 시뮬레이션만 검증, 실물 미검증 |
| 기본 안전/전류/온도 제한 파일 | 포함 |
| 고객/상업 연동 코드 | 제외 |

## ROS 2 팔 연결 — 실물 미검증

`arm_ros2`(ros2_control의 JointTrajectoryController) 어댑터가 들어 있습니다.
**시뮬레이션에서만 검증했고, 실물 액추에이터에서는 아직 검증하지 않았습니다.**

| 단계 | 결과 |
|---|---|
| 콘솔 → 런타임 → ROS 2 DDS → 가상 관절(GenericSystem) | 연결·취소·오류 처리 확인 |
| Gazebo 1축 물리 모델(중력·관성·마찰, 토크 상한 20Nm/2Nm) | 도달/실패 구분 확인, 실패가 성공으로 표시되지 않음 |
| 실물 로봇 | **미검증** |

ROS 2가 설치되지 않은 환경에는 영향이 없습니다(`rclpy`는 이 어댑터를 열 때만 불러옵니다).
자세한 기록: [docs/ROS2_CONNECTION_AND_ACTUATOR_SIMULATION_20260921_KR.md](docs/ROS2_CONNECTION_AND_ACTUATOR_SIMULATION_20260921_KR.md),
[docs/ACTUATOR_PHYSICS_BENCH_20260921_KR.md](docs/ACTUATOR_PHYSICS_BENCH_20260921_KR.md)

Public Release Notes
This folder is a prepared public release candidate for GitHub.

It intentionally focuses on:

architecture
simulation
supported physical robot execution
module descriptor contracts
the console UI
safety and verification concepts
It includes:

OpenManipulator-X adapter
MyCobot 280 M5 adapter
safety limit files for those supported arms
It intentionally excludes:

operator logs
personal robot instances
customer-specific or commercial integration documents
target tracking and arm-follow operational tuning

## 구조

```text
console/                 웹 콘솔과 운영 API
runtime/                 로봇 런타임과 어댑터 계약
install/modules/         공개용 예제 부품 기술서
install/robots/          사용자 로봇 인스턴스 예제
data/                    운영 데이터 자리
tests/                   공개판 계약 테스트
tools/                   공개 전 검사와 보조 도구
docs/                    공개판 문서
```

## 설치 — 리눅스 / WSL

Ubuntu/WSL에서는 Python 3, pip, venv가 필요합니다 (`python3-venv` 패키지).
설치 스크립트는 프로젝트의 `.venv`에 의존성과 테스트 도구를 설치합니다.
실물 로봇 패키지 설치가 실패하면 시뮬레이션만 사용할 수 있으며 이유가 표시됩니다.

```bash
./install/install.sh
```

## 실행

```bash
./run.sh        # 시작 — 콘솔과 등록된 로봇의 런타임을 모두 띄운다
./restart.sh    # 완전 초기화 후 다시 시작 (비상 정지는 그대로)
./stop.sh       # 모두 끄기
```

브라우저: `http://127.0.0.1:8099`

세 스크립트와 윈도우의 bat 파일, 화면의 "완전 초기화" 단추는 모두 `tools/launcher.py`
하나를 부릅니다. 실행기는

- 등록된 로봇(`install/robots/*.json`)을 읽어 런타임을 포트별로 띄우고
- 장치를 번호(`/dev/ttyUSB0`, `COM3`)가 아니라 부품 기술서의 USB 신원(`usb_ids`)으로 찾으며
  (리눅스에서는 번호가 바뀌어도 이어지는 `/dev/serial/by-id/…` 경로로 엽니다)
- WSL에서는 윈도우에 꽂힌 USB를 `usbipd`로 붙여 보고
- 무엇을 띄웠고 무엇을 못 띄웠는지 이유와 함께 `data/run/last_report.json`에 남깁니다.

화면에서 로봇을 추가하면 그 로봇의 런타임도 바로 띄웁니다.

**시뮬레이션:** 콘솔의 **로봇 추가**에서 시뮬레이션 팔(`arm_sim`)을 고르면 실물 없이 현재 위치 읽기,
미세 이동, 절대 이동을 시험할 수 있습니다. 가상 팔의 기본 관절 범위는 0~4095 ticks입니다.
시뮬레이션 팔과 OMX는 기본 포트(8601)가 같으므로 한 번에 하나만 등록하세요.

런타임을 손으로 띄울 수도 있습니다.

```bash
./install/run_runtime.sh arm_sim --simulate
DEVICE=/dev/ttyUSB1 ./install/run_runtime.sh arm_omx
```

## 테스트

```bash
.venv/bin/python -m pytest -q
```

현재 공개 폴더 기준 확인:

```text
300 passed, 19 skipped
```

## 공개판에서 사용하지 않는 기능

물체·색상 추적과 팔 따라가기는 제공하지 않습니다. 관련 상태 조회는 미지원으로
응답하고, 화면은 해당 기능을 자동 조회하지 않습니다. `eye_sim`은 영상 생성기가
아닌 카메라 인터페이스 예제이며 `read_frame()`은 `None`을 반환합니다.

`./stop.sh`와 `./restart.sh`는 같은 프로젝트 경로에서 실행된 서버만 종료합니다.
이 스크립트는 Linux/WSL용입니다.

## 안전 고지

이 공개판은 지원 하드웨어에 연결하면 실제 로봇을 움직일 수 있습니다.
공개판은 산업 안전 인증을 받은 제어 시스템이 아닙니다.
실물 동작을 켜기 전에 반드시 자기 하드웨어에서 안전 범위와 정지 동작을 검증해야 합니다.

## 공개 범위

공개판은 구조, 연동 계약, 그리고 제한된 실물 하드웨어 실행 경로를 보여주는 버전입니다.
진단/사고 보고 도구와 고객별 연동 코드는 별도로 관리합니다.

## 라이선스

Apache License 2.0
