"""手机端文件快速预览拉取 Worker。"""

from __future__ import annotations

from pathlib import Path
import subprocess

from PySide6.QtCore import QThread, Signal

from phonetransfer.adb.core import adb_cmd
from phonetransfer.workers.base import reclaim_qobject_to_main


class RemotePreviewWorker(QThread):
    """在后台将手机端选中的文件快速拉取至临时预览目录，用于触发 Quick Look。"""

    ready = Signal(str)    # 本地缓存文件路径
    failed = Signal(str)   # 错误原因

    def __init__(
        self,
        remote_path: str,
        remote_size: int,
        local_cache_path: str,
        serial: str | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._remote_path = remote_path
        self._remote_size = remote_size
        self._local_cache = Path(local_cache_path)
        self._serial = serial

    def run(self) -> None:
        try:
            # 命中缓存检测（大小一致即复用）
            if self._local_cache.exists() and self._local_cache.stat().st_size == self._remote_size:
                self.ready.emit(str(self._local_cache))
                return

            self._local_cache.parent.mkdir(parents=True, exist_ok=True)
            cmd = adb_cmd("pull", self._remote_path, str(self._local_cache), serial=self._serial)
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if res.returncode == 0 and self._local_cache.exists():
                self.ready.emit(str(self._local_cache))
            else:
                err = (res.stderr or res.stdout or "拉取失败").strip()
                self.failed.emit(err)
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            reclaim_qobject_to_main(self)

