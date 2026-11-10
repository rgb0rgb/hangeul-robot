@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Hangeul Robot - Stop
set "PY=.venv\Scripts\python.exe"
if exist "python\python.exe" set "PY=python\python.exe"
if not exist "%PY%" exit /b 0
"%PY%" tools\launcher.py stop
timeout /t 5
