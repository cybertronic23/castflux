@echo off
setlocal
title CastFlux
cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
    echo ============================================
    echo   First run: preparing CastFlux environment
    echo ============================================
    echo.
    call "%~dp0setup_gui.bat"
    if errorlevel 1 (
        echo.
        echo [ERROR] Environment setup failed.
        pause
        exit /b 1
    )
    cd /d "%~dp0.."
)

set "PATH=%~dp0ffmpeg\bin;%PATH%"
echo Starting CastFlux...
".venv\Scripts\python.exe" -m castflux.gui
if errorlevel 1 (
    echo.
    echo [ERROR] CastFlux failed to start.
    echo Please run scripts\setup_gui.bat again or check runtime\logs.
    pause
)
