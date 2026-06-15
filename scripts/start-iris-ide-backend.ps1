param(
    [string]$Workspace = "",
    [int]$Port = 3100
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Entry = Join-Path $Root "iris-ide\applications\browser\lib\backend\main.js"

if (-not (Test-Path $Entry)) {
    Write-Error "Backend not built. Run scripts\build-iris-ide.ps1 first."
}

if (-not $Workspace) {
    $Workspace = $Root
}

Write-Host "Starting Iris IDE backend on 127.0.0.1:$Port workspace=$Workspace"
node $Entry $Workspace --hostname=127.0.0.1 --port=$Port
