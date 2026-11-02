#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""常驻存储容量探测 Worker（手机与本机磁盘）"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot

from phonetransfer.adb.storage import query_available_space, query_local_disk_space
from phonetransfer.workers.base import reclaim_qobject_to_main


class StorageWorker(QObject):
    """常驻存储探测（手机 / 本机）。"""

    finished = Signal(str, int)
    failed = Signal(str, int)
    _kick = Signal(str, int, str, str)

    def __init__(self) -> None:
        super().__init__()
        self._kick.connect(self._run)

    def probe(
        self, path: str, gen: int, *, target: str, serial: str | None = None
    ) -> None:
        self._kick.emit(path, gen, target, serial or "")

    @Slot()
    def prepare_shutdown(self) -> None:
        self.blockSignals(True)
        reclaim_qobject_to_main(self)

    def _run(self, path: str, gen: int, target: str, serial: str = "") -> None:
        try:
            if target == "local":
                text = query_local_disk_space(path)
            else:
                avail = query_available_space(path, serial=serial or None)
                text = avail if avail else "—"
            self.finished.emit(text, gen)
        except Exception as e:
            self.failed.emit(str(e), gen)

