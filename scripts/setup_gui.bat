@echo off
setlocal
title CastFlux Setup
cd /d "%~dp0.."

echo ============================================
echo   CastFlux Setup
echo ============================================
echo.

set "PS_ARGS=%*"
if /I "%~1"=="--installer" set "PS_ARGS=-Installer"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows_bootstrap.ps1" %PS_ARGS%
set "SETUP_RC=%ERRORLEVEL%"

if not "%SETUP_RC%"=="0" (
    echo.
    echo [ERROR] CastFlux setup failed. See runtime\logs for details.
    echo You can run scripts\collect_support_logs.bat and send the zip file to the developer.
    pause
    exit /b %SETUP_RC%
)

if /I not "%~1"=="--installer" (
    echo.
    echo Setup complete. You can now run CastFlux from the desktop shortcut.
    pause
)

exit /b 0
