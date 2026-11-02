#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手机与本地磁盘存储容量查询"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from phonetransfer.adb.core import adb_cmd
from phonetransfer.utils import human_size


def parse_df_available(raw: str) -> str | None:
    """Parse `df -h` Available column into a display value like '23.4 GB'."""
    raw = raw.strip()
    if not raw or raw in ("-", "—", "Avail", "Available", "Free"):
        return None

    units = {"K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4, "B": 1}
    suffix = raw[-1].upper()
    if suffix in units:
        try:
            num = float(raw[:-1])
            if num >= 0:
                return human_size(int(num * units[suffix]))
        except ValueError:
            return None

    if raw.isdigit():
        return human_size(int(raw) * 1024)
    return None


def parse_stat_f_stdout(text: str) -> str | None:
    """Parse output of `stat -f -c '%a %S'` into human-readable size."""
    parts = text.strip().split()
    if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
        blocks = int(parts[0])
        bsize = int(parts[1])
        if blocks > 0 and bsize > 0:
            return human_size(blocks * bsize)
    return None


def parse_df_stdout(text: str) -> str | None:
    """Extract available space from `adb shell df -h` output."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None

    # Detect column index of 'Avail' / 'Free' from header if present
    avail_col = -1
    for line in lines:
        lower = line.lower()
        if "avail" in lower or "free" in lower:
            cols = [c.lower() for c in line.split()]
            for idx, c in enumerate(cols):
                if "avail" in c or "free" in c:
                    avail_col = idx
                    break
            break

    for line in lines:
        parts = line.split()
        if not parts or parts[0].lower().startswith("filesystem") or parts[0].lower().startswith("size"):
            continue
        if avail_col != -1 and len(parts) > avail_col:
            avail = parse_df_available(parts[avail_col])
            if avail:
                return avail
        if len(parts) >= 4:
            avail = parse_df_available(parts[3])
            if avail:
                return avail
    return None


def query_available_space(remote_path: str, serial: str | None = None) -> str | None:
    """Query free space for a phone path via adb stat or df."""
    # 1. Fast path: Android 6.0+ Toybox stat -f (exact byte calculation, ~30ms)
    stat_cmd = "stat -f -c '%a %S' /sdcard 2>/dev/null || stat -f -c '%a %s' /sdcard 2>/dev/null"
    try:
        r = subprocess.run(
            adb_cmd("shell", stat_cmd, serial=serial),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if r.returncode == 0:
            avail = parse_stat_f_stdout(r.stdout or "")
            if avail:
                return avail
    except (subprocess.TimeoutExpired, OSError):
        pass

    # 2. Candidate paths with df -h
    path = remote_path.rstrip("/") or "/sdcard"
    candidates = [path]
    if path.startswith("/sdcard"):
        candidates.extend(
            [
                path.replace("/sdcard", "/storage/emulated/0", 1),
                "/storage/emulated/0",
                "/storage/emulated",
            ]
        )

    seen: set[str] = set()
    for query in candidates:
        if query in seen:
            continue
        seen.add(query)
        try:
            r = subprocess.run(
                adb_cmd("shell", "df", "-h", query, serial=serial),
                capture_output=True,
                text=True,
                timeout=5,
            )
            if r.returncode == 0:
                avail = parse_df_stdout((r.stdout or "").strip())
                if avail:
                    return avail
        except (subprocess.TimeoutExpired, OSError):
            continue

    # 3. Global df -h
    try:
        r = subprocess.run(
            adb_cmd("shell", "df", "-h", serial=serial),
            capture_output=True,
            text=True,
            timeout=6,
        )
        if r.returncode == 0:
            text = r.stdout or ""
            for line in text.splitlines():
                if "/storage/emulated" in line or "emulated" in line or "/data" in line:
                    avail = parse_df_stdout(line)
                    if avail:
                        return avail
            return parse_df_stdout(text)
    except (subprocess.TimeoutExpired, OSError):
        return None
    return None


def query_local_disk_space(path: str) -> str:
    target = Path(path).expanduser()
    root = target if target.exists() and target.is_dir() else target.parent
    if not str(root):
        root = Path.home()
    try:
        return human_size(shutil.disk_usage(root).free)
    except OSError:
        return "—"

