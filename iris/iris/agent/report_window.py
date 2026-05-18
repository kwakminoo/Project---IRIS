"""검색/리서치 보고서 창."""

from __future__ import annotations

import html
from typing import List

try:
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
except Exception:  # pragma: no cover - 구버전 호환
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg  # type: ignore
from matplotlib.figure import Figure
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from iris.agent.web_agent import SearchHit


def _esc(text: str) -> str:
    return html.escape(text or "", quote=True)


class ReportWindow(QDialog):
    """출처 기반 요약·링크·표·차트 탭."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Iris 리서치 보고서")
        self.resize(960, 720)

        tabs = QTabWidget()
        self._summary = QTextBrowser()
        self._summary.setOpenExternalLinks(True)
        tabs.addTab(self._summary, "출처 요약")

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["제목", "URL", "날짜", "요약 스니펫"])
        self._table.horizontalHeader().setStretchLastSection(True)
        tabs.addTab(self._table, "출처 목록")

        chart = QWidget()
        lay = QVBoxLayout(chart)
        self._figure = Figure(figsize=(5, 3), tight_layout=True)
        self._canvas = FigureCanvasQTAgg(self._figure)
        lay.addWidget(QLabel("스니펫 길이 (출처별)"))
        lay.addWidget(self._canvas)
        tabs.addTab(chart, "차트")

        root = QVBoxLayout(self)
        root.addWidget(tabs)

    def set_hits(self, query: str, hits: List[SearchHit]) -> None:
        """출처 기반 HTML 요약 + 테이블."""
        page_hits = [h for h in hits if h.source_label == "page" or h.snippet]
        display = page_hits if page_hits else hits

        lines = [
            f"<h2>리서치: {_esc(query)}</h2>",
            "<p>아래는 Playwright로 수집한 출처입니다. "
            "민감 페이지는 읽기만 하며 본문 추출이 제한될 수 있습니다.</p>",
        ]
        for i, h in enumerate(display[:10], 1):
            title = _esc(h.title)
            url = _esc(h.url)
            snip = _esc((h.snippet or "")[:600])
            date = _esc(h.date_candidate) if h.date_candidate else "—"
            badge = (
                ' <span style="color:#f87171;">[민감·제한]</span>'
                if h.read_only_restricted
                else ""
            )
            lines.append(
                f'<section style="margin-bottom:1.2em;">'
                f"<h3>{i}. {title}{badge}</h3>"
                f'<p><a href="{url}">{url}</a></p>'
                f"<p><small>날짜 후보: {date}</small></p>"
                f'<p style="color:#cbd5e1;">{snip}</p>'
                f"</section>"
            )
        if len(display) > 10:
            lines.append(f"<p><i>… 외 {len(display) - 10}건</i></p>")
        self._summary.setHtml("\n".join(lines))

        self._table.setRowCount(0)
        for h in hits:
            r = self._table.rowCount()
            self._table.insertRow(r)
            self._table.setItem(r, 0, QTableWidgetItem(h.title))
            self._table.setItem(r, 1, QTableWidgetItem(h.url))
            self._table.setItem(r, 2, QTableWidgetItem(h.date_candidate or "—"))
            snip_cell = h.snippet or ""
            if h.read_only_restricted and "[민감" not in snip_cell:
                snip_cell = "[민감 페이지] " + snip_cell
            self._table.setItem(r, 3, QTableWidgetItem(snip_cell[:500]))

        self._figure.clear()
        ax = self._figure.add_subplot(111)
        chart_hits = [h for h in display[:8] if h.snippet]
        if not chart_hits:
            chart_hits = display[:8]
        titles = [h.title[:18] + "…" if len(h.title) > 18 else h.title for h in chart_hits]
        vals = [len(h.snippet or h.title) for h in chart_hits]
        if vals:
            ax.bar(range(len(vals)), vals, color="#7c3aed")
            ax.set_xticks(range(len(titles)))
            ax.set_xticklabels(titles, rotation=35, ha="right", fontsize=7)
            ax.set_ylabel("스니펫 길이")
        self._canvas.draw()
