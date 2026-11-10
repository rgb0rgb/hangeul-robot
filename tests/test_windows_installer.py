"""윈도우 설치 파일 — 컴맹이 받아 두 번 누르면 되는 것이 깨지지 않게 (2026-11-10).

설치 파일 자체는 윈도우와 Inno Setup이 있어야 만들어진다. 여기서는 만드는 규칙만 지킨다.
실제 설치·제거·재설치는 윈도우에서 시험했다(CHANGELOG 0.5.6).
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_windows_installer",
                                              ROOT / "tools" / "build_windows_installer.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


def test_installed_parts_are_pinned():
    """설치할 때마다 판이 달라지면 어제 되던 것이 오늘 안 된다."""
    lines = [l.split("#")[0].strip() for l in
             (ROOT / "install/windows/installer-requirements.txt").read_text("utf-8").splitlines()]
    parts = [l for l in lines if l]
    assert parts and all(re.fullmatch(r"[A-Za-z0-9_.\-]+==[0-9][0-9A-Za-z.]*", p) for p in parts), parts
    assert {p.split("==")[0].lower() for p in parts} >= {"fastapi", "uvicorn", "pyserial",
                                                          "dynamixel-sdk", "pymycobot"}


def test_embedded_python_finds_console_and_runtime():
    """내장형 파이썬은 PYTHONPATH를 무시한다 — ._pth에 없으면 콘솔·런타임이 안 뜬다."""
    assert "..\\console\\src" in build.PTH_LINES
    assert "..\\runtime\\src" in build.PTH_LINES
    assert "import site" in build.PTH_LINES


def test_uninstall_and_upgrade_keep_what_the_operator_made():
    text = build.iss_text("APP", "OUT", "ICON")
    data_line = next(l for l in text.splitlines() if l.startswith('Source: "APP\\data\\*"'))
    assert "onlyifdoesntexist" in data_line        # 판올림이 고쳐 둔 안전 범위를 덮지 않는다
    assert "uninsneveruninstall" in data_line      # 지워도 가르친 자세·안전 범위가 남는다
    deleted = re.findall(r'Name: "\{app\}\\(\w+)"', text.split("[UninstallDelete]")[1].split("[Code]")[0])
    assert "data" not in deleted and "install" not in deleted, deleted


def test_installer_asks_nothing_and_needs_no_admin():
    text = build.iss_text("APP", "OUT", "ICON")
    for line in ("PrivilegesRequired=lowest", "DisableDirPage=yes", "DisableProgramGroupPage=yes"):
        assert line in text
    assert "Korean.isl" in text
    assert "Stop.bat" in text.split("[UninstallRun]")[1]   # 켜진 채로는 파일이 지워지지 않는다


@pytest.mark.skipif(not (ROOT / "Start.bat").exists(),
                    reason="윈도우 시작 파일은 공개본에만 있다 — 설치 파일도 공개본에서 만든다")
def test_start_files_prefer_the_bundled_python():
    for name in ("Start.bat", "Reset.bat", "Stop.bat"):
        text = (ROOT / name).read_text("utf-8")
        assert 'if exist "python\\python.exe" set "PY=python\\python.exe"' in text, name
        assert '"%PY%" tools\\launcher.py' in text, name
