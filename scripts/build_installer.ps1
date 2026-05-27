# CastFlux Windows installer builder
# Usage: powershell -ExecutionPolicy Bypass -File scripts\build_installer.ps1

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$PythonVersion = "3.11.9"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$VendorDir = Join-Path $PSScriptRoot "vendor"
$VendorDownloads = Join-Path $VendorDir "downloads"
$WheelhouseDir = Join-Path $VendorDir "wheelhouse"
$LauncherDir = Join-Path $PSScriptRoot "launcher"
$LauncherOutDir = Join-Path $LauncherDir "bin\Release\net48"

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

Write-Host "[1/4] Preparing offline payload..." -ForegroundColor Yellow
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

Write-Host "[2/5] Compiling C# launcher..." -ForegroundColor Yellow

# Check for dotnet SDK
$dotnet = Get-Command dotnet -ErrorAction SilentlyContinue
if (-not $dotnet) {
    Write-Host "  [WARNING] dotnet SDK not found, skipping launcher compilation" -ForegroundColor Yellow
    Write-Host "  Install .NET SDK from https://dotnet.microsoft.com/download" -ForegroundColor Yellow
} else {
    Write-Host "  Building CastFluxLauncher..." -ForegroundColor Gray
    & dotnet build $LauncherDir\CastFluxLauncher.csproj -c Release -o $LauncherOutDir
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [WARNING] Launcher build failed, installer will use batch file launcher" -ForegroundColor Yellow
    } else {
        Write-Host "  Launcher built: $LauncherOutDir\CastFlux.exe" -ForegroundColor Green
    }
}

Write-Host "[3/5] Checking Inno Setup..." -ForegroundColor Yellow
$InnoCandidates = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
)
$InnoPath = $null
foreach ($Candidate in $InnoCandidates) {
    if (Test-Path $Candidate) {
        $InnoPath = $Candidate
        break
    }
}
if (-not $InnoPath) {
    Write-Host ""
    Write-Host "  [ERROR] Inno Setup 6 was not found." -ForegroundColor Red
    Write-Host "  Install Inno Setup 6, then run this script again:" -ForegroundColor Yellow
    Write-Host "  https://jrsoftware.org/isdl.php" -ForegroundColor Yellow
    exit 1
}

$OutputDir = Join-Path $RepoRoot "dist"
if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}
Write-Host "[4/5] Output directory: $OutputDir" -ForegroundColor Yellow

$IssPath = Join-Path $PSScriptRoot "installer.iss"
Write-Host "[5/5] Compiling installer..." -ForegroundColor Yellow
Write-Host "  ISCC: $InnoPath" -ForegroundColor Gray
Write-Host "  ISS:  $IssPath" -ForegroundColor Gray

& $InnoPath $IssPath
if ($LASTEXITCODE -ne 0) {
    throw "ISCC failed (exit code: $LASTEXITCODE)"
}

Write-Host "  Compile succeeded." -ForegroundColor Green
Write-Host "Generated files:" -ForegroundColor Yellow
Get-ChildItem $OutputDir -Filter "CastFlux_Setup*.exe" | ForEach-Object {
    $size = "{0:N1} MB" -f ($_.Length / 1MB)
    Write-Host "  $($_.Name)  ($size)" -ForegroundColor White
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Done" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
