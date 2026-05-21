#Requires -Version 5.1
<#
.SYNOPSIS
  CastFlux 一键安装脚本 (Windows)
.DESCRIPTION
  自动安装 ffmpeg、Python、UV 依赖，并配置 CastFlux 运行环境。
#>

$ErrorActionPreference = "Stop"
$RepoUrl = "https://github.com/cybertronic23/castflux.git"

Write-Host "=== CastFlux 安装脚本 (Windows) ===" -ForegroundColor Cyan

# ----- 1. 检查 Git -----
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "[1/5] 安装 Git..." -ForegroundColor Yellow
    winget install --id Git.Git -e --source winget
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
} else {
    Write-Host "[1/5] Git 已安装" -ForegroundColor Green
}

# ----- 2. 检查/安装 ffmpeg -----
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Host "[2/5] 安装 ffmpeg..." -ForegroundColor Yellow
    winget install --id Gyan.FFmpeg -e --source winget
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
} else {
    Write-Host "[2/5] ffmpeg 已安装" -ForegroundColor Green
}

# ----- 3. 检查/安装 UV -----
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "[3/5] 安装 UV..." -ForegroundColor Yellow
    powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
} else {
    Write-Host "[3/5] UV 已安装" -ForegroundColor Green
}

# ----- 4. 克隆/更新仓库 -----
$ProjectDir = "$env:USERPROFILE\castflux"
if (Test-Path "$ProjectDir\.git") {
    Write-Host "[4/5] 更新 CastFlux..." -ForegroundColor Yellow
    git -C $ProjectDir pull
} else {
    Write-Host "[4/5] 克隆 CastFlux..." -ForegroundColor Yellow
    git clone $RepoUrl $ProjectDir
}
Set-Location $ProjectDir

# ----- 5. 安装 Python 依赖 -----
Write-Host "[5/5] 安装 Python 依赖..." -ForegroundColor Yellow
uv sync
uv pip install -e .

Write-Host ""
Write-Host "=== 安装完成 ===" -ForegroundColor Green
Write-Host ""
Write-Host "下一步:" -ForegroundColor Cyan
Write-Host "  1. 设置 API 密钥 (复制以下内容到命令行执行):"
Write-Host '     set DEEPSEEK_API_KEY=sk-...'
Write-Host '     set HF_TOKEN=hf_...'
Write-Host ""
Write-Host "  2. 运行 CastFlux:"
Write-Host "     cd %USERPROFILE%\castflux"
Write-Host '     uv run castflux video.mp4 -o output'
Write-Host ""
Write-Host "  首次运行会自动下载 Whisper 模型 (~200MB for base, ~3GB for large-v3)"
Write-Host "  无 GPU 环境建议使用默认 auto 模式, 自动选择 base 模型"
Write-Host ""
pause
