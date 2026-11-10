"""릴리스 만들기 — 설치 파일과, 콘솔이 믿는 서명된 업데이트 목록(latest.json)을 함께 낸다.

    python3 tools/release.py keygen                  처음 한 번: 서명 열쇠를 만든다
    python3 tools/release.py sign [--safety-change]  build/windows의 설치 파일로 목록을 만들고 서명한다
    GITHUB_TOKEN=… python3 tools/release.py upload    GitHub Releases에 v<판>으로 올린다

**비밀 열쇠는 저장소에 두지 않는다**(~/.config/hangeul-robot/release_ed25519.pem, 권한 600).
잃어버리면 이미 깔린 판들이 새 업데이트를 믿지 않는다 — 따로 백업한다. 새 열쇠로 바꾸려면
사용자가 설치 파일을 한 번 손으로 다시 깔아야 한다(콘솔에 새 공개 열쇠가 들어가야 하므로).

목록에 적는 것: 판, 설치 파일 주소·크기·지문(SHA-256), 바뀐 것(CHANGELOG의 그 판 부분),
안전 동작이 바뀌는 판인지. 콘솔(updater.py)은 서명이 맞을 때만 목록을 믿고, 받은 설치 파일이
크기·지문과 맞을 때만 쓴다.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = "rgb0rgb/hangeul-robot"
KEY_PATH = Path(os.environ.get("HANGEUL_RELEASE_KEY",
                               Path.home() / ".config" / "hangeul-robot" / "release_ed25519.pem"))


def _version() -> str:
    return (ROOT / "VERSION").read_text(encoding="utf-8").strip()


def _changelog_section(version: str) -> str:
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(rf"^# {re.escape(version)} .*?(?=^# |\Z)", text, flags=re.M | re.S)
    if not match:
        raise SystemExit(f"CHANGELOG.md에 {version} 부분이 없습니다 — 바뀐 것을 먼저 적으세요")
    return match.group(0).strip()


def keygen() -> int:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    if KEY_PATH.exists():
        raise SystemExit(f"이미 열쇠가 있습니다: {KEY_PATH} — 덮어쓰면 깔린 판들이 업데이트를 받지 못합니다")
    KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    key = Ed25519PrivateKey.generate()
    KEY_PATH.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                           serialization.NoEncryption()))
    os.chmod(KEY_PATH, 0o600)
    public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    print(f"비밀 열쇠: {KEY_PATH} (따로 백업하세요)")
    print(f"공개 열쇠(updater.PUBLIC_KEY_B64에 넣는다): {base64.b64encode(public).decode()}")
    return 0


def _private_key():
    from cryptography.hazmat.primitives import serialization
    try:
        return serialization.load_pem_private_key(KEY_PATH.read_bytes(), password=None)
    except FileNotFoundError:
        raise SystemExit(f"서명 열쇠가 없습니다: {KEY_PATH}")


def release_dir(version: str) -> Path:
    return ROOT / "build" / "release" / f"v{version}"


def sign(safety_change: bool, notes_ko: str) -> int:
    version = _version()
    exe = ROOT / "build" / "windows" / f"HangeulRobot-Setup-{version}.exe"
    if not exe.exists():
        raise SystemExit(f"설치 파일이 없습니다: {exe} — tools/build_windows_installer.py 먼저")
    out = release_dir(version)
    out.mkdir(parents=True, exist_ok=True)
    shutil.copy2(exe, out / exe.name)
    data = exe.read_bytes()
    manifest = {
        "version": version,
        "url": f"https://github.com/{REPO}/releases/download/v{version}/{exe.name}",
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "safety_change": bool(safety_change),
        "notes_ko": notes_ko,
        "notes_en": _changelog_section(version),
    }
    raw = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
    signature = _private_key().sign(raw)
    (out / "latest.json").write_bytes(raw)
    (out / "latest.json.sig").write_text(base64.b64encode(signature).decode("ascii") + "\n", encoding="ascii")
    print(f"만들었습니다: {out} (설치 파일 · latest.json · latest.json.sig)")
    return 0


def _api(method: str, url: str, token: str, body: bytes | None = None,
         content_type: str = "application/json") -> dict:
    request = urllib.request.Request(url, data=body, method=method, headers={
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
        "Content-Type": content_type, "User-Agent": "hangeul-robot-release"})
    with urllib.request.urlopen(request, timeout=300) as response:
        return json.loads(response.read() or b"{}")


def upload() -> int:
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise SystemExit("GITHUB_TOKEN이 없습니다. 웹에서 올리려면 build/release/v<판>의 세 파일을 "
                         "Releases → Draft a new release(태그 v<판>)에 끌어다 놓으세요")
    version = _version()
    out = release_dir(version)
    files = [out / f"HangeulRobot-Setup-{version}.exe", out / "latest.json", out / "latest.json.sig"]
    missing = [f.name for f in files if not f.exists()]
    if missing:
        raise SystemExit("먼저 sign 하세요 — 없음: " + ", ".join(missing))
    manifest = json.loads((out / "latest.json").read_text(encoding="utf-8"))
    release = _api("POST", f"https://api.github.com/repos/{REPO}/releases", token, json.dumps({
        "tag_name": f"v{version}", "target_commitish": "main", "name": f"한글 로봇 {version}",
        "body": manifest["notes_en"], "draft": False, "prerelease": False}).encode("utf-8"))
    upload_url = release["upload_url"].split("{")[0]
    for path in files:
        kind = "application/octet-stream" if path.suffix == ".exe" else "application/json" \
            if path.suffix == ".json" else "text/plain"
        _api("POST", f"{upload_url}?name={path.name}", token, path.read_bytes(), kind)
        print(f"  올림: {path.name}")
    print(f"릴리스: {release['html_url']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("keygen")
    s = sub.add_parser("sign")
    s.add_argument("--safety-change", action="store_true", help="안전 동작이 바뀌는 판(화면이 강조한다)")
    s.add_argument("--notes-ko", default="", help="화면에 먼저 보일 한국어 한 줄 요약")
    sub.add_parser("upload")
    args = parser.parse_args(argv)
    if args.action == "keygen":
        return keygen()
    if args.action == "sign":
        return sign(args.safety_change, args.notes_ko)
    return upload()


if __name__ == "__main__":
    sys.exit(main())
