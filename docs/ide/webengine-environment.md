# WebEngine Environment

## Iris Python

항상 `iris\.venv\Scripts\python.exe`를 사용합니다.

```powershell
cd IRIS\iris
.\.venv\Scripts\python.exe -m iris
```

## 검증된 버전 (Windows 64-bit)

```
PyQt6==6.11.0
PyQt6-WebEngine==6.11.0
```

설치:

```powershell
.\.venv\Scripts\python.exe -m pip install PyQt6==6.11.0 PyQt6-WebEngine==6.11.0
```

## 진단

```powershell
# 저장소 루트
.\scripts\diagnose-iris-ide.ps1

# WebEngine만
.\iris\.venv\Scripts\python.exe .\iris\scripts\diagnose_webengine.py
.\iris\.venv\Scripts\python.exe .\iris\scripts\smoke_webengine.py
```

## QtWebEngineProcess

설치 후 경로:

```
iris\.venv\Lib\site-packages\PyQt6\Qt6\bin\QtWebEngineProcess.exe
```

없으면 `PyQt6-WebEngine-Qt6` 재설치.

## 로그

| 파일 | 내용 |
|------|------|
| `~/.iris/logs/ide-webengine.log` | Chromium 콘솔·렌더 프로세스 |
| `~/.iris/logs/ide-preflight.log` | IDE 시작 전 점검 |
| `~/.iris/logs/ide-backend.log` | Theia Node backend |
| `~/.iris/logs/ide-recovery.log` | 환경 복구 pip/yarn |

## GPU 이슈 (진단용)

일시적으로만 시험:

```powershell
$env:QTWEBENGINE_CHROMIUM_FLAGS="--disable-gpu"
.\.venv\Scripts\python.exe -m iris
```

영구 비활성화는 권장하지 않습니다.
