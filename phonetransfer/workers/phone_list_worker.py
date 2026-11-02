#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手机远端目录内容浏览列表异步加载 Worker"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from phonetransfer.adb.file_ops import list_remote_listing, resolve_remote_dir
from phonetransfer.workers.base import reclaim_qobject_to_main


class PhoneListWorker(QObject):
    dirs_finished = Signal(list, int, str)
    files_finished = Signal(list, int)
    failed = Signal(str, int)

    def __init__(self, remote_dir: str, token: int) -> None:
        super().__init__()
        self.remote_dir = remote_dir
        self.token = token
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            if self._cancelled:
                return
            resolved_dir = resolve_remote_dir(self.remote_dir)
            dirs, files = list_remote_listing(resolved_dir)
            if self._cancelled:
                return
            self.dirs_finished.emit(dirs, self.token, resolved_dir)
            if self._cancelled:
                return
            self.files_finished.emit(files, self.token)
        except Exception as e:
            if not self._cancelled:
                self.failed.emit(str(e), self.token)
        finally:
            # 线程退出前把 affinity 交还主线程，避免随后 deleteLater 崩在 Shiboken
            reclaim_qobject_to_main(self)

