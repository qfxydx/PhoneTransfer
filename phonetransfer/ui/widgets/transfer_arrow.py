"""Transfer direction arrow widget."""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QWidget


class TransferArrow(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(62, 16)
        self._quaternary = QColor("#aeaeb2")
        self._tertiary = QColor("#86868b")

    def set_colors(self, quaternary: str, tertiary: str) -> None:
        self._quaternary = QColor(quaternary)
        self._tertiary = QColor(tertiary)
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        cy = h / 2
        grad = QLinearGradient(QPointF(0, cy), QPointF(w - 10, cy))
        grad.setColorAt(0.0, self._quaternary)
        grad.setColorAt(1.0, self._tertiary)
        pen = QPen(QBrush(grad), 2)
        p.setPen(pen)
        p.drawLine(QPointF(0, cy), QPointF(w - 12, cy))
        p.setBrush(QBrush(self._tertiary))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPolygon(
            [
                QPointF(w - 12, cy - 4),
                QPointF(w - 2, cy),
                QPointF(w - 12, cy + 4),
            ]
        )
        p.end()

