# Iris IDE — 패키징 (향후 installer 포함용)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Src = Join-Path $Root "iris-ide\applications\browser\lib"
$Dest = Join-Path $Root "iris\iris\resources\ide\lib"

if (-not (Test-Path $Src)) {
    Write-Error "Build output not found. Run scripts\build-iris-ide.ps1 first."
}

New-Item -ItemType Directory -Force -Path $Dest | Out-Null
Copy-Item -Path (Join-Path $Src "*") -Destination $Dest -Recurse -Force
Write-Host "Packaged to $Dest" -ForegroundColor Green
