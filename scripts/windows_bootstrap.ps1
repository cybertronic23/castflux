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

function Test-ExecutableFile([string]$Path) {
    return (Test-Path $Path -PathType Leaf)
}

function Find-PythonExeCandidate {
    $Candidates = New-Object System.Collections.Generic.List[string]

    function Add-PythonCandidate([string]$Path) {
        if ($Path) {
            [void]$Candidates.Add($Path)
        }
    }

    function Add-PythonCandidateFromRoot([string]$Root) {
        if ($Root) {
            Add-PythonCandidate (Join-Path $Root "Python311\python.exe")
        }
    }

    Add-PythonCandidate $PythonExe
    Add-PythonCandidateFromRoot (Join-Path $env:LOCALAPPDATA "Programs\Python")
    Add-PythonCandidateFromRoot $env:ProgramFiles
    Add-PythonCandidateFromRoot ${env:ProgramFiles(x86)}

    $RegistryRoots = @(
        "HKCU:\Software\Python\PythonCore\3.11\InstallPath",
        "HKLM:\Software\Python\PythonCore\3.11\InstallPath",
        "HKLM:\Software\WOW6432Node\Python\PythonCore\3.11\InstallPath"
    )
    foreach ($Root in $RegistryRoots) {
        try {
            $Key = Get-Item -Path $Root -ErrorAction Stop
            $InstallPath = $Key.GetValue("")
            if ($InstallPath) {
                Add-PythonCandidate (Join-Path $InstallPath "python.exe")
            }
            $ExecutablePath = $Key.GetValue("ExecutablePath")
            if ($ExecutablePath) {
                Add-PythonCandidate $ExecutablePath
            }
        } catch {
            # Registry key may not exist; keep searching other locations.
        }
    }

    foreach ($Candidate in ($Candidates | Select-Object -Unique)) {
        if (Test-ExecutableFile $Candidate) {
            return $Candidate
        }
    }
    return $null
}

function Install-PrivatePython {
    $InstallerPath = Join-Path $DownloadDir "python-$PythonVersion-amd64.exe"
    if (-not (Test-ExecutableFile $InstallerPath)) {
        Invoke-Download "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-amd64.exe" $InstallerPath
    }

    if ((Test-Path $PythonDir) -and -not (Test-ExecutableFile $PythonExe)) {
        Write-Host "  Removing incomplete Python directory: $PythonDir" -ForegroundColor Yellow
        Remove-Item $PythonDir -Recurse -Force
    }

    $PythonInstallLog = Join-Path $LogDir ("python-installer-{0:yyyyMMdd-HHmmss}.log" -f (Get-Date))
    $PythonArgs = @(
        "/quiet",
        "InstallAllUsers=0",
        "TargetDir=`"$PythonDir`"",
        "DefaultJustForMeTargetDir=`"$PythonDir`"",
        "Include_pip=1",
        "Include_tcltk=1",
        "Include_launcher=0",
        "Include_test=0",
        "PrependPath=0",
        "Shortcuts=0",
        "/log",
        "`"$PythonInstallLog`""
    ) -join " "

    Write-Host "  Python installer: $InstallerPath" -ForegroundColor Gray
    Write-Host "  Python install log: $PythonInstallLog" -ForegroundColor Gray
    $Process = Start-Process -FilePath $InstallerPath -ArgumentList $PythonArgs -Wait -PassThru
    Assert-CommandSucceeded "Python installer" $Process.ExitCode

    if (-not (Test-ExecutableFile $PythonExe)) {
        $FoundPython = $null
        if (Test-Path $PythonDir) {
            $FoundPython = Get-ChildItem $PythonDir -Recurse -Filter "python.exe" -ErrorAction SilentlyContinue |
                Where-Object { $_.FullName -notlike "*\Scripts\python.exe" } |
                Select-Object -First 1
        }
        if ($FoundPython) {
            Write-Host "  Found Python at non-standard path: $($FoundPython.FullName)" -ForegroundColor Yellow
            $script:PythonExe = $FoundPython.FullName
        } else {
            $Candidate = Find-PythonExeCandidate
            if ($Candidate) {
                Write-Host "  Found Python installed outside runtime: $Candidate" -ForegroundColor Yellow
                $script:PythonExe = $Candidate
            }
        }
    }

    if (-not (Test-ExecutableFile $PythonExe)) {
        Write-Host "  Python directory contents:" -ForegroundColor Yellow
        if (Test-Path $PythonDir) {
            Get-ChildItem $PythonDir -Force -ErrorAction SilentlyContinue | ForEach-Object {
                Write-Host "    $($_.FullName)" -ForegroundColor Gray
            }
        } else {
            Write-Host "    $PythonDir does not exist" -ForegroundColor Gray
        }
        throw "Python was not installed to $PythonExe. See $PythonInstallLog"
    }
}

function Assert-PrivatePython {
    if (-not (Test-ExecutableFile $PythonExe)) {
        throw "Private Python is missing or not a file: $PythonExe"
    }
    & $PythonExe --version
    Assert-CommandSucceeded "Python version check" $LASTEXITCODE
    & $PythonExe -c "import tkinter, ensurepip; print('  tkinter and pip are available')"
    Assert-CommandSucceeded "Python tkinter/pip check" $LASTEXITCODE
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
    if (-not (Test-ExecutableFile $PythonExe)) {
        Install-PrivatePython
    }
    Assert-PrivatePython

    Write-Step "[2/5] Creating Python virtual environment"
    if (-not (Test-ExecutableFile $VenvPython)) {
        & $PythonExe -m venv $VenvDir
        Assert-CommandSucceeded "venv creation" $LASTEXITCODE
    }
    Invoke-PipInstall -Description "pip bootstrap" -Arguments @("--upgrade", "pip", "setuptools", "wheel")

    Write-Step "[3/5] Installing CastFlux Python dependencies"
    Invoke-PipInstall -Description "CastFlux dependency installation" -Arguments @("-e", $AppRoot)

    Write-Step "[4/5] Preparing local ffmpeg"
    if (-not (Test-ExecutableFile $FfmpegExe)) {
        # Check multiple locations for ffmpeg zip
        $FfmpegZip = $null
        $Locations = @(
            (Join-Path $PSScriptRoot "ffmpeg.zip"),
            (Join-Path $AppRoot "ffmpeg.zip"),
            (Join-Path $DownloadDir "ffmpeg-release-essentials.zip")
        )
        foreach ($Loc in $Locations) {
            if (Test-ExecutableFile $Loc) {
                $FfmpegZip = $Loc
                Write-Host "  Found ffmpeg at: $Loc" -ForegroundColor Gray
                break
            }
        }
        
        if (-not $FfmpegZip) {
            $FfmpegZip = Join-Path $DownloadDir "ffmpeg-release-essentials.zip"
            $FfmpegUrls = @(
                "https://github.com/cybertronic23/castflux/releases/latest/download/ffmpeg-release-essentials.zip",
                "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
            )
            $Downloaded = $false
            foreach ($Url in $FfmpegUrls) {
                try {
                    Write-Host "  Downloading ffmpeg..." -ForegroundColor Gray
                    Invoke-Download $Url $FfmpegZip
                    $Downloaded = $true
                    break
                } catch {
                    Write-Host "  ffmpeg download source failed: $Url" -ForegroundColor Yellow
                }
            }
            if (-not $Downloaded) {
                throw "ffmpeg download failed. Please ask the developer for an offline installer."
            }
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
