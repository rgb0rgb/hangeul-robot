"""한글 로봇 실행기 — 시작 · 멈춤 · 완전 초기화를 한 곳에서 한다.

    python tools/launcher.py start    콘솔과 등록된 로봇의 런타임을 띄운다
    python tools/launcher.py reset    전부 끄고, 막힌 것을 풀고, 다시 띄운다
    python tools/launcher.py stop     전부 끈다
    python tools/launcher.py ensure   빠진 런타임만 띄운다 (로봇을 추가한 뒤)
    python tools/launcher.py status   지금 무엇이 떠 있는지 본다
    python tools/launcher.py shortcuts  바탕화면에 시작·초기화 바로가기를 만든다(윈도우)

윈도우의 Start.bat · Reset.bat, 리눅스의 run.sh, 화면의 "서버 재시작"이
모두 이 파일을 부른다. 길이 하나여야 한쪽만 고쳐지는 일이 없다.

왜 이런 파일이 따로 있나(2026-09-24). USB가 잠깐 끊겼다 붙으면서 장치 번호가
ttyUSB0 → ttyUSB1 로 바뀌었다. 화면의 서버 재시작은 bash 스크립트가
"ttyUSB0 없음 — 건너뜀"으로 런타임을 아예 띄우지 않았고, 그 사실을 화면에
알리지도 않았다. 사람은 재시작을 눌렀는데 아무것도 되지 않았다.
그래서 이 실행기는
  · 장치를 번호가 아니라 **USB 신원(VID:PID)** 으로 찾는다
  · WSL이면 빠진 USB를 **스스로 다시 붙여** 본다 (usbipd)
  · 무엇을 띄웠고 무엇을 못 띄웠는지 **이유와 함께 남긴다** (data/run/last_report.json)
  · 죽일 때는 **이 폴더의 한글 로봇 프로세스만** 죽인다 — 포트 주인을 확인한다

**정지(비상 정지) 래치는 풀지 않는다.** 초기화는 프로그램을 새로 띄우는
일이고, 정지를 푸는 것은 사람이 화면에서 로봇을 보고 하는 일이다.
표준 라이브러리만 쓴다 — 설치가 반쯤 깨진 상태에서도 돌아야 하기 때문이다.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
RUN_DIR = ROOT / "data" / "run"
REPORT = RUN_DIR / "last_report.json"
MODULE_DIR = ROOT / "install" / "modules"
ROBOT_DIR = ROOT / "install" / "robots"
IS_WINDOWS = os.name == "nt"
CONSOLE_HOST = os.environ.get("HOST", "127.0.0.1")
CONSOLE_PORT = int(os.environ.get("PORT", "8099"))
OURS = ("hangeul_console", "hangeul_runtime")


# ── 무엇을 띄워야 하나 ───────────────────────────────────────────
def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def descriptors() -> dict[str, dict[str, Any]]:
    out = {}
    for path in sorted(MODULE_DIR.glob("*.json")):
        data = _read_json(path)
        if data.get("module_id"):
            out[str(data["module_id"])] = data
    return out


def plan() -> tuple[list[dict[str, Any]], list[str]]:
    """등록된 로봇을 런타임(포트) 단위로 묶는다. 같은 포트 = 같은 팔."""
    mods, groups, problems = descriptors(), {}, []
    for path in sorted(ROBOT_DIR.glob("*.json")):
        if path.name.endswith(".example.json"):
            continue                              # 콘솔(registry.py)과 같은 규칙
        robot = _read_json(path)
        if not robot.get("instance_id"):
            continue                              # 예제 파일 등
        name = robot.get("display_name") or robot["instance_id"]
        arm = next((m for m in robot.get("modules") or []
                    if (mods.get(m) or {}).get("module_class") == "arm"), None)
        if not arm:
            continue                              # 팔 없는 로봇은 런타임이 없다
        url = urlparse(str(robot.get("runtime_url") or mods[arm].get("runtime_url") or ""))
        if url.hostname not in ("127.0.0.1", "localhost") or not url.port:
            problems.append(f"{name}: 이 컴퓨터의 런타임이 아니라 띄우지 않습니다 ({url.geturl()})")
            continue
        group = groups.setdefault(url.port, {"port": url.port, "module": arm, "robots": []})
        if group["module"] != arm:
            problems.append(f"{name}: 포트 {url.port}를 다른 팔({group['module']})과 같이 씁니다 — "
                            "로봇 설정의 runtime_url을 나누세요")
            continue
        group["robots"].append(name)
    return [groups[p] for p in sorted(groups)], problems


# ── 장치 찾기 ───────────────────────────────────────────────────
def _usb_ids(desc: dict[str, Any]) -> list[tuple[int, int]]:
    ids = []
    for item in desc.get("usb_ids") or []:
        try:
            ids.append((int(str(item["vid"]), 16), int(str(item["pid"]), 16)))
        except (KeyError, ValueError, TypeError):
            pass
    return ids


def _serial_ports() -> list[tuple[str, int | None, int | None]]:
    """(장치, VID, PID). pyserial이 있으면 그것으로, 없으면 리눅스 sysfs로."""
    try:
        from serial.tools import list_ports
        return [(p.device, p.vid, p.pid) for p in list_ports.comports()]
    except Exception:                             # noqa: BLE001 — 없어도 돌아야 한다
        pass
    out = []
    for tty in sorted(Path("/sys/class/tty").glob("tty[UA]*")):
        dev = (tty / "device").resolve()
        for up in (dev, *dev.parents):
            vid, pid = up / "idVendor", up / "idProduct"
            if vid.exists() and pid.exists():
                out.append((f"/dev/{tty.name}", int(vid.read_text(), 16), int(pid.read_text(), 16)))
                break
    return out


def _stable(device: str) -> str:
    """리눅스: 번호(ttyUSB0) 대신 일련번호 경로(/dev/serial/by-id/…)."""
    by_id = Path("/dev/serial/by-id")
    if IS_WINDOWS or not by_id.is_dir():
        return device
    target = os.path.realpath(device)
    for link in sorted(by_id.iterdir()):
        if os.path.realpath(link) == target:
            return str(link)
    return device


def find_device(desc: dict[str, Any]) -> str:
    ids = set(_usb_ids(desc))
    ports = _serial_ports()
    for device, vid, pid in ports:
        if (vid, pid) in ids:
            return _stable(device)
    # 신원을 모르는 부품은 기술서에 적힌 이름을 믿는다(있을 때만)
    fallback = str((desc.get("device") or {}).get("windows" if IS_WINDOWS else "linux") or "")
    if fallback and not ids:
        if IS_WINDOWS and any(d.upper() == fallback.upper() for d, _, _ in ports):
            return fallback
        if not IS_WINDOWS and os.path.exists(fallback):
            return _stable(fallback)
    return ""


def _is_wsl() -> bool:
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except OSError:
        return False


def _usbipd() -> str:
    found = shutil.which("usbipd.exe")
    default = "/mnt/c/Program Files/usbipd-win/usbipd.exe"
    return found or (default if os.path.exists(default) else "")


def wsl_attach(desc: dict[str, Any]) -> str:
    """WSL이면 윈도우에 꽂혀 있는 장치를 붙여 본다. 붙였으면 빈 문자열, 아니면 이유."""
    exe = _usbipd() if (not IS_WINDOWS and _is_wsl()) else ""
    if not exe or not _usb_ids(desc):
        return "USB 장치가 보이지 않습니다 — 케이블과 전원을 확인하세요"
    last = ""
    for vid, pid in _usb_ids(desc):
        try:
            done = subprocess.run([exe, "attach", "--wsl", "--hardware-id", f"{vid:04x}:{pid:04x}"],
                                  capture_output=True, text=True, errors="replace", timeout=30,
                                  cwd="/mnt/c")
        except (OSError, subprocess.TimeoutExpired) as exc:
            last = str(exc)
            continue
        if done.returncode == 0:
            for _ in range(20):                   # 리눅스 쪽에 장치가 생길 때까지
                if find_device(desc):
                    return ""
                time.sleep(0.5)
        last = (done.stderr or done.stdout).strip().splitlines()[-1:] or [""]
        last = last[0]
    if "not shared" in last or "bind" in last:
        return ("USB 장치를 WSL에 붙이려면 한 번 공유가 필요합니다 — 윈도우 관리자 명령창에서 "
                "usbipd bind --hardware-id " + ", ".join(f"{v:04x}:{p:04x}" for v, p in _usb_ids(desc)))
    return f"USB 장치가 보이지 않습니다 — 케이블과 전원을 확인하세요 ({last or '윈도우에도 없음'})"


# ── 프로세스 ────────────────────────────────────────────────────
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _run_text(args: list[str], timeout: float = 15) -> str:
    """외부 명령의 출력을 **어떤 인코딩이 와도** 글자로 읽는다.

    윈도우의 netstat·tasklist·powershell 은 시스템 인코딩(한국어 윈도우는 CP949)으로
    답한다. 폴더 이름에 한글이 있으면 UTF-8 로 읽다가 깨져 출력이 통째로 사라졌고,
    화면의 '완전 초기화'가 아무 말 없이 죽었다(2026-09-24 윈도우 실기).
    """
    try:
        raw = subprocess.run(args, capture_output=True, timeout=timeout,
                             creationflags=_NO_WINDOW).stdout or b""
    except (OSError, subprocess.TimeoutExpired):
        return ""
    for encoding in ("utf-8", "mbcs" if IS_WINDOWS else "latin-1"):
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def python_exe() -> str:
    for candidate in (ROOT / ".venv" / "Scripts" / "python.exe", ROOT / ".venv" / "bin" / "python"):
        if candidate.exists():
            return str(candidate)
    return sys.executable


def _cmdline(pid: int) -> str:
    try:
        if IS_WINDOWS:
            return _run_text(["powershell", "-NoProfile", "-Command",
                              "[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
                              f"(Get-CimInstance Win32_Process -Filter 'ProcessId={pid}').CommandLine"]).strip()
        return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _cwd(pid: int) -> str:
    try:
        return os.path.realpath(f"/proc/{pid}/cwd") if not IS_WINDOWS else ""
    except OSError:
        return ""


def _listening_pid(port: int) -> int | None:
    """그 포트를 듣고 있는 프로세스."""
    if IS_WINDOWS:
        out = _run_text(["netstat", "-ano", "-p", "TCP"])
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[1].endswith(f":{port}") and parts[3].upper() == "LISTENING":
                return int(parts[4])
        return None
    inodes = set()
    for table in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            for line in Path(table).read_text().splitlines()[1:]:
                f = line.split()
                if f[3] == "0A" and int(f[1].rsplit(":", 1)[1], 16) == port:
                    inodes.add(f[9])
        except (OSError, IndexError, ValueError):
            pass
    if not inodes:
        return None
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            for fd in (proc / "fd").iterdir():
                link = os.readlink(fd)
                if link.startswith("socket:[") and link[8:-1] in inodes:
                    return int(proc.name)
        except OSError:
            continue
    return None


def _ours(pid: int) -> bool:
    """이 폴더의 한글 로봇 프로세스인가. 남의 프로그램은 죽이지 않는다."""
    cmd = _cmdline(pid)
    if not any(tag in cmd for tag in OURS):
        return False
    cwd = _cwd(pid)
    return not cwd or Path(cwd) == ROOT or str(ROOT) in cmd


def _alive(pid: int) -> bool:
    if IS_WINDOWS:
        out = _run_text(["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"])
        return f'"{pid}"' in out
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _kill(pid: int) -> None:
    if IS_WINDOWS:
        # /T(자식까지)를 쓰지 않는다. 화면의 "완전 초기화"는 이 실행기를 콘솔의
        # 자식으로 띄우므로, /T 로 콘솔을 끄면 실행기도 함께 죽어 아무것도 다시
        # 뜨지 않았다(2026-09-24 윈도우 실기). venv 의 python.exe 는 진짜 python 을
        # 자식으로 띄우는 대리인이라 둘 다 따로 찾아 끈다(pid 파일 + 포트 주인).
        _run_text(["taskkill", "/PID", str(pid), "/F"])
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return
    for _ in range(40):                           # uvicorn은 TERM 뒤에도 잠깐 더 답한다
        if not _alive(pid):
            return
        time.sleep(0.25)
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


def _pid_files() -> list[Path]:
    return sorted(RUN_DIR.glob("*.pid")) if RUN_DIR.exists() else []


def _all_ours() -> set[int]:
    """떠 있는 이 폴더의 한글 로봇 프로세스 — pid 파일, 포트 주인, (리눅스) 전체 목록."""
    found = set()
    for path in _pid_files():
        try:
            pid = int(json.loads(path.read_text())["pid"])
        except (OSError, ValueError, KeyError):
            continue
        if _alive(pid) and _ours(pid):
            found.add(pid)
    ports = [CONSOLE_PORT] + [g["port"] for g in plan()[0]]
    for port in ports:
        pid = _listening_pid(port)
        if pid and _ours(pid):
            found.add(pid)
    if not IS_WINDOWS:
        for proc in Path("/proc").iterdir():
            if proc.name.isdigit() and int(proc.name) != os.getpid():
                pid = int(proc.name)
                cmd = _cmdline(pid)
                if ("-m hangeul_runtime.server" in cmd or "hangeul_console.app:app" in cmd) \
                        and _cwd(pid) == str(ROOT):
                    found.add(pid)
    found.discard(os.getpid())
    return found


def _spawn(name: str, args: list[str], log: Path, pythonpath: str) -> int:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PYTHONPATH=pythonpath, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    kw: dict[str, Any] = {"cwd": str(ROOT), "stdin": subprocess.DEVNULL,
                          "stdout": open(log, "ab"), "stderr": subprocess.STDOUT, "env": env}
    if IS_WINDOWS:
        # 창 없이, 이 창과 떨어져 돈다 — Start.bat 창을 닫아도 꺼지지 않는다.
        kw["creationflags"] = (subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW)
    else:
        kw["start_new_session"] = True
    proc = subprocess.Popen(args, **kw)
    (RUN_DIR / f"{name}.pid").write_text(json.dumps({"pid": proc.pid, "args": args,
                                                     "started_at": _now()}), encoding="utf-8")
    return proc.pid


def _get(url: str, timeout: float = 2.0) -> dict[str, Any] | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as res:
            return json.loads(res.read().decode("utf-8"))
    except Exception:                             # noqa: BLE001
        return None


def _wait_json(url: str, seconds: float) -> dict[str, Any] | None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        answer = _get(url)
        if answer is not None:
            return answer
        time.sleep(0.5)
    return None


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ── 일 ─────────────────────────────────────────────────────────
def start_runtime(group: dict[str, Any]) -> dict[str, Any]:
    port, module = group["port"], group["module"]
    row = {"port": port, "module": module, "robots": group["robots"], "device": ""}
    url = f"http://127.0.0.1:{port}/api/estop-status"
    running = _get(url)
    if running is not None:
        row.update(state="already_running", device=running.get("device", ""),
                   message=_runtime_message(running))
        return row
    desc = descriptors().get(module) or {}
    simulate = bool(desc.get("simulated"))
    device = "" if simulate else find_device(desc)
    if not simulate and not device:
        reason = wsl_attach(desc)
        device = find_device(desc)
        if not device:
            row.update(state="no_device", message=reason)
            return row
    args = [python_exe(), "-m", "hangeul_runtime.server", "--module", module, "--port", str(port)]
    args += ["--simulate"] if simulate else ["--device", device]
    _spawn(f"runtime_{port}", args, ROOT / "data" / f"runtime_{module}.log",
           str(ROOT / "runtime" / "src"))
    answer = _wait_json(url, 25)
    if answer is None:
        row.update(state="failed", device=device,
                   message=f"런타임이 답하지 않습니다 — data/runtime_{module}.log 를 보세요")
        return row
    row.update(state="started", device=answer.get("device", device), message=_runtime_message(answer))
    return row


def _runtime_message(status: dict[str, Any]) -> str:
    notes = []
    if status.get("simulated"):
        notes.append("시늉 모드" + (f" — {status['simulate_reason']}" if status.get("simulate_reason") else ""))
    else:
        notes.append(f"연결됨 ({status.get('device', '')})")
    if status.get("estop_active"):
        notes.append("정지가 걸려 있습니다 — 로봇을 확인한 뒤 화면에서 '정지 해제'를 누르세요")
    return " · ".join(notes)


def start_console() -> dict[str, Any]:
    url = f"http://127.0.0.1:{CONSOLE_PORT}/api/status"
    if _get(url, timeout=3) is not None:
        return {"state": "already_running", "url": f"http://127.0.0.1:{CONSOLE_PORT}"}
    owner = _listening_pid(CONSOLE_PORT)
    if owner and not _ours(owner):
        return {"state": "port_busy",
                "message": f"다른 프로그램(PID {owner})이 {CONSOLE_PORT}번 포트를 쓰고 있습니다"}
    _spawn("console", [python_exe(), "-m", "uvicorn", "hangeul_console.app:app",
                       "--host", CONSOLE_HOST, "--port", str(CONSOLE_PORT)],
           ROOT / "data" / "console.log", str(ROOT / "console" / "src"))
    if _wait_json(url, 30) is None:
        return {"state": "failed", "message": "콘솔이 답하지 않습니다 — data/console.log 를 보세요"}
    return {"state": "started", "url": f"http://127.0.0.1:{CONSOLE_PORT}"}


def stop_all() -> list[int]:
    pids = sorted(_all_ours())
    for pid in pids:
        _kill(pid)
    for path in _pid_files():
        path.unlink(missing_ok=True)
    return pids


def clear_stuck_state() -> list[str]:
    """프로그램이 죽으며 남긴 '막힘'을 푼다. **비상 정지와 부재 모드는 그대로 둔다.**

    - 단선 래치: 새로 띄운 런타임이 실제로 다시 붙어 확인하므로 옛 기록은 필요 없다
    - 일시정지: 끝난 프로세스가 걸어 둔 것이다
    - 장치 임대: 주인이 죽은 임대가 남으면 새 콘솔이 30초 동안 막힌다
    """
    cleared = []
    for path in sorted((ROOT / "data").glob("safety_state_*.json")):
        state = _read_json(path)
        if state.get("disconnect_latched") or state.get("paused"):
            state.update(disconnect_latched=False, disconnect_reason="", paused=False)
            path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            cleared.append(f"{path.name}: 단선·일시정지 기록을 지웠습니다")
    for path in sorted((ROOT / "data" / "leases").glob("*.json")):
        path.unlink(missing_ok=True)
        cleared.append(f"장치 임대 {path.name} 해제")
    return cleared


def up(action: str) -> dict[str, Any]:
    report: dict[str, Any] = {"action": action, "at": _now(), "stopped": [], "cleared": []}
    if action == "reset":
        report["stopped"] = stop_all()
        report["cleared"] = clear_stuck_state()
    groups, problems = plan()
    report["problems"] = problems
    report["runtimes"] = [start_runtime(g) for g in groups]
    report["console"] = start_console() if action != "ensure" else {"state": "skipped"}
    report["ok"] = report["console"]["state"] in ("started", "already_running", "skipped") and \
        all(r["state"] in ("started", "already_running") for r in report["runtimes"])
    report["finished_at"] = _now()
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def print_report(report: dict[str, Any]) -> None:
    words = {"started": "시작", "already_running": "이미 떠 있음", "no_device": "장치 없음",
             "failed": "실패", "port_busy": "포트 사용 중", "skipped": "건너뜀"}
    if report.get("stopped"):
        print(f"  멈춘 프로세스 {len(report['stopped'])}개")
    for line in report.get("cleared") or []:
        print("  " + line)
    if not report.get("runtimes"):
        print("  등록된 로봇이 없습니다 — 화면의 '로봇 추가'로 등록하세요")
    for row in report.get("runtimes") or []:
        who = ", ".join(row["robots"])
        print(f"  [{words.get(row['state'], row['state'])}] {who} ({row['module']} :{row['port']})"
              + (f" — {row['message']}" if row.get("message") else ""))
    for line in report.get("problems") or []:
        print("  [확인] " + line)
    console = report.get("console") or {}
    if console.get("state") != "skipped":
        print(f"  [{words.get(console.get('state'), console.get('state'))}] 화면 "
              + (console.get("url") or console.get("message") or ""))


def make_shortcuts() -> list[str]:
    """바탕화면 바로가기. 한글 이름은 bat 안에서 만들면 글자가 깨지므로 여기서 만든다."""
    if not IS_WINDOWS or os.environ.get("HANGEUL_NO_SHORTCUTS"):
        return []
    import base64
    items = [("한글 로봇", "Start.bat"), ("한글 로봇 초기화", "Reset.bat")]
    lines = ["$s = New-Object -ComObject WScript.Shell",
             "$d = [Environment]::GetFolderPath('Desktop')"]
    for name, target in items:
        path = str(ROOT / target).replace("'", "''")
        lines += [f"$l = $s.CreateShortcut((Join-Path $d '{name}.lnk'))",
                  f"$l.TargetPath = '{path}'",
                  f"$l.WorkingDirectory = '{str(ROOT).replace(chr(39), chr(39) * 2)}'",
                  "$l.Save()"]
    encoded = base64.b64encode("\n".join(lines).encode("utf-16-le")).decode()
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                    "-EncodedCommand", encoded], check=True, capture_output=True,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return [name for name, _ in items]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=["start", "reset", "stop", "ensure", "status", "shortcuts"])
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--delay", type=float, default=0.0,
                        help="시작 전에 기다린다(화면이 스스로를 재시작할 때 응답을 보낼 틈)")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    time.sleep(max(0.0, args.delay))

    if args.action == "shortcuts":
        try:
            names = make_shortcuts()
        except (OSError, subprocess.CalledProcessError) as exc:
            print(f"  바로가기를 만들지 못했습니다 ({exc}) — 폴더의 Start.bat 을 쓰세요")
            return 0
        print("  바탕화면 바로가기: " + (", ".join(names) or "건너뜀"))
        return 0
    if args.action == "stop":
        print(f"멈춘 프로세스 {len(stop_all())}개")
        return 0
    if args.action == "status":
        groups, problems = plan()
        for g in groups:
            answer = _get(f"http://127.0.0.1:{g['port']}/api/estop-status")
            print(f"  {', '.join(g['robots'])} ({g['module']} :{g['port']}) — "
                  + (_runtime_message(answer) if answer else "꺼져 있음"))
        for line in problems:
            print("  [확인] " + line)
        print(f"  화면 :{CONSOLE_PORT} — "
              + ("떠 있음" if _get(f"http://127.0.0.1:{CONSOLE_PORT}/api/status") else "꺼져 있음"))
        return 0

    try:
        return _up_and_report(args)
    except Exception as exc:                      # noqa: BLE001 — 죽더라도 이유는 남긴다
        RUN_DIR.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps({"action": args.action, "at": _now(), "finished_at": _now(),
                                      "ok": False, "runtimes": [], "console": {"state": "failed"},
                                      "problems": [f"실행기 오류: {type(exc).__name__}: {exc}"]},
                                     ensure_ascii=False, indent=2), encoding="utf-8")
        raise


def _up_and_report(args: argparse.Namespace) -> int:
    print({"start": "한글 로봇을 시작합니다", "reset": "한글 로봇을 완전히 초기화하고 다시 시작합니다",
           "ensure": "빠진 로봇 런타임을 띄웁니다"}[args.action])
    report = up(args.action)
    print_report(report)
    console = report.get("console") or {}
    if console.get("url") and not args.no_browser and not os.environ.get("HANGEUL_NO_BROWSER"):
        webbrowser.open(console["url"])
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
