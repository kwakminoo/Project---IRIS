# Iris 의존성 설치 스크립트 (Windows PowerShell)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Python 3.11 권장 (기본 `python`이 3.13이면 PyQt6 DLL/ TTS 이슈가 잦음)
$pyLauncher = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    $py311 = & py -3.11 -c "import sys; print(sys.executable)" 2>$null
    if ($LASTEXITCODE -eq 0 -and $py311) {
        $pyLauncher = $py311.Trim()
    }
}
if (-not $pyLauncher) {
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        Write-Error "python 을 PATH 에서 찾을 수 없습니다. Python 3.11을 설치하세요. (https://www.python.org/downloads/)"
    }
    $pyLauncher = "python"
    $ver = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
    if ([version]$ver -ge [version]"3.13") {
        Write-Warning "현재 python=$ver 입니다. Iris는 Python 3.11 venv를 권장합니다: py -3.11 -m venv .venv"
    }
}

$venvPath = Join-Path $PSScriptRoot ".venv"
if (-not (Test-Path $venvPath)) {
    Write-Host "venv 생성: $pyLauncher -m venv .venv"
    & $pyLauncher -m venv .venv
}

$py = Join-Path $venvPath "Scripts\python.exe"
& $py -m pip install --upgrade pip
& $py -m pip install -r requirements.txt

# WebEngine — IDE 임베드 필수 (Windows)
$weCheck = & $py -c "from PyQt6.QtWebEngineWidgets import QWebEngineView" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "PyQt6-WebEngine 설치 중..." -ForegroundColor Yellow
    & $py -m pip install "PyQt6-WebEngine==6.11.0"
}

# Qt 바이너리 번들 누락 시 조기 실패 (OneDrive/불완전 설치 대비)
$qtCheck = & $py -c "from PyQt6.QtGui import QGuiApplication; print('ok')" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "PyQt6 Qt 바이너리 복구 중 (PyQt6-Qt6 재설치)..." -ForegroundColor Yellow
    & $py -m pip install --force-reinstall "PyQt6==6.11.0" "PyQt6-Qt6==6.11.1"
}

Write-Host "Playwright Chromium 설치(선택)..."
& $py -m playwright install chromium

Write-Host "완료. 실행:"
Write-Host "  cd iris"
Write-Host "  .\.venv\Scripts\python.exe -m iris"
Write-Host "또는 run.bat"
