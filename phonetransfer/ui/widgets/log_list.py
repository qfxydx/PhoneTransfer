"""Log detail list and parser."""

from __future__ import annotations

from dataclasses import dataclass
import re

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


@dataclass
class ParsedLogEntry:
    kind: str
    title: str
    detail: str = ""


LOG_KIND_META: dict[str, tuple[str, str]] = {
    "device": ("#5aa3ec", "机"),
    "transfer": ("#9a7cf0", "传"),
    "success": ("#34c759", "✓"),
    "warning": ("#f5a623", "!"),
    "error": ("#e8685a", "×"),
    "progress": ("#5aa3ec", "…"),
    "info": ("#8e8e93", "·"),
}


def _parse_adb_push_summary(line: str) -> ParsedLogEntry:
    count_match = re.search(r"(\d+) files? pushed", line)
    speed_match = re.search(r"([\d.]+ [KMGT]?B/s)", line)
    count = count_match.group(1) if count_match else None
    speed = speed_match.group(1) if speed_match else ""
    if count:
        title = f"传输完成 · {count} 个文件"
        detail = f"速度 {speed}" if speed else ""
        return ParsedLogEntry("success", title, detail)
    return ParsedLogEntry("success", "传输完成", line)


def parse_log_line(text: str) -> ParsedLogEntry | None:
    t = text.strip()
    if not t:
        return None

    if re.match(r"已传输 \d+/\d+", t):
        return None

    if t.startswith("引擎就绪"):
        detail = t.split("·", 1)[1].strip() if "·" in t else ""
        return ParsedLogEntry("info", "引擎就绪", detail)

    if "正在检测设备" in t:
        return ParsedLogEntry("device", "正在检测设备")

    if t.startswith("已连接"):
        return ParsedLogEntry("success", "设备已连接", t[3:].strip())

    if "未检测到设备" in t:
        return ParsedLogEntry("warning", "未检测到设备")

    if "USB 调试" in t or "允许 USB 调试" in t:
        return ParsedLogEntry("warning", t)

    if "设备状态异常" in t:
        detail = t.split("：", 1)[1].strip() if "：" in t else ""
        return ParsedLogEntry("error", "设备状态异常", detail)

    if "设备检测失败" in t:
        return ParsedLogEntry("error", "设备检测失败")

    if t.startswith("已添加"):
        return ParsedLogEntry("info", t)

    if t.startswith("打开选择器失败"):
        return ParsedLogEntry("error", t)

    transfer_match = re.match(r"开始传输 (.+)", t)
    if transfer_match:
        return ParsedLogEntry("transfer", "开始传输", transfer_match.group(1).strip())

    item_match = re.match(r"\[(\d+)/(\d+)\] (.+)", t)
    if item_match:
        return ParsedLogEntry(
            "progress",
            f"传输第 {item_match.group(1)}/{item_match.group(2)} 项",
            item_match.group(3),
        )

    if t.startswith("同步 ") and "个文件" in t:
        return ParsedLogEntry("progress", t)

    if "批量解析完成" in t:
        return ParsedLogEntry("progress", t)

    if t.startswith("正在生成传输清单"):
        return ParsedLogEntry("progress", "正在生成传输清单")

    if "整包传输" in t:
        return ParsedLogEntry("progress", t)

    if "files pushed" in t or "file pushed" in t:
        return _parse_adb_push_summary(t)

    if "files pulled" in t or "file pulled" in t:
        count_match = re.search(r"(\d+) files? pulled", t)
        speed_match = re.search(r"([\d.]+ [KMGT]?B/s)", t)
        count = count_match.group(1) if count_match else None
        speed = speed_match.group(1) if speed_match else ""
        if count:
            return ParsedLogEntry(
                "success",
                f"拉取完成 · {count} 个文件",
                f"速度 {speed}" if speed else "",
            )
        return ParsedLogEntry("success", "拉取完成", t)

    if "已切换方向" in t:
        return ParsedLogEntry("info", t)

    if t.startswith("耗时 "):
        return ParsedLogEntry("success", t)

    if t.startswith("已发送"):
        return ParsedLogEntry("success", t)

    if "传输已取消" in t or "正在停止" in t:
        return ParsedLogEntry("warning", t)

    if "失败" in t or "超时" in t or t.startswith("无法"):
        return ParsedLogEntry("error", t)

    if "同名文件处理" in t:
        return ParsedLogEntry("info", t)

    if (
        t.startswith("覆盖同名")
        or t.startswith("重命名为")
        or t.startswith("同步到已有")
        or "检测到符号链接" in t
        or ("其中 " in t and "需复制" in t)
        or "改为逐文件传输" in t
    ):
        return ParsedLogEntry("info", t)

    if t.startswith("-rw") or t.startswith("total ") or "传输完成（校验" in t:
        return None

    if len(t) > 96:
        return ParsedLogEntry("info", "传输日志", t[:96] + "…")

    return ParsedLogEntry("info", t)


class LogDetailList(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("logDetail")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.scroll = QScrollArea()
        self.scroll.setObjectName("logDetailScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)

        self.container = QWidget()
        self.container.setObjectName("logDetailContainer")
        self.list_layout = QVBoxLayout(self.container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(0)
        self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll)

        self._rows: list[QFrame] = []
        self._empty_label: QLabel | None = None
        self._ensure_empty()

    def sync_lines(self, lines: list[str]) -> None:
        self.clear()
        for line in lines:
            self.append(line, auto_scroll=False)
        if not self._rows:
            self._ensure_empty()
        else:
            self._remove_empty()
        self._scroll_to_bottom()

    def append(self, text: str, *, auto_scroll: bool = True) -> None:
        entry = parse_log_line(text)
        if entry is None:
            return
        self._remove_empty()
        if self._rows:
            self._rows[-1].setProperty("last", False)
            self._rows[-1].style().unpolish(self._rows[-1])
            self._rows[-1].style().polish(self._rows[-1])
        row = self._make_row(entry)
        row.setProperty("last", True)
        self._rows.append(row)
        self.list_layout.addWidget(row)
        if auto_scroll:
            QTimer.singleShot(0, self._scroll_to_bottom)

    def clear(self) -> None:
        self._rows.clear()
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._empty_label = None

    def _ensure_empty(self) -> None:
        if self._rows or self._empty_label is not None:
            return
        self._empty_label = QLabel("暂无活动记录")
        self._empty_label.setObjectName("logEmpty")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.list_layout.addWidget(self._empty_label)

    def _remove_empty(self) -> None:
        if self._empty_label is None:
            return
        self.list_layout.removeWidget(self._empty_label)
        self._empty_label.deleteLater()
        self._empty_label = None

    def _scroll_to_bottom(self) -> None:
        bar = self.scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _make_row(self, entry: ParsedLogEntry) -> QFrame:
        color, glyph = LOG_KIND_META.get(entry.kind, LOG_KIND_META["info"])
        row = QFrame()
        row.setObjectName("logRow")
        h = QHBoxLayout(row)
        h.setContentsMargins(10, 8, 10, 8)
        h.setSpacing(10)

        icon = QLabel(glyph)
        icon.setFixedSize(24, 24)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(
            f"background: {color}; color: #ffffff; border-radius: 12px;"
            f"font-size: 11px; font-weight: 700;"
        )
        h.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        title = QLabel(entry.title)
        title.setObjectName("logRowTitle")
        title.setWordWrap(True)
        text_col.addWidget(title)
        if entry.detail:
            detail = QLabel(entry.detail)
            detail.setObjectName("logRowDetail")
            detail.setWordWrap(True)
            text_col.addWidget(detail)
        h.addLayout(text_col, 1)
        return row

