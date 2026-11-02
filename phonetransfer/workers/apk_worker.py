"""APK 应用后台安装 Worker。"""

from __future__ import annotations

from pathlib import Path
import re
import subprocess

from PySide6.QtCore import QThread, Signal

from phonetransfer.adb.core import ADB, adb_cmd
from phonetransfer.workers.base import reclaim_qobject_to_main


_APK_ERROR_TRANSLATIONS = {
    "INSTALL_FAILED_ALREADY_EXISTS": "应用已存在且签名冲突",
    "INSTALL_FAILED_INSUFFICIENT_STORAGE": "手机可用存储空间不足",
    "INSTALL_FAILED_UPDATE_INCOMPATIBLE": "与手机已安装版本签名冲突，请先在手机上卸载旧版应用",
    "INSTALL_FAILED_VERSION_DOWNGRADE": "系统禁止版本降级",
    "INSTALL_FAILED_USER_RESTRICTED": "安装已被手机系统拦截，请在手机弹窗中点击「允许安装」",
    "INSTALL_FAILED_ABORTED": "用户在手机弹窗上取消了安装",
    "INSTALL_PARSE_FAILED_INCONSISTENT_CERTIFICATES": "安装包签名证书不一致",
    "INSTALL_PARSE_FAILED_NO_CERTIFICATES": "未签名的 APK，无法直接安装",
    "INSTALL_FAILED_TEST_ONLY": "该包带有 testOnly 标记",
    "INSTALL_FAILED_OLDER_SDK": "应用所需的最低 Android 版本高于当前手机系统",
}


def explain_apk_error(output: str) -> str:
    """提取 ADB install 失败原因并转化为友好中文提示。"""
    for code, explanation in _APK_ERROR_TRANSLATIONS.items():
        if code in output:
            return explanation

    match = re.search(r"Failure\s*\[([^\]]+)\]", output)
    if match:
        raw_code = match.group(1).strip()
        return _APK_ERROR_TRANSLATIONS.get(raw_code, raw_code)

    for line in output.splitlines():
        line = line.strip()
        if "Failure" in line or "Error" in line or "error" in line:
            return line
    return output.strip() or "未知安装错误"


class ApkInstallWorker(QThread):
    """在后台线程中依次执行 APK 的流式安装，避免阻塞主线程。"""

    started_install = Signal(str)                  # 当前正在安装的 APK 名称
    progress = Signal(int, int, str)              # (当前序号 1-based, 总数, 文件名)
    log = Signal(str)                             # 文本日志输出
    finished = Signal(int, int, list)             # (成功数量, 总数量, 错误列表)

    def __init__(self, apk_paths: list[str], serial: str | None = None, parent=None) -> None:
        super().__init__(parent)
        self._apk_paths = [str(p) for p in apk_paths if Path(p).is_file()]
        self._serial = serial
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        success_count = 0
        total = len(self._apk_paths)
        errors: list[str] = []

        try:
            for idx, apk in enumerate(self._apk_paths, 1):
                if self._cancelled:
                    self.log.emit("APK 安装已取消")
                    break

                name = Path(apk).name
                self.started_install.emit(name)
                self.progress.emit(idx, total, name)
                self.log.emit(f"[{idx}/{total}] 正在安装应用：{name}…")

                cmd = adb_cmd("install", "-r", "-d", "-t", apk, serial=self._serial)
                try:
                    res = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=180,
                    )
                    out = (res.stdout or "") + "\n" + (res.stderr or "")
                    if res.returncode == 0 and "Success" in out:
                        success_count += 1
                        self.log.emit(f"✓ 应用安装成功：{name}")
                    else:
                        err = explain_apk_error(out)
                        errors.append(f"{name}: {err}")
                        self.log.emit(f"× 应用安装失败：{name}（{err}）")
                except subprocess.TimeoutExpired:
                    err = "安装超时（手机未在规定时间内响应）"
                    errors.append(f"{name}: {err}")
                    self.log.emit(f"× 应用安装超时：{name}")
                except Exception as exc:
                    err = str(exc)
                    errors.append(f"{name}: {err}")
                    self.log.emit(f"× 安装异常：{name} - {err}")

            self.finished.emit(success_count, total, errors)
        finally:
            reclaim_qobject_to_main(self)

