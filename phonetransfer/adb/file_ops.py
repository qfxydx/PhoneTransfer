#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手机远端与本地文件系统操作、目录遍历与清单构建"""

from __future__ import annotations

import os
import posixpath
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from phonetransfer.adb.core import adb_shell, shell_quote
from phonetransfer.constants import FolderSyncMode, MEDIA_SCAN_SUFFIXES, MKDIR_BATCH_SIZE
from phonetransfer.utils import path_size


@dataclass
class RemoteEntry:
    name: str
    path: str
    is_dir: bool
    size: int
    mtime: float = 0.0


@dataclass
class RemoteManifest:
    files: list[tuple[str, int]]


def parse_ls_mtime(date_s: str, time_s: str) -> float:
    stamp = f"{date_s} {time_s}"
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(stamp, fmt).timestamp()
        except ValueError:
            continue
    return 0.0


def local_entry_time(path: Path) -> float:
    """Prefer birth time (creation) on macOS; fall back to mtime."""
    try:
        st = path.stat()
    except OSError:
        return 0.0
    birth = getattr(st, "st_birthtime", None)
    if isinstance(birth, (int, float)) and birth > 0:
        return float(birth)
    return float(st.st_mtime)


def sort_remote_entries(entries: list[RemoteEntry]) -> list[RemoteEntry]:
    return sorted(entries, key=lambda item: (-item.mtime, item.name.lower()))


def remote_file_size(remote: str) -> int:
    result = adb_shell(f"ls -l {shell_quote(remote)}", timeout=15)
    parts = (result.stdout or "").strip().split()
    if len(parts) >= 5 and parts[4].isdigit():
        return int(parts[4])
    return 0


def list_remote_listing(remote_dir: str) -> tuple[list[RemoteEntry], list[RemoteEntry]]:
    """One-level phone listing via `ls -la`, newest first."""
    remote_dir = remote_dir.rstrip("/")
    result = adb_shell(
        f"ls -la {shell_quote(remote_dir)} 2>/dev/null",
        timeout=60,
    )
    dirs: list[RemoteEntry] = []
    files: list[RemoteEntry] = []
    for line in (result.stdout or "").splitlines():
        line = line.strip()
        if not line or line.startswith("total "):
            continue
        parts = line.split(None, 7)
        if len(parts) < 8:
            continue
        mode = parts[0]
        name = parts[7]
        if " -> " in name:
            name = name.split(" -> ", 1)[0]
        if not name or name in (".", ".."):
            continue
        size = int(parts[4]) if parts[4].isdigit() else 0
        mtime = parse_ls_mtime(parts[5], parts[6])
        path = posixpath.join(remote_dir, name)
        entry = RemoteEntry(name, path, mode.startswith("d"), size, mtime)
        if entry.is_dir:
            dirs.append(entry)
        else:
            files.append(entry)
    return sort_remote_entries(dirs), sort_remote_entries(files)


def list_remote_dirs(remote_dir: str) -> list[RemoteEntry]:
    dirs, _ = list_remote_listing(remote_dir)
    return dirs


def list_remote_files(remote_dir: str) -> list[RemoteEntry]:
    _, files = list_remote_listing(remote_dir)
    return files


def list_remote_dir(remote_dir: str) -> list[RemoteEntry]:
    dirs, files = list_remote_listing(remote_dir)
    return sort_remote_entries(dirs + files)


def resolve_remote_dir(remote_dir: str) -> str:
    """自动解析兼容不同厂商（三星、Pixel、小米等）的相册与截图路径。"""
    remote_dir = remote_dir.strip().rstrip("/")
    if remote_dir == "/sdcard/DCIM/Camera":
        cmd = 'for p in /sdcard/DCIM/Camera /sdcard/DCIM; do [ -d "$p" ] && echo "$p" && break; done'
        res = adb_shell(cmd, timeout=5)
        out = (res.stdout or "").strip()
        if out:
            return out
    elif remote_dir in ("/sdcard/DCIM/Screenshots", "/sdcard/Pictures/Screenshots"):
        cmd = 'for p in /sdcard/DCIM/Screenshots /sdcard/Pictures/Screenshots /sdcard/Pictures; do [ -d "$p" ] && echo "$p" && break; done'
        res = adb_shell(cmd, timeout=5)
        out = (res.stdout or "").strip()
        if out:
            return out
    return remote_dir


def remote_mkdir(remote_dir: str) -> tuple[bool, str]:
    """在手机端内部存储中安全创建新文件夹。"""
    target = remote_dir.strip().rstrip("/")
    if not target:
        return False, "文件夹路径不能为空"
    if not (target.startswith("/sdcard/") or target.startswith("/storage/")):
        return False, "仅允许在手机内部存储 (/sdcard/ 或 /storage/) 内创建文件夹"

    base_name = posixpath.basename(target)
    if not base_name or any(c in base_name for c in ("\0", ":", "*", "?", '"', "<", ">", "|", "\\")):
        return False, "文件夹名称包含非法字符"

    res = adb_shell(f"mkdir -p {shell_quote(target)}", timeout=15)
    if res.returncode != 0:
        err = (res.stderr or res.stdout or "创建文件夹失败").strip()
        return False, err
    return True, ""


def remote_rename(old_path: str, new_path: str) -> tuple[bool, str]:
    """在手机端重命名文件或文件夹，并同步刷新媒体库。"""
    old_p = old_path.strip().rstrip("/")
    new_p = new_path.strip().rstrip("/")
    if not old_p or not new_p:
        return False, "路径不能为空"
    if not (old_p.startswith("/sdcard/") or old_p.startswith("/storage/")):
        return False, "仅允许重命名手机内部存储中的项目"
    if not (new_p.startswith("/sdcard/") or new_p.startswith("/storage/")):
        return False, "目标路径不合法"
    if old_p == new_p:
        return True, ""

    new_name = posixpath.basename(new_p)
    if not new_name or any(c in new_name for c in ("\0", ":", "*", "?", '"', "<", ">", "|", "\\", "/")):
        return False, "新名称包含非法字符"

    res = adb_shell(f"mv {shell_quote(old_p)} {shell_quote(new_p)}", timeout=15)
    if res.returncode != 0:
        err = (res.stderr or res.stdout or "重命名失败").strip()
        return False, err

    ext_old = posixpath.splitext(old_p)[1].lower()
    ext_new = posixpath.splitext(new_p)[1].lower()
    if ext_old in MEDIA_SCAN_SUFFIXES or ext_new in MEDIA_SCAN_SUFFIXES:
        try:
            from phonetransfer.adb.media import scan_media_paths
            scan_media_paths([old_p, new_p])
        except Exception:
            pass

    return True, ""


FORBIDDEN_DELETE_PATHS = {
    "/",
    "/sdcard",
    "/sdcard/",
    "/storage",
    "/storage/",
    "/storage/emulated",
    "/storage/emulated/0",
    "/system",
    "/data",
    "/vendor",
    "/dev",
    "/etc",
    "/proc",
    "/sys",
}


def remote_delete(paths: list[str]) -> tuple[bool, str]:
    """在手机端安全删除文件或文件夹（防误删系统/存储根目录），并同步通知媒体库。"""
    if not paths:
        return False, "未选择要删除的项目"

    valid_paths: list[str] = []
    for p in paths:
        cleaned = p.strip().rstrip("/")
        if not cleaned:
            continue
        if cleaned in FORBIDDEN_DELETE_PATHS:
            return False, f"禁止删除系统或存储根目录：{cleaned}"
        if not (cleaned.startswith("/sdcard/") or cleaned.startswith("/storage/")):
            return False, f"仅允许删除手机内部存储的项目：{cleaned}"
        rel_sdcard = posixpath.relpath(cleaned, "/sdcard")
        rel_storage = posixpath.relpath(cleaned, "/storage/emulated/0")
        if rel_sdcard in (".", "..", "/") and rel_storage in (".", "..", "/"):
            return False, f"禁止删除根存储目录：{cleaned}"
        valid_paths.append(cleaned)

    if not valid_paths:
        return False, "未找到有效的删除路径"

    chunk_size = 50
    for i in range(0, len(valid_paths), chunk_size):
        chunk = valid_paths[i : i + chunk_size]
        quoted = " ".join(shell_quote(item) for item in chunk)
        res = adb_shell(f"rm -rf {quoted}", timeout=30)
        if res.returncode != 0:
            err = (res.stderr or res.stdout or "删除失败").strip()
            return False, err

    media_paths = [p for p in valid_paths if posixpath.splitext(p)[1].lower() in MEDIA_SCAN_SUFFIXES]
    if media_paths:
        try:
            from phonetransfer.adb.media import scan_media_paths
            scan_media_paths(media_paths)
        except Exception:
            pass

    return True, ""


def build_remote_manifest(root: str) -> RemoteManifest:
    """批量获取远端目录下的所有文件及其大小。"""
    root = root.rstrip("/")
    files: list[tuple[str, int]] = []

    # 1. 优先尝试 stat -c "%s %n"（Android 6+ toybox 原生支持，1 次 ADB 调用完成所有文件大小与路径统计）
    cmd_stat = f"find {shell_quote(root)} -type f -exec stat -c '%s %n' {{}} + 2>/dev/null"
    res = adb_shell(cmd_stat, timeout=120)
    stdout = (res.stdout or "").strip()
    if stdout:
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split(" ", 1)
            if len(parts) == 2 and parts[0].isdigit():
                files.append((parts[1], int(parts[0])))
        if files:
            return RemoteManifest(files)

    # 2. 备选：find ... -exec ls -ld {} + 批量输出
    cmd_ls = f"find {shell_quote(root)} -type f -exec ls -ld {{}} + 2>/dev/null"
    res_ls = adb_shell(cmd_ls, timeout=120)
    stdout_ls = (res_ls.stdout or "").strip()
    if stdout_ls:
        for line in stdout_ls.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split(None, 7)
            if len(parts) >= 8 and parts[4].isdigit():
                files.append((parts[7], int(parts[4])))
        if files:
            return RemoteManifest(files)

    # 3. 兜底方案：find -type f 先列出路径，再按 50 个一组批量 ls -ld，避免 N 次 subprocess 调用
    res_find = adb_shell(f"find {shell_quote(root)} -type f 2>/dev/null", timeout=120)
    paths = [ln.strip() for ln in (res_find.stdout or "").splitlines() if ln.strip()]
    if not paths:
        return RemoteManifest([])

    chunk_size = 50
    for i in range(0, len(paths), chunk_size):
        chunk = paths[i : i + chunk_size]
        quoted = " ".join(shell_quote(p) for p in chunk)
        chunk_res = adb_shell(f"ls -ld {quoted} 2>/dev/null", timeout=30)
        for line in (chunk_res.stdout or "").splitlines():
            parts = line.strip().split(None, 7)
            if len(parts) >= 8 and parts[4].isdigit():
                files.append((parts[7], int(parts[4])))

    recorded = {p for p, _ in files}
    for p in paths:
        if p not in recorded:
            files.append((p, 0))

    return RemoteManifest(files)


def manifest_remote_bytes(manifest: RemoteManifest) -> int:
    return sum(size for _, size in manifest.files)


def count_pull_totals(remotes: list[str]) -> tuple[int, int]:
    total_bytes = 0
    total_files = 0
    for remote in remotes:
        if remote_is_dir(remote):
            manifest = build_remote_manifest(remote)
            total_files += len(manifest.files)
            total_bytes += manifest_remote_bytes(manifest)
        elif remote_is_file(remote):
            total_files += 1
            total_bytes += remote_file_size(remote)
    return max(total_bytes, 1), max(total_files, 1)


def remote_exists(remote: str) -> bool:
    remote = remote.strip()
    if not remote:
        return False
    result = adb_shell(f"test -e {shell_quote(remote)}")
    return result.returncode == 0


def remote_is_dir(remote: str) -> bool:
    remote = remote.strip()
    if not remote:
        return False
    result = adb_shell(f"test -d {shell_quote(remote)}")
    return result.returncode == 0


def remote_is_file(remote: str) -> bool:
    remote = remote.strip()
    if not remote:
        return False
    result = adb_shell(f"test -f {shell_quote(remote)}")
    return result.returncode == 0


def ensure_remote_dir(dest: str) -> tuple[bool, str]:
    dest = dest.rstrip("/")
    if not dest.startswith("/"):
        return False, f"目标路径需以 / 开头，例如 /sdcard/Download（当前：{dest}）"
    result = adb_shell(f"mkdir -p {shell_quote(dest)}")
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        return False, f"无法创建手机目录 {dest}：{err or '未知错误'}"
    if not remote_exists(dest):
        return False, f"手机目录不存在或无法访问：{dest}"
    return True, ""


def ensure_remote_dirs(parents: set[str]) -> None:
    ordered = sorted(parents)
    for start in range(0, len(ordered), MKDIR_BATCH_SIZE):
        chunk = ordered[start : start + MKDIR_BATCH_SIZE]
        cmd = " && ".join(f"mkdir -p {shell_quote(path)}" for path in chunk)
        adb_shell(cmd, timeout=120)


def ensure_local_dir(dest: str) -> tuple[bool, str]:
    path = Path(dest).expanduser()
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return False, f"无法创建电脑目录 {path}：{exc}"
    if not path.is_dir():
        return False, f"电脑目标路径不是文件夹：{path}"
    return True, ""


def timestamped_basename(name: str, attempt: int) -> str:
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    stem = Path(name).stem
    suffix = Path(name).suffix
    if attempt == 0:
        return f"{stem}{ts}{suffix}"
    return f"{stem}{ts}_{attempt + 1}{suffix}"


def resolve_remote_path(
    dest: str,
    name: str,
    is_dir: bool,
    log,
    *,
    sync_mode: FolderSyncMode = "overwrite",
) -> str:
    """Resolve target path: folders merge into existing; files follow sync_mode."""
    dest = dest.rstrip("/")
    remote = f"{dest}/{name}"

    if is_dir:
        if remote_is_dir(remote):
            log(f"同步到已有文件夹：{name}")
            return remote
        if remote_is_file(remote):
            raise RuntimeError(f"无法同步，同名路径已被文件占用：{name}")
        return remote

    if not remote_exists(remote):
        return remote

    if sync_mode == "overwrite":
        log(f"覆盖同名文件：{name}")
        return remote

    log(f"目标文件已存在：{name}")
    for attempt in range(99):
        new_name = timestamped_basename(name, attempt)
        candidate = f"{dest}/{new_name}"
        if not remote_exists(candidate):
            log(f"重命名为 {new_name}")
            return candidate
    raise RuntimeError(f"无法为 {name} 生成唯一文件名")


def resolve_local_path(
    dest: str,
    name: str,
    is_dir: bool,
    log,
    *,
    sync_mode: FolderSyncMode = "overwrite",
) -> Path:
    base = Path(dest).expanduser()
    candidate = base / name
    if is_dir:
        if candidate.is_dir():
            log(f"同步到已有文件夹：{name}")
            return candidate
        if candidate.is_file():
            raise RuntimeError(f"无法同步，同名路径已被文件占用：{name}")
        return candidate

    if not candidate.exists():
        return candidate

    if sync_mode == "overwrite":
        log(f"覆盖同名文件：{name}")
        return candidate

    log(f"目标文件已存在：{name}")
    for attempt in range(99):
        new_name = timestamped_basename(name, attempt)
        alt = base / new_name
        if not alt.exists():
            log(f"重命名为 {new_name}")
            return alt
    raise RuntimeError(f"无法为 {name} 生成唯一文件名")


def should_skip_upload(rel: str) -> bool:
    for part in rel.split("/"):
        if part == ".DS_Store" or part.startswith("._") or part == "__MACOSX":
            return True
    return False


def resolve_push_source(path: Path) -> Path | None:
    if path.is_symlink():
        try:
            target = path.resolve()
        except OSError:
            return None
        return target if target.is_file() else None
    if path.is_file():
        return path
    return None


@dataclass
class PushManifest:
    files: list[tuple[Path, str]]
    symlink_count: int


def build_push_manifest(root: Path) -> PushManifest:
    """一次遍历：收集待传文件、解析符号链接目标、统计链接数量。"""
    if not root.is_dir():
        return PushManifest([], 0)
    files: list[tuple[Path, str]] = []
    symlink_count = 0
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            symlink_count += 1
        src = resolve_push_source(path)
        if src is None:
            continue
        rel = path.relative_to(root).as_posix()
        if should_skip_upload(rel):
            continue
        files.append((src, rel))
    return PushManifest(files, symlink_count)


def iter_local_files(root: Path) -> list[tuple[Path, str]]:
    return build_push_manifest(root).files


def verify_local_file(path: Path) -> tuple[bool, str]:
    src = path
    if path.is_symlink():
        try:
            src = path.resolve()
        except OSError:
            return False, f"符号链接无效：{path.name}"
    try:
        with src.open("rb") as handle:
            handle.read(1)
    except OSError:
        return False, f"无法读取「{path.name}」，请确认文件已下载到本机（iCloud 文件需先点开下载）"
    return True, ""


def verify_local_pushable(path: Path) -> tuple[bool, str]:
    if not path.exists():
        return False, f"本地路径不存在：{path}"
    if path.is_dir():
        for file_path, rel in iter_local_files(path):
            ok, err = verify_local_file(file_path)
            if not ok:
                return False, f"{err}\n路径：{rel}"
        return True, ""
    return verify_local_file(path)

