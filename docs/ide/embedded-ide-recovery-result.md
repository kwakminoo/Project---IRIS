# Embedded IDE Recovery Result

> Date: 2026-06-15

## 1. 기준 커밋

`d5f7642` (main) — 작업 후 로컬 수정 포함

## 2. 최초 오류의 실제 원인

**`iris\.venv`에 `PyQt6-WebEngine` 패키지가 설치되지 않음.**

- `PyQt6` 6.11.0은 설치되어 UI는 동작
- `from PyQt6.QtWebEngineWidgets import QWebEngineView` → `ModuleNotFoundError`
- `embedded_theia_view.py`의 `ImportError` 핸들러가 `_WEBENGINE = False`로 설정
- `load_url()`이 즉시 "PyQt6-WebEngine을 사용할 수 없습니다." 표시

Theia 빌드·backend는 이미 정상이었음.

## 3. 사용한 Python 인터프리터

`C:\Users\kwakm\OneDrive\Desktop\Cusor-Project\IRIS\iris\.venv\Scripts\python.exe` (3.13.7 amd64)

## 4. 최종 PyQt6/WebEngine 버전

- PyQt6==6.11.0
- PyQt6-WebEngine==6.11.0
- PyQt6-WebEngine-Qt6==6.11.1

## 5. 최종 Node/Theia 버전

- Node 20.18.1 (bundled)
- Theia 1.55.0
- Yarn 1.22.22

## 6. 수정한 requirements

- `iris/requirements-base.txt` — `PyQt6==6.11.0`
- `iris/requirements-windows.txt` — `PyQt6-WebEngine==6.11.0`

## 7. Theia build 산출물

- `iris-ide/applications/browser/lib/backend/main.js`
- `iris-ide/applications/browser/lib/frontend/index.html`
- `iris-ide/applications/browser/lib/frontend/bundle.js`

## 8. Backend 실행 명령

```
node main.js <workspace> --hostname=127.0.0.1 --port=<port>
```

CWD: `iris-ide/applications/browser`

## 9. QWebEngine 로딩 흐름

```
IDE 클릭 → preflight → worker에서 backend ensure_running
→ load_url → loadFinished → JS Theia shell probe → READY
→ __IRIS_BRIDGE_URL__ 주입
```

## 10. 오류 진단 개선

- ImportError + OSError 캡처, Python 경로·버전 표시
- 단계별 오류 메시지 (WebEngine / Build / Backend / Shell)
- `IrisWebEnginePage` → `ide-webengine.log`
- `IdePreflightReport` 구조화

## 11. E2E 테스트 결과

```
tests/windows_smoke/test_embedded_theia_e2e.py
  test_theia_backend_health — PASS
  test_backend_reuse_same_workspace — PASS
  test_webengine_local_html — windows_smoke_gui
  test_embedded_theia_shell_readiness — windows_smoke_gui
```

```
iris/scripts/smoke_webengine.py — PASS
scripts/diagnose-iris-ide.ps1 — ALL CHECKS PASSED
```

## 12. 기존 전체 테스트 결과

```
tests/test_ide_backend_manager.py — 5 passed
tests/test_main_window_workspace.py — 4 passed
```

## 13. 남은 제한

- GUI E2E(`windows_smoke_gui`)는 로컬 Windows GUI 세션 필요
- Explorer/Editor/Terminal DOM 상호작용 E2E는 Theia bridge API 확장 시 보강 가능
- Python 3.13 + PyQt6 6.11 조합 — CI matrix와 별도 검증 권장

## 14. 다음 단계 진입 가능 여부

**가능** — WebEngine 설치·진단·비동기 backend·readiness probe 완료.

사용자 확인:

1. `.\iris\.venv\Scripts\python.exe -m iris`
2. IDE 버튼 → 중앙 Theia workbench 표시
