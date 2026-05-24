# CastFlux Installer Builder
# 在 Windows 上运行此脚本以编译安装程序 EXE
# 用法: .\build_installer.ps1

param(
    [string]$OutputDir = (Join-Path $PSScriptRoot "..\dist")
)

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  CastFlux Installer Builder" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$InnoDir = Join-Path $env:TEMP "inno-setup-portable"

# 1. 下载 Inno Setup Portable（如果不存在）
$InnoExe = Join-Path $InnoDir "ISCC.exe"
if (-not (Test-Path $InnoExe)) {
    Write-Host "[1/3] 下载 Inno Setup Portable..." -ForegroundColor Yellow
    if (-not (Test-Path $InnoDir)) { New-Item -ItemType Directory -Path $InnoDir -Force | Out-Null }

    $InnoUrl = "https://jrsoftware.org/download.php/innosetup-portable.zip"
    $InnoZip = Join-Path $env:TEMP "innosetup-portable.zip"

    try {
        Invoke-WebRequest -Uri $InnoUrl -OutFile $InnoZip -UseBasicParsing
        Expand-Archive -Path $InnoZip -DestinationPath $InnoDir -Force
        Write-Host "  Inno Setup 已解压到: $InnoDir" -ForegroundColor Green
    } catch {
        Write-Host "  [ERROR] 下载失败: $_" -ForegroundColor Red
        Write-Host "  请手动下载: https://jrsoftware.org/download.php/innosetup-portable.zip"
        Write-Host "  解压到: $InnoDir"
        exit 1
    }
} else {
    Write-Host "[1/3] Inno Setup 已就绪" -ForegroundColor Green
}

# 2. 确保 dist 目录存在
if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}
Write-Host "[2/3] 输出目录: $OutputDir" -ForegroundColor Yellow

# 3. 编译安装程序
$IssPath = Join-Path $PSScriptRoot "installer.iss"
Write-Host "[3/3] 编译安装程序..." -ForegroundColor Yellow
Write-Host "  ISS: $IssPath" -ForegroundColor Gray

try {
    & $InnoExe $IssPath
    if ($LASTEXITCODE -ne 0) {
        throw "ISCC 编译失败 (exit code: $LASTEXITCODE)"
    }
    Write-Host "  编译成功！" -ForegroundColor Green
} catch {
    Write-Host "  [ERROR] 编译失败: $_" -ForegroundColor Red
    exit 1
}

# 列出生成的 EXE
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  生成的文件:" -ForegroundColor Cyan
Get-ChildItem $OutputDir -Filter "CastFlux_Setup*.exe" | ForEach-Object {
    $size = "{0:N1} MB" -f ($_.Length / 1MB)
    Write-Host "  $($_.Name)  ($size)" -ForegroundColor White
}
Write-Host "========================================" -ForegroundColor Cyan

pause
