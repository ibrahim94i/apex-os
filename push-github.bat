@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

cd /d "%~dp0"
set "PATH=C:\Program Files\GitHub CLI;C:\Program Files\Git\bin;%PATH%"

echo.
echo  ========================================
echo   APEX OS — رفع على GitHub
echo  ========================================
echo.

where gh >nul 2>&1
if errorlevel 1 (
    echo [ERROR] GitHub CLI غير مثبت
    echo         https://cli.github.com/
    pause
    exit /b 1
)

gh auth status >nul 2>&1
if errorlevel 1 (
    echo [!] تسجيل الدخول إلى GitHub...
    echo     سيفتح المتصفح — أكّد الدخول والصلاحيات
    echo.
    gh auth login --hostname github.com --git-protocol https --web
    if errorlevel 1 (
        echo [ERROR] فشل تسجيل الدخول
        pause
        exit /b 1
    )
)

echo.
echo [..] إنشاء repository: apex-os
echo.

gh repo view %USERNAME%/apex-os >nul 2>&1
if not errorlevel 1 (
    echo [OK] المستودع موجود — رفع التحديثات...
    git remote remove origin 2>nul
    for /f "delims=" %%u in ('gh api user -q .login') do set "GH_USER=%%u"
    git remote add origin https://github.com/!GH_USER!/apex-os.git
    git push -u origin main
) else (
    gh repo create apex-os --public --source=. --remote=origin --push
)

if errorlevel 1 (
    echo [ERROR] فشل الرفع
    pause
    exit /b 1
)

echo.
for /f "delims=" %%u in ('gh api user -q .login') do set "GH_USER=%%u"
echo  ========================================
echo   تم الرفع بنجاح!
echo   https://github.com/!GH_USER!/apex-os
echo  ========================================
echo.
pause
