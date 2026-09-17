@echo off
setlocal
pushd "%~dp0..\.."
set "PYTHON=python"
if exist ".venv\Scripts\python.exe" set "PYTHON=.venv\Scripts\python.exe"
set "PYTHONPATH=%CD%\console\src"
"%PYTHON%" -m uvicorn hangeul_console.app:app --host 127.0.0.1 --port 8099
popd
endlocal
