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
    echo 首次运行，正在配置 CastFlux 环境...
    call "%~dp0setup_gui.bat"
    if errorlevel 1 (
        echo [ERROR] 环境配置失败
        pause
        exit /b 1
    )
)

set "PATH=%~dp0ffmpeg\bin;%PATH%"
echo 运行 CastFlux...
".venv\Scripts\python.exe" -m castflux "%~1" -o output --verbose
pause
