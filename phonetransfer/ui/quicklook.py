"""macOS 原生 Quick Look 与音视频快速预览管理器。"""

from __future__ import annotations

from pathlib import Path
import hashlib
import subprocess
import sys
import tempfile

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QCloseEvent, QKeyEvent
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import QDialog, QVBoxLayout


def is_apple_silicon() -> bool:
    if sys.platform != "darwin":
        return False
    try:
        res = subprocess.run(
            ["/usr/sbin/sysctl", "-n", "hw.optional.arm64"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        return res.returncode == 0 and res.stdout.strip() == "1"
    except Exception:
        return False


_IS_ARM64 = is_apple_silicon()

VIDEO_SUFFIXES = {
    ".mp4",
    ".mov",
    ".m4v",
    ".mkv",
    ".avi",
    ".webm",
    ".3gp",
    ".flv",
    ".wmv",
    ".ts",
}


class VideoPreviewDialog(QDialog):
    """用于音视频文件的轻量级浮动预览窗口。

    macOS 系统的 /usr/bin/qlmanage 在处理任何 MP4/MOV 等视频时存在已知系统底层 Bug
    (Movie.qldisplay 在 AVKitCore 中抛出 NSInternalInconsistencyException 导致崩溃闪退)。
    通过 Qt 原生多媒体播放器实现空格键即时浮窗播放，兼具极速响应、全格式支持与 100% 稳定性。
    """

    def __init__(self, file_path: str, parent=None) -> None:
        super().__init__(parent)
        p = Path(file_path)
        self.setWindowTitle(f"预览 — {p.name}")
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.CustomizeWindowHint
        )
        self.resize(720, 460)
        self.setStyleSheet("background: #000000; border-radius: 8px;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.video_widget = QVideoWidget(self)
        self.video_widget.setStyleSheet("background: #000000;")
        layout.addWidget(self.video_widget)

        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video_widget)

        self.file_path = str(p)
        self.player.setSource(QUrl.fromLocalFile(str(p)))
        self.player.play()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Escape):
            self.close()
            event.accept()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()
        event.accept()

    def closeEvent(self, event: QCloseEvent) -> None:
        try:
            self.player.stop()
        except Exception:
            pass
        super().closeEvent(event)


class QuickLookManager:
    """管理空格键快速预览窗口。

    - 视频文件（.mp4/.mov 等）：自动采用 Qt 原生多媒体播放窗口，完美规避 macOS qlmanage 视频解码系统 Bug；
    - 图片/PDF/文本文件：调用 macOS 原生 Quick Look 窗口，保留原汁原味 Mac 质感。
    """

    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self._video_dlg: VideoPreviewDialog | None = None
        self._current_path: str | None = None

    def is_previewing(self) -> bool:
        if self._video_dlg is not None and self._video_dlg.isVisible():
            return True
        if self._proc is not None:
            if self._proc.poll() is None:
                return True
            self._proc = None
            self._current_path = None
        return False

    def current_path(self) -> str | None:
        if self.is_previewing():
            return self._current_path
        return None

    def close(self) -> None:
        if self._video_dlg is not None:
            try:
                self._video_dlg.close()
                self._video_dlg.deleteLater()
            except Exception:
                pass
            self._video_dlg = None
        if self._proc is not None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=0.4)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            self._proc = None
        self._current_path = None

    def toggle(self, path: str | Path) -> bool:
        """空格键触发：若当前正在预览该文件则关闭；否则打开该文件预览。"""
        p = Path(path).resolve()
        if not p.exists() or p.stat().st_size == 0:
            return False

        if self.is_previewing() and str(p) == self._current_path:
            self.close()
            return False

        return self.preview(p)

    def preview(self, path: str | Path) -> bool:
        p = Path(path).resolve()
        if not p.exists() or p.stat().st_size == 0:
            return False

        self.close()

        ext = p.suffix.lower()
        if ext in VIDEO_SUFFIXES:
            try:
                dlg = VideoPreviewDialog(str(p))
                dlg.show()
                self._video_dlg = dlg
                self._current_path = str(p)
                return True
            except Exception:
                self._video_dlg = None
                self._current_path = None
                return False

        if sys.platform != "darwin":
            return False

        cmd = ["/usr/bin/qlmanage", "-p", str(p)]
        if _IS_ARM64 and Path("/usr/bin/arch").exists():
            cmd = ["/usr/bin/arch", "-arm64", "/usr/bin/qlmanage", "-p", str(p)]

        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._current_path = str(p)
            return True
        except Exception:
            self._proc = None
            self._current_path = None
            return False

    @staticmethod
    def preview_cache_dir() -> Path:
        cache = Path(tempfile.gettempdir()) / "phonetransfer_preview"
        cache.mkdir(parents=True, exist_ok=True)
        return cache

    @classmethod
    def get_preview_cache_path(cls, remote_path: str, serial: str | None = None) -> Path:
        """Keep caches isolated by ADB device and full remote path."""
        cache_dir = cls.preview_cache_dir()
        device_key = hashlib.sha256((serial or "unknown").encode("utf-8")).hexdigest()[:16]
        path_key = hashlib.sha256(remote_path.encode("utf-8")).hexdigest()[:24]
        filename = Path(remote_path).name
        if not filename or filename in (".", ".."):
            filename = "preview_file"
        return cache_dir / device_key / path_key / filename
