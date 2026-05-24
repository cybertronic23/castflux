@echo off
title CastFlux 安装程序
cd /d "%~dp0.."

echo ============================================
echo   CastFlux 直播切片工具 - 一键安装
echo ============================================
echo.

:: ---- 1. 检测 / 安装 Python ----
echo [1/5] 检测 Python 环境...
python --version >nul 2>nul
if not errorlevel 1 (
    python --version
    echo   Python 已安装
    goto :python_done
)
echo   Python 未安装，正在下载安装...
powershell -Command "& {Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.13.10/python-3.13.10-amd64.exe' -OutFile '%TEMP%\python-installer.exe'}"
if errorlevel 1 (
    echo.
    echo   [ERROR] 下载失败，请手动下载:
    echo          https://www.python.org/downloads/
    echo   安装时务必勾选 "Add Python to PATH"
    pause
    exit /b 1
)
start /wait "" "%TEMP%\python-installer.exe" /quiet InstallAllUsers=1 PrependPath=1
echo   Python 安装完成
:: 让当前会话能找到 Python
for %%p in (
    "%ProgramFiles%\Python313\python.exe"
    "%ProgramFiles(x86)%\Python313\python.exe"
    "%LocalAppData%\Programs\Python\Python313\python.exe"
) do (
    if exist %%p (
        set "PYTHON_BIN=%%~p"
        goto :python_done
    )
)
echo   [WARN] 未找到 python.exe，可能需要重启电脑
:python_done

:: ---- 2. 安装 UV ----
echo.
echo [2/5] 安装 UV 包管理器...
set "UV_CMD=uv"
%UV_CMD% --version >nul 2>nul
if not errorlevel 1 (
    %UV_CMD% --version
    echo   UV 已安装
    goto :uv_done
)
echo   正在安装 UV...
powershell -Command "& {Invoke-WebRequest -Uri 'https://astral.sh/uv/install.ps1' -OutFile '%TEMP%\install-uv.ps1'}"
powershell -ExecutionPolicy RemoteSigned -File "%TEMP%\install-uv.ps1"
:: 刷新 PATH 找 uv
set "PATH=%USERPROFILE%\.local\bin;%LocalAppData%\Microsoft\WindowsApps;%PATH%"
%UV_CMD% --version >nul 2>nul
if not errorlevel 1 (
    %UV_CMD% --version
    echo   UV 可用
    goto :uv_done
)
:: 尝试 python -m uv
python -m uv --version >nul 2>nul
if not errorlevel 1 (
    set "UV_CMD=python -m uv"
    echo   UV 已安装（通过 python -m uv）
    goto :uv_done
)
echo   [ERROR] UV 安装失败，无法继续
pause
exit /b 1
:uv_done

:: ---- 3. 安装 ffmpeg ----
echo.
echo [3/5] 安装 ffmpeg（视频处理引擎）...
set "FFMPEG_BIN=%~dp0ffmpeg\bin"
if exist "%FFMPEG_BIN%\ffmpeg.exe" (
    echo   ffmpeg 已安装
    "%FFMPEG_BIN%\ffmpeg.exe" -version 2>&1 | findstr "ffmpeg version" >nul
    if not errorlevel 1 echo   ffmpeg 可用
    goto :ffmpeg_done
)
echo   正在下载 ffmpeg...
if not exist "%~dp0ffmpeg" mkdir "%~dp0ffmpeg"
powershell -Command "& {Invoke-WebRequest -Uri 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip' -OutFile '%TEMP%\ffmpeg.zip'}"
if errorlevel 1 (
    echo   [WARN] 下载失败，GUI 会引导手动下载
    goto :ffmpeg_done
)
powershell -Command "& {Expand-Archive -Path '%TEMP%\ffmpeg.zip' -DestinationPath '%~dp0ffmpeg' -Force}"
for /d %%d in ("%~dp0ffmpeg\ffmpeg-*") do (
    if exist "%%d\bin\ffmpeg.exe" (
        xcopy /s /e /y "%%d\bin" "%FFMPEG_BIN%\" >nul
        rmdir /s /q "%%d"
    )
)
if exist "%FFMPEG_BIN%\ffmpeg.exe" (
    echo   ffmpeg 安装完成
) else (
    echo   [WARN] 未找到 ffmpeg.exe，请手动下载
)
:ffmpeg_done

:: ---- 4. 安装项目依赖 ----
echo.
echo [4/5] 安装项目依赖（首次运行需下载模型，可能较慢）...
%UV_CMD% sync
if errorlevel 1 (
    echo   [ERROR] 依赖安装失败
    pause
    exit /b 1
)
echo   依赖安装完成

:: ---- 5. 创建桌面快捷方式 ----
echo.
echo [5/5] 创建桌面快捷方式...
set "SHORTCUT=%USERPROFILE%\Desktop\CastFlux.lnk"
set "TARGET=%~dp0run_gui.bat"
if exist "%SHORTCUT%" (
    echo   桌面快捷方式已存在
) else (
    powershell -Command "& {$ws = New-Object -ComObject WScript.Shell; $sc = $ws.CreateShortcut('%SHORTCUT%'); $sc.TargetPath = '%TARGET%'; $sc.WorkingDirectory = '%CD%'; $sc.Description = 'CastFlux 直播切片工具'; $sc.Save()}"
    echo   桌面快捷方式已创建
)

echo.
echo ============================================
echo   安装完成！
echo.
echo   双击桌面 "CastFlux" 图标启动
echo   或运行 scripts\run_gui.bat
echo ============================================
pause
