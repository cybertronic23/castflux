#Requires -Version 5.1
<#
.SYNOPSIS
  Installs everything CastFlux needs on Windows without requiring users to
  understand Python, PATH, ffmpeg, or package managers.
#>

param(
    [switch]$Installer
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$AppRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RuntimeDir = Join-Path $AppRoot "runtime"
$DownloadDir = Join-Path $RuntimeDir "downloads"
$LogDir = Join-Path $RuntimeDir "logs"
$WheelhouseDir = Join-Path $RuntimeDir "wheelhouse"
$PythonVersion = "3.11.9"
$PythonDir = Join-Path $RuntimeDir "python311"
$PythonExe = Join-Path $PythonDir "python.exe"
$VenvDir = Join-Path $AppRoot ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$FfmpegRoot = Join-Path $PSScriptRoot "ffmpeg"
$FfmpegBin = Join-Path $FfmpegRoot "bin"
$FfmpegExe = Join-Path $FfmpegBin "ffmpeg.exe"

New-Item -ItemType Directory -Force -Path $RuntimeDir, $DownloadDir, $LogDir | Out-Null
$LogFile = Join-Path $LogDir ("setup-{0:yyyyMMdd-HHmmss}.log" -f (Get-Date))

Start-Transcript -Path $LogFile -Append | Out-Null

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host $Message -ForegroundColor Cyan
}

function Invoke-Download([string]$Url, [string]$OutFile) {
    for ($Attempt = 1; $Attempt -le 5; $Attempt++) {
        try {
            Write-Host "  Downloading (attempt $Attempt/5): $Url" -ForegroundColor Gray
            $ProgressPreference = 'SilentlyContinue'
            Invoke-WebRequest -Uri $Url -OutFile $OutFile -UseBasicParsing -TimeoutSec 300
            return
        } catch {
            Write-Host "  Download failed: $($_.Exception.Message)" -ForegroundColor Yellow
            if ($Attempt -eq 5) { throw }
            Start-Sleep -Seconds (5 * $Attempt)
        }
    }
}

function Assert-CommandSucceeded([string]$What, [int]$Code) {
    if ($Code -ne 0) {
        throw "$What failed with exit code $Code"
    }
}

function Get-PipIndexes {
    $Indexes = @()
    if ($env:PIP_INDEX_URL) {
        $Indexes += $env:PIP_INDEX_URL
    }
    $Indexes += @(
        "https://pypi.org/simple",
        "https://pypi.tuna.tsinghua.edu.cn/simple",
        "https://mirrors.aliyun.com/pypi/simple"
    )
    $Indexes | Select-Object -Unique
}

function Invoke-PipInstall {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,

        [Parameter(Mandatory = $true)]
        [string]$Description
    )

    $BaseArgs = @(
        "-m", "pip", "install",
        "--prefer-binary",
        "--retries", "10",
        "--timeout", "120",
        "--no-input",
        "--disable-pip-version-check"
    )

    $OfflineWheels = @()
    if (Test-Path $WheelhouseDir) {
        $OfflineWheels = Get-ChildItem $WheelhouseDir -Filter "*.whl" -ErrorAction SilentlyContinue
    }

    if ($OfflineWheels.Count -gt 0) {
        Write-Host "  $Description (offline wheelhouse: $WheelhouseDir)" -ForegroundColor Gray
        & $VenvPython @BaseArgs --no-index --find-links $WheelhouseDir @Arguments
        if ($LASTEXITCODE -eq 0) {
            return
        }
        Write-Host "  Offline wheelhouse install failed with exit code $LASTEXITCODE; falling back to online indexes." -ForegroundColor Yellow
    }

    foreach ($IndexUrl in Get-PipIndexes) {
        for ($Attempt = 1; $Attempt -le 3; $Attempt++) {
            Write-Host "  $Description (index: $IndexUrl, attempt $Attempt/3)" -ForegroundColor Gray
            & $VenvPython @BaseArgs --index-url $IndexUrl @Arguments
            if ($LASTEXITCODE -eq 0) {
                return
            }
            Write-Host "  pip failed with exit code $LASTEXITCODE, retrying..." -ForegroundColor Yellow
            Start-Sleep -Seconds (5 * $Attempt)
        }
    }

    throw "$Description failed after trying all package indexes"
}

try {
    Write-Host "============================================" -ForegroundColor Cyan
    Write-Host "  CastFlux one-click Windows setup" -ForegroundColor Cyan
    Write-Host "============================================" -ForegroundColor Cyan
    Write-Host "App: $AppRoot"
    Write-Host "Log: $LogFile"

    Write-Step "[1/5] Preparing private Python $PythonVersion"
    if (-not (Test-Path $PythonExe)) {
        $InstallerPath = Join-Path $DownloadDir "python-$PythonVersion-amd64.exe"
        if (-not (Test-Path $InstallerPath)) {
            Invoke-Download "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-amd64.exe" $InstallerPath
        }

        New-Item -ItemType Directory -Force -Path $PythonDir | Out-Null
        $PythonArgs = @(
            "/quiet",
            "InstallAllUsers=0",
            "TargetDir=`"$PythonDir`"",
            "Include_pip=1",
            "Include_tcltk=1",
            "Include_launcher=0",
            "Include_test=0",
            "PrependPath=0",
            "Shortcuts=0",
            "SimpleInstall=1"
        )
        $Process = Start-Process -FilePath $InstallerPath -ArgumentList $PythonArgs -Wait -PassThru
        Assert-CommandSucceeded "Python installer" $Process.ExitCode
    }
    & $PythonExe --version
    & $PythonExe -c "import tkinter, ensurepip; print('  tkinter and pip are available')"

    Write-Step "[2/5] Creating Python virtual environment"
    if (-not (Test-Path $VenvPython)) {
        & $PythonExe -m venv $VenvDir
        Assert-CommandSucceeded "venv creation" $LASTEXITCODE
    }
    Invoke-PipInstall -Description "pip bootstrap" -Arguments @("--upgrade", "pip", "setuptools", "wheel")

    Write-Step "[3/5] Installing CastFlux Python dependencies"
    Invoke-PipInstall -Description "CastFlux dependency installation" -Arguments @("-e", $AppRoot)

    Write-Step "[4/5] Preparing local ffmpeg"
    if (-not (Test-Path $FfmpegExe)) {
        # Check multiple locations for ffmpeg zip
        $FfmpegZip = $null
        $Locations = @(
            (Join-Path $PSScriptRoot "ffmpeg.zip"),
            (Join-Path $AppRoot "ffmpeg.zip"),
            (Join-Path $DownloadDir "ffmpeg-release-essentials.zip")
        )
        foreach ($Loc in $Locations) {
            if (Test-Path $Loc) {
                $FfmpegZip = $Loc
                Write-Host "  Found ffmpeg at: $Loc" -ForegroundColor Gray
                break
            }
        }
        
        if (-not $FfmpegZip) {
            # Download from GitHub Release (fast CDN)
            $FfmpegZip = Join-Path $DownloadDir "ffmpeg-release-essentials.zip"
            $FfmpegUrl = "https://github.com/cybertronic23/castflux/releases/download/v1.0.4/ffmpeg-release-essentials.zip"
            Write-Host "  Downloading ffmpeg from GitHub Release..." -ForegroundColor Gray
            Invoke-Download $FfmpegUrl $FfmpegZip
        }

        if (Test-Path $FfmpegRoot) {
            Remove-Item $FfmpegRoot -Recurse -Force
        }
        New-Item -ItemType Directory -Force -Path $FfmpegRoot | Out-Null
        Expand-Archive -Path $FfmpegZip -DestinationPath $FfmpegRoot -Force

        $ExtractedFfmpeg = Get-ChildItem $FfmpegRoot -Recurse -Filter "ffmpeg.exe" |
            Select-Object -First 1
        if (-not $ExtractedFfmpeg) {
            throw "ffmpeg.exe was not found after extracting $FfmpegZip"
        }

        $ExtractedBin = $ExtractedFfmpeg.Directory.FullName
        New-Item -ItemType Directory -Force -Path $FfmpegBin | Out-Null
        Copy-Item (Join-Path $ExtractedBin "*") $FfmpegBin -Recurse -Force

        Get-ChildItem $FfmpegRoot -Directory |
            Where-Object { $_.FullName -ne $FfmpegBin -and $_.Name -like "ffmpeg-*" } |
            Remove-Item -Recurse -Force
    }
    & $FfmpegExe -version | Select-Object -First 1

    Write-Step "[5/5] Creating user files and shortcuts"
    $EnvPath = Join-Path $AppRoot ".env"
    if (-not (Test-Path $EnvPath)) {
        New-Item -ItemType File -Path $EnvPath -Force | Out-Null
    }

    $Desktop = [Environment]::GetFolderPath("Desktop")
    $ShortcutPath = Join-Path $Desktop "CastFlux.lnk"
    $Target = Join-Path $PSScriptRoot "run_gui.bat"
    $Shell = New-Object -ComObject WScript.Shell
    $Shortcut = $Shell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = $Target
    $Shortcut.WorkingDirectory = $AppRoot
    $Shortcut.Description = "CastFlux live stream clipper"
    $Shortcut.Save()
    Write-Host "  Shortcut: $ShortcutPath"

    Write-Host ""
    Write-Host "CastFlux setup completed successfully." -ForegroundColor Green
    Write-Host "Open the desktop shortcut, then use Settings to enter HF_TOKEN and your LLM API key."
    exit 0
}
catch {
    Write-Host ""
    Write-Host "[ERROR] $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Full setup log: $LogFile" -ForegroundColor Yellow
    exit 1
}
finally {
    Stop-Transcript | Out-Null
}
