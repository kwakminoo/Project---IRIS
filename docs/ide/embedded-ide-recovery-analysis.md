# Embedded IDE Recovery Analysis

> Generated: 2026-06-15 | Baseline commit: `d5f7642`

## 1. 실제 Iris Python 인터프리터

| 항목 | 값 |
|------|-----|
| `sys.executable` | `iris\.venv\Scripts\python.exe` |
| Python | 3.13.7 64-bit |
| 가상환경 | `IRIS\iris\.venv` |

Iris는 `iris\install.ps1`이 만든 `.venv`를 사용합니다. PATH의 전역 `python`이 아닙니다.

## 2. Qt 관련 패키지 버전 조합

| 패키지 | 버전 |
|--------|------|
| PyQt6 | 6.11.0 |
| PyQt6-Qt6 | 6.11.0 |
| PyQt6-sip | 13.11.1 |
| PyQt6-WebEngine | 6.11.0 |
| PyQt6-WebEngine-Qt6 | 6.11.1 |
| QT_VERSION_STR | 6.11.0 |
| PYQT_VERSION_STR | 6.11.0 |

## 3. WebEngine import의 실제 예외 (최초)

```
ModuleNotFoundError: No module named 'PyQt6.QtWebEngineWidgets'
```

`pip show PyQt6`는 성공했으나 **PyQt6-WebEngine 패키지가 venv에 설치되지 않음**이 근본 원인이었습니다.

## 4. QtWebEngineProcess 존재 여부

설치 후:

```
iris\.venv\Lib\site-packages\PyQt6\Qt6\bin\QtWebEngineProcess.exe
```

## 5. Theia package 버전

- `@theia/*`: **1.55.0** (iris-ide/package.json resolutions)
- Node (bundled): **20.18.1**
- Yarn: **1.22.22**

## 6. Theia Backend entry 존재 여부

`iris-ide\applications\browser\lib\backend\main.js` — **존재**

## 7. Frontend build 산출물 존재 여부

- `lib\frontend\index.html` — 존재
- `lib\frontend\bundle.js` — 존재

## 8. Backend 단독 실행 결과

`scripts\start-iris-ide-backend.ps1` — Node 20 + `main.js` + workspace + `--hostname=127.0.0.1`

HTTP `/` 및 `/bundle.js` 200 응답 확인.

## 9. QWebEngine 단독 실행 결과

`iris\scripts\smoke_webengine.py` — **PASS**

- `loadFinished(True)`
- `document.title == IRIS_WEBENGINE_OK`

## 10. 수정 예정 파일

- `iris/requirements-base.txt` — PyQt6==6.11.0 고정
- `iris/requirements-windows.txt` — PyQt6-WebEngine==6.11.0 고정
- `iris/install.ps1` — WebEngine 설치 검증
- `iris/iris/ui/ide/embedded_theia_view.py` — import 오류·상태·readiness probe
- `iris/iris/ui/ide/iris_webengine_page.py` — 신규
- `iris/iris/infrastructure/ide/ide_preflight.py` — 신규
- `iris/iris/infrastructure/ide/ide_backend_worker.py` — 신규
- `iris/iris/infrastructure/ide/ide_backend_manager.py` — health check 강화
- `iris/iris/ui/main_window.py` — 비동기 backend·복구 UX
- `scripts/diagnose-iris-ide.ps1` — 신규
- `scripts/verify-embedded-ide.ps1` — 신규
