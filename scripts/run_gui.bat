@echo off
title CastFlux
cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
    echo ============================================
    echo   首次运行，正在配置环境...
    echo ============================================
    echo.
    call scripts\setup_gui.bat
    if errorlevel 1 (
        echo.
        echo   [ERROR] 环境配置失败
        pause
        exit /b 1
    )
    cd /d "%~dp0.."
)

echo 启动 CastFlux...
".venv\Scripts\python.exe" -m castflux.gui
if errorlevel 1 (
    echo.
    echo   [ERROR] 启动失败
    pause
)
