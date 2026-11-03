"""Severity metadata for legacy text-only log signals.

Catalog source keys are stable IDs, independent of the active language. Match
the *whole* rendered template, never translated keywords or dynamic values.
New emitters with a known outcome should pass an explicit kind at the UI sink;
register source keys here when an existing Signal(str) cannot carry metadata.
Unknown external diagnostics remain info unless the receiving boundary knows
their outcome. No worker, ADB API, or cancellation sentinel is changed.
"""
from __future__ import annotations

from functools import lru_cache
import re
from string import Formatter

from phonetransfer.i18n import catalog, current_language


SOURCE_KINDS = {
    "error": (
        '操作失败：{p0}', '预览加载失败：{p0}', '[投屏错误] {p0}',
        '打开选择器失败：{p0}', 'adb devices 失败：{p0}', '检测失败：{p0}',
        '未选择目标设备，请先在右上角切换到要传输的手机',
        '检测到多台设备，请先在右上角选择要传输的手机',
        '设备未就绪（{p0}），请检查 USB 调试是否已授权',
        '超时：{p0}', '操作超时', '完成 {p0}/{p1} 项，{p2} 项失败',
        '× 应用安装失败：{p0}（{p1}）', '× 应用安装超时：{p0}',
        '× 安装异常：{p0} - {p1}', '传输失败：{p0}（{p1}）', '传输失败：{p0}',
        '安全上传失败：{p0}', '安全下载失败：{p0}',
        '本地文件不存在：{p0}', '手机文件不存在：{p0}',
        '手机文件不存在或无法访问：{p0}', '电脑目标路径不存在或无法写入：{p0}',
        '电脑磁盘空间不足，无法保存：{p0}', '没有权限写入电脑目标路径：{p0}',
        '设备无法校验 SHA-256，已保留原文件',
        'SHA-256 校验失败，原文件未被覆盖', 'SHA-256 校验失败，电脑原文件未被覆盖',
        '上传临时文件失败', '安全替换失败',
        '无法创建手机目录，同名路径已被文件占用：{p0}',
        '无法创建手机目录 {p0}：{p1}',
    ),
    "warning": (
        '已取消', '传输已取消', 'APK 安装已取消', '正在停止传输…',
        '未检测到设备', '预览完成时设备已切换，已忽略旧设备文件',
        '刷新媒体库时出错：{p0}', '媒体库刷新未确认成功，可在手机上下拉刷新相册后再看',
        '传输完成（跳过后续校验）',
    ),
    "device": ('正在检测设备…',),
    "transfer": (
        '开始传输 {p0} 项（共 {p1} 个文件，{p2}）→ {p3}',
        '开始传输 {p0} 项 → {p1}', '开始向手机安装 {p0} 个应用…',
        '正在读取手机预览文件：{p0}…', '同步 {p0} 个文件（{p1}）',
        '批量解析完成：{p0} 个文件（含 {p1} 个符号链接）',
        '其中 {p0} 个文件需复制（跨磁盘），其余使用硬链接',
    ),
    "progress": (
        '[{p0}/{p1}] 正在安装应用：{p2}…', '正在生成传输清单…', '整包传输中…',
        '已处理 {p0}/{p1} 个文件', '复用已校验文件：{p0}', '刷新媒体库（{p0} 个）…',
    ),
    "success": (
        '已连接 {p0}（{p1}）', '已切换到{p0}：{p1}（{p2}）',
        '[跨端速传] {p0}: {p1}', '[投屏] 已启动 scrcpy: {p0} ({p1})',
        '✓ 应用安装成功：{p0}', '已发送 1 个文件', '已发送 {p0} 个文件',
        '传输完成（校验信息：{p0}）', '已保存为 {p0}',
        '文件夹为空，无需传输', '已刷新媒体，相册/图库中应可立即看到',
        '已新建文件夹「{p0}」', '重命名成功', '已从手机删除 {p0} 个项目',
    ),
}


@lru_cache(maxsize=6)
def _patterns(language: str):
    messages = catalog(language)
    fallback = catalog("en")
    result = []
    for kind, sources in SOURCE_KINDS.items():
        for source in sources:
            template = messages.get(source, fallback.get(source, source))
            pattern = "".join(
                re.escape(literal) + (r"[\s\S]*?" if field is not None else "")
                for literal, field, _, _ in Formatter().parse(template)
            )
            result.append((re.compile(pattern), kind))
    return tuple(result)


def catalog_log_kind(text: str) -> str | None:
    for pattern, kind in _patterns(current_language()):
        if pattern.fullmatch(text):
            return kind
    return None
