"""Iris UI 테마 토큰 — PyQt·Theia 공통 사이버스페이스 색상."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ThemeTokens:
    # 우주 배경
    void_black: str = "#020408"
    space_deep: str = "#050810"
    space_navy: str = "#0a0618"
    nebula_purple: str = "#1a0a2e"
    nebula_magenta: str = "#2d0a3a"

    # 레이어
    background_primary: str = "#030508"
    background_secondary: str = "#080612"
    panel_background: str = "rgba(12, 8, 24, 0.35)"
    panel_overlay: str = "rgba(8, 6, 18, 0.45)"
    border_color: str = "rgba(139, 92, 246, 0.18)"
    border_subtle: str = "rgba(148, 163, 184, 0.12)"
    divider: str = "rgba(167, 139, 250, 0.14)"

    # 텍스트
    text_primary: str = "#e8eaf6"
    text_secondary: str = "#94a3b8"
    text_muted: str = "#64748b"
    text_hud_label: str = "rgba(196, 181, 253, 0.72)"
    text_accent: str = "#c4b5fd"

    # 네온 포인트
    neon_purple: str = "#a855f7"
    neon_magenta: str = "#e879f9"
    neon_blue: str = "#38bdf8"
    neon_cyan: str = "#22d3ee"
    glow_purple: str = "rgba(168, 85, 247, 0.45)"
    glow_magenta: str = "rgba(232, 121, 249, 0.35)"

    # 액센트·상태
    accent_primary: str = "rgba(88, 28, 135, 0.55)"
    accent_hover: str = "rgba(109, 40, 217, 0.65)"
    accent_border: str = "rgba(167, 139, 250, 0.55)"
    success: str = "#34d399"
    warning: str = "#fbbf24"
    error: str = "#f87171"

    # HUD 메트릭
    metric_track: str = "rgba(15, 10, 30, 0.6)"
    metric_fill_cpu: str = "#a855f7"
    metric_fill_gpu: str = "#e879f9"
    metric_fill_mem: str = "#38bdf8"

    # 폰트
    font_family: str = '"Segoe UI Variable", "Segoe UI", "Noto Sans KR", "Malgun Gothic"'
    font_mono: str = '"Consolas", "Cascadia Mono", "Courier New"'
    font_size_base: str = "13px"
    font_size_hud: str = "11px"
    font_size_micro: str = "10px"


TOKENS = ThemeTokens()
