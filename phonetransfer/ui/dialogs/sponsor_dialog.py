#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""请作者喝杯咖啡 (Buy Me a Coffee) 赞助支持弹窗"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

ASSETS_DIR = Path(__file__).resolve().parent.parent.parent / "assets"
WECHAT_QR_PATH = ASSETS_DIR / "wechat_qr.png"
ALIPAY_QR_PATH = ASSETS_DIR / "alipay_qr.png"


class SponsorDialog(QDialog):
    """支持与赞助对话框。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("请作者喝杯咖啡 ☕")
        self.setModal(True)
        self.setFixedWidth(380)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # 头部标题
        header_l = QVBoxLayout()
        header_l.setSpacing(4)
        title = QLabel("☕ 请作者喝杯咖啡")
        title.setStyleSheet("font-size: 16px; font-weight: 600;")
        header_l.addWidget(title)

        subtitle = QLabel(
            "PhoneTransfer 是一款用业余时间打磨的开源独立工具。\n"
            "如果它为你省下了时间与精力，欢迎请作者喝杯咖啡，支持后续持续维护与更新！"
        )
        subtitle.setStyleSheet("font-size: 12px; color: #8e8e93; line-height: 1.4;")
        subtitle.setWordWrap(True)
        header_l.addWidget(subtitle)
        layout.addLayout(header_l)

        # 支付方式切换 Segment
        segment_row = QHBoxLayout()
        segment_row.setSpacing(8)

        self.btn_wechat = QPushButton("🟢 微信支付")
        self.btn_wechat.setCheckable(True)
        self.btn_wechat.setChecked(True)
        self.btn_wechat.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_wechat.setStyleSheet(
            "QPushButton { padding: 6px 16px; font-size: 13px; font-weight: 500; border-radius: 6px; }"
            "QPushButton:checked { background: #07c160; color: #ffffff; font-weight: 600; border: none; }"
            "QPushButton:!checked { background: rgba(128, 128, 128, 0.12); color: #8e8e93; border: 1px solid rgba(128, 128, 128, 0.2); }"
        )

        self.btn_alipay = QPushButton("🔵 支付宝")
        self.btn_alipay.setCheckable(True)
        self.btn_alipay.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_alipay.setStyleSheet(
            "QPushButton { padding: 6px 16px; font-size: 13px; font-weight: 500; border-radius: 6px; }"
            "QPushButton:checked { background: #1678ff; color: #ffffff; font-weight: 600; border: none; }"
            "QPushButton:!checked { background: rgba(128, 128, 128, 0.12); color: #8e8e93; border: 1px solid rgba(128, 128, 128, 0.2); }"
        )

        self.pay_group = QButtonGroup(self)
        self.pay_group.addButton(self.btn_wechat)
        self.pay_group.addButton(self.btn_alipay)
        self.btn_wechat.clicked.connect(self._show_wechat)
        self.btn_alipay.clicked.connect(self._show_alipay)

        segment_row.addWidget(self.btn_wechat)
        segment_row.addWidget(self.btn_alipay)
        layout.addLayout(segment_row)

        # 二维码展示卡片容器（白色底衬，确保扫描对比度 100% 完美）
        self.card_frame = QFrame()
        self.card_frame.setStyleSheet(
            "QFrame { background: #ffffff; border: 1px solid rgba(128, 128, 128, 0.2); "
            "border-radius: 12px; }"
        )
        card_l = QVBoxLayout(self.card_frame)
        card_l.setContentsMargins(16, 16, 16, 12)
        card_l.setSpacing(8)
        card_l.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.qr_label = QLabel()
        self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_label.setFixedSize(220, 240)
        card_l.addWidget(self.qr_label)

        self.author_label = QLabel("扫码支持作者：Berethor (**旭)")
        self.author_label.setStyleSheet("font-size: 12px; color: #555555; font-weight: 500;")
        self.author_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_l.addWidget(self.author_label)

        layout.addWidget(self.card_frame)

        # 底部温馨说明
        self.tip_label = QLabel("💡 手机扫一扫即可赞助，金额随意（¥3 润喉 / ¥9 拿铁 / ¥18 咖啡豆）")
        self.tip_label.setStyleSheet("font-size: 11px; color: #8e8e93;")
        self.tip_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tip_label.setWordWrap(True)
        layout.addWidget(self.tip_label)

        # 底部功能按钮栏
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.btn_github = QPushButton("⭐ 去 GitHub 给个 Star")
        self.btn_github.setObjectName("segmentBtn")
        self.btn_github.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_github.setToolTip("点个 Star 也是巨大的鼓舞！")
        self.btn_github.clicked.connect(self._open_github)
        btn_row.addWidget(self.btn_github)

        btn_row.addStretch(1)

        self.btn_close = QPushButton("关闭")
        self.btn_close.setObjectName("segmentBtn")
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.clicked.connect(self.accept)
        btn_row.addWidget(self.btn_close)

        layout.addLayout(btn_row)

        # 默认展示微信
        self._show_wechat()

    def _show_wechat(self) -> None:
        if WECHAT_QR_PATH.exists():
            pm = QPixmap(str(WECHAT_QR_PATH))
            scaled = pm.scaled(
                220, 240, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            self.qr_label.setPixmap(scaled)
        else:
            self.qr_label.setText("未找到微信二维码")
        self.author_label.setText("微信扫码支持：Berethor (**旭)")

    def _show_alipay(self) -> None:
        if ALIPAY_QR_PATH.exists():
            pm = QPixmap(str(ALIPAY_QR_PATH))
            scaled = pm.scaled(
                220, 240, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            self.qr_label.setPixmap(scaled)
        else:
            self.qr_label.setText("未找到支付宝二维码")
        self.author_label.setText("支付宝扫码支持：Berethor (**旭)")

    def _open_github(self) -> None:
        QDesktopServices.openUrl(QUrl("https://github.com/qfxydx/PhoneTransfer"))

