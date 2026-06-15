# Embedded IDE Workspace — 현재 코드 분석

> 작성 기준: MainWindow 리팩터링 전 상태 분석

## 1. 현재 MainWindow의 Splitter와 Layout 구조

**파일:** `iris/iris/ui/main_window.py` — 클래스 `MainWindow(QMainWindow)`

```
QMainWindow (frameless, min 1100×720)
└── FramelessShell
    └── QWidget (central)
        └── QVBoxLayout
            ├── DragTab
            ├── QFrame#StatusHeader
            └── QSplitter (Horizontal, handle 8px)
                ├── [0] WindowListPanel (220px 고정)
                ├── [1] QWidget#WorkspacePanel — Visualizer + LiveActivity + ChatPanel
                └── [2] QWidget#WorkspacePanel — UnifiedMonitorPanel + NotificationPanel
```

- 초기 Splitter sizes: `[230, 760, 390]`
- index 0만 `setCollapsible(False)`
- `WorkspacePanel`은 별도 클래스가 아닌 `objectName` CSS 훅

## 2. 기존 Assistant 화면을 구성하는 Widget 목록

| 위젯 | 파일 | 역할 |
|------|------|------|
| DragTab | `drag_tab.py` | 타이틀바·설정·창 제어 |
| StatusHeader | `main_window.py` | 모델·상태·TTS·백엔드 |
| WindowListPanel | `window_list_panel.py` | 실행 중 창 목록 |
| Visualizer | `visualizer.py` → `particle_visualizer.py` | 상태 오브 |
| LiveActivityPanel | `live_activity_panel.py` | 파이프라인 로그 |
| ChatPanel | `chat_panel.py` | 대화·스트리밍·입력 |
| UnifiedMonitorPanel | `unified_monitor_panel.py` | 창 썸네일·모니터 |
| NotificationPanel | `notification_panel.py` | 알림 |

## 3. WindowListPanel의 크기·갱신·포커스 동작

- **크기:** `_SIDEBAR_WIDTH = 220`, `Fixed` × `Expanding`
- **갱신:** `QTimer` 2500ms, `list_visible_windows()`, 시그니처 변경 시만 UI 재구성
- **최대:** 30개, 제목 24자 truncate
- **포커스:** `focus_window_by_hwnd` → 실패 시 `focus_and_place`
- **닫기:** `close_window_by_hwnd` (WM_CLOSE), 300ms 후 강제 갱신

## 4. 시스템 Metrics 구현 여부

- `iris/iris/system/` **없음**
- `iris/iris/automation/system_info.py` — 정적 스냅샷 (CPU 이름, RAM 총량, GPU 이름)
- **실시간 CPU/GPU/MEMORY 사용률 UI 없음** → 신규 `MetricsWorker` + `SystemMetricsPanel` 필요

## 5. 현재 Chat·음성 입력 Pipeline

```
ChatPanel.send_clicked → MainWindow._on_user_text(from_voice=False)
ContinuousListenController → VoiceCommandGate → _on_voice_utterance → _on_user_text(from_voice=True)
_on_user_text → AgentWorker(TurnCoordinator) → _on_agent_worker_reply → _iris_reply
```

- 단일 `IrisAssistant` 인스턴스 (`MainWindow.__init__`)
- 상태: `StateMachine` → `_on_state_changed` → `Visualizer.set_state`

## 6. 기존 Iris 구체 또는 애니메이션 Asset 존재 여부

- `iris/assets/visuals/iris_core.png` — 코어 비트맵
- `ParticleVisualizer` — QPainter 기반 글로우·링·펄스
- `Visualizer` — MainWindow API 래퍼 (`set_state`, `set_mic_level`)
- IDE Coding Panel에서 **재사용** 예정 (`IrisOrbWidget`)

## 7. Theia를 내장하는 데 필요한 Python·TypeScript 경계

| 계층 | 기술 |
|------|------|
| Iris Shell | PyQt6 `QWebEngineView` (`EmbeddedTheiaView`) |
| Theia Frontend | Browser app (`iris-ide/applications/browser`) |
| Theia Backend | Node `lib/backend/main.js`, `127.0.0.1` only |
| Process 관리 | `IdeBackendManager` (Python) |
| Context Bridge | HTTP localhost (`IdeBridgeClient` + `iris-bridge` extension) |
| Workspace 경로 | `Settings.ide_workspace_path` → 미설정 시 저장소 루트 |

## 8. 변경할 파일 목록

**수정:** `main_window.py`, `settings.py`, `requirements-windows.txt`, `.gitignore`

**신규 Python:**
- `ui/workspaces/assistant_workspace_page.py`, `ide_workspace_page.py`
- `ui/left_sidebar_panel.py`, `sidebar_utility_panel.py`, `system_metrics_panel.py`, `workspace_action_panel.py`
- `ui/ide/embedded_theia_view.py`, `iris_coding_panel.py`, `iris_orb_widget.py`, `coding_chat_view.py`
- `ui/theme_tokens.py`
- `system/metrics_worker.py`, `metrics_snapshot.py`, `gpu_provider.py`
- `infrastructure/ide/ide_backend_manager.py`, `ide_workspace_resolver.py`, `ide_bridge_client.py`

**신규 TypeScript:** `iris-ide/` 전체, `protocol/*.json`

**신규 스크립트:** `scripts/setup-iris-ide.ps1` 등 4개

## 9. 기존 기능 회귀 위험

| 위험 | 완화 |
|------|------|
| MonitorManager / Voice 연결 끊김 | Widget 이동만, 시그널은 MainWindow 유지 |
| Splitter 크기 초기화 | workspace별 `saveState`/`restoreState` |
| Chat 기록 소실 | AssistantWorkspacePage 인스턴스 보존 |
| closeEvent Backend 미종료 | `IdeBackendManager.shutdown()` |
| PyQt6-WebEngine 미설치 | import guard + IDE 버튼 안내 |
