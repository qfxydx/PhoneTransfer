#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""无线 ADB 连接与配对后台 Worker"""

from __future__ import annotations

import ipaddress
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
        action: Literal["connect", "pair", "usb_to_wifi", "disable_tcpip"],
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
        elif self.action == "disable_tcpip":
            self._run_disable_tcpip()

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
            if proc.returncode == 0 and (
                output.lower().startswith("connected to ")
                or output.lower().startswith("already connected to ")
            ):
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

    @staticmethod
    def _classic_wifi_target(serial: str) -> bool:
        """Only legacy IPv4 ADB on port 5555 can be reset by this action."""
        host, sep, port = serial.rpartition(":")
        if not sep or port != "5555":
            return False
        try:
            return ipaddress.ip_address(host).version == 4
        except ValueError:
            return False

    def _run_disable_tcpip(self) -> None:
        target = str(self.params.get("serial") or "")
        if not self._classic_wifi_target(target):
            self.action_finished.emit("disable_tcpip", False,
                                      "只允许关闭已选中的经典 5555 无线 ADB 连接。", False)
            return
        self.progress.emit(f"正在请求 {target} 切回 USB 调试模式…")
        try:
            response = subprocess.run(
                [ADB, "-s", target, "usb"], capture_output=True,
                text=True, timeout=12,
            )
            output = (response.stdout or "") + (response.stderr or "")
            if response.returncode != 0 or "restarting in usb mode" not in output.lower():
                self.action_finished.emit(
                    "disable_tcpip", False,
                    "无法确认无线监听已关闭。请使用 USB 连接执行 adb usb，"
                    "或在手机开发者选项关闭调试，勿只执行 adb disconnect。"
                    f"\n{output.strip()}", False,
                )
                return
            try:
                subprocess.run([ADB, "disconnect", target], capture_output=True,
                               text=True, timeout=6)
            except (OSError, subprocess.TimeoutExpired):
                # A confirmed USB mode reset is the security-critical step;
                # a stale host-side entry does not re-enable TCP adbd.
                pass
            self.action_finished.emit(
                "disable_tcpip", True,
                "已收到设备切回 USB 模式的确认，已断开本机无线会话。"
                "如要继续使用 USB，请连接数据线。", True,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.action_finished.emit(
                "disable_tcpip", False,
                f"无法确认无线监听已关闭：{exc}。请在手机上关闭调试或重新连接 USB 执行 adb usb。",
                False,
            )

    def _run_usb_to_wifi(self) -> None:
        """Legacy TCP ADB: never silently choose among multiple USB devices."""
        self.progress.emit("正在检查 USB 调试设备…")
        tcpip_enabled = False
        serial = ""
        target = ""
        try:
            result = subprocess.run([ADB, "devices", "-l"], capture_output=True,
                                    text=True, timeout=5)
            if result.returncode != 0:
                raise RuntimeError("ADB 无法列出设备")
            usb_serials = []
            for line in result.stdout.splitlines()[1:]:
                parts = line.strip().split()
                if (len(parts) >= 2 and parts[1] == "device"
                        and not is_emulator_serial(parts[0])
                        and not is_wifi_serial(parts[0])):
                    usb_serials.append(parts[0])
            chosen = str(self.params.get("serial") or "")
            if chosen:
                if chosen not in usb_serials:
                    raise RuntimeError("选中的 USB 设备已断开或不再可用")
                serial = chosen
            elif len(usb_serials) == 1:
                serial = usb_serials[0]
            elif len(usb_serials) > 1:
                raise RuntimeError("检测到多台 USB 设备，请先在主界面选择目标设备")
            else:
                raise RuntimeError("未检测到已授权的 USB Android 设备")

            r_ip = subprocess.run(
                [ADB, "-s", serial, "shell", "ip -f inet addr show wlan0"],
                capture_output=True, text=True, timeout=5,
            )
            match = re.search(r"inet\s+(\d{1,3}(?:\.\d{1,3}){3})", r_ip.stdout or "")
            ip = match.group(1) if match else None
            if not ip:
                r_route = subprocess.run(
                    [ADB, "-s", serial, "shell", "ip route"],
                    capture_output=True, text=True, timeout=5,
                )
                for line in (r_route.stdout or "").splitlines():
                    if "wlan0" in line and "src" in line:
                        m = re.search(r"src\s+(\d{1,3}(?:\.\d{1,3}){3})", line)
                        if m:
                            ip = m.group(1)
                            break
            try:
                addr = ipaddress.ip_address(ip) if ip else None
                if (addr is None or not addr.is_private or addr.is_loopback
                        or addr.is_link_local or addr.is_unspecified):
                    raise ValueError()
            except ValueError:
                raise RuntimeError("无法确认手机使用可信的局域网 IP，请改用 Android 11+ 配对码模式")

            target = f"{ip}:5555"
            self.progress.emit(f"正在为设备 {serial} 开启经典 TCP ADB…")
            # The TCP command may succeed even if the response gets lost.
            # Always try a rollback if we cannot confirm the resulting state.
            tcpip_enabled = True
            tcp = subprocess.run(
                [ADB, "-s", serial, "tcpip", "5555"],
                capture_output=True, text=True, timeout=8,
            )
            if tcp.returncode != 0 or "restarting in tcp mode" not in (
                    (tcp.stdout or "") + (tcp.stderr or "")).lower():
                # If the response is ambiguous, a reset attempt is safer than
                # treating the classic service as closed.
                raise RuntimeError("手机未确认启动 TCP 调试")
            time.sleep(1)
            conn = subprocess.run(
                [ADB, "connect", target], capture_output=True,
                text=True, timeout=10,
            )
            detail = ((conn.stdout or "") + (conn.stderr or "")).strip()
            if conn.returncode != 0 or not (
                detail.lower().startswith("connected to ")
                or detail.lower().startswith("already connected to ")
            ):
                raise RuntimeError(f"无线连接失败：{detail or '未知错误'}")
            self.action_finished.emit(
                "usb_to_wifi", True,
                f"已连接 {target}。经典 TCP ADB 5555 可能继续监听，"
                "仅限可信私有网络；使用结束后请从本工具选择「关闭经典无线调试」。",
                True,
            )
        except (OSError, subprocess.TimeoutExpired, RuntimeError) as exc:
            rollback_ok = False
            if tcpip_enabled:
                # Prefer the same USB serial; it may remain usable on some ROMs.
                for address in (serial, target):
                    if not address:
                        continue
                    try:
                        reset = subprocess.run(
                            [ADB, "-s", address, "usb"],
                            capture_output=True, text=True, timeout=8,
                        )
                        if (reset.returncode == 0 and "restarting in usb mode" in
                                ((reset.stdout or "") + (reset.stderr or "")).lower()):
                            rollback_ok = True
                            break
                    except (OSError, subprocess.TimeoutExpired):
                        pass
            suffix = (
                " 已收到切回 USB 模式的确认。"
                if rollback_ok else
                " 若已开启 5555，无法确认监听已关闭；请通过 USB 执行 adb usb，"
                "或在手机开发者选项关闭调试。"
            )
            self.action_finished.emit("usb_to_wifi", False, f"无线连接失败：{exc}。{suffix}", False)
