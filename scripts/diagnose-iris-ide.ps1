# Iris IDE 환경 진단 — WebEngine·Node·Theia 빌드
param(
    [switch]$SkipBackendSmoke
)

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
$IrisDir = Join-Path $Root "iris"
$VenvPy = Join-Path $IrisDir ".venv\Scripts\python.exe"
$IdeDir = Join-Path $Root "iris-ide"
$ExitCode = 0

function Write-Section($title) {
    Write-Host ""
    Write-Host "=== $title ===" -ForegroundColor Cyan
}

function Fail($code, $msg) {
    Write-Host "[FAIL] $msg" -ForegroundColor Red
    if ($script:ExitCode -eq 0) { $script:ExitCode = $code }
}

function Pass($msg) {
    Write-Host "[PASS] $msg" -ForegroundColor Green
}

Write-Section "Repository"
Write-Host "Root: $Root"
Write-Host "Iris: $IrisDir"

Write-Section "Python"
if (-not (Test-Path $VenvPy)) {
    Fail 1 "Iris venv not found: $VenvPy"
} else {
    Pass "Iris venv python: $VenvPy"
    & $VenvPy -c "import sys,struct; print('version:', sys.version.replace(chr(10),' ')); print('64bit:', struct.calcsize('P')*8==64)"
}

Write-Section "PyQt6 / WebEngine"
$DiagPy = Join-Path $IrisDir "scripts\diagnose_webengine.py"
if (Test-Path $VenvPy) {
    if (Test-Path $DiagPy) {
        & $VenvPy $DiagPy
        if ($LASTEXITCODE -ne 0) { Fail 1 "WebEngine diagnose failed" } else { Pass "WebEngine import" }
    } else {
        & $VenvPy -m pip show PyQt6 PyQt6-WebEngine 2>$null
        & $VenvPy -c "from PyQt6.QtWebEngineWidgets import QWebEngineView; print('QWebEngineView OK')"
        if ($LASTEXITCODE -ne 0) { Fail 1 "WebEngine import" } else { Pass "WebEngine import" }
    }
    $qtProc = Get-ChildItem -Path (Join-Path $IrisDir ".venv\Lib\site-packages\PyQt6") -Recurse -Filter "QtWebEngineProcess.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($qtProc) { Pass "QtWebEngineProcess: $($qtProc.FullName)" } else { Fail 1 "QtWebEngineProcess.exe not found" }
}

Write-Section "Node / Yarn"
$NodeBundled = Join-Path $IdeDir "node_modules\node-win-x64\bin\node.exe"
$NodeCmd = if (Test-Path $NodeBundled) { $NodeBundled } else { (Get-Command node -ErrorAction SilentlyContinue).Source }
if (-not $NodeCmd) {
    Fail 2 "Node.js not found"
} else {
    $nv = & $NodeCmd -v
    Pass "Node: $NodeCmd ($nv)"
}
if (Get-Command yarn -ErrorAction SilentlyContinue) {
    Pass "Yarn: $(yarn -v)"
} else {
    Fail 2 "Yarn not found"
}

Write-Section "Theia build artifacts"
$BackendMain = Join-Path $IdeDir "applications\browser\lib\backend\main.js"
$FrontendIndex = Join-Path $IdeDir "applications\browser\lib\frontend\index.html"
$FrontendBundle = Join-Path $IdeDir "applications\browser\lib\frontend\bundle.js"
foreach ($pair in @(
    @{ Path = $BackendMain; Label = "Backend main.js" },
    @{ Path = $FrontendIndex; Label = "Frontend index.html" },
    @{ Path = $FrontendBundle; Label = "Frontend bundle.js" }
)) {
    if (Test-Path $pair.Path) { Pass $pair.Label } else { Fail 3 "$($pair.Label) missing" }
}

$PkgJson = Join-Path $IdeDir "package.json"
if (Test-Path $PkgJson) {
    $pkg = Get-Content $PkgJson -Raw | ConvertFrom-Json
    $theiaVersions = @()
    if ($pkg.resolutions) {
        $pkg.resolutions.PSObject.Properties | Where-Object { $_.Name -like "@theia/*" } | ForEach-Object {
            $theiaVersions += $_.Value
        }
    }
    $unique = $theiaVersions | Select-Object -Unique
    if ($unique.Count -le 1) {
        Pass "@theia/* version aligned: $($unique[0])"
    } else {
        Fail 3 "@theia/* version mismatch: $($unique -join ', ')"
    }
}

Write-Section "Workspace"
$Ws = $Root
Write-Host "Default workspace: $Ws"

if (-not $SkipBackendSmoke) {
    Write-Section "Backend standalone smoke"
    $SmokePort = 3198
    $StartScript = Join-Path $Root "scripts\start-iris-ide-backend.ps1"
    if ((Test-Path $StartScript) -and (Test-Path $BackendMain) -and $NodeCmd) {
        $job = Start-Job -ScriptBlock {
            param($script, $ws, $port)
            & powershell -NoProfile -ExecutionPolicy Bypass -File $script -Workspace $ws -Port $port 2>&1
        } -ArgumentList $StartScript, $Ws, $SmokePort
        Start-Sleep -Seconds 8
        try {
            $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$SmokePort/" -UseBasicParsing -TimeoutSec 5
            if ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 500) {
                Pass "Backend HTTP $($resp.StatusCode)"
            } else {
                Fail 4 "Backend HTTP $($resp.StatusCode)"
            }
            $bundle = Invoke-WebRequest -Uri "http://127.0.0.1:$SmokePort/bundle.js" -UseBasicParsing -TimeoutSec 5 -ErrorAction SilentlyContinue
            if ($bundle.StatusCode -lt 500) { Pass "Frontend bundle HTTP" } else { Fail 4 "bundle.js HTTP fail" }
        } catch {
            Fail 4 "Backend health: $_"
        }
        Get-Job | Stop-Job -ErrorAction SilentlyContinue
        Get-Job | Remove-Job -Force -ErrorAction SilentlyContinue
        Get-CimInstance Win32_Process -Filter "Name = 'node.exe'" -ErrorAction SilentlyContinue | ForEach-Object {
            if ($_.CommandLine -match "lib\\backend\\main\.js" -and $_.CommandLine -match ":$SmokePort") {
                Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
            }
        }
    }
}

Write-Section "QWebEngine smoke"
if (Test-Path $VenvPy) {
    $SmokeWe = Join-Path $IrisDir "scripts\smoke_webengine.py"
    if (Test-Path $SmokeWe) {
        & $VenvPy $SmokeWe --headless-ms 2000
        if ($LASTEXITCODE -ne 0) { Fail 5 "QWebEngine smoke" } else { Pass "QWebEngine local HTML" }
    }
}

Write-Host ""
if ($ExitCode -eq 0) {
    Write-Host "IRIS IDE DIAGNOSE: ALL CHECKS PASSED" -ForegroundColor Green
} else {
    Write-Host "IRIS IDE DIAGNOSE: FAILED (exit $ExitCode)" -ForegroundColor Red
}
exit $ExitCode
