#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ADB 基础命令与设备连接管理"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys
import threading
from pathlib import Path

from phonetransfer.constants import (
    ADB_CANDIDATES,
    _USB_ANDROID_NAME_HINTS,
    _USB_ANDROID_VENDOR_IDS,
)


def find_adb() -> str:
    for p in ADB_CANDIDATES:
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)
    return shutil.which("adb") or "adb"


ADB = find_adb()

# 当前选中的 adb 设备序列号；多设备时所有 adb 命令必须带 -s
_active_serial_lock = threading.Lock()
_active_serial: str | None = None


def get_active_serial() -> str | None:
    with _active_serial_lock:
        return _active_serial


def set_active_serial(serial: str | None) -> None:
    global _active_serial
    with _active_serial_lock:
        _active_serial = serial


def adb_cmd(*args: str, serial: str | None = None) -> list[str]:
    """构造 adb 命令；有目标设备时自动插入 -s <serial>。"""
    target = serial if serial is not None else get_active_serial()
    if target:
        return [ADB, "-s", target, *args]
    return [ADB, *args]


def shell_quote(path: str) -> str:
    """POSIX 安全单引号转义，避免 Android shell 解析变量 ($) 或反引号。"""
    return shlex.quote(path)


def adb_shell(
    cmd: str, *, serial: str | None = None, timeout: int = 15, input: str | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        adb_cmd("shell", cmd, serial=serial),
        input=input,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def adb_push(
    local_path: str, remote_path: str, *, serial: str | None = None, timeout: int = 30
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        adb_cmd("push", local_path, remote_path, serial=serial),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def is_wifi_serial(serial: str) -> bool:
    """IP:PORT 形式的序列号表示无线 ADB 连接（非本地回环 / 模拟器）。"""
    s = (serial or "").strip()
    return bool(re.match(r"\d{1,3}(\.\d{1,3}){3}:\d+", s)) and not s.startswith("127.")


def is_emulator_serial(serial: str) -> bool:
    s = (serial or "").lower()
    return s.startswith("emulator-") or s.startswith("127.0.0.1:") or s.startswith("localhost:")


def format_model_name(model: str) -> str:
    model = model.replace("_", " ").strip()
    if model and not model[0].isupper():
        return model.title()
    return model or "Android"


def pick_preferred_device(
    online: list[dict], preferred_serial: str | None = None
) -> dict | None:
    """优先沿用用户已选设备；否则优先 USB 真机，再 Wi-Fi 真机，最后模拟器。"""
    if not online:
        return None
    if preferred_serial:
        for d in online:
            if d.get("serial") == preferred_serial:
                return d
    # USB 真机 > Wi-Fi 真机 > 模拟器
    usb = [
        d
        for d in online
        if not is_emulator_serial(str(d.get("serial") or ""))
        and not is_wifi_serial(str(d.get("serial") or ""))
    ]
    if usb:
        return usb[0]
    wifi = [d for d in online if is_wifi_serial(str(d.get("serial") or ""))]
    if wifi:
        return wifi[0]
    return online[0]


def device_display_name(device: dict) -> str:
    model = format_model_name(str(device.get("model") or "Android"))
    serial = str(device.get("serial") or "")
    if is_emulator_serial(serial):
        return f"{model}（模拟器）"
    if is_wifi_serial(serial):
        return f"🛜 {model}"
    return f"🔌 {model}"


def detect_usb_android_phones() -> list[dict[str, str]]:
    """macOS: 通过 IOKit 枚举 USB，找出已插入的安卓手机（即便未开 USB 调试）。"""
    if sys.platform != "darwin":
        return []
    try:
        result = subprocess.run(
            ["ioreg", "-p", "IOUSB", "-l", "-w", "0"],
            capture_output=True,
            text=True,
            timeout=8,
        )
    except (subprocess.TimeoutExpired, OSError, FileNotFoundError):
        return []

    phones: list[dict[str, str]] = []
    seen: set[str] = set()
    for block in re.split(r"\+-o ", result.stdout or ""):
        product_m = re.search(r'"USB Product Name"\s*=\s*"([^"]*)"', block)
        vendor_m = re.search(r'"USB Vendor Name"\s*=\s*"([^"]*)"', block)
        serial_m = re.search(r'"USB Serial Number"\s*=\s*"([^"]*)"', block)
        vid_m = re.search(r'"idVendor"\s*=\s*(\d+)', block)
        if not (product_m or vendor_m or vid_m):
            continue
        product = (product_m.group(1) if product_m else "").strip()
        vendor = (vendor_m.group(1) if vendor_m else "").strip()
        serial = (serial_m.group(1) if serial_m else "").strip()
        vid = int(vid_m.group(1)) if vid_m else 0
        blob = f"{product} {vendor}".lower()
        if not (
            any(h in blob for h in _USB_ANDROID_NAME_HINTS)
            or f"0x{vid:04x}".lower() in _USB_ANDROID_VENDOR_IDS
        ):
            continue
        key = serial or f"{vid}:{product}:{vendor}"
        if key in seen:
            continue
        seen.add(key)
        label = product.replace("_", " ").strip() or vendor or "Android"
        phones.append(
            {
                "product": product,
                "vendor": vendor,
                "serial": serial,
                "label": label,
            }
        )
    return phones


def explain_adb_device_state(state: str) -> str:
    state = (state or "").strip().lower()
    if state == "unauthorized":
        return "请在手机上点「允许 USB 调试」"
    if state == "offline":
        return "设备离线，请重新插拔数据线或重启 USB 调试"
    if state == "recovery":
        return "手机处于 Recovery 模式，请退出后重试"
    if state == "sideload":
        return "手机处于 Sideload 模式，请退出后重试"
    if state:
        return f"设备状态异常：{state}"
    return "设备状态异常"


def explain_adb_error(text: str, local: Path, remote: str) -> str | None:
    lower = text.lower()
    if "no such file or directory" in lower:
        if "cannot stat" in lower:
            return f"本地文件无法读取（请确认已从 iCloud 下载到本机）：{local.name}"
        if not remote.startswith("/"):
            return f"手机目标路径格式不正确：{remote}（请使用如 /sdcard/Download）"
        return f"手机目标路径不存在或无法访问：{remote}"
    if "no space left" in lower or "not enough space" in lower:
        return f"手机存储空间不足，无法传输：{local.name}"
    if "permission denied" in lower:
        return f"没有权限写入手机目标路径：{local.name}"
    if "symlink failed" in lower or "remote symlink" in lower:
        return (
            f"文件夹包含符号链接，无法直接传输：{local.name}"
            "（将自动改为传输实际文件内容）"
        )
    return None


def format_adb_failure(lines: list[str], local: Path, remote: str) -> str:
    text = "\n".join(lines)
    detail = explain_adb_error(text, local, remote)
    if detail:
        return detail
    for line in reversed(lines):
        line = line.strip()
        if line and "pushed" not in line.lower():
            return f"传输失败：{local.name}（{line}）"
    return f"传输失败：{local.name}"

