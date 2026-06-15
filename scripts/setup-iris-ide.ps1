# Iris IDE — Theia 의존성 설치
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$IdeDir = Join-Path $Root "iris-ide"

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

Require-Command "node" 18
Require-Command "yarn"

Push-Location $IdeDir
try {
    yarn install
    Write-Host "Iris IDE dependencies installed." -ForegroundColor Green
} finally {
    Pop-Location
}
