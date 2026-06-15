# Embedded IDE Shell — 구현 결과

## 1. 기준 커밋

구현 완료 시점 working tree (embedded Theia IDE workspace).

## 2. 변경 파일 (요약)

### Python
- `iris/iris/ui/main_window.py` — QStackedWidget workspace 전환
- `iris/iris/ui/left_sidebar_panel.py`, `system_metrics_panel.py`, `workspace_action_panel.py`
- `iris/iris/ui/workspaces/*`, `iris/iris/ui/ide/*`
- `iris/iris/system/*` — MetricsWorker, GPU provider
- `iris/iris/infrastructure/ide/*` — Backend manager, Bridge, Resolver
- `iris/iris/config/settings.py` — `ide_workspace_path`
- `iris/requirements-windows.txt` — PyQt6-WebEngine

### TypeScript
- `iris-ide/` — Theia browser app + iris-bridge + iris-product

### 스크립트·문서·테스트
- `scripts/setup-iris-ide.ps1` 등 4개
- `docs/ide/*`, `docs/ui/workspace-switching.md`
- `protocol/*.json`
- `iris/tests/test_*workspace*`, `test_system_metrics`, `test_ide_*`, `test_coding_panel`

## 3. Persistent Sidebar 구조

`LeftSidebarPanel` = `WindowListPanel` (50%) + `SystemMetricsPanel` + `WorkspaceActionPanel`

## 4. Assistant·IDE Workspace 전환

`QStackedWidget`: index 0 Assistant, index 1 IDE. Toggle 버튼 `IDE` / `돌아가기`.

## 5. Theia 내장 방식

`EmbeddedTheiaView` (`QWebEngineView`) — `127.0.0.1` URL only.

## 6. Theia Backend 생명주기

`IdeBackendManager.ensure_running()` / `shutdown()` on app exit.

## 7. Editor·파일·Terminal 배치

Theia 기본 레이아웃: Explorer 좌측, Editor 중앙, Terminal/Problems/Output/Debug 하단.

## 8. Iris 구체·Coding Chat

`IrisCodingPanel` = `IrisOrbWidget` + `CodingChatView`

## 9. 음성·텍스트 요청 흐름

`CodingChatView` → `_on_coding_user_text` → `AgentWorker` (단일 `IrisAssistant`)

## 10. IDE Context 전달

HTTP bridge — `POST /context`, `GET /commands`

## 11. 아직 구현하지 않은 코딩 기능

- AI 코드 덮어쓰기, Patch 적용, Build/Test, Git Commit

## 12. 테스트 결과

```
657 passed, 46 skipped (pytest -q --ignore=tests/windows_smoke)
23 passed (IDE 전용 신규 테스트)
```

## 13. 다음 단계

1. `yarn build` 후 실제 Theia E2E 검증
2. Bridge WebSocket 또는 command polling 고도화
3. 코드 수정·Patch 적용 (Task Runtime·Approval 연동)
4. Installer에 `package-iris-ide.ps1` 산출물 포함
