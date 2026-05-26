@echo off
setlocal
title CastFlux Setup
cd /d "%~dp0.."

echo ============================================
echo   CastFlux Setup
echo ============================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows_bootstrap.ps1" %*
set "SETUP_RC=%ERRORLEVEL%"

if not "%SETUP_RC%"=="0" (
    echo.
    echo [ERROR] CastFlux setup failed. See runtime\logs for details.
    pause
    exit /b %SETUP_RC%
)

if /I not "%~1"=="--installer" (
    echo.
    echo Setup complete. You can now run CastFlux from the desktop shortcut.
    pause
)

exit /b 0
