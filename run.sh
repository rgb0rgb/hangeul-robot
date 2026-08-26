#!/usr/bin/env bash
# Public demo launcher. Starts the console only; run runtimes explicitly when needed.
set -euo pipefail
cd "$(dirname "$0")"

mkdir -p data/instances data/leases

echo "콘솔  http://127.0.0.1:${PORT:-8099}"
PYTHONPATH=console/src exec python3 -m uvicorn hangeul_console.app:app \
  --host "${HOST:-127.0.0.1}" --port "${PORT:-8099}"

