"""허깅페이스 Space에 올릴 묶음을 만든다 — 실물 없이 화면만 보이는 시늉 모드.

왜 따로 만드는가. 허깅페이스에 올리는 것은 **저장소가 아니라 데모**다. 받는 사람이
로봇 없이 화면을 먼저 볼 수 있어야 "설치할지" 판단한다. 그래서 이 묶음에는

  - 남의 컴퓨터에서 뜻이 없는 것(운영자 데이터·시험·문서)을 넣지 않고
  - 대신 **시늉 로봇 두 대**를 미리 등록해 둔다. 빈 화면은 데모가 아니다

실물에 닿는 경로는 그대로 들어 있지만 런타임을 `--simulate`로 띄우므로
**어떤 장치에도 아무것도 보내지 않는다.**

    python3 tools/make_hf_space.py           → build/hf_space/
"""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "build" / "hf_space"

# 데모에 세울 로봇. 실물 검증된 두 계열을 그대로 쓴다 — 없는 것을 만들어 보이지 않는다.
DEMO_ROBOTS = [
    {"instance_id": "demo_omx", "display_name": "OMX (시늉 / simulated)",
     "runtime_url": "http://127.0.0.1:8601",
     "modules": ["core_a", "arm_omx", "hand_omx"], "module": "arm_omx", "port": 8601},
    {"instance_id": "demo_mycobot", "display_name": "MyCobot (시늉 / simulated)",
     "runtime_url": "http://127.0.0.1:8602",
     "modules": ["core_a", "arm_mycobot", "hand_mycobot"], "module": "arm_mycobot", "port": 8602},
]

SPACE_HEADER = """---
title: Hangeul Robot Console
emoji: 🦾
colorFrom: gray
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
license: apache-2.0
short_description: Teach-and-run console for robot arms — simulated demo, no hardware attached
---

"""

SPACE_BODY = """# Hangeul Robot — console demo

**Everything here is simulated. No device is attached and nothing is sent to any
hardware.** Two robots are pre-registered so the screen has something in it; both
runtimes run with `--simulate`.

Just as Hangeul writes every sound from a small set of letters, this console builds
what a robot can do from a small set of parts:

    parts (arm · hand · eye · ear) + motion + condition  →  a task

A part descriptor is a letter. The assembly is a syllable. **Swap a part and it
becomes a different syllable** — what the robot can do, and what has been *proven*
on it, is recomputed on the spot.

## What to look at

| | |
|---|---|
| Robot list | Parts, joints and limits come from `install/modules/*.json`, not from console code |
| Simulation notice | The console says *why* it is simulating instead of pretending |
| Configuration fingerprint | Change a part and poses taught on the old part are blocked before they run |
| Stop | Leaves from any state |

## What this demo cannot show

Motion. Nothing moves, because nothing is connected. Camera, microphone, voice,
autonomy and learned policies **do not exist yet** — not in the demo and not in the
product. Every pose in this system was taught by a person.

## Real hardware

Source, install steps and the honest "works / does not work yet" table:
see the project repository. Verified on OpenManipulator-X and MyCobot 280 M5,
by one person in one room.

**This software drives machines that exert force.** Check the joint limits against
your own robot before attaching anything real, and use it only where a person can see it.

Apache-2.0.
"""

DOCKERFILE = """# 한글 로봇 — 허깅페이스 Space (시늉 모드 전용)
FROM python:3.11-slim

# Space는 uid 1000으로 돈다. 콘솔이 data/ 아래에 써야 하므로 그 사용자로 맞춘다.
RUN useradd -m -u 1000 user
WORKDIR /app

COPY --chown=user:user requirements-space.txt .
RUN pip install --no-cache-dir -r requirements-space.txt

COPY --chown=user:user . /app
RUN mkdir -p /app/data/instances /app/data/leases && chown -R user:user /app

USER user
ENV PYTHONUNBUFFERED=1
EXPOSE 7860
CMD ["bash", "start.sh"]
"""

REQUIREMENTS = """# 시늉 모드에는 실물 로봇 패키지가 필요 없다
fastapi>=0.110
uvicorn>=0.27
"""

START = """#!/usr/bin/env bash
# 시늉 로봇 런타임을 띄우고 콘솔을 연다. 어떤 장치에도 연결하지 않는다.
set -euo pipefail
cd "$(dirname "$0")"

{runtime_lines}
sleep 2

PYTHONPATH=console/src exec python3 -m uvicorn hangeul_console.app:app \\
  --host 0.0.0.0 --port 7860
"""


def build() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    # 코드는 그대로 간다. 경로 계산이 저장소 뿌리를 기준으로 하므로 구조를 유지한다.
    for rel in ("console", "runtime", "install/modules"):
        shutil.copytree(ROOT / rel, OUT / rel,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

    (OUT / "install" / "robots").mkdir(parents=True)
    (OUT / "data" / "instances").mkdir(parents=True)
    (OUT / "data" / "leases").mkdir(parents=True)
    for name in ("tasks.json",):
        if (ROOT / "data" / name).exists():
            shutil.copy2(ROOT / "data" / name, OUT / "data" / name)
    for path in (ROOT / "data").glob("safety_limits_*.json"):
        shutil.copy2(path, OUT / "data" / path.name)

    lines = []
    for robot in DEMO_ROBOTS:
        instance = {k: robot[k] for k in ("instance_id", "display_name", "runtime_url", "modules")}
        (OUT / "install" / "robots" / f"{robot['instance_id']}.json").write_text(
            json.dumps(instance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        lines.append(
            f"PYTHONPATH=runtime/src nohup python3 -m hangeul_runtime.server "
            f"--module {robot['module']} --port {robot['port']} --simulate "
            f"> data/runtime_{robot['module']}.log 2>&1 &")

    (OUT / "Dockerfile").write_text(DOCKERFILE, encoding="utf-8")
    (OUT / "requirements-space.txt").write_text(REQUIREMENTS, encoding="utf-8")
    (OUT / "start.sh").write_text(START.format(runtime_lines="\n".join(lines)), encoding="utf-8")
    (OUT / "README.md").write_text(SPACE_HEADER + SPACE_BODY, encoding="utf-8")
    shutil.copy2(ROOT / "LICENSE", OUT / "LICENSE")

    count = sum(1 for p in OUT.rglob("*") if p.is_file())
    size = sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file())
    print(f"만들었습니다: {OUT}")
    print(f"  파일 {count}개 · {size/1024:.0f} KB · 시늉 로봇 {len(DEMO_ROBOTS)}대")
    print("  올리는 방법은 docs/PUBLISH.md 를 보십시오.")
    return 0


if __name__ == "__main__":
    sys.exit(build())
