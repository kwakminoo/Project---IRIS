# Iris — SearXNG (Google 전용) Docker 기동
$ErrorActionPreference = "Stop"

# Docker Desktop PATH (새 터미널에 docker가 없을 때)
$dockerBin = "C:\Program Files\Docker\Docker\resources\bin"
if (Test-Path $dockerBin) {
    $env:PATH = "$dockerBin;$env:PATH"
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "Docker가 없습니다. winget install Docker.DockerDesktop 후 Docker Desktop을 실행하세요."
    exit 1
}

$dd = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
if (-not (Get-Process "Docker Desktop" -ErrorAction SilentlyContinue) -and (Test-Path $dd)) {
    Write-Host "Docker Desktop 시작 중..."
    Start-Process $dd
    $deadline = (Get-Date).AddMinutes(3)
    while ((Get-Date) -lt $deadline) {
        docker info 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { break }
        Start-Sleep -Seconds 3
    }
}

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$dir = Join-Path $here "searxng"
Set-Location $dir
Write-Host "SearXNG 시작 (Google only) — http://127.0.0.1:8080"
docker compose up -d
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$irisEnv = Join-Path (Split-Path (Split-Path $here -Parent) -Parent) "iris\.env"
if (Test-Path $irisEnv) {
    $text = Get-Content $irisEnv -Raw
    if ($text -notmatch "SEARXNG_BASE_URL") {
        Add-Content $irisEnv "`nSEARXNG_BASE_URL=http://127.0.0.1:8080`nIRIS_SEARCH_PROVIDER=searxng"
        Write-Host "iris/.env 에 SEARXNG_BASE_URL, IRIS_SEARCH_PROVIDER 추가함."
    }
} else {
    Write-Host "iris/.env 에 SEARXNG_BASE_URL=http://127.0.0.1:8080 를 추가하세요."
}
Write-Host "완료. 브라우저: http://127.0.0.1:8080"
