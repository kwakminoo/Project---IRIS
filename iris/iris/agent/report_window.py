"""검색/조사 보고서 창."""

from __future__ import annotations

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


class ReportWindow(QDialog):
    """제목·링크·요약·표·차트 탭."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Iris 보고서")
        self.resize(960, 720)

        tabs = QTabWidget()
        self._summary = QTextBrowser()
        tabs.addTab(self._summary, "요약")

        self._table = QTableWidget(0, 3)
        self._table.setHorizontalHeaderLabels(["제목", "URL", "스니펫"])
        tabs.addTab(self._table, "링크")

        chart = QWidget()
        lay = QVBoxLayout(chart)
        self._figure = Figure(figsize=(5, 3), tight_layout=True)
        self._canvas = FigureCanvasQTAgg(self._figure)
        lay.addWidget(QLabel("간단 차트 (항목 길이)"))
        lay.addWidget(self._canvas)
        tabs.addTab(chart, "차트")

        root = QVBoxLayout(self)
        root.addWidget(tabs)

    def set_hits(self, query: str, hits: List[SearchHit]) -> None:
        lines = [f"<h2>검색: {query}</h2>", "<ul>"]
        for h in hits[:8]:
            safe_title = h.title.replace("<", "&lt;")
            lines.append(f"<li><b>{safe_title}</b><br/><a href=\"{h.url}\">{h.url}</a></li>")
        lines.append("</ul>")
        self._summary.setHtml("\n".join(lines))

        self._table.setRowCount(0)
        for h in hits:
            r = self._table.rowCount()
            self._table.insertRow(r)
            self._table.setItem(r, 0, QTableWidgetItem(h.title))
            self._table.setItem(r, 1, QTableWidgetItem(h.url))
            self._table.setItem(r, 2, QTableWidgetItem(h.snippet))

        self._figure.clear()
        ax = self._figure.add_subplot(111)
        titles = [h.title[:20] for h in hits[:8]]
        vals = [len(h.title) for h in hits[:8]]
        ax.bar(range(len(vals)), vals, color="#7c3aed")
        ax.set_xticks(range(len(titles)))
        ax.set_xticklabels(titles, rotation=35, ha="right", fontsize=7)
        ax.set_ylabel("제목 길이")
        self._canvas.draw()
