"""Transfer cards: SourceCard, DestinationCard, LocalDestinationCard, PhoneSourceCard."""

from __future__ import annotations

from pathlib import Path
import posixpath

from PySide6.QtCore import QPoint, QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QContextMenuEvent, QDragEnterEvent, QDropEvent, QKeyEvent, QResizeEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from phonetransfer.adb.file_ops import RemoteEntry, local_entry_time, sort_remote_entries
from phonetransfer.constants import (
    CARD_INNER_WIDTH,
    DEST_PRESETS,
    LOCAL_DEST_PRESETS,
    PHONE_CATEGORY_EXTENSIONS,
    PHONE_CATEGORY_PRESETS,
    PHONE_QUICK_PRESETS,
)
from phonetransfer.ui.dialogs.remote_file_dialogs import (
    DeleteConfirmDialog,
    NewFolderDialog,
    RenameDialog,
)
from phonetransfer.utils import (
    card_shadow,
    file_badge,
    human_size,
    make_mac_folder_plus_icon,
    path_size,
    sym,
)
from phonetransfer.workers.base import _UI, dispose_qthread_pair
from phonetransfer.workers.phone_list_worker import PhoneListWorker
from phonetransfer.workers.remote_op_worker import RemoteOpWorker

SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


class SourceCard(QFrame):
    paths_changed = Signal()
    apk_detected = Signal(list)
    preview_requested = Signal(str)
    install_requested = Signal(str)

    def __init__(self, symbol_font: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._symbol_font = symbol_font
        self._paths: list[str] = []
        self._selected_index: int = -1

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 14)
        outer.setSpacing(0)

        header = QWidget()
        header.setObjectName("cardHeader")
        header_row = QHBoxLayout(header)
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(0)

        header_spacer = QWidget()
        header_spacer.setFixedWidth(28)
        header_row.addWidget(header_spacer, 0, Qt.AlignmentFlag.AlignTop)

        header_l = QVBoxLayout()
        header_l.setContentsMargins(0, 0, 0, 0)
        header_l.setSpacing(4)
        header_l.setAlignment(Qt.AlignmentFlag.AlignCenter)

        eyebrow = QLabel("来源")
        eyebrow.setObjectName("eyebrow")
        eyebrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_l.addWidget(eyebrow)

        title = QLabel("这台电脑")
        title.setObjectName("sectionTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_l.addWidget(title)
        header_row.addLayout(header_l, 1)

        self.btn_refresh = QToolButton()
        self.btn_refresh.setObjectName("refreshBtn")
        self.btn_refresh.setText(sym("arrow.clockwise"))
        self.btn_refresh.setToolTip("刷新列表（按创建时间重新排序）")
        self.btn_refresh.setFixedSize(28, 28)
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.clicked.connect(self.refresh_paths)
        header_row.addWidget(self.btn_refresh, 0, Qt.AlignmentFlag.AlignTop)

        outer.addWidget(header)
        outer.addSpacing(16)

        self.stack = QVBoxLayout()
        self.stack.setSpacing(0)

        self.empty = QWidget()
        empty_l = QVBoxLayout(self.empty)
        empty_l.setContentsMargins(0, 8, 0, 0)
        empty_l.setSpacing(10)
        empty_l.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_box = QFrame()
        icon_box.setObjectName("emptyIconBox")
        icon_box.setFixedSize(64, 64)
        icon_box_l = QVBoxLayout(icon_box)
        icon_box_l.setContentsMargins(0, 0, 0, 0)
        icon = QLabel(sym("tray.and.arrow.up"))
        icon.setObjectName("emptySymbol")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_box_l.addWidget(icon)
        empty_l.addWidget(icon_box, 0, Qt.AlignmentFlag.AlignCenter)

        main = QLabel("拖入文件以传输")
        main.setObjectName("sectionSubtitle")
        main.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_l.addWidget(main)

        sub = QLabel("支持多选，可点击下方按钮")
        sub.setObjectName("emptyHint")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setWordWrap(True)
        sub.setMaximumWidth(CARD_INNER_WIDTH)
        empty_l.addWidget(sub)

        empty_l.addSpacing(8)
        self.btn_pick = QPushButton("选择文件…")
        self.btn_pick.setObjectName("pickBtn")
        self.btn_pick.setCursor(Qt.CursorShape.PointingHandCursor)
        empty_l.addWidget(self.btn_pick, 0, Qt.AlignmentFlag.AlignCenter)
        empty_l.addStretch(1)

        self.list_wrap = QWidget()
        list_outer = QVBoxLayout(self.list_wrap)
        list_outer.setContentsMargins(0, 4, 0, 0)
        list_outer.setSpacing(4)

        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("filterSearchEdit")
        self.search_edit.setPlaceholderText("搜索已选文件 (Esc 清空)…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._on_search_changed)
        list_outer.addWidget(self.search_edit)

        self.scroll = QScrollArea()
        self.scroll.setObjectName("fileScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.file_container = QWidget()
        self.file_container.setMaximumWidth(CARD_INNER_WIDTH)
        self.file_container.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Minimum,
        )
        self.file_layout = QVBoxLayout(self.file_container)
        self.file_layout.setContentsMargins(0, 0, 0, 0)
        self.file_layout.setSpacing(8)
        self.file_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.file_container)
        list_outer.addWidget(self.scroll, 1)

        self.list_wrap.setMinimumWidth(0)

        self.stack.addWidget(self.empty)
        self.stack.addWidget(self.list_wrap)
        outer.addLayout(self.stack, 1)

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 8, 0, 0)
        footer.setSpacing(8)
        self.summary = QLabel("")
        self.summary.setObjectName("summaryLabel")
        self.btn_clear = QPushButton("清空")
        self.btn_clear.setObjectName("clearBtn")
        self.btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear.clicked.connect(self.clear_paths)
        footer.addWidget(self.summary, 1)
        footer.addWidget(self.btn_clear, 0, Qt.AlignmentFlag.AlignRight)
        outer.addLayout(footer)

        card_shadow(self)
        self._sync_view()
        self._schedule_sync_list_width()

    def _target_inner_width(self) -> int:
        """Never exceed card inner width; viewport can be wrong before layout."""
        viewport_w = self.scroll.viewport().width()
        if viewport_w > 0:
            return min(viewport_w, CARD_INNER_WIDTH)
        return CARD_INNER_WIDTH

    def _schedule_sync_list_width(self) -> None:
        QTimer.singleShot(0, self._sync_list_width)

    def _sync_list_width(self) -> None:
        inner_w = self._target_inner_width()
        self.file_container.setFixedWidth(inner_w)
        sub = self.empty.findChild(QLabel, "emptyHint")
        if sub is not None:
            sub.setMaximumWidth(inner_w)
        for i in range(self.file_layout.count()):
            item = self.file_layout.itemAt(i)
            if not item or not item.widget():
                continue
            row = item.widget()
            if row.objectName() != "fileRow":
                continue
            row.setMaximumWidth(inner_w)
            row.setFixedWidth(inner_w)
            name_label = row.findChild(QLabel, "fileName")
            if name_label is not None:
                full_name = row.property("full_name") or name_label.toolTip()
                if full_name:
                    self._apply_row_name_elide(name_label, str(full_name))

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._sync_list_width()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._schedule_sync_list_width()

    def paths(self) -> list[str]:
        return list(self._paths)

    def _sort_paths_newest_first(self) -> None:
        self._paths.sort(key=lambda p: (-local_entry_time(Path(p)), Path(p).name.lower()))

    def set_paths(self, paths: list[str]) -> None:
        self._paths = [p for p in paths if Path(p).exists()]
        self._sort_paths_newest_first()
        self._rebuild_rows()
        self._sync_view()
        self._schedule_sync_list_width()
        self.paths_changed.emit()

    def _visible_paths(self) -> list[str]:
        q = self.search_edit.text().strip().lower()
        if not q:
            return list(self._paths)
        return [p for p in self._paths if q in Path(p).name.lower()]

    def _on_search_changed(self, _text: str) -> None:
        self._rebuild_rows()
        self._sync_view()
        self._schedule_sync_list_width()

    def select_index(self, index: int) -> None:
        vis = self._visible_paths()
        if not vis:
            self._selected_index = -1
            return
        index = max(0, min(len(vis) - 1, index))
        self._selected_index = index
        for i in range(self.file_layout.count()):
            item = self.file_layout.itemAt(i)
            if not item or not item.widget():
                continue
            row = item.widget()
            is_sel = (i == index)
            if row.property("selected") != is_sel:
                row.setProperty("selected", is_sel)
                row.style().unpolish(row)
                row.style().polish(row)
            if is_sel:
                self.scroll.ensureWidgetVisible(row)

    def selected_path(self) -> str | None:
        vis = self._visible_paths()
        if 0 <= self._selected_index < len(vis):
            return vis[self._selected_index]
        return None

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            if self.search_edit.text():
                self.search_edit.clear()
                event.accept()
                return
        elif event.key() == Qt.Key.Key_Space:
            target = self.selected_path()
            vis = self._visible_paths()
            if not target and vis:
                self.select_index(0)
                target = vis[0]
            if target:
                self.preview_requested.emit(target)
            event.accept()
            return
        elif event.key() == Qt.Key.Key_Up:
            self.select_index(self._selected_index - 1)
            event.accept()
            return
        elif event.key() == Qt.Key.Key_Down:
            self.select_index(self._selected_index + 1)
            event.accept()
            return
        super().keyPressEvent(event)

    def add_paths(self, paths: list[str]) -> int:
        added = 0
        for path in paths:
            resolved = str(Path(path).expanduser().resolve())
            if Path(resolved).exists() and resolved not in self._paths:
                self._paths.append(resolved)
                added += 1
        if added:
            self._sort_paths_newest_first()
            self._rebuild_rows()
            self._sync_view()
            self._schedule_sync_list_width()
            self.paths_changed.emit()
            self.select_index(0)

            apks = [
                str(Path(p).resolve())
                for p in paths
                if Path(p).suffix.lower() == ".apk" and Path(p).is_file()
            ]
            if apks:
                self.apk_detected.emit(apks)
        return added

    def remove_path(self, path: str) -> None:
        if path in self._paths:
            self._paths.remove(path)
            self._rebuild_rows()
            self._sync_view()
            self._schedule_sync_list_width()
            self.paths_changed.emit()

    def clear_paths(self) -> None:
        self.search_edit.blockSignals(True)
        self.search_edit.clear()
        self.search_edit.blockSignals(False)
        self._paths = []
        self._selected_index = -1
        self._rebuild_rows()
        self._sync_view()
        self._schedule_sync_list_width()
        self.paths_changed.emit()

    def refresh_paths(self) -> None:
        """Drop missing items and re-sort by creation time (newest first)."""
        before = list(self._paths)
        self._paths = [p for p in self._paths if Path(p).exists()]
        self._sort_paths_newest_first()
        if self._paths != before:
            self._rebuild_rows()
            self._sync_view()
            self._schedule_sync_list_width()
            self.paths_changed.emit()
        else:
            self._rebuild_rows()
            self._schedule_sync_list_width()

    def _sync_view(self) -> None:
        has = bool(self._paths)
        self.empty.setVisible(not has)
        self.list_wrap.setVisible(has)
        self.btn_clear.setVisible(has)
        if has:
            q = self.search_edit.text().strip().lower()
            if q:
                vis = self._visible_paths()
                matched_bytes = sum(path_size(Path(p)) for p in vis)
                self.summary.setText(f"匹配 {len(vis)}/{len(self._paths)} 项 · 共 {human_size(matched_bytes)}")
            else:
                total_bytes = sum(path_size(Path(p)) for p in self._paths)
                n = len(self._paths)
                self.summary.setText(f"{n} 个文件 · 共 {human_size(total_bytes)}")
        else:
            self.summary.setText("")

    def _rebuild_rows(self) -> None:
        while self.file_layout.count():
            item = self.file_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        vis = self._visible_paths()
        if not vis and self._paths:
            no_match = QLabel("无匹配文件 (按 Esc 重置)")
            no_match.setObjectName("emptyHint")
            no_match.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.file_layout.addWidget(no_match)
        else:
            for idx, path in enumerate(vis):
                self.file_layout.addWidget(self._make_row(path, idx))

        if vis:
            if self._selected_index < 0 or self._selected_index >= len(vis):
                self._selected_index = 0
            self.select_index(self._selected_index)
        else:
            self._selected_index = -1

    def _make_row(self, path: str, idx: int) -> QWidget:
        p = Path(path)
        inner_w = CARD_INNER_WIDTH
        row = QFrame()
        row.setObjectName("fileRow")
        row.setMaximumWidth(inner_w)
        row.setFixedWidth(inner_w)
        row.setCursor(Qt.CursorShape.PointingHandCursor)
        row.setProperty("selected", idx == self._selected_index)
        full_name = p.name + ("/" if p.is_dir() else "")
        row.setProperty("full_name", full_name)
        h = QHBoxLayout(row)
        h.setContentsMargins(10, 8, 8, 8)
        h.setSpacing(8)

        badge_label, badge_color = file_badge(p)
        badge = QLabel(badge_label)
        badge.setObjectName("fileBadge")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFixedSize(30, 30)
        badge.setStyleSheet(
            f"background: {badge_color}; border-radius: 7px; color: #ffffff;"
            f"font-size: 11px; font-weight: 600;"
        )
        h.addWidget(badge)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        name = QLabel()
        name.setObjectName("fileName")
        name.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        name.setMinimumWidth(0)
        # 为右侧可能的「安装」按钮预留宽度
        is_apk = p.suffix.lower() == ".apk" and not p.is_dir()
        name_max_w = max(40, inner_w - (140 if is_apk else 90))
        name.setMaximumWidth(name_max_w)
        size = QLabel(human_size(path_size(p)))
        size.setObjectName("fileSize")
        text_col.addWidget(name)
        text_col.addWidget(size)
        h.addLayout(text_col, 1)

        if is_apk:
            btn_install = QPushButton("安装")
            btn_install.setObjectName("installRowBtn")
            btn_install.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_install.setToolTip("直接将此 APK 安装到手机")
            btn_install.clicked.connect(lambda _=False, apk=path: self.install_requested.emit(apk))
            h.addWidget(btn_install)

        rm = QPushButton("\u00d7")
        rm.setObjectName("removeBtn")
        rm.setFixedSize(24, 24)
        rm.setCursor(Qt.CursorShape.PointingHandCursor)
        rm.setToolTip("移除")
        rm.clicked.connect(lambda _=False, pt=path: self.remove_path(pt))
        h.addWidget(rm)

        # 点击选择该行；双击触发 Quick Look 预览
        row.mousePressEvent = lambda _ev, i=idx: (self.select_index(i), self.setFocus())
        row.mouseDoubleClickEvent = lambda _ev, pt=path: self.preview_requested.emit(pt)

        self._apply_row_name_elide(name, full_name)
        return row

    def _apply_row_name_elide(self, label: QLabel, full_name: str) -> None:
        inner_w = self._target_inner_width()
        text_w = max(40, inner_w - 90)
        label.setMaximumWidth(text_w)
        label.setText(
            label.fontMetrics().elidedText(
                full_name, Qt.TextElideMode.ElideMiddle, text_w
            )
        )
        label.setToolTip(full_name)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setObjectName("dropHighlight")
            self.style().unpolish(self)
            self.style().polish(self)

    def dragLeaveEvent(self, event) -> None:
        self.setObjectName("card")
        self.style().unpolish(self)
        self.style().polish(self)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        self.setObjectName("card")
        self.style().unpolish(self)
        self.style().polish(self)
        urls = [u.toLocalFile() for u in event.mimeData().urls() if u.toLocalFile()]
        self.add_paths(urls)
        event.acceptProposedAction()


class DestinationCard(QFrame):
    destination_changed = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("card")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 14)
        outer.setSpacing(0)

        header = QWidget()
        header.setObjectName("cardHeader")
        header_l = QVBoxLayout(header)
        header_l.setContentsMargins(0, 0, 0, 0)
        header_l.setSpacing(4)
        header_l.setAlignment(Qt.AlignmentFlag.AlignCenter)

        eyebrow = QLabel("目标")
        eyebrow.setObjectName("eyebrow")
        eyebrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_l.addWidget(eyebrow)

        title = QLabel("手机存储")
        title.setObjectName("sectionTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_l.addWidget(title)

        outer.addWidget(header)
        outer.addSpacing(16)

        lab = QLabel("保存位置")
        lab.setObjectName("sectionLabel")
        outer.addWidget(lab)

        dest_content = QWidget()
        dest_content.setFixedWidth(CARD_INNER_WIDTH)
        dest_content_l = QVBoxLayout(dest_content)
        dest_content_l.setContentsMargins(0, 8, 0, 0)
        dest_content_l.setSpacing(8)

        segment_frame = QFrame()
        segment_frame.setObjectName("segmentControl")
        segment_grid = QGridLayout(segment_frame)
        segment_grid.setContentsMargins(4, 4, 4, 4)
        segment_grid.setSpacing(4)

        self.preset_group = QButtonGroup(self)
        self.preset_group.setExclusive(True)
        self.preset_buttons: list[QPushButton] = []
        segment_labels = [name for name, _ in DEST_PRESETS] + ["自定义"]
        for i, label in enumerate(segment_labels):
            btn = QPushButton(label)
            btn.setObjectName("quickTagBtn")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(26)
            if i < len(DEST_PRESETS):
                btn.setProperty("dest_path", DEST_PRESETS[i][1])
            self.preset_group.addButton(btn, i)
            row = i // 3
            col = i % 3
            segment_grid.addWidget(btn, row, col)
            self.preset_buttons.append(btn)

        dest_content_l.addWidget(segment_frame)

        self.custom_wrap = QWidget()
        custom_l = QVBoxLayout(self.custom_wrap)
        custom_l.setContentsMargins(0, 0, 0, 0)
        custom_l.setSpacing(0)
        self.dest_edit = QLineEdit("/sdcard/Download")
        self.dest_edit.setObjectName("pathEdit")
        self.dest_edit.setPlaceholderText("/sdcard/…")
        self.dest_edit.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.dest_edit.setMinimumWidth(0)
        custom_l.addWidget(self.dest_edit)
        self.custom_wrap.setVisible(False)
        dest_content_l.addWidget(self.custom_wrap)

        outer.addWidget(dest_content)

        outer.addStretch(1)

        self._last_valid_space: str | None = None
        self._spinner_frame = 0
        self._spinner_timer = QTimer(self)
        self._spinner_timer.setInterval(80)
        self._spinner_timer.timeout.connect(self._step_spinner)

        self.space_wrap = QWidget()
        space_l = QHBoxLayout(self.space_wrap)
        space_l.setContentsMargins(0, 0, 0, 0)
        space_l.setSpacing(6)
        space_l.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.space_spinner = QLabel("")
        self.space_spinner.setObjectName("spaceSpinner")
        self.space_spinner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.space_spinner.setVisible(False)

        self.space_label = QLabel("可用 —")
        self.space_label.setObjectName("spaceLabel")
        self.space_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        space_l.addWidget(self.space_spinner)
        space_l.addWidget(self.space_label)
        outer.addWidget(self.space_wrap, 0, Qt.AlignmentFlag.AlignHCenter)

        self.preset_buttons[0].setChecked(True)
        self.preset_group.idClicked.connect(self._on_preset)
        self.dest_edit.textChanged.connect(self._emit_dest)

        card_shadow(self)

    def _step_spinner(self) -> None:
        self._spinner_frame = (self._spinner_frame + 1) % len(SPINNER_FRAMES)
        self.space_spinner.setText(SPINNER_FRAMES[self._spinner_frame])

    def set_storage_busy(self, busy: bool) -> None:
        if busy:
            if not self._spinner_timer.isActive():
                self._spinner_frame = 0
                self.space_spinner.setText(SPINNER_FRAMES[0])
                self.space_spinner.setVisible(True)
                self._spinner_timer.start()
            if self._last_valid_space:
                self.space_label.setText(f"可用 {self._last_valid_space}")
                self.space_wrap.setToolTip("正在重新检测可用空间…")
            else:
                self.space_label.setText("正在检测可用空间…")
                self.space_wrap.setToolTip("正在检测可用空间…")
        else:
            self._spinner_timer.stop()
            self.space_spinner.setVisible(False)
            self.space_wrap.setToolTip("")

    def _on_preset(self, _id: int) -> None:
        is_custom = self.preset_buttons[-1].isChecked()
        self.custom_wrap.setVisible(is_custom)
        if not is_custom:
            btn = self.preset_group.checkedButton()
            if btn and btn.property("dest_path"):
                self.dest_edit.setText(str(btn.property("dest_path")))
        self._emit_dest()

    def destination(self) -> str:
        if self.preset_buttons[-1].isChecked():
            return self.dest_edit.text().strip()
        btn = self.preset_group.checkedButton()
        if btn and btn.property("dest_path"):
            return str(btn.property("dest_path"))
        return "/sdcard/Download"

    def set_available_space(self, text: str) -> None:
        self.set_storage_busy(False)
        clean = text.strip() if text else ""
        if clean and clean not in ("—", "-", ""):
            self._last_valid_space = clean
            self.space_label.setText(f"可用 {clean}")
        else:
            if self._last_valid_space:
                self.space_label.setText(f"可用 {self._last_valid_space}")
            else:
                self.space_label.setText("可用 —")

    def reset_available_space(self) -> None:
        self._last_valid_space = None
        self.set_storage_busy(False)
        self.space_label.setText("可用 —")

    def _emit_dest(self) -> None:
        self.destination_changed.emit(self.destination())


class LocalDestinationCard(QFrame):
    destination_changed = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("card")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 14)
        outer.setSpacing(0)

        header = QWidget()
        header_l = QVBoxLayout(header)
        header_l.setContentsMargins(0, 0, 0, 0)
        header_l.setSpacing(4)
        header_l.setAlignment(Qt.AlignmentFlag.AlignCenter)
        eyebrow = QLabel("目标")
        eyebrow.setObjectName("eyebrow")
        eyebrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_l.addWidget(eyebrow)
        title = QLabel("这台电脑")
        title.setObjectName("sectionTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_l.addWidget(title)
        outer.addWidget(header)
        outer.addSpacing(16)

        lab = QLabel("保存位置")
        lab.setObjectName("sectionLabel")
        outer.addWidget(lab)

        dest_content = QWidget()
        dest_content.setFixedWidth(CARD_INNER_WIDTH)
        dest_content_l = QVBoxLayout(dest_content)
        dest_content_l.setContentsMargins(0, 8, 0, 0)
        dest_content_l.setSpacing(8)

        segment_frame = QFrame()
        segment_frame.setObjectName("segmentControl")
        segment_row = QHBoxLayout(segment_frame)
        segment_row.setContentsMargins(2, 2, 2, 2)
        segment_row.setSpacing(0)

        self.preset_group = QButtonGroup(self)
        self.preset_group.setExclusive(True)
        self.preset_buttons: list[QPushButton] = []
        segment_labels = [name for name, _ in LOCAL_DEST_PRESETS] + ["自定义"]
        for i, label in enumerate(segment_labels):
            btn = QPushButton(label)
            btn.setObjectName("segmentBtn")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
            )
            if i < len(LOCAL_DEST_PRESETS):
                btn.setProperty("dest_path", LOCAL_DEST_PRESETS[i][1])
            self.preset_group.addButton(btn, i)
            segment_row.addWidget(btn, 1)
            self.preset_buttons.append(btn)
        dest_content_l.addWidget(segment_frame)

        self.custom_wrap = QWidget()
        custom_l = QVBoxLayout(self.custom_wrap)
        custom_l.setContentsMargins(0, 0, 0, 0)
        self.dest_edit = QLineEdit(str(Path.home() / "Downloads"))
        self.dest_edit.setObjectName("pathEdit")
        self.dest_edit.setPlaceholderText("/Users/…")
        custom_l.addWidget(self.dest_edit)
        self.custom_wrap.setVisible(False)
        dest_content_l.addWidget(self.custom_wrap)
        outer.addWidget(dest_content)
        outer.addStretch(1)

        self._last_valid_space: str | None = None
        self._spinner_frame = 0
        self._spinner_timer = QTimer(self)
        self._spinner_timer.setInterval(80)
        self._spinner_timer.timeout.connect(self._step_spinner)

        self.space_wrap = QWidget()
        space_l = QHBoxLayout(self.space_wrap)
        space_l.setContentsMargins(0, 0, 0, 0)
        space_l.setSpacing(6)
        space_l.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.space_spinner = QLabel("")
        self.space_spinner.setObjectName("spaceSpinner")
        self.space_spinner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.space_spinner.setVisible(False)

        self.space_label = QLabel("可用 —")
        self.space_label.setObjectName("spaceLabel")
        self.space_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        space_l.addWidget(self.space_spinner)
        space_l.addWidget(self.space_label)
        outer.addWidget(self.space_wrap, 0, Qt.AlignmentFlag.AlignHCenter)

        self.preset_buttons[0].setChecked(True)
        self.preset_group.idClicked.connect(self._on_preset)
        self.dest_edit.textChanged.connect(self._emit_dest)
        card_shadow(self)

    def _step_spinner(self) -> None:
        self._spinner_frame = (self._spinner_frame + 1) % len(SPINNER_FRAMES)
        self.space_spinner.setText(SPINNER_FRAMES[self._spinner_frame])

    def set_storage_busy(self, busy: bool) -> None:
        if busy:
            if not self._spinner_timer.isActive():
                self._spinner_frame = 0
                self.space_spinner.setText(SPINNER_FRAMES[0])
                self.space_spinner.setVisible(True)
                self._spinner_timer.start()
            if self._last_valid_space:
                self.space_label.setText(f"可用 {self._last_valid_space}")
                self.space_wrap.setToolTip("正在重新检测可用空间…")
            else:
                self.space_label.setText("正在检测可用空间…")
                self.space_wrap.setToolTip("正在检测可用空间…")
        else:
            self._spinner_timer.stop()
            self.space_spinner.setVisible(False)
            self.space_wrap.setToolTip("")

    def _on_preset(self, _id: int) -> None:
        is_custom = self.preset_buttons[-1].isChecked()
        self.custom_wrap.setVisible(is_custom)
        if not is_custom:
            btn = self.preset_group.checkedButton()
            if btn and btn.property("dest_path"):
                self.dest_edit.setText(str(btn.property("dest_path")))
        self._emit_dest()

    def destination(self) -> str:
        if self.preset_buttons[-1].isChecked():
            return self.dest_edit.text().strip()
        btn = self.preset_group.checkedButton()
        if btn and btn.property("dest_path"):
            return str(btn.property("dest_path"))
        return str(Path.home() / "Downloads")

    def set_available_space(self, text: str) -> None:
        self.set_storage_busy(False)
        clean = text.strip() if text else ""
        if clean and clean not in ("—", "-", ""):
            self._last_valid_space = clean
            self.space_label.setText(f"可用 {clean}")
        else:
            if self._last_valid_space:
                self.space_label.setText(f"可用 {self._last_valid_space}")
            else:
                self.space_label.setText("可用 —")

    def reset_available_space(self) -> None:
        self._last_valid_space = None
        self.set_storage_busy(False)
        self.space_label.setText("可用 —")

    def _emit_dest(self) -> None:
        self.destination_changed.emit(self.destination())


class BrowseEntryRow(QFrame):
    checked_changed = Signal(str, bool)
    open_requested = Signal(str)
    row_clicked = Signal(str)
    row_double_clicked = Signal(str)
    rename_requested = Signal(str)
    delete_requested = Signal(str)
    preview_requested = Signal(str, int)

    def __init__(
        self, entry: RemoteEntry, checked: bool, inner_w: int, parent=None
    ) -> None:
        super().__init__(parent)
        self._entry = entry
        self.setObjectName("fileRow")
        self.setFixedWidth(inner_w)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        h = QHBoxLayout(self)
        h.setContentsMargins(6, 5, 4, 5)
        h.setSpacing(6)

        self.chk = QCheckBox()
        self.chk.setObjectName("browseCheck")
        self.chk.setChecked(checked)
        self.chk.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk.toggled.connect(self._on_check)
        h.addWidget(self.chk)

        badge_label, badge_color = (
            ("DIR", "#98989d") if entry.is_dir else file_badge(Path(entry.name))
        )
        badge = QLabel(badge_label)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFixedSize(28, 28)
        badge.setStyleSheet(
            f"background: {badge_color}; border-radius: 7px; color: #fff;"
            f"font-size: 10px; font-weight: 600;"
        )
        h.addWidget(badge)

        text_col = QVBoxLayout()
        text_col.setSpacing(1)
        name = QLabel(entry.name)
        name.setObjectName("fileName")
        size = QLabel("文件夹" if entry.is_dir else human_size(entry.size))
        size.setObjectName("fileSize")
        text_col.addWidget(name)
        text_col.addWidget(size)
        h.addLayout(text_col, 1)

        if entry.is_dir:
            btn_open = QToolButton()
            btn_open.setObjectName("navOpenBtn")
            btn_open.setText(sym("chevron.right"))
            btn_open.setFixedSize(26, 26)
            btn_open.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_open.setToolTip("进入文件夹")
            btn_open.clicked.connect(
                lambda _checked=False, p=entry.path: self.open_requested.emit(p)
            )
            h.addWidget(btn_open)

        self.btn_more = QToolButton()
        self.btn_more.setObjectName("navActionBtn")
        self.btn_more.setText("···")
        self.btn_more.setFixedSize(24, 24)
        self.btn_more.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_more.setToolTip("更多操作")
        self.btn_more.clicked.connect(self._show_context_menu_from_btn)
        h.addWidget(self.btn_more)

    def mousePressEvent(self, event) -> None:
        super().mousePressEvent(event)
        self.row_clicked.emit(self._entry.path)

    def mouseDoubleClickEvent(self, event) -> None:
        super().mouseDoubleClickEvent(event)
        self.row_double_clicked.emit(self._entry.path)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        self._show_context_menu(event.globalPos())

    def _show_context_menu_from_btn(self) -> None:
        pos = self.btn_more.mapToGlobal(QPoint(0, self.btn_more.height()))
        self._show_context_menu(pos)

    def _show_context_menu(self, global_pos: QPoint) -> None:
        self.row_clicked.emit(self._entry.path)
        menu = QMenu(self)
        if not self._entry.is_dir:
            act_preview = menu.addAction("空格预览")
            act_preview.triggered.connect(
                lambda: self.preview_requested.emit(self._entry.path, self._entry.size)
            )
        else:
            act_open = menu.addAction("进入文件夹")
            act_open.triggered.connect(lambda: self.open_requested.emit(self._entry.path))

        menu.addSeparator()
        act_rename = menu.addAction("重命名…")
        act_rename.triggered.connect(lambda: self.rename_requested.emit(self._entry.path))

        act_del = menu.addAction("从手机删除…")
        act_del.triggered.connect(lambda: self.delete_requested.emit(self._entry.path))

        menu.exec(global_pos)

    def _on_check(self, checked: bool) -> None:
        self.checked_changed.emit(self._entry.path, checked)


class PhoneSourceCard(QFrame):
    paths_changed = Signal()
    browse_dir_changed = Signal(str)
    preview_requested = Signal(str, int)
    operation_started = Signal(str)
    operation_finished = Signal(bool, str, str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._paths: list[str] = []
        self._path_is_dir: dict[str, bool] = {}
        self._browse_dir = PHONE_QUICK_PRESETS[0][1]
        self._entries: list[RemoteEntry] = []
        self._filter_category = "all"
        self._visible_entries: list[RemoteEntry] = []
        self._selected_index: int = -1
        self._list_token = 0
        self._files_loading = False
        self._list_thread: QThread | None = None
        self._list_worker: PhoneListWorker | None = None
        self._op_thread: QThread | None = None
        self._op_worker: RemoteOpWorker | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 14)
        outer.setSpacing(0)

        header = QWidget()
        header.setObjectName("cardHeader")
        header_row = QHBoxLayout(header)
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(0)

        header_spacer = QWidget()
        header_spacer.setFixedWidth(28)
        header_row.addWidget(header_spacer, 0, Qt.AlignmentFlag.AlignTop)

        header_l = QVBoxLayout()
        header_l.setContentsMargins(0, 0, 0, 0)
        header_l.setSpacing(4)
        header_l.setAlignment(Qt.AlignmentFlag.AlignCenter)
        eyebrow = QLabel("来源")
        eyebrow.setObjectName("eyebrow")
        eyebrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_l.addWidget(eyebrow)
        title = QLabel("手机")
        title.setObjectName("sectionTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_l.addWidget(title)
        header_row.addLayout(header_l, 1)

        self.btn_refresh = QToolButton()
        self.btn_refresh.setObjectName("refreshBtn")
        self.btn_refresh.setText(sym("arrow.clockwise"))
        self.btn_refresh.setToolTip("刷新列表")
        self.btn_refresh.setFixedSize(28, 28)
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.clicked.connect(self.reload_listing)
        header_row.addWidget(self.btn_refresh, 0, Qt.AlignmentFlag.AlignTop)

        outer.addWidget(header)
        outer.addSpacing(8)

        lab = QLabel("快捷目录")
        lab.setObjectName("sectionLabel")
        outer.addWidget(lab)

        presets_grid_frame = QFrame()
        presets_grid_frame.setObjectName("quickPresetsGrid")
        presets_grid = QGridLayout(presets_grid_frame)
        presets_grid.setContentsMargins(0, 4, 0, 4)
        presets_grid.setSpacing(4)

        self.preset_group = QButtonGroup(self)
        self.preset_group.setExclusive(True)
        self.preset_buttons: list[QPushButton] = []
        for i, (label, path) in enumerate(PHONE_QUICK_PRESETS):
            btn = QPushButton(label)
            btn.setObjectName("quickTagBtn")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(24)
            btn.setProperty("browse_path", path)
            self.preset_group.addButton(btn, i)
            row = i // 3
            col = i % 3
            presets_grid.addWidget(btn, row, col)
            self.preset_buttons.append(btn)
            btn.clicked.connect(
                lambda _checked=False, p=path: self._navigate_to(p)
            )
        self.preset_buttons[0].setChecked(True)
        outer.addWidget(presets_grid_frame)
        outer.addSpacing(6)

        nav_row = QHBoxLayout()
        nav_row.setSpacing(4)
        self.btn_back = QToolButton()
        self.btn_back.setObjectName("navBackBtn")
        self.btn_back.setText(sym("chevron.left"))
        self.btn_back.setFixedSize(26, 26)
        self.btn_back.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_back.setToolTip("返回上一级")
        self.btn_back.clicked.connect(self._navigate_up)
        nav_row.addWidget(self.btn_back)

        self.path_label = QLabel("")
        self.path_label.setObjectName("caption")
        self.path_label.setWordWrap(False)
        nav_row.addWidget(self.path_label, 1)

        self.btn_mkdir = QToolButton()
        self.btn_mkdir.setObjectName("navActionBtn")
        self.btn_mkdir.setIcon(make_mac_folder_plus_icon())
        self.btn_mkdir.setIconSize(QSize(18, 18))
        self.btn_mkdir.setFixedSize(26, 26)
        self.btn_mkdir.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_mkdir.setToolTip("在当前目录新建文件夹")
        self.btn_mkdir.clicked.connect(self._prompt_new_folder)
        nav_row.addWidget(self.btn_mkdir)

        self.btn_delete = QToolButton()
        self.btn_delete.setObjectName("navActionBtn")
        self.btn_delete.setText(sym("trash"))
        self.btn_delete.setFixedSize(26, 26)
        self.btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_delete.setToolTip("删除勾选的项目")
        self.btn_delete.setEnabled(False)
        self.btn_delete.clicked.connect(self._prompt_delete_checked)
        nav_row.addWidget(self.btn_delete)

        outer.addLayout(nav_row)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)
        filter_row.setContentsMargins(0, 4, 0, 4)

        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("filterSearchEdit")
        self.search_edit.setPlaceholderText("搜索文件… (Esc 清空)")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._on_filter_changed)
        filter_row.addWidget(self.search_edit, 1)

        self.btn_category = QPushButton("全部 ▾")
        self.btn_category.setObjectName("filterCategoryBtn")
        self.btn_category.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_category.setFixedWidth(72)
        self.btn_category.clicked.connect(self._popup_category_menu)
        filter_row.addWidget(self.btn_category)

        outer.addLayout(filter_row)

        self.browse_scroll = QScrollArea()
        self.browse_scroll.setObjectName("fileScroll")
        self.browse_scroll.setWidgetResizable(True)
        self.browse_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.browse_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.browse_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.browse_scroll.setMinimumHeight(130)
        self.browse_container = QWidget()
        self.browse_layout = QVBoxLayout(self.browse_container)
        self.browse_layout.setContentsMargins(0, 0, 0, 0)
        self.browse_layout.setSpacing(4)
        self.browse_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.browse_scroll.setWidget(self.browse_container)
        outer.addWidget(self.browse_scroll, 1)

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 8, 0, 0)
        self.summary = QLabel("勾选需要传输的文件或文件夹")
        self.summary.setObjectName("summaryLabel")
        self.summary.setWordWrap(True)
        self.btn_clear = QPushButton("清空")
        self.btn_clear.setObjectName("clearBtn")
        self.btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear.clicked.connect(self.clear_paths)
        footer.addWidget(self.summary, 1)
        footer.addWidget(self.btn_clear)
        outer.addLayout(footer)

        card_shadow(self)
        self._update_nav()
        self._sync_view()

    def paths(self) -> list[str]:
        return list(self._paths)

    def _popup_category_menu(self) -> None:
        menu = QMenu(self)
        for cat_id, label in PHONE_CATEGORY_PRESETS:
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(self._filter_category == cat_id)
            action.triggered.connect(lambda _checked=False, c=cat_id: self._set_category(c))
        menu.exec(self.btn_category.mapToGlobal(QPoint(0, self.btn_category.height() + 2)))

    def _set_category(self, cat_id: str) -> None:
        if self._filter_category == cat_id:
            return
        self._filter_category = cat_id
        label = dict(PHONE_CATEGORY_PRESETS).get(cat_id, "全部")
        self.btn_category.setText(f"{label} ▾")
        self.btn_category.setProperty("active", cat_id != "all")
        self.btn_category.style().unpolish(self.btn_category)
        self.btn_category.style().polish(self.btn_category)
        self._rebuild_browse_rows()
        self._sync_view()

    def _on_filter_changed(self, _text: str = "") -> None:
        self._rebuild_browse_rows()
        self._sync_view()

    def clear_filter(self) -> None:
        has_filter = bool(self.search_edit.text()) or self._filter_category != "all"
        if not has_filter:
            return
        self.search_edit.blockSignals(True)
        self.search_edit.clear()
        self.search_edit.blockSignals(False)
        self._filter_category = "all"
        self.btn_category.setText("全部 ▾")
        self.btn_category.setProperty("active", False)
        self.btn_category.style().unpolish(self.btn_category)
        self.btn_category.style().polish(self.btn_category)
        self._rebuild_browse_rows()
        self._sync_view()

    def _get_filtered_entries(self) -> list[RemoteEntry]:
        q = self.search_edit.text().strip().lower()
        cat = self._filter_category
        exts = PHONE_CATEGORY_EXTENSIONS.get(cat)

        res: list[RemoteEntry] = []
        for entry in self._entries:
            if exts is not None:
                if entry.is_dir:
                    continue
                ext = posixpath.splitext(entry.name)[1].lower()
                if ext not in exts:
                    continue
            if q and q not in entry.name.lower():
                continue
            res.append(entry)
        return res

    def select_index(self, index: int) -> None:
        if not self._visible_entries:
            self._selected_index = -1
            return
        index = max(0, min(len(self._visible_entries) - 1, index))
        self._selected_index = index
        row_idx = 0
        for i in range(self.browse_layout.count()):
            item = self.browse_layout.itemAt(i)
            if not item or not item.widget():
                continue
            row = item.widget()
            if row.objectName() != "fileRow":
                continue
            is_sel = (row_idx == index)
            if row.property("selected") != is_sel:
                row.setProperty("selected", is_sel)
                row.style().unpolish(row)
                row.style().polish(row)
            if is_sel:
                self.browse_scroll.ensureWidgetVisible(row)
            row_idx += 1

    def selected_entry(self) -> RemoteEntry | None:
        if 0 <= self._selected_index < len(self._visible_entries):
            return self._visible_entries[self._selected_index]
        return None

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            if self.search_edit.text() or self._filter_category != "all":
                self.clear_filter()
                event.accept()
                return
        elif event.key() == Qt.Key.Key_Space:
            entry = self.selected_entry()
            if not entry and self._visible_entries:
                self.select_index(0)
                entry = self._visible_entries[0]
            if entry:
                if entry.is_dir:
                    self._navigate_to(entry.path)
                else:
                    self.preview_requested.emit(entry.path, entry.size)
            event.accept()
            return
        elif event.key() == Qt.Key.Key_Up:
            self.select_index(self._selected_index - 1)
            event.accept()
            return
        elif event.key() == Qt.Key.Key_Down:
            self.select_index(self._selected_index + 1)
            event.accept()
            return
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            entry = self.selected_entry()
            if entry and entry.is_dir:
                self._navigate_to(entry.path)
                event.accept()
                return
        super().keyPressEvent(event)

    def clear_paths(self) -> None:
        self._paths = []
        self._path_is_dir = {}
        self._sync_view()
        self._rebuild_browse_rows()
        self.paths_changed.emit()

    def set_checked(self, path: str, checked: bool, *, is_dir: bool) -> None:
        if checked:
            if path not in self._paths:
                self._paths.append(path)
            self._path_is_dir[path] = is_dir
        else:
            if path in self._paths:
                self._paths.remove(path)
            self._path_is_dir.pop(path, None)
        self._sync_view()
        self.paths_changed.emit()

    def _parent_dir(self) -> str | None:
        current = self._browse_dir.rstrip("/")
        parent = posixpath.dirname(current)
        if not parent or parent == current:
            return None
        if not parent.startswith("/sdcard"):
            return None
        return parent

    def _navigate_to(self, path: str) -> None:
        target = str(path).rstrip("/")
        if not target:
            return
        self.search_edit.blockSignals(True)
        self.search_edit.clear()
        self.search_edit.blockSignals(False)
        self._filter_category = "all"
        self.btn_category.setText("全部 ▾")
        self.btn_category.setProperty("active", False)
        self.btn_category.style().unpolish(self.btn_category)
        self.btn_category.style().polish(self.btn_category)

        changed = target != self._browse_dir.rstrip("/")
        self._browse_dir = target
        if changed:
            self.browse_dir_changed.emit(self._browse_dir)
        self._update_nav()
        self.reload_listing()

    def _navigate_up(self) -> None:
        parent = self._parent_dir()
        if parent:
            self._navigate_to(parent)

    def _display_name_for_dir(self, remote_dir: str) -> str:
        current = remote_dir.rstrip("/")
        for label, path in PHONE_QUICK_PRESETS:
            if current == path.rstrip("/"):
                return label
        for label, path in DEST_PRESETS:
            if current == path.rstrip("/"):
                return label
        return posixpath.basename(current) or remote_dir

    def _update_nav(self) -> None:
        parent = self._parent_dir()
        self.btn_back.setEnabled(parent is not None)
        name = self._display_name_for_dir(self._browse_dir)
        if self._files_loading and self._entries:
            self.path_label.setText(f"{name} · 加载文件中…")
        elif self._files_loading:
            self.path_label.setText(f"{name} · 加载中…")
        else:
            self.path_label.setText(name)
        self.path_label.setToolTip(self._browse_dir)
        self._sync_preset_button()

    def _sync_preset_button(self) -> None:
        current = self._browse_dir.rstrip("/")
        match = -1
        for i, (_, path) in enumerate(PHONE_QUICK_PRESETS):
            root = path.rstrip("/")
            if current == root or current.startswith(root + "/"):
                if match < 0 or len(root) > len(PHONE_QUICK_PRESETS[match][1].rstrip("/")):
                    match = i
        self.preset_group.blockSignals(True)
        for i, btn in enumerate(self.preset_buttons):
            btn.blockSignals(True)
            btn.setChecked(i == match)
            btn.blockSignals(False)
        self.preset_group.blockSignals(False)

    def _prompt_new_folder(self) -> None:
        current_name = self._display_name_for_dir(self._browse_dir)
        dlg = NewFolderDialog(self, current_name)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            folder_name = dlg.folder_name()
            if folder_name:
                target_path = posixpath.join(self._browse_dir, folder_name)
                self._run_remote_op("mkdir", [target_path])

    def _prompt_rename(self, old_path: str) -> None:
        current_name = posixpath.basename(old_path.rstrip("/"))
        dlg = RenameDialog(self, current_name)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_name = dlg.new_name()
            if new_name and new_name != current_name:
                parent_dir = posixpath.dirname(old_path.rstrip("/"))
                new_path = posixpath.join(parent_dir, new_name)
                self._run_remote_op("rename", [old_path, new_path])

    def _prompt_delete_checked(self) -> None:
        if not self._paths:
            return
        self._prompt_delete_paths(list(self._paths))

    def _prompt_delete_single(self, path: str) -> None:
        self._prompt_delete_paths([path])

    def _prompt_delete_paths(self, paths: list[str]) -> None:
        if not paths:
            return
        sample_name = posixpath.basename(paths[0].rstrip("/"))
        dlg = DeleteConfirmDialog(self, count=len(paths), sample_name=sample_name)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._run_remote_op("delete", paths)

    def _run_remote_op(self, op_type: str, paths: list[str]) -> None:
        self._detach_op_worker()
        thread = QThread()
        thread.setObjectName("RemoteOpThread")
        worker = RemoteOpWorker(op_type, paths)  # type: ignore[arg-type]
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_remote_op_done, _UI)
        worker.finished.connect(thread.quit)
        thread._pt_worker = worker  # type: ignore[attr-defined]
        thread.finished.connect(self._cleanup_op_thread, _UI)
        self._op_thread = thread
        self._op_worker = worker

        desc = {
            "mkdir": "新建文件夹",
            "rename": "重命名",
            "delete": f"删除 {len(paths)} 个项目",
        }.get(op_type, op_type)
        self.operation_started.emit(f"正在{desc}…")
        thread.start()

    def _cleanup_op_thread(self) -> None:
        thread = self.sender()
        if not isinstance(thread, QThread):
            return
        worker = getattr(thread, "_pt_worker", None)
        try:
            delattr(thread, "_pt_worker")
        except AttributeError:
            pass
        if self._op_thread is thread:
            self._op_thread = None
        if worker is not None and self._op_worker is worker:
            self._op_worker = None
        dispose_qthread_pair(thread, worker)

    def _detach_op_worker(self) -> None:
        worker = self._op_worker
        thread = self._op_thread
        self._op_worker = None
        self._op_thread = None
        if worker is not None:
            try:
                worker.cancel()
            except RuntimeError:
                pass
            for signal in (worker.finished,):
                try:
                    signal.disconnect()
                except (TypeError, RuntimeError):
                    pass
        if thread is not None:
            try:
                if thread.isRunning():
                    thread.quit()
                    thread.wait(500)
            except RuntimeError:
                pass
            dispose_qthread_pair(thread, worker)

    def _on_remote_op_done(
        self, ok: bool, msg: str, op_type: str, paths: list[str]
    ) -> None:
        if ok:
            if op_type == "delete":
                for p in paths:
                    if p in self._paths:
                        self._paths.remove(p)
                    self._path_is_dir.pop(p, None)
                self._sync_view()
                self.paths_changed.emit()
            elif op_type == "rename" and len(paths) >= 2:
                old_p, new_p = paths[0], paths[1]
                if old_p in self._paths:
                    idx = self._paths.index(old_p)
                    self._paths[idx] = new_p
                    is_d = self._path_is_dir.pop(old_p, False)
                    self._path_is_dir[new_p] = is_d
                    self._sync_view()
                    self.paths_changed.emit()
            self.reload_listing()
        self.operation_finished.emit(ok, msg, op_type)

    def _detach_list_worker(self) -> None:
        worker = self._list_worker
        thread = self._list_thread
        self._list_worker = None
        self._list_thread = None
        if worker is not None:
            try:
                worker.cancel()
            except RuntimeError:
                pass
            for signal in (worker.dirs_finished, worker.files_finished, worker.failed):
                try:
                    signal.disconnect()
                except (TypeError, RuntimeError):
                    pass
        if thread is not None:
            try:
                if thread.isRunning():
                    thread.quit()
                    thread.wait(500)
            except RuntimeError:
                pass
            dispose_qthread_pair(thread, worker)

    def shutdown(self) -> None:
        self._list_token += 1
        self._detach_list_worker()
        self._detach_op_worker()

    def reload_listing(self) -> None:
        self._list_token += 1
        self._detach_list_worker()
        token = self._list_token
        browse_dir = self._browse_dir
        self._entries = []
        self._files_loading = True
        self.btn_refresh.setEnabled(False)
        self._update_nav()
        self._clear_browse_rows()
        self.browse_scroll.verticalScrollBar().setValue(0)
        loading = QLabel(f"正在读取 {self._display_name_for_dir(browse_dir)}…")
        loading.setObjectName("emptyHint")
        loading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.browse_layout.addWidget(loading)

        thread = QThread()
        thread.setObjectName("PhoneListThread")
        worker = PhoneListWorker(browse_dir, token)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.dirs_finished.connect(self._on_dirs_ready, _UI)
        worker.files_finished.connect(self._on_files_ready, _UI)
        worker.failed.connect(self._on_list_fail, _UI)
        worker.files_finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread._pt_worker = worker  # type: ignore[attr-defined]
        thread.finished.connect(self._cleanup_list_thread, _UI)
        self._list_thread = thread
        self._list_worker = worker
        thread.start()

    def _cleanup_list_thread(self) -> None:
        thread = self.sender()
        if not isinstance(thread, QThread):
            return
        worker = getattr(thread, "_pt_worker", None)
        try:
            delattr(thread, "_pt_worker")
        except AttributeError:
            pass
        if self._list_thread is thread:
            self._list_thread = None
        if worker is not None and self._list_worker is worker:
            self._list_worker = None
        dispose_qthread_pair(thread, worker)

    def _on_dirs_ready(self, dirs: list, token: int, resolved_dir: str = "") -> None:
        if token != self._list_token:
            return
        if resolved_dir and resolved_dir != self._browse_dir:
            self._browse_dir = resolved_dir
            self.browse_dir_changed.emit(self._browse_dir)
        self._entries = sort_remote_entries(list(dirs))
        self._update_nav()
        self._rebuild_browse_rows(loading_files=True)
        self._sync_view()

    def _on_files_ready(self, files: list, token: int) -> None:
        if token != self._list_token:
            return
        self._files_loading = False
        self.btn_refresh.setEnabled(True)
        dirs = [entry for entry in self._entries if entry.is_dir]
        self._entries = sort_remote_entries(dirs + list(files))
        self._update_nav()
        self._rebuild_browse_rows(loading_files=False)
        self._sync_view()

    def _on_list_fail(self, message: str, token: int) -> None:
        if token != self._list_token:
            return
        self._entries = []
        self._visible_entries = []
        self._files_loading = False
        self.btn_refresh.setEnabled(True)
        self._clear_browse_rows()
        self._update_nav()
        self._sync_view()
        hint = QLabel(message or "读取失败")
        hint.setObjectName("emptyHint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setWordWrap(True)
        self.browse_layout.addWidget(hint)

    def _clear_browse_rows(self) -> None:
        while self.browse_layout.count():
            item = self.browse_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

    def _rebuild_browse_rows(self, *, loading_files: bool = False) -> None:
        self._clear_browse_rows()
        inner_w = CARD_INNER_WIDTH
        entries = self._get_filtered_entries()
        self._visible_entries = entries

        if not entries and not loading_files:
            if self.search_edit.text() or self._filter_category != "all":
                hint = QLabel("无匹配文件 (按 Esc 重置)")
            else:
                hint = QLabel("此文件夹为空")
            hint.setObjectName("emptyHint")
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.browse_layout.addWidget(hint)
            return

        for idx, entry in enumerate(entries):
            row = BrowseEntryRow(
                entry, entry.path in self._paths, inner_w
            )
            row.setProperty("selected", idx == self._selected_index)
            row.checked_changed.connect(
                lambda path, checked, p=entry.path, d=entry.is_dir: self.set_checked(
                    p, checked, is_dir=d
                )
            )
            if entry.is_dir:
                row.open_requested.connect(self._navigate_to)
            row.row_clicked.connect(lambda _p, i=idx: (self.select_index(i), self.setFocus()))
            row.row_double_clicked.connect(
                lambda _p, e=entry: self._navigate_to(e.path) if e.is_dir else self.preview_requested.emit(e.path, e.size)
            )
            row.rename_requested.connect(self._prompt_rename)
            row.delete_requested.connect(self._prompt_delete_single)
            row.preview_requested.connect(self.preview_requested.emit)
            self.browse_layout.addWidget(row)

        if entries:
            if self._selected_index < 0 or self._selected_index >= len(entries):
                self._selected_index = 0
            self.select_index(self._selected_index)
        else:
            self._selected_index = -1

        if loading_files:
            hint = QLabel("正在加载文件…")
            hint.setObjectName("emptyHint")
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.browse_layout.addWidget(hint)

    def _sync_view(self) -> None:
        n = len(self._paths)
        self.btn_clear.setVisible(n > 0)
        self.btn_delete.setEnabled(n > 0)

        is_filtered = bool(self.search_edit.text()) or self._filter_category != "all"
        if is_filtered:
            matched = len(self._visible_entries)
            total = len(self._entries)
            if n == 0:
                self.summary.setText(f"匹配 {matched}/{total} 项 · 未勾选")
            else:
                self.summary.setText(f"匹配 {matched}/{total} 项 · 已选 {n} 项")
            return

        if n == 0:
            self.summary.setText("勾选需要传输的文件或文件夹")
            return
        dirs = sum(1 for p in self._paths if self._path_is_dir.get(p, False))
        files = n - dirs
        parts: list[str] = []
        if files:
            parts.append(f"{files} 个文件")
        if dirs:
            parts.append(f"{dirs} 个文件夹")
        self.summary.setText(f"已选 {' · '.join(parts)}")
