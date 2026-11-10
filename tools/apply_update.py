"""업데이트 도우미 — 콘솔이 허락받은 업데이트를 넘기면, 콘솔이 꺼진 뒤에도 끝까지 간다.

콘솔(updater.py)이 이 파일과 파이썬 기본 파일을 data\\updates 로 복사해 그 파이썬으로 돌린다.
설치 파일이 프로그램 폴더의 파이썬을 바꾸는 동안 그 파이썬으로는 돌 수 없기 때문이다.
표준 라이브러리만 쓴다.

    1. 콘솔이 응답을 보낼 틈을 두고 기다린다
    2. 새 설치 파일을 조용히 돌린다(설치 파일이 먼저 로봇 프로그램을 끄고, 자료는 지킨다)
    3. VERSION이 새 판이고 화면(콘솔)이 답하면 성공
       — 로봇 USB가 빠져 있어 실행기가 '장치 없음'을 내는 것은 실패가 아니다
    4. 아니면 지금 판의 설치 파일로 되돌린다
    5. 결과를 last_result.json에 남긴다 — 다시 켜진 콘솔이 읽어 화면에 알린다
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _run(args: list[str], cwd: Path, timeout: float) -> int:
    try:
        return subprocess.run(args, cwd=str(cwd), timeout=timeout, creationflags=NO_WINDOW,
                              stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL).returncode
    except (OSError, subprocess.TimeoutExpired):
        return -1


def _console_answers(port: int, seconds: float) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=3):
                return True
        except Exception:                           # noqa: BLE001
            time.sleep(2)
    return False


def _version(app: Path) -> str:
    try:
        return (app / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _start(app: Path) -> None:
    """실행기로 콘솔·런타임을 다시 띄운다. 돌려준 코드는 보지 않는다(장치 없음도 정상 기동이다)."""
    _run([str(app / "python" / "python.exe"), str(app / "tools" / "launcher.py"), "start", "--no-browser"],
         app, timeout=180)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", required=True)
    parser.add_argument("--installer", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--rollback", default="")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8099")))
    parser.add_argument("--wait", type=float, default=3.0)
    args = parser.parse_args(argv)
    app, out = Path(args.app), Path(args.installer).parent
    log = out / "update.log"

    time.sleep(args.wait)
    _run([args.installer, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", f"/LOG={log}"], app, timeout=900)
    result = "applied"
    if _version(app) == args.version:
        _start(app)
        if not _console_answers(args.port, 90):
            result = "console_silent"
    else:
        result = "not_installed"
    if result != "applied":
        if args.rollback and Path(args.rollback).exists():
            _run([args.rollback, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], app, timeout=900)
            _start(app)
            result = f"rolled_back ({result})"
        else:
            result = f"failed_no_rollback ({result})"
    (out / "last_result.json").write_text(
        json.dumps({"result": result, "version": args.version, "now": _version(app)}, ensure_ascii=False),
        encoding="utf-8")
    return 0 if result == "applied" else 1


if __name__ == "__main__":
    sys.exit(main())
