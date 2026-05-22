@echo off
chcp 65001 >nul
title CastFlux
cd /d "%~dp0.."

echo 正在启动 CastFlux...
uv run python -m castflux.gui

if %errorlevel% neq 0 (
    echo.
    echo ❌ 启动失败，请先运行 setup_gui.bat 完成安装。
    pause
)
