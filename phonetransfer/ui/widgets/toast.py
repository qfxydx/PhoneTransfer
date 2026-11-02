"""Floating toast notification widget."""

from __future__ import annotations

from PySide6.QtCore import QPropertyAnimation, Qt, QTimer
from PySide6.QtWidgets import QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QWidget

from phonetransfer.constants import TOAST_DURATION_MS, TOAST_FADE_MS
from phonetransfer.utils import sym


class TransferToast(QFrame):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("transferToast")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        row = QHBoxLayout(self)
        row.setContentsMargins(16, 10, 16, 10)
        row.setSpacing(8)
        self._icon = QLabel(sym("checkmark.circle"))
        self._icon.setObjectName("toastIcon")
        self._text = QLabel("")
        self._text.setObjectName("toastText")
        row.addWidget(self._icon)
        row.addWidget(self._text)
        self._opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._fade_out)
        self._fade_anim: QPropertyAnimation | None = None
        self.hide()

    def show_message(self, text: str) -> None:
        self._hide_timer.stop()
        if self._fade_anim is not None:
            self._fade_anim.stop()
            self._fade_anim = None
        self._text.setText(text)
        self.adjustSize()
        self._reposition()
        self._opacity.setOpacity(1.0)
        self.show()
        self.raise_()
        self._hide_timer.start(TOAST_DURATION_MS)

    def dismiss(self) -> None:
        self._hide_timer.stop()
        if self._fade_anim is not None:
            self._fade_anim.stop()
            self._fade_anim = None
        self.hide()

    def _fade_out(self) -> None:
        anim = QPropertyAnimation(self._opacity, b"opacity", self)
        anim.setDuration(TOAST_FADE_MS)
        anim.setStartValue(self._opacity.opacity())
        anim.setEndValue(0.0)
        anim.finished.connect(self.hide)
        anim.start()
        self._fade_anim = anim

    def _reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        x = max(0, (parent.width() - self.width()) // 2)
        y = max(0, parent.height() - self.height() - 96)
        self.move(x, y)

