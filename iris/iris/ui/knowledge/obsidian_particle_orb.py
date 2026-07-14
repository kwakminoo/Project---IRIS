"""Obsidian 지식 구체 — 드래그 회전·휠 줌·노트 클릭."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QRadialGradient
from PyQt6.QtWidgets import QSizePolicy, QWidget

# Obsidian 보석 톤 — Iris 시안과 구분
_ACCENT = (167, 139, 250)
_ACCENT_CORE = (109, 40, 217)
# 내핵 — Iris 기본 구체와 같은 청색 파티클
_INNER_ACCENT = (59, 130, 246)
_INNER_ACCENT_HOT = (34, 211, 238)
_CONNECT_DIST = 0.42
_INNER_CONNECT_DIST = 0.52
_ORB_RATIO = 0.36
_INNER_RADIUS_SCALE = 0.40
_INNER_PARTICLE_COUNT = 40
_EMPTY_PLACEHOLDER = 12
_NOTE_SUFFIXES = {".md", ".mdc"}

# 드래그 회전·휠 줌
_DRAG_RAD_PER_PX = 0.008
_CLICK_SLOP_PX = 6.0
_ZOOM_MIN = 0.55
_ZOOM_MAX = 2.6
_ZOOM_STEP = 1.1
_ROT_X_LIMIT = math.radians(78)


@dataclass(frozen=True)
class ObsidianOrbNode:
    """구체 한 점 = 지식 소스 하나."""

    source_id: int
    title: str
    path: str = ""


def display_title_for_source(*, title: str, path: str) -> str:
    """UI 라벨 — title 우선, 없으면 파일명."""
    t = (title or "").strip()
    if t:
        return t
    name = Path(path).name if path else ""
    return name or "(untitled)"


def is_obsidian_note_path(path: str) -> bool:
    return Path(path).suffix.lower() in _NOTE_SUFFIXES


def _fibonacci_sphere(n: int, seed: int = 7) -> list[tuple[float, float, float]]:
    if n <= 0:
        return []
    rng = random.Random(seed)
    pts: list[tuple[float, float, float]] = []
    golden = math.pi * (3.0 - math.sqrt(5.0))
    for i in range(n):
        y = 1.0 - (i / float(max(n - 1, 1))) * 2.0
        r = math.sqrt(max(0.0, 1.0 - y * y))
        theta = golden * i
        x = math.cos(theta) * r
        z = math.sin(theta) * r
        j = 0.03 * rng.random()
        pts.append((x + j, y + j, z + j))
    return pts


def _flat_disk(n: int, seed: int = 7) -> list[tuple[float, float, float]]:
    """단위 원판 골든앵글 배치 — 2D 모드용."""
    if n <= 0:
        return []
    if n == 1:
        return [(0.0, 0.0, 0.0)]
    rng = random.Random(seed)
    golden = math.pi * (3.0 - math.sqrt(5.0))
    pts: list[tuple[float, float, float]] = []
    for i in range(n):
        r = math.sqrt((i + 0.5) / n) * 0.92
        theta = golden * i
        j = 0.02 * rng.random()
        pts.append((r * math.cos(theta) + j, r * math.sin(theta) + j, 0.0))
    return pts


def _short_label(text: str, *, max_chars: int) -> str:
    t = " ".join(text.split())
    if len(t) <= max_chars:
        return t
    return t[: max(1, max_chars - 1)] + "…"


class ObsidianParticleOrb(QWidget):
    """지식 노트 파티클 구 — 자동 회전 없음, 드래그·휠로만 조작."""

    note_selected = pyqtSignal(int)  # source_id

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ObsidianParticleOrb")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

        self._rot_y = 0.0
        self._rot_x = 0.18
        self._zoom = 1.0
        self._view_mode = "3d"
        self._nodes: list[ObsidianOrbNode] = []
        self._pts = _fibonacci_sphere(_EMPTY_PLACEHOLDER)
        self._inner_pts = _fibonacci_sphere(_INNER_PARTICLE_COUNT, seed=91)
        self._selected_id: int | None = None
        self._last_projected: list[tuple[float, float, float, float]] = []

        self._press_pos: QPointF | None = None
        self._last_pos: QPointF | None = None
        self._dragging = False
        self._press_hit: int | None = None

    def view_mode(self) -> str:
        return self._view_mode

    def set_view_mode(self, mode: str) -> None:
        """3d(구) / 2d(평면 디스크)."""
        name = "2d" if str(mode).strip().lower() == "2d" else "3d"
        if name == self._view_mode:
            return
        self._view_mode = name
        self._rebuild_geometry()
        if name == "2d":
            self._rot_x = 0.0
            self._rot_y = 0.0
        else:
            self._rot_x = 0.18
        self.update()

    def set_notes(self, notes: list[ObsidianOrbNode]) -> None:
        """실제 지식 소스로 구체 재구성 — 점 개수 = 노트 개수."""
        self._nodes = list(notes)
        if self._selected_id is not None and all(
            n.source_id != self._selected_id for n in self._nodes
        ):
            self._selected_id = None
        self._rebuild_geometry()
        self.update()

    def _rebuild_geometry(self) -> None:
        n = len(self._nodes)
        count = n if n > 0 else _EMPTY_PLACEHOLDER
        if self._view_mode == "2d":
            self._pts = _flat_disk(count, seed=7)
            self._inner_pts = _flat_disk(max(12, _INNER_PARTICLE_COUNT // 2), seed=91)
        else:
            self._pts = _fibonacci_sphere(count, seed=7)
            self._inner_pts = _fibonacci_sphere(_INNER_PARTICLE_COUNT, seed=91)

    def note_count(self) -> int:
        return len(self._nodes)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        pos = event.position()
        self._press_pos = QPointF(pos)
        self._last_pos = QPointF(pos)
        self._dragging = False
        self._press_hit = self._hit_test(pos.x(), pos.y()) if self._nodes else None
        self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._press_pos is None or not (
            event.buttons() & Qt.MouseButton.LeftButton
        ):
            super().mouseMoveEvent(event)
            return
        pos = event.position()
        if self._last_pos is None:
            self._last_pos = QPointF(pos)
        dx = pos.x() - self._last_pos.x()
        dy = pos.y() - self._last_pos.y()
        moved = math.hypot(
            pos.x() - self._press_pos.x(),
            pos.y() - self._press_pos.y(),
        )
        if moved >= _CLICK_SLOP_PX:
            self._dragging = True
        if self._dragging:
            # 3D: 구 회전 / 2D: 평면 내 회전만
            self._rot_y += dx * _DRAG_RAD_PER_PX
            if self._view_mode == "3d":
                self._rot_x = max(
                    -_ROT_X_LIMIT,
                    min(_ROT_X_LIMIT, self._rot_x + dy * _DRAG_RAD_PER_PX),
                )
            else:
                self._rot_y += dy * _DRAG_RAD_PER_PX * 0.35
            self.update()
        self._last_pos = QPointF(pos)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            super().mouseReleaseEvent(event)
            return
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        if not self._dragging and self._nodes:
            idx = self._press_hit
            if idx is None:
                idx = self._hit_test(event.position().x(), event.position().y())
            if idx is not None:
                node = self._nodes[idx]
                self._selected_id = node.source_id
                self.note_selected.emit(node.source_id)
                self.update()
        self._press_pos = None
        self._last_pos = None
        self._dragging = False
        self._press_hit = None

    def wheelEvent(self, event) -> None:  # noqa: N802
        delta = event.angleDelta().y()
        if delta == 0:
            return
        if delta > 0:
            self._zoom = min(_ZOOM_MAX, self._zoom * _ZOOM_STEP)
        else:
            self._zoom = max(_ZOOM_MIN, self._zoom / _ZOOM_STEP)
        self.update()
        event.accept()

    def _hit_test(self, mx: float, my: float) -> int | None:
        projected = self._last_projected or self._project_for_size()
        best_i: int | None = None
        best_depth = -1.0
        for i, (x, y, depth, size) in enumerate(projected):
            if i >= len(self._nodes):
                break
            hit_r = max(10.0, size * 4.0)
            in_dot = (mx - x) ** 2 + (my - y) ** 2 <= hit_r * hit_r
            in_label = (
                abs(mx - x) <= max(28.0, hit_r * 1.6)
                and y <= my <= y + hit_r + 16.0
            )
            if not (in_dot or in_label):
                continue
            if depth >= best_depth:
                best_depth = depth
                best_i = i
        return best_i

    def paintEvent(self, event) -> None:  # noqa: ARG002, N802
        w, h = self.width(), self.height()
        if w < 8 or h < 8:
            return
        cx, cy = w * 0.5, h * 0.48
        radius = min(w, h) * _ORB_RATIO * self._zoom

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        self._draw_glow(p, cx, cy, radius)
        projected = self._draw_outer_shell(p, cx, cy, radius)
        self._last_projected = projected
        self._draw_inner_haze(p, cx, cy, radius)
        self._draw_inner_shell(p, cx, cy, radius * _INNER_RADIUS_SCALE)
        if self._nodes:
            self._draw_labels(p, projected)
        else:
            self._draw_empty_hint(p, cx, cy, radius)
        p.end()

    def _draw_glow(self, p: QPainter, cx: float, cy: float, radius: float) -> None:
        r = radius * 1.7
        g = QRadialGradient(cx, cy, r)
        g.setColorAt(0.0, QColor(*_ACCENT, 55))
        g.setColorAt(0.4, QColor(*_ACCENT_CORE, 28))
        g.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(QRectF(cx - r, cy - r, r * 2, r * 2), g)

    def _draw_inner_haze(self, p: QPainter, cx: float, cy: float, radius: float) -> None:
        r = radius * (_INNER_RADIUS_SCALE + 0.14)
        g = QRadialGradient(cx, cy, r)
        g.setColorAt(0.0, QColor(255, 255, 255, 36))
        g.setColorAt(0.4, QColor(*_INNER_ACCENT, 55))
        g.setColorAt(1.0, QColor(*_INNER_ACCENT, 0))
        p.setBrush(g)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

    def _project_for_size(self) -> list[tuple[float, float, float, float]]:
        w, h = max(self.width(), 1), max(self.height(), 1)
        cx, cy = w * 0.5, h * 0.48
        radius = min(w, h) * _ORB_RATIO * self._zoom
        return self._project(cx, cy, radius, self._pts)

    def _project(
        self,
        cx: float,
        cy: float,
        radius: float,
        pts: list[tuple[float, float, float]],
        *,
        size_boost: float = 1.0,
    ) -> list[tuple[float, float, float, float]]:
        out: list[tuple[float, float, float, float]] = []
        if self._view_mode == "2d":
            # 평면 Z축 회전 — 찌그러짐 없이 데이터만 펼침
            cos_z, sin_z = math.cos(self._rot_y), math.sin(self._rot_y)
            for px, py, _pz in pts:
                x1 = px * cos_z - py * sin_z
                y1 = px * sin_z + py * cos_z
                depth = 0.55 + 0.45 * (1.0 - min(1.0, math.hypot(px, py)))
                out.append(
                    (
                        cx + x1 * radius,
                        cy + y1 * radius,
                        depth,
                        (1.1 + depth * 2.0) * size_boost,
                    )
                )
            return out

        cos_y, sin_y = math.cos(self._rot_y), math.sin(self._rot_y)
        cos_x, sin_x = math.cos(self._rot_x), math.sin(self._rot_x)
        scale = radius
        for px, py, pz in pts:
            x1 = px * cos_y + pz * sin_y
            z1 = -px * sin_y + pz * cos_y
            y2 = py * cos_x - z1 * sin_x
            z2 = py * sin_x + z1 * cos_x
            depth = (z2 + 1.0) * 0.5
            out.append(
                (
                    cx + x1 * scale,
                    cy + y2 * scale * 0.94,
                    depth,
                    (1.1 + depth * 2.0) * size_boost,
                )
            )
        return out

    def _draw_shell(
        self,
        p: QPainter,
        projected: list[tuple[float, float, float, float]],
        *,
        radius: float,
        accent: tuple[int, int, int],
        connect_dist: float,
        line_w: float,
        brighter: bool = False,
        selected_index: int | None = None,
        selected_accent: tuple[int, int, int] | None = None,
    ) -> None:
        connect_sq = (connect_dist * radius) ** 2
        n = len(projected)
        link_window = 28 if n > 120 else n

        p.save()
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)

        for i in range(n):
            x1, y1, d1, _ = projected[i]
            for j in range(i + 1, min(n, i + link_window)):
                x2, y2, d2, _ = projected[j]
                dx, dy = x2 - x1, y2 - y1
                if dx * dx + dy * dy > connect_sq:
                    continue
                avg = (d1 + d2) * 0.5
                base = 18 + 36 if brighter else 10 + 36
                alpha = int(base * avg)
                pen = QPen(QColor(*accent, alpha))
                pen.setWidthF(line_w)
                p.setPen(pen)
                p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        for i, (x, y, depth, size) in enumerate(projected):
            selected = selected_index is not None and i == selected_index
            color = (
                selected_accent
                if selected and selected_accent is not None
                else accent
            )
            alpha = int((70 + 170 * depth) if brighter else (50 + 170 * depth))
            r = size * (1.35 if selected else 0.95)
            g = QRadialGradient(x, y, r * 2.2)
            g.setColorAt(0.0, QColor(255, 255, 255, min(255, alpha + 50)))
            g.setColorAt(0.4, QColor(*color, alpha))
            g.setColorAt(1.0, QColor(*color, 0))
            p.setBrush(g)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QRectF(x - r, y - r, r * 2, r * 2))

        p.restore()

    def _draw_outer_shell(
        self, p: QPainter, cx: float, cy: float, radius: float
    ) -> list[tuple[float, float, float, float]]:
        projected = self._project(cx, cy, radius, self._pts)
        selected_index = None
        if self._selected_id is not None:
            for i, node in enumerate(self._nodes):
                if node.source_id == self._selected_id:
                    selected_index = i
                    break
        self._draw_shell(
            p,
            projected,
            radius=radius,
            accent=_ACCENT,
            connect_dist=_CONNECT_DIST,
            line_w=0.55,
            selected_index=selected_index,
            selected_accent=(236, 72, 153),
        )
        return projected

    def _draw_inner_shell(self, p: QPainter, cx: float, cy: float, radius: float) -> None:
        """Iris 스타일 내핵 파티클 구."""
        projected = self._project(
            cx, cy, radius, self._inner_pts, size_boost=1.25
        )
        self._draw_shell(
            p,
            projected,
            radius=radius,
            accent=_INNER_ACCENT,
            connect_dist=_INNER_CONNECT_DIST,
            line_w=0.8,
            brighter=True,
        )
        # 중심 하이라이트
        hot_r = radius * 0.22
        g = QRadialGradient(cx, cy, hot_r)
        g.setColorAt(0.0, QColor(255, 255, 255, 210))
        g.setColorAt(0.4, QColor(*_INNER_ACCENT_HOT, 150))
        g.setColorAt(1.0, QColor(*_INNER_ACCENT, 0))
        p.setBrush(g)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(cx - hot_r, cy - hot_r, hot_r * 2, hot_r * 2))

    def _draw_labels(
        self,
        p: QPainter,
        projected: list[tuple[float, float, float, float]],
    ) -> None:
        n = len(self._nodes)
        if n == 0:
            return
        max_chars = 22 if n < 40 else (16 if n < 100 else 12)
        font_pt = 8.5 if n < 40 else (7.0 if n < 100 else 6.0)
        font = QFont(p.font())
        font.setPointSizeF(font_pt)
        p.setFont(font)
        fm = p.fontMetrics()

        order = sorted(range(min(n, len(projected))), key=lambda i: projected[i][2])
        for i in order:
            x, y, depth, size = projected[i]
            label = _short_label(self._nodes[i].title, max_chars=max_chars)
            alpha = int(40 + 185 * depth)
            p.setPen(QColor(230, 225, 255, alpha))
            tw = fm.horizontalAdvance(label)
            p.drawText(QPointF(x - tw * 0.5, y + size + font_pt + 1.0), label)

    def _draw_empty_hint(self, p: QPainter, cx: float, cy: float, radius: float) -> None:
        p.setPen(QColor(*_ACCENT, 160))
        font = QFont(p.font())
        font.setPointSizeF(10)
        p.setFont(font)
        p.drawText(
            QRectF(cx - radius, cy + radius * 0.55, radius * 2, 28),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            "인덱싱된 Iris Wiki 노트 없음",
        )