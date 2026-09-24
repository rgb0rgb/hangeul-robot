#!/usr/bin/env bash
# 한글 로봇 완전 초기화 — 전부 끄고, 막힌 것을 풀고(비상 정지는 그대로), 다시 띄운다.
set -euo pipefail
cd "$(dirname "$0")"
PYTHON="${PYTHON:-python3}"
if [ -x .venv/bin/python ]; then PYTHON="$PWD/.venv/bin/python"; fi
exec "$PYTHON" tools/launcher.py reset "$@"
