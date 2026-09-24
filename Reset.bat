@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"
title Hangeul Robot - Reset
if not exist ".venv\Scripts\python.exe" (
  echo 아직 설치되지 않았습니다. 먼저 설치합니다.
  call "%~dp0Setup.bat"
  exit /b
)
echo 한글 로봇을 모두 끄고 처음부터 다시 시작합니다. 팔을 낮은 자세에 두세요.
echo.
".venv\Scripts\python.exe" tools\launcher.py reset
if errorlevel 1 (
  echo.
  echo 위에 [장치 없음] 이나 [실패] 가 있으면 그 줄의 안내를 따르세요.
  echo 해결한 뒤 바탕화면의 [한글 로봇 초기화] 를 누르면 처음부터 다시 시작합니다.
  pause
  exit /b 1
)
echo.
echo 다시 시작했습니다. 이 창은 닫아도 됩니다.
timeout /t 15
