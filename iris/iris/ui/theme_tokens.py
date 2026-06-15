"""Iris UI 테마 토큰 — PyQt·Theia 공통 색상."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ThemeTokens:
    background_primary: str = "#0b1220"
    background_secondary: str = "#0f172a"
    panel_background: str = "#111827"
    border_color: str = "#334155"
    text_primary: str = "#e2e8f0"
    text_secondary: str = "#94a3b8"
    accent_primary: str = "#312e81"
    accent_hover: str = "#4338ca"
    success: str = "#22c55e"
    warning: str = "#f59e0b"
    error: str = "#ef4444"


TOKENS = ThemeTokens()
