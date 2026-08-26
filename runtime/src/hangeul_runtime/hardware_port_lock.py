"""OS 파일 락 기반 하드웨어 포트 상호 배제.

파이썬 프로세스 수준의 락(threading.Lock 등)은 서로 다른 프로세스이므로 의미가
없다 — OS 레벨 파일 락(flock)만이 프로세스 경계를 넘어 실제로 상호 배제를
보장한다. 같은 물리 장치를 가리키는 두 인스턴스(예: 같은 MyCobot을 쓰는 두 서버
프로세스)는 인스턴스 설정의 device_lock_key를 이 락의 키로 써야 한다 — device
경로가 아니라 device_lock_key를 기준으로 잠그는 이유는, 같은 장치를 가리키는
경로 표기가 여러 개일 수 있기 때문이다(예: serial 장치의 대체 심볼릭 링크).
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Optional

if os.name == "nt":
    import msvcrt
else:
    import fcntl


def _lock_path_for_key(lock_key: str) -> Path:
    safe = lock_key.replace("/", "_").replace("\\", "_").strip("_") or "default"
    return Path(tempfile.gettempdir()) / f"beom_hw_port_lock_{safe}.lock"


class HardwarePortBusyError(RuntimeError):
    """다른 프로세스가 이미 이 하드웨어 포트에 대한 락을 쥐고 있을 때 발생."""


class HardwarePortLock:
    """device_lock_key별 OS 파일 락. 같은 프로세스 내 재진입은 허용하지 않는다(1키 1소유자).

    사용:
        lock = HardwarePortLock(device_lock_key)
        lock.acquire()   # 실패 시 HardwarePortBusyError
        try:
            ...하드웨어 통신...
        finally:
            lock.release()
    """

    def __init__(self, lock_key: str) -> None:
        self.lock_key = lock_key
        self._path = _lock_path_for_key(lock_key)
        self._fd: Optional[int] = None

    def acquire(self) -> None:
        if self._fd is not None:
            return
        fd = os.open(str(self._path), os.O_CREAT | os.O_RDWR, 0o644)
        try:
            if os.name == "nt":
                os.write(fd, b"\0")
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                os.lseek(fd, 0, os.SEEK_SET)
            else:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            raise HardwarePortBusyError(
                f"{self.lock_key} is locked by another process (possibly a concurrent "
                f"Beom server instance). Lock file: {self._path}"
            )
        os.write(fd, str(os.getpid()).encode("utf-8"))
        self._fd = fd

    def release(self) -> None:
        if self._fd is None:
            return
        try:
            if os.name == "nt":
                os.lseek(self._fd, 0, os.SEEK_SET)
                msvcrt.locking(self._fd, msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
        finally:
            os.close(self._fd)
            self._fd = None

    def __enter__(self) -> "HardwarePortLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()
