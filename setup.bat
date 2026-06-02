@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

:: ============================================================
:: APEX OS v2.0 — First-time setup (Windows native)
:: Run once before start.bat
:: ============================================================

cd /d "%~dp0"
set "ROOT=%CD%"
set "BACKEND=%ROOT%\apex-backend"
set "FRONTEND=%ROOT%\apex-frontend"

echo.
echo  ========================================
echo   APEX OS v2.0 - Setup
echo  ========================================
echo.

if not exist "%ROOT%\.env" (
    copy "%ROOT%\.env.example" "%ROOT%\.env"
    echo [OK] Created .env from .env.example
)

:: --- Python (prefer 3.11/3.12 over 3.13 for pandas compatibility) ---
set "PYTHON="
where py >nul 2>&1 && (
    py -3.11 -c "import sys" >nul 2>&1 && set "PYTHON=py -3.11"
    if not defined PYTHON py -3.12 -c "import sys" >nul 2>&1 && set "PYTHON=py -3.12"
    if not defined PYTHON py -3.13 -c "import sys" >nul 2>&1 && set "PYTHON=py -3.13"
)
if not defined PYTHON where python >nul 2>&1 && set "PYTHON=python"
if not defined PYTHON (
    echo [ERROR] Python 3.11+ not found. Install from https://www.python.org/downloads/
    pause
    exit /b 1
)
echo [OK] Python: %PYTHON%

:: --- Node.js ---
where node >nul 2>&1 || (
    echo [ERROR] Node.js not found. Install from https://nodejs.org/
    pause
    exit /b 1
)
echo [OK] Node.js: 
node -v

:: --- Backend venv ---
set "VENV_PY=%BACKEND%\.venv\Scripts\python.exe"

:: Recreate venv if missing or corrupted (e.g. partial delete)
if exist "%BACKEND%\.venv" if not exist "%BACKEND%\.venv\pyvenv.cfg" (
    echo [WARN] Broken venv detected, recreating...
    rmdir /s /q "%BACKEND%\.venv" 2>nul
)

if not exist "%BACKEND%\.venv" (
    echo [..] Creating Python venv...
    cd /d "%BACKEND%"
    %PYTHON% -m venv .venv
)

if not exist "%VENV_PY%" (
    echo [ERROR] venv creation failed at %BACKEND%\.venv
    pause
    exit /b 1
)

echo [..] Installing backend dependencies...
"%VENV_PY%" -m pip install --upgrade pip
if errorlevel 1 (
    echo [WARN] pip upgrade skipped, continuing with existing pip...
)
"%VENV_PY%" -m pip install -r "%BACKEND%\requirements.txt"
if errorlevel 1 (
    echo [ERROR] pip install failed.
    echo        If you use Python 3.13, install Python 3.11 and run: py -3.11 -m venv apex-backend\.venv
    pause
    exit /b 1
)
echo [OK] Backend dependencies installed

:: --- Frontend ---
echo [..] Installing frontend dependencies...
cd /d "%FRONTEND%"
if not exist "node_modules\.bin\next.cmd" call npm install
echo [OK] Frontend dependencies installed

:: --- Sync .env ---
copy /Y "%ROOT%\.env" "%BACKEND%\.env" >nul
copy /Y "%ROOT%\.env" "%FRONTEND%\.env.local" >nul
echo [OK] Environment files synced

:: --- PostgreSQL database ---
call "%ROOT%\scripts\init-db.bat"
if errorlevel 1 (
    echo [WARN] Database init failed — set PG_PASSWORD in .env if postgres password is required
)

echo.
echo  Setup complete. Run start.bat to launch APEX.
echo.
pause
