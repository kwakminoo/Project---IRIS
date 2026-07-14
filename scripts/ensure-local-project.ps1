# Iris 프로젝트를 OneDrive 밖 로컬 경로에 미러링합니다.
# ponytail: robocopy 1회 미러 — 대용량 .venv/node_modules는 제외 후 대상에서 install.ps1 실행
$ErrorActionPreference = "Stop"

$src = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$dest = Join-Path $env:USERPROFILE "Projects\IRIS"

Write-Host "원본: $src"
Write-Host "로컬: $dest"

New-Item -ItemType Directory -Path (Split-Path $dest) -Force | Out-Null

$excludeDirs = @(
    ".venv", ".venv-tts", "node_modules", "__pycache__", ".pytest_cache",
    ".pytest_tmp", ".pytest_tmp2", ".pytest_tmp3", ".pytest_tmp4", ".pytest_tmp5",
    ".pytest_tmp_mobile", ".pytest_tmp_mobile2", ".pytest_tmp_mobile3",
    ".pytest_tmp_mobile4", ".pytest_tmp_mobile_unit", ".pytest_tmp_mobile_unit2"
)
$xd = ($excludeDirs | ForEach-Object { "/XD", $_ })

robocopy $src $dest /MIR /R:2 /W:2 /NFL /NDL /NJH /NJS @xd | Out-Null
if ($LASTEXITCODE -ge 8) {
    throw "robocopy 실패 (exit $LASTEXITCODE)"
}

$install = Join-Path $dest "iris\install.ps1"
if (-not (Test-Path $install)) {
    throw "대상 install.ps1 없음: $install"
}

Push-Location (Join-Path $dest "iris")
& $install
Pop-Location

$marker = Join-Path $dest "LOCAL_PROJECT.txt"
@(
    "Iris local project root (OneDrive sync 비사용)"
    "Created: $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
    "Source snapshot: $src"
    "Run: cd `"$($dest)\iris`"; .\.venv\Scripts\python.exe -m iris"
) | Set-Content -Path $marker -Encoding UTF8

Write-Host "완료. Cursor에서 이 폴더를 열세요: $dest" -ForegroundColor Green
