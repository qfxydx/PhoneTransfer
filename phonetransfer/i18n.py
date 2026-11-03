"""Central UTF-8 message catalogs; language is fixed for one application session.

Source strings are stable catalog keys. Use ``tr(key, p0=value)`` instead of
interpolating before lookup. Values (including paths and device diagnostics)
are never translated. Settings changes take effect on the next launch so worker
messages and their cancellation sentinels always use the same session language.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QLibraryInfo, QLocale, QSettings, QTranslator

LANGUAGES = ("zh-CN", "en", "ja", "ko", "de", "es")
LANGUAGE_NAMES = {
    "zh-CN": "简体中文", "en": "English", "ja": "日本語",
    "ko": "한국어", "de": "Deutsch", "es": "Español",
}
CATALOG_DIR = Path(__file__).resolve().parent / "locales"
SETTING_KEY = "ui/language"


def language_for_locale(locale: str) -> str | None:
    """Match region/script variants; all Chinese variants use Simplified Chinese."""
    base = str(locale).replace("_", "-").lower().split("-", 1)[0]
    if base == "zh":
        return "zh-CN"
    return base if base in LANGUAGES else None


def resolve_language(selection: str, preferred: list[str] | None = None) -> str:
    if selection in LANGUAGES:
        return selection
    for locale in QLocale.system().uiLanguages() if preferred is None else preferred:
        match = language_for_locale(locale)
        if match:
            return match
    return "en"


def settings() -> QSettings:
    # Explicit identity also works before QApplication construction and when frozen.
    return QSettings("PhoneTransfer", "PhoneTransfer")


def saved_selection(store: QSettings | None = None) -> str:
    value = (store if store is not None else settings()).value(SETTING_KEY, "auto")
    return value if value in ("auto", *LANGUAGES) else "auto"


def save_selection(selection: str, store: QSettings | None = None) -> None:
    if selection not in ("auto", *LANGUAGES):
        raise ValueError(f"Unsupported language selection: {selection}")
    target = store if store is not None else settings()
    target.setValue(SETTING_KEY, selection)
    target.sync()
    if target.status() != QSettings.Status.NoError:
        raise OSError(tr("无法保存语言设置，请检查系统偏好设置权限。"))


@lru_cache(maxsize=6)
def catalog(language: str) -> dict[str, str]:
    with (CATALOG_DIR / f"{language}.json").open(encoding="utf-8") as stream:
        return json.load(stream)


_language = resolve_language(saved_selection())


def current_language() -> str:
    return _language


def tr(source: str, **values: object) -> str:
    messages = catalog(_language)
    template = messages.get(source)
    if template is None:
        template = catalog("en").get(source, source)
    # A string without parameters may contain literal braces (e.g. help text).
    return template.format(**values) if values else template


# Qt-owned controls must use the same language as our own dialogs. The bundled
# Qt catalogs handle file dialogs; this translator covers standard message boxes
# even when a wheel's optional qtbase translations are absent.
_QT_KEYS = {
    "OK": "确定", "&OK": "确定", "Cancel": "取消", "&Cancel": "取消",
    "Close": "关闭", "&Close": "关闭", "Yes": "是", "&Yes": "是",
    "No": "否", "&No": "否", "Save": "保存", "&Save": "保存",
    "Open": "打开", "&Open": "打开", "Abort": "中止", "Retry": "重试",
    "Ignore": "忽略", "Show Details...": "显示详细信息…",
    "Hide Details...": "隐藏详细信息…", "Help": "帮助",
}


class StandardButtonTranslator(QTranslator):
    def isEmpty(self) -> bool:
        return False

    def translate(self, context, sourceText, disambiguation=None, n=-1):
        key = _QT_KEYS.get(sourceText)
        return tr(key) if key else None


def initialize(app=None, *, selection: str | None = None,
               store: QSettings | None = None, preferred: list[str] | None = None) -> str:
    """Initialize at launch. Reinitialization is for isolated UI tests only."""
    global _language
    _language = resolve_language(selection if selection is not None else saved_selection(store), preferred)
    if app is not None:
        for translator in getattr(app, "_pt_translators", []):
            app.removeTranslator(translator)
        translators = []
        base = QTranslator(app)
        qt_locale = "zh_CN" if _language == "zh-CN" else _language
        if base.load(f"qtbase_{qt_locale}", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
            app.installTranslator(base)
            translators.append(base)
        buttons = StandardButtonTranslator(app)
        app.installTranslator(buttons)
        translators.append(buttons)
        app._pt_translators = translators
    return _language
