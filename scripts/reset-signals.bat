@echo off
cd /d "%~dp0..\apex-backend"
set PYTHONPATH=%CD%
call .venv\Scripts\python.exe scripts\reset_signals_h1.py
pause
