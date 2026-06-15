# IRIS Windows 다음 단계 진입 품질 관문
param(
    [switch]$IncludeSmoke,
    [switch]$IncludeGuiSmoke
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$irisDir = Join-Path $repoRoot "iris"

if (-not (Test-Path $irisDir)) {
    Write-Error "iris directory not found: $irisDir"
}

function Invoke-Step {
    param(
        [string]$Name,
        [scriptblock]$Action
    )
    Write-Host ""
    Write-Host "==> $Name"
    & $Action
    $exitCode = $LASTEXITCODE
    if ($null -eq $exitCode) { $exitCode = 0 }
    if ($exitCode -ne 0) {
        Write-Host "[FAIL] $Name"
        return $false
    }
    Write-Host "[PASS] $Name"
    return $true
}

$allPassed = $true
Push-Location $repoRoot
try {
    if (-not (Invoke-Step "Compile" { python -m compileall iris -q })) {
        $allPassed = $false
        throw "compile failed"
    }

    Push-Location $irisDir

    if (-not (Invoke-Step "Unit Tests" {
        python -m pytest -q -m "not windows_smoke and not external_service and not requires_model"
    })) { $allPassed = $false; throw "unit tests failed" }

    if (-not (Invoke-Step "Integration Tests" {
        python -m pytest -v -m "integration and not windows_smoke and not external_service and not requires_model" --timeout=180
    })) { $allPassed = $false; throw "integration tests failed" }

    if (-not (Invoke-Step "Migration" {
        python -m pytest -q tests/test_sqlite_task_repositories.py::test_schema_migrations_applied tests/test_task_runtime_stabilization.py::test_migration_failure_is_not_silently_ignored
    })) { $allPassed = $false; throw "migration tests failed" }

    if (-not (Invoke-Step "Foreign Key Check" {
        python -m pytest -q tests/test_task_runtime_stabilization.py::test_foreign_key_check_has_no_errors
    })) { $allPassed = $false; throw "foreign key check failed" }

    if ($IncludeSmoke) {
        $artifactRoot = Join-Path $irisDir "artifacts/windows-smoke"
        if (Test-Path $artifactRoot) { Remove-Item -Recurse -Force $artifactRoot }
        New-Item -ItemType Directory -Force -Path $artifactRoot | Out-Null
        Set-Content -Path (Join-Path $artifactRoot "created-processes.json") -Value "[]" -Encoding utf8

        $smokeMarker = "windows_smoke and not windows_smoke_gui"
        if ($IncludeGuiSmoke) { $smokeMarker = "windows_smoke" }

        if (-not (Invoke-Step "Windows Smoke" {
            python -m pytest tests/windows_smoke -m $smokeMarker -v --timeout=120 `
                --junitxml=artifacts/windows-smoke/junit.xml
        })) { $allPassed = $false; throw "smoke tests failed" }

        & (Join-Path $repoRoot "scripts/cleanup-smoke-processes.ps1") -ArtifactsRoot "iris/artifacts/windows-smoke"
    }

    Write-Host ""
    if (-not $allPassed) {
        Write-Host "IRIS is NOT ready for the next development phase."
        exit 1
    }
    Write-Host "IRIS is ready for the next development phase."
    exit 0
}
catch {
    Write-Host ""
    Write-Host "IRIS is NOT ready for the next development phase."
    exit 1
}
finally {
    Pop-Location
    Pop-Location
}
