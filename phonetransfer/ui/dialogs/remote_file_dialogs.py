#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手机远端文件操作对话框：新建文件夹、重命名、删除确认"""

from __future__ import annotations

import posixpath
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)


class NewFolderDialog(QDialog):
    """新建远端文件夹输入框。"""

    def __init__(self, parent=None, current_dir_name: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle("新建文件夹")
        self.setModal(True)
        self.setFixedWidth(340)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        title = QLabel("新建文件夹")
        title.setStyleSheet("font-size: 15px; font-weight: 600;")
        layout.addWidget(title)

        hint = QLabel(f"在「{current_dir_name or '当前目录'}」中创建新文件夹：")
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size: 12px; color: #8e8e93;")
        layout.addWidget(hint)

        self.edit = QLineEdit("新建文件夹")
        self.edit.setObjectName("pathEdit")
        self.edit.selectAll()
        self.edit.returnPressed.connect(self._on_accept)
        layout.addWidget(self.edit)

        self.err_label = QLabel("")
        self.err_label.setStyleSheet("color: #e8685a; font-size: 11px;")
        self.err_label.setVisible(False)
        layout.addWidget(self.err_label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch(1)

        btn_cancel = QPushButton("取消")
        btn_cancel.setObjectName("segmentBtn")
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        btn_ok = QPushButton("创建")
        btn_ok.setObjectName("pickBtn")
        btn_ok.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_ok.clicked.connect(self._on_accept)
        btn_row.addWidget(btn_ok)

        layout.addLayout(btn_row)

    def _on_accept(self) -> None:
        name = self.edit.text().strip()
        if not name:
            self.err_label.setText("文件夹名称不能为空")
            self.err_label.setVisible(True)
            return
        if any(c in name for c in ("\0", ":", "*", "?", '"', "<", ">", "|", "\\", "/")):
            self.err_label.setText("文件夹名称不能包含 / : * ? \" < > | 等特殊字符")
            self.err_label.setVisible(True)
            return
        self.accept()

    def folder_name(self) -> str:
        return self.edit.text().strip()


class RenameDialog(QDialog):
    """重命名文件或文件夹对话框。"""

    def __init__(self, parent=None, current_name: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle("重命名")
        self.setModal(True)
        self.setFixedWidth(340)
        self._original_name = current_name

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        title = QLabel("重命名")
        title.setStyleSheet("font-size: 15px; font-weight: 600;")
        layout.addWidget(title)

        hint = QLabel(f"原名称：{current_name}")
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size: 12px; color: #8e8e93;")
        layout.addWidget(hint)

        self.edit = QLineEdit(current_name)
        self.edit.setObjectName("pathEdit")
        # 如果是文件，选中主文件名（不包含后缀）
        stem, ext = posixpath.splitext(current_name)
        if ext and stem:
            self.edit.setSelection(0, len(stem))
        else:
            self.edit.selectAll()
        self.edit.returnPressed.connect(self._on_accept)
        layout.addWidget(self.edit)

        self.err_label = QLabel("")
        self.err_label.setStyleSheet("color: #e8685a; font-size: 11px;")
        self.err_label.setVisible(False)
        layout.addWidget(self.err_label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch(1)

        btn_cancel = QPushButton("取消")
        btn_cancel.setObjectName("segmentBtn")
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        btn_ok = QPushButton("确定")
        btn_ok.setObjectName("pickBtn")
        btn_ok.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_ok.clicked.connect(self._on_accept)
        btn_row.addWidget(btn_ok)

        layout.addLayout(btn_row)

    def _on_accept(self) -> None:
        name = self.edit.text().strip()
        if not name:
            self.err_label.setText("名称不能为空")
            self.err_label.setVisible(True)
            return
        if name == self._original_name:
            self.reject()
            return
        if any(c in name for c in ("\0", ":", "*", "?", '"', "<", ">", "|", "\\", "/")):
            self.err_label.setText("名称不能包含 / : * ? \" < > | 等特殊字符")
            self.err_label.setVisible(True)
            return
        self.accept()

    def new_name(self) -> str:
        return self.edit.text().strip()


class DeleteConfirmDialog(QDialog):
    """远端删除二次确认对话框（高危操作，防误触）。"""

    def __init__(self, parent=None, count: int = 1, sample_name: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle("删除确认")
        self.setModal(True)
        self.setFixedWidth(360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        title = QLabel("永久删除")
        title.setStyleSheet("font-size: 15px; font-weight: 600; color: #e8685a;")
        layout.addWidget(title)

        if count == 1:
            main_text = f"确定要从手机中永久删除「{sample_name}」吗？"
        else:
            main_text = f"确定要从手机中永久删除选中的 {count} 个项目吗？"
            if sample_name:
                main_text += f"\n包含：{sample_name} 等"

        lab_main = QLabel(main_text)
        lab_main.setWordWrap(True)
        lab_main.setStyleSheet("font-size: 13px; line-height: 1.4;")
        layout.addWidget(lab_main)

        hint = QLabel("⚠️ 此操作将从手机内部存储中彻底移除，无法撤销。")
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size: 11px; color: #8e8e93;")
        layout.addWidget(hint)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch(1)

        btn_cancel = QPushButton("取消")
        btn_cancel.setObjectName("segmentBtn")
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.setDefault(True)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        btn_del = QPushButton("删除")
        btn_del.setObjectName("dangerBtn")
        btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_del.clicked.connect(self.accept)
        btn_row.addWidget(btn_del)

        layout.addLayout(btn_row)

