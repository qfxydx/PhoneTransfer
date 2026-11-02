#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文件上传 (push) 与下载 (pull) 核心传输逻辑、冲突检测与进度管理"""

from __future__ import annotations

import os
import posixpath
import shutil
import subprocess
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

from phonetransfer.adb.core import (
    adb_cmd,
    adb_shell,
    format_adb_failure,
    shell_quote,
)
from phonetransfer.adb.file_ops import (
    PushManifest,
    RemoteManifest,
    build_push_manifest,
    build_remote_manifest,
    ensure_local_dir,
    ensure_remote_dir,
    ensure_remote_dirs,
    iter_local_files,
    manifest_remote_bytes,
    remote_file_size,
    remote_is_dir,
    remote_is_file,
    resolve_local_path,
    resolve_remote_path,
    timestamped_basename,
)
from phonetransfer.constants import FolderSyncMode, PUSH_PARALLEL
from phonetransfer.utils import path_size


def run_adb_push_quiet(
    local_path: str,
    remote_path: str,
    cancel_check: Callable[[], bool] | None = None,
) -> tuple[bool, str]:
    """Parallel uploads must be cancellable even when adb emits no output."""
    try:
        proc = subprocess.Popen(
            adb_cmd("push", local_path, remote_path),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError as exc:
        return False, str(exc)
    try:
        while True:
            if cancel_check is not None and cancel_check():
                proc.kill()
                proc.communicate()
                return False, "已取消"
            try:
                stdout, stderr = proc.communicate(timeout=0.25)
                return proc.returncode == 0, f"{stdout or ''}{stderr or ''}".strip()
            except subprocess.TimeoutExpired:
                continue
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.communicate()


def materialize_resolved_tree(manifest: PushManifest, staging: Path) -> int:
    """在临时目录按相对路径硬链接真实文件；跨盘时复制。返回复制（非硬链）的文件数。"""
    copied = 0
    for src, rel in manifest.files:
        dest = staging / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            continue
        try:
            os.link(src, dest)
        except OSError:
            shutil.copy2(src, dest)
            copied += 1
    return copied


def manifest_total_bytes(manifest: PushManifest) -> int:
    seen: set[Path] = set()
    total = 0
    for src, _ in manifest.files:
        key = src.resolve()
        if key in seen:
            continue
        seen.add(key)
        try:
            total += key.stat().st_size
        except OSError:
            pass
    return total


def count_transfer_totals(locals: list[str]) -> tuple[int, int]:
    total_bytes = 0
    total_files = 0
    for local in locals:
        path = Path(local)
        if path.is_dir():
            manifest = build_push_manifest(path)
            total_files += len(manifest.files)
            total_bytes += manifest_total_bytes(manifest)
        elif path.is_file():
            total_files += 1
            total_bytes += path_size(path)
    return max(total_bytes, 1), max(total_files, 1)


class FileProgressTracker:
    def __init__(
        self,
        total_bytes: int,
        total_files: int,
        emit: Callable[[int, int, int, int, str], None],
    ) -> None:
        self.total_bytes = max(total_bytes, 1)
        self.total_files = max(total_files, 1)
        self.done_bytes = 0
        self.done_files = 0
        self._emit = emit
        self._lock = threading.Lock()

    def _emit_progress(self, name: str) -> None:
        self._emit(
            self.done_bytes,
            self.total_bytes,
            self.done_files,
            self.total_files,
            name,
        )

    def report(self, name: str) -> None:
        with self._lock:
            self._emit_progress(name)

    def file_completed(self, name: str, file_bytes: int = 0, count: int = 1) -> None:
        with self._lock:
            self.done_bytes = min(self.done_bytes + file_bytes, self.total_bytes)
            self.done_files = min(self.done_files + count, self.total_files)
            self._emit_progress(name)

    def bulk_push(
        self,
        name: str,
        file_count: int,
        batch_bytes: int,
        cancel_check,
        push_fn: Callable[[], tuple[bool, list[str]]],
    ) -> tuple[bool, list[str]]:
        if batch_bytes <= 0 and file_count <= 0:
            return push_fn()

        base_bytes = self.done_bytes
        base_files = self.done_files
        stop = threading.Event()

        def estimate() -> None:
            start = time.monotonic()
            estimate_secs = batch_bytes / (35 * 1024 * 1024) if batch_bytes else 1.0
            estimate_secs = max(estimate_secs, 0.5)
            while not stop.wait(0.3):
                if cancel_check():
                    return
                elapsed = time.monotonic() - start
                fraction = min(0.97, elapsed / estimate_secs)
                est_bytes = base_bytes + int(batch_bytes * fraction)
                with self._lock:
                    self._emit(
                        min(est_bytes, self.total_bytes),
                        self.total_bytes,
                        base_files,
                        self.total_files,
                        name,
                    )

        self.report(name)
        thread = threading.Thread(target=estimate, daemon=True)
        thread.start()
        try:
            ok, lines = push_fn()
        finally:
            stop.set()
            thread.join(timeout=1.0)
        if ok:
            with self._lock:
                self.done_bytes = min(base_bytes + batch_bytes, self.total_bytes)
                self.done_files = min(base_files + file_count, self.total_files)
                self._emit_progress(name)
        return ok, lines

    def bulk_pull(
        self,
        name: str,
        file_count: int,
        batch_bytes: int,
        cancel_check,
        pull_fn: Callable[[], tuple[bool, list[str]]],
    ) -> tuple[bool, list[str]]:
        return self.bulk_push(
            name, file_count, batch_bytes, cancel_check, pull_fn
        )


def push_folder_via_staging(
    local: Path,
    remote: str,
    manifest: PushManifest,
    log,
    cancel_check,
    *,
    progress: FileProgressTracker | None = None,
) -> tuple[bool, str]:
    with tempfile.TemporaryDirectory(prefix="phonetransfer_") as tmp:
        staging = Path(tmp)
        log(
            f"批量解析完成：{len(manifest.files)} 个文件"
            f"（含 {manifest.symlink_count} 个符号链接）"
        )
        log("正在生成传输清单…")
        copied = materialize_resolved_tree(manifest, staging)
        if copied:
            log(f"其中 {copied} 个文件需复制（跨磁盘），其余使用硬链接")
        if cancel_check():
            return False, "已取消"
        log("整包传输中…")
        push_args = (f"{staging}/.", f"{remote}/", log, cancel_check)
        if progress:
            ok, lines = progress.bulk_push(
                local.name,
                len(manifest.files),
                manifest_total_bytes(manifest),
                cancel_check,
                lambda: run_adb_push(*push_args),
            )
        else:
            ok, lines = run_adb_push(*push_args)
        if not ok:
            return False, format_adb_failure(lines, local, remote)
    return True, remote


def list_remote_relative_files(remote_dir: str) -> set[str]:
    """Recursive relative file paths under remote_dir (for conflict checks)."""
    remote_dir = remote_dir.rstrip("/")
    if not remote_is_dir(remote_dir):
        return set()
    try:
        result = adb_shell(
            f"find {shell_quote(remote_dir)} -type f 2>/dev/null",
            timeout=180,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("读取手机文件夹内容超时，请稍后重试")
    prefix = remote_dir + "/"
    rels: set[str] = set()
    for line in (result.stdout or "").splitlines():
        line = line.strip()
        if line.startswith(prefix):
            rels.add(line[len(prefix) :])
    return rels


def find_folder_conflicts(local: str, dest: str) -> list[str]:
    root = Path(local)
    remote_base = f"{dest.rstrip('/')}/{root.name}"
    if not remote_is_dir(remote_base):
        return []
    local_rels = {rel for _, rel in iter_local_files(root)}
    return sorted(local_rels & list_remote_relative_files(remote_base))


def find_file_conflict(local: str, dest: str) -> str | None:
    path = Path(local)
    if path.is_dir():
        return None
    remote = f"{dest.rstrip('/')}/{path.name}"
    if remote_is_file(remote):
        return path.name
    return None


def collect_sync_conflicts(locals: list[str], dest: str) -> list[str]:
    conflicts: list[str] = []
    for local in locals:
        path = Path(local)
        if path.is_dir():
            for rel in find_folder_conflicts(local, dest):
                conflicts.append(f"{path.name}/{rel}")
        else:
            name = find_file_conflict(local, dest)
            if name:
                conflicts.append(name)
    return sorted(conflicts)


def run_adb_push(
    local_path: str, remote_path: str, log, cancel_check
) -> tuple[bool, list[str]]:
    proc = subprocess.Popen(
        adb_cmd("push", local_path, remote_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    lines: list[str] = []
    for line in proc.stdout:
        if cancel_check():
            proc.kill()
            return False, lines
        line = line.rstrip()
        if line:
            lines.append(line)
            log(line)
    if proc.wait() != 0:
        return False, lines
    return True, lines


def push_folder_files(
    local: Path,
    remote: str,
    sync_mode: FolderSyncMode,
    log,
    cancel_check,
    *,
    manifest: PushManifest | None = None,
    progress: FileProgressTracker | None = None,
) -> tuple[bool, str]:
    if manifest is None:
        manifest = build_push_manifest(local)
    files = manifest.files
    if not files:
        log("文件夹为空，无需传输")
        return True, remote

    parents: set[str] = set()
    for _, rel in files:
        parent = posixpath.dirname(f"{remote.rstrip('/')}/{rel}")
        if parent:
            parents.add(parent)
    ensure_remote_dirs(parents)

    mode_label = "覆盖" if sync_mode == "overwrite" else "两者都保留"
    total = len(files)
    log(f"同步 {total} 个文件（{mode_label}）")
    if progress:
        progress.report(local.name)

    if sync_mode == "keep_both":
        return _push_folder_files_sequential(
            files, remote, sync_mode, log, cancel_check, progress=progress
        )
    return _push_folder_files_parallel(
        files, remote, local, log, cancel_check, progress=progress
    )


def _push_folder_files_sequential(
    files: list[tuple[Path, str]],
    remote: str,
    sync_mode: FolderSyncMode,
    log,
    cancel_check,
    *,
    progress: FileProgressTracker | None = None,
) -> tuple[bool, str]:
    for abs_path, rel in files:
        if cancel_check():
            return False, "已取消"
        remote_file = f"{remote.rstrip('/')}/{rel}"
        if sync_mode == "keep_both" and remote_is_file(remote_file):
            name = posixpath.basename(rel)
            parent = posixpath.dirname(remote_file)
            parent_dir = parent if parent else remote.rstrip("/")
            remote_file = resolve_remote_path(
                parent_dir, name, False, log, sync_mode="keep_both"
            )
        file_bytes = path_size(abs_path)
        if progress:
            ok, lines = progress.bulk_push(
                rel,
                1,
                file_bytes,
                cancel_check,
                lambda src=str(abs_path), dst=remote_file: run_adb_push(
                    src, dst, log, cancel_check
                ),
            )
        else:
            ok, lines = run_adb_push(str(abs_path), remote_file, log, cancel_check)
        if not ok:
            return False, format_adb_failure(lines, abs_path, remote_file)
    return True, remote


def _push_folder_files_parallel(
    files: list[tuple[Path, str]],
    remote: str,
    local: Path,
    log,
    cancel_check,
    *,
    progress: FileProgressTracker | None = None,
) -> tuple[bool, str]:
    total = len(files)
    done = 0
    milestone = max(1, total // 10)
    failed: tuple[str, str] | None = None
    stop = threading.Event()

    def should_stop() -> bool:
        return stop.is_set() or cancel_check()

    def push_one(item: tuple[Path, str]) -> tuple[str, bool, str, int]:
        abs_path, rel = item
        remote_file = f"{remote.rstrip('/')}/{rel}"
        if should_stop():
            return rel, False, "已取消", 0
        ok, output = run_adb_push_quiet(str(abs_path), remote_file, should_stop)
        return rel, ok, output, path_size(abs_path)

    with ThreadPoolExecutor(max_workers=PUSH_PARALLEL) as executor:
        futures = [executor.submit(push_one, item) for item in files]
        for future in as_completed(futures):
            if cancel_check():
                failed = ("", "已取消")
                stop.set()
                for pending in futures:
                    pending.cancel()
                break
            if future.cancelled():
                continue
            rel, ok, output, size = future.result()
            done += 1
            if not ok and failed is None:
                failed = (rel, output)
                stop.set()
                for pending in futures:
                    pending.cancel()
            if progress and ok:
                progress.file_completed(rel, size)
            elif progress is None and (done % milestone == 0 or done == total):
                log(f"已处理 {done}/{total} 个文件")

    if failed:
        rel, output = failed
        if output == "已取消":
            return False, "已取消"
        sample = files[0][0] if files else local
        return False, format_adb_failure(
            [output], sample, f"{remote.rstrip('/')}/{rel}"
        )
    return True, remote


def push_folder(
    local: Path,
    remote: str,
    sync_mode: FolderSyncMode,
    log,
    cancel_check,
    *,
    progress: FileProgressTracker | None = None,
) -> tuple[bool, str]:
    mkdir = adb_shell(f"mkdir -p {shell_quote(remote)}")
    if not remote_is_dir(remote):
        mkdir_err = (mkdir.stderr or mkdir.stdout or "").strip()
        if remote_is_file(remote):
            return False, f"无法创建手机目录，同名路径已被文件占用：{remote}"
        return False, f"无法创建手机目录 {remote}：{mkdir_err or '未知错误'}"

    manifest = build_push_manifest(local)
    if not manifest.files:
        log("文件夹为空，无需传输")
        return True, remote

    if sync_mode == "overwrite":
        if manifest.symlink_count == 0:
            push_args = (f"{local}/.", f"{remote}/", log, cancel_check)
            if progress:
                ok, lines = progress.bulk_push(
                    local.name,
                    len(manifest.files),
                    manifest_total_bytes(manifest),
                    cancel_check,
                    lambda: run_adb_push(*push_args),
                )
            else:
                ok, lines = run_adb_push(*push_args)
            if not ok:
                return False, format_adb_failure(lines, local, remote)
            return True, remote
        ok, msg = push_folder_via_staging(
            local, remote, manifest, log, cancel_check, progress=progress
        )
        if ok:
            return True, msg
        log("整包传输失败，改为逐文件传输…")
        return push_folder_files(
            local,
            remote,
            sync_mode,
            log,
            cancel_check,
            manifest=manifest,
            progress=progress,
        )

    return push_folder_files(
        local,
        remote,
        sync_mode,
        log,
        cancel_check,
        manifest=manifest,
        progress=progress,
    )


def push_one(
    local: str,
    dest: str,
    log,
    cancel_check,
    *,
    folder_sync_mode: FolderSyncMode = "overwrite",
    progress: FileProgressTracker | None = None,
) -> tuple[bool, str]:
    if cancel_check():
        return False, "已取消"

    src = Path(local)
    if not src.exists():
        return False, f"本地文件不存在：{local}"

    dest = dest.rstrip("/")
    ok, err = ensure_remote_dir(dest)
    if not ok:
        log(err)
        return False, err

    is_dir = src.is_dir()
    try:
        remote = resolve_remote_path(
            dest, src.name, is_dir, log, sync_mode=folder_sync_mode
        )
    except RuntimeError as e:
        msg = str(e)
        log(msg)
        return False, msg

    if is_dir:
        return push_folder(
            src, remote, folder_sync_mode, log, cancel_check, progress=progress
        )

    push_src, push_dst = str(src), remote
    file_bytes = path_size(src)
    if progress:
        ok, adb_lines = progress.bulk_push(
            src.name,
            1,
            file_bytes,
            cancel_check,
            lambda: run_adb_push(push_src, push_dst, log, cancel_check),
        )
    else:
        ok, adb_lines = run_adb_push(push_src, push_dst, log, cancel_check)
    if not ok:
        if cancel_check():
            return False, "已取消"
        return False, format_adb_failure(adb_lines, src, remote)

    try:
        check = adb_shell(f"ls -lh {shell_quote(remote)}", timeout=30)
        out = (check.stdout or check.stderr or "").strip()
        if check.returncode == 0 and out:
            log(out)
        elif out:
            log(f"传输完成（校验信息：{out}）")
    except subprocess.TimeoutExpired:
        log("传输完成（跳过后续校验）")
    if Path(remote).name != src.name:
        log(f"已保存为 {Path(remote).name}")
    return True, remote


def explain_pull_error(text: str, remote: str, local: Path) -> str | None:
    lower = text.lower()
    if "no such file or directory" in lower:
        if "remote object" in lower or "does not exist" in lower:
            return f"手机文件不存在或无法访问：{remote}"
        return f"电脑目标路径不存在或无法写入：{local}"
    if "no space left" in lower or "not enough space" in lower:
        return f"电脑磁盘空间不足，无法保存：{local.name}"
    if "permission denied" in lower:
        return f"没有权限写入电脑目标路径：{local}"
    return None


def format_pull_failure(lines: list[str], remote: str, local: Path) -> str:
    text = "\n".join(lines)
    detail = explain_pull_error(text, remote, local)
    if detail:
        return detail
    name = posixpath.basename(remote.rstrip("/"))
    for line in reversed(lines):
        line = line.strip()
        if line and "pulled" not in line.lower():
            return f"传输失败：{name}（{line}）"
    return f"传输失败：{name}"


def run_adb_pull(
    remote_path: str, local_path: str, log, cancel_check
) -> tuple[bool, list[str]]:
    proc = subprocess.Popen(
        adb_cmd("pull", remote_path, local_path),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    lines: list[str] = []
    for line in proc.stdout:
        if cancel_check():
            proc.kill()
            return False, lines
        line = line.rstrip()
        if line:
            lines.append(line)
            log(line)
    if proc.wait() != 0:
        return False, lines
    return True, lines


def find_pull_folder_conflicts(remote: str, dest: str) -> list[str]:
    remote = remote.rstrip("/")
    local_base = Path(dest).expanduser() / posixpath.basename(remote)
    if not local_base.is_dir():
        return []
    remote_root = remote
    remote_rels = {
        posixpath.relpath(path, remote_root)
        for path, _ in build_remote_manifest(remote_root).files
    }
    local_rels = {
        str(path.relative_to(local_base)).replace("\\", "/")
        for path in local_base.rglob("*")
        if path.is_file()
    }
    return sorted(remote_rels & local_rels)


def find_pull_file_conflict(remote: str, dest: str) -> str | None:
    if remote_is_dir(remote):
        return None
    name = posixpath.basename(remote)
    local = Path(dest).expanduser() / name
    if local.exists():
        return name
    return None


def collect_pull_conflicts(remotes: list[str], dest: str) -> list[str]:
    conflicts: list[str] = []
    for remote in remotes:
        if remote_is_dir(remote):
            for rel in find_pull_folder_conflicts(remote, dest):
                conflicts.append(f"{posixpath.basename(remote.rstrip('/'))}/{rel}")
        else:
            name = find_pull_file_conflict(remote, dest)
            if name:
                conflicts.append(name)
    return sorted(conflicts)


def pull_folder_files(
    remote: str,
    local: Path,
    manifest: RemoteManifest,
    sync_mode: FolderSyncMode,
    log,
    cancel_check,
    *,
    progress: FileProgressTracker | None = None,
) -> tuple[bool, str]:
    remote = remote.rstrip("/")
    files = manifest.files
    if not files:
        return True, str(local)

    for remote_file, size in files:
        if cancel_check():
            return False, "已取消"
        rel = posixpath.relpath(remote_file, remote)
        local_file = local / rel
        local_file.parent.mkdir(parents=True, exist_ok=True)
        if sync_mode == "keep_both" and local_file.exists():
            local_file = resolve_local_path(
                str(local_file.parent),
                local_file.name,
                False,
                log,
                sync_mode="keep_both",
            )
        if progress:
            ok, lines = progress.bulk_pull(
                rel,
                1,
                size,
                cancel_check,
                lambda rf=remote_file, lf=str(local_file): run_adb_pull(
                    rf, lf, log, cancel_check
                ),
            )
        else:
            ok, lines = run_adb_pull(remote_file, str(local_file), log, cancel_check)
        if not ok:
            return False, format_pull_failure(lines, remote_file, local_file)
    return True, str(local)


def pull_folder(
    remote: str,
    local_dest: str,
    sync_mode: FolderSyncMode,
    log,
    cancel_check,
    *,
    progress: FileProgressTracker | None = None,
) -> tuple[bool, str]:
    remote = remote.rstrip("/")
    manifest = build_remote_manifest(remote)
    if not manifest.files:
        log("文件夹为空，无需传输")
        return True, local_dest

    name = posixpath.basename(remote)
    try:
        local_target = resolve_local_path(
            local_dest, name, True, log, sync_mode=sync_mode
        )
    except RuntimeError as exc:
        msg = str(exc)
        log(msg)
        return False, msg
    local_target.mkdir(parents=True, exist_ok=True)

    if sync_mode == "overwrite":
        pull_args = (f"{remote}/.", f"{local_target}/", log, cancel_check)
        if progress:
            ok, lines = progress.bulk_pull(
                name,
                len(manifest.files),
                manifest_remote_bytes(manifest),
                cancel_check,
                lambda: run_adb_pull(*pull_args),
            )
        else:
            ok, lines = run_adb_pull(*pull_args)
        if not ok:
            return False, format_pull_failure(
                lines, remote, Path(local_dest) / name
            )
        return True, str(local_target)

    return pull_folder_files(
        remote, local_target, manifest, sync_mode, log, cancel_check, progress=progress
    )


def pull_one(
    remote: str,
    dest: str,
    log,
    cancel_check,
    *,
    folder_sync_mode: FolderSyncMode = "overwrite",
    progress: FileProgressTracker | None = None,
) -> tuple[bool, str]:
    if cancel_check():
        return False, "已取消"

    remote = remote.rstrip("/")
    if not remote_exists(remote):
        return False, f"手机文件不存在：{remote}"

    ok, err = ensure_local_dir(dest)
    if not ok:
        log(err)
        return False, err

    is_dir = remote_is_dir(remote)
    name = posixpath.basename(remote)
    try:
        local_target = resolve_local_path(
            dest, name, is_dir, log, sync_mode=folder_sync_mode
        )
    except RuntimeError as exc:
        msg = str(exc)
        log(msg)
        return False, msg

    if is_dir:
        return pull_folder(
            remote,
            dest,
            folder_sync_mode,
            log,
            cancel_check,
            progress=progress,
        )

    local_target.parent.mkdir(parents=True, exist_ok=True)
    file_bytes = remote_file_size(remote)
    if progress:
        ok, lines = progress.bulk_pull(
            name,
            1,
            file_bytes,
            cancel_check,
            lambda: run_adb_pull(remote, str(local_target), log, cancel_check),
        )
    else:
        ok, lines = run_adb_pull(remote, str(local_target), log, cancel_check)
    if not ok:
        if cancel_check():
            return False, "已取消"
        return False, format_pull_failure(lines, remote, local_target)
    return True, str(local_target)

