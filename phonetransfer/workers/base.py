#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Worker 线程生命周期与安全释放工具"""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, QObject, QThread, Qt

# 跨线程更新 UI 必须排队到主线程。lambda/普通函数默认 DirectConnection，会在
# 工作线程里调 setVisible → AppKit 创建 NSWindow → SIGABRT。
_UI = Qt.ConnectionType.QueuedConnection


def reclaim_qobject_to_main(obj: QObject) -> None:
    """必须在 obj 当前所在线程调用，才能把 affinity 挪回主线程。"""
    app = QCoreApplication.instance()
    if app is None:
        return
    try:
        if obj.thread() is not app.thread():
            obj.moveToThread(app.thread())
    except RuntimeError:
        pass


def dispose_qthread_pair(thread: QThread | None, worker: QObject | None) -> None:
    """安全销毁 ephemeral QThread + worker，避免 PySide 长时间运行后 SIGSEGV。

    典型崩溃栈：worker.deleteLater 落在已结束的 QThread 上 →
    QObject::~QObject → QThreadWrapper::disconnectNotify → PyDict_GetItem。
    worker 应在 run() finally 里先 reclaim_qobject_to_main(self)。
    """
    if worker is not None:
        try:
            worker.blockSignals(True)
        except RuntimeError:
            pass
        try:
            worker.deleteLater()
        except RuntimeError:
            pass
    if thread is not None:
        try:
            thread.blockSignals(True)
        except RuntimeError:
            pass
        try:
            thread.setParent(None)
        except RuntimeError:
            pass
        try:
            thread.deleteLater()
        except RuntimeError:
            pass

