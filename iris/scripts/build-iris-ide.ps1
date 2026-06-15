# iris/ 폴더에서 실행해도 저장소 루트의 build 스크립트를 호출합니다.
$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
& (Join-Path $RepoRoot "scripts\build-iris-ide.ps1") @args
