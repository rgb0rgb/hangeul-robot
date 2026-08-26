#!/usr/bin/env bash
set -euo pipefail
pkill -f "hangeul_console.app:app" || true
pkill -f "hangeul_runtime.server" || true

