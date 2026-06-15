# Iris Cyberspace Theme — UI 구조 분석

> 작성일: 2026-06-15  
> 목적: 레이아웃·기능 유지, 시각 테마만 사이버스페이스 HUD로 개편하기 위한 사전 분석

---

## 1. 현재 UI 전체 레이아웃 구조

```
MainWindow (FramelessShell)
├── DragTab                    — 상단 타이틀바 (드래그·창 제어·설정)
├── StatusHeader (QFrame)      — 모델명·상태·TTS·백엔드 정보
└── QSplitter [Horizontal]
    ├── LeftSidebarPanel (220px 고정)
    │   └── QSplitter [Vertical]
    │       ├── WindowListPanel      — 실행 중인 창
    │       └── SidebarUtilityPanel
    │           ├── SystemMetricsPanel — CPU/GPU/MEM
    │           └── WorkspaceActionPanel — IDE 버튼
    └── QStackedWidget (Workspace)
        ├── AssistantWorkspacePage
        │   └── QSplitter [Horizontal]
        │       ├── center_column (Visualizer + LiveActivity + Chat)
        │       └── right_column (UnifiedMonitor + Notification)
        └── IdeWorkspacePage (Theia + CodingPanel)
```

- 루트: `main_window.py` — `FramelessShell` + `central` QWidget + `QVBoxLayout`
- 마진: 14/12/14/12, spacing 10
- Splitter 비율: 좌측 230 : workspace 1150 (assistant 내부 760 : 390)

---

## 2. 좌 / 중앙 / 우 패널 구성

| 영역 | 위젯 | 역할 |
|------|------|------|
| **좌** | `WindowListPanel` | 실행 중 창 목록, 포커스/닫기 |
| **좌** | `SystemMetricsPanel` | CPU/GPU/MEM 프로그레스바 |
| **좌** | `WorkspaceActionPanel` | IDE 전환 버튼 |
| **중앙** | `Visualizer` → `ParticleVisualizer` | Iris 구체(orb), AppState 반응 |
| **중앙** | `LiveActivityPanel` | 내부 로그 스트림 |
| **중앙** | `ChatPanel` | 사용자·Iris 대화 |
| **우** | `UnifiedMonitorPanel` | 창 썸네일 + 모니터링 상태 |
| **우** | `NotificationPanel` | 알림·스누즈·무시 |

---

## 3. 상단바 / 상태바 / 하단 로그·터미널 구조

| 구역 | 구현 | 내용 |
|------|------|------|
| **상단 타이틀** | `DragTab` | IRIS 로고, 설정/최소/최대/닫기 |
| **상태 헤더** | `QFrame#StatusHeader` | 모델, `상태: IDLE`, TTS, external backend |
| **하단 터미널** | 별도 dock 없음 | `LiveActivityPanel`이 중앙열 하단에 내장 |
| **상태바** | Qt statusBar 미사용 | StatusHeader + LiveActivity가 역할 분담 |

---

## 4. 스타일 적용 핵심 위젯 목록

1. `main_window._apply_dark_theme` — 전역 QSS·팔레트
2. `theme_tokens.TOKENS` — 색상 토큰 (현재 기본 다크)
3. `particle_visualizer.ParticleVisualizer` — 중앙 orb
4. `window_list_panel.WindowListPanel` — 좌측 창 목록
5. `system_metrics_panel.SystemMetricsPanel` — 메트릭 바
6. `workspace_action_panel.WorkspaceActionPanel` — IDE 버튼
7. `unified_monitor_panel.UnifiedMonitorPanel` — 우측 모니터
8. `notification_panel.NotificationPanel` — 알림
9. `live_activity_panel.LiveActivityPanel` — 로그 HUD
10. `chat_panel.ChatPanel` — 채팅 입력/표시
11. `drag_tab.DragTab` — 타이틀바
12. `assistant_workspace_page` — 중앙/우 컬럼 컨테이너
13. `left_sidebar_panel` — 좌측 사이드바
14. IDE: `iris_orb_widget`, `iris_coding_panel`, `coding_chat_view`, `embedded_theia_view`

---

## 5. 레이아웃 유지·스타일만 변경 영역

| 유지 | 스타일만 변경 |
|------|---------------|
| Splitter 비율·고정폭 220px | 배경색·테두리·글로우 |
| 위젯 add 순서·stretch | QSS objectName·투명도 |
| 시그널/슬롯 연결 | 폰트 weight·크기·색 |
| MetricsWorker → metrics.apply_snapshot | 바 두께·HUD 라벨 |
| WindowListPanel 타이머·hwnd 로직 | 행 hover·리스트 스타일 |
| ParticleVisualizer set_state API | 색·입자·펄스 렌더링 |
| Workspace 전환 (assistant ↔ ide) | 버튼 네온 라인 |

---

## 6. 구체(Orb) 표현 위치

- **주 orb**: `AssistantWorkspacePage` 중앙열 최상단 `Visualizer` (`stretch=1`, minHeight 300)
- **IDE orb**: `IrisCodingPanel` → `IrisOrbWidget` (컴팩트, 100–140px)
- **렌더링 엔진**: `particle_visualizer.ParticleVisualizer` (공유)
- **상태 연동**: `MainWindow._on_state_changed` → `_viz.set_state(s)` + IDE coding panel
- **에셋**: `iris/assets/visuals/iris_core.png` (있으면 내부 코어로 재사용)

Orb는 중앙열 상단이 시각적 중심. 배경 성운은 전체 workspace 뒤, orb 글로우는 particle 레이어에서 처리.

---

## 7. 수정 예정 파일 목록

| 파일 | 변경 내용 |
|------|-----------|
| `iris/ui/theme_tokens.py` | 사이버스페이스 색상·글로우 토큰 확장 |
| `iris/ui/cyberspace_theme.py` | **신규** — QSS 빌더·테마 적용 |
| `iris/ui/cyberspace_background.py` | **신규** — 성운·지평선 그리드 배경 |
| `iris/ui/particle_visualizer.py` | 보라/마젠타 입자 네트워크 orb |
| `iris/ui/main_window.py` | 테마 적용·배경 컨테이너 |
| `iris/ui/window_list_panel.py` | HUD 리스트 스타일 |
| `iris/ui/system_metrics_panel.py` | 얇은 HUD 메트릭 바 |
| `iris/ui/workspace_action_panel.py` | 네온 모드 전환 버튼 |
| `iris/ui/unified_monitor_panel.py` | 오버레이 패널 스타일 |
| `iris/ui/notification_panel.py` | HUD 알림 스타일 |
| `iris/ui/assistant_workspace_page.py` | 투명 컨테이너 |
| `iris/ui/left_sidebar_panel.py` | 투명 사이드바 |
| `iris/ui/live_activity_panel.py` | HUD 라벨 색상 |
| `iris/tests/test_cyberspace_theme.py` | **신규** — orb·토큰·테마 테스트 |

---

## 8. 기능 회귀 위험 요소

| 위험 | 대응 |
|------|------|
| orb 애니메이션 CPU 과다 | 입자 수 제한(~48), 40ms tick, 거리 임계 연결 |
| 투명 배경으로 텍스트 대비 저하 | text_primary `#e8eaf6`, 라벨 미세 text-shadow(QSS color) |
| QSS 전역 변경이 입력 위젯 포커스 깨짐 | ChatPanel objectName 스코프 유지 |
| Splitter handle 투명화로 드래그 어려움 | handle 1px + hover glow 유지 |
| WindowListPanel ×/포커스 클릭 영역 축소 | hit area·padding 유지 |
| IDE Theia iframe과 배경 충돌 | IDE 페이지만 불투명 배경 유지 |
| 기존 `test_main_window_workspace` | 레이아웃 API 불변 확인 |
| `PROCESSING` vs `THINKING` 명칭 | AppState 유지, 시각 프로필만 THINKING 톤 적용 |

---

## 수동 확인 체크리스트 (구현 후)

1. [ ] 전체 분위기가 레퍼런스처럼 사이버 공간 느낌인지
2. [ ] 중앙 orb가 시각 중심인지
3. [ ] 박스형 패널 느낌이 충분히 줄었는지
4. [ ] 정보가 HUD/오버레이처럼 보이는지
5. [ ] 가독성이 유지되는지
6. [ ] 기존 기능(창 포커스, IDE 전환, 채팅, 메트릭)이 그대로 동작하는지
