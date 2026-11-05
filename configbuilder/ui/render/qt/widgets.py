"""Small shared widgets the pages reuse (Stage 8).

One component lives here today: :class:`CollapsibleSection`. It exists because
two pages need the same progressive-disclosure pattern — "show the few
decisions the task needs, keep the rest one labelled click away" — and because
doing it once keeps the wording, the arrow and the keyboard behaviour
identical instead of each page inventing its own toggle.

Nothing here knows about a service, a job or a page: the widget displays what
it is given and reports the expanded state, nothing more. Styling stays in
``style.py``; this module uses the ordinary Qt widgets and no colour of its
own, so both Windows themes keep working.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from configbuilder.ui.render.qt.style import COLORS

__all__ = ["CollapsibleSection", "app_mark_pixmap", "navigation_icon"]

#: Logical size of a navigation glyph (the sheet scales the row around it).
_GLYPH = 16
#: Paint at twice the logical size so the glyph stays crisp on scaled displays.
_DPR = 2


def _canvas() -> QPixmap:
    """An empty transparent pixmap at the glyph's logical size."""
    pixmap = QPixmap(_GLYPH * _DPR, _GLYPH * _DPR)
    pixmap.fill(Qt.transparent)
    pixmap.setDevicePixelRatio(_DPR)
    return pixmap


def _painter(pixmap: QPixmap, colour: str) -> QPainter:
    """A stroke painter with the mockup's line weight and round joins."""
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(QColor(colour))
    pen.setWidthF(1.5)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    return painter


def _draw_overview(painter: QPainter) -> None:
    """A four-cell grid: the control-centre destination."""
    for x, y in ((2, 2), (9, 2), (2, 9), (9, 9)):
        painter.drawRoundedRect(QRectF(x, y, 5, 5), 1.4, 1.4)


def _draw_entities(painter: QPainter) -> None:
    """Two connected nodes: the entity workspace."""
    painter.drawEllipse(QPointF(4.2, 6.2), 2.2, 2.2)
    painter.drawEllipse(QPointF(11.6, 10.2), 2.2, 2.2)
    painter.drawLine(QPointF(6.1, 7.4), QPointF(9.7, 9.0))


def _draw_generate(painter: QPainter) -> None:
    """A folder: the destination of the output plan."""
    path = QPainterPath()
    path.moveTo(2.0, 4.6)
    path.lineTo(6.4, 4.6)
    path.lineTo(7.9, 6.6)
    path.lineTo(14.0, 6.6)
    path.lineTo(14.0, 13.0)
    path.lineTo(2.0, 13.0)
    path.closeSubpath()
    painter.drawPath(path)


def _draw_preview(painter: QPainter) -> None:
    """Angle brackets: the serialized document."""
    painter.drawPolyline(QPolygonF([QPointF(6.2, 3.8), QPointF(2.6, 8.0), QPointF(6.2, 12.2)]))
    painter.drawPolyline(QPolygonF([QPointF(9.8, 3.8), QPointF(13.4, 8.0), QPointF(9.8, 12.2)]))


_DRAWERS = {
    "overview": _draw_overview,
    "entities": _draw_entities,
    "generate": _draw_generate,
    "preview": _draw_preview,
}


def _glyph(name: str, colour: str) -> QPixmap:
    pixmap = _canvas()
    painter = _painter(pixmap, colour)
    try:
        _DRAWERS[name](painter)
    finally:
        painter.end()
    return pixmap


def navigation_icon(name: str) -> QIcon:
    """The sidebar glyph for one destination, muted or accented.

    Two pixmaps per icon (normal and selected) let the row follow the
    destination state without the widget knowing any colour. ``name`` is one
    of ``overview``, ``entities``, ``generate``, ``preview``.
    """
    icon = QIcon()
    icon.addPixmap(_glyph(name, COLORS["muted"]), QIcon.Normal, QIcon.Off)
    icon.addPixmap(_glyph(name, COLORS["accent"]), QIcon.Selected, QIcon.Off)
    icon.addPixmap(_glyph(name, COLORS["border"]), QIcon.Disabled, QIcon.Off)
    return icon


def app_mark_pixmap(size: int = 20) -> QPixmap:
    """The header's small three-node mark, in the accent colour."""
    pixmap = QPixmap(size * _DPR, size * _DPR)
    pixmap.fill(Qt.transparent)
    pixmap.setDevicePixelRatio(_DPR)
    painter = _painter(pixmap, COLORS["accent"])
    try:
        painter.setBrush(QColor(COLORS["accent"]))
        points = (QPointF(3.0, 4.2), QPointF(3.0, 15.8), QPointF(15.0, 10.0))
        for start, end in ((points[0], points[1]), (points[1], points[2]), (points[2], points[0])):
            painter.drawLine(start, end)
        for point in points:
            painter.drawEllipse(point, 2.1, 2.1)
    finally:
        painter.end()
    return pixmap


class CollapsibleSection(QWidget):
    """A labelled header that shows or hides a body.

    The header is a checkable ``QToolButton`` with an arrow, which keeps the
    usual Qt keyboard behaviour (focus, Space/Enter to toggle) and never relies
    on colour: the arrow and the body's visibility are the signal.

    ``body`` is a plain ``QWidget`` the caller fills; it is hidden until the
    header is activated for the first time, so an option the user rarely needs
    does not compete with the task at hand. The body is never *destroyed*, so
    values the user typed stay exactly as they were across a collapse.
    """

    def __init__(self, title: str, expanded: bool = False, parent=None) -> None:
        super().__init__(parent)
        self._button = QToolButton()
        self._button.setText(title)
        self._button.setCheckable(True)
        self._button.setChecked(expanded)
        self._button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self._button.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self._button.clicked.connect(self._on_toggled)
        self.body = QWidget()
        self.body.setVisible(expanded)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._button)
        layout.addWidget(self.body)
        self._button.setAccessibleName(title)

    # -- state -------------------------------------------------------------

    def is_expanded(self) -> bool:
        """True while the body is shown."""
        return self._button.isChecked()

    def set_expanded(self, expanded: bool) -> None:
        """Show or hide the body without pretending the user clicked."""
        self._button.setChecked(expanded)
        self._on_toggled()

    def toggle(self) -> None:
        """Activate the header exactly as a click does (used by tests)."""
        self._button.click()

    def header_text(self) -> str:
        """The header wording as displayed."""
        return self._button.text()

    def _on_toggled(self) -> None:
        expanded = self._button.isChecked()
        self._button.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self.body.setVisible(expanded)
