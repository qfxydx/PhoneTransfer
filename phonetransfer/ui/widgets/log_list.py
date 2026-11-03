"""Log detail list and parser."""

from __future__ import annotations

from phonetransfer.i18n import tr
from phonetransfer.log_kinds import catalog_log_kind

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
    "device": ("#5aa3ec", "▣"),
    "transfer": ("#9a7cf0", "↔"),
    "success": ("#34c759", "✓"),
    "warning": ("#f5a623", "!"),
    "error": ("#e8685a", "×"),
    "progress": ("#5aa3ec", "…"),
    "info": ("#8e8e93", "·"),
}


_ADB_SUMMARY = re.compile(
    r"(?:[^\n]+: )?(?P<count>\d+) files? (?P<verb>pushed|pulled)"
    r"(?:, (?:\d+ skipped\.?(?: [^\n]*)?|[\d.]+ [KMGT]?B/s(?: \([^\n]*\))?))?"
)


def _parse_adb_push_summary(line: str) -> ParsedLogEntry:
    """Compatibility helper re-exported by phone_transfer.py; keep raw detail."""
    count = re.search(r"(\d+) files? pushed", line)
    title = tr('传输完成 · {p0} 个文件', p0=count.group(1)) if count else tr('传输完成')
    return ParsedLogEntry("success", title, line)


def parse_log_line(text: str, *, kind: str | None = None) -> ParsedLogEntry | None:
    t = text.strip()
    if not t:
        return None
    if kind is not None:
        if kind not in LOG_KIND_META:
            raise ValueError(f"Unknown log kind: {kind}")
        return ParsedLogEntry(kind, text)
    # Legacy Signal(str) emitters are classified by stable catalog source IDs.
    # Resolve these before raw ADB formats so filenames/stderr cannot override
    # the outcome of the enclosing application message.
    catalog_kind = catalog_log_kind(t)
    if catalog_kind:
        return ParsedLogEntry(catalog_kind, text)
    # External ADB protocol prefixes and neutral symbols are language invariant.
    if t.startswith("adb: error:"):
        return ParsedLogEntry("error", text)
    if t.startswith("adb: warning:"):
        return ParsedLogEntry("warning", text)
    if t.startswith(("×", "❌")):
        return ParsedLogEntry("error", text)
    if t.startswith(("✓", "✅")):
        return ParsedLogEntry("success", text)
    if re.match(r"\[\d+/\d+\]", t):
        return ParsedLogEntry("progress", text)
    summary = _ADB_SUMMARY.fullmatch(t)
    if summary:
        if summary.group("verb") == "pushed":
            return _parse_adb_push_summary(text)
        count = summary.group("count")
        return ParsedLogEntry("success", tr('拉取完成 · {p0} 个文件', p0=count), text)
    return ParsedLogEntry("info", text)


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
        self.sync_entries([entry for line in lines if (entry := parse_log_line(line)) is not None])

    def sync_entries(self, entries: list[ParsedLogEntry]) -> None:
        self.clear()
        for entry in entries:
            self.append_entry(entry, auto_scroll=False)
        if not self._rows:
            self._ensure_empty()
        else:
            self._remove_empty()
        self._scroll_to_bottom()

    def append(self, text: str, *, auto_scroll: bool = True) -> None:
        entry = parse_log_line(text)
        if entry is None:
            return
        self.append_entry(entry, auto_scroll=auto_scroll)

    def append_entry(self, entry: ParsedLogEntry, *, auto_scroll: bool = True) -> None:
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
        self._empty_label = QLabel(tr('暂无活动记录'))
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
        row.setProperty("kind", entry.kind)
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
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setObjectName("logRowTitle")
        title.setWordWrap(True)
        text_col.addWidget(title)
        if entry.detail:
            detail = QLabel(entry.detail)
            detail.setTextFormat(Qt.TextFormat.PlainText)
            detail.setObjectName("logRowDetail")
            detail.setWordWrap(True)
            text_col.addWidget(detail)
        h.addLayout(text_col, 1)
        return row

