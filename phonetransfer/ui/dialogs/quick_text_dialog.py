#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跨端文本与链接速传弹窗：直达手机剪贴板，支持一键粘贴使用，以及网页打开与便签存储"""

from __future__ import annotations

import re
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from phonetransfer.adb.text_ops import (
    is_pure_ascii,
    is_valid_url,
    push_text_file_to_phone,
    push_text_input_to_phone,
    push_text_to_clipboard,
    push_url_to_phone,
)


class QuickTextDialog(QDialog):
    """文本与网页链接速传对话框：优先直达手机系统剪贴板。"""

    text_sent = Signal(str, str)  # (action_type, message)

    def __init__(self, parent=None, serial: str | None = None, initial_text: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle("速传到手机 (⌘⇧V)")
        self.setModal(True)
        self.setFixedWidth(460)
        self._serial = serial

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("📋 跨端速传到手机")
        title.setStyleSheet("font-size: 15px; font-weight: 600;")
        layout.addWidget(title)

        self.tip_label = QLabel("正在分析文本类型…")
        self.tip_label.setStyleSheet("font-size: 12px; color: #8e8e93;")
        self.tip_label.setWordWrap(True)
        layout.addWidget(self.tip_label)

        self.text_edit = QPlainTextEdit()
        self.text_edit.setPlaceholderText("在此粘贴或输入需要发送给手机的文本、网址或验证码…\n(快捷键 ⌘↵ 直接发送)")
        self.text_edit.setStyleSheet(
            "QPlainTextEdit { "
            "  background: rgba(128, 128, 128, 0.08); "
            "  border: 1px solid rgba(128, 128, 128, 0.2); "
            "  border-radius: 8px; "
            "  font-size: 13px; "
            "  padding: 8px; "
            "}"
        )
        self.text_edit.setMinimumHeight(120)
        self.text_edit.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.text_edit)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("font-size: 11px; color: #e8685a;")
        self.status_label.setVisible(False)
        layout.addWidget(self.status_label)

        # 按钮操作栏
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.btn_secondary = QPushButton("📄 另存为便签文件")
        self.btn_secondary.setObjectName("segmentBtn")
        self.btn_secondary.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_secondary.clicked.connect(self._on_secondary_action)
        btn_row.addWidget(self.btn_secondary)

        btn_row.addStretch(1)

        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setObjectName("segmentBtn")
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(self.btn_cancel)

        self.btn_primary = QPushButton("📋 复制到手机剪贴板 (⌘↵)")
        self.btn_primary.setObjectName("pickBtn")
        self.btn_primary.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_primary.clicked.connect(self._on_primary_action)
        btn_row.addWidget(self.btn_primary)

        layout.addLayout(btn_row)

        if initial_text:
            self.text_edit.setPlainText(initial_text.strip())
            self.text_edit.selectAll()
        self._on_text_changed()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier):
                if self.btn_primary.isEnabled():
                    self._on_primary_action()
                    return
        super().keyPressEvent(event)

    def _on_text_changed(self) -> None:
        raw = self.text_edit.toPlainText().strip()
        self.status_label.setVisible(False)

        if not raw:
            self.tip_label.setText("输入或粘贴文本将直接写入手机剪贴板；输入网址可一键在手机浏览器打开。")
            self.btn_primary.setText("📋 复制到手机剪贴板 (⌘↵)")
            self.btn_primary.setEnabled(False)
            self.btn_secondary.setVisible(False)
            return

        self.btn_primary.setEnabled(True)
        self.btn_secondary.setVisible(True)

        if is_valid_url(raw):
            self.tip_label.setText("🌐 检测到网页链接：点击可直接在手机浏览器打开，也可复制到剪贴板。")
            self.btn_primary.setText("🚀 在手机打开网页 (⌘↵)")
            self.btn_secondary.setText("📋 复制到剪贴板")
        else:
            length_info = f"{len(raw)} 字"
            if "\n" in raw:
                length_info += f"，{raw.count(chr(10)) + 1} 行"
            self.tip_label.setText(
                f"📋 检测到文本 ({length_info})：点击直接写入手机剪贴板，手机端长按或输入法弹条可直接粘贴！"
            )
            self.btn_primary.setText("📋 复制到手机剪贴板 (⌘↵)")
            self.btn_secondary.setText("📄 另存为便签文件")

    def _on_primary_action(self) -> None:
        raw = self.text_edit.toPlainText().strip()
        if not raw:
            return

        if is_valid_url(raw):
            ok, err = push_url_to_phone(raw, serial=self._serial)
            if ok:
                self.text_sent.emit("url", f"已在手机浏览器打开：{raw}")
                self.accept()
            else:
                self.status_label.setText(err or "打开网页失败")
                self.status_label.setVisible(True)
        else:
            self._on_copy_to_clipboard()

    def _on_secondary_action(self) -> None:
        raw = self.text_edit.toPlainText().strip()
        if not raw:
            return

        if is_valid_url(raw):
            self._on_copy_to_clipboard()
        else:
            self._on_save_file()

    def _on_copy_to_clipboard(self) -> None:
        raw = self.text_edit.toPlainText().strip()
        if not raw:
            return
        ok, err = push_text_to_clipboard(raw, serial=self._serial)
        if ok:
            preview = raw[:26].replace("\n", " ") + ("…" if len(raw) > 26 else "")
            self.text_sent.emit("clipboard", f"已复制到剪贴板: {preview}")
            self.accept()
        else:
            self.status_label.setText(err or "写入手机剪贴板失败")
            self.status_label.setVisible(True)

    def _on_save_file(self) -> None:
        raw = self.text_edit.toPlainText().strip()
        if not raw:
            return
        ok, res = push_text_file_to_phone(raw, serial=self._serial)
        if ok:
            self.text_sent.emit("file", f"已保存便签至手机：{res}")
            self.accept()
        else:
            self.status_label.setText(res or "保存便签文件失败")
            self.status_label.setVisible(True)
