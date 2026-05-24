# CastFlux Installer Builder
# 在 Windows 上运行此脚本以编译安装程序 EXE
# 用法: .\build_installer.ps1

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  CastFlux Installer Builder" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 1. 确认 Inno Setup 已安装
$InnoPath = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $InnoPath)) {
    $InnoPath = "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
}
if (-not (Test-Path $InnoPath)) {
    Write-Host "[1/3] 安装 Inno Setup..." -ForegroundColor Yellow
    try {
        choco install innosetup -y --no-progress
        $InnoPath = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
    } catch {
        Write-Host "  [ERROR] Chocolatey 安装失败，尝试便携版..." -ForegroundColor Red
    }
}

# 2. 如果 Chocolatey 不可用，使用便携版
if (-not (Test-Path $InnoPath)) {
    $InnoDir = Join-Path $env:TEMP "inno-setup-portable"
    $InnoPath = Join-Path $InnoDir "ISCC.exe"
    if (-not (Test-Path $InnoPath)) {
        Write-Host "  下载 Inno Setup Portable..." -ForegroundColor Yellow
        $InnoUrl = "https://jrsoftware.org/download.php/innosetup-portable.zip"
        $InnoZip = Join-Path $env:TEMP "innosetup-portable.zip"
        try {
            Invoke-WebRequest -Uri $InnoUrl -OutFile $InnoZip -UseBasicParsing
            Expand-Archive -Path $InnoZip -DestinationPath $InnoDir -Force
            Write-Host "  Inno Setup 已解压" -ForegroundColor Green
        } catch {
            Write-Host "  [ERROR] 下载/解压失败: $_" -ForegroundColor Red
            exit 1
        }
    }
}

# 3. 创建输出目录
$OutputDir = Join-Path $PSScriptRoot "..\dist"
if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}
Write-Host "[1/3] 输出目录: $OutputDir" -ForegroundColor Yellow

# 4. 编译安装程序
$IssPath = Join-Path $PSScriptRoot "installer.iss"
Write-Host "[2/3] 编译安装程序..." -ForegroundColor Yellow
Write-Host "  ISCC: $InnoPath" -ForegroundColor Gray
Write-Host "  ISS:  $IssPath" -ForegroundColor Gray

try {
    & $InnoPath $IssPath
    if ($LASTEXITCODE -ne 0) {
        throw "ISCC 编译失败 (exit code: $LASTEXITCODE)"
    }
    Write-Host "  编译成功！" -ForegroundColor Green
} catch {
    Write-Host "  [ERROR] 编译失败: $_" -ForegroundColor Red
    exit 1
}

# 5. 列出生成的 EXE
Write-Host "[3/3] 生成文件：" -ForegroundColor Yellow
Get-ChildItem $OutputDir -Filter "CastFlux_Setup*.exe" | ForEach-Object {
    $size = "{0:N1} MB" -f ($_.Length / 1MB)
    Write-Host "  $($_.Name)  ($size)" -ForegroundColor White
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  完成！" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
