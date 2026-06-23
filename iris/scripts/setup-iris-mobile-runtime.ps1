param(
    [switch]$Install,
    [switch]$AcceptLicenses,
    [switch]$CreateAvd
)

$ErrorActionPreference = "Stop"

$Packages = @(
    "platform-tools",
    "emulator",
    "platforms;android-35",
    "system-images;android-35;google_apis_playstore;x86_64"
)
$AvdName = "IRIS_Mobile_Play"
$SystemImage = "system-images;android-35;google_apis_playstore;x86_64"

function Get-CandidateSdkRoots {
    $roots = @()
    if ($env:ANDROID_HOME) { $roots += $env:ANDROID_HOME }
    if ($env:ANDROID_SDK_ROOT) { $roots += $env:ANDROID_SDK_ROOT }
    if ($env:LOCALAPPDATA) { $roots += (Join-Path $env:LOCALAPPDATA "Android\Sdk") }
    $roots += (Join-Path $HOME "AppData\Local\Android\Sdk")
    $roots += (Join-Path $HOME "Android\Sdk")
    $roots | Select-Object -Unique
}

function Find-FirstFile($Folder, $Names) {
    foreach ($name in $Names) {
        $path = Join-Path $Folder $name
        if (Test-Path -LiteralPath $path -PathType Leaf) {
            return $path
        }
    }
    return $null
}

function Get-AndroidSdkStatus {
    foreach ($root in Get-CandidateSdkRoots) {
        if (-not (Test-Path -LiteralPath $root -PathType Container)) {
            continue
        }
        $toolsBin = Join-Path $root "cmdline-tools\latest\bin"
        return [pscustomobject]@{
            SdkRoot = $root
            SdkManager = Find-FirstFile $toolsBin @("sdkmanager.bat", "sdkmanager.exe", "sdkmanager")
            AvdManager = Find-FirstFile $toolsBin @("avdmanager.bat", "avdmanager.exe", "avdmanager")
            Adb = Find-FirstFile (Join-Path $root "platform-tools") @("adb.exe", "adb")
            Emulator = Find-FirstFile (Join-Path $root "emulator") @("emulator.exe", "emulator")
        }
    }
    return [pscustomobject]@{
        SdkRoot = $null
        SdkManager = $null
        AvdManager = $null
        Adb = $null
        Emulator = $null
    }
}

$status = Get-AndroidSdkStatus
$missing = @()
if (-not $status.SdkManager) { $missing += "Android SDK Command-line Tools / sdkmanager" }
if (-not $status.AvdManager) { $missing += "Android SDK Command-line Tools / avdmanager" }
if (-not $status.Adb) { $missing += "platform-tools / adb" }
if (-not $status.Emulator) { $missing += "emulator" }

if ($missing.Count -gt 0) {
    Write-Host "Android 모바일 런타임 필수 패키지가 설치되어 있지 않습니다."
    Write-Host "누락 항목:"
    $missing | ForEach-Object { Write-Host " - $_" }
    Write-Host ""
    Write-Host "설치 명령 미리보기:"
    Write-Host "sdkmanager --install `"$($Packages -join '" "')`""
    Write-Host "sdkmanager --licenses"
    Write-Host "avdmanager create avd -n $AvdName -k `"$SystemImage`" -d pixel_7 --force"
    if (-not $Install) {
        Write-Host ""
        Write-Host "실행하려면 Android SDK Command-line Tools를 준비한 뒤 -Install 플래그를 명시하세요."
        exit 2
    }
}

if ($AcceptLicenses) {
    if (-not $status.SdkManager) { throw "sdkmanager를 찾을 수 없습니다." }
    & $status.SdkManager --licenses
}

if ($Install) {
    if (-not $status.SdkManager) { throw "sdkmanager를 찾을 수 없습니다. Android SDK Command-line Tools를 먼저 설치하세요." }
    & $status.SdkManager --install @Packages
    $status = Get-AndroidSdkStatus
}

if ($CreateAvd) {
    if (-not $status.AvdManager) { throw "avdmanager를 찾을 수 없습니다." }
    $existing = @()
    if ($status.Emulator) {
        $existing = & $status.Emulator -list-avds
    }
    if ($existing -notcontains $AvdName) {
        & $status.AvdManager create avd -n $AvdName -k $SystemImage -d pixel_7 --force
    }
}

Write-Host "IRIS mobile runtime install protocol complete."
