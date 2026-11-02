#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phone Transfer 常量与类型定义"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

ADB_CANDIDATES = [
    Path.home() / "Library/Android/sdk/platform-tools/adb",
    Path("/opt/homebrew/bin/adb"),
    Path("/usr/local/bin/adb"),
]

PHONE_QUICK_PRESETS = [
    ("下载", "/sdcard/Download"),
    ("相册", "/sdcard/DCIM/Camera"),
    ("截屏", "/sdcard/DCIM/Screenshots"),
    ("视频", "/sdcard/Movies"),
    ("音乐", "/sdcard/Music"),
    ("文档", "/sdcard/Documents"),
]

PHONE_CATEGORY_PRESETS = [
    ("all", "全部"),
    ("image", "🖼️ 图片"),
    ("video", "🎬 视频"),
    ("doc", "📄 文档"),
    ("apk", "📦 APK"),
    ("audio", "🎵 音频"),
]

PHONE_CATEGORY_EXTENSIONS: dict[str, set[str]] = {
    "image": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic", ".heif", ".raw", ".cr2", ".nef", ".svg"},
    "video": {".mp4", ".mov", ".mkv", ".avi", ".flv", ".webm", ".m4v", ".wmv", ".3gp", ".ts"},
    "doc": {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".md", ".csv", ".json", ".zip", ".rar", ".7z", ".tar", ".gz"},
    "apk": {".apk", ".apks", ".xapk", ".apkm"},
    "audio": {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".wma", ".opus"},
}

DEST_PRESETS = [
    ("下载", "/sdcard/Download"),
    ("相册", "/sdcard/DCIM/Camera"),
    ("截屏", "/sdcard/DCIM/Screenshots"),
    ("视频", "/sdcard/Movies"),
    ("文档", "/sdcard/Documents"),
]

LOCAL_DEST_PRESETS = [
    ("下载", str(Path.home() / "Downloads")),
    ("桌面", str(Path.home() / "Desktop")),
    ("文稿", str(Path.home() / "Documents")),
]

TransferDirection = Literal["to_phone", "to_computer"]
FolderSyncMode = Literal["overwrite", "keep_both"]
ConnectionUIState = Literal["busy", "online", "empty", "error"]
LogState = Literal["info", "success", "warning", "error", "progress", "device"]

CARD_WIDTH = 320
CARD_HEIGHT = 420
CARD_H_MARGIN = 32  # 卡片左右内边距合计（16px × 2）
CARD_BORDER = 2  # QFrame#card 左右边框各 1px
CARD_INNER_WIDTH = CARD_WIDTH - CARD_H_MARGIN - CARD_BORDER
SWAP_BTN_SIZE = 36
CARDS_ROW_GAP = 8
MAIN_H_MARGIN = 24
CONTENT_WIDTH = CARD_WIDTH * 2 + SWAP_BTN_SIZE + CARDS_ROW_GAP * 2 + CARD_BORDER
WINDOW_WIDTH = CONTENT_WIDTH + MAIN_H_MARGIN * 2

DEVICE_POLL_INTERVAL_MS = 2500
STORAGE_POLL_INTERVAL_MS = 5000
DEVICE_MISS_THRESHOLD = 2
LOG_DETAIL_HEIGHT = 160
TOAST_DURATION_MS = 2200
TOAST_FADE_MS = 300
TRANSFER_PANEL_HEIGHT = 130
PUSH_PARALLEL = 4
MKDIR_BATCH_SIZE = 50

SYMBOL_FONT = "SF Symbols"

FILE_BADGE_COLORS: dict[str, tuple[str, str]] = {
    ".pdf": ("PDF", "#e8685a"),
    ".jpg": ("JPG", "#5aa3ec"),
    ".jpeg": ("JPG", "#5aa3ec"),
    ".png": ("PNG", "#5aa3ec"),
    ".gif": ("GIF", "#5aa3ec"),
    ".heic": ("HEIC", "#5aa3ec"),
    ".mp4": ("MP4", "#9a7cf0"),
    ".mov": ("MOV", "#9a7cf0"),
    ".avi": ("AVI", "#9a7cf0"),
    ".mkv": ("MKV", "#9a7cf0"),
    ".zip": ("ZIP", "#f5a623"),
    ".doc": ("DOC", "#5aa3ec"),
    ".docx": ("DOC", "#5aa3ec"),
    ".txt": ("TXT", "#98989d"),
    ".apk": ("APK", "#34c759"),
}

MEDIA_SCAN_SUFFIXES = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".heic",
    ".heif",
    ".bmp",
    ".dng",
    ".mp4",
    ".mov",
    ".mkv",
    ".avi",
    ".webm",
    ".3gp",
    ".m4v",
    ".mp3",
    ".m4a",
    ".aac",
    ".wav",
    ".flac",
    ".ogg",
    ".opus",
}

_USB_ANDROID_NAME_HINTS = (
    "android",
    "adb",
    "mtp",
    "samsung",
    "xiaomi",
    "huawei",
    "honor",
    "oppo",
    "vivo",
    "oneplus",
    "pixel",
    "nexus",
    "redmi",
    "realme",
    "meizu",
    "zte",
    "lenovo",
    "motorola",
    "moto",
    "sony",
    "xperia",
    "asus",
    "rog",
    "transsion",
    "infinix",
    "tecno",
    "itel",
)

_USB_ANDROID_VENDOR_IDS = {
    "0x04e8",  # Samsung
    "0x2717",  # Xiaomi
    "0x12d1",  # Huawei
    "0x22d9",  # OPPO
    "0x2e04",  # Vivo
    "0x18d1",  # Google
    "0x05c6",  # Qualcomm
    "0x2a70",  # OnePlus
    "0x0fce",  # Sony
    "0x0b05",  # ASUS
    "0x17ef",  # Lenovo
    "0x22b8",  # Motorola
    "0x19d2",  # ZTE
    "0x2ae5",  # Fairphone
    "0x0bb4",  # HTC
    "0x1004",  # LG
}

