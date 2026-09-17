"""Stop only Hangeul processes whose working directory is this checkout (Linux/WSL)."""
from __future__ import annotations

import os
from pathlib import Path
import signal
import time

ROOT = Path(__file__).resolve().parents[1]


def is_project_server(cwd: Path, argv: list[str], root: Path = ROOT) -> bool:
    if cwd.resolve() != root.resolve():
        return False
    return ("hangeul_console.app:app" in argv
            or any(argv[i:i + 2] == ["-m", "hangeul_runtime.server"]
                   for i in range(len(argv) - 1)))


def matches(pid: int) -> bool:
    try:
        proc = Path('/proc') / str(pid)
        argv = (proc / 'cmdline').read_bytes().decode().strip('\0').split('\0')
        return is_project_server((proc / 'cwd').resolve(strict=True), argv)
    except (OSError, UnicodeError):
        return False


def main() -> int:
    pids = [int(p.name) for p in Path('/proc').iterdir()
            if p.name.isdigit() and int(p.name) != os.getpid() and matches(int(p.name))]
    for pid in pids:
        if matches(pid):
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    deadline = time.monotonic() + 10
    while any(matches(pid) for pid in pids) and time.monotonic() < deadline:
        time.sleep(0.1)
    remaining = [pid for pid in pids if matches(pid)]
    if remaining:
        print(f"Servers still shutting down: {remaining}")
        return 1
    print(f"Stopped {len(pids)} server(s) in {ROOT}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
