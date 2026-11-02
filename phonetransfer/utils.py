#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phone Transfer 工具函数集"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QEventLoop, QProcess
from PySide6.QtGui import QFontDatabase, QIcon
from PySide6.QtWidgets import QFileDialog, QWidget

from phonetransfer.constants import FILE_BADGE_COLORS

# 项目根目录（兼容从 phonetransfer 包内调用和单文件调用）
_HERE = Path(__file__).resolve().parent
PROJECT_ROOT = _HERE.parent if (_HERE.parent / "pick_items.swift").is_file() else _HERE


def card_shadow(widget: QWidget) -> None:
    """Flat cards use border only; no drop shadow."""
    widget.setGraphicsEffect(None)


def file_badge(path: Path) -> tuple[str, str]:
    if path.is_dir():
        return "DIR", "#98989d"
    ext = path.suffix.lower()
    if ext in FILE_BADGE_COLORS:
        return FILE_BADGE_COLORS[ext]
    label = ext.lstrip(".").upper()[:4] or "FILE"
    return label, "#8e8e93"


def resolve_symbol_font() -> str:
    families = set(QFontDatabase.families())
    for name in ("SF Symbols", "SF Pro Symbols", ".AppleSymbols"):
        if name in families:
            return name
    return ".AppleSystemUIFont"


def make_mac_folder_plus_icon(
    normal: str = "#86868b", hover: str = "#007aff", disabled: str = "#555558", size: int = 18
) -> QIcon:
    """生成官方 macOS Finder 风格的「新建文件夹 (folder.badge.plus)」矢量图标。"""
    from PySide6.QtCore import QByteArray, Qt
    from PySide6.QtGui import QPainter, QPixmap
    from PySide6.QtSvg import QSvgRenderer

    svg_template = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M12 19H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.93a2 2 0 0 1 1.66.9l.82 1.2a2 2 0 0 0 1.66.9H20a2 2 0 0 1 2 2v4"/>
  <line x1="19" y1="13" x2="19" y2="21"/>
  <line x1="15" y1="17" x2="23" y2="17"/>
</svg>"""

    icon = QIcon()
    modes = [
        (normal, QIcon.Mode.Normal),
        (hover, QIcon.Mode.Active),
        (disabled, QIcon.Mode.Disabled),
    ]
    for color, mode in modes:
        svg_data = svg_template.format(color=color).encode("utf-8")
        renderer = QSvgRenderer(QByteArray(svg_data))
        pm = QPixmap(size * 2, size * 2)  # 2x Retina
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        renderer.render(p)
        p.end()
        icon.addPixmap(pm, mode)
    return icon


def make_mac_coffee_icon(
    normal: str = "#86868b", hover: str = "#ff9f0a", disabled: str = "#555558", size: int = 18
) -> QIcon:
    """生成官方 macOS 风格的「咖啡杯 (cup.and.saucer)」矢量图标。"""
    from PySide6.QtCore import QByteArray, Qt
    from PySide6.QtGui import QPainter, QPixmap
    from PySide6.QtSvg import QSvgRenderer

    svg_template = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round">
  <path d="M18 8h1a4 4 0 0 1 0 8h-1"/>
  <path d="M2 8h16v9a4 4 0 0 1-4 4H6a4 4 0 0 1-4-4V8z"/>
  <line x1="6" y1="1" x2="6" y2="4"/>
  <line x1="10" y1="1" x2="10" y2="4"/>
  <line x1="14" y1="1" x2="14" y2="4"/>
</svg>"""

    icon = QIcon()
    modes = [
        (normal, QIcon.Mode.Normal),
        (hover, QIcon.Mode.Active),
        (disabled, QIcon.Mode.Disabled),
    ]
    for color, mode in modes:
        svg_data = svg_template.format(color=color).encode("utf-8")
        renderer = QSvgRenderer(QByteArray(svg_data))
        pm = QPixmap(size * 2, size * 2)  # 2x Retina
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        renderer.render(p)
        p.end()
        icon.addPixmap(pm, mode)
    return icon


def make_mac_screen_icon(
    normal: str = "#86868b", hover: str = "#007aff", disabled: str = "#555558", size: int = 18
) -> QIcon:
    """生成官方 macOS 风格的「屏幕/投屏 (display)」矢量图标。"""
    from PySide6.QtCore import QByteArray, Qt
    from PySide6.QtGui import QPainter, QPixmap
    from PySide6.QtSvg import QSvgRenderer

    svg_template = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
  <rect x="2" y="3" width="20" height="14" rx="2"/>
  <line x1="8" y1="21" x2="16" y2="21"/>
  <line x1="12" y1="17" x2="12" y2="21"/>
</svg>"""

    icon = QIcon()
    modes = [
        (normal, QIcon.Mode.Normal),
        (hover, QIcon.Mode.Active),
        (disabled, QIcon.Mode.Disabled),
    ]
    for color, mode in modes:
        svg_data = svg_template.format(color=color).encode("utf-8")
        renderer = QSvgRenderer(QByteArray(svg_data))
        pm = QPixmap(size * 2, size * 2)  # 2x Retina
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        renderer.render(p)
        p.end()
        icon.addPixmap(pm, mode)
    return icon


def sym(name: str) -> str:
    mapping = {
        "arrow.clockwise": "\u21bb",
        "trash": "\U0001F5D1",
        "tray.and.arrow.up": "\u2b06",
        "doc": "\U0001F4C4",
        "folder": "\U0001F4C1",
        "iphone": "\U0001F4F1",
        "checkmark.circle": "\u2713",
        "xmark.circle": "\u2715",
        "chevron.down": "\u25be",
        "chevron.right": "\u25b8",
        "chevron.left": "\u25c2",
        "arrow.left.arrow.right": "\u2194",
        "paperplane": "\u2708",
        "folder.badge.plus": "\U0001F4C1+",
    }
    return mapping.get(name, "\u2022")


def human_size(num_bytes: int) -> str:
    if num_bytes < 1024:
        return f"{num_bytes} B"
    if num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    if num_bytes < 1024 * 1024 * 1024:
        return f"{num_bytes / (1024 * 1024):.1f} MB"
    return f"{num_bytes / (1024 * 1024 * 1024):.1f} GB"


_path_size_cache: dict[str, tuple[float, int]] = {}


def path_size(path: Path) -> int:
    """计算文件或目录大小。对目录使用 mtime 缓存与 os.walk，避免重复深度扫描导致界面卡死。"""
    try:
        st = path.stat()
    except OSError:
        return 0
    if not path.is_dir():
        return st.st_size

    cache_key = str(path.resolve())
    cached = _path_size_cache.get(cache_key)
    if cached is not None and cached[0] == st.st_mtime:
        return cached[1]

    total = 0
    try:
        for root, _, files in os.walk(str(path)):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
    except OSError:
        pass

    _path_size_cache[cache_key] = (st.st_mtime, total)
    return total


def resolve_app_icon() -> QIcon:
    candidates = [
        PROJECT_ROOT / "icon_build" / "icon_1024.png",
        PROJECT_ROOT / "icon_build" / "icon_512.png",
        PROJECT_ROOT / "AppIcon.icns",
        Path("/Applications/Phone Transfer.app/Contents/Resources/AppIcon.icns"),
    ]
    icon = QIcon()
    for path in candidates:
        if path.exists():
            icon = QIcon(str(path))
            if not icon.isNull():
                return icon
    return icon


def picker_helper_path() -> Path | None:
    binary = PROJECT_ROOT / "bin" / "pick_items"
    source = PROJECT_ROOT / "pick_items.swift"
    if not source.is_file():
        return binary if binary.is_file() else None
    try:
        binary.parent.mkdir(parents=True, exist_ok=True)
        needs_build = (
            not binary.is_file()
            or binary.stat().st_mtime < source.stat().st_mtime
        )
        if needs_build:
            r = subprocess.run(
                ["swiftc", "-O", "-o", str(binary), str(source)],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if r.returncode != 0:
                return None
        return binary if binary.is_file() else None
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return binary if binary.is_file() else None


def _run_picker_process(executable: str, args: list[str]) -> tuple[int, str, str]:
    process = QProcess()
    process.start(executable, args)
    if not process.waitForStarted(5000):
        return 1, "", "picker failed to start"

    loop = QEventLoop()
    process.finished.connect(loop.quit)
    loop.exec()

    stdout = bytes(process.readAllStandardOutput()).decode("utf-8", errors="replace")
    stderr = bytes(process.readAllStandardError()).decode("utf-8", errors="replace")
    return process.exitCode(), stdout, stderr


def pick_files_and_folders(title: str = "选择要传输的内容") -> list[str]:
    if sys.platform == "darwin":
        helper = picker_helper_path()
        if helper is not None:
            code, stdout, _stderr = _run_picker_process(str(helper), [title])
            if code == 0:
                paths = [ln.strip() for ln in stdout.splitlines() if ln.strip()]
                if paths:
                    return paths

    dialog = QFileDialog()
    dialog.setWindowTitle(title)
    dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)
    dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
    if dialog.exec() != QFileDialog.DialogCode.Accepted:
        return []
    return [p for p in dialog.selectedFiles() if p]


def send_macos_notification(
    message: str,
    title: str = "Phone Transfer",
    subtitle: str = "",
    sound: bool = True,
) -> None:
    """调用 macOS 系统 Notification Center 异步发送原生横幅通知。"""
    if sys.platform != "darwin":
        return

    def _clean(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").strip()

    script = f'display notification "{_clean(message)}" with title "{_clean(title)}"'
    if subtitle:
        script += f' subtitle "{_clean(subtitle)}"'
    if sound:
        script += ' sound name "default"'
    try:
        subprocess.Popen(
            ["osascript", "-e", script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


