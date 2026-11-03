"""Entry point for PhoneTransfer."""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from phonetransfer.i18n import initialize
from phonetransfer.ui.main_window import MainWindow
from phonetransfer.utils import resolve_app_icon


def main() -> None:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setOrganizationName("PhoneTransfer")
    app.setApplicationName("Phone Transfer")
    initialize(app)
    app.setFont(QFont(".AppleSystemUIFont", 13))
    icon = resolve_app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)
    win = MainWindow()
    if not icon.isNull():
        win.setWindowIcon(icon)
    win.show()
    win.raise_()
    win.activateWindow()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

