# Iris IDE — Theia 의존성 설치
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$IdeDir = Join-Path $Root "iris-ide"
$Node20 = Join-Path $IdeDir "node_modules\node-win-x64\bin\node.exe"
$NodeGyp = Join-Path $IdeDir "node_modules\node-gyp\bin\node-gyp.js"
$NativePkgs = @("keytar", "drivelist", "node-pty")

function Require-Command($name, $minVersion = $null) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if (-not $cmd) {
        throw "$name 이(가) 설치되어 있지 않습니다."
    }
    if ($minVersion -and $name -eq "node") {
        $ver = (& node -v) -replace '^v', ''
        $major = [int]($ver.Split('.')[0])
        if ($major -lt $minVersion) {
            throw "Node.js $minVersion+ 필요 (현재: $ver)"
        }
    }
}

function Rebuild-NativeModules {
    if (-not (Test-Path $Node20)) {
        Write-Host "Node 20 runtime not found — run yarn install first." -ForegroundColor Yellow
        return
    }
    foreach ($pkg in $NativePkgs) {
        $dir = Join-Path $IdeDir "node_modules\$pkg"
        if (-not (Test-Path $dir)) { continue }
        Write-Host "Rebuilding native module: $pkg (Node 20)..." -ForegroundColor Cyan
        Push-Location $dir
        try {
            & $Node20 $NodeGyp rebuild | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "node-gyp rebuild failed for $pkg" }
        } finally {
            Pop-Location
        }
    }
}

Require-Command "node" 18
if (-not (Get-Command yarn -ErrorAction SilentlyContinue)) {
    Write-Host "Yarn not found — installing via npm..." -ForegroundColor Yellow
    npm install -g yarn
}
Require-Command "yarn"

# Iris venv WebEngine 사전 점검
$IrisPy = Join-Path $Root "iris\.venv\Scripts\python.exe"
if (Test-Path $IrisPy) {
    & $IrisPy -c "from PyQt6.QtWebEngineWidgets import QWebEngineView" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Installing PyQt6-WebEngine into Iris venv..." -ForegroundColor Yellow
        & $IrisPy -m pip install "PyQt6==6.11.0" "PyQt6-WebEngine==6.11.0"
    }
}

Push-Location $IdeDir
try {
    yarn install --ignore-scripts
    if ($LASTEXITCODE -ne 0) { throw "yarn install failed" }

    $RipgrepPost = Join-Path $IdeDir "node_modules\@vscode\ripgrep\lib\postinstall.js"
    if (Test-Path $RipgrepPost) {
        Write-Host "Ensuring ripgrep binary..." -ForegroundColor Yellow
        node $RipgrepPost
    }

    Rebuild-NativeModules
    Write-Host "Iris IDE dependencies installed." -ForegroundColor Green
} finally {
    Pop-Location
}
