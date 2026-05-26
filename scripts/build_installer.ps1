# CastFlux Installer Builder
# 在 Windows 上运行此脚本以编译安装程序 EXE
# 用法: .\build_installer.ps1

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$PythonVersion = "3.11.9"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$VendorDir = Join-Path $PSScriptRoot "vendor"
$VendorDownloads = Join-Path $VendorDir "downloads"
$WheelhouseDir = Join-Path $VendorDir "wheelhouse"

function Invoke-DownloadWithRetry {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][string]$OutFile
    )

    for ($Attempt = 1; $Attempt -le 3; $Attempt++) {
        try {
            Write-Host "  Downloading $Url (attempt $Attempt/3)" -ForegroundColor Gray
            Invoke-WebRequest -Uri $Url -OutFile $OutFile -UseBasicParsing
            return
        } catch {
            Write-Host "  Download failed: $_" -ForegroundColor Yellow
            if ($Attempt -eq 3) {
                throw
            }
            Start-Sleep -Seconds (5 * $Attempt)
        }
    }
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  CastFlux Installer Builder" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 1. 准备离线安装载荷：Python 安装器、ffmpeg、Python wheels
Write-Host "[1/4] 准备离线安装载荷..." -ForegroundColor Yellow
New-Item -ItemType Directory -Path $VendorDownloads, $WheelhouseDir -Force | Out-Null

$PythonInstaller = Join-Path $VendorDownloads "python-$PythonVersion-amd64.exe"
if (-not (Test-Path $PythonInstaller)) {
    Invoke-DownloadWithRetry -Url "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-amd64.exe" -OutFile $PythonInstaller
}

$FfmpegZip = Join-Path $VendorDownloads "ffmpeg-release-essentials.zip"
if (-not (Test-Path $FfmpegZip)) {
    Invoke-DownloadWithRetry -Url "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip" -OutFile $FfmpegZip
}

$Deps = @(
    "pip",
    "setuptools",
    "wheel",
    "faster-whisper>=1.0.0",
    "pyannote.audio>=3.1.0",
    "torch>=2.0.0",
    "openai>=1.0.0",
    "tqdm>=4.0.0",
    "Pillow>=10.0.0"
)

Write-Host "  Downloading Python wheels into $WheelhouseDir" -ForegroundColor Gray
$PipDownloadArgs = @(
    "-m", "pip", "download",
    "--dest", $WheelhouseDir,
    "--prefer-binary",
    "--only-binary=:all:",
    "--retries", "10",
    "--timeout", "120"
) + $Deps
& python @PipDownloadArgs
if ($LASTEXITCODE -ne 0) {
    throw "pip download failed (exit code: $LASTEXITCODE)"
}

# 2. 确认 Inno Setup 已安装
$InnoPath = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $InnoPath)) {
    $InnoPath = "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
}
if (-not (Test-Path $InnoPath)) {
    Write-Host "[2/4] 安装 Inno Setup..." -ForegroundColor Yellow
    try {
        choco install innosetup -y --no-progress
        $InnoPath = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
    } catch {
        Write-Host "  [ERROR] Chocolatey 安装失败，尝试便携版..." -ForegroundColor Red
    }
}

# 3. 如果 Chocolatey 不可用，使用便携版
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

# 4. 创建输出目录
$OutputDir = Join-Path $RepoRoot "dist"
if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}
Write-Host "[3/4] 输出目录: $OutputDir" -ForegroundColor Yellow

# 5. 编译安装程序
$IssPath = Join-Path $PSScriptRoot "installer.iss"
Write-Host "[4/4] 编译安装程序..." -ForegroundColor Yellow
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

# 6. 列出生成的 EXE
Write-Host "生成文件：" -ForegroundColor Yellow
Get-ChildItem $OutputDir -Filter "CastFlux_Setup*.exe" | ForEach-Object {
    $size = "{0:N1} MB" -f ($_.Length / 1MB)
    Write-Host "  $($_.Name)  ($size)" -ForegroundColor White
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  完成！" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
