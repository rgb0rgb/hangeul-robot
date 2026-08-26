@echo off
REM 한글 로봇 콘솔 — 윈도우 실행
set PYTHONPATH=%~dp0..\..\console\src
python -m uvicorn hangeul_console.app:app --host 127.0.0.1 --port 8099
