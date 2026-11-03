"""Catalog, preferences and offscreen UI coverage. All device work is mocked."""
import ast
import json
import os
import re
import shutil
import importlib.util
import sys
import string
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QCoreApplication, QPoint, QSettings, Qt, QThread, QTimer
from PySide6.QtGui import QFont, QIcon
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QComboBox, QLabel, QPushButton, QMessageBox, QToolButton
from phonetransfer import i18n
from phonetransfer.ui.main_window import MainWindow
from phonetransfer.ui.dialogs import QuickTextDialog, WifiConnectDialog, SponsorDialog, ScrcpyInstallDialog
from phonetransfer.ui.dialogs.remote_file_dialogs import NewFolderDialog, RenameDialog, DeleteConfirmDialog
from phonetransfer.ui.widgets.log_list import parse_log_line
from phonetransfer.workers.apk_worker import explain_apk_error

ROOT = Path(__file__).resolve().parents[1]


def fields(text):
    return sorted((name, spec, conv) for _, name, spec, conv in string.Formatter().parse(text) if name is not None)


class TestCatalogs(unittest.TestCase):
    def tearDown(self):
        i18n.initialize(QApplication.instance(), selection="zh-CN")

    def test_six_catalogs_complete_and_placeholders_match(self):
        source = i18n.catalog("zh-CN")
        self.assertGreater(len(source), 450)
        for locale in i18n.LANGUAGES:
            with self.subTest(locale=locale):
                translated = i18n.catalog(locale)
                self.assertEqual(set(source), set(translated))
                for key, value in translated.items():
                    self.assertTrue(value.strip(), key)
                    self.assertEqual(fields(key), fields(value), (locale, key))
                    # Verify actual formatting, including numeric precision and !r.
                    args = {name: 12 for name, _, _ in fields(key)}
                    i18n.initialize(selection=locale)
                    self.assertIsInstance(i18n.tr(key, **args), str)

    def test_every_literal_key_and_call_argument_is_valid(self):
        source = i18n.catalog("zh-CN")
        for path in (ROOT / "phonetransfer").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "tr":
                    if node.args and isinstance(node.args[0], ast.Constant):
                        key = node.args[0].value
                        self.assertIn(key, source, (path, node.lineno, key))
                        self.assertEqual({n for n, _, _ in fields(key)}, {k.arg for k in node.keywords})

    def test_no_untracked_chinese_ui_keys(self):
        source = i18n.catalog("zh-CN")
        for path in (ROOT / "phonetransfer").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
            for node in ast.walk(tree):
                if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                    continue
                if not re.search("[\u4e00-\u9fff]", node.value):
                    continue
                parent = parents.get(node)
                if isinstance(parent, ast.Expr):  # documentation
                    continue
                if isinstance(parent, ast.JoinedStr):
                    # Stable generated note filename. User data is never translated.
                    self.assertEqual(node.value, "便签_")
                    continue
                if path.name == "i18n.py" and node.value in ("简体中文", "日本語"):
                    continue  # language autonyms
                self.assertIn(node.value, source, (path, node.lineno, node.value))

    def test_core_algorithms_match_baseline_after_message_normalization(self):
        from scripts.check_i18n_core import verify
        self.assertEqual(verify(), 11)

    def test_all_python_sources_parse_as_python_310(self):
        paths = [ROOT / "phone_transfer.py", *(ROOT / "phonetransfer").rglob("*.py")]
        for path in paths:
            ast.parse(path.read_text(encoding="utf-8"), feature_version=(3, 10))

    def test_cancellation_messages_and_cleanup_all_languages(self):
        from phonetransfer.adb.transfer import push_file_verified, pull_file_verified
        with tempfile.TemporaryDirectory() as folder:
            local = Path(folder) / "keep.txt"
            local.write_text("keep", encoding="utf-8")
            for language in i18n.LANGUAGES:
                i18n.initialize(selection=language)
                with patch("phonetransfer.adb.transfer.adb_shell") as shell, \
                     patch("phonetransfer.adb.transfer.run_adb_push_quiet") as push, \
                     patch("phonetransfer.adb.transfer.run_adb_pull") as pull:
                    self.assertEqual(push_file_verified(str(local), "/sdcard/keep.txt", lambda: True),
                                     (False, i18n.tr("已取消")))
                    self.assertEqual(pull_file_verified("/sdcard/keep.txt", local, lambda line: None, lambda: True),
                                     (False, [i18n.tr("已取消")]))
                    push.assert_not_called()
                    pull.assert_not_called()
                    self.assertIn("/.pt-part-", shell.call_args.args[0])
                    self.assertEqual(local.read_text(), "keep")

    def test_locale_regions_scripts_and_preferred_order(self):
        for locale, expected in (("en_GB", "en"), ("ja-JP", "ja"), ("ko_KR", "ko"),
                                 ("de-AT", "de"), ("es-MX", "es"), ("zh-Hant-TW", "zh-CN"),
                                 ("zh-Hans-CN", "zh-CN")):
            self.assertEqual(i18n.resolve_language("auto", [locale]), expected)
        self.assertEqual(i18n.resolve_language("auto", ["fr-FR", "de-DE", "en"]), "de")
        self.assertEqual(i18n.resolve_language("auto", ["fr-FR", "ar"]), "en")
        self.assertEqual(i18n.resolve_language("auto", []), "en")
        self.assertEqual(i18n.resolve_language("es", ["ja"]), "es")

    def test_system_preferences_are_used(self):
        with patch.object(i18n, "QLocale") as locale:
            locale.system.return_value.uiLanguages.return_value = ["ko-KR", "en-US"]
            self.assertEqual(i18n.resolve_language("auto"), "ko")

    def test_persistence_all_options_invalid_setting_and_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / "settings.ini")
            store = QSettings(path, QSettings.Format.IniFormat)
            self.assertEqual(i18n.saved_selection(store), "auto")
            for option in ("auto", *i18n.LANGUAGES):
                i18n.save_selection(option, store)
                reopened = QSettings(path, QSettings.Format.IniFormat)
                self.assertEqual(i18n.saved_selection(reopened), option)
                expected = "ja" if option == "auto" else option
                self.assertEqual(i18n.initialize(store=reopened, preferred=["ja-JP"]), expected)
            store.setValue(i18n.SETTING_KEY, "invalid")
            self.assertEqual(i18n.saved_selection(store), "auto")
            with self.assertRaises(ValueError):
                i18n.save_selection("fr", store)

    def test_values_paths_and_diagnostics_are_untouched(self):
        sample = "/sdcard/下载/日本語 한글 ä ñ {file}.txt"
        for language in i18n.LANGUAGES:
            i18n.initialize(selection=language)
            self.assertIn(sample, i18n.tr("本地文件不存在：{p0}", p0=sample))
            self.assertIn("SHA-256", i18n.tr("设备无法校验 SHA-256，已保留原文件"))
            self.assertIn("testOnly", explain_apk_error("Failure [INSTALL_FAILED_TEST_ONLY]"))

    def test_resource_location_does_not_depend_on_cwd(self):
        old = Path.cwd()
        try:
            os.chdir(tempfile.gettempdir())
            i18n.catalog.cache_clear()
            self.assertIn("下载", i18n.catalog("en"))
        finally:
            os.chdir(old)
        spec = (ROOT / "PhoneTransfer.spec").read_text()
        self.assertIn("('phonetransfer/locales', 'phonetransfer/locales')", spec)

    def test_frozen_style_extracted_resources(self):
        with tempfile.TemporaryDirectory() as folder:
            package = Path(folder) / "phonetransfer"
            package.mkdir()
            shutil.copy(ROOT / "phonetransfer/i18n.py", package / "i18n.py")
            shutil.copytree(ROOT / "phonetransfer/locales", package / "locales")
            spec = importlib.util.spec_from_file_location("pt_frozen_i18n_test", package / "i18n.py")
            module = importlib.util.module_from_spec(spec)
            with patch.object(sys, "frozen", True, create=True), patch.object(sys, "_MEIPASS", folder, create=True):
                spec.loader.exec_module(module)
                for language in module.LANGUAGES:
                    module.initialize(selection=language)
                    self.assertEqual(module.tr("下载"), i18n.catalog(language)["下载"])
                self.assertEqual(module.CATALOG_DIR, (package / "locales").resolve())

    def test_packaging_manifest_has_all_json_and_qt_resources(self):
        prefix = (ROOT / "PhoneTransfer.spec").read_text().split("a = Analysis(", 1)[0]
        scope = {}
        exec(compile(prefix, "PhoneTransfer.spec", "exec"), scope)
        resources = scope["added_files"]
        self.assertIn(("phonetransfer/locales", "phonetransfer/locales"), resources)
        qt_files = {Path(src).name for src, target in resources if target == "PySide6/Qt/translations"}
        self.assertEqual(qt_files, {f"qtbase_{locale}.qm" for locale in ("zh_CN", "en", "ja", "ko", "de", "es")})
        self.assertTrue(all(Path(src).exists() for src, _ in resources))

    def test_english_fallback_for_missing_translation(self):
        i18n.initialize(selection="de")
        with patch.object(i18n, "catalog", side_effect=lambda lang: {} if lang == "de" else {"test": "English {p0}"}):
            self.assertEqual(i18n.tr("test", p0="value"), "English value")


class TestLocalizedUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setFont(QFont(".AppleSystemUIFont", 13))

    def tearDown(self):
        i18n.initialize(self.app, selection="zh-CN")
        self.app.processEvents()

    def make_window(self):
        # Prevent background threads, polling and every subprocess/device call.
        with patch.object(QThread, "start"), patch.object(MainWindow, "refresh_device"), \
             patch("subprocess.run") as run, patch("subprocess.Popen") as popen:
            window = MainWindow()
            window._device_poll_timer.stop()
            window._storage_poll_timer.stop()
            self.app.processEvents()
            run.assert_not_called()
            popen.assert_not_called()
        return window

    def assert_buttons_fit(self, widget):
        for label in widget.findChildren(QLabel):
            if label.isVisible() and label.text() and label.wordWrap():
                self.assertGreaterEqual(label.height(), label.heightForWidth(label.width()),
                                        (i18n.current_language(), label.text(), label.size()))
        for button in widget.findChildren(QPushButton):
            if button.isVisible() and button.text() and len(button.text()) > 2:
                self.assertGreaterEqual(button.width(), button.sizeHint().width(),
                                        (i18n.current_language(), button.text(), button.width(), button.sizeHint().width()))

    def test_main_both_directions_and_long_progress_all_locales(self):
        for language in i18n.LANGUAGES:
            with self.subTest(language=language):
                i18n.initialize(self.app, selection=language)
                window = self.make_window()
                try:
                    window.show()
                    self.app.processEvents()
                    self.assertEqual(window.btn_go.text(), i18n.tr("传输到手机"))
                    self.assertEqual(len(window.language_menu.actions()), 7)
                    self.assertEqual(window.language_button.accessibleName(), i18n.tr("界面语言"))
                    self.assertEqual(window._shortcut_quick_text.key().toString(), "Ctrl+Shift+V")
                    self.assertEqual(window._shortcut_scrcpy.key().toString(), "Ctrl+Shift+M")
                    self.assert_buttons_fit(window)
                    window._show_toast(i18n.tr("已复制到手机剪贴板（可在手机直接粘贴）"))
                    self.app.processEvents()
                    self.assertLessEqual(window.toast.width(), window.width())
                    self.assert_buttons_fit(window)
                    window.toast.dismiss()
                    self.assertEqual(window.phone_source_card._display_name_for_dir("/sdcard/Download"), i18n.tr("下载"))
                    with patch.object(window.phone_source_card, "reload_listing"), patch.object(window, "_refresh_storage"):
                        window._toggle_direction()
                    self.app.processEvents()
                    self.assertEqual(window.btn_go.text(), i18n.tr("传输到电脑"))
                    self.assert_buttons_fit(window)
                    window.phone_source_card._set_category("doc")
                    self.assertIn(i18n.tr("📄 文档"), window.phone_source_card.btn_category.text())
                    window._busy = True
                    window._set_progress_visible(True)
                    window.progress_pct.setText(i18n.tr("传输中"))
                    self.app.processEvents()
                    self.assertGreaterEqual(window.progress_pct.width(), window.progress_pct.sizeHint().width())
                    window._on_transfer_progress(500, 1000, 1, 2, "long-name.txt")
                    self.app.processEvents()
                    self.assertIn(i18n.tr("传输及完整性校验中 · 只统计已校验文件"), window.progress_eta.text())
                    self.assertGreaterEqual(window.progress_wrap.height(), window.progress_wrap.minimumSizeHint().height())
                finally:
                    window.close()
                    window.deleteLater()
                    self.app.processEvents()

    def test_all_dialogs_and_text_modes_all_locales(self):
        for language in i18n.LANGUAGES:
            i18n.initialize(self.app, selection=language)
            parent = self.make_window()
            dialogs = [QuickTextDialog(parent), WifiConnectDialog(parent), SponsorDialog(parent), ScrcpyInstallDialog(parent),
                       NewFolderDialog(parent), RenameDialog(parent, current_name="sample.txt"),
                       DeleteConfirmDialog(parent, count=2, sample_name="sample.txt")]
            try:
                for dialog in dialogs:
                    with self.subTest(language=language, dialog=type(dialog).__name__):
                        dialog.show()
                        self.app.processEvents()
                        dialog.adjustSize()
                        self.app.processEvents()
                        self.assertGreaterEqual(dialog.width(), dialog.minimumSizeHint().width())
                        self.assertGreaterEqual(dialog.height(), dialog.minimumSizeHint().height())
                        self.assert_buttons_fit(dialog)
                        dialog.hide()
                text = dialogs[0]
                for value in ("", "hello\nworld", "https://example.com"):
                    text.text_edit.setPlainText(value)
                    self.assertNotIn("检测到", text.tip_label.text()) if language not in ("zh-CN",) else None
                wifi = dialogs[1]
                wifi._do_pair()
                self.assertEqual(wifi.pair_result.text(), i18n.tr("❌ 请输入 IP 地址"))
                new = dialogs[4]
                new.edit.clear()
                new._on_accept()
                self.assertEqual(new.err_label.text(), i18n.tr("文件夹名称不能为空"))
            finally:
                for dialog in dialogs:
                    dialog.close()
                    dialog.deleteLater()
                parent.close()
                parent.deleteLater()
                self.app.processEvents()

    def test_selection_saves_but_entire_session_stays_in_old_language(self):
        i18n.initialize(self.app, selection="en")
        with tempfile.TemporaryDirectory() as folder:
            store = QSettings(str(Path(folder) / "prefs.ini"), QSettings.Format.IniFormat)
            with patch("phonetransfer.ui.main_window.saved_selection", side_effect=lambda: i18n.saved_selection(store)), \
                 patch("phonetransfer.ui.main_window.save_selection", side_effect=lambda selection: i18n.save_selection(selection, store)), \
                 patch.object(QMessageBox, "information") as notice:
                window = self.make_window()
                try:
                    next(a for a in window.language_menu.actions() if a.data() == "de").trigger()
                    self.assertEqual(i18n.saved_selection(store), "de")
                    self.assertEqual(i18n.current_language(), "en")
                    self.assertEqual(window.btn_go.text(), "Send to phone")
                    self.assertIn("quit and reopen", notice.call_args.args[2])
                    window.close()
                    i18n.initialize(self.app, store=QSettings(store.fileName(), QSettings.Format.IniFormat))
                    reopened = self.make_window()
                    try:
                        self.assertEqual(reopened.btn_go.text(), "An Handy senden")
                        self.assertEqual([a.data() for a in reopened.language_menu.actions() if a.isChecked()], ["de"])
                    finally:
                        reopened.close()
                        reopened.deleteLater()
                finally:
                    window.close()
                    window.deleteLater()

    def test_language_button_is_icon_only_and_menu_has_exact_choices_all_locales(self):
        for language in i18n.LANGUAGES:
            with self.subTest(language=language), \
                 patch("phonetransfer.ui.main_window.saved_selection", return_value=language):
                i18n.initialize(self.app, selection=language)
                window = self.make_window()
                try:
                    window.show()
                    self.app.processEvents()
                    button = window.language_button
                    self.assertIsInstance(button, QToolButton)
                    self.assertEqual(button.objectName(), "languageButton")
                    self.assertEqual(button.text(), "")
                    self.assertFalse(button.icon().isNull())
                    self.assertEqual(button.toolButtonStyle(), Qt.ToolButtonStyle.ToolButtonIconOnly)
                    self.assertEqual((button.width(), button.height()), (26, 26))
                    self.assertEqual((button.iconSize().width(), button.iconSize().height()), (18, 18))
                    self.assertEqual(button.accessibleName(), i18n.tr("界面语言"))
                    self.assertEqual(button.accessibleDescription(), i18n.tr("语言设置在重新启动后生效。"))
                    self.assertEqual(button.toolTip(), i18n.tr("界面语言") + "\n" + i18n.tr("语言设置在重新启动后生效。"))
                    self.assertFalse(window.findChildren(QComboBox, "languageSelector"))
                    self.assertFalse(hasattr(window, "language_combo"))
                    header = button.parentWidget()
                    self.assertFalse(any(label.isVisible() and label.text() in
                                         [*i18n.LANGUAGE_NAMES.values(), i18n.tr("界面语言"), i18n.tr("系统 / 自动")]
                                         for label in header.findChildren(QLabel)))
                    self.assertEqual(window.width(), 742)
                    self.assertEqual([b.x() for b in (window.btn_send_text, window.btn_scrcpy,
                                                     window.btn_wifi, window.btn_coffee)], [16, 50, 84, 118])
                    self.assertGreater(button.x(), window.btn_refresh.x())
                    self.assertEqual(button.menu(), window.language_menu)
                    self.assertEqual([a.text() for a in button.menu().actions()],
                                     [i18n.tr("系统 / 自动"), *i18n.LANGUAGE_NAMES.values()])
                    self.assertEqual([a.data() for a in button.menu().actions()], ["auto", *i18n.LANGUAGES])
                    self.assertTrue(all(a.isCheckable() and a.isEnabled() for a in button.menu().actions()))
                    self.assertEqual([a.data() for a in button.menu().actions() if a.isChecked()], [language])
                finally:
                    window.close()
                    window.deleteLater()

    def test_language_menu_all_choices_persist_and_current_choice_is_noop(self):
        for language in i18n.LANGUAGES:
            i18n.initialize(self.app, selection=language)
            with self.subTest(language=language), tempfile.TemporaryDirectory() as folder:
                store = QSettings(str(Path(folder) / "prefs.ini"), QSettings.Format.IniFormat)
                with patch("phonetransfer.ui.main_window.saved_selection", side_effect=lambda: i18n.saved_selection(store)), \
                     patch("phonetransfer.ui.main_window.save_selection", side_effect=lambda selection: i18n.save_selection(selection, store)) as save, \
                     patch.object(QMessageBox, "information") as notice:
                    window = self.make_window()
                    try:
                        icon = window.language_button.icon().cacheKey()
                        for action in window.language_menu.actions():
                            previous = i18n.saved_selection(store)
                            save.reset_mock()
                            notice.reset_mock()
                            action.trigger()
                            if action.data() == previous:
                                save.assert_not_called()
                                notice.assert_not_called()
                            else:
                                save.assert_called_once_with(action.data())
                                notice.assert_called_once_with(window, i18n.tr("界面语言"), i18n.tr("语言设置已保存。请在当前操作完成后退出并重新打开 PhoneTransfer，所有界面将使用新语言。"))
                            window.language_menu.popup(window.language_button.mapToGlobal(QPoint(0, 26)))
                            self.app.processEvents()
                            self.assertEqual([a.data() for a in window.language_menu.actions() if a.isChecked()], [action.data()])
                            window.language_menu.hide()
                            self.assertEqual(i18n.saved_selection(QSettings(store.fileName(), QSettings.Format.IniFormat)), action.data())
                            self.assertEqual(i18n.current_language(), language)
                            self.assertEqual(window.btn_go.text(), i18n.tr("传输到手机"))
                            self.assertEqual(window.language_button.text(), "")
                            self.assertEqual(window.language_button.icon().cacheKey(), icon)
                            save.reset_mock()
                            notice.reset_mock()
                            action.trigger()
                            save.assert_not_called()
                            notice.assert_not_called()
                        # Return to auto after an explicit language; it must remain a distinct saved option.
                        window.language_menu.actions()[0].trigger()
                        self.assertEqual(i18n.saved_selection(store), "auto")
                        self.assertTrue(window.language_menu.actions()[0].isChecked())
                    finally:
                        window.close()
                        window.deleteLater()

    def test_language_menu_save_failure_restores_previous_choice_all_locales(self):
        for language in i18n.LANGUAGES:
            i18n.initialize(self.app, selection=language)
            with self.subTest(language=language), \
                 patch("phonetransfer.ui.main_window.saved_selection", return_value="auto"), \
                 patch("phonetransfer.ui.main_window.save_selection", side_effect=OSError("raw OS error")), \
                 patch.object(QMessageBox, "warning") as warning, \
                 patch.object(QMessageBox, "information") as notice:
                window = self.make_window()
                try:
                    next(a for a in window.language_menu.actions() if a.data() == language).trigger()
                    warning.assert_called_once_with(window, i18n.tr("界面语言"), i18n.tr("无法保存语言设置，请检查系统偏好设置权限。"))
                    notice.assert_not_called()
                    window.language_menu.popup(window.language_button.mapToGlobal(QPoint(0, 26)))
                    self.app.processEvents()
                    self.assertEqual([a.data() for a in window.language_menu.actions() if a.isChecked()], ["auto"])
                    window.language_menu.hide()
                    self.assertEqual(i18n.current_language(), language)
                finally:
                    window.close()
                    window.deleteLater()

    def test_language_menu_keyboard_mouse_anchor_and_theme_states(self):
        from phonetransfer.ui.theme import AppTheme
        for dark in (False, True):
            with self.subTest(dark=dark), patch.object(MainWindow, "_is_dark", return_value=dark), \
                 patch("phonetransfer.ui.main_window.saved_selection", return_value="en"):
                window = self.make_window()
                try:
                    window.show()
                    self.app.processEvents()
                    theme = AppTheme(dark)
                    icon = window.language_button.icon()
                    images = [icon.pixmap(18, 18, mode).toImage() for mode in
                              (QIcon.Mode.Normal, QIcon.Mode.Active, QIcon.Mode.Disabled)]
                    for image, color in zip(images, (theme.secondary, theme.accent_hover, theme.btn_disabled_text)):
                        pixels = [image.pixelColor(x, y) for x in range(image.width()) for y in range(image.height())]
                        self.assertTrue(any(p.alpha() > 200 and p.name() == color for p in pixels))
                    self.assertNotEqual(images[0], images[1])
                    self.assertNotEqual(images[0], images[2])
                    window.language_button.setEnabled(False)
                    self.assertFalse(window.language_button.isEnabled())
                    window.language_button.setEnabled(True)
                    observed = []
                    def inspect_popup():
                        try:
                            visible = window.language_menu.isVisible()
                            position = window.language_menu.pos()
                            QTest.keyClick(window.language_menu, Qt.Key.Key_Down)
                            observed.append((visible, position, window.language_menu.activeAction()))
                            QTest.keyClick(window.language_menu, Qt.Key.Key_Escape)
                        finally:
                            window.language_menu.hide()
                    for keyboard in (False, True):
                        QTimer.singleShot(0, inspect_popup)
                        if keyboard:
                            window.language_button.setFocus()
                            QTest.keyClick(window.language_button, Qt.Key.Key_Space)
                        else:
                            QTest.mouseClick(window.language_button, Qt.MouseButton.LeftButton)
                        self.app.processEvents()
                        self.assertTrue(observed[-1][0])
                        self.assertEqual(observed[-1][1].y(), window.language_button.mapToGlobal(QPoint(0, 26)).y())
                        self.assertIsNotNone(observed[-1][2])
                        self.assertFalse(window.language_menu.isVisible())
                    self.assertIn("QMenu#languageMenu::item", window.styleSheet())
                    self.assertIn("QToolButton#languageButton::menu-indicator", window.styleSheet())
                    self.assertEqual(window.language_button.text(), "")
                    self.assertIn(theme.primary, window.styleSheet())
                    self.assertIn(theme.card, window.styleSheet())
                finally:
                    window.close()
                    window.deleteLater()

    def test_qt_standard_buttons_follow_selected_language(self):
        for language in i18n.LANGUAGES:
            i18n.initialize(self.app, selection=language)
            box = QMessageBox()
            box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel)
            for button, key in ((QMessageBox.StandardButton.Yes, "是"), (QMessageBox.StandardButton.No, "否"), (QMessageBox.StandardButton.Cancel, "取消")):
                self.assertEqual(box.button(button).text().replace("&", ""), i18n.tr(key))

    def test_safety_and_conflict_prompts_all_locales(self):
        for language in i18n.LANGUAGES:
            i18n.initialize(self.app, selection=language)
            wifi = WifiConnectDialog()
            with patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.No) as warning, \
                 patch.object(wifi, "_start_worker") as start:
                wifi._do_usb_to_wifi()
                self.assertIn("5555", warning.call_args.args[2])
                self.assertIn("Android 11+", warning.call_args.args[2])
                self.assertEqual(warning.call_args.args[4], QMessageBox.StandardButton.No)
                start.assert_not_called()
            wifi.close()
            wifi.deleteLater()
            window = self.make_window()
            try:
                seen = []
                def inspect(box):
                    box.show()
                    self.app.processEvents()
                    self.assertEqual(box.text(), i18n.tr("在{p0}中已存在 {p1} 个同名文件。\n请选择处理方式：", p0=i18n.tr("手机目标文件夹"), p1=1))
                    self.assertIn("unchanged.txt", box.detailedText())
                    self.assertIn(i18n.tr("覆盖同名文件"), [b.text() for b in box.buttons()])
                    self.assertIn(i18n.tr("两者都保留"), [b.text() for b in box.buttons()])
                    self.assert_buttons_fit(box)
                    seen.append(True)
                    box.hide()
                    return 0
                with patch.object(QMessageBox, "exec", inspect):
                    self.assertIsNone(window._ask_sync_policy(["unchanged.txt"], to_phone=True))
                self.assertTrue(seen)
                window._on_quick_text_sent("clipboard", "sample")
                self.assertIn(i18n.tr("📋 复制到剪贴板"), window._log_lines[-1])
            finally:
                window.close()
                window.deleteLater()
                self.app.processEvents()

    def test_translated_logs_keep_full_details_and_paths(self):
        for language in i18n.LANGUAGES:
            i18n.initialize(selection=language)
            text = i18n.tr("操作失败：{p0}", p0="/sdcard/" + "long-path/" * 25)
            self.assertEqual(parse_log_line(text).title, text)
            self.assertIn("12", parse_log_line("12 files pushed, 1.2 MB/s").title)


if __name__ == "__main__":
    unittest.main()
