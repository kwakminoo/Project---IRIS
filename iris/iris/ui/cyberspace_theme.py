"""사이버스페이스 HUD 테마 — QSS 빌더 및 적용."""

from __future__ import annotations

from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QWidget

from iris.ui.theme_tokens import TOKENS


def build_cyberspace_qss() -> str:
    """전역 사이버스페이스 QSS."""
    t = TOKENS
    return f"""
        QWidget {{
            background-color: transparent;
            color: {t.text_primary};
            font-family: {t.font_family};
            font-size: {t.font_size_base};
        }}
        CyberspaceBackground {{
            background-color: {t.void_black};
        }}
        QTextEdit, QListWidget, QLineEdit, QPlainTextEdit {{
            background-color: {t.panel_overlay};
            border: 1px solid {t.border_subtle};
            border-radius: 4px;
            color: {t.text_primary};
            selection-background-color: rgba(109, 40, 217, 0.45);
        }}
        QWidget#LiveActivityPanel,
        QPlainTextEdit#LiveActivityLog {{
            background: transparent;
            background-color: transparent;
            border: none;
        }}
        QPushButton {{
            background-color: {t.accent_primary};
            color: {t.text_primary};
            border: 1px solid {t.border_color};
            border-radius: 4px;
            padding: 6px 12px;
        }}
        QPushButton:hover {{
            background-color: {t.accent_hover};
            border-color: {t.accent_border};
        }}
        QFrame#StatusHeader {{
            background-color: transparent;
            border: none;
            border-bottom: 1px solid {t.divider};
            border-radius: 0;
        }}
        QFrame#StatusHeader QLabel {{
            background-color: transparent;
        }}
        QFrame#WorkspacePanel,
        QWidget#AssistantWorkspacePage,
        QWidget#LeftSidebarPanel,
        QWidget#WindowListPanel,
        QWidget#SidebarUtilityPanel,
        QWidget#SystemMetricsPanel,
        QWidget#WorkspaceActionPanel {{
            background: transparent;
            border: none;
        }}
        QLabel#StatusPill {{
            background-color: transparent;
            border: none;
            color: {t.neon_cyan};
            font-size: {t.font_size_hud};
            letter-spacing: 0.5px;
        }}
        QLabel#BackendStatus {{
            color: {t.text_muted};
            font-size: {t.font_size_micro};
        }}
        QLabel#TtsStatus {{
            color: {t.text_secondary};
            font-size: {t.font_size_hud};
        }}
        QLabel#ModelStatus {{
            color: {t.text_accent};
            font-weight: 500;
            font-size: {t.font_size_hud};
            letter-spacing: 0.8px;
        }}
        QSplitter::handle {{
            background-color: {t.divider};
            margin: 6px 1px;
            border-radius: 1px;
            max-width: 2px;
        }}
        QSplitter::handle:hover {{
            background-color: {t.neon_purple};
        }}
        QScrollBar:vertical {{
            background: transparent;
            width: 10px;
            margin: 2px;
        }}
        QScrollBar:horizontal {{
            background: transparent;
            height: 10px;
            margin: 2px;
        }}
        QScrollBar::handle:vertical,
        QScrollBar::handle:horizontal {{
            background: rgba(100, 116, 139, 0.35);
            border: 1px solid {t.border_subtle};
            border-radius: 4px;
            min-height: 28px;
            min-width: 28px;
        }}
        QScrollBar::handle:vertical:hover,
        QScrollBar::handle:horizontal:hover {{
            background: {t.neon_purple};
            border-color: {t.accent_border};
        }}
        QScrollBar::add-line,
        QScrollBar::sub-line,
        QScrollBar::add-page,
        QScrollBar::sub-page {{
            background: transparent;
            border: none;
            width: 0;
            height: 0;
        }}
        QPushButton#WinCtrl {{
            background-color: transparent;
            border: 1px solid {t.border_subtle};
            padding: 0;
            min-width: 34px;
            max-width: 34px;
            min-height: 28px;
            max-height: 28px;
            font-size: 14px;
            font-weight: 400;
            border-radius: 3px;
        }}
        QPushButton#WinCtrl:hover {{
            background-color: {t.accent_primary};
            border-color: {t.accent_border};
        }}
        QPushButton#WinCtrl:pressed {{
            background-color: rgba(76, 29, 149, 0.5);
        }}
        QLabel#DragTitle {{
            font-weight: 300;
            font-size: 15px;
            letter-spacing: 4px;
            color: {t.text_accent};
        }}
        QLabel#PanelTitle,
        QLabel#SidebarTitle,
        QLabel#HudSectionTitle {{
            font-weight: 500;
            font-size: {t.font_size_hud};
            letter-spacing: 1.2px;
            color: {t.text_hud_label};
            background: transparent;
        }}
        QPushButton#HudModeButton {{
            background: transparent;
            border: 1px solid {t.border_color};
            border-radius: 3px;
            padding: 8px 10px;
            font-weight: 500;
            font-size: {t.font_size_hud};
            letter-spacing: 0.6px;
            color: {t.text_accent};
        }}
        QPushButton#HudModeButton:hover {{
            background: {t.accent_primary};
            border-color: {t.neon_magenta};
            color: {t.text_primary};
        }}
        QPushButton#HudModeButton[active="true"] {{
            background: rgba(109, 40, 217, 0.35);
            border-color: {t.neon_magenta};
            color: {t.neon_cyan};
        }}
        QProgressBar#HudMetricBar {{
            background: {t.metric_track};
            border: none;
            border-radius: 2px;
            height: 6px;
            text-align: right;
            color: {t.text_secondary};
            font-size: {t.font_size_micro};
        }}
        QProgressBar#HudMetricBar::chunk {{
            border-radius: 2px;
        }}
        QWidget#UnifiedMonitorPanel,
        QWidget#NotificationPanel {{
            background: {t.panel_overlay};
            border: 1px solid {t.border_subtle};
            border-radius: 4px;
        }}
        QFrame#HudWindowRow {{
            background: transparent;
            border: none;
            border-bottom: 1px solid {t.border_subtle};
            border-radius: 0;
        }}
        QFrame#HudWindowRow:hover {{
            background: rgba(109, 40, 217, 0.12);
            border-bottom-color: {t.accent_border};
        }}
    """


def apply_cyberspace_theme(widget: QWidget) -> None:
    """팔레트 + QSS 적용."""
    t = TOKENS
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(t.void_black))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(t.text_primary))
    pal.setColor(QPalette.ColorRole.Base, QColor(8, 6, 18))
    pal.setColor(QPalette.ColorRole.Text, QColor(t.text_primary))
    pal.setColor(QPalette.ColorRole.Button, QColor(12, 8, 24))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(t.text_primary))
    widget.setPalette(pal)
    widget.setStyleSheet(build_cyberspace_qss())
