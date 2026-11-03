#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""设备后台探测 Worker（USB 与 Wi-Fi ADB 状态、mDNS 发现与排序）"""

from __future__ import annotations

from phonetransfer.i18n import tr

import re
import subprocess
import time

from PySide6.QtCore import QObject, Signal, Slot

from phonetransfer.adb.core import (
    ADB,
    detect_usb_android_phones,
    format_model_name,
    is_emulator_serial,
    is_wifi_serial,
)
from phonetransfer.workers.base import reclaim_qobject_to_main


class DeviceWorker(QObject):
    """常驻后台探测：避免每 2.5s 新建/销毁 QThread。"""

    finished = Signal(dict, int)
    failed = Signal(str, int)
    _kick = Signal(int, bool)

    def __init__(self) -> None:
        super().__init__()
        self._mdns_counter = 0
        self._failed_targets: dict[str, float] = {}
        self._kick.connect(self._run)

    def probe(self, gen: int, force_mdns: bool = False) -> None:
        self._kick.emit(gen, force_mdns)

    @Slot()
    def prepare_shutdown(self) -> None:
        self.blockSignals(True)
        reclaim_qobject_to_main(self)

    def _run(self, gen: int, force_mdns: bool = False) -> None:
        # adb 偶发 busy / offline：轻量重试一次，减少误报
        last_err = tr('adb 返回非零')
        for attempt in range(2):
            try:
                r = subprocess.run(
                    [ADB, "devices", "-l"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if r.returncode != 0:
                    last_err = (r.stderr or r.stdout or tr('adb 返回非零')).strip()
                    if attempt == 0:
                        time.sleep(0.35)
                        continue
                    self.failed.emit(tr('adb devices 失败：{p0}', p0=last_err), gen)
                    return

                lines = [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
                devices = []
                for ln in lines[1:]:
                    parts = ln.split()
                    if len(parts) < 2:
                        continue
                    serial, state = parts[0], parts[1]
                    model = next(
                        (
                            p.split(":", 1)[1]
                            for p in parts[2:]
                            if p.startswith("model:")
                        ),
                        "Android",
                    )
                    devices.append(
                        {"serial": serial, "state": state, "model": model}
                    )

                # ── 自动清理处于 offline 状态的无线 ADB 连接，防止幽灵设备残留 ──
                for d in devices:
                    serial = str(d.get("serial") or "")
                    if d.get("state") == "offline" and is_wifi_serial(serial):
                        try:
                            subprocess.run(
                                [ADB, "disconnect", serial],
                                capture_output=True,
                                text=True,
                                timeout=2,
                            )
                        except Exception:
                            pass
                devices = [
                    d
                    for d in devices
                    if not (
                        d.get("state") == "offline"
                        and is_wifi_serial(str(d.get("serial") or ""))
                    )
                ]

                # ── mDNS 自动发现：降频轮询（每 5 次轮询查 1 次，或手动刷新强制查）──
                self._mdns_counter += 1
                should_check_mdns = force_mdns or (self._mdns_counter % 5 == 1)
                if should_check_mdns:
                    try:
                        mdns = subprocess.run(
                            [ADB, "mdns", "services"],
                            capture_output=True,
                            text=True,
                            timeout=3,
                        )
                        existing_serials = {d["serial"] for d in devices}
                        now = time.monotonic()
                        for line in (mdns.stdout or "").splitlines():
                            # 忽略配对端口，只连接服务端口（_adb-tls-connect._tcp 或 _adb._tcp）
                            if "_adb-tls-pairing" in line:
                                continue
                            # 匹配 IP:端口（兼容制表符/空格及冒号分割）
                            m = re.search(
                                r"(\d{1,3}(?:\.\d{1,3}){3})[:\s]+(\d+)", line
                            )
                            if not m:
                                continue
                            ip, port = m.group(1), int(m.group(2))
                            target = f"{ip}:{port}"
                            if target in existing_serials:
                                continue
                            # 若近期（30秒内）连接该 target 失败过，跳过重试避免轮询阻塞
                            if now - self._failed_targets.get(target, 0) < 30:
                                continue
                            try:
                                conn_res = subprocess.run(
                                    [ADB, "connect", target],
                                    capture_output=True,
                                    text=True,
                                    timeout=3,
                                )
                                conn_out = (
                                    conn_res.stdout + conn_res.stderr
                                ).lower()
                                if "connected" not in conn_out:
                                    self._failed_targets[target] = now
                                else:
                                    self._failed_targets.pop(target, None)
                            except Exception:
                                self._failed_targets[target] = now
                    except Exception:
                        pass

                # ── 去重：同一台设备同时有 USB 和 Wi-Fi 连接时只保留 USB ──
                usb_models = {
                    format_model_name(d["model"])
                    for d in devices
                    if d.get("state") == "device"
                    and not is_wifi_serial(str(d.get("serial") or ""))
                    and not is_emulator_serial(str(d.get("serial") or ""))
                }
                devices = [
                    d
                    for d in devices
                    if not (
                        is_wifi_serial(str(d.get("serial") or ""))
                        and format_model_name(d.get("model") or "")
                        in usb_models
                    )
                ]

                # ── 排序：USB 真机 → Wi-Fi 真机 → 模拟器 → 其他 ────────────
                def _sort_key(d: dict) -> int:
                    s = str(d.get("serial") or "")
                    if is_emulator_serial(s):
                        return 2
                    if is_wifi_serial(s):
                        return 1
                    return 0

                devices.sort(key=_sort_key)

                usb_phones: list[dict[str, str]] = []
                if not any(d.get("state") == "device" for d in devices):
                    # 仅在未就绪时查 USB，避免每次轮询都跑 ioreg
                    usb_phones = detect_usb_android_phones()
                self.finished.emit(
                    {"devices": devices, "usb_phones": usb_phones},
                    gen,
                )
                return
            except Exception as e:
                last_err = str(e)
                if attempt == 0:
                    time.sleep(0.35)
                    continue
                self.failed.emit(tr('检测失败：{p0}', p0=last_err), gen)
                return

