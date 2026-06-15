# Embedded IDE 아키텍처

## 개요

Iris MainWindow는 **Persistent LeftSidebar** + **QStackedWidget**(Assistant / IDE) 구조로 workspace를 전환합니다.

```
MainWindow
├── TopArea (DragTab + StatusHeader)
└── QSplitter
    ├── LeftSidebarPanel (항상 유지)
    │   ├── WindowListPanel
    │   └── SidebarUtilityPanel
    │       ├── SystemMetricsPanel
    │       └── WorkspaceActionPanel [IDE / 돌아가기]
    └── QStackedWidget
        ├── AssistantWorkspacePage (기존 Iris UI)
        └── IdeWorkspacePage
            ├── EmbeddedTheiaView (QWebEngineView)
            └── IrisCodingPanel
```

## Theia 내장

- **Frontend:** `QWebEngineView` → `http://127.0.0.1:{port}`
- **Backend:** `IdeBackendManager`가 `node lib/backend/main.js` child process 실행
- **Bridge:** `IdeBridgeClient` HTTP server ↔ `iris-bridge` Theia extension

## 생명주기

| 이벤트 | Backend |
|--------|---------|
| IDE 버튼 | 시작 또는 재사용 |
| Assistant 복귀 | 유지 (세션 보존) |
| Iris 종료 | `shutdown()` |

## 보안

- `127.0.0.1` bind only
- `shell=False` subprocess
- Secret/binary 파일 context 차단
