# IRIS Hybrid Router 벤치마크 (Windows)
param(
    [string]$Modes = "hybrid,frontier_first,unified_only",
    [string]$Out = "iris\tmp_router_benchmark.json"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path (Join-Path $Root "iris"))) {
    $Root = Split-Path -Parent $PSScriptRoot
}
Set-Location $Root
python iris/scripts/benchmark_router.py --modes $Modes --out $Out
