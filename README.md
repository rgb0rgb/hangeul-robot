# 한글 로봇 공개판

한글 로봇은 로봇을 교체 가능한 부품 조합으로 보고, 현재 구성에서 가능한 일을 계산하며,
검증과 안전 조건을 통과한 동작만 실행하는 경량 Physical AI 운영 계층입니다.

이 공개판은 **시뮬레이션과 지원 하드웨어 직접 연결**을 모두 포함합니다.
OpenManipulator-X와 MyCobot 280 M5 어댑터가 들어 있으므로, 사용자가 자기 장치와
안전 범위를 확인하면 실제 로봇을 움직일 수 있습니다.
고객별 연동 코드와 상업용 운영 도구는 포함하지 않습니다.

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
| 기본 안전/전류/온도 제한 파일 | 포함 |
| 고객/상업 연동 코드 | 제외 |

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

## 설치

```bash
./install/install.sh
```

## 실행

콘솔:

```bash
./run.sh
```

브라우저:

```text
http://127.0.0.1:8099
```

시뮬레이션 런타임:

```bash
./install/run_runtime.sh arm_sim --simulate
```

실물 런타임 예:

```bash
./install/run_runtime.sh arm_omx
./install/run_runtime.sh arm_mycobot
```

장치 포트가 다르면 환경변수로 지정합니다.

```bash
DEVICE=/dev/ttyUSB1 ./install/run_runtime.sh arm_omx
DEVICE=/dev/ttyACM1 ./install/run_runtime.sh arm_mycobot
```

## 테스트

```bash
python3 -m pytest -q
```

현재 공개 폴더 기준 확인:

```text
79 passed, 16 skipped
```

## 안전 고지

이 공개판은 지원 하드웨어에 연결하면 실제 로봇을 움직일 수 있습니다.
공개판은 산업 안전 인증을 받은 제어 시스템이 아닙니다.
실물 동작을 켜기 전에 반드시 자기 하드웨어에서 안전 범위와 정지 동작을 검증해야 합니다.

## 공개 범위

공개판은 구조, 연동 계약, 그리고 제한된 실물 하드웨어 실행 경로를 보여주는 버전입니다.
진단/사고 보고 도구와 고객별 연동 코드는 별도로 관리합니다.

## 라이선스

Apache License 2.0
