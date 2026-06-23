"""IDE 통합 레이아웃 geometry 상수 — Theia chrome 여백."""

from __future__ import annotations

# Theia Activity Bar 폭 (CSS와 동일하게 유지)
THEIA_ACTIVITY_BAR_WIDTH = 48

# Activity Bar 아이콘 슬롯 크기 (Manage·설정 버튼과 동일)
THEIA_ACTIVITY_TAB_SIZE = 48

# Theia 상단 메뉴바 높이
THEIA_MENU_BAR_HEIGHT = 28

# Theia 하단 상태바 높이
THEIA_STATUS_BAR_HEIGHT = 22

# IRIS Assistant Dock 폭
ASSISTANT_DOCK_DEFAULT_WIDTH = 320
ASSISTANT_DOCK_MIN_WIDTH = 280
ASSISTANT_DOCK_MAX_WIDTH = 420

# Editor 최소 폭 (dock 표시 시)
EDITOR_MIN_WIDTH = 520

# 우측 Assistant Dock — 구체 고정 높이 (채팅이 남은 공간 흡수)
ASSISTANT_DOCK_ORB_HEIGHT = 280
# 구체 상단 glow 여유
ASSISTANT_DOCK_ORB_TOP_PAD = 16
DOCK_ORB_SCALE = 1.65

# 웰컴 타이틀 구체 — 컴팩트 슬롯 (Dock 280px와 분리)
WELCOME_ORB_SLOT_SIZE = 250
