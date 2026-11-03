#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文件批量传输后台 Worker（进度通知、取消管理、媒体库刷新）"""

from __future__ import annotations

from phonetransfer.i18n import tr

import posixpath
import subprocess
import time

from PySide6.QtCore import QObject, Signal

from phonetransfer.adb.core import adb_cmd, get_active_serial
from phonetransfer.adb.file_ops import count_pull_totals
from phonetransfer.adb.media import refresh_phone_media
from phonetransfer.adb.transfer import (
    FileProgressTracker,
    count_transfer_totals,
    pull_one,
    push_one,
)
from phonetransfer.constants import FolderSyncMode, TransferDirection
from phonetransfer.utils import human_size
from phonetransfer.workers.base import reclaim_qobject_to_main


class TransferWorker(QObject):
    log = Signal(str)
    progress = Signal(int, int, int, int, str)
    finished = Signal(bool, str)

    def __init__(
        self,
        items: list[str],
        dest: str,
        *,
        direction: TransferDirection = "to_phone",
        folder_sync_mode: FolderSyncMode = "overwrite",
    ) -> None:
        super().__init__()
        self.items = items
        self.dest = dest.rstrip("/")
        self.direction = direction
        self.folder_sync_mode = folder_sync_mode
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def _cancelled_check(self) -> bool:
        return self._cancelled

    def run(self) -> None:
        try:
            if self.direction == "to_phone":
                total_bytes, total_files = count_transfer_totals(self.items)
            else:
                total_bytes, total_files = count_pull_totals(self.items)
            tracker = FileProgressTracker(total_bytes, total_files, self.progress.emit)
            tracker.report(tr('准备中…'))
            self.log.emit(
                tr('开始传输 {p0} 项（共 {p1} 个文件，{p2}）→ {p3}', p0=len(self.items), p1=total_files, p2=human_size(total_bytes), p3=self.dest)
            )
            serial = get_active_serial()
            if not serial:
                self.finished.emit(
                    False, tr('未选择目标设备，请先在右上角切换到要传输的手机')
                )
                return
            st = subprocess.run(
                adb_cmd("get-state"),
                capture_output=True,
                text=True,
                timeout=10,
            )
            state = (st.stdout or "").strip()
            if state != "device":
                err = (st.stderr or st.stdout or "").strip()
                if "more than one" in err.lower():
                    self.finished.emit(
                        False, tr('检测到多台设备，请先在右上角选择要传输的手机')
                    )
                else:
                    self.finished.emit(
                        False,
                        tr('设备未就绪（{p0}），请检查 USB 调试是否已授权', p0=serial),
                    )
                return

            ok_count = 0
            failed: list[str] = []
            pushed_remotes: list[str] = []
            start = time.monotonic()

            for i, item in enumerate(self.items, 1):
                if self._cancelled:
                    self.finished.emit(False, tr('传输已取消'))
                    return
                name = posixpath.basename(item.rstrip("/"))
                self.log.emit(f"[{i}/{len(self.items)}] {name}")
                try:
                    if self.direction == "to_phone":
                        ok, msg = push_one(
                            item,
                            self.dest,
                            self.log.emit,
                            self._cancelled_check,
                            folder_sync_mode=self.folder_sync_mode,
                            progress=tracker,
                        )
                    else:
                        ok, msg = pull_one(
                            item,
                            self.dest,
                            self.log.emit,
                            self._cancelled_check,
                            folder_sync_mode=self.folder_sync_mode,
                            progress=tracker,
                        )
                except subprocess.TimeoutExpired:
                    ok, msg = False, tr('超时：{p0}', p0=name)
                except Exception as e:
                    ok, msg = False, f"{name}：{e}"
                if ok:
                    ok_count += 1
                    if self.direction == "to_phone" and msg:
                        pushed_remotes.append(msg)
                else:
                    if msg == tr('已取消'):
                        self.finished.emit(False, tr('传输已取消'))
                        return
                    failed.append(msg)

            elapsed = time.monotonic() - start
            self.log.emit(tr('耗时 {p0:.1f}s', p0=elapsed))

            if self.direction == "to_phone" and pushed_remotes:
                try:
                    refresh_phone_media(pushed_remotes, self.log.emit)
                except Exception as e:
                    self.log.emit(tr('刷新媒体库时出错：{p0}', p0=e))

            if failed:
                summary = tr('完成 {p0}/{p1} 项，{p2} 项失败', p0=ok_count, p1=len(self.items), p2=len(failed))
                self.finished.emit(False, f"{summary}\n{failed[0]}")
                return

            if len(self.items) == 1:
                self.finished.emit(True, tr('已发送 1 个文件'))
            else:
                self.finished.emit(True, tr('已发送 {p0} 个文件', p0=len(self.items)))
        except subprocess.TimeoutExpired:
            self.finished.emit(False, tr('操作超时'))
        except Exception as e:
            self.finished.emit(False, str(e))
        finally:
            reclaim_qobject_to_main(self)

