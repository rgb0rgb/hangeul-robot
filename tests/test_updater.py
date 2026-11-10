"""새 판 알림과 허락받은 업데이트 (2026-11-10).

지키는 것: 사람이 허락하기 전에는 받지 않는다 · 서명이 틀린 목록은 믿지 않는다 · 크기·지문이
다른 설치 파일은 쓰지 않는다 · 로봇이 일하는 중에는 하지 않는다 · 새 판이 뜨지 않으면 되돌린다.
"""
from __future__ import annotations

import base64
import hashlib
import http.server
import json
import os
import stat
import sys
import threading
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from hangeul_console import updater as up

ROOT = Path(__file__).resolve().parents[1]
KEY = Ed25519PrivateKey.generate()
PUB = base64.b64encode(KEY.public_key().public_bytes(serialization.Encoding.Raw,
                                                     serialization.PublicFormat.Raw)).decode()
EXE = b"MZ fake installer bytes" * 100


def signed(manifest: dict) -> tuple[bytes, bytes]:
    raw = json.dumps(manifest, ensure_ascii=False).encode("utf-8")
    return raw, base64.b64encode(KEY.sign(raw))


def manifest(version="9.9.9", data=EXE, **extra):
    return {"version": version, "url": f"https://example/releases/download/v{version}/HangeulRobot-Setup-{version}.exe",
            "size": len(data), "sha256": hashlib.sha256(data).hexdigest(), "safety_change": False,
            "notes_ko": "", "notes_en": "notes", **extra}


class Server:
    """가짜 GitHub — 주소별로 바이트를 돌려준다. 없으면 인터넷이 끊긴 것처럼 실패한다."""

    def __init__(self):
        self.files: dict[str, bytes] = {}
        self.asked: list[str] = []

    def put_release(self, m: dict, data: bytes = EXE, url: str = up.MANIFEST_URL):
        raw, sig = signed(m)
        self.files[url], self.files[url + ".sig"] = raw, sig
        self.files[m["url"]] = data

    def fetch(self, url: str) -> bytes:
        self.asked.append(url)
        if url not in self.files:
            raise OSError("no network")
        return self.files[url]


@pytest.fixture
def app_root(tmp_path):
    (tmp_path / "VERSION").write_text("1.0.0\n", encoding="utf-8")
    return tmp_path


def make(app_root, server, kind="windows_installer", monkeypatch=None):
    u = up.Updater(app_root, fetch=server.fetch, public_key_b64=PUB)
    if monkeypatch:
        monkeypatch.setattr(u, "install_kind", lambda: kind)
        monkeypatch.setattr(u, "_helper_command", lambda inst, rb, v: ["helper", str(inst), str(rb), v])
    return u


# ── 목록과 서명 ────────────────────────────────────────────────
def test_versions_compare_as_numbers():
    assert up.parse_version("0.5.10") > up.parse_version("0.5.9")
    assert up.parse_version("v1.0.0") == (1, 0, 0)
    with pytest.raises(up.UpdateError):
        up.parse_version("1.0.0-beta")


def test_a_correctly_signed_list_is_trusted():
    raw, sig = signed(manifest())
    assert up.verify_manifest(raw, sig.decode(), PUB)["version"] == "9.9.9"


@pytest.mark.parametrize("tamper", ["byte", "other_key", "missing_field"])
def test_a_tampered_list_is_refused(tamper):
    m = manifest()
    raw, sig = signed(m)
    if tamper == "byte":
        raw = raw.replace(b"9.9.9", b"9.9.8")                 # 한 글자만 바꿔도
    elif tamper == "other_key":
        sig = base64.b64encode(Ed25519PrivateKey.generate().sign(raw))
    else:
        del m["sha256"]
        raw, sig = signed(m)
    with pytest.raises(up.UpdateError):
        up.verify_manifest(raw, sig.decode(), PUB)


def test_the_shipped_public_key_is_a_real_key():
    assert len(base64.b64decode(up.PUBLIC_KEY_B64)) == 32


# ── 확인 ──────────────────────────────────────────────────────
def test_a_newer_signed_release_is_announced(app_root):
    s = Server(); s.put_release(manifest("1.0.1"))
    u = make(app_root, s)
    u.check()
    status = u.status()
    assert status["available"] and status["latest"]["version"] == "1.0.1"
    assert s.asked == [up.MANIFEST_URL, up.MANIFEST_URL + ".sig"]   # 설치 파일은 받지 않았다


def test_the_same_or_older_release_is_not_announced(app_root):
    s = Server(); s.put_release(manifest("1.0.0"))
    u = make(app_root, s); u.check()
    assert not u.status()["available"]


def test_no_internet_is_quiet(app_root):
    u = make(app_root, Server())
    u.check()                                                  # 예외를 올리지 않는다
    status = u.status()
    assert not status["available"] and "확인하지 못했습니다" in status["reason"]


def test_a_forged_release_is_never_announced(app_root):
    s = Server(); s.put_release(manifest("1.0.1"))
    s.files[up.MANIFEST_URL + ".sig"] = base64.b64encode(Ed25519PrivateKey.generate().sign(s.files[up.MANIFEST_URL]))
    u = make(app_root, s); u.check()
    assert not u.status()["available"] and "서명" in u.status()["reason"]


def test_dismissed_version_stays_quiet(app_root):
    s = Server(); s.put_release(manifest("1.0.1"))
    u = make(app_root, s); u.check()
    assert u.status(dismissed="1.0.1")["dismissed"] is True
    assert u.status(dismissed="1.0.0")["dismissed"] is False


# ── 적용 ──────────────────────────────────────────────────────
def test_a_source_copy_only_announces(app_root):
    s = Server(); s.put_release(manifest("1.0.1"))
    u = make(app_root, s); u.check()
    assert u.install_kind() == "source" and u.status()["can_apply"] is False
    with pytest.raises(up.UpdateError, match="git"):
        u.apply(operator="t", busy_reasons=[])


def test_busy_robot_refuses_and_downloads_nothing(app_root, monkeypatch):
    s = Server(); s.put_release(manifest("1.0.1"))
    u = make(app_root, s, monkeypatch=monkeypatch); u.check()
    with pytest.raises(up.UpdateError, match="일하는 중"):
        u.apply(operator="t", busy_reasons=["로봇1 실행"])
    assert manifest("1.0.1")["url"] not in s.asked


@pytest.mark.parametrize("bad", ["size", "sha"])
def test_an_installer_that_does_not_match_the_list_is_not_used(app_root, monkeypatch, bad):
    m = manifest("1.0.1")
    s = Server(); s.put_release(m, data=EXE + b"x" if bad == "size" else EXE[:-1] + b"y")
    u = make(app_root, s, monkeypatch=monkeypatch); u.check()
    spawned = []
    with pytest.raises(up.UpdateError, match="크기" if bad == "size" else "지문"):
        u.apply(operator="t", busy_reasons=[], spawn=spawned.append)
    assert spawned == []
    assert not list((app_root / "data" / "updates").glob("*.exe"))


def test_a_good_update_hands_over_with_a_rollback_copy(app_root, monkeypatch):
    s = Server()
    s.put_release(manifest("1.0.1"))
    current = manifest("1.0.0", data=b"MZ current installer")
    s.put_release(current, data=b"MZ current installer", url=up.TAG_MANIFEST_URL.format(version="1.0.0"))
    u = make(app_root, s, monkeypatch=monkeypatch); u.check()
    spawned = []
    answer = u.apply(operator="screen", busy_reasons=[], spawn=spawned.append)
    assert answer["success"] and answer["rollback_ready"]
    _, installer, rollback, version = spawned[0]
    assert Path(installer).read_bytes() == EXE and Path(rollback).read_bytes() == b"MZ current installer"
    assert version == "1.0.1"
    history = [json.loads(l) for l in (app_root / "data/updates/history.jsonl").read_text("utf-8").splitlines()]
    assert history[-1]["result"] == "started" and history[-1]["operator"] == "screen"


# ── 화면 API ──────────────────────────────────────────────────
def test_the_screen_must_confirm(client):
    assert client.post("/api/update/apply", json={}).json()["success"] is False


def test_the_screen_refuses_while_a_robot_runs(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from hangeul_console import app as app_mod
    from hangeul_console.device_lease import LeaseBook
    from hangeul_console.registry import Registry

    robots = tmp_path / "robots"; robots.mkdir()
    (robots / "r1.json").write_text(json.dumps({"instance_id": "r1", "display_name": "시험 로봇",
                                                "runtime_url": "http://127.0.0.1:9",
                                                "modules": ["core_a", "arm_omx", "hand_omx"]}), encoding="utf-8")
    monkeypatch.setattr(app_mod, "ROBOT_CONFIG_DIR", robots)
    monkeypatch.setattr(app_mod, "registry", Registry(app_mod.MODULE_DIR, robots))
    monkeypatch.setattr(app_mod, "INSTANCE_DIR", tmp_path / "instances")
    monkeypatch.setattr(app_mod, "CONSOLE_STATE", tmp_path / "console.json")
    monkeypatch.setattr(app_mod, "leases", LeaseBook(tmp_path / "leases"))
    client = TestClient(app_mod.app)
    app_mod._store("r1").update_runtime(run_state="실행")
    monkeypatch.setattr(app_mod.updater, "status", lambda dismissed="": {
        "available": True, "can_apply": True, "current": "1.0.0", "latest": {"version": "1.0.1"}})
    answer = client.post("/api/update/apply", json={"confirmed": True}).json()
    assert answer["success"] is False and "일하는 중" in answer["error"]


# ── 도우미 (tools/apply_update.py) ─────────────────────────────
def _script(path: Path, body: str) -> Path:
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


@pytest.fixture
def console_port():
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.end_headers(); self.wfile.write(b"{}")

        def log_message(self, *a):
            pass
    httpd = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd.server_address[1]
    httpd.shutdown()


def _helper():
    import importlib.util
    spec = importlib.util.spec_from_file_location("apply_update", ROOT / "tools" / "apply_update.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


@pytest.mark.skipif(os.name == "nt", reason="가짜 설치 파일을 sh로 만든다")
def test_helper_applies_and_reports(tmp_path, console_port):
    app = tmp_path / "app"; (app / "python").mkdir(parents=True); (app / "VERSION").write_text("1.0.0")
    _script(app / "python" / "python.exe", "exit 0\n")
    out = tmp_path / "updates"; out.mkdir()
    new = _script(out / "new.exe", f'echo 1.0.1 > "{app}/VERSION"\n')
    assert _helper().main(["--app", str(app), "--installer", str(new), "--version", "1.0.1",
                           "--port", str(console_port), "--wait", "0"]) == 0
    assert json.loads((out / "last_result.json").read_text("utf-8"))["result"] == "applied"


@pytest.mark.skipif(os.name == "nt", reason="가짜 설치 파일을 sh로 만든다")
def test_helper_rolls_back_when_the_new_version_did_not_land(tmp_path, console_port):
    app = tmp_path / "app"; (app / "python").mkdir(parents=True); (app / "VERSION").write_text("1.0.0")
    _script(app / "python" / "python.exe", "exit 0\n")
    out = tmp_path / "updates"; out.mkdir()
    broken = _script(out / "new.exe", "exit 1\n")                         # 설치가 깨졌다
    back = _script(out / "old.exe", f'echo rolled > "{tmp_path}/rollback_ran"\n')
    assert _helper().main(["--app", str(app), "--installer", str(broken), "--version", "1.0.1",
                           "--rollback", str(back), "--port", str(console_port), "--wait", "0"]) == 1
    assert (tmp_path / "rollback_ran").exists()
    assert json.loads((out / "last_result.json").read_text("utf-8"))["result"].startswith("rolled_back")


def test_the_helpers_result_is_picked_up_when_the_screen_asks(client, monkeypatch, tmp_path):
    """도우미는 새 콘솔이 켜진 **뒤에** 결과를 쓴다 — 켜질 때 한 번만 읽으면 놓친다."""
    from hangeul_console import app as app_mod
    monkeypatch.setattr(app_mod, "updater", up.Updater(tmp_path))
    (tmp_path / "VERSION").write_text("1.0.1", encoding="utf-8")
    (tmp_path / "data" / "updates").mkdir(parents=True)
    (tmp_path / "data" / "updates" / "last_result.json").write_text(
        json.dumps({"result": "rolled_back (not_installed)", "version": "1.0.2"}), encoding="utf-8")
    client.get("/api/update/status")
    assert not (tmp_path / "data" / "updates" / "last_result.json").exists()
    assert app_mod._console().get("update_dismissed") == "1.0.2"     # 실패한 판은 다시 권하지 않는다
    history = (tmp_path / "data" / "updates" / "history.jsonl").read_text("utf-8")
    assert "rolled_back" in history
