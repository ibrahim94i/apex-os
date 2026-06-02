@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

:: ============================================================
:: APEX OS v2.0 — Start all services (Windows native)
:: Double-click to launch dashboard at http://localhost:3000
:: ============================================================

cd /d "%~dp0"
set "ROOT=%CD%"
set "BACKEND=%ROOT%\apex-backend"
set "FRONTEND=%ROOT%\apex-frontend"
set "PIDFILE=%ROOT%\.apex-pids"
set "VENV_PY=%BACKEND%\.venv\Scripts\python.exe"
set "VENV_ALEMBIC=%BACKEND%\.venv\Scripts\alembic.exe"

title APEX OS v2.0 - Starting...

echo.
echo  ========================================
echo   APEX OS v2.0 - Starting...
echo  ========================================
echo.

:: --- Check setup ---
if not exist "%BACKEND%\.venv" (
    echo [!] First run detected. Running setup.bat...
    call "%ROOT%\setup.bat"
)

if not exist "%ROOT%\.env" (
    copy "%ROOT%\.env.example" "%ROOT%\.env"
)
copy /Y "%ROOT%\.env" "%BACKEND%\.env" >nul
copy /Y "%ROOT%\.env" "%FRONTEND%\.env.local" >nul

:: --- Stop any previous instance ---
if exist "%ROOT%\stop.bat" call "%ROOT%\stop.bat" >nul 2>&1
ping 127.0.0.1 -n 3 >nul

del "%PIDFILE%" 2>nul

:: ============================================================
:: 1. PostgreSQL
:: ============================================================
echo [1/5] Starting PostgreSQL...

set "PG_STARTED=0"
for %%S in (postgresql-x64-18 postgresql-x64-16 postgresql-x64-15 PostgreSQL postgresql-x64-14) do (
    if !PG_STARTED!==0 (
        sc query "%%S" >nul 2>&1 && (
            net start "%%S" >nul 2>&1
            if not errorlevel 1 (
                echo       Service started: %%S
                set "PG_STARTED=1"
            )
        )
    )
)

if !PG_STARTED!==0 (
    echo       Checking if PostgreSQL already listening on 5432...
    netstat -an | findstr ":5432.*LISTENING" >nul 2>&1 && (
        echo       [OK] PostgreSQL already running on port 5432
        set "PG_STARTED=1"
    )
)

if !PG_STARTED!==0 (
    echo [WARN] Could not start PostgreSQL service automatically.
    echo        Make sure PostgreSQL for Windows is installed and running.
)

:: ============================================================
:: 2. Redis
:: ============================================================
echo [2/5] Starting Redis...

set "REDIS_STARTED=0"
for %%S in (Redis Memurai redis) do (
    if !REDIS_STARTED!==0 (
        sc query "%%S" >nul 2>&1 && (
            net start "%%S" >nul 2>&1
            if not errorlevel 1 (
                echo       Service started: %%S
                set "REDIS_STARTED=1"
            )
        )
    )
)

if !REDIS_STARTED!==0 (
    netstat -an | findstr ":6379.*LISTENING" >nul 2>&1 && (
        echo       [OK] Redis already running on port 6379
        set "REDIS_STARTED=1"
    )
)

if !REDIS_STARTED!==0 (
    echo [WARN] Could not start Redis service automatically.
    echo        Install Redis for Windows or Memurai, then start the service.
)

:: Wait for services
ping 127.0.0.1 -n 3 >nul

:: --- Initialize PostgreSQL user/database ---
echo       Initializing database (apex / apexdb)...
call "%ROOT%\scripts\init-db.bat"
if errorlevel 1 (
    echo [WARN] Database init failed — backend may run in degraded mode.
)

:: ============================================================
:: 3. Backend (FastAPI + Alembic)
:: ============================================================
echo [3/5] Starting Backend (port 8000)...

if not exist "%VENV_PY%" (
    echo [ERROR] Python venv not found at %BACKEND%\.venv
    echo        Run setup.bat first.
    pause
    exit /b 1
)

cd /d "%BACKEND%"
set PYTHONPATH=%BACKEND%
set PYTHONUNBUFFERED=1

echo       Running database migrations...
"%VENV_ALEMBIC%" upgrade head >nul 2>&1
if errorlevel 1 "%VENV_ALEMBIC%" upgrade head

start "APEX-Backend" /MIN cmd /c ""%ROOT%\scripts\run-backend.bat""
echo       [OK] Backend starting...

:: ============================================================
:: 4. Celery Worker
:: ============================================================
echo [4/5] Starting Celery Worker...

start "APEX-Celery" /MIN cmd /c ""%ROOT%\scripts\run-celery.bat""
echo       [OK] Celery starting...

:: ============================================================
:: 5. Frontend (Next.js)
:: ============================================================
echo [5/5] Starting Frontend (port 3000)...

start "APEX-Frontend" /MIN cmd /c ""%ROOT%\scripts\run-frontend.bat""
echo       [OK] Frontend starting...

:: ============================================================
:: Wait for services and open browser
:: ============================================================
echo.
echo [..] Waiting for services to be ready...

set "READY=0"
for /L %%i in (1,1,30) do (
    ping 127.0.0.1 -n 3 >nul
    curl -s http://localhost:8000/api/v1/health 2>nul | findstr /C:"\"status\":\"ok\"" >nul 2>&1 && (
        curl -s -o nul -w "%%{http_code}" http://localhost:3000 2>nul | findstr "200" >nul 2>&1 && (
            set "READY=1"
            goto :ready
        )
    )
    echo       Attempt %%i/30...
)

:ready
echo.
if !READY!==1 (
    echo  ========================================
    echo   APEX OS v2.0 is RUNNING
    echo  ========================================
    echo   Dashboard : http://localhost:3000
    echo   API       : http://localhost:8000
    echo   API Docs  : http://localhost:8000/docs
    echo  ========================================
    echo.
    start "" "http://localhost:3000"
) else (
    echo [WARN] Services may still be starting.
    echo        Opening dashboard anyway...
    start "" "http://localhost:3000"
    echo        Check minimized windows: APEX-Backend, APEX-Celery, APEX-Frontend
)

echo.
echo  Press any key to close this window (services keep running).
echo  Use stop.bat to shut down everything.
echo.
pause >nul
