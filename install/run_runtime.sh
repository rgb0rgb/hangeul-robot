#!/usr/bin/env bash
# 로봇 런타임 실행 — 로봇 한 대에 하나씩 띄운다
#
# 장치 이름과 포트는 **부품 기술서가 들고 있다.** 여기에 로봇 목록을 적지 않는다.
# 이전에는 case 문에 omx|mycobot을 박아 두어, 로봇이 늘 때마다 이 파일을 고쳐야
# 했다(xArm 반증 시험 20260817에서 드러남).
set -euo pipefail
cd "$(dirname "$0")/.."

MODULE="${1:-}"
if [ -z "$MODULE" ]; then
  echo "사용법: $0 <부품ID|별칭> [--simulate]"
  echo "붙일 수 있는 팔:"
  PYTHONPATH=console/src python3 - <<'PY'
import json, pathlib
for p in sorted(pathlib.Path("install/modules").glob("*.json")):
    d = json.loads(p.read_text(encoding="utf-8"))
    if d.get("module_class") == "arm":
        print(f"  {p.stem:14s} {d.get('display_name','')}")
PY
  exit 2
fi
shift || true

# 별칭(omx) → 부품 ID(arm_omx). 기술서 파일 이름이 곧 부품 ID다.
if [ ! -f "install/modules/${MODULE}.json" ] && [ -f "install/modules/arm_${MODULE}.json" ]; then
  MODULE="arm_${MODULE}"
fi
if [ ! -f "install/modules/${MODULE}.json" ]; then
  echo "그런 부품 기술서가 없습니다: install/modules/${MODULE}.json" >&2
  exit 2
fi

# 기술서에서 장치와 포트를 읽는다 (DEVICE/PORT 환경변수로 덮어쓸 수 있다)
eval "$(MODULE="$MODULE" python3 - <<'PY'
import json, os, sys
from urllib.parse import urlparse
d = json.load(open(f"install/modules/{os.environ['MODULE']}.json", encoding="utf-8"))
plat = "windows" if sys.platform.startswith("win") else "linux"
device = (d.get("device") or {}).get(plat, "")
port = urlparse(d.get("runtime_url") or "").port or 8501
print(f'DESC_DEVICE={device!r}')
print(f'DESC_PORT={port}')
PY
)"

DEVICE="${DEVICE:-$DESC_DEVICE}"
PORT="${PORT:-$DESC_PORT}"

echo "런타임 ${MODULE} — 장치 ${DEVICE:-(없음)} · 포트 ${PORT}"
PYTHONPATH=runtime/src exec python3 -m hangeul_runtime.server \
  --module "$MODULE" --device "$DEVICE" --port "$PORT" "$@"
