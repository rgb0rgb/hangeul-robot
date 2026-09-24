@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"
title Hangeul Robot - Setup
echo ==================================================
echo   한글 로봇 설치
echo   필요한 프로그램을 받아 설치합니다. 인터넷이 필요합니다.
echo ==================================================
echo.

echo [1/4] 파이썬 확인
call :findpy
if defined PY goto :have_python
echo   파이썬이 없습니다. 자동으로 설치합니다. 몇 분 걸릴 수 있습니다.
where winget >nul 2>nul
if errorlevel 1 goto :no_winget
winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
call :findpy
if not defined PY goto :no_python
:have_python
echo   사용할 파이썬: %PY%
echo.

echo [2/4] 프로그램 전용 공간 만들기 (.venv)
if not exist ".venv\Scripts\python.exe" %PY% -m venv .venv
if not exist ".venv\Scripts\python.exe" goto :fail_venv
set "VPY=%~dp0.venv\Scripts\python.exe"
echo.

echo [3/4] 필요한 부품 받기
"%VPY%" -m pip install --disable-pip-version-check -q --upgrade pip
"%VPY%" -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 goto :fail_pip
"%VPY%" -m pip install --disable-pip-version-check -q -r requirements-robot.txt
if errorlevel 1 echo   실물 로봇 부품을 받지 못했습니다. 시뮬레이션은 쓸 수 있습니다.
echo.

echo [4/4] 바탕화면 바로가기 만들기
"%VPY%" tools\launcher.py shortcuts
echo.
echo ==================================================
echo   설치가 끝났습니다. 이제 한글 로봇을 시작합니다.
echo   다음부터는 바탕화면의 [한글 로봇]을 두 번 누르세요.
echo ==================================================
echo.
call "%~dp0Start.bat"
exit /b 0

:findpy
set "PY="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if not errorlevel 1 (
  set "PY=py -3"
  goto :eof
)
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if not errorlevel 1 (
  set "PY=python"
  goto :eof
)
for %%V in (313 312 311 310) do (
  if exist "%LocalAppData%\Programs\Python\Python%%V\python.exe" (
    set PY="%LocalAppData%\Programs\Python\Python%%V\python.exe"
    goto :eof
  )
)
goto :eof

:no_winget
echo.
echo   자동 설치 도구(winget)가 없습니다.
echo   열리는 페이지에서 Python 3.12 를 받아 설치하세요.
echo   설치 첫 화면에서 [Add python.exe to PATH] 를 반드시 체크하세요.
echo   설치가 끝나면 이 Setup.bat 을 다시 두 번 누르세요.
start "" https://www.python.org/downloads/
pause
exit /b 1

:no_python
echo.
echo   파이썬을 설치했지만 아직 찾지 못했습니다.
echo   이 창을 닫고 Setup.bat 을 한 번 더 두 번 누르세요.
pause
exit /b 1

:fail_venv
echo.
echo   프로그램 전용 공간을 만들지 못했습니다. 위의 메시지를 확인하세요.
pause
exit /b 1

:fail_pip
echo.
echo   부품을 받지 못했습니다. 인터넷 연결을 확인한 뒤 Setup.bat 을 다시 누르세요.
pause
exit /b 1
