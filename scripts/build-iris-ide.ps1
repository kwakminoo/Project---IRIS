# Iris IDE — Theia Browser Application 빌드
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$IdeDir = Join-Path $Root "iris-ide"
$RipgrepPost = Join-Path $IdeDir "node_modules\@vscode\ripgrep\lib\postinstall.js"
$Node20 = Join-Path $IdeDir "node_modules\node-win-x64\bin\node.exe"
$NodeGyp = Join-Path $IdeDir "node_modules\node-gyp\bin\node-gyp.js"
$NativePkgs = @("keytar", "drivelist", "node-pty")
$BackendMain = Join-Path $IdeDir "applications\browser\lib\backend\main.js"
$BackendNativeDir = Join-Path $IdeDir "applications\browser\lib\backend\native"

function Stop-IrisIdeBackendProcesses {
    # Iris/Theia backend가 native .node를 잡고 있으면 webpack EBUSY 발생
    $stopped = 0
    Get-CimInstance Win32_Process -Filter "Name = 'node.exe'" -ErrorAction SilentlyContinue | ForEach-Object {
        $cmd = $_.CommandLine
        if ($null -eq $cmd) { return }
        if ($cmd -match [regex]::Escape("iris-ide") -and $cmd -match "lib\\backend\\main\.js") {
            Write-Host "Stopping Iris IDE backend (PID $($_.ProcessId))..." -ForegroundColor Yellow
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
            $stopped++
        }
    }
    if ($stopped -gt 0) {
        Start-Sleep -Seconds 2
    }
}

function Ensure-Ripgrep {
    $rg = Join-Path $IdeDir "node_modules\@vscode\ripgrep\bin\rg.exe"
    if (-not (Test-Path $rg) -and (Test-Path $RipgrepPost)) {
        Write-Host "Downloading ripgrep binary..." -ForegroundColor Yellow
        node $RipgrepPost
    }
}

function Ensure-NativeModules {
    if (-not (Test-Path $Node20)) {
        throw "Node 20 runtime missing. Run scripts\setup-iris-ide.ps1 first."
    }
    foreach ($pkg in $NativePkgs) {
        $artifact = switch ($pkg) {
            "keytar" { Join-Path $IdeDir "node_modules\keytar\build\Release\keytar.node" }
            "drivelist" { Join-Path $IdeDir "node_modules\drivelist\build\Release\drivelist.node" }
            "node-pty" { Join-Path $IdeDir "node_modules\node-pty\build\Release\pty.node" }
        }
        if (Test-Path $artifact) { continue }
        Write-Host "Building $pkg..." -ForegroundColor Yellow
        Push-Location (Join-Path $IdeDir "node_modules\$pkg")
        try {
            & $Node20 $NodeGyp rebuild | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "node-gyp rebuild failed for $pkg" }
        } finally {
            Pop-Location
        }
    }
}

Ensure-Ripgrep
Ensure-NativeModules
Stop-IrisIdeBackendProcesses

Push-Location $IdeDir
try {
    yarn build
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "Build failed. If you see EBUSY on *.node:" -ForegroundColor Yellow
        Write-Host "  1. Close Iris (python -m iris) completely" -ForegroundColor Yellow
        Write-Host "  2. Wait a few seconds, then run this script again" -ForegroundColor Yellow
        Write-Host "  3. OneDrive sync can also lock files under OneDrive paths" -ForegroundColor Yellow
        throw "yarn build failed (exit $LASTEXITCODE)"
    }
    if (-not (Test-Path $BackendMain)) {
        throw "Backend entry not found: $BackendMain"
    }
    Write-Host "Iris IDE build complete." -ForegroundColor Green
    Write-Host "Backend entry: iris-ide\applications\browser\lib\backend\main.js"
} finally {
    Pop-Location
}
