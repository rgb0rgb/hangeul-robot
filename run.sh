#!/usr/bin/env bash
# Public demo launcher. Starts the console only; run runtimes explicitly when needed.
set -euo pipefail
cd "$(dirname "$0")"
PYTHON="${PYTHON:-python3}"
if [ -x .venv/bin/python ]; then PYTHON="$PWD/.venv/bin/python"; fi

mkdir -p data/instances data/leases

echo "콘솔  http://127.0.0.1:${PORT:-8099}"
PYTHONPATH=console/src exec "$PYTHON" -m uvicorn hangeul_console.app:app \
  --host "${HOST:-127.0.0.1}" --port "${PORT:-8099}"

