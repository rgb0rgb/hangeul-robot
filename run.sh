#!/usr/bin/env bash
# 한글 로봇 시작 — 콘솔과 등록된 로봇의 런타임을 띄운다.
# 일은 tools/launcher.py 가 한다. 윈도우의 Start.bat, 화면의 "완전 초기화"와 같은 길이다.
# 장치는 번호(ttyUSB0)가 아니라 USB 신원으로 찾고, 못 띄운 것은 이유를 말한다.
set -euo pipefail
cd "$(dirname "$0")"
PYTHON="${PYTHON:-python3}"
if [ -x .venv/bin/python ]; then PYTHON="$PWD/.venv/bin/python"; fi
exec "$PYTHON" tools/launcher.py start "$@"
