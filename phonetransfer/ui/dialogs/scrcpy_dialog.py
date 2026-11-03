#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scrcpy 投屏引导与安装提示弹窗"""

from __future__ import annotations

from phonetransfer.i18n import tr

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from phonetransfer.adb.scrcpy import open_terminal_to_install_scrcpy


class ScrcpyInstallDialog(QDialog):
    """引导用户安装 scrcpy 的优雅对话框。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr('手机投屏与协同控制'))
        self.setModal(True)
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # 标题栏
        header_l = QVBoxLayout()
        header_l.setSpacing(4)
        title = QLabel(tr('🖥️ 手机屏幕镜像与协同控制'))
        title.setWordWrap(True)
        title.setStyleSheet("font-size: 16px; font-weight: 600;")
        header_l.addWidget(title)

        subtitle = QLabel(tr('在 Mac 上以 60 FPS 极低延迟实时投屏，并使用鼠标键盘直接反向操控手机。'))
        subtitle.setStyleSheet("font-size: 12px; color: #8e8e93;")
        subtitle.setWordWrap(True)
        header_l.addWidget(subtitle)
        layout.addLayout(header_l)

        # 特性亮点卡片
        features_box = QFrame()
        features_box.setStyleSheet(
            "QFrame { background: rgba(128, 128, 128, 0.08); border-radius: 8px; }"
        )
        fb_layout = QVBoxLayout(features_box)
        fb_layout.setContentsMargins(12, 10, 12, 10)
        fb_layout.setSpacing(6)

        items = [
            tr('⚡ 60 FPS 高清画质与极低延迟，传完文件秒开预览'),
            tr('🖱️ 完整支持 Mac 鼠标拖拽、滚轮滑动与点击操控'),
            tr('⌨️ 支持 Mac 物理键盘直接输入文字到手机'),
            tr('📋 手机与 Mac 剪贴板自动双向同步'),
        ]
        for item in items:
            lbl = QLabel(item)
            lbl.setWordWrap(True)
            lbl.setStyleSheet("font-size: 12px;")
            fb_layout.addWidget(lbl)
        layout.addWidget(features_box)

        # 安装指引框
        guide_box = QFrame()
        guide_box.setStyleSheet(
            "QFrame { background: rgba(128, 128, 128, 0.06); border: 1px solid rgba(128, 128, 128, 0.2); border-radius: 8px; }"
        )
        gb_layout = QVBoxLayout(guide_box)
        gb_layout.setContentsMargins(12, 10, 12, 10)
        gb_layout.setSpacing(8)

        guide_title = QLabel(tr('检测到 Mac 尚未安装 scrcpy 组件，可通过 Homebrew 一键安装：'))
        guide_title.setStyleSheet("font-size: 12px;")
        guide_title.setWordWrap(True)
        gb_layout.addWidget(guide_title)

        cmd_label = QLabel("brew install scrcpy")
        cmd_label.setStyleSheet(
            "font-family: Menlo, 'SF Mono', monospace; font-size: 13px; font-weight: 600; "
            "color: #007aff; background: rgba(0, 122, 255, 0.1); padding: 8px 12px; border-radius: 6px;"
        )
        cmd_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        gb_layout.addWidget(cmd_label)
        layout.addWidget(guide_box)

        self.tip_label = QLabel("")
        self.tip_label.setStyleSheet("font-size: 11px; color: #ff9f0a;")
        self.tip_label.setWordWrap(True)
        self.tip_label.setVisible(False)
        layout.addWidget(self.tip_label)

        # 底部按钮栏
        btn_row = QVBoxLayout()
        btn_row.setSpacing(8)

        self.btn_copy = QPushButton(tr('📋 复制命令'))
        self.btn_copy.setObjectName("segmentBtn")
        self.btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_copy.clicked.connect(self._copy_command)
        btn_row.addWidget(self.btn_copy)

        btn_row.addStretch(1)

        self.btn_close = QPushButton(tr('关闭'))
        self.btn_close.setObjectName("segmentBtn")
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.clicked.connect(self.reject)
        btn_row.addWidget(self.btn_close)

        self.btn_run_terminal = QPushButton(tr('🚀 在终端一键安装'))
        self.btn_run_terminal.setObjectName("pickBtn")
        self.btn_run_terminal.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_run_terminal.clicked.connect(self._run_in_terminal)
        btn_row.addWidget(self.btn_run_terminal)

        layout.addLayout(btn_row)

    def _copy_command(self) -> None:
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText("brew install scrcpy")
        self.tip_label.setText(tr('✓ 已复制命令到剪贴板，可粘贴到终端回车执行'))
        self.tip_label.setVisible(True)

    def _run_in_terminal(self) -> None:
        ok, err = open_terminal_to_install_scrcpy()
        if ok:
            self.tip_label.setText(tr('✓ 已为您打开 Terminal 终端并开始安装，安装完成后即可直接投屏！'))
            self.tip_label.setVisible(True)
        else:
            self.tip_label.setText(tr('打开终端失败：{p0}，请手动复制命令在终端执行', p0=err))
            self.tip_label.setVisible(True)
