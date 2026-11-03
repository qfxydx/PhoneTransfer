#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手机 MediaStore 媒体库广播与刷新"""

from __future__ import annotations

from phonetransfer.i18n import tr

import subprocess
from pathlib import Path
from typing import Callable

from phonetransfer.adb.core import adb_shell, shell_quote
from phonetransfer.adb.file_ops import remote_is_dir, remote_is_file
from phonetransfer.constants import MEDIA_SCAN_SUFFIXES


def to_media_store_path(remote: str) -> str:
    """Normalize adb paths to the absolute form MediaStore expects."""
    remote = remote.strip()
    if remote.startswith("/sdcard/") or remote == "/sdcard":
        return "/storage/emulated/0" + remote[len("/sdcard") :]
    if remote.startswith("/storage/self/primary/") or remote == "/storage/self/primary":
        return "/storage/emulated/0" + remote[len("/storage/self/primary") :]
    return remote


def is_media_scan_path(path: str) -> bool:
    return Path(path).suffix.lower() in MEDIA_SCAN_SUFFIXES


def collect_remote_media_paths(remote: str) -> list[str]:
    """Return media file paths under a pushed file or folder."""
    remote = remote.rstrip("/")
    if not remote:
        return []
    if remote_is_file(remote):
        return [remote] if is_media_scan_path(remote) else []
    if not remote_is_dir(remote):
        return []
    try:
        result = adb_shell(
            f"find {shell_quote(remote)} -type f 2>/dev/null",
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return []
    paths: list[str] = []
    for line in (result.stdout or "").splitlines():
        path = line.strip()
        if path and is_media_scan_path(path):
            paths.append(path)
    return paths


def scan_remote_media_file(remote: str) -> bool:
    """Ask MediaStore to index one file so Gallery can show it immediately."""
    path = to_media_store_path(remote)
    try:
        result = adb_shell(
            "content call --uri content://media/external/file "
            f"--method scan_file --arg {shell_quote(path)}",
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        result = None
    text = ""
    if result is not None:
        text = f"{result.stdout or ''}{result.stderr or ''}"
        if result.returncode == 0 and "Exception" not in text and "Error:" not in text:
            return True
    # Legacy fallback used by older Android / OEM gallery apps.
    try:
        fallback = adb_shell(
            "am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE "
            f"-d {shell_quote('file://' + path)}",
            timeout=15,
        )
    except subprocess.TimeoutExpired:
        return False
    return fallback.returncode == 0


def refresh_phone_media(
    remotes: list[str],
    log: Callable[[str], None] | None = None,
) -> int:
    """Scan newly pushed media so Photos / Gallery can see them without waiting."""
    ordered: list[str] = []
    seen: set[str] = set()
    for remote in remotes:
        for path in collect_remote_media_paths(remote):
            key = to_media_store_path(path)
            if key in seen:
                continue
            seen.add(key)
            ordered.append(path)
    if not ordered:
        return 0
    if log:
        log(tr('刷新媒体库（{p0} 个）…', p0=len(ordered)))
    scanned = 0
    for path in ordered:
        if scan_remote_media_file(path):
            scanned += 1
    if log:
        if scanned:
            log(tr('已刷新媒体，相册/图库中应可立即看到'))
        else:
            log(tr('媒体库刷新未确认成功，可在手机上下拉刷新相册后再看'))
    return scanned

