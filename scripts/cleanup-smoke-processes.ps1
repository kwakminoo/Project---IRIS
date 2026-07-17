# Windows Smoke — 테스트가 등록한 PID만 종료
param(
    [string]$ArtifactsRoot = "iris/artifacts/windows-smoke"
)

$ErrorActionPreference = "Continue"
$repoRoot = Split-Path -Parent $PSScriptRoot
$artifactDir = Join-Path $repoRoot $ArtifactsRoot
$jsonPath = Join-Path $artifactDir "created-processes.json"

if (-not (Test-Path $jsonPath)) {
    Write-Host "No created-processes.json at $jsonPath — nothing to clean."
    exit 0
}

try {
    $entries = Get-Content $jsonPath -Raw -Encoding UTF8 | ConvertFrom-Json
} catch {
    Write-Host "Failed to parse $jsonPath : $_"
    exit 0
}

if (-not $entries) {
    Write-Host "Empty process registry."
    exit 0
}

foreach ($entry in $entries) {
    $pid = [int]$entry.pid
    if ($pid -le 0) { continue }

    $proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
    if (-not $proc) { continue }

    $expectedExe = [string]$entry.exe
    if ($expectedExe -and $proc.ProcessName.ToLower() -ne $expectedExe.Replace('.exe','').ToLower()) {
        Write-Host "Skip PID $pid — process name mismatch ($($proc.ProcessName) vs $expectedExe)"
        continue
    }

    if ($null -ne $entry.create_time) {
        try {
            $expected = [double]$entry.create_time
            $actual = $proc.StartTime.ToUniversalTime().Subtract([datetime]'1970-01-01').TotalSeconds
            if ([Math]::Abs($actual - $expected) -gt 2.0) {
                Write-Host "Skip PID $pid — create_time mismatch (PID reuse suspected)"
                continue
            }
        } catch {
            Write-Host "Skip PID $pid — could not verify create_time"
            continue
        }
    }

    Write-Host "Terminating registered smoke process PID $pid ($($proc.ProcessName))"
    Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
}

[System.IO.File]::WriteAllText($jsonPath, "[]")
Write-Host "Smoke process cleanup complete."
