"""Main application window for PhoneTransfer."""

from __future__ import annotations

from pathlib import Path
import subprocess
import time
from typing import Literal

from PySide6.QtCore import QMetaObject, QSize, Qt, QThread, QTimer
from PySide6.QtGui import (
    QCloseEvent,
    QGuiApplication,
    QKeySequence,
    QPalette,
    QResizeEvent,
    QShortcut,
    QShowEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from phonetransfer.adb.core import (
    ADB,
    device_display_name,
    explain_adb_device_state,
    format_model_name,
    get_active_serial,
    is_emulator_serial,
    is_wifi_serial,
    pick_preferred_device,
    set_active_serial,
)
from phonetransfer.adb.file_ops import (
    ensure_local_dir,
    remote_exists,
    verify_local_pushable,
)
from phonetransfer.adb.transfer import (
    collect_pull_conflicts,
    collect_sync_conflicts,
)
from phonetransfer.adb.scrcpy import is_scrcpy_available, launch_scrcpy
from phonetransfer.constants import (
    CARD_HEIGHT,
    CARD_WIDTH,
    CARDS_ROW_GAP,
    CONTENT_WIDTH,
    DEST_PRESETS,
    DEVICE_MISS_THRESHOLD,
    DEVICE_POLL_INTERVAL_MS,
    LOG_DETAIL_HEIGHT,
    MAIN_H_MARGIN,
    PHONE_QUICK_PRESETS,
    STORAGE_POLL_INTERVAL_MS,
    SWAP_BTN_SIZE,
    TRANSFER_PANEL_HEIGHT,
    WINDOW_WIDTH,
    FolderSyncMode,
    TransferDirection,
)
from phonetransfer.ui.dialogs import (
    QuickTextDialog,
    ScrcpyInstallDialog,
    SponsorDialog,
    WifiConnectDialog,
)
from phonetransfer.ui.quicklook import QuickLookManager
from phonetransfer.ui.theme import AppTheme
from phonetransfer.ui.widgets import (
    DestinationCard,
    LocalDestinationCard,
    LogDetailList,
    PhoneSourceCard,
    SourceCard,
    TransferArrow,
    TransferToast,
)
from phonetransfer.utils import (
    human_size,
    make_mac_coffee_icon,
    make_mac_screen_icon,
    pick_files_and_folders,
    resolve_symbol_font,
    send_macos_notification,
    sym,
)
from phonetransfer.workers.apk_worker import ApkInstallWorker
from phonetransfer.workers.base import _UI, dispose_qthread_pair
from phonetransfer.workers.device_worker import DeviceWorker
from phonetransfer.workers.preview_worker import RemotePreviewWorker
from phonetransfer.workers.storage_worker import StorageWorker
from phonetransfer.workers.transfer_worker import TransferWorker


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Phone Transfer")
        self.resize(WINDOW_WIDTH, 680)
        self.setMinimumSize(WINDOW_WIDTH, 660)
        self.setMaximumWidth(WINDOW_WIDTH)

        self._symbol_font = resolve_symbol_font()
        self._busy = False
        self._picking = False
        self._transfer_cancelled = False
        self._device: dict | None = None
        self._online_devices: list[dict] = []
        self._device_gen = 0
        self._device_miss_count = 0
        self._device_probe_busy = False
        self._user_picked_serial: str | None = None
        self._storage_gen = 0
        self._storage_target = "phone"
        self._storage_probe_busy = False
        self._transfer_thread: QThread | None = None
        self._transfer_worker: TransferWorker | None = None
        self._transfer_started_at = 0.0
        self._log_lines: list[str] = []
        self._known_device_serial: str | None = None
        self._pending_device_manual = False
        self._connect_hint_key: str | None = None
        self._layout_metrics_ready = False
        self._log_detail_expanded = False
        self._main_area_baseline = 0
        self._log_bar_collapsed_height = 0
        self._collapsed_window_height = 680
        self._log_spacing = 8
        self._direction: TransferDirection = "to_phone"
        self._closing = False
        self._quicklook = QuickLookManager()
        self._scrcpy_process: subprocess.Popen | None = None
        self._apk_worker: ApkInstallWorker | None = None
        self._preview_worker: RemotePreviewWorker | None = None

        self._device_poll_timer = QTimer(self)
        self._device_poll_timer.setInterval(DEVICE_POLL_INTERVAL_MS)
        self._device_poll_timer.timeout.connect(self._poll_device)

        self._storage_poll_timer = QTimer(self)
        self._storage_poll_timer.setInterval(STORAGE_POLL_INTERVAL_MS)
        self._storage_poll_timer.timeout.connect(self._poll_storage)

        # 常驻探测线程：避免每几秒新建/销毁 QThread 导致长时间运行后崩溃
        self._device_thread = QThread(self)
        self._device_worker = DeviceWorker()
        self._device_worker.moveToThread(self._device_thread)
        self._device_worker.finished.connect(self._on_device_ok, _UI)
        self._device_worker.failed.connect(self._on_device_fail, _UI)
        self._device_thread.start()

        self._storage_thread = QThread(self)
        self._storage_worker = StorageWorker()
        self._storage_worker.moveToThread(self._storage_thread)
        self._storage_worker.finished.connect(self._on_storage_ok, _UI)
        self._storage_worker.failed.connect(self._on_storage_fail, _UI)
        self._storage_thread.start()

        self._build_ui()
        self._apply_theme()
        self._update_transfer_button()
        self.append_log(f"引擎就绪 · {ADB}")
        self.refresh_device(manual=True)
        self._device_poll_timer.start()

        # 连接 Wi-Fi 按钮信号（_build_ui 之后才可以访问 btn_wifi）
        self.btn_wifi.clicked.connect(self._open_wifi_dialog)

        # 快捷键：Cmd+Shift+V / Ctrl+Shift+V 打开跨端速传
        self._shortcut_quick_text = QShortcut(QKeySequence("Ctrl+Shift+V"), self)
        self._shortcut_quick_text.activated.connect(self._open_quick_text_dialog)

        # 快捷键：Cmd+Shift+M / Ctrl+Shift+M 打开手机投屏协同
        self._shortcut_scrcpy = QShortcut(QKeySequence("Ctrl+Shift+M"), self)
        self._shortcut_scrcpy.activated.connect(self._launch_scrcpy)

        app = QApplication.instance()
        if app is not None:
            app.paletteChanged.connect(self._apply_theme)

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("root")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # —— 顶栏工具与设备状态 ——
        title_strip = QFrame()
        title_strip.setObjectName("titleStrip")
        title_strip.setFixedHeight(50)
        ts = QHBoxLayout(title_strip)
        ts.setContentsMargins(16, 0, 16, 0)
        ts.setSpacing(8)

        # —— 左侧快捷工具区 ——
        self.btn_send_text = QToolButton()
        self.btn_send_text.setObjectName("sendTextBtn")
        self.btn_send_text.setText(sym("paperplane"))
        self.btn_send_text.setToolTip("发送到手机剪贴板 (⌘⇧V)")
        self.btn_send_text.setFixedSize(26, 26)
        self.btn_send_text.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_send_text.clicked.connect(self._open_quick_text_dialog)

        self.btn_scrcpy = QToolButton()
        self.btn_scrcpy.setObjectName("scrcpyBtn")
        self.btn_scrcpy.setIcon(make_mac_screen_icon())
        self.btn_scrcpy.setIconSize(QSize(18, 18))
        self.btn_scrcpy.setToolTip("手机投屏 (⌘⇧M)")
        self.btn_scrcpy.setFixedSize(26, 26)
        self.btn_scrcpy.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_scrcpy.clicked.connect(self._launch_scrcpy)

        self.btn_wifi = QToolButton()
        self.btn_wifi.setObjectName("wifiBtn")
        self.btn_wifi.setText("≋")
        self.btn_wifi.setToolTip("添加无线设备")
        self.btn_wifi.setFixedSize(26, 26)
        self.btn_wifi.setCursor(Qt.CursorShape.PointingHandCursor)

        self.btn_coffee = QToolButton()
        self.btn_coffee.setObjectName("coffeeBtn")
        self.btn_coffee.setIcon(make_mac_coffee_icon())
        self.btn_coffee.setIconSize(QSize(18, 18))
        self.btn_coffee.setToolTip("请作者喝杯咖啡 (Buy Me a Coffee)")
        self.btn_coffee.setFixedSize(26, 26)
        self.btn_coffee.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_coffee.clicked.connect(self._open_sponsor_dialog)

        ts.addWidget(self.btn_send_text)
        ts.addWidget(self.btn_scrcpy)
        ts.addWidget(self.btn_wifi)
        ts.addWidget(self.btn_coffee)

        # —— 中间弹性空白，将功能区与设备状态区分开 ——
        ts.addStretch(1)

        # —— 右侧设备选择与状态 ——
        device_wrap = QWidget()
        device_row = QHBoxLayout(device_wrap)
        device_row.setContentsMargins(0, 0, 0, 0)
        device_row.setSpacing(0)

        self.device_name = QToolButton()
        self.device_name.setObjectName("devicePickerBtn")
        self.device_name.setText("未连接")
        self.device_name.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.device_name.setCursor(Qt.CursorShape.ArrowCursor)
        self.device_name.setPopupMode(QToolButton.ToolButtonPopupMode.DelayedPopup)
        self.device_name.setAutoRaise(True)
        self.device_name.setEnabled(False)
        self.device_name.setToolTip("连接设备后可在此切换")
        self.device_name.clicked.connect(self._popup_device_menu)

        self.device_chevron = QToolButton()
        self.device_chevron.setObjectName("deviceChevron")
        self.device_chevron.setText(sym("chevron.down"))
        self.device_chevron.setVisible(False)
        self.device_chevron.setCursor(Qt.CursorShape.PointingHandCursor)
        self.device_chevron.setToolTip("点击切换设备")
        self.device_chevron.setAutoRaise(True)
        self.device_chevron.clicked.connect(self._popup_device_menu)

        device_row.addWidget(self.device_name)
        device_row.addWidget(self.device_chevron)

        self.status_dot = QLabel()
        self.status_dot.setObjectName("statusDotOffline")
        self.status_dot.setFixedSize(8, 8)

        self.status_connected = QLabel("已连接")
        self.status_connected.setObjectName("statusConnected")
        self.status_connected.setVisible(False)

        self.btn_refresh = QToolButton()
        self.btn_refresh.setObjectName("refreshBtn")
        self.btn_refresh.setText(sym("arrow.clockwise"))
        self.btn_refresh.setToolTip("刷新设备")
        self.btn_refresh.setFixedSize(26, 26)
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.clicked.connect(lambda: self.refresh_device(manual=True))

        ts.addWidget(device_wrap)
        ts.addWidget(self.status_dot)
        ts.addWidget(self.status_connected)
        ts.addWidget(self.btn_refresh)
        root.addWidget(title_strip)

        # —— 主内容区（双卡固定宽度 + 下方传输按钮）——
        main_area = QWidget()
        main_area.setObjectName("mainArea")
        main_layout = QVBoxLayout(main_area)
        main_layout.setContentsMargins(MAIN_H_MARGIN, 16, MAIN_H_MARGIN, 16)
        main_layout.setSpacing(0)

        content_wrap = QWidget()
        content_wrap.setFixedWidth(CONTENT_WIDTH)
        content_layout = QVBoxLayout(content_wrap)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        cards_row = QHBoxLayout()
        cards_row.setContentsMargins(0, 0, 0, 0)
        cards_row.setSpacing(CARDS_ROW_GAP)
        cards_row.setAlignment(Qt.AlignmentFlag.AlignTop)

        source_host = QWidget()
        source_host.setObjectName("cardHost")
        source_host.setFixedWidth(CARD_WIDTH)
        source_host_l = QVBoxLayout(source_host)
        source_host_l.setContentsMargins(0, 0, 0, 0)
        self._source_stack = QStackedWidget()
        self._source_stack.setFixedSize(CARD_WIDTH, CARD_HEIGHT)
        self.source_card = SourceCard(self._symbol_font)
        self.source_card.setFixedSize(CARD_WIDTH, CARD_HEIGHT)
        self.phone_source_card = PhoneSourceCard()
        self.phone_source_card.setFixedSize(CARD_WIDTH, CARD_HEIGHT)
        self._source_stack.addWidget(self.source_card)
        self._source_stack.addWidget(self.phone_source_card)
        source_host_l.addWidget(self._source_stack)
        self.source_card.btn_pick.clicked.connect(self.pick_items)
        self.source_card.paths_changed.connect(self._on_paths_changed)
        self.source_card.apk_detected.connect(self._on_apk_detected)
        self.source_card.preview_requested.connect(self._on_local_preview)
        self.source_card.install_requested.connect(lambda apk: self.install_apks([apk]))
        self.phone_source_card.paths_changed.connect(self._on_paths_changed)
        self.phone_source_card.browse_dir_changed.connect(self._on_phone_browse_dir)
        self.phone_source_card.preview_requested.connect(self._on_remote_preview)
        self.phone_source_card.operation_started.connect(self._on_remote_op_started)
        self.phone_source_card.operation_finished.connect(self._on_remote_op_finished)

        self.btn_swap = QToolButton()
        self.btn_swap.setObjectName("swapBtn")
        self.btn_swap.setText(sym("arrow.left.arrow.right"))
        self.btn_swap.setToolTip("切换传输方向")
        self.btn_swap.setFixedSize(SWAP_BTN_SIZE, SWAP_BTN_SIZE)
        self.btn_swap.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_swap.clicked.connect(self._toggle_direction)

        dest_host = QWidget()
        dest_host.setObjectName("cardHost")
        dest_host.setFixedWidth(CARD_WIDTH)
        dest_host_l = QVBoxLayout(dest_host)
        dest_host_l.setContentsMargins(0, 0, 0, 0)
        self._dest_stack = QStackedWidget()
        self._dest_stack.setFixedSize(CARD_WIDTH, CARD_HEIGHT)
        self.dest_card = DestinationCard()
        self.dest_card.setFixedSize(CARD_WIDTH, CARD_HEIGHT)
        self.local_dest_card = LocalDestinationCard()
        self.local_dest_card.setFixedSize(CARD_WIDTH, CARD_HEIGHT)
        self._dest_stack.addWidget(self.dest_card)
        self._dest_stack.addWidget(self.local_dest_card)
        dest_host_l.addWidget(self._dest_stack)
        self.dest_card.destination_changed.connect(
            lambda *_args: self._refresh_storage(force=True)
        )
        self.local_dest_card.destination_changed.connect(
            lambda *_args: self._refresh_storage(force=True)
        )

        cards_row.addWidget(source_host)
        cards_row.addWidget(self.btn_swap, 0, Qt.AlignmentFlag.AlignVCenter)
        cards_row.addWidget(dest_host)
        content_layout.addLayout(cards_row)

        transfer_section = QWidget()
        self.transfer_section = transfer_section
        transfer_section.setFixedWidth(CONTENT_WIDTH)
        transfer_section_l = QVBoxLayout(transfer_section)
        self._transfer_section_layout = transfer_section_l
        transfer_section_l.setContentsMargins(0, 14, 0, 0)
        transfer_section_l.setSpacing(8)
        transfer_section_l.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self.transfer_arrow = TransferArrow()
        transfer_section_l.addWidget(
            self.transfer_arrow, 0, Qt.AlignmentFlag.AlignHCenter
        )

        self.btn_go = QPushButton("传输到手机")
        self.btn_go.setObjectName("transferBtn")
        self.btn_go.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_go.setFixedSize(220, 44)
        self.btn_go.setEnabled(False)
        self.btn_go.setProperty("ready", False)
        self.btn_go.clicked.connect(self.start_transfer)

        self.transfer_hint = QLabel("请先选择内容")
        self.transfer_hint.setObjectName("transferHint")
        self.transfer_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.progress_wrap = QWidget()
        pw = QVBoxLayout(self.progress_wrap)
        pw.setContentsMargins(0, 0, 0, 2)
        pw.setSpacing(6)

        bar_row = QHBoxLayout()
        bar_row.setSpacing(10)
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("transferBar")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.progress_pct = QLabel("0%")
        self.progress_pct.setObjectName("caption")
        self.progress_pct.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.progress_pct.setFixedWidth(42)
        bar_row.addWidget(self.progress_bar, 1)
        bar_row.addWidget(self.progress_pct)

        meta_row = QHBoxLayout()
        meta_row.setSpacing(12)
        self.progress_count = QLabel("0/0 个文件")
        self.progress_count.setObjectName("caption")
        self.progress_eta = QLabel("")
        self.progress_eta.setObjectName("caption")
        self.progress_eta.setAlignment(Qt.AlignmentFlag.AlignRight)
        meta_row.addWidget(self.progress_count)
        meta_row.addStretch(1)
        meta_row.addWidget(self.progress_eta)

        self.progress_file = QLabel("")
        self.progress_file.setObjectName("secondaryText")
        self.progress_file.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress_file.setFixedHeight(18)

        self.btn_stop = QPushButton("取消")
        self.btn_stop.setObjectName("stopBtn")
        self.btn_stop.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_stop.setFixedHeight(30)
        self.btn_stop.clicked.connect(self.stop_transfer)
        stop_row = QHBoxLayout()
        stop_row.addStretch(1)
        stop_row.addWidget(self.btn_stop)
        stop_row.addStretch(1)

        pw.addLayout(bar_row)
        pw.addLayout(meta_row)
        pw.addWidget(self.progress_file)
        pw.addLayout(stop_row)

        idle_page = QWidget()
        idle_layout = QVBoxLayout(idle_page)
        idle_layout.setContentsMargins(0, 0, 0, 0)
        idle_layout.setSpacing(8)
        idle_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        idle_layout.addWidget(self.btn_go, 0, Qt.AlignmentFlag.AlignHCenter)
        idle_layout.addWidget(self.transfer_hint, 0, Qt.AlignmentFlag.AlignHCenter)
        idle_layout.addStretch(1)

        self.transfer_panel = QWidget()
        self.transfer_panel.setFixedSize(320, TRANSFER_PANEL_HEIGHT)
        panel_layout = QVBoxLayout(self.transfer_panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)

        self.transfer_stack = QStackedWidget()
        self.transfer_stack.setFixedSize(320, TRANSFER_PANEL_HEIGHT)
        self.transfer_stack.addWidget(idle_page)
        self.transfer_stack.addWidget(self.progress_wrap)
        self.transfer_stack.setCurrentIndex(0)
        panel_layout.addWidget(self.transfer_stack)
        transfer_section_l.addWidget(
            self.transfer_panel, 0, Qt.AlignmentFlag.AlignHCenter
        )
        content_layout.addWidget(transfer_section)

        main_layout.addWidget(content_wrap, 0, Qt.AlignmentFlag.AlignHCenter)
        main_area.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        self._main_area = main_area
        root.addWidget(main_area, 0)

        # —— 日志栏 ——
        log_bar = QFrame()
        log_bar.setObjectName("logBar")
        log_l = QVBoxLayout(log_bar)
        log_l.setContentsMargins(28, 11, 28, 11)
        log_l.setSpacing(self._log_spacing)
        self._log_layout = log_l

        log_head = QHBoxLayout()
        log_head.setSpacing(8)
        self.log_summary = QLabel("等待连接设备…")
        self.log_summary.setObjectName("logText")
        self.btn_log_toggle = QPushButton(f"查看详情  {sym('chevron.right')}")
        self.btn_log_toggle.setObjectName("logLink")
        self.btn_log_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_log_toggle.clicked.connect(self._toggle_log_detail)
        log_head.addWidget(self.log_summary, 1)
        log_head.addWidget(self.btn_log_toggle)
        log_l.addLayout(log_head)

        self.log_detail = LogDetailList()
        self.log_detail.setVisible(False)
        self.log_detail.setFixedHeight(LOG_DETAIL_HEIGHT)
        log_l.addWidget(self.log_detail)

        self.serial_label = QLabel("")
        self.serial_label.setObjectName("caption")
        self.serial_label.setVisible(False)
        log_l.addWidget(self.serial_label)

        root.addWidget(log_bar)
        self._log_bar = log_bar

        self.toast = TransferToast(central)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if self.toast.isVisible():
            self.toast._reposition()

    def _ensure_layout_metrics(self) -> None:
        if self._layout_metrics_ready:
            return
        self._main_area_baseline = self._main_area.sizeHint().height()
        if self._main_area_baseline > 0:
            self._main_area.setMinimumHeight(self._main_area_baseline)
        self._log_bar_collapsed_height = self._log_bar.height()
        self._collapsed_window_height = self.height()
        self._layout_metrics_ready = True

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._ensure_layout_metrics()

    def _predict_log_delta(self, with_serial: bool) -> int:
        delta = LOG_DETAIL_HEIGHT + self._log_spacing
        if with_serial:
            delta += self.serial_label.sizeHint().height() + self._log_spacing
        return delta

    def _lock_main_area_height(self) -> None:
        h = max(self._main_area.height(), self._main_area_baseline)
        self._main_area.setMinimumHeight(h)
        self._main_area.setMaximumHeight(h)

    def _unlock_main_area_height(self) -> None:
        if self._main_area_baseline > 0:
            self._main_area.setMinimumHeight(self._main_area_baseline)
        self._main_area.setMaximumHeight(16777215)

    def _toggle_log_detail(self) -> None:
        self._ensure_layout_metrics()
        expanding = not self._log_detail_expanded
        with_serial = self._device is not None
        chevron = sym("chevron.down") if expanding else sym("chevron.right")
        self.btn_log_toggle.setText(
            f"收起详情  {chevron}" if expanding else f"查看详情  {chevron}"
        )

        if expanding:
            delta = self._predict_log_delta(with_serial)
            self._collapsed_window_height = self.height()
            self._lock_main_area_height()
            self.resize(self.width(), self.height() + delta)
            self.log_detail.sync_lines(self._log_lines)
            self.log_detail.setVisible(True)
            self.serial_label.setVisible(with_serial)
            self._log_detail_expanded = True
            QTimer.singleShot(0, self._correct_log_expand_height)
            return

        self.log_detail.setVisible(False)
        self.serial_label.setVisible(False)
        self._log_detail_expanded = False
        self._unlock_main_area_height()
        target_h = max(self.minimumHeight(), self._collapsed_window_height)
        self.resize(self.width(), target_h)

    def _correct_log_expand_height(self) -> None:
        if not self._log_detail_expanded:
            return
        actual_delta = self._log_bar.height() - self._log_bar_collapsed_height
        predicted = self._predict_log_delta(self._device is not None)
        correction = actual_delta - predicted
        if correction:
            self.resize(self.width(), self.height() + correction)

    def _is_dark(self) -> bool:
        app = QApplication.instance()
        if app is None:
            return False
        hints = app.styleHints()
        if hasattr(hints, "colorScheme"):
            return hints.colorScheme() == Qt.ColorScheme.Dark
        return app.palette().color(QPalette.ColorRole.Window).lightness() < 128

    def _apply_theme(self, *_args) -> None:
        theme = AppTheme(self._is_dark())
        self.setStyleSheet(theme.stylesheet(self._symbol_font))
        self.transfer_arrow.set_colors(theme.quaternary, theme.tertiary)

    def _open_wifi_dialog(self) -> None:
        """打开「无线连接」对话框。"""
        dlg = WifiConnectDialog(self)
        dlg.exec()

    def _open_sponsor_dialog(self) -> None:
        """打开「请作者喝杯咖啡」赞助对话框。"""
        dlg = SponsorDialog(self)
        dlg.exec()

    def _open_quick_text_dialog(self) -> None:
        """跨端文本与链接速传对话框 (⌘⇧V)"""
        serial = get_active_serial()
        if not serial:
            self._show_toast("请先连接手机")
            return
        clipboard = QGuiApplication.clipboard()
        initial_text = clipboard.text() if clipboard else ""
        dlg = QuickTextDialog(self, serial=serial, initial_text=initial_text)
        dlg.text_sent.connect(self._on_quick_text_sent)
        dlg.exec()

    def _on_quick_text_sent(self, action_type: str, detail: str) -> None:
        if action_type == "clipboard":
            self._show_toast("已复制到手机剪贴板（可在手机直接粘贴）")
        else:
            self._show_toast(f"跨端速传成功: {detail}")
        self.append_log(f"[跨端速传] {action_type}: {detail}")

    def _launch_scrcpy(self) -> None:
        """启动 scrcpy 投屏控制或弹出安装指引 (⌘⇧M)。"""
        serial = get_active_serial()
        if not serial:
            self._show_toast("请先连接手机")
            return

        if not is_scrcpy_available():
            dlg = ScrcpyInstallDialog(self)
            dlg.exec()
            return

        if self._scrcpy_process is not None and self._scrcpy_process.poll() is None:
            self._show_toast("投屏窗口已在运行中")
            return

        dev_name = self.device_name.text().strip() or "Android"
        title = f"Phone Mirror - {dev_name}"
        proc, err = launch_scrcpy(serial=serial, title=title, stay_awake=True)
        if proc is not None:
            self._scrcpy_process = proc
            self._show_toast("已启动手机投屏")
            self.append_log(f"[投屏] 已启动 scrcpy: {title} ({serial})")
        else:
            self._show_toast(f"启动投屏失败: {err}")
            self.append_log(f"[投屏错误] {err}")

    def _on_local_preview(self, path: str) -> None:
        """空格键或双击快速预览电脑端本地文件。"""
        if self._busy:
            self._show_toast("当前正在传输文件，传输完成后可预览")
            return
        p = Path(path)
        if not p.exists() or p.stat().st_size == 0:
            self._show_toast("文件为空或尚未写入完成，暂无法预览")
            return
        self._quicklook.toggle(path)

    def _on_remote_preview(self, remote_path: str, remote_size: int) -> None:
        """空格键或双击预览手机端文件：若无本地缓存则异步快速拉取后预览。"""
        if self._busy:
            self._show_toast("当前正在传输文件，传输完成后可预览")
            return
        if remote_size <= 0:
            self._show_toast("空文件暂不支持预览")
            return
        if self._preview_worker is not None and self._preview_worker.isRunning():
            return

        serial = get_active_serial()
        cache_path = self._quicklook.get_preview_cache_path(remote_path, serial)
        if self._quicklook.current_path() == str(cache_path):
            self._quicklook.close()
            return
        name = Path(remote_path).name
        self._show_toast(f"正在加载预览：{name}…")
        self.append_log(f"正在读取手机预览文件：{remote_path}…")

        self._preview_worker = RemotePreviewWorker(
            remote_path, remote_size, str(cache_path), serial=serial, parent=self
        )
        self._preview_worker.ready.connect(self._on_remote_preview_ready, _UI)
        self._preview_worker.failed.connect(self._on_remote_preview_failed, _UI)
        self._preview_worker.start()

    def _on_remote_preview_ready(self, local_cache_path: str) -> None:
        self._hide_toast()
        if self._preview_worker is not None and self._preview_worker._serial != get_active_serial():
            self.append_log("预览完成时设备已切换，已忽略旧设备文件")
            return
        self._quicklook.preview(local_cache_path)

    def _on_remote_preview_failed(self, error: str) -> None:
        self._hide_toast()
        self.append_log(f"预览加载失败：{error}")
        self._show_toast("无法加载文件预览")

    def _on_apk_detected(self, apks: list[str]) -> None:
        """当拖拽或选择的文件中包含 .apk 安装包时触发快捷安装选项。"""
        if not apks or self._device is None:
            return

        device_name = self.device_name.text() or "当前手机"
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("检测到 Android 安装包")

        preview_names = "\n".join(f"• {Path(p).name}" for p in apks[:5])
        if len(apks) > 5:
            preview_names += f"\n…等共 {len(apks)} 个安装包"

        box.setText(
            f"检测到已添加 {len(apks)} 个 APK 安装包：\n\n{preview_names}\n\n"
            f"是否直接将其安装到手机（{device_name}）？"
        )
        install_btn = box.addButton("⚡ 直接安装到手机", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("仅加入传输列表", QMessageBox.ButtonRole.RejectRole)
        box.exec()

        if box.clickedButton() == install_btn:
            self.install_apks(apks)

    def install_apks(self, apks: list[str]) -> None:
        """异步执行 APK 应用安装。"""
        if not apks:
            return
        if self._device is None:
            QMessageBox.warning(self, "设备未连接", "请先连接手机并开启 USB 调试后再安装应用。")
            return
        if self._apk_worker is not None and self._apk_worker.isRunning():
            QMessageBox.information(self, "正在安装", "已有应用安装任务正在进行中，请稍候。")
            return

        serial = get_active_serial()
        self.append_log(f"开始向手机安装 {len(apks)} 个应用…")
        self._show_toast(f"正在安装应用：{Path(apks[0]).name}…")

        self._apk_worker = ApkInstallWorker(apks, serial=serial, parent=self)
        self._apk_worker.log.connect(self.append_log, _UI)
        self._apk_worker.progress.connect(self._on_apk_progress, _UI)
        self._apk_worker.finished.connect(self._on_apk_finished, _UI)
        self._apk_worker.start()

    def _on_apk_progress(self, current: int, total: int, name: str) -> None:
        self.log_summary.setText(f"正在安装应用 ({current}/{total})：{name}")
        self._show_toast(f"正在安装 ({current}/{total})：{name}")

    def _on_apk_finished(self, success_count: int, total_count: int, errors: list) -> None:
        self._hide_toast()
        if success_count == total_count and total_count > 0:
            msg = f"已成功安装 {success_count} 个应用到手机"
            self.log_summary.setText("应用安装完成")
            self._show_toast(f"✓ {msg}")
            send_macos_notification(msg, title="应用安装成功", subtitle="Phone Transfer")
        elif success_count > 0:
            msg = f"已安装 {success_count}/{total_count} 个应用（{len(errors)} 个失败）"
            self.log_summary.setText(msg)
            self._show_toast(msg)
            send_macos_notification(msg, title="应用安装结果", subtitle="Phone Transfer")
        else:
            err_summary = errors[0] if errors else "安装未成功"
            self.log_summary.setText("应用安装失败")
            self._show_toast("应用安装失败")
            send_macos_notification(f"安装失败：{err_summary}", title="应用安装失败", subtitle="Phone Transfer")

    def append_log(self, text: str) -> None:
        line = text.rstrip()
        if not line:
            return
        self._log_lines.append(line)
        self.log_detail.append(line)

    def _clear_log(self) -> None:
        self._log_lines.clear()
        self.log_detail.clear()

    def _active_source_card(self) -> SourceCard | PhoneSourceCard:
        if self._direction == "to_phone":
            return self.source_card
        return self.phone_source_card

    def _active_dest_card(self) -> DestinationCard | LocalDestinationCard:
        if self._direction == "to_phone":
            return self.dest_card
        return self.local_dest_card

    def _toggle_direction(self) -> None:
        if self._busy:
            return
        self.source_card.clear_paths()
        self.phone_source_card.clear_paths()
        self._direction = (
            "to_computer" if self._direction == "to_phone" else "to_phone"
        )
        label = "传输到电脑" if self._direction == "to_computer" else "传输到手机"
        self.append_log(f"已切换方向：{label}")
        self._apply_direction()

    def _apply_direction(self) -> None:
        to_phone = self._direction == "to_phone"
        self._source_stack.setCurrentIndex(0 if to_phone else 1)
        self._dest_stack.setCurrentIndex(0 if to_phone else 1)
        self.btn_swap.setEnabled(not self._busy)
        if not to_phone and self._device:
            self.phone_source_card.reload_listing()
        self._refresh_storage(force=True)
        self._update_transfer_button()

    def _on_paths_changed(self) -> None:
        self.toast.dismiss()
        self._update_transfer_button()

    def _on_phone_browse_dir(self, remote_dir: str) -> None:
        label = remote_dir
        for name, path in PHONE_QUICK_PRESETS:
            if remote_dir.rstrip("/") == path.rstrip("/"):
                label = name
                break
        else:
            for name, path in DEST_PRESETS:
                if remote_dir.rstrip("/") == path.rstrip("/"):
                    label = name
                    break
        self.append_log(f"已切换到手机目录：{label}")

    def _on_remote_op_started(self, message: str) -> None:
        self.append_log(message, "info")

    def _on_remote_op_finished(self, success: bool, message: str, op_type: str) -> None:
        if success:
            self.toast.show(message, "success")
            self.append_log(message, "success")
            if op_type == "delete":
                self._refresh_storage(force=True)
        else:
            self.toast.show(message, "error")
            self.append_log(f"操作失败：{message}", "error")

    def _update_transfer_button(self) -> None:
        has_files = bool(self._active_source_card().paths())
        connected = self._device is not None
        to_phone = self._direction == "to_phone"
        if self._busy:
            return
        ready = has_files and connected
        self.btn_go.setEnabled(ready)
        self.btn_go.setProperty("ready", ready)
        self.btn_go.style().unpolish(self.btn_go)
        self.btn_go.style().polish(self.btn_go)
        self.btn_go.setCursor(
            Qt.CursorShape.PointingHandCursor
            if ready
            else Qt.CursorShape.ForbiddenCursor
        )
        self.btn_go.setText("传输到手机" if to_phone else "传输到电脑")
        if not has_files:
            self.transfer_hint.setText(
                "请先选择内容" if to_phone else "请从手机选择文件"
            )
            self.transfer_hint.setVisible(True)
        elif not connected:
            hint_key = self._connect_hint_key or ""
            if hint_key.startswith("usb_debug_off"):
                self.transfer_hint.setText("请先打开手机 USB 调试")
            elif hint_key.startswith("adb_state:unauthorized"):
                self.transfer_hint.setText("请在手机上允许 USB 调试")
            else:
                self.transfer_hint.setText("请先连接手机")
            self.transfer_hint.setVisible(True)
        else:
            self.transfer_hint.setText("可开始传输")
            self.transfer_hint.setVisible(True)

    def _set_progress_visible(self, visible: bool) -> None:
        self.transfer_stack.setCurrentIndex(1 if visible else 0)
        self.transfer_arrow.setVisible(not visible)
        self.btn_swap.setEnabled(not visible)
        self._transfer_section_layout.setSpacing(8 if not visible else 0)
        self._transfer_section_layout.setContentsMargins(
            0, 14 if not visible else 4, 0, 0
        )

    def _show_toast(self, text: str) -> None:
        self.toast.show_message(text)

    def _hide_toast(self) -> None:
        self.toast.dismiss()

    def set_connection_ui(self, state: str, model: str, _status: str) -> None:
        if state == "online":
            multi = len(self._online_devices) > 1
            self.device_name.setText(model)
            self.device_name.setEnabled(multi)
            self.device_chevron.setVisible(multi)
            self.device_name.setCursor(
                Qt.CursorShape.PointingHandCursor
                if multi
                else Qt.CursorShape.ArrowCursor
            )
            tip = "点击切换设备" if multi else "当前已连接设备"
            self.device_name.setToolTip(tip)
            self.device_chevron.setToolTip(tip)
            self.status_dot.setObjectName("statusDotOnline")
            self.status_dot.setVisible(True)
            if multi:
                self.status_connected.setText(f"已连接 · {len(self._online_devices)} 台")
            else:
                self.status_connected.setText("已连接")
            self.status_connected.setVisible(True)
        elif state == "busy":
            self.device_name.setText(model)
            self.device_name.setEnabled(False)
            self.device_chevron.setVisible(False)
            self.device_name.setCursor(Qt.CursorShape.ArrowCursor)
            self.device_name.setToolTip("")
            self.status_dot.setObjectName("statusDotBusy")
            self.status_dot.setVisible(True)
            self.status_connected.setVisible(False)
        else:
            self.device_name.setText(model if model else "未连接")
            self.device_name.setEnabled(False)
            self.device_chevron.setVisible(False)
            self.device_name.setCursor(Qt.CursorShape.ArrowCursor)
            self.device_name.setToolTip("连接设备后可在此切换")
            self.status_dot.setObjectName("statusDotOffline")
            self.status_dot.setVisible(False)
            self.status_connected.setVisible(False)
        self.status_dot.style().unpolish(self.status_dot)
        self.status_dot.style().polish(self.status_dot)

    def _popup_device_menu(self) -> None:
        if len(self._online_devices) <= 1 or self._busy:
            return
        menu = QMenu(self)
        current = get_active_serial()
        for d in self._online_devices:
            serial = str(d.get("serial") or "")
            name = device_display_name(d)
            action = menu.addAction(name)
            action.setCheckable(True)
            action.setChecked(serial == current)
            action.triggered.connect(
                lambda _checked=False, s=serial: self._select_device_serial(s)
            )
        anchor = self.device_name.mapToGlobal(
            self.device_name.rect().bottomLeft()
        )
        menu.exec(anchor)

    def _select_device_serial(self, serial: str) -> None:
        if not serial or self._busy:
            return
        target = next(
            (d for d in self._online_devices if d.get("serial") == serial),
            None,
        )
        if target is None:
            return
        if get_active_serial() == serial and self._device and self._device.get("serial") == serial:
            return
        self._user_picked_serial = serial
        self._apply_selected_device(target, announce=True, switched=True)

    def _apply_selected_device(
        self, device: dict, *, announce: bool, switched: bool = False
    ) -> None:
        serial = str(device.get("serial") or "")
        set_active_serial(serial)
        self._device = device
        self._known_device_serial = serial
        self._device_miss_count = 0
        self._connect_hint_key = "online"
        name = device_display_name(device)
        self.set_connection_ui("online", name, "")
        self.log_summary.setText(f"已连接 {name}")
        self.serial_label.setText(f"序列号 {serial}  ·  adb {ADB}")
        if announce:
            if is_emulator_serial(serial):
                kind = "模拟器"
            elif is_wifi_serial(serial):
                kind = "Wi-Fi 设备"
            else:
                kind = "手机"
            if switched:
                self.append_log(f"已切换到{kind}：{name}（{serial}）")
            else:
                self.append_log(f"已连接 {name}（{serial}）")
        self._start_storage_poll()
        if self._direction == "to_computer":
            self.phone_source_card.reload_listing()
        self._update_transfer_button()

    def _poll_device(self) -> None:
        if self._busy:
            return
        self.refresh_device(manual=False)

    def refresh_device(self, *, manual: bool = False) -> None:
        # Keep the target device pinned for the lifetime of a transfer.
        if self._busy or self._closing or self._device_worker is None:
            return
        if self._device_probe_busy and not manual:
            return

        self._device_gen += 1
        gen = self._device_gen
        self._pending_device_manual = manual
        if manual:
            self._device_miss_count = 0
            self._device = None
            self.set_connection_ui("busy", "检测中…", "")
            self.btn_refresh.setEnabled(False)
            self.log_summary.setText("正在检测设备…")
            self.append_log("正在检测设备…")
            self._update_transfer_button()

        self._device_probe_busy = True
        self._device_worker.probe(gen, force_mdns=manual)

    def _emit_connect_hint(self, key: str, summary: str, detail: str, *, manual: bool) -> None:
        """更新摘要；仅在状态变化或手动刷新时写日志，避免轮询刷屏。"""
        self.log_summary.setText(summary)
        if manual or key != self._connect_hint_key:
            self.append_log(detail or summary)
        self._connect_hint_key = key

    def _clear_device_selection(self) -> None:
        set_active_serial(None)
        self._device = None
        self._online_devices = []
        self._known_device_serial = None
        self._device_miss_count = 0
        self._stop_storage_poll()
        self.serial_label.clear()
        self.device_chevron.setVisible(False)

    def _on_device_ok(self, payload: dict, gen: int) -> None:
        if gen != self._device_gen:
            return
        self._device_probe_busy = False
        if self._busy:
            # An earlier in-flight probe must not change the active ADB
            # target while a transfer is using it.
            self.btn_refresh.setEnabled(True)
            return
        devices = payload.get("devices") or []
        usb_phones = payload.get("usb_phones") or []
        manual = self._pending_device_manual
        self.btn_refresh.setEnabled(True)

        online = [d for d in devices if d.get("state") == "device"]
        self._online_devices = online
        preferred = self._user_picked_serial or self._known_device_serial
        selected = pick_preferred_device(online, preferred)
        new_serial = selected["serial"] if selected else None

        # 后台轮询且仍是同一台在线设备：只刷新菜单/状态，不刷日志
        if (
            not manual
            and new_serial
            and new_serial == self._known_device_serial
            and self._device is not None
        ):
            self._device_miss_count = 0
            self._connect_hint_key = "online"
            set_active_serial(new_serial)
            name = device_display_name(selected)
            self.set_connection_ui("online", name, "")
            if not self._storage_poll_timer.isActive():
                self._start_storage_poll()
            return

        if not devices:
            if not manual and self._known_device_serial is not None:
                self._device_miss_count += 1
                if self._device_miss_count < DEVICE_MISS_THRESHOLD:
                    return
            prev_serial = self._known_device_serial
            self._clear_device_selection()
            if usb_phones:
                label = usb_phones[0].get("label") or "Android"
                serial = usb_phones[0].get("serial") or ""
                self.set_connection_ui("offline", "需开启 USB 调试", "")
                summary = f"已插入 {label}，但未开启 USB 调试"
                detail = (
                    f"检测到手机已通过 USB 连接（{label}"
                    + (f" · {serial}" if serial else "")
                    + "），但调试通道未就绪。"
                    "请打开：设置 → 开发者选项 → USB 调试；"
                    "通知栏 USB 用途选「文件传输」，并在弹窗中点「允许」。"
                )
                self._emit_connect_hint(
                    f"usb_debug_off:{serial or label}",
                    summary,
                    detail,
                    manual=manual or prev_serial is not None,
                )
            else:
                self.set_connection_ui("offline", "未连接", "")
                self._emit_connect_hint(
                    "no_device",
                    "未检测到设备",
                    "未检测到设备",
                    manual=manual or prev_serial is not None,
                )
            self._update_transfer_button()
            return

        if online and selected is not None:
            prev_serial = self._known_device_serial
            switched = prev_serial is not None and prev_serial != selected["serial"]
            first_seen = prev_serial is None
            if self._user_picked_serial and self._user_picked_serial not in {
                d.get("serial") for d in online
            }:
                self._user_picked_serial = None
            self._apply_selected_device(
                selected,
                announce=manual or switched or first_seen,
                switched=switched,
            )
            if len(online) > 1 and (manual or first_seen or switched):
                others = [
                    device_display_name(d)
                    for d in online
                    if d.get("serial") != selected["serial"]
                ]
                self.append_log(
                    f"另有 {len(others)} 台设备在线，可点击右上角设备名切换："
                    + "、".join(others)
                )
        else:
            d = devices[0]
            if not manual and self._known_device_serial is not None:
                self._device_miss_count += 1
                if self._device_miss_count < DEVICE_MISS_THRESHOLD:
                    return
            self._clear_device_selection()
            state = str(d.get("state") or "")
            model = format_model_name(d.get("model") or "Android")
            tip = explain_adb_device_state(state)
            self.set_connection_ui("offline", model, "")
            if state == "unauthorized":
                title = "需允许 USB 调试"
                summary = f"{model} 已连接，请在手机上允许 USB 调试"
            else:
                title = tip
                summary = f"{model}：{tip}"
            self._emit_connect_hint(
                f"adb_state:{state}:{d.get('serial')}",
                summary,
                f"{title}（状态：{state or '未知'}）",
                manual=manual,
            )
            self._update_transfer_button()

    def _on_device_fail(self, text: str, gen: int) -> None:
        if gen != self._device_gen:
            return
        self._device_probe_busy = False
        if self._busy:
            self.btn_refresh.setEnabled(True)
            return
        manual = self._pending_device_manual
        self.btn_refresh.setEnabled(True)
        if not manual:
            if self._known_device_serial is not None:
                self._device_miss_count += 1
                if self._device_miss_count < DEVICE_MISS_THRESHOLD:
                    return
            else:
                return
        self._clear_device_selection()
        self.set_connection_ui("offline", "检测失败", "")
        self.log_summary.setText("设备检测失败")
        self.append_log(text)
        self._update_transfer_button()

    def _poll_storage(self) -> None:
        if self._busy:
            return
        if self._direction == "to_phone" and not self._device:
            return
        self._refresh_storage()

    def _start_storage_poll(self) -> None:
        self._refresh_storage(force=True)
        if not self._storage_poll_timer.isActive():
            self._storage_poll_timer.start()

    def _stop_storage_poll(self) -> None:
        self._storage_poll_timer.stop()
        self.dest_card.reset_available_space()
        self.local_dest_card.reset_available_space()

    def _refresh_storage(self, force: bool = False, *_args) -> None:
        if self._closing or self._storage_worker is None:
            return
        if self._storage_probe_busy and not force:
            return

        self._storage_gen += 1
        gen = self._storage_gen
        serial = get_active_serial()

        if self._direction == "to_phone":
            if not self._device or not serial:
                self.dest_card.reset_available_space()
                return
            path = self.dest_card.destination()
            self._storage_target = "phone"
            target = "phone"
            self.dest_card.set_storage_busy(True)
        else:
            path = self.local_dest_card.destination()
            self._storage_target = "local"
            target = "local"
            self.local_dest_card.set_storage_busy(True)

        self._storage_probe_busy = True
        self._storage_worker.probe(path, gen, target=target, serial=serial)

    def _on_storage_ok(self, text: str, gen: int) -> None:
        if gen != self._storage_gen:
            return
        self._storage_probe_busy = False
        if self._storage_target == "local":
            self.local_dest_card.set_available_space(text)
        else:
            self.dest_card.set_available_space(text)

    def _on_storage_fail(self, _error: str, gen: int) -> None:
        if gen != self._storage_gen:
            return
        self._storage_probe_busy = False
        if self._storage_target == "local":
            self.local_dest_card.set_storage_busy(False)
        else:
            self.dest_card.set_storage_busy(False)

    def pick_items(self) -> None:
        if self._picking or self._busy:
            return

        self._picking = True
        self.source_card.btn_pick.setEnabled(False)

        paths: list[str] = []
        try:
            paths = pick_files_and_folders("选择要传输的文件或文件夹")
        except Exception as e:
            self.append_log(f"打开选择器失败：{e}")
            QMessageBox.warning(self, "无法打开选择器", str(e))
        finally:
            self._picking = False
            self.source_card.btn_pick.setEnabled(True)

        if paths:
            added = self.source_card.add_paths(paths)
            if added:
                names = ", ".join(Path(p).name for p in self.source_card.paths()[-added:])
                self.append_log(f"已添加 {added} 项：{names}")

    def _ask_sync_policy(
        self, conflicts: list[str], *, to_phone: bool
    ) -> FolderSyncMode | None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("发现同名文件")
        target = "手机目标文件夹" if to_phone else "电脑目标文件夹"
        box.setText(
            f"在{target}中已存在 {len(conflicts)} 个同名文件。\n"
            "请选择处理方式："
        )
        preview = conflicts[:30]
        detail = "\n".join(preview)
        if len(conflicts) > 30:
            detail += f"\n…等 {len(conflicts)} 个"
        box.setDetailedText(detail)
        overwrite_btn = box.addButton("覆盖同名文件", QMessageBox.ButtonRole.DestructiveRole)
        keep_btn = box.addButton("两者都保留", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked == overwrite_btn:
            return "overwrite"
        if clicked == keep_btn:
            return "keep_both"
        return None

    def start_transfer(self) -> None:
        if self._busy:
            return
        to_phone = self._direction == "to_phone"
        items = self._active_source_card().paths()
        dest = self._active_dest_card().destination()
        if not items:
            return
        if not dest:
            QMessageBox.warning(
                self,
                "还差一步",
                "请填写手机保存路径" if to_phone else "请填写电脑保存路径",
            )
            return

        # 立即锁定传输按钮并更新提示，防止重复点击造成并发冲突
        self.btn_go.setEnabled(False)
        self.log_summary.setText("正在检查待传输文件…")
        QApplication.processEvents()

        def _cancel_prep(err_title: str = "", err_msg: str = "") -> None:
            self.btn_go.setEnabled(True)
            self.log_summary.setText("就绪")
            if err_title and err_msg:
                QMessageBox.critical(self, err_title, err_msg)

        if to_phone:
            missing = [p for p in items if not Path(p).exists()]
            if missing:
                _cancel_prep("路径无效", f"找不到：\n{missing[0]}")
                return
            for local in items:
                ok, err = verify_local_pushable(Path(local))
                if not ok:
                    _cancel_prep("无法传输", err)
                    return
        else:
            for remote in items:
                if not remote_exists(remote):
                    _cancel_prep("路径无效", f"手机上找不到：\n{remote}")
                    return
            ok, err = ensure_local_dir(dest)
            if not ok:
                _cancel_prep("无法传输", err)
                return

        sync_mode: FolderSyncMode = "overwrite"
        try:
            self.log_summary.setText("正在比对文件差异…")
            QApplication.processEvents()
            if to_phone:
                conflicts = collect_sync_conflicts(items, dest)
            else:
                conflicts = collect_pull_conflicts(items, dest)
        except (subprocess.TimeoutExpired, RuntimeError) as exc:
            _cancel_prep("比对失败", str(exc) or "比对同名文件超时，请稍后重试")
            return
        if conflicts:
            choice = self._ask_sync_policy(conflicts, to_phone=to_phone)
            if choice is None:
                _cancel_prep()
                return
            sync_mode = choice
            label = "覆盖同名文件" if choice == "overwrite" else "两者都保留"
            self.append_log(f"同名文件处理：{label}（{len(conflicts)} 个）")

        self._busy = True
        self._transfer_cancelled = False
        self._transfer_started_at = time.monotonic()
        self._hide_toast()
        self.btn_go.setEnabled(False)
        self.btn_swap.setEnabled(False)
        self._set_progress_visible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate until a verified file completes.
        self.progress_pct.setText("传输中")
        self.progress_count.setText("0 B 已校验")
        self.progress_file.setText("准备中…")
        self.progress_file.setToolTip("")
        self.progress_eta.setText("")
        self.append_log(f"开始传输 {len(items)} 项 → {dest}")

        thread = QThread()
        worker = TransferWorker(
            items,
            dest,
            direction=self._direction,
            folder_sync_mode=sync_mode,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.log.connect(self.append_log, _UI)
        worker.progress.connect(self._on_transfer_progress, _UI)
        worker.finished.connect(self._on_transfer_done, _UI)
        worker.finished.connect(thread.quit)
        thread._pt_worker = worker  # type: ignore[attr-defined]
        thread.finished.connect(self._cleanup_transfer_thread, _UI)

        self._transfer_thread = thread
        self._transfer_worker = worker
        thread.start()

    def _elide_progress_name(self, name: str) -> str:
        text_w = max(120, self.progress_file.width() - 8)
        return self.progress_file.fontMetrics().elidedText(
            name, Qt.TextElideMode.ElideMiddle, text_w
        )

    def _on_transfer_progress(
        self,
        done_bytes: int,
        total_bytes: int,
        done_files: int,
        total_files: int,
        name: str,
    ) -> None:
        # All numbers are verified, committed bytes. In-flight file progress
        # is deliberately indeterminate rather than estimated by a fake speed.
        if done_files == 0:
            self.progress_bar.setRange(0, 0)
            self.progress_pct.setText("传输中")
        else:
            self.progress_bar.setRange(0, 100)
            pct = int(done_bytes / total_bytes * 100) if total_bytes else 0
            self.progress_bar.setValue(max(0, min(100, pct)))
            self.progress_pct.setText(f"{pct}%")
        size_text = f"{human_size(done_bytes)} / {human_size(total_bytes)}"
        if total_files > 1:
            self.progress_count.setText(f"{size_text}（已验证 {done_files}/{total_files} 个）")
        else:
            self.progress_count.setText(f"{size_text}（已验证 {done_files}/{total_files}）")
        self.progress_file.setText(self._elide_progress_name(name))
        self.progress_file.setToolTip(name)
        self.progress_eta.setText("传输及完整性校验中 · 只统计已校验文件"
                                  if done_files < total_files else "全部文件已校验")

    def stop_transfer(self) -> None:
        if self._transfer_worker is not None:
            self._transfer_worker.cancel()
        self.append_log("正在停止传输…")

    def _on_transfer_done(self, ok: bool, message: str) -> None:
        self._busy = False
        self._set_progress_visible(False)
        self.progress_bar.setRange(0, 100)
        if ok:
            self.progress_bar.setValue(100)
            self._active_source_card().clear_paths()
            self._show_toast(message)
            self.append_log(message)
            send_macos_notification(message, title="传输完成", subtitle="Phone Transfer")
        else:
            self._hide_toast()
            self.append_log(message)
            if message != "传输已取消":
                send_macos_notification(message, title="传输失败", subtitle="Phone Transfer")
                QMessageBox.critical(self, "传输失败", message)
        self._update_transfer_button()

    def _cleanup_transfer_thread(self) -> None:
        thread = self.sender()
        if not isinstance(thread, QThread):
            worker = self._transfer_worker
            thread = self._transfer_thread
            self._transfer_worker = None
            self._transfer_thread = None
            dispose_qthread_pair(thread, worker)
            return
        worker = getattr(thread, "_pt_worker", None)
        try:
            delattr(thread, "_pt_worker")
        except AttributeError:
            pass
        if self._transfer_thread is thread:
            self._transfer_thread = None
        if worker is not None and self._transfer_worker is worker:
            self._transfer_worker = None
        dispose_qthread_pair(thread, worker)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._closing = True
        self._quicklook.close()
        self._device_poll_timer.stop()
        self._storage_poll_timer.stop()
        if hasattr(self, "phone_source_card") and self.phone_source_card is not None:
            try:
                self.phone_source_card.shutdown()
            except Exception:
                pass
        if self._apk_worker is not None and self._apk_worker.isRunning():
            try:
                self._apk_worker.cancel()
                self._apk_worker.wait(500)
            except RuntimeError:
                pass
        if self._preview_worker is not None and self._preview_worker.isRunning():
            try:
                self._preview_worker.wait(500)
            except RuntimeError:
                pass
        if self._scrcpy_process is not None and self._scrcpy_process.poll() is None:
            try:
                self._scrcpy_process.terminate()
            except Exception:
                pass
            self._scrcpy_process = None
        if self._transfer_worker is not None:
            try:
                self._transfer_worker.cancel()
            except RuntimeError:
                pass
        if self._transfer_thread is not None:
            try:
                self._transfer_thread.quit()
                self._transfer_thread.wait(1500)
            except RuntimeError:
                pass
            dispose_qthread_pair(self._transfer_thread, self._transfer_worker)
            self._transfer_thread = None
            self._transfer_worker = None

        for thread, worker in (
            (self._device_thread, self._device_worker),
            (self._storage_thread, self._storage_worker),
        ):
            if worker is not None and thread is not None and thread.isRunning():
                try:
                    QMetaObject.invokeMethod(
                        worker,
                        "prepare_shutdown",
                        Qt.ConnectionType.BlockingQueuedConnection,
                    )
                except (RuntimeError, TypeError):
                    pass
            if thread is not None:
                try:
                    thread.quit()
                    thread.wait(1500)
                except RuntimeError:
                    pass
            dispose_qthread_pair(thread, worker)
        self._device_thread = None
        self._device_worker = None
        self._storage_thread = None
        self._storage_worker = None
        super().closeEvent(event)
