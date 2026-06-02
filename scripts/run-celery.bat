@echo off
cd /d "%~dp0..\apex-backend"
set PYTHONPATH=%CD%
"%CD%\.venv\Scripts\python.exe" -m celery -A app.workers.celery_app worker --loglevel=info --pool=solo
