@echo off
REM CastFlux Windows CLI 快捷运行脚本
REM 使用: 拖拽视频文件到本脚本上，或 castflux.bat video.mp4

cd /d "%~dp0.."

if "%~1"=="" (
    echo 请将视频文件拖拽到本脚本上运行
    echo.
    echo 或者: castflux.bat video.mp4
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] 未检测到虚拟环境，请先运行 setup_gui.bat
    pause
    exit /b 1
)

echo 运行 CastFlux...
".venv\Scripts\python.exe" -m castflux "%~1" -o output --verbose
pause
