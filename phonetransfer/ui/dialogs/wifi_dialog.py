"""Wi-Fi ADB connection dialog."""

from __future__ import annotations

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

from phonetransfer.workers.base import _UI
from phonetransfer.workers.wifi_worker import WifiActionWorker


class WifiConnectDialog(QDialog):
    """添加无线 ADB 设备：手动输入 IP / 配对码（Android 11+）/ 插线转无线。

    所有底层 ADB 操作均移至后台线程异步执行，保证界面丝滑响应。
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("添加无线设备")
        self.setModal(True)
        self.setFixedWidth(430)
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
            "如果觉得配对码繁琐，可通过数据线一键开启无线：\n"
            "1. 用数据线将手机连接到电脑，并在手机上允许调试；\n"
            "2. 点击下方按钮，系统自动开启无线端口并建立连接；\n"
            "3. 成功后即可拔掉数据线，随时无线传输！"
        )
        usb_hint.setWordWrap(True)
        usb_hint.setStyleSheet("color: gray; font-size: 12px;")
        ul.addWidget(usb_hint)

        self.btn_usb_to_wifi = QPushButton("⚡ 插线一键开启无线并连接")
        self.btn_usb_to_wifi.clicked.connect(self._do_usb_to_wifi)
        ul.addWidget(self.btn_usb_to_wifi)

        self.usb_to_wifi_result = QLabel("")
        self.usb_to_wifi_result.setWordWrap(True)
        ul.addWidget(self.usb_to_wifi_result)
        ul.addStretch(1)

        self.tabs.addTab(self.usb_tab, "插线转无线 (免配对)")

        # ── Tab 2: 配对码（Android 11+）─────────────────────────────────────
        self.pair_tab = QWidget()
        pl = QVBoxLayout(self.pair_tab)
        pl.setContentsMargins(12, 12, 12, 12)
        pl.setSpacing(10)

        pair_hint = QLabel(
            "Android 11+：开发者选项 → 无线调试 → 使用配对码配对，\n"
            "输入该界面显示的 IP、配对端口（3xxxx）和 6 位配对码。\n"
            "配对成功后设备会自动出现在主界面设备列表中。"
        )
        pair_hint.setWordWrap(True)
        pair_hint.setStyleSheet("color: gray; font-size: 12px;")
        pl.addWidget(pair_hint)

        form2 = QFormLayout()
        form2.setSpacing(8)
        self.pair_ip = QLineEdit()
        self.pair_ip.setPlaceholderText("192.168.1.100")
        form2.addRow("IP 地址：", self.pair_ip)
        self.pair_port = QSpinBox()
        self.pair_port.setRange(1, 65535)
        self.pair_port.setValue(37000)
        form2.addRow("配对端口：", self.pair_port)
        self.pair_code = QLineEdit()
        self.pair_code.setPlaceholderText("123456")
        self.pair_code.setMaxLength(6)
        form2.addRow("配对码：", self.pair_code)
        pl.addLayout(form2)

        self.btn_pair = QPushButton("配对")
        self.btn_pair.clicked.connect(self._do_pair)
        pl.addWidget(self.btn_pair)

        self.pair_result = QLabel("")
        self.pair_result.setWordWrap(True)
        pl.addWidget(self.pair_result)
        pl.addStretch(1)

        self.tabs.addTab(self.pair_tab, "配对码 (Android 11+)")

        # ── Tab 3: 手动输入 ──────────────────────────────────────────────────
        self.manual_tab = QWidget()
        ml = QVBoxLayout(self.manual_tab)
        ml.setContentsMargins(12, 12, 12, 12)
        ml.setSpacing(10)

        tip = QLabel("在手机「开发者选项 → 无线调试」中可以看到 IP 地址和端口。")
        tip.setWordWrap(True)
        tip.setStyleSheet("color: gray; font-size: 12px;")
        ml.addWidget(tip)

        form1 = QFormLayout()
        form1.setSpacing(8)
        self.manual_ip = QLineEdit()
        self.manual_ip.setPlaceholderText("192.168.1.100")
        form1.addRow("IP 地址：", self.manual_ip)
        self.manual_port = QSpinBox()
        self.manual_port.setRange(1, 65535)
        self.manual_port.setValue(5555)
        form1.addRow("端口：", self.manual_port)
        ml.addLayout(form1)

        self.btn_manual_connect = QPushButton("连接")
        self.btn_manual_connect.clicked.connect(self._manual_connect)
        ml.addWidget(self.btn_manual_connect)

        self.manual_result = QLabel("")
        self.manual_result.setWordWrap(True)
        ml.addWidget(self.manual_result)
        ml.addStretch(1)

        self.tabs.addTab(self.manual_tab, "手动输入")

        # 默认选中第一项（插线转无线）
        self.tabs.setCurrentIndex(0)

        # ── 关闭按钮 ─────────────────────────────────────────────────────────
        self.btn_close = QPushButton("关闭")
        self.btn_close.clicked.connect(self.reject)
        layout.addWidget(self.btn_close)

    def _set_busy(self, busy: bool) -> None:
        self.tabs.setEnabled(not busy)
        self.btn_manual_connect.setEnabled(not busy)
        self.btn_pair.setEnabled(not busy)
        self.btn_usb_to_wifi.setEnabled(not busy)
        self.btn_close.setEnabled(not busy)

    def _start_worker(
        self, action: Literal["connect", "pair", "usb_to_wifi"], params: dict
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
                QMessageBox.information(
                    self,
                    "无线开启成功",
                    f"{msg}\n\n现在您可以拔掉数据线，即可进行无线文件传输！",
                )
                self.accept()

    def _manual_connect(self) -> None:
        ip = self.manual_ip.text().strip()
        port = self.manual_port.value()
        if not ip:
            self.manual_result.setText("❌ 请输入 IP 地址")
            return
        self._start_worker("connect", {"ip": ip, "port": port})

    def _do_pair(self) -> None:
        ip = self.pair_ip.text().strip()
        port = self.pair_port.value()
        code = self.pair_code.text().strip()
        if not ip:
            self.pair_result.setText("❌ 请输入 IP 地址")
            return
        if not code:
            self.pair_result.setText("❌ 请输入配对码")
            return
        self._start_worker("pair", {"ip": ip, "port": port, "code": code})

    def _do_usb_to_wifi(self) -> None:
        self._start_worker("usb_to_wifi", {})

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.terminate()
            self._worker.wait(1000)
        super().closeEvent(event)

    def reject(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.terminate()
            self._worker.wait(1000)
        super().reject()

