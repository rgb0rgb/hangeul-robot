@echo off
chcp 65001 >nul
REM 한글 로봇 — 윈도우에서 두 번 눌러 WSL의 run.sh를 띄운다.
REM
REM 이 파일이 따로 있는 이유:
REM  1. run.sh는 리눅스 스크립트다. 윈도우 탐색기에서 두 번 눌러도 실행되지 않는다.
REM  2. \\wsl.localhost\... 는 UNC 경로다. cmd는 UNC를 현재 폴더로 쓰지 못해서
REM     "UNC 경로는 지원되지 않습니다"를 내고 멈춘다. 그래서 이 파일은 자기 폴더를
REM     쓰지 않고, 아래 리눅스 절대 경로만 쓴다.
setlocal
cd /d %SystemRoot%

set DISTRO=Ubuntu
set PROJECT=/root/hangeul_robot

echo 한글 로봇을 WSL(%DISTRO%)에서 띄웁니다 — %PROJECT%
echo 창을 닫으면 콘솔도 함께 꺼집니다.
echo.

REM 화면이 준비될 때쯤 브라우저를 연다.
start "" cmd /c "timeout /t 8 >nul & start http://127.0.0.1:8099"

wsl.exe -d %DISTRO% -- bash -lc "cd %PROJECT% && ./run.sh"

if errorlevel 1 (
  echo.
  echo 띄우지 못했습니다. 위의 줄을 그대로 읽어 주세요.
  echo  · WSL 배포판 이름이 %DISTRO%가 아니면 이 파일의 DISTRO 값을 바꾸세요 ^(wsl -l -q로 확인^).
  echo  · %PROJECT% 가 없으면 PROJECT 값을 바꾸세요.
)
pause
