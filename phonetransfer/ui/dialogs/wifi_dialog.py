"""Wi-Fi ADB connection dialog."""

from __future__ import annotations

from phonetransfer.i18n import tr

from typing import Literal

from PySide6.QtCore import QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from phonetransfer.adb.core import get_active_serial
from phonetransfer.workers.base import _UI
from phonetransfer.workers.wifi_worker import WifiActionWorker


class WifiConnectDialog(QDialog):
    """添加无线 ADB 设备：手动输入 IP / 配对码（Android 11+）/ 插线转无线。

    所有底层 ADB 操作均移至后台线程异步执行，保证界面丝滑响应。
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr('添加无线设备'))
        self.setModal(True)
        self.setMinimumWidth(430)
        self._worker: WifiActionWorker | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # ── Tab 1: 插线转无线 (免配对) ────────────────────────────────────
        self.usb_tab = QWidget()
        ul = QVBoxLayout(self.usb_tab)
        ul.setContentsMargins(12, 12, 12, 12)
        ul.setSpacing(10)

        usb_hint = QLabel(
            tr('经典 TCP ADB 模式（端口 5555），仅限可信私有网络。\n手机端的 TCP 调试可能在拔掉 USB 后继续监听；建议优先使用 Android 11+ 的配对码无线调试。\n使用完毕后必须选择关闭经典无线调试，单纯断开电脑连接并不能关闭手机监听端口。')
        )
        usb_hint.setWordWrap(True)
        usb_hint.setStyleSheet("color: gray; font-size: 12px;")
        ul.addWidget(usb_hint)

        self.btn_usb_to_wifi = QPushButton(tr('⚡ 插线一键开启无线并连接'))
        self.btn_usb_to_wifi.clicked.connect(self._do_usb_to_wifi)
        ul.addWidget(self.btn_usb_to_wifi)

        self.btn_disable_tcpip = QPushButton(tr('关闭已选设备的经典无线调试（5555）'))
        selected = get_active_serial() or ""
        self.btn_disable_tcpip.setEnabled(WifiActionWorker._classic_wifi_target(selected))
        if not self.btn_disable_tcpip.isEnabled():
            self.btn_disable_tcpip.setToolTip(tr('先在主界面选择已连接的 IP:5555 无线设备'))
        self.btn_disable_tcpip.clicked.connect(self._do_disable_tcpip)
        ul.addWidget(self.btn_disable_tcpip)

        self.usb_to_wifi_result = QLabel("")
        self.usb_to_wifi_result.setWordWrap(True)
        ul.addWidget(self.usb_to_wifi_result)
        ul.addStretch(1)

        self.tabs.addTab(self.usb_tab, tr('插线转无线 (免配对)'))

        # ── Tab 2: 配对码（Android 11+）─────────────────────────────────────
        self.pair_tab = QWidget()
        pl = QVBoxLayout(self.pair_tab)
        pl.setContentsMargins(12, 12, 12, 12)
        pl.setSpacing(10)

        pair_hint = QLabel(
            tr('Android 11+：开发者选项 → 无线调试 → 使用配对码配对，\n输入该界面显示的 IP、配对端口（3xxxx）和 6 位配对码。\n配对成功后设备会自动出现在主界面设备列表中。')
        )
        pair_hint.setWordWrap(True)
        pair_hint.setStyleSheet("color: gray; font-size: 12px;")
        pl.addWidget(pair_hint)

        form2 = QFormLayout()
        form2.setSpacing(8)
        self.pair_ip = QLineEdit()
        self.pair_ip.setPlaceholderText("192.168.1.100")
        form2.addRow(tr('IP 地址：'), self.pair_ip)
        self.pair_port = QSpinBox()
        self.pair_port.setRange(1, 65535)
        self.pair_port.setValue(37000)
        form2.addRow(tr('配对端口：'), self.pair_port)
        self.pair_code = QLineEdit()
        self.pair_code.setPlaceholderText("123456")
        self.pair_code.setMaxLength(6)
        form2.addRow(tr('配对码：'), self.pair_code)
        pl.addLayout(form2)

        self.btn_pair = QPushButton(tr('配对'))
        self.btn_pair.clicked.connect(self._do_pair)
        pl.addWidget(self.btn_pair)

        self.pair_result = QLabel("")
        self.pair_result.setWordWrap(True)
        pl.addWidget(self.pair_result)
        pl.addStretch(1)

        self.tabs.addTab(self.pair_tab, tr('配对码 (Android 11+)'))

        # ── Tab 3: 手动输入 ──────────────────────────────────────────────────
        self.manual_tab = QWidget()
        ml = QVBoxLayout(self.manual_tab)
        ml.setContentsMargins(12, 12, 12, 12)
        ml.setSpacing(10)

        tip = QLabel(tr('在手机「开发者选项 → 无线调试」中可以看到 IP 地址和端口。'))
        tip.setWordWrap(True)
        tip.setStyleSheet("color: gray; font-size: 12px;")
        ml.addWidget(tip)

        form1 = QFormLayout()
        form1.setSpacing(8)
        self.manual_ip = QLineEdit()
        self.manual_ip.setPlaceholderText("192.168.1.100")
        form1.addRow(tr('IP 地址：'), self.manual_ip)
        self.manual_port = QSpinBox()
        self.manual_port.setRange(1, 65535)
        self.manual_port.setValue(5555)
        form1.addRow(tr('端口：'), self.manual_port)
        ml.addLayout(form1)

        self.btn_manual_connect = QPushButton(tr('连接'))
        self.btn_manual_connect.clicked.connect(self._manual_connect)
        ml.addWidget(self.btn_manual_connect)

        self.manual_result = QLabel("")
        self.manual_result.setWordWrap(True)
        ml.addWidget(self.manual_result)
        ml.addStretch(1)

        self.tabs.addTab(self.manual_tab, tr('手动输入'))

        # 默认选中第一项（插线转无线）
        self.tabs.setCurrentIndex(0)

        # ── 关闭按钮 ─────────────────────────────────────────────────────────
        self.btn_close = QPushButton(tr('关闭'))
        self.btn_close.clicked.connect(self.reject)
        layout.addWidget(self.btn_close)

    def _set_busy(self, busy: bool) -> None:
        self.tabs.setEnabled(not busy)
        self.btn_manual_connect.setEnabled(not busy)
        self.btn_pair.setEnabled(not busy)
        self.btn_usb_to_wifi.setEnabled(not busy)
        serial = get_active_serial() or ""
        self.btn_disable_tcpip.setEnabled(
            not busy and WifiActionWorker._classic_wifi_target(serial)
        )
        self.btn_close.setEnabled(not busy)

    def _start_worker(
        self, action: Literal["connect", "pair", "usb_to_wifi", "disable_tcpip"], params: dict
    ) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        self._set_busy(True)
        self._worker = WifiActionWorker(action, params, self)
        self._worker.progress.connect(self._on_progress, _UI)
        self._worker.action_finished.connect(self._on_finished, _UI)
        self._worker.start()

    def _on_progress(self, msg: str) -> None:
        idx = self.tabs.currentIndex()
        if idx == 0:
            self.usb_to_wifi_result.setText(msg)
        elif idx == 1:
            self.pair_result.setText(msg)
        else:
            self.manual_result.setText(msg)

    def _on_finished(
        self, action: str, success: bool, msg: str, should_refresh: bool
    ) -> None:
        self._set_busy(False)
        self._on_progress(msg)

        if should_refresh:
            parent = self.parent()
            if parent is not None and hasattr(parent, "refresh_device"):
                parent.refresh_device(manual=True)

        if success:
            if action == "connect":
                QTimer.singleShot(600, self.accept)
            elif action == "usb_to_wifi":
                QMessageBox.information(self, tr('无线连接成功'), msg)
                self.accept()
            elif action == "disable_tcpip":
                QMessageBox.information(self, tr('经典无线调试已关闭'), msg)
                self.accept()

    def _manual_connect(self) -> None:
        ip = self.manual_ip.text().strip()
        port = self.manual_port.value()
        if not ip:
            self.manual_result.setText(tr('❌ 请输入 IP 地址'))
            return
        self._start_worker("connect", {"ip": ip, "port": port})

    def _do_pair(self) -> None:
        ip = self.pair_ip.text().strip()
        port = self.pair_port.value()
        code = self.pair_code.text().strip()
        if not ip:
            self.pair_result.setText(tr('❌ 请输入 IP 地址'))
            return
        if not code:
            self.pair_result.setText(tr('❌ 请输入配对码'))
            return
        self._start_worker("pair", {"ip": ip, "port": port, "code": code})

    def _do_usb_to_wifi(self) -> None:
        confirm = QMessageBox.warning(
            self, tr('启用经典无线调试'),
            tr('这会在手机上开启经典 TCP ADB 5555 监听端口。拔线或关闭 PhoneTransfer 不一定会关闭该端口。\n\n请仅在你信任的私人 Wi-Fi 上使用，结束后明确关闭经典无线调试。建议优先使用 Android 11+ 的配对码模式。\n\n确定要开启吗？'),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        serial = get_active_serial()
        # Never silently switch targets if several USB devices are connected.
        self._start_worker("usb_to_wifi", {"serial": serial} if serial else {})

    def _do_disable_tcpip(self) -> None:
        serial = get_active_serial() or ""
        if not WifiActionWorker._classic_wifi_target(serial):
            self.usb_to_wifi_result.setText(tr('请先在主界面选择 IP:5555 设备'))
            return
        self._start_worker("disable_tcpip", {"serial": serial})

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._worker is not None and self._worker.isRunning():
            # terminate() could kill a thread after it enabled TCP debugging
            # but before its rollback/cleanup code has executed.
            event.ignore()
            return
        super().closeEvent(event)

    def reject(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        super().reject()

