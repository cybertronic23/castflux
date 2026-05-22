@echo off
chcp 65001 >nul
title CastFlux 安装程序
cd /d "%~dp0.."

echo ============================================
echo   CastFlux 直播切片工具 - 一键安装
echo ============================================
echo.

:: ---- 1. 检测 / 安装 Python ----
echo [1/5] 检测 Python 环境...
where python >nul 2>nul
if %errorlevel% equ 0 (
    python --version
    echo   Python 已安装
) else (
    echo   Python 未安装，正在下载安装...
    powershell -Command "& {Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.13.10/python-3.13.10-amd64.exe' -OutFile '%TEMP%\python-installer.exe'}"
    if %errorlevel% neq 0 (
        echo   ❌ 下载失败，请手动下载 Python 3.13 安装:
        echo      https://www.python.org/downloads/
        echo   安装时务必勾选 "Add Python to PATH"
        pause
        exit /b 1
    )
    start /wait "" "%TEMP%\python-installer.exe" /quiet InstallAllUsers=1 PrependPath=1
    echo   ✅ Python 安装完成
)

:: ---- 2. 安装 UV ----
echo.
echo [2/5] 安装 UV 包管理器...
where uv >nul 2>nul
if %errorlevel% equ 0 (
    uv --version
    echo   UV 已安装
) else (
    powershell -Command "& {Invoke-WebRequest -Uri 'https://astral.sh/uv/install.ps1' -OutFile '%TEMP%\install-uv.ps1'}"
    powershell -ExecutionPolicy RemoteSigned -File "%TEMP%\install-uv.ps1"
    echo   ✅ UV 安装完成
)

:: 刷新 PATH 使 UV 可用
for /f "tokens=*" %%i in ('where uv 2^>nul') do set UV_PATH=%%i
if not defined UV_PATH (
    set "PATH=%USERPROFILE%\.local\bin;%PATH%"
)

:: ---- 3. 安装 ffmpeg ----
echo.
echo [3/5] 安装 ffmpeg（视频处理引擎）...
set "FFMPEG_DIR=%~dp0ffmpeg"
set "FFMPEG_BIN=%FFMPEG_DIR%\bin"

if exist "%FFMPEG_BIN%\ffmpeg.exe" (
    echo   ffmpeg 已安装
    "%FFMPEG_BIN%\ffmpeg.exe" -version 2>&1 | findstr "ffmpeg version" >nul && echo   ffmpeg 可用
) else (
    echo   正在下载 ffmpeg...
    if not exist "%FFMPEG_DIR%" mkdir "%FFMPEG_DIR%"
    powershell -Command "& {Invoke-WebRequest -Uri 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip' -OutFile '%TEMP%\ffmpeg.zip'}"
    if %errorlevel% neq 0 (
        echo   ⚠ 下载失败，尝试备用地址...
        powershell -Command "& {Invoke-WebRequest -Uri 'https://objects.githubusercontent.com/github-production-release-asset-2e65be/57245070/8ef2a479-9d3b-4cd4-8bfb-8be9aaf4f0a5' -OutFile '%TEMP%\ffmpeg.zip'}"
    )
    if %errorlevel% equ 0 (
        powershell -Command "& {Expand-Archive -Path '%TEMP%\ffmpeg.zip' -DestinationPath '%FFMPEG_DIR%' -Force}"
        :: 查找解压后的 ffmpeg.exe（不同版本目录名不同）
        for /d %%d in ("%FFMPEG_DIR%\ffmpeg-*") do (
            if exist "%%d\bin\ffmpeg.exe" (
                xcopy /s /e /y "%%d\bin" "%FFMPEG_BIN%\" >nul
                rmdir /s /q "%%d"
            )
        )
        if exist "%FFMPEG_BIN%\ffmpeg.exe" (
            echo   ✅ ffmpeg 安装完成
        ) else (
            echo   ⚠ ffmpeg 解压后未找到 ffmpeg.exe
        )
    ) else (
        echo   ⚠ ffmpeg 下载失败，后续 GUI 会引导手动下载
    )
)

:: ---- 4. 安装项目依赖 ----
echo.
echo [4/5] 安装项目依赖（首次下载模型可能需要较长时间）...
uv sync
if %errorlevel% neq 0 (
    echo   ❌ 依赖安装失败
    pause
    exit /b 1
)
echo   ✅ 依赖安装完成

:: ---- 5. 创建桌面快捷方式 ----
echo.
echo [5/5] 创建桌面快捷方式...
set "SHORTCUT=%USERPROFILE%\Desktop\CastFlux.lnk"
set "TARGET=%~dp0run_gui.bat"

if exist "%SHORTCUT%" (
    echo   桌面快捷方式已存在
) else (
    powershell -Command "& {$ws = New-Object -ComObject WScript.Shell; $sc = $ws.CreateShortcut('%SHORTCUT%'); $sc.TargetPath = '%TARGET%'; $sc.WorkingDirectory = '%CD%'; $sc.Description = 'CastFlux 直播切片工具'; $sc.Save()}"
    echo   ✅ 桌面快捷方式已创建
)

echo.
echo ============================================
echo   ✅ 安装完成！
echo.
echo   双击桌面 "CastFlux" 图标启动
echo   或运行 scripts\run_gui.bat
echo ============================================
pause
