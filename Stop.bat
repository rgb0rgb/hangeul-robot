@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Hangeul Robot - Stop
if not exist ".venv\Scripts\python.exe" exit /b 0
".venv\Scripts\python.exe" tools\launcher.py stop
timeout /t 5
