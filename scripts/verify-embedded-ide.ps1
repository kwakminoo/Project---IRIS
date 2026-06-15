# Iris Embedded IDE 전체 검증
param(
    [switch]$SkipE2E
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$IrisDir = Join-Path $Root "iris"
$VenvPy = Join-Path $IrisDir ".venv\Scripts\python.exe"
$Fail = $false

function Step($name, [scriptblock]$action) {
    Write-Host ""
    Write-Host "==> $name"
    & $action
    $code = $LASTEXITCODE
    if ($null -eq $code) { $code = 0 }
    if ($code -ne 0) {
        Write-Host "[FAIL] $name" -ForegroundColor Red
        $script:Fail = $true
        return
    }
    Write-Host "[PASS] $name" -ForegroundColor Green
}

Push-Location $Root
try {
    Step "IDE environment diagnose" {
        powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Root "scripts\diagnose-iris-ide.ps1") -SkipBackendSmoke
    }

    Step "Python environment" {
        if (-not (Test-Path $VenvPy)) { exit 1 }
        & $VenvPy -c "import iris; print('iris ok')"
    }

    Step "PyQt6-WebEngine import" {
        & $VenvPy (Join-Path $IrisDir "scripts\diagnose_webengine.py")
    }

    Step "QWebEngine local HTML" {
        & $VenvPy (Join-Path $IrisDir "scripts\smoke_webengine.py") --headless-ms 2000
    }

    Step "Theia build" {
        $main = Join-Path $Root "iris-ide\applications\browser\lib\backend\main.js"
        if (-not (Test-Path $main)) { exit 1 }
    }

    Step "Theia backend" {
        powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Root "scripts\diagnose-iris-ide.ps1") -SkipBackendSmoke:$false 2>$null
        # backend smoke is inside diagnose; re-run backend portion only if needed
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

    Step "Theia frontend" {
        $idx = Join-Path $Root "iris-ide\applications\browser\lib\frontend\index.html"
        if (-not (Test-Path $idx)) { exit 1 }
    }

    if (-not $SkipE2E) {
        Push-Location $IrisDir
        Step "Embedded Theia E2E" {
            & $VenvPy -m pytest tests/windows_smoke/test_embedded_theia_e2e.py -m "ide_e2e" -q --timeout=180
        }
        Pop-Location
    }

    Write-Host ""
    if ($Fail) {
        Write-Host "IRIS EMBEDDED IDE NOT READY" -ForegroundColor Red
        exit 1
    }
    Write-Host "IRIS EMBEDDED IDE READY" -ForegroundColor Green
    exit 0
}
finally {
    Pop-Location
}
