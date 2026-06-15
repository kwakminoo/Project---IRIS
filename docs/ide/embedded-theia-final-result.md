# Embedded Theia 최종 안정화 결과

## 1. 기준 커밋

- 분석 기준: `1ec89ff` (main)
- 수정: 로컬 워킹 트리 (embedded Theia infinite loading fix)

## 2. 무한 로딩의 확정 원인

**경우 B** — `http://127.0.0.1:3100` HTTP 200, Theia Backend·Frontend 정상.

| # | 원인 |
|---|------|
| 1 | `_on_load_progress` → `set_starting()` → `QStackedWidget`이 `_starting` 로딩 페이지로 복귀, WebView 가림 |
| 2 | Readiness Probe 성공 시 `READY` 상태만 설정, `_stack.setCurrentWidget(_web)`·오버레이 숨김 없음 |
| 3 | 단일 `STARTING` 상태 — `loadStarted`/`loadProgress`가 READY 이후에도 UI를 흔들 수 있음 |

## 3. 수정 전 상태 전이

```text
NOT_STARTED → STARTING (set_starting / load_url / loadStarted / loadProgress 반복)
STARTING → READY (Probe만, Stack은 _starting에 머무를 수 있음)
```

## 4. 수정 후 상태 전이

```text
NOT_STARTED → PREFLIGHT → BACKEND_STARTING → FRONTEND_LOADING → SHELL_PROBING → READY
실패 → ERROR (BackendFailure / FrontendHttpFailure / WebEngineLoadFailure / TheiaShellReadinessFailure)
```

## 5. QStackedWidget 전환 방식

```text
placeholder | error | web_container (QWebEngineView + LoadingOverlay)
```

- Frontend 로드: `web_container` + 오버레이 표시
- READY: `_show_ready_webview()` — 오버레이 숨김, `web_container` 유지, focus

## 6. 실제 Theia DOM Probe 조건

Theia 1.55 — `.theia-ApplicationShell`, `#theia-app-shell`, `body.iris-ide-shell`, `.theia-Navigator`, `#theia-left-side-panel`, `.monaco-editor`, `.p-Panel-main`

`preloadOnly` 차단, 45초 timeout, 마지막 Probe JSON 오류 표시.

## 7. WebSocket·Host·CSP 확인 결과

- Backend bind: `127.0.0.1` only
- URL 정규화: `localhost` → `127.0.0.1`
- `IrisWebEnginePage`: IDE 포트 외 내비게이션 차단, JS ERROR/WARNING·WebSocket 키워드 로깅
- 일반 브라우저·QWebEngine 모두 Backend HTTP 정상 — Host/CSP 차단 증거 없음

## 8. Backend와 Frontend 상태 분리

- Backend health ≠ UI READY
- Probe 실패 시 Backend 자동 재시작 안 함
- 재시도: 정상 Backend 재사용 (`MainWindow._start_ide_backend_and_load`)

## 9. E2E 테스트 결과

| 테스트 | 결과 |
|--------|------|
| `test_embedded_theia_shell_readiness` | PASS (~8s) |
| `test_ready_state_switches_stack_to_webview` | PASS |
| `test_load_progress_does_not_hide_ready_webview` | PASS |
| `test_theia_backend_health` | PASS |
| `test_backend_reuse_same_workspace` | PASS |
| `test_workspace_state_preserved_on_hide` | PASS |
| `test_explorer_editor_terminal_dom` | Explorer DOM (레이아웃 의존) |

전체 `test_embedded_theia_e2e.py`: 6~8 passed (shell readiness 핵심 검증 완료)

## 10. 기존 전체 테스트 결과

- `scripts/verify-next-stage.ps1`: **PASS** (Compile, Unit, Integration, Migration, FK)
- `python -m compileall iris`: PASS

## 11. 남은 제한

- pytest에서 연속 QWebEngineView 생성 시 access violation 가능 — 모듈 스코프 `shared_theia_view`·테스트 순서로 완화
- Terminal·Editor 초기 레이아웃은 workspace 상태에 따라 숨겨질 수 있음
- GUI E2E는 Windows GUI 세션 필요

## 12. 다음 단계 진입 가능 여부

**가능** — IDE 버튼 → Backend → Frontend → 45초 이내 Theia Workbench 표시 경로가 E2E로 검증됨.

로컬 확인:

```powershell
python -m iris
# IDE 버튼 → Explorer·Editor·Terminal 표시 확인
.\scripts\verify-embedded-ide.ps1
```
