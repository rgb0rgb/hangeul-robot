"""새 판 알림과 허락받은 업데이트 — GitHub Releases가 중앙 서버다 (2026-11-10).

    확인     켤 때와 하루에 한 번, 최신 릴리스의 latest.json과 서명을 받는다
    알림     새 판이면 화면 위에 띠를 띄운다. 인터넷이 없으면 조용히 넘어간다
    허락     **사람이 누르기 전에는 아무것도 받지 않는다.** 로봇이 움직이는 중이면 막는다
    검증     목록은 우리 열쇠의 서명(Ed25519)이 맞아야 믿는다. 설치 파일은 목록에 적힌
             크기·지문(SHA-256)이 맞아야 쓴다 — 서버가 털려 가짜가 올라와도 깔리지 않는다
    적용     로봇 프로그램을 끄고 설치 파일을 조용히 돌린 뒤 다시 켠다(설치 파일이 자료를 지킨다)
    되돌리기 새 판이 뜨지 않으면 지금 판의 설치 파일로 다시 깐다
    기록     data/updates/history.jsonl

설치 파일로 깐 윈도우 판(python\\python.exe·unins000.exe가 있는 곳)만 스스로 바꾼다.
git으로 받은 사본은 알림만 한다 — 그 폴더의 주인은 git이다.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

REPO = "rgb0rgb/hangeul-robot"
# 최신 릴리스의 파일은 이 주소로 바로 받을 수 있다(GitHub가 최신 릴리스로 돌려보낸다).
# HANGEUL_UPDATE_URL·HANGEUL_UPDATE_TAG_URL은 시험용이다 — 다른 서버를 가리켜도 서명은 그대로 확인한다.
MANIFEST_URL = os.environ.get("HANGEUL_UPDATE_URL") or \
    f"https://github.com/{REPO}/releases/latest/download/latest.json"
TAG_MANIFEST_URL = os.environ.get("HANGEUL_UPDATE_TAG_URL") or \
    f"https://github.com/{REPO}/releases/download/v{{version}}/latest.json"
CHECK_EVERY_S = 24 * 60 * 60
TIMEOUT_S = 10

# 릴리스 목록을 서명한 열쇠의 공개 반쪽. 비밀 반쪽은 저장소에 없다(tools/release.py 참고).
# 이 값을 바꾸면 이미 깔린 판들은 새 열쇠로 서명한 업데이트를 받지 않는다 — 함부로 바꾸지 않는다.
PUBLIC_KEY_B64 = "scOOR68NqELomDQFY/T8ybc9dAVbpGEYotP7WUsDlY4="


class UpdateError(Exception):
    """사람에게 그대로 보일 수 있는 이유를 담는다."""


def parse_version(text: str) -> tuple[int, ...]:
    parts = str(text).strip().lstrip("v").split(".")
    if not parts or not all(p.isdigit() for p in parts):
        raise UpdateError(f"판 번호를 읽지 못했습니다: {text}")
    return tuple(int(p) for p in parts)


def verify_manifest(raw: bytes, signature_b64: str, public_key_b64: str = "") -> dict[str, Any]:
    """서명이 맞을 때만 목록을 믿는다. 바이트 그대로를 검증한다(다시 직렬화하지 않는다)."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    try:
        key = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64 or PUBLIC_KEY_B64))
        key.verify(base64.b64decode(signature_b64.strip()), raw)
    except (InvalidSignature, ValueError) as exc:
        raise UpdateError("업데이트 목록의 서명이 맞지 않습니다 — 받지 않습니다") from exc
    manifest = json.loads(raw.decode("utf-8"))
    for key_name in ("version", "url", "sha256", "size"):
        if key_name not in manifest:
            raise UpdateError(f"업데이트 목록에 {key_name}이(가) 없습니다")
    parse_version(manifest["version"])
    return manifest


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _get(url: str, timeout: float = TIMEOUT_S) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "hangeul-robot-updater"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


class Updater:
    """콘솔 한 대에 하나. 상태는 메모리에, 기록과 받은 파일은 data/updates에 둔다."""

    def __init__(self, root: Path, *, fetch: Callable[[str], bytes] = _get,
                 public_key_b64: str = "", manifest_url: str = "") -> None:
        self.root = Path(root)
        self.dir = self.root / "data" / "updates"
        self.fetch = fetch
        self.public_key_b64 = public_key_b64
        self.manifest_url = manifest_url or MANIFEST_URL
        self.lock = threading.Lock()
        self.state: dict[str, Any] = {"phase": "idle", "checked_at": "", "latest": None,
                                      "reason": "", "progress": 0}

    # ── 지금 무엇인가 ──────────────────────────────────────────
    def current_version(self) -> str:
        try:
            return (self.root / "VERSION").read_text(encoding="utf-8").strip()
        except OSError:
            return "0"

    def install_kind(self) -> str:
        """windows_installer: 설치 파일로 깐 윈도우 판 — 스스로 바꿀 수 있다. source: 알림만."""
        if os.name == "nt" and (self.root / "python" / "python.exe").exists() \
                and (self.root / "unins000.exe").exists():
            return "windows_installer"
        return "source"

    def status(self, dismissed: str = "") -> dict[str, Any]:
        with self.lock:
            state = dict(self.state)
        latest = state.get("latest") or {}
        newer = False
        if latest:
            try:
                newer = parse_version(latest["version"]) > parse_version(self.current_version())
            except UpdateError:
                newer = False
        return {**state, "current": self.current_version(), "install_kind": self.install_kind(),
                "available": newer, "dismissed": bool(newer and dismissed == latest.get("version")),
                "can_apply": newer and self.install_kind() == "windows_installer"}

    # ── 확인 ────────────────────────────────────────────────
    def check(self) -> dict[str, Any]:
        """새 판이 있는지 본다. 실패해도 예외를 올리지 않는다 — 인터넷이 없는 곳이 흔하다."""
        with self.lock:
            if self.state["phase"] in ("downloading", "applying"):
                return dict(self.state)
            self.state["phase"] = "checking"
        try:
            raw = self.fetch(self.manifest_url)
            sig = self.fetch(self.manifest_url + ".sig").decode("ascii")
            manifest = verify_manifest(raw, sig, self.public_key_b64)
            with self.lock:
                self.state.update(phase="idle", latest=manifest, reason="",
                                  checked_at=datetime.now().isoformat(timespec="seconds"))
        except UpdateError as exc:
            with self.lock:
                self.state.update(phase="idle", reason=str(exc),
                                  checked_at=datetime.now().isoformat(timespec="seconds"))
        except Exception as exc:                  # noqa: BLE001 — 인터넷 없음·서버 없음
            with self.lock:
                self.state.update(phase="idle", reason=f"새 판을 확인하지 못했습니다 ({type(exc).__name__})",
                                  checked_at=datetime.now().isoformat(timespec="seconds"))
        return dict(self.state)

    def check_in_background(self, every_s: float = CHECK_EVERY_S) -> threading.Thread:
        def loop() -> None:
            while True:
                self.check()
                time.sleep(every_s)
        thread = threading.Thread(target=loop, name="update-check", daemon=True)
        thread.start()
        return thread

    # ── 받기 ────────────────────────────────────────────────
    def _download(self, manifest: dict[str, Any]) -> Path:
        self.dir.mkdir(parents=True, exist_ok=True)
        name = Path(str(manifest["url"]).split("?")[0]).name
        if not name.endswith(".exe") or "/" in name or "\\" in name:
            raise UpdateError("업데이트 목록의 설치 파일 이름이 이상합니다")
        target = self.dir / name
        if target.exists() and target.stat().st_size == int(manifest["size"]) \
                and sha256_of(target) == manifest["sha256"]:
            return target
        data = self.fetch(manifest["url"])
        if len(data) != int(manifest["size"]):
            raise UpdateError("받은 설치 파일의 크기가 목록과 다릅니다 — 쓰지 않습니다")
        partial = target.with_suffix(".part")
        partial.write_bytes(data)
        if sha256_of(partial) != manifest["sha256"]:
            partial.unlink(missing_ok=True)
            raise UpdateError("받은 설치 파일의 지문이 목록과 다릅니다 — 쓰지 않습니다")
        partial.replace(target)
        return target

    def _rollback_copy(self) -> Path | None:
        """지금 판의 설치 파일. 새 판이 뜨지 않을 때 되돌릴 길이다. 못 구하면 None."""
        current = self.current_version()
        try:
            url = TAG_MANIFEST_URL.format(version=current)
            raw = self.fetch(url)
            manifest = verify_manifest(raw, self.fetch(url + ".sig").decode("ascii"),
                                       self.public_key_b64)
            if manifest["version"] != current:
                return None
            return self._download(manifest)
        except Exception:                          # noqa: BLE001 — 되돌릴 길이 없어도 업데이트는 막지 않는다
            return None

    # ── 적용 ────────────────────────────────────────────────
    def apply(self, *, operator: str, busy_reasons: list[str], spawn: Callable[..., Any] | None = None
              ) -> dict[str, Any]:
        """허락받은 업데이트. 받고 검증한 뒤, 콘솔 밖의 도우미가 끄고-깔고-켠다."""
        status = self.status()
        if not status["available"]:
            raise UpdateError("받을 새 판이 없습니다")
        if self.install_kind() != "windows_installer":
            raise UpdateError("이 사본은 설치 파일로 깐 것이 아니라 스스로 바꾸지 않습니다 — git으로 받으세요")
        if busy_reasons:
            raise UpdateError("로봇이 일하는 중이라 업데이트하지 않습니다: " + ", ".join(busy_reasons))
        with self.lock:
            if self.state["phase"] in ("downloading", "applying"):
                raise UpdateError("이미 업데이트를 진행하고 있습니다")
            self.state.update(phase="downloading", reason="")
        manifest = status["latest"]
        try:
            installer = self._download(manifest)
            rollback = self._rollback_copy()
        except UpdateError as exc:
            with self.lock:
                self.state.update(phase="idle", reason=str(exc))
            self._record(operator, manifest["version"], "refused", str(exc))
            raise
        except Exception as exc:                   # noqa: BLE001
            reason = f"설치 파일을 받지 못했습니다 ({type(exc).__name__})"
            with self.lock:
                self.state.update(phase="idle", reason=reason)
            self._record(operator, manifest["version"], "failed", reason)
            raise UpdateError(reason) from exc
        command = self._helper_command(installer, rollback, manifest["version"])
        with self.lock:
            self.state.update(phase="applying")
        self._record(operator, manifest["version"], "started",
                     "되돌릴 설치 파일 있음" if rollback else "되돌릴 설치 파일 없음")
        (spawn or self._spawn_detached)(command)
        return {"success": True, "version": manifest["version"], "rollback_ready": rollback is not None,
                "message": "업데이트를 설치합니다. 한글 로봇이 잠시 꺼졌다가 1~2분 안에 다시 켜집니다."}

    def _helper_command(self, installer: Path, rollback: Path | None, version: str) -> list[str]:
        """콘솔이 꺼져도 끝까지 가는 도우미(tools/apply_update.py)를 돌릴 명령.

        설치 파일이 프로그램 폴더의 파이썬을 바꾸므로, 그 파이썬의 기본 파일만 data\\updates로
        복사해 그것으로 돌린다. 경로에 한글이 있어도 되도록 bat을 쓰지 않는다(cmd는 UTF-8 bat의
        한글을 잘못 읽는다 — 0.5.2).
        """
        import shutil
        src = self.root / "python"
        dst = self.dir / "helper_python"
        shutil.rmtree(dst, ignore_errors=True)
        dst.mkdir(parents=True)
        for item in src.iterdir():
            if item.is_file() and item.suffix.lower() in (".exe", ".dll", ".pyd", ".zip", ".cat"):
                shutil.copy2(item, dst / item.name)
        # 복사본은 표준 라이브러리만 본다 — site-packages도 콘솔 코드도 필요 없다
        for pth in dst.glob("*._pth"):
            pth.unlink()
        (dst / f"python{sys.version_info.major}{sys.version_info.minor}._pth").write_text(
            f"python{sys.version_info.major}{sys.version_info.minor}.zip\r\n.\r\n", encoding="ascii")
        script = self.dir / "apply_update.py"
        shutil.copy2(self.root / "tools" / "apply_update.py", script)
        (self.dir / "last_result.json").unlink(missing_ok=True)
        command = [str(dst / "python.exe"), str(script), "--app", str(self.root),
                   "--installer", str(installer), "--version", version]
        if rollback:
            command += ["--rollback", str(rollback)]
        return command

    def _spawn_detached(self, command: list[str]) -> None:
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) \
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen(command, cwd=str(self.dir), creationflags=flags, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)

    # ── 기록 ────────────────────────────────────────────────
    def last_result(self) -> dict[str, Any]:
        """지난 업데이트가 어떻게 끝났는지 — 다시 켜진 콘솔이 한 번 읽어 화면에 알린다."""
        path = self.dir / "last_result.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        path.unlink(missing_ok=True)
        self._record("helper", str(data.get("version", "")), str(data.get("result", "")),
                     f"설치 뒤 판 {self.current_version()}")
        return data

    def _record(self, operator: str, version: str, result: str, detail: str) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        entry = {"at": datetime.now().isoformat(timespec="seconds"), "operator": operator,
                 "from": self.current_version(), "to": version, "result": result, "detail": detail}
        with open(self.dir / "history.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
