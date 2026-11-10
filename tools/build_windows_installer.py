"""윈도우 설치 파일(HangeulRobot-Setup-<판>.exe)을 만든다 — WSL에서 실행한다.

    python3 tools/build_windows_installer.py

받는 사람이 할 일은 **파일 하나를 받아 두 번 누르는 것**뿐이어야 한다. 그래서
  · 파이썬을 따로 설치하지 않는다 — 파이썬 공식 내장형(embeddable)을 프로그램 폴더에 넣는다
  · 인터넷이 없어도 된다 — 필요한 부품을 설치 파일 안에 미리 넣는다(판 고정:
    install/windows/installer-requirements.txt)
  · 관리자 권한을 묻지 않는다 — 사용자 폴더(%LOCALAPPDATA%\\Programs\\HangeulRobot)에 깐다
  · 설치 위치를 묻지 않는다

부품은 **윈도우의 그 파이썬으로** 받는다. 리눅스에서 윈도우용을 대신 받으면 부품마다 붙은
'이 OS에서만' 조건을 리눅스 기준으로 풀어, 리눅스 전용(dbus_fast·bleak 등)이 섞인다(20261110 확인).

필요한 것: WSL에서 윈도우 명령(cmd.exe)을 부를 수 있을 것, 윈도우에 Inno Setup 6.
"""
from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# HANGEUL_BUILD_VERSION은 업데이트 시험용이다 — 같은 코드로 '새 판'을 하나 더 만든다
VERSION = os.environ.get("HANGEUL_BUILD_VERSION") or (ROOT / "VERSION").read_text(encoding="utf-8").strip()
PYTHON_VERSION = "3.12.10"          # 내장형 zip이 나오는 마지막 3.12 버그 수정판
PYTHON_TAG = "312"
EMBED_URL = f"https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-embed-amd64.zip"
GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"
ISCC = Path("/mnt/c/Program Files (x86)/Inno Setup 6/ISCC.exe")
CMD = Path("/mnt/c/Windows/System32/cmd.exe")

# 설치본에 넣지 않는 것 — 받는 사람이 쓰지 않는 개발용
EXCLUDE_TOP = {"tests", "build", ".gitattributes", ".gitignore", "pytest.ini", "Setup.bat",
               "requirements-test.txt", "run.sh", "restart.sh", "stop.sh"}
EXCLUDE_FILES = {"tools/build_windows_installer.py", "tools/make_hf_space.py",
                 "tools/publish_check.py", "tools/release.py"}

# 콘솔·런타임이 서로를 찾는 길. 내장형 파이썬은 PYTHONPATH를 무시하고 ._pth만 본다 —
# 실행기가 자식 프로세스에 PYTHONPATH를 주어도 소용이 없어서 여기에 적는다.
PTH_LINES = [f"python{PYTHON_TAG}.zip", ".", "Lib\\site-packages",
             "..\\console\\src", "..\\runtime\\src", "", "import site"]


def _win_temp() -> tuple[Path, str]:
    out = subprocess.run([str(CMD), "/c", "echo %LOCALAPPDATA%"], capture_output=True,
                         text=True, cwd="/mnt/c").stdout.strip()
    win = out + "\\Temp\\hangeul_robot_installer"
    linux = Path(subprocess.run(["wslpath", "-u", win], capture_output=True, text=True).stdout.strip())
    return linux, win


def _win(path: Path) -> str:
    return subprocess.run(["wslpath", "-w", str(path)], capture_output=True, text=True).stdout.strip()


def _run_windows(args: list[str], cwd: Path) -> None:
    """윈도우 프로그램을 부른다. 실패하면 그 출력을 그대로 보이고 멈춘다."""
    done = subprocess.run(args, cwd=str(cwd), capture_output=True)
    text = (done.stdout + done.stderr).decode("utf-8", errors="replace")
    if done.returncode != 0:
        print(text)
        raise SystemExit(f"실패: {' '.join(args[:3])} … (코드 {done.returncode})")


def _tracked_files() -> list[str]:
    names = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True,
                           check=True).stdout.splitlines()
    return [n for n in names
            if n.split("/")[0] not in EXCLUDE_TOP and n not in EXCLUDE_FILES]


def stage(app: Path) -> None:
    for name in _tracked_files():
        target = app / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    print(f"  프로그램 파일 {len(_tracked_files())}개")


def python_embed(app: Path, cache: Path) -> Path:
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / Path(EMBED_URL).name
    if not archive.exists():
        archive.write_bytes(urllib.request.urlopen(EMBED_URL, timeout=120).read())
    py = app / "python"
    with zipfile.ZipFile(archive) as z:
        z.extractall(py)
    (py / f"python{PYTHON_TAG}._pth").write_text("\r\n".join(PTH_LINES) + "\r\n", encoding="ascii")
    get_pip = cache / "get-pip.py"
    if not get_pip.exists():
        get_pip.write_bytes(urllib.request.urlopen(GET_PIP_URL, timeout=120).read())
    shutil.copy2(get_pip, py / "get-pip.py")
    return py


def install_parts(py: Path) -> None:
    exe = str(py / "python.exe")      # 실행 파일은 WSL 경로로 부르고, 넘기는 파일은 윈도우 경로로 준다
    _run_windows([exe, "get-pip.py", "--no-warn-script-location", "-q"], py)
    (py / "get-pip.py").unlink()
    req = _win(ROOT / "install" / "windows" / "installer-requirements.txt")
    _run_windows([exe, "-m", "pip", "install", "-q", "--no-warn-script-location",
                  "--disable-pip-version-check", "-r", req], py)
    # 받는 사람의 PC에서 쓰지 않는 것은 덜어낸다(설치 파일이 작아진다)
    for junk in (py / "Scripts",):
        shutil.rmtree(junk, ignore_errors=True)


def check_imports(app: Path, py: Path) -> None:
    """설치본이 **그 자체로** 콘솔·런타임·실물 SDK를 불러오는지 윈도우에서 확인한다."""
    probe = ("import fastapi, uvicorn, serial, dynamixel_sdk, pymycobot, cryptography;"
             "from hangeul_console.updater import verify_manifest;"
             "import hangeul_console.app, hangeul_runtime.server;"
             "print('부품 확인 완료')")
    _run_windows([str(py / "python.exe"), "-c", probe], app)
    print("  설치본에서 콘솔·런타임·SDK를 불러왔습니다")


def iss_text(app_win: str, out_win: str, icon: str) -> str:
    return f"""; 만든 것: tools/build_windows_installer.py — 손으로 고치지 않는다
#define AppVer "{VERSION}"
[Setup]
AppId={{{{6B1D2A4E-6C2E-4D8B-9B7A-4A0E1F7C9E11}}
AppName=한글 로봇
AppVersion={{#AppVer}}
AppPublisher=Hangeul Robot
AppPublisherURL=https://github.com/rgb0rgb/hangeul-robot
DefaultDirName={{localappdata}}\\Programs\\HangeulRobot
DisableDirPage=yes
DisableProgramGroupPage=yes
DefaultGroupName=한글 로봇
PrivilegesRequired=lowest
OutputDir={out_win}
OutputBaseFilename=HangeulRobot-Setup-{{#AppVer}}
SetupIconFile={icon}
UninstallDisplayIcon={{app}}\\hangeul_robot.ico
UninstallDisplayName=한글 로봇
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=no

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\\Korean.isl"

[Files]
; 프로그램 — 판올림 때 새것으로 바꾼다
Source: "{app_win}\\*"; DestDir: "{{app}}"; Excludes: "\\data"; Flags: recursesubdirs createallsubdirs ignoreversion
; 운영자 자산(안전 범위·작업 목록) — 이미 있으면 **덮어쓰지 않고**, 프로그램을 지워도 **남긴다**.
; 고쳐 둔 안전 범위가 판올림·재설치로 사라지면 안 된다(20261110 시험에서 제거가 지웠다)
Source: "{app_win}\\data\\*"; DestDir: "{{app}}\\data"; Flags: recursesubdirs createallsubdirs onlyifdoesntexist uninsneveruninstall

[Icons]
Name: "{{autodesktop}}\\한글 로봇"; Filename: "{{app}}\\Start.bat"; WorkingDir: "{{app}}"; IconFilename: "{{app}}\\hangeul_robot.ico"
Name: "{{autodesktop}}\\한글 로봇 초기화"; Filename: "{{app}}\\Reset.bat"; WorkingDir: "{{app}}"; IconFilename: "{{app}}\\hangeul_robot.ico"
Name: "{{group}}\\한글 로봇"; Filename: "{{app}}\\Start.bat"; WorkingDir: "{{app}}"; IconFilename: "{{app}}\\hangeul_robot.ico"
Name: "{{group}}\\한글 로봇 초기화"; Filename: "{{app}}\\Reset.bat"; WorkingDir: "{{app}}"; IconFilename: "{{app}}\\hangeul_robot.ico"
Name: "{{group}}\\한글 로봇 끄기"; Filename: "{{app}}\\Stop.bat"; WorkingDir: "{{app}}"; IconFilename: "{{app}}\\hangeul_robot.ico"
Name: "{{group}}\\한글 로봇 지우기"; Filename: "{{uninstallexe}}"

[Run]
Filename: "{{app}}\\Start.bat"; WorkingDir: "{{app}}"; Description: "지금 한글 로봇 시작"; Flags: postinstall nowait shellexec skipifsilent

[UninstallRun]
; 켜져 있으면 파일이 잡혀 지워지지 않는다 — 먼저 끈다
Filename: "{{app}}\\Stop.bat"; WorkingDir: "{{app}}"; Flags: runhidden waituntilterminated; RunOnceId: "StopHangeulRobot"

[UninstallDelete]
; 프로그램이 실행 중에 만든 것. **data(가르친 자세·로그)와 install\\robots(등록한 로봇)는 남긴다**
Type: filesandordirs; Name: "{{app}}\\python"
Type: filesandordirs; Name: "{{app}}\\console"
Type: filesandordirs; Name: "{{app}}\\runtime"
Type: filesandordirs; Name: "{{app}}\\tools"

[Code]
// 판올림 설치 전에 돌고 있는 한글 로봇을 끈다 — 켜진 채로는 파일을 바꿀 수 없다
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Code: Integer;
begin
  Result := '';
  if FileExists(ExpandConstant('{{app}}\\Stop.bat')) then
    Exec(ExpandConstant('{{app}}\\Stop.bat'), '', ExpandConstant('{{app}}'), SW_HIDE, ewWaitUntilTerminated, Code);
end;
"""


def main() -> int:
    if not CMD.exists() or not ISCC.exists():
        print("WSL에서 윈도우의 cmd.exe와 Inno Setup 6(ISCC.exe)이 필요합니다.")
        return 2
    work, work_win = _win_temp()
    shutil.rmtree(work, ignore_errors=True)
    app = work / "app"
    app.mkdir(parents=True)
    print(f"한글 로봇 {VERSION} 윈도우 설치 파일을 만듭니다 — {work_win}")
    stage(app)
    (app / "VERSION").write_text(VERSION + "\n", encoding="utf-8")
    py = python_embed(app, work.parent / "hangeul_robot_installer_cache")
    print(f"  파이썬 {PYTHON_VERSION} 내장형")
    install_parts(py)
    check_imports(app, py)
    # Inno Setup은 윈도우 프로그램이다 — WSL 쪽 경로(\\wsl.localhost)에 쓰게 하지 않고,
    # 윈도우 임시 폴더에서 만든 뒤 저장소의 build/windows로 옮긴다.
    icon = work / "hangeul_robot.ico"
    shutil.copy2(ROOT / "install" / "windows" / "hangeul_robot.ico", icon)
    shutil.copy2(icon, app / "hangeul_robot.ico")
    iss = work / "hangeul_robot.iss"
    # Inno Setup은 BOM 있는 UTF-8을 유니코드로 읽는다(한글 이름)
    iss.write_text(iss_text(_win(app), _win(work / "out"), _win(icon)), encoding="utf-8-sig")
    _run_windows([str(ISCC), "/Q", _win(iss)], work)
    built = work / "out" / f"HangeulRobot-Setup-{VERSION}.exe"
    out = ROOT / "build" / "windows"
    out.mkdir(parents=True, exist_ok=True)
    exe = out / built.name
    shutil.copy2(built, exe)
    print(f"만들었습니다: {exe} ({exe.stat().st_size // (1024 * 1024)} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
