#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scrcpy 手机投屏与协同控制集成模块"""

from __future__ import annotations

from phonetransfer.i18n import tr

import os
from pathlib import Path
import shutil
import subprocess

from phonetransfer.adb.core import ADB, get_active_serial


SCRCPY_CANDIDATES = [
    "/opt/homebrew/bin/scrcpy",
    "/usr/local/bin/scrcpy",
    str(Path.home() / ".local/bin/scrcpy"),
    "/Applications/scrcpy.app/Contents/MacOS/scrcpy",
]


def find_scrcpy() -> str | None:
    """查找系统中安装的 scrcpy 可执行文件。"""
    found = shutil.which("scrcpy")
    if found:
        return found
    for path in SCRCPY_CANDIDATES:
        if Path(path).is_file() and os.access(path, os.X_OK):
            return path
    return None


def is_scrcpy_available() -> bool:
    return find_scrcpy() is not None


def launch_scrcpy(
    serial: str | None = None,
    title: str | None = None,
    *,
    stay_awake: bool = True,
) -> tuple[subprocess.Popen | None, str]:
    """启动 scrcpy 投屏窗口。

    - 自动传入当前 ADB 序列号 -s <serial>
    - 自动配置 ADB 环境变量，保证 scrcpy 使用与 PhoneTransfer 相同的 adb
    - 异步后台运行，不阻塞主应用界面
    """
    scrcpy_bin = find_scrcpy()
    if not scrcpy_bin:
        return None, tr('未检测到已安装的 scrcpy')

    target_serial = serial or get_active_serial()
    cmd = [scrcpy_bin]

    if target_serial:
        cmd.extend(["-s", target_serial])

    window_title = title or (f"Phone Mirror - {target_serial}" if target_serial else "Phone Mirror")
    cmd.extend(["--window-title", window_title])

    if stay_awake:
        cmd.append("--stay-awake")

    env = os.environ.copy()
    if ADB:
        env["ADB"] = ADB
        adb_dir = str(Path(ADB).parent)
        current_path = env.get("PATH", "")
        if adb_dir not in current_path:
            env["PATH"] = f"{adb_dir}:{current_path}"

    try:
        proc = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        return proc, ""
    except Exception as e:
        return None, tr('启动 scrcpy 失败：{p0}', p0=e)


def open_terminal_to_install_scrcpy() -> tuple[bool, str]:
    """通过 macOS AppleScript 打开终端并自动执行 brew install scrcpy。"""
    script = 'tell application "Terminal" to do script "brew install scrcpy"'
    try:
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            return True, ""
        return False, (r.stderr or tr('执行 AppleScript 失败')).strip()
    except Exception as e:
        return False, str(e)

