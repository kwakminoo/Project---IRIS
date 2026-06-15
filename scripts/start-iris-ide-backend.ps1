# Iris IDE — Theia Backend 단독 실행 (검증용)
param(
    [string]$Workspace = "",
    [int]$Port = 3100
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$IdeDir = Join-Path $Root "iris-ide"
$Entry = Join-Path $IdeDir "applications\browser\lib\backend\main.js"
$NodeBundled = Join-Path $IdeDir "node_modules\node-win-x64\bin\node.exe"
$LogDir = Join-Path $env:USERPROFILE ".iris\logs"
$LogFile = Join-Path $LogDir "ide-backend-standalone.log"

if (-not (Test-Path $Entry)) {
    Write-Error "Backend not built. Run scripts\build-iris-ide.ps1 first."
}

$Node = if (Test-Path $NodeBundled) { $NodeBundled } else { (Get-Command node).Source }
if (-not $Workspace) { $Workspace = $Root }

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

Write-Host "=== Iris IDE Backend Standalone ==="
Write-Host "Node:       $Node"
Write-Host "Node ver:   $(& $Node -v)"
Write-Host "Entry:      $Entry"
Write-Host "Workspace:  $Workspace"
Write-Host "Bind:       127.0.0.1:$Port"
Write-Host "CWD:        $(Join-Path $IdeDir 'applications\browser')"
Write-Host "Log:        $LogFile"
Write-Host ""

$Cwd = Join-Path $IdeDir "applications\browser"
$args = @($Entry, $Workspace, "--hostname=127.0.0.1", "--port=$Port")
Write-Host "Command: $Node $($args -join ' ')"
Write-Host "Open in browser: http://127.0.0.1:$Port"
Write-Host ""

Push-Location $Cwd
try {
    & $Node @args 2>&1 | Tee-Object -FilePath $LogFile -Append
} finally {
    Pop-Location
}
