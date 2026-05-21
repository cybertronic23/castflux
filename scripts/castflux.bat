@echo off
REM CastFlux Windows 快捷运行脚本
REM 使用: 双击运行，或拖拽视频文件到本脚本上

setlocal

set "HF_TOKEN=你的_HF_TOKEN"
set "DEEPSEEK_API_KEY=你的_DEEPSEEK_API_KEY"

if "%~1"=="" (
    echo 请将视频文件拖拽到本脚本上运行
    echo.
    echo 或者: castflux.bat video.mp4
    pause
    exit /b 1
)

echo 运行 CastFlux...
uv run castflux "%~1" -o output --verbose
pause
