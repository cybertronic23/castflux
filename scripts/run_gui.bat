@echo off
title CastFlux
cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo   [ERROR] 未检测到虚拟环境
    echo   请先双击 scripts\setup_gui.bat 完成安装
    echo.
    pause
    exit /b 1
)

echo 启动 CastFlux...
".venv\Scripts\python.exe" -m castflux.gui

echo.
echo 程序已退出
pause
