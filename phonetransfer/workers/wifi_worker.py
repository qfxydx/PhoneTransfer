#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""无线 ADB 连接与配对后台 Worker"""

from __future__ import annotations

import re
import subprocess
import time
from typing import Literal

from PySide6.QtCore import QObject, QThread, Signal

from phonetransfer.adb.core import ADB, is_emulator_serial, is_wifi_serial


class WifiActionWorker(QThread):
    """在后台线程中执行 ADB 连接、配对与插线转无线，杜绝主线程卡顿与彩虹球。"""

    progress = Signal(str)
    action_finished = Signal(str, bool, str, bool)  # (action, success, message, should_refresh)

    def __init__(
        self,
        action: Literal["connect", "pair", "usb_to_wifi"],
        params: dict,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.action = action
        self.params = params

    def run(self) -> None:
        if self.action == "connect":
            self._run_connect()
        elif self.action == "pair":
            self._run_pair()
        elif self.action == "usb_to_wifi":
            self._run_usb_to_wifi()

    def _run_connect(self) -> None:
        ip = self.params.get("ip", "").strip()
        port = self.params.get("port", 5555)
        target = f"{ip}:{port}"
        self.progress.emit(f"正在连接 {target}…")
        try:
            proc = subprocess.run(
                [ADB, "connect", target],
                capture_output=True,
                text=True,
                timeout=10,
            )
            output = (proc.stdout + proc.stderr).strip()
            if "connected" in output.lower():
                self.action_finished.emit("connect", True, f"✅ {output}", True)
            else:
                msg = f"❌ {output}" if output else "❌ 连接失败，请检查 IP 和端口"
                self.action_finished.emit("connect", False, msg, False)
        except subprocess.TimeoutExpired:
            self.action_finished.emit("connect", False, "❌ 连接超时，目标设备不可达", False)
        except Exception as e:
            self.action_finished.emit("connect", False, f"❌ 错误：{e}", False)

    def _run_pair(self) -> None:
        ip = self.params.get("ip", "").strip()
        port = self.params.get("port", 37000)
        code = self.params.get("code", "").strip()
        target = f"{ip}:{port}"
        self.progress.emit(f"正在向 {target} 发送配对码…")
        try:
            proc = subprocess.run(
                [ADB, "pair", target],
                input=code + "\n",
                capture_output=True,
                text=True,
                timeout=15,
            )
            output = (proc.stdout + proc.stderr).strip()
            if "successfully" in output.lower() or "paired" in output.lower():
                msg = f"✅ 配对成功！设备下次自动轮询或切换到「手动输入」即可连接。\n{output}"
                self.action_finished.emit("pair", True, msg, True)
            else:
                msg = f"❌ 配对失败\n{output}" if output else "❌ 配对失败，请检查配对码和端口"
                self.action_finished.emit("pair", False, msg, False)
        except subprocess.TimeoutExpired:
            self.action_finished.emit("pair", False, "❌ 配对超时，请在手机上重新生成配对码", False)
        except Exception as e:
            self.action_finished.emit("pair", False, f"❌ 错误：{e}", False)

    def _run_usb_to_wifi(self) -> None:
        self.progress.emit("正在检测 USB 设备…")
        try:
            r = subprocess.run(
                [ADB, "devices", "-l"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            usb_serials = []
            for line in r.stdout.splitlines()[1:]:
                parts = line.strip().split()
                if len(parts) >= 2 and parts[1] == "device":
                    s = parts[0]
                    if not is_emulator_serial(s) and not is_wifi_serial(s):
                        usb_serials.append(s)

            if not usb_serials:
                self.action_finished.emit(
                    "usb_to_wifi",
                    False,
                    "❌ 未检测到 USB 连接的手机，请先插上数据线并允许 USB 调试。",
                    False,
                )
                return

            serial = usb_serials[0]
            self.progress.emit(f"正在获取手机 Wi-Fi IP ({serial})…")

            ip = None
            r_ip = subprocess.run(
                [ADB, "-s", serial, "shell", "ip -f inet addr show wlan0"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            m = re.search(r"inet\s+(\d{1,3}(?:\.\d{1,3}){3})", r_ip.stdout or "")
            if m:
                ip = m.group(1)

            if not ip:
                r_route = subprocess.run(
                    [ADB, "-s", serial, "shell", "ip route"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                for line in (r_route.stdout or "").splitlines():
                    if "wlan0" in line and "src" in line:
                        m2 = re.search(r"src\s+(\d{1,3}(?:\.\d{1,3}){3})", line)
                        if m2:
                            ip = m2.group(1)
                            break

            if not ip:
                self.action_finished.emit(
                    "usb_to_wifi",
                    False,
                    "❌ 未能获取到手机的 Wi-Fi IP，请确认手机已连接 Wi-Fi。",
                    False,
                )
                return

            self.progress.emit(f"正在开启 5555 端口 (IP: {ip})…")
            subprocess.run(
                [ADB, "-s", serial, "tcpip", "5555"],
                capture_output=True,
                text=True,
                timeout=8,
            )
            time.sleep(1)

            target = f"{ip}:5555"
            self.progress.emit(f"正在无线连接 {target}…")
            r_conn = subprocess.run(
                [ADB, "connect", target],
                capture_output=True,
                text=True,
                timeout=10,
            )
            conn_out = (r_conn.stdout + r_conn.stderr).strip()

            if "connected" in conn_out.lower():
                msg = f"✅ 无线连接成功 ({target})！\n现在可以拔掉数据线了。"
                self.action_finished.emit("usb_to_wifi", True, msg, True)
            else:
                self.action_finished.emit(
                    "usb_to_wifi",
                    False,
                    f"❌ 连接失败：{conn_out}",
                    False,
                )
        except subprocess.TimeoutExpired:
            self.action_finished.emit("usb_to_wifi", False, "❌ 操作超时", False)
        except Exception as e:
            self.action_finished.emit("usb_to_wifi", False, f"❌ 发生异常：{e}", False)

