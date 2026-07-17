param(
    [switch]$StartEmulator,
    [int]$BootTimeoutSec = 180
)

$ErrorActionPreference = "Stop"

$AvdName = "IRIS_Mobile_Play"

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
    Write-Host "설치 프로토콜:"
    Write-Host ".\scripts\setup-iris-mobile-runtime.ps1 -Install"
    Write-Host ".\scripts\setup-iris-mobile-runtime.ps1 -AcceptLicenses"
    Write-Host ".\scripts\setup-iris-mobile-runtime.ps1 -CreateAvd"
    exit 2
}

$avds = & $status.Emulator -list-avds
if ($avds -notcontains $AvdName) {
    Write-Host "IRIS AVD가 없습니다: $AvdName"
    Write-Host "생성 명령:"
    Write-Host "avdmanager create avd -n $AvdName -k `"system-images;android-35;google_apis_playstore;x86_64`" -d pixel_7 --force"
    exit 3
}

$devices = & $status.Adb devices -l
Write-Host $devices
$running = $devices | Select-String -Pattern "emulator-\d+\s+device"

if (-not $running -and $StartEmulator) {
    Start-Process -FilePath $status.Emulator -ArgumentList @("-avd", $AvdName) -WindowStyle Hidden
    & $status.Adb wait-for-device
    $devices = & $status.Adb devices -l
    $running = $devices | Select-String -Pattern "emulator-\d+\s+device"
}

if (-not $running) {
    Write-Host "ADB에 연결된 실행 중인 IRIS 에뮬레이터가 없습니다. 실행하려면 -StartEmulator를 명시하세요."
    exit 4
}

$serial = ($running[0].ToString().Split(" ", [System.StringSplitOptions]::RemoveEmptyEntries))[0]
$deadline = (Get-Date).AddSeconds($BootTimeoutSec)
do {
    $booted = (& $status.Adb -s $serial shell getprop sys.boot_completed).Trim()
    if ($booted -eq "1") {
        Write-Host "IRIS mobile runtime ready"
        exit 0
    }
    Start-Sleep -Seconds 2
} while ((Get-Date) -lt $deadline)

Write-Host "에뮬레이터 부팅 완료 확인 시간이 초과되었습니다."
exit 5
