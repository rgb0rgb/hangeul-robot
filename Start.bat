@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"
title Hangeul Robot - Start
if not exist ".venv\Scripts\python.exe" (
  echo 아직 설치되지 않았습니다. 먼저 설치합니다.
  call "%~dp0Setup.bat"
  exit /b
)
echo 한글 로봇을 시작합니다. 잠시 뒤 브라우저가 열립니다.
echo.
".venv\Scripts\python.exe" tools\launcher.py start
if errorlevel 1 (
  echo.
  echo 위에 [장치 없음] 이나 [실패] 가 있으면 그 줄의 안내를 따르세요.
  echo 해결한 뒤 바탕화면의 [한글 로봇 초기화] 를 누르면 처음부터 다시 시작합니다.
  pause
  exit /b 1
)
echo.
echo 이 창은 닫아도 됩니다. 로봇 프로그램은 계속 돕니다.
timeout /t 15
