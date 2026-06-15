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
        QMainWindow {{
            background-color: {t.void_black};
            border: none;
        }}
        QWidget#FramelessShell {{
            background: transparent;
            border: none;
        }}
        CyberspaceBackground {{
            background-color: {t.void_black};
        }}
        QTextEdit, QListWidget, QLineEdit, QPlainTextEdit {{
            background-color: {t.panel_overlay};
            border: 1px solid {t.border_subtle};
            border-radius: 4px;
            color: {t.text_primary};
            selection-background-color: rgba(37, 99, 235, 0.45);
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
            background: transparent;
            margin: 0;
            border: none;
            width: 0px;
            height: 0px;
            max-width: 0px;
            max-height: 0px;
        }}
        QSplitter::handle:hover {{
            background: transparent;
        }}
        QScrollBar:vertical,
        QScrollBar:horizontal {{
            width: 0px;
            height: 0px;
            background: transparent;
            margin: 0;
        }}
        QScrollBar::handle:vertical,
        QScrollBar::handle:horizontal {{
            width: 0px;
            height: 0px;
            background: transparent;
            border: none;
            min-height: 0;
            min-width: 0;
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
            background-color: rgba(30, 58, 138, 0.5);
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
            border-color: {t.neon_cyan};
            color: {t.text_primary};
        }}
        QPushButton#HudModeButton[active="true"] {{
            background: rgba(37, 99, 235, 0.35);
            border-color: {t.neon_cyan};
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
        QWidget#UiOverlay {{
            background: transparent;
            border: none;
        }}
        QWidget#OrbLayoutSpacer {{
            background: transparent;
            border: none;
        }}
        QPushButton#AlertActionButton {{
            background: transparent;
            border: none;
            color: {t.text_secondary};
            padding: 4px 8px;
            font-size: {t.font_size_micro};
        }}
        QPushButton#AlertActionButton:hover {{
            color: {t.text_accent};
            background: transparent;
        }}
        QWidget#UnifiedMonitorPanel,
        QWidget#NotificationPanel {{
            background: transparent;
            border: none;
        }}
        QWidget#SectionHeader {{
            background: transparent;
            border: none;
        }}
        QFrame#SectionUnderline {{
            background: {t.border_color};
            border: none;
            max-height: 1px;
        }}
        QTextEdit#ChatLog,
        QWidget#ChatPanel,
        QWidget#ChatInputArea,
        QWidget#ChatInputBar,
        QWidget#ChatInputShell {{
            background: transparent;
            border: none;
        }}
        QLineEdit#ChatInput {{
            background: transparent;
            border: none;
        }}
        QWidget#NotificationPanel QListWidget {{
            background: transparent;
            border: none;
        }}
        QFrame#HudWindowRow {{
            background: transparent;
            border: none;
            border-radius: 0;
        }}
        QFrame#HudWindowRow:hover {{
            background: rgba(37, 99, 235, 0.12);
        }}
    """


def apply_cyberspace_theme(widget: QWidget) -> None:
    """팔레트 + QSS 적용."""
    t = TOKENS
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(t.void_black))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(t.text_primary))
    pal.setColor(QPalette.ColorRole.Base, QColor(6, 14, 28))
    pal.setColor(QPalette.ColorRole.Text, QColor(t.text_primary))
    pal.setColor(QPalette.ColorRole.Button, QColor(8, 16, 32))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(t.text_primary))
    widget.setPalette(pal)
    widget.setStyleSheet(build_cyberspace_qss())
