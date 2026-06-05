# Iris Tab Monitor - Chrome extension setup (Windows)
# Run from repo root: .\scripts\setup-iris-chrome-extension.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$ExtDir = Join-Path $Root "chrome-extension"
$EnvFile = Join-Path $Root "iris\.env"

if (-not (Test-Path $ExtDir)) {
    Write-Error "chrome-extension folder not found: $ExtDir"
}

Write-Host ""
Write-Host "=== Iris Chrome extension ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "1) Open: chrome://extensions"
Write-Host "2) Enable Developer mode"
Write-Host "3) Load unpacked -> select this folder:"
Write-Host "   $ExtDir" -ForegroundColor Yellow
Write-Host ""
Write-Host "4) Pin 'Iris Tab Monitor' on the toolbar"
Write-Host "5) Open extension popup -> check sites (e.g. YouTube)"
Write-Host "   Port 17777 -> Save (no per-tab allow needed)"
Write-Host ""

$port = 17777
if (Test-Path $EnvFile) {
    $m = Select-String -Path $EnvFile -Pattern '^\s*IRIS_EXTENSION_PORT\s*=\s*(\d+)' -ErrorAction SilentlyContinue
    if ($m) { $port = [int]$m.Matches[0].Groups[1].Value }
}
Write-Host "Iris ingest port (iris/.env): $port" -ForegroundColor Green
Write-Host ""

Set-Clipboard -Value $ExtDir
Write-Host "Extension folder path copied to clipboard." -ForegroundColor Green

$chromePaths = @(
    "${env:ProgramFiles}\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
)
$chrome = $chromePaths | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($chrome) {
    Start-Process $chrome "chrome://extensions/"
    Write-Host "Opened chrome://extensions"
} else {
    Write-Host "Chrome not found. Open chrome://extensions manually."
}

Write-Host ""
