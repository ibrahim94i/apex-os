@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

:: ============================================================
:: APEX OS v2.0 — Stop all services
:: ============================================================

cd /d "%~dp0"
set "ROOT=%CD%"

echo.
echo  ========================================
echo   APEX OS v2.0 - Stopping...
echo  ========================================
echo.

:: Kill by window title
for %%T in ("APEX-Backend" "APEX-Celery" "APEX-Frontend") do (
    taskkill /FI "WINDOWTITLE eq %%T*" /F >nul 2>&1
    if not errorlevel 1 echo [OK] Stopped %%T
)

:: Kill processes on ports 8000 and 3000
for %%P in (8000 3000) do (
    for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":%%P .*LISTENING"') do (
        if not "%%a"=="0" (
            taskkill /PID %%a /F >nul 2>&1
            if not errorlevel 1 echo [OK] Freed port %%P (PID %%a)
        )
    )
)

:: Kill orphaned uvicorn/celery/node for this project
wmic process where "CommandLine like '%%apex-backend%%' and CommandLine like '%%uvicorn%%'" delete >nul 2>&1
wmic process where "CommandLine like '%%apex-backend%%' and CommandLine like '%%celery%%'" delete >nul 2>&1
wmic process where "CommandLine like '%%apex-frontend%%' and CommandLine like '%%next%%'" delete >nul 2>&1

del "%ROOT%\.apex-pids" 2>nul

echo.
echo  All APEX services stopped.
echo  PostgreSQL and Redis services are still running (Windows services).
echo  To stop them: net stop Redis  /  net stop postgresql-x64-18
echo.
ping 127.0.0.1 -n 4 >nul
