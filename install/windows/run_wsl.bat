@echo off
chcp 65001 >nul
REM Hangeul Robot - double-click on Windows to start run.sh inside WSL.
REM
REM Why this file exists:
REM  1. run.sh is a Linux script; double-clicking it in Explorer does nothing.
REM  2. \\wsl.localhost\... is a UNC path. cmd cannot use UNC as the current folder and
REM     stops with "UNC paths are not supported". So this file never uses its own folder,
REM     only the Linux absolute path below.
REM
REM Comments here are ASCII on purpose. cmd misreads non-ASCII REM lines in a UTF-8 batch
REM file (before or after chcp 65001) and runs the fragments as commands (2026-11-08).
setlocal
cd /d %SystemRoot%

set DISTRO=Ubuntu
set PROJECT=/root/hangeul_robot

echo 한글 로봇을 WSL(%DISTRO%)에서 띄웁니다 — %PROJECT%
echo 창을 닫으면 콘솔도 함께 꺼집니다.
echo.

REM Open the browser once the console has had time to start.
start "" cmd /c "timeout /t 8 >nul & start http://127.0.0.1:8099"

wsl.exe -d %DISTRO% -- bash -lc "cd %PROJECT% && ./run.sh"

if errorlevel 1 (
  echo.
  echo 띄우지 못했습니다. 위의 줄을 그대로 읽어 주세요.
  echo  · WSL 배포판 이름이 %DISTRO%가 아니면 이 파일의 DISTRO 값을 바꾸세요 ^(wsl -l -q로 확인^).
  echo  · %PROJECT% 가 없으면 PROJECT 값을 바꾸세요.
)
pause
