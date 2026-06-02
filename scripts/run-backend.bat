@echo off
cd /d "%~dp0..\apex-backend"
set PYTHONPATH=%CD%
"%CD%\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
