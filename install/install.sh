#!/usr/bin/env bash
# 한글 로봇 설치 — 리눅스/WSL
set -euo pipefail
# Keep ROS/system Python packages out of this project environment.
unset PYTHONPATH
cd "$(dirname "$0")/.."
echo "[1/4] 필요한 것 설치"
python3 -m venv .venv
PYTHON="$PWD/.venv/bin/python"
"$PYTHON" -m pip install -q -r requirements-test.txt
"$PYTHON" -m pip install -q -r requirements-robot.txt || echo "  (실물 로봇 패키지는 건너뜀 — 시늉 모드로 쓸 수 있습니다)"
echo "[2/4] 폴더 준비"
mkdir -p data/instances data/leases
echo "[3/4] 로봇 확인"
PYTHONPATH=console/src "$PYTHON" - <<'PY'
from pathlib import Path
from hangeul_console.registry import Registry
r = Registry(Path('install/modules'), Path('install/robots'))
print(f"  등록된 로봇 {len(r.all())}대:", ", ".join(i.display_name for i in r.all()))
for p in r.problems:
    print("  문제:", p)
PY
echo "[4/4] 시험"
"$PYTHON" -m pytest -q
cat <<'MSG'

설치 끝. 실행 방법

  콘솔      ./run.sh                     (http://127.0.0.1:8099)
  런타임    ./install/run_runtime.sh omx  또는 mycobot
  자동 시작 ./install/install_autostart.sh

MSG
