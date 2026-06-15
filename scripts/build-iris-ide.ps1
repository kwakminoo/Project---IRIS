# Iris IDE — Theia Browser Application 빌드
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$IdeDir = Join-Path $Root "iris-ide"

Push-Location $IdeDir
try {
    yarn build
    Write-Host "Iris IDE build complete." -ForegroundColor Green
    Write-Host "Backend entry: iris-ide\applications\browser\lib\backend\main.js"
} finally {
    Pop-Location
}
