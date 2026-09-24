#!/usr/bin/env bash
# 한글 로봇 정지 — 이 폴더의 콘솔과 로봇 런타임만 끈다(포트 주인을 확인한다).
set -euo pipefail
cd "$(dirname "$0")"
PYTHON="${PYTHON:-python3}"
if [ -x .venv/bin/python ]; then PYTHON="$PWD/.venv/bin/python"; fi
exec "$PYTHON" tools/launcher.py stop "$@"
