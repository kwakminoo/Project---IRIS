# Iris 의존성 설치 스크립트 (Windows PowerShell)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "python 을 PATH 에서 찾을 수 없습니다. Python 3.11+ 를 설치하세요."
}

$venvPath = Join-Path $PSScriptRoot ".venv"
if (-not (Test-Path $venvPath)) {
    python -m venv .venv
}

$py = Join-Path $venvPath "Scripts\python.exe"
& $py -m pip install --upgrade pip
& $py -m pip install -r requirements.txt

Write-Host "Playwright Chromium 설치(선택)..."
& $py -m playwright install chromium

Write-Host "완료. 실행: .\.venv\Scripts\python.exe -m iris 또는 run.bat (PATH에 python이 있으면 python -m iris)"
