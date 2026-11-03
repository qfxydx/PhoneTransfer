#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手机远端文件操作（新建文件夹、重命名、删除）异步 Worker"""

from __future__ import annotations

from phonetransfer.i18n import tr

from typing import Literal
from PySide6.QtCore import QObject, Signal

from phonetransfer.adb.file_ops import remote_delete, remote_mkdir, remote_rename
from phonetransfer.workers.base import reclaim_qobject_to_main

RemoteOpType = Literal["mkdir", "rename", "delete"]


class RemoteOpWorker(QObject):
    """异步执行 ADB 远端文件操作，防止阻塞 Qt 主线程。"""

    finished = Signal(bool, str, str, list)  # (success, message, op_type, paths)

    def __init__(self, op_type: RemoteOpType, paths: list[str]) -> None:
        super().__init__()
        self.op_type: RemoteOpType = op_type
        self.paths: list[str] = list(paths)
        self._cancelled: bool = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            if self._cancelled:
                return

            if self.op_type == "mkdir":
                target = self.paths[0] if self.paths else ""
                ok, err = remote_mkdir(target)
                msg = tr('已新建文件夹「{p0}」', p0=target) if ok else (err or tr('创建文件夹失败'))
                if not self._cancelled:
                    self.finished.emit(ok, msg, self.op_type, self.paths)

            elif self.op_type == "rename":
                old_p = self.paths[0] if len(self.paths) > 0 else ""
                new_p = self.paths[1] if len(self.paths) > 1 else ""
                ok, err = remote_rename(old_p, new_p)
                msg = tr('重命名成功') if ok else (err or tr('重命名失败'))
                if not self._cancelled:
                    self.finished.emit(ok, msg, self.op_type, self.paths)

            elif self.op_type == "delete":
                ok, err = remote_delete(self.paths)
                n = len(self.paths)
                msg = tr('已从手机删除 {p0} 个项目', p0=n) if ok else (err or tr('删除失败'))
                if not self._cancelled:
                    self.finished.emit(ok, msg, self.op_type, self.paths)

            else:
                if not self._cancelled:
                    self.finished.emit(False, tr('未知的操作类型: {p0}', p0=self.op_type), self.op_type, self.paths)

        except Exception as e:
            if not self._cancelled:
                self.finished.emit(False, tr('操作异常: {p0}', p0=e), self.op_type, self.paths)
        finally:
            reclaim_qobject_to_main(self)

