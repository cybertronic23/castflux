@echo off
setlocal
title CastFlux Support Logs
cd /d "%~dp0.."

if not exist "runtime\support" mkdir "runtime\support"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$stamp=Get-Date -Format 'yyyyMMdd-HHmmss';" ^
  "$zip=Join-Path (Resolve-Path 'runtime\support') ('castflux-support-' + $stamp + '.zip');" ^
  "$items=@();" ^
  "if (Test-Path 'runtime\logs') { $items += 'runtime\logs' };" ^
  "$diag=Join-Path (Resolve-Path 'runtime\support') 'diagnostics.txt';" ^
  "'CastFlux support package' | Set-Content -Encoding UTF8 $diag;" ^
  "'Working directory: ' + (Get-Location) | Add-Content -Encoding UTF8 $diag;" ^
  "'Date: ' + (Get-Date) | Add-Content -Encoding UTF8 $diag;" ^
  "$items += $diag;" ^
  "Compress-Archive -Path $items -DestinationPath $zip -Force;" ^
  "Write-Host ''; Write-Host 'Support log package created:'; Write-Host $zip"

echo.
echo 请把上面这个 castflux-support-*.zip 文件发给开发者。
pause
