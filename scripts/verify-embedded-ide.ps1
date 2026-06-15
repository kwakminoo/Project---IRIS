# Iris Embedded IDE 전체 검증
param(
    [switch]$SkipE2E,
    [switch]$IncludeGui
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$IrisDir = Join-Path $Root "iris"
$VenvPy = Join-Path $IrisDir ".venv\Scripts\python.exe"
$Fail = $false
$Results = @()

function Step($name, [scriptblock]$action) {
    Write-Host ""
    Write-Host "==> $name"
    & $action
    $code = $LASTEXITCODE
    if ($null -eq $code) { $code = 0 }
    if ($code -ne 0) {
        Write-Host "[FAIL] $name" -ForegroundColor Red
        $script:Fail = $true
        $script:Results += "[FAIL] $name"
        return
    }
    Write-Host "[PASS] $name" -ForegroundColor Green
    $script:Results += "[PASS] $name"
}

Push-Location $Root
try {
    Step "Python·Qt·WebEngine" {
        if (-not (Test-Path $VenvPy)) { exit 1 }
        & $VenvPy (Join-Path $IrisDir "scripts\diagnose_webengine.py")
    }

    Step "Theia Build" {
        $main = Join-Path $Root "iris-ide\applications\browser\lib\backend\main.js"
        $idx = Join-Path $Root "iris-ide\applications\browser\lib\frontend\index.html"
        $bundle = Join-Path $Root "iris-ide\applications\browser\lib\frontend\bundle.js"
        if (-not (Test-Path $main)) { exit 1 }
        if (-not (Test-Path $idx)) { exit 1 }
        if (-not (Test-Path $bundle)) { exit 1 }
    }

    Step "Theia Backend HTTP" {
        $port = 3197
        $entry = Join-Path $Root "iris-ide\applications\browser\lib\backend\main.js"
        $node = Join-Path $Root "iris-ide\node_modules\node-win-x64\bin\node.exe"
        if (-not (Test-Path $node)) { $node = "node" }
        $p = Start-Process -FilePath $node -ArgumentList @($entry, $Root, "--hostname=127.0.0.1", "--port=$port") -PassThru -WindowStyle Hidden
        Start-Sleep -Seconds 10
        try {
            $r = Invoke-WebRequest "http://127.0.0.1:$port/" -UseBasicParsing -TimeoutSec 5
            if ($r.StatusCode -ge 500) { exit 1 }
        } finally {
            Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
        }
    }

    Step "Theia Frontend Bundle HTTP" {
        $port = 3196
        $entry = Join-Path $Root "iris-ide\applications\browser\lib\backend\main.js"
        $node = Join-Path $Root "iris-ide\node_modules\node-win-x64\bin\node.exe"
        if (-not (Test-Path $node)) { $node = "node" }
        $p = Start-Process -FilePath $node -ArgumentList @($entry, $Root, "--hostname=127.0.0.1", "--port=$port") -PassThru -WindowStyle Hidden
        Start-Sleep -Seconds 10
        try {
            $b = Invoke-WebRequest "http://127.0.0.1:$port/bundle.js" -UseBasicParsing -TimeoutSec 5
            if ($b.StatusCode -ge 500) { exit 1 }
        } finally {
            Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
        }
    }

    Step "WebEngine Local HTML" {
        & $VenvPy (Join-Path $IrisDir "scripts\smoke_webengine.py") --headless-ms 2000
    }

    $runGui = $IncludeGui -or (-not $SkipE2E)
    if ($runGui) {
        Push-Location $IrisDir
        Step "Embedded Theia Load + Shell Readiness" {
            & $VenvPy -m pytest tests/windows_smoke/test_embedded_theia_e2e.py -m "ide_e2e" -q
        }
        Pop-Location
    } else {
        Write-Host ""
        Write-Host "[SKIP] GUI E2E (use -IncludeGui or omit -SkipE2E)" -ForegroundColor Yellow
    }

    Write-Host ""
    foreach ($r in $Results) { Write-Host $r }
    Write-Host ""
    if ($Fail) {
        Write-Host "IRIS EMBEDDED IDE NOT READY" -ForegroundColor Red
        exit 1
    }
    if (-not $runGui) {
        Write-Host "IRIS EMBEDDED IDE PARTIAL (GUI E2E skipped)" -ForegroundColor Yellow
        exit 2
    }
    Write-Host "IRIS EMBEDDED IDE READY" -ForegroundColor Green
    exit 0
}
finally {
    Pop-Location
}
