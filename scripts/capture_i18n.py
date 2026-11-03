#!/usr/bin/env python3
"""Capture globe-menu evidence offscreen, with device/process work blocked.

Writes to a fresh directory and refuses to overwrite any previous evidence.
"""
import argparse
import os
import sys
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QPoint, QThread
from PySide6.QtGui import QFont, QPainter, QPixmap
from PySide6.QtWidgets import QApplication
from phonetransfer.i18n import initialize, LANGUAGES
from phonetransfer.ui.main_window import MainWindow

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] /
                    "docs" / "i18n-screenshots" / "globe-rc2")
args = parser.parse_args()
out = args.output
if out.exists() and any(out.iterdir()):
    parser.error(f"Output directory must be empty to preserve earlier screenshots: {out}")
out.mkdir(parents=True, exist_ok=True)
app = QApplication([])
app.setFont(QFont(".AppleSystemUIFont", 13))


def save(pixmap, filename):
    if not pixmap.save(str(out / filename)):
        raise RuntimeError(f"Could not save {filename}")
    print(filename, pixmap.width(), pixmap.height())


for dark in (False, True):
    for language in (LANGUAGES if not dark else ("zh-CN", "en")):
        initialize(app, selection=language)
        with patch.object(QThread, "start"), patch.object(MainWindow, "refresh_device"), \
             patch.object(MainWindow, "_is_dark", return_value=dark), \
             patch("phonetransfer.ui.main_window.saved_selection", return_value=language), \
             patch("subprocess.run") as run, patch("subprocess.Popen") as popen:
            window = MainWindow()
            window._device_poll_timer.stop()
            window._storage_poll_timer.stop()
            try:
                window.show()
                app.processEvents()
                assert (window.width(), window.height()) == (742, 680)
                assert window.language_button.text() == ""
                assert not window.language_button.icon().isNull()
                assert len(window.language_menu.actions()) == 7
                suffix = "-dark" if dark else ""
                save(window.grab(), f"main-{language}{suffix}.png")
                if language in ("zh-CN", "en"):
                    menu = window.language_menu
                    button = window.language_button
                    menu.popup(button.mapToGlobal(QPoint(0, button.height())))
                    app.processEvents()
                    assert [a.data() for a in menu.actions() if a.isChecked()] == [language]
                    # QMenu is a separate popup surface; composite actual widget grabs at
                    # their global positions, without drawing or substituting UI content.
                    bounds = window.frameGeometry().united(menu.frameGeometry())
                    canvas = QPixmap(bounds.size())
                    canvas.fill(window.palette().window().color())
                    painter = QPainter(canvas)
                    painter.drawPixmap(window.mapToGlobal(QPoint()) - bounds.topLeft(), window.grab())
                    painter.drawPixmap(menu.mapToGlobal(QPoint()) - bounds.topLeft(), menu.grab())
                    painter.end()
                    save(canvas, f"menu-{language}{suffix}.png")
                    menu.hide()
            finally:
                window.close()
                window.deleteLater()
                app.processEvents()
            run.assert_not_called()
            popen.assert_not_called()
