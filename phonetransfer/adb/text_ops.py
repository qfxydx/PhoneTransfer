#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跨端文本与链接速传操作（URL 浏览器打开、键盘模拟输入、便签文件推送）"""

from __future__ import annotations

from datetime import datetime
import hashlib
import os
from pathlib import Path
import re
import tempfile

from phonetransfer.adb.core import adb_push, adb_shell, shell_quote
from phonetransfer.adb.media import scan_remote_media_file

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
CLIP_JAR_LOCAL = ASSETS_DIR / "pt_clip.jar"
REMOTE_CLIP_JAR = "/data/local/tmp/pt_clip.jar"
CLIP_CLASS = "com.phonetransfer.clip.ClipTool"

# 本地 JAR 哈希缓存: ((st_mtime_ns, st_size), md5_hexdigest)
_LOCAL_JAR_CACHE: tuple[tuple[int, int], str] = ((0, 0), "")


def get_local_jar_md5() -> str:
    """获取本地 pt_clip.jar 的 MD5 哈希（基于 st_mtime_ns + st_size 双重缓存）。"""
    global _LOCAL_JAR_CACHE
    if not CLIP_JAR_LOCAL.exists():
        return ""
    st = CLIP_JAR_LOCAL.stat()
    cache_key = (st.st_mtime_ns, st.st_size)
    if _LOCAL_JAR_CACHE[0] == cache_key and _LOCAL_JAR_CACHE[1]:
        return _LOCAL_JAR_CACHE[1]
    h = hashlib.md5(CLIP_JAR_LOCAL.read_bytes()).hexdigest().lower()
    _LOCAL_JAR_CACHE = (cache_key, h)
    return h


def ensure_clipboard_helper(serial: str | None = None) -> tuple[bool, str]:
    """确保手机端 /data/local/tmp/pt_clip.jar 助手已就绪且哈希一致。"""
    if not CLIP_JAR_LOCAL.exists():
        return False, f"本地缺少剪贴板助手组件：{CLIP_JAR_LOCAL}"

    local_hash = get_local_jar_md5()

    try:
        # 尝试通过 md5sum 严格比对文件哈希
        res = adb_shell(
            f"[ -f {REMOTE_CLIP_JAR} ] && md5sum {REMOTE_CLIP_JAR}",
            serial=serial,
            timeout=5,
        )
        if res.returncode == 0 and res.stdout:
            parts = res.stdout.strip().split()
            # 若哈希一致，直接复用手机端现有 JAR，省去推送
            if parts and parts[0].lower() == local_hash:
                return True, ""
        # 若不支持 md5sum、远程文件不存在或哈希不一致：
        # 由于 pt_clip.jar 仅约 2.5 KB，直接推流更新成本极低（数十毫秒），
        # 绝不降级为单纯比对文件大小，坚决杜绝因新旧字节数恰好相同误用旧版本的隐患
    except Exception:
        pass

    p_res = adb_push(str(CLIP_JAR_LOCAL), REMOTE_CLIP_JAR, serial=serial, timeout=10)
    if p_res.returncode != 0:
        err = (p_res.stderr or p_res.stdout or "推送剪贴板组件失败").strip()
        return False, err
    return True, ""


def push_text_to_clipboard(text: str, serial: str | None = None) -> tuple[bool, str]:
    """将文本直接写入手机系统剪贴板（支持任意长度、换行、中英文和 Emoji）。"""
    if not text:
        return False, "文本内容不能为空"

    ok, err = ensure_clipboard_helper(serial=serial)
    if not ok:
        return False, err

    cmd = f"CLASSPATH={REMOTE_CLIP_JAR} app_process /system/bin {CLIP_CLASS} -"
    res = adb_shell(cmd, serial=serial, timeout=10, input=text)
    if res.returncode != 0:
        err_msg = (res.stderr or res.stdout or "写入手机剪贴板失败").strip()
        return False, err_msg
    return True, ""


def get_clipboard_from_phone(serial: str | None = None) -> tuple[bool, str]:
    """从手机系统剪贴板读取当前文本。"""
    ok, err = ensure_clipboard_helper(serial=serial)
    if not ok:
        return False, err

    cmd = f"CLASSPATH={REMOTE_CLIP_JAR} app_process /system/bin {CLIP_CLASS}"
    res = adb_shell(cmd, serial=serial, timeout=10)
    if res.returncode != 0:
        err_msg = (res.stderr or res.stdout or "读取手机剪贴板失败").strip()
        return False, err_msg
    return True, res.stdout


def is_valid_url(text: str) -> bool:
    t = text.strip()
    if not t or "\n" in t or " " in t:
        return False
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://\S+$", t):
        return True
    return bool(re.match(r"^([a-zA-Z0-9\-]+\.)+[a-zA-Z]{2,}(:\d+)?(\/\S*)?$", t))


def is_pure_ascii(text: str) -> bool:
    return text.isascii()


def escape_adb_input_text(text: str) -> str:
    """Android input text 将空格作为 %s 处理，并对 shell 元字符进行反斜杠转义。"""
    escaped = text.replace(" ", "%s")
    for ch in ("&", "<", ">", "(", ")", "[", "]", "{", "}", ";", "*", "~", "|", "!", '"', "'", "`", "$"):
        escaped = escaped.replace(ch, "\\" + ch)
    return escaped


def push_url_to_phone(url: str, serial: str | None = None) -> tuple[bool, str]:
    """在手机端默认浏览器中直接打开网址。"""
    url = url.strip()
    if not url:
        return False, "网址不能为空"
    if not (url.startswith("http://") or url.startswith("https://") or "://" in url):
        url = "https://" + url

    cmd = f"am start -a android.intent.action.VIEW -d {shell_quote(url)}"
    res = adb_shell(cmd, serial=serial, timeout=10)
    if res.returncode != 0:
        err = (res.stderr or res.stdout or "无法在手机上打开链接").strip()
        return False, err
    return True, ""


def push_text_input_to_phone(text: str, serial: str | None = None) -> tuple[bool, str]:
    """通过 ADB 键盘模拟将文本输入到手机当前获得焦点的输入框（支持英文、数字、符号、空格）。"""
    text = text.strip()
    if not text:
        return False, "输入内容不能为空"

    escaped = escape_adb_input_text(text)
    cmd = f"input text {escaped}"
    res = adb_shell(cmd, serial=serial, timeout=10)
    if res.returncode != 0:
        err = (res.stderr or res.stdout or "模拟输入失败").strip()
        return False, err
    return True, ""


def push_text_file_to_phone(
    text: str, filename: str | None = None, serial: str | None = None
) -> tuple[bool, str]:
    """将文本作为 UTF-8 便签文件推送到手机的 /sdcard/Download 目录并通知系统更新。"""
    text = text.strip()
    if not text:
        return False, "文本内容不能为空"

    if not filename:
        now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"便签_{now_str}.txt"

    tmp_dir = Path(tempfile.gettempdir()) / "phonetransfer_text"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / filename

    try:
        tmp_path.write_text(text, encoding="utf-8")
        remote_dest = f"/sdcard/Download/{filename}"
        res = adb_push(str(tmp_path), remote_dest, serial=serial, timeout=15)
        if res.returncode != 0:
            err = (res.stderr or res.stdout or "推送便签文件失败").strip()
            return False, err

        try:
            scan_remote_media_file(remote_dest)
        except Exception:
            pass

        return True, remote_dest
    except Exception as e:
        return False, str(e)
    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
