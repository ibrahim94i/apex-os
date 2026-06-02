@echo off
setlocal EnableDelayedExpansion

:: ============================================================
:: APEX OS — Initialize PostgreSQL (user apex / db apexdb)
:: Called from setup.bat and start.bat
:: ============================================================

set "ROOT=%~dp0.."
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

set "PG_USER=postgres"
set "PG_PASSWORD="
set "PG_BIN="

:: Load PG settings from .env if present
if exist "%ROOT%\.env" (
    for /f "usebackq tokens=1,* delims==" %%A in (`findstr /r /i "^PG_USER= ^PG_PASSWORD= ^PG_BIN=" "%ROOT%\.env"`) do (
        if /i "%%A"=="PG_USER" set "PG_USER=%%B"
        if /i "%%A"=="PG_PASSWORD" set "PG_PASSWORD=%%B"
        if /i "%%A"=="PG_BIN" set "PG_BIN=%%B"
    )
)

:: Auto-detect psql.exe
if not defined PG_BIN set "PG_BIN=C:\Program Files\PostgreSQL\18\bin"
if not exist "%PG_BIN%\psql.exe" (
    for %%V in (18 17 16 15 14) do (
        if not exist "%PG_BIN%\psql.exe" if exist "C:\Program Files\PostgreSQL\%%V\bin\psql.exe" (
            set "PG_BIN=C:\Program Files\PostgreSQL\%%V\bin"
        )
    )
)

if not exist "%PG_BIN%\psql.exe" (
    echo [ERROR] psql.exe not found. Install PostgreSQL for Windows.
    exit /b 1
)

set "PSQL=%PG_BIN%\psql.exe"
set "PG_CTL=%PG_BIN%\pg_ctl.exe"
for %%I in ("%PG_BIN%\..") do set "PG_HOME=%%~fI"
set "PGDATA=%PG_HOME%\data"
set "PG_HBA=%PGDATA%\pg_hba.conf"
set "PG_HBA_BAK=%PGDATA%\pg_hba.conf.apex.bak"
set "SQL=%ROOT%\scripts\init-db.sql"

echo [..] Initializing APEX database via %PG_BIN%...

:: Attempt 1: password from .env
if defined PG_PASSWORD (
    set "PGPASSWORD=%PG_PASSWORD%"
    "%PSQL%" -U %PG_USER% -h 127.0.0.1 -f "%SQL%"
    if not errorlevel 1 goto :verify
)

:: Attempt 2: trust auth bootstrap (local dev)
if not exist "%PG_HBA%" (
    echo [ERROR] pg_hba.conf not found at %PG_HBA%
    exit /b 1
)

echo [..] Enabling temporary local trust auth for bootstrap...
copy /Y "%PG_HBA%" "%PG_HBA_BAK%" >nul

powershell -NoProfile -Command ^
  "$p='%PG_HBA%';" ^
  "$c=Get-Content $p -Raw;" ^
  "$c=$c -replace '(?m)^host\s+all\s+all\s+127\.0\.0\.1/32\s+\S+','host    all             all             127.0.0.1/32            trust';" ^
  "$c=$c -replace '(?m)^host\s+all\s+all\s+::1/128\s+\S+','host    all             all             ::1/128                 trust';" ^
  "Set-Content -Path $p -Value $c -NoNewline"

if exist "%PG_CTL%" (
    "%PG_CTL%" reload -D "%PGDATA%" >nul 2>&1
) else (
    "%PSQL%" -U %PG_USER% -h 127.0.0.1 -d postgres -c "SELECT pg_reload_conf();" >nul 2>&1
)

ping 127.0.0.1 -n 2 >nul
"%PSQL%" -U %PG_USER% -h 127.0.0.1 -f "%SQL%"
set "INIT_ERR=!errorlevel!"

echo [..] Restoring pg_hba.conf...
copy /Y "%PG_HBA_BAK%" "%PG_HBA%" >nul
del "%PG_HBA_BAK%" >nul 2>&1
if exist "%PG_CTL%" (
    "%PG_CTL%" reload -D "%PGDATA%" >nul 2>&1
) else (
    "%PSQL%" -U %PG_USER% -h 127.0.0.1 -d postgres -c "SELECT pg_reload_conf();" >nul 2>&1
)

if !INIT_ERR! neq 0 (
    echo [ERROR] Database init failed.
    exit /b 1
)

:verify
set "PGPASSWORD=apex"
"%PSQL%" -U apex -h 127.0.0.1 -d apexdb -tAc "SELECT 1" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] apex user verification failed.
    exit /b 1
)

echo [OK] Database ready: apex / apexdb
exit /b 0
