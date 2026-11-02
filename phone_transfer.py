#!/usr/bin/env python3
"""Phone Transfer: macOS ADB 文件互传工具。

重构说明：
本项目代码已模块化拆分为 `phonetransfer/` 包：
- `phonetransfer.constants`: 尺寸、超时、预设路径、分类常量
- `phonetransfer.utils`: 阴影、图标、格式化、macOS 原生选择器桥接
- `phonetransfer.adb`: 底层 ADB 命令行封装、存储探测、文件清单、媒体库刷新、推拉传输
- `phonetransfer.workers`: QThread 异步探测与传输 Worker
- `phonetransfer.ui`: 主窗口、各类卡片、日志、Toast、无线 ADB 对话框

本文件作为根目录入口及向后兼容层，重导出所有公共 API，
确保无论是 `python3 phone_transfer.py` 还是任何依赖旧符号的代码与自动化脚本均 100% 兼容。
"""

from __future__ import annotations

import sys

# 1. 常量
from phonetransfer.constants import (
    ADB_CANDIDATES,
    CARD_BORDER,
    CARD_HEIGHT,
    CARD_H_MARGIN,
    CARD_INNER_WIDTH,
    CARD_WIDTH,
    CARDS_ROW_GAP,
    ConnectionUIState,
    CONTENT_WIDTH,
    DEST_PRESETS,
    DEVICE_MISS_THRESHOLD,
    DEVICE_POLL_INTERVAL_MS,
    FILE_BADGE_COLORS,
    FolderSyncMode,
    LOCAL_DEST_PRESETS,
    LOG_DETAIL_HEIGHT,
    LogState,
    MAIN_H_MARGIN,
    MEDIA_SCAN_SUFFIXES,
    MKDIR_BATCH_SIZE,
    PUSH_PARALLEL,
    STORAGE_POLL_INTERVAL_MS,
    SWAP_BTN_SIZE,
    SYMBOL_FONT,
    TOAST_DURATION_MS,
    TOAST_FADE_MS,
    TRANSFER_PANEL_HEIGHT,
    TransferDirection,
    WINDOW_WIDTH,
    _USB_ANDROID_NAME_HINTS,
    _USB_ANDROID_VENDOR_IDS,
)

# 2. 通用工具
from phonetransfer.utils import (
    PROJECT_ROOT,
    _path_size_cache,
    card_shadow,
    file_badge,
    human_size,
    path_size,
    pick_files_and_folders,
    picker_helper_path,
    resolve_app_icon,
    resolve_symbol_font,
    send_macos_notification,
    sym,
)

# 3. ADB 底层模块
from phonetransfer.adb.core import (
    ADB,
    adb_cmd,
    adb_shell,
    device_display_name,
    explain_adb_device_state,
    find_adb,
    format_model_name,
    get_active_serial,
    is_emulator_serial,
    is_wifi_serial,
    pick_preferred_device,
    set_active_serial,
    shell_quote,
)
from phonetransfer.adb.storage import (
    parse_df_available,
    parse_df_stdout,
    query_available_space,
    query_local_disk_space,
)
from phonetransfer.adb.file_ops import (
    RemoteEntry,
    RemoteManifest,
    build_push_manifest,
    build_remote_manifest,
    count_pull_totals,
    ensure_local_dir,
    ensure_remote_dir,
    ensure_remote_dirs,
    iter_local_files,
    list_remote_dir,
    list_remote_dirs,
    list_remote_files,
    list_remote_listing,
    local_entry_time,
    manifest_remote_bytes,
    parse_ls_mtime,
    remote_exists,
    remote_file_size,
    remote_is_dir,
    remote_is_file,
    resolve_local_path,
    resolve_push_source,
    resolve_remote_path,
    should_skip_upload,
    sort_remote_entries,
    timestamped_basename,
    verify_local_file,
    verify_local_pushable,
)
from phonetransfer.adb.media import (
    collect_remote_media_paths,
    is_media_scan_path,
    refresh_phone_media,
    scan_remote_media_file,
    to_media_store_path,
)
from phonetransfer.adb.transfer import (
    FileProgressTracker,
    collect_pull_conflicts,
    collect_sync_conflicts,
    pull_folder,
    pull_folder_files,
    pull_one,
    push_folder,
    push_folder_files,
    push_one,
    run_adb_pull,
    run_adb_push,
)

# 4. 后台 Worker
from phonetransfer.workers.base import (
    _UI,
    dispose_qthread_pair,
    reclaim_qobject_to_main,
)
from phonetransfer.workers.apk_worker import ApkInstallWorker, explain_apk_error
from phonetransfer.workers.device_worker import DeviceWorker
from phonetransfer.workers.phone_list_worker import PhoneListWorker
from phonetransfer.workers.preview_worker import RemotePreviewWorker
from phonetransfer.workers.storage_worker import StorageWorker
from phonetransfer.workers.transfer_worker import TransferWorker
from phonetransfer.workers.wifi_worker import WifiActionWorker

# 5. UI 界面与控件
from phonetransfer.ui.theme import AppTheme
from phonetransfer.ui.quicklook import QuickLookManager
from phonetransfer.ui.widgets.transfer_arrow import TransferArrow
from phonetransfer.ui.widgets.toast import TransferToast
from phonetransfer.ui.widgets.log_list import (
    LOG_KIND_META,
    LogDetailList,
    ParsedLogEntry,
    _parse_adb_push_summary,
    parse_log_line,
)
from phonetransfer.ui.widgets.cards import (
    BrowseEntryRow,
    DestinationCard,
    LocalDestinationCard,
    PhoneSourceCard,
    SourceCard,
)
from phonetransfer.ui.dialogs.wifi_dialog import WifiConnectDialog
from phonetransfer.ui.main_window import MainWindow

# 6. 入口主函数
from phonetransfer.main import main


if __name__ == "__main__":
    main()
