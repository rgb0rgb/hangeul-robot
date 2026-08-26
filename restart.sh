#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
./stop.sh || true
exec ./run.sh

