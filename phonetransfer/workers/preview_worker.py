"""手机端文件快速预览拉取 Worker。"""

from __future__ import annotations

from pathlib import Path
import os
import shutil
import subprocess
import uuid

from PySide6.QtCore import QThread, Signal

from phonetransfer.adb.core import adb_cmd, shell_quote
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

    def _remote_signature(self) -> tuple[int, str] | None:
        """Size and nanosecond mtime when available; never trust size alone."""
        cmd = adb_cmd(
            "shell", f"stat -c '%s|%Y|%y' {shell_quote(self._remote_path)}",
            serial=self._serial,
        )
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            return None
        if res.returncode != 0 or "|" not in res.stdout:
            return None
        size_text, _, stamp = res.stdout.strip().partition("|")
        try:
            return int(size_text), stamp.strip()
        except ValueError:
            return None

    def run(self) -> None:
        cache = self._local_cache
        metadata = cache.with_name(cache.name + ".ptmeta")
        temp = cache.with_name(f".{cache.name}.pt-preview-{uuid.uuid4().hex}")
        try:
            signature = self._remote_signature()
            expected_size = signature[0] if signature else self._remote_size
            fingerprint = f"{signature[0]}|{signature[1]}" if signature else None

            metadata_matches = False
            if fingerprint and metadata.is_file():
                try:
                    metadata_matches = metadata.read_text(encoding="utf-8") == fingerprint
                except (OSError, UnicodeError):
                    pass
            if (
                metadata_matches
                and cache.is_file()
                and cache.stat().st_size == expected_size
            ):
                self.ready.emit(str(cache))
                return

            cache.parent.mkdir(parents=True, exist_ok=True)
            available = shutil.disk_usage(cache.parent).free
            if expected_size > max(0, available - 32 * 1024 * 1024):
                raise RuntimeError("Mac 可用磁盘空间不足，无法缓存文件预览")

            cmd = adb_cmd("pull", self._remote_path, str(temp), serial=self._serial)
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(
                    "手机文件预览下载超时，建议先将大型视频传输到 Mac 后打开"
                ) from exc
            if res.returncode != 0:
                raise RuntimeError(
                    (res.stderr or res.stdout or "拉取失败").strip()
                )
            if not temp.is_file() or temp.stat().st_size != expected_size:
                raise RuntimeError("预览文件大小校验失败，未使用不完整缓存")
            if signature and self._remote_signature() != signature:
                raise RuntimeError("预览过程中手机文件发生变化，请重新打开")

            os.replace(temp, cache)
            if fingerprint:
                metadata.write_text(fingerprint, encoding="utf-8")
            else:
                # No metadata support: do not reuse this cache on the next visit.
                metadata.unlink(missing_ok=True)
            self.ready.emit(str(cache))
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
            reclaim_qobject_to_main(self)
