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
    Write-Host "  Downloading: $Url" -ForegroundColor Gray
    Invoke-WebRequest -Uri $Url -OutFile $OutFile -UseBasicParsing
}

function Assert-CommandSucceeded([string]$What, [int]$Code) {
    if ($Code -ne 0) {
        throw "$What failed with exit code $Code"
    }
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
    & $VenvPython -m pip install --upgrade pip setuptools wheel --prefer-binary
    Assert-CommandSucceeded "pip bootstrap" $LASTEXITCODE

    Write-Step "[3/5] Installing CastFlux Python dependencies"
    & $VenvPython -m pip install -e $AppRoot --prefer-binary
    Assert-CommandSucceeded "CastFlux dependency installation" $LASTEXITCODE

    Write-Step "[4/5] Preparing local ffmpeg"
    if (-not (Test-Path $FfmpegExe)) {
        $FfmpegZip = Join-Path $DownloadDir "ffmpeg-release-essentials.zip"
        if (-not (Test-Path $FfmpegZip)) {
            Invoke-Download "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip" $FfmpegZip
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
