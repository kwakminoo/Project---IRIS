# Embedded Theia 무한 로딩 분석

## 1. 로딩 화면을 표시하는 코드

- `MainWindow._start_ide_backend_and_load()` → `EmbeddedTheiaView.set_preflight()` / `set_starting()`
- `EmbeddedTheiaView.load_url()` → `_show_loading_overlay()` (WebView 위 오버레이)
- **수정 전**: `QStackedWidget`의 `_starting` 페이지가 별도 Stack 레이어로 존재

## 2. QWebEngineView를 표시하는 코드

- `EmbeddedTheiaView._ensure_web_view()` — `_WebContainer` 내부에 `QWebEngineView` 생성
- `load_url()` — `_stack.setCurrentWidget(self._web_container)` 후 `setUrl()`
- **수정 전 READY 경로**: Probe 성공 시 `_state = READY`만 설정, Stack 전환 없음

## 3. STARTING → READY 상태 전환 위치

| 단계 | 수정 전 | 수정 후 |
|------|---------|---------|
| Backend 준비 | `set_starting()` → `STARTING` | `BACKEND_STARTING` |
| Frontend 로드 | `load_url()` → `STARTING` | `FRONTEND_LOADING` |
| Shell 확인 | Probe 성공 → `READY` (화면 전환 없음) | `_show_ready_webview()` → `READY` |

## 4. QStackedWidget의 현재 Widget 변경 위치

- `set_preflight()` / `set_starting()` (Backend 단계) → `_placeholder`
- `load_url()` → `_web_container`
- `_show_ready_webview()` → `_web_container` + 오버레이 숨김
- `set_error()` → `_error_panel`

## 5. Readiness Probe 코드와 실제 Selector

Theia 1.55 실제 DOM (iris-ide 빌드·CSS 확인):

```text
.theia-ApplicationShell
#theia-app-shell
body.iris-ide-shell          ← iris-product extension
.theia-Navigator
#theia-left-side-panel
.theia-Editor
.monaco-editor
.p-Panel-main
```

초기 HTML은 `<div class="theia-preload">`만 존재 — `preloadOnly` 조건으로 조기 READY 방지.

## 6. Probe 재시도 횟수와 Timeout

| 항목 | 수정 전 | 수정 후 |
|------|---------|---------|
| 초기 지연 | 없음 (400ms 간격 즉시) | 500ms |
| 간격 | 400ms | 750ms |
| 최대 대기 | 30s (75회) | 45s |
| Timeout 처리 | 단순 오류 메시지 | 마지막 Probe JSON 포함 |

## 7. Backend URL과 현재 Workspace

- Bind: `127.0.0.1:<3100–3199>`
- Frontend URL: `http://127.0.0.1:<port>?irisBridgePort=<bridge>`
- Workspace: `resolve_ide_workspace(settings)` → 기본 IRIS 저장소 루트

## 8. WebEngine Console 오류

- `IrisWebEnginePage.javaScriptConsoleMessage` — ERROR/WARNING 강조, WebSocket·CSP 키워드 태깅
- 로그: `%USERPROFILE%\.iris\logs\ide-webengine.log`

## 9. WebSocket·CSP·Host 관련 오류

- 일반 브라우저 `http://127.0.0.1:3100` HTTP 200 확인 → **경우 B** (Theia Backend 정상, Iris QWebEngine 문제)
- 내비게이션: `127.0.0.1:<IDE 포트>`만 허용, `file://`·외부 호스트 차단
- URL 정규화: `localhost` → `127.0.0.1`

## 10. 무한 로딩의 확정 원인

**경우 B 확정** — 일반 브라우저에서 Theia HTTP·Backend 정상.

**근본 원인 (복합)**:

1. **`loadProgress`가 `set_starting()` 호출** → Stack을 `_starting` 로딩 페이지로 되돌림 → WebView가 가려짐
2. **Readiness Probe 성공 시 `_show_ready_webview()` 없음** → 상태만 `READY`, 사용자는 로딩 화면 유지
3. 상태 머신이 `STARTING` 단일 값 — `loadProgress`·`loadStarted`가 READY 후에도 상태·Stack을 흔들 수 있음

## 11. 수정 예정 파일

- `iris/iris/ui/ide/embedded_theia_view.py` — 상태 머신·오버레이·Probe·`_show_ready_webview()`
- `iris/iris/ui/ide/iris_webengine_page.py` — 진단·내비게이션 제한
- `iris/iris/ui/main_window.py` — Backend 재사용·오류 분류
- `iris/tests/windows_smoke/test_embedded_theia_e2e.py` — Stack·READY 테스트
- `scripts/verify-embedded-ide.ps1` — 검증 단계 확장
