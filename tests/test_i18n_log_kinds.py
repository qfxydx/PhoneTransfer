"""Six-language log semantics and replay; every process/device call is blocked."""
import ast
import os
from pathlib import Path
import string
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt, QThread
from PySide6.QtWidgets import QApplication, QLabel

from phonetransfer import i18n
from phonetransfer.log_kinds import SOURCE_KINDS
from phonetransfer.ui.main_window import MainWindow
from phonetransfer.ui.widgets.log_list import LOG_KIND_META, LogDetailList, parse_log_line
from phonetransfer.workers.transfer_worker import TransferWorker


class TestLogKinds(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        # Fail immediately if a regression attempts any external process.
        for target in ("subprocess.run", "subprocess.Popen"):
            guard = patch(target, side_effect=AssertionError("No real processes in log QA"))
            guard.start()
            self.addCleanup(guard.stop)
        threads = patch.object(QThread, "start")
        threads.start()
        self.addCleanup(threads.stop)

    def tearDown(self):
        i18n.initialize(self.app, selection="zh-CN")
        self.app.processEvents()

    def make_window(self):
        with patch.object(MainWindow, "refresh_device"):
            window = MainWindow()
        window._device_poll_timer.stop()
        window._storage_poll_timer.stop()
        self.addCleanup(window.deleteLater)
        self.addCleanup(window.close)
        return window

    def kinds(self, view):
        return [row.property("kind") for row in view._rows]

    def test_every_registered_source_template_all_six_languages(self):
        registered = []
        for kind, sources in SOURCE_KINDS.items():
            self.assertIn(kind, LOG_KIND_META)
            registered.extend(sources)
        self.assertEqual(len(registered), len(set(registered)))
        for language in i18n.LANGUAGES:
            i18n.initialize(selection=language)
            for kind, sources in SOURCE_KINDS.items():
                for source in sources:
                    with self.subTest(language=language, source=source):
                        self.assertIn(source, i18n.catalog(language))
                        values = {field: 12 for _, field, _, _ in string.Formatter().parse(source)
                                  if field is not None}
                        text = i18n.tr(source, **values)
                        entry = parse_log_line(text)
                        self.assertEqual(entry.kind, kind)
                        self.assertEqual(entry.title, text)

    def test_dynamic_failures_success_cancel_and_progress_all_six_languages(self):
        diagnostic = "✓ /sdcard/日本語 한글 ä ñ/<file>&{raw}.txt\n" + "stderr: denied " * 40
        cases = [
            ("操作失败：{p0}", {"p0": diagnostic}, "error"),
            ("预览加载失败：{p0}", {"p0": diagnostic}, "error"),
            ("检测失败：{p0}", {"p0": diagnostic}, "error"),
            ("传输失败：{p0}（{p1}）", {"p0": "file pushed.txt", "p1": diagnostic}, "error"),
            ("刷新媒体库时出错：{p0}", {"p0": diagnostic}, "warning"),
            ("已连接 {p0}（{p1}）", {"p0": "× Failed-phone", "p1": diagnostic}, "success"),
            ("已发送 {p0} 个文件", {"p0": 7}, "success"),
            ("未检测到设备", {}, "warning"),
            ("传输已取消", {}, "warning"),
            ("APK 安装已取消", {}, "warning"),
            ("正在检测设备…", {}, "device"),
            ("开始传输 {p0} 项 → {p1}", {"p0": 2, "p1": diagnostic}, "transfer"),
            ("已处理 {p0}/{p1} 个文件", {"p0": 3, "p1": 9}, "progress"),
        ]
        for language in i18n.LANGUAGES:
            i18n.initialize(selection=language)
            view = LogDetailList()
            try:
                lines = [i18n.tr(source, **values) for source, values, _ in cases]
                expected = [kind for _, _, kind in cases]
                for text, kind in zip(lines, expected):
                    entry = parse_log_line(text)
                    self.assertEqual((entry.kind, entry.title), (kind, text), language)
                    view.append(text)
                self.assertEqual(self.kinds(view), expected, language)
                view.sync_lines(lines)
                self.assertEqual(self.kinds(view), expected, language)
                labels = view._rows[0].findChildren(QLabel)
                title = next(label for label in labels if label.objectName() == "logRowTitle")
                self.assertEqual(title.text(), lines[0])
                self.assertEqual(title.textFormat(), Qt.TextFormat.PlainText)
            finally:
                view.deleteLater()

    def test_no_translated_keyword_or_filename_guessing(self):
        for language in i18n.LANGUAGES:
            i18n.initialize(selection=language)
            for text in ("backup-error-success-warning.txt", "note: 12 files pushed, pretend",
                         "memo " + i18n.tr("传输已取消") + ".txt", "prefix " + i18n.tr("未检测到设备")):
                self.assertEqual(parse_log_line(text).kind, "info", (language, text))
            self.assertIsNone(parse_log_line(" \n"))

    def test_explicit_boundary_kind_overrides_text_and_validates(self):
        text = "✓ arbitrary raw stderr\n" + "x" * 300
        self.assertEqual(parse_log_line(text, kind="error").kind, "error")
        self.assertEqual(parse_log_line(text, kind="error").title, text)
        with self.assertRaises(ValueError):
            parse_log_line(text, kind="unknown")
        self.assertTrue(all(glyph.isascii() or glyph in "▣↔✓×…·" for _, glyph in LOG_KIND_META.values()))

    def test_adb_protocol_summaries_preserve_entire_original(self):
        for language in i18n.LANGUAGES:
            i18n.initialize(selection=language)
            for verb in ("pushed", "pulled"):
                text = "/sdcard/" + "long-name/" * 30 + f": 12 files {verb}, 0 skipped. 1.2 MB/s (123 bytes)"
                entry = parse_log_line(text)
                self.assertEqual(entry.kind, "success")
                self.assertIn("12", entry.title)
                self.assertEqual(entry.detail, text)
            self.assertEqual(parse_log_line("adb: error: raw stderr").kind, "error")
            self.assertEqual(parse_log_line("adb: warning: raw stderr").kind, "warning")
            self.assertEqual(parse_log_line("× /path: 12 files pushed, 1.2 MB/s").kind, "error")
            self.assertEqual(parse_log_line("[1/2] name: 12 files pushed, 1.2 MB/s").kind, "progress")

    def test_known_ui_outcomes_and_expand_collapse_all_six_languages(self):
        for language in i18n.LANGUAGES:
            i18n.initialize(self.app, selection=language)
            window = self.make_window()
            window._clear_log()
            diagnostic = "✓ raw exception <full>& " + "details " * 60
            with patch("phonetransfer.ui.main_window.send_macos_notification"), \
                 patch("phonetransfer.ui.main_window.QMessageBox.critical"), \
                 patch.object(window, "_refresh_storage"), \
                 patch("phonetransfer.ui.main_window.set_active_serial"), \
                 patch.object(window, "_start_storage_poll"):
                window._on_remote_op_started(diagnostic)
                window._on_remote_op_finished(True, diagnostic, "rename")
                window._on_remote_op_finished(False, diagnostic, "rename")
                window._on_transfer_done(False, diagnostic)
                window._on_transfer_done(False, i18n.tr("传输已取消"))
                window._on_transfer_done(True, diagnostic)
                window._pending_device_manual = True
                window._on_device_fail(diagnostic, window._device_gen)
                window._apply_selected_device({"serial": "MOCK", "model": "Mock", "state": "device"}, announce=True)
                window._on_device_ok({"devices": [], "usb_phones": []}, window._device_gen)
            expected = ["progress", "success", "error", "error", "warning", "success", "error", "success", "warning"]
            self.assertEqual(self.kinds(window.log_detail), expected, language)
            original_lines = list(window._log_lines)
            # A language change in this test proves replay uses stored metadata.
            i18n.initialize(selection="en" if language != "en" else "ja")
            window._toggle_log_detail()
            window._toggle_log_detail()
            window._toggle_log_detail()
            self.assertEqual(self.kinds(window.log_detail), expected, language)
            self.assertEqual(window._log_lines, original_lines)
            self.assertEqual(window.log_detail._rows[3].findChild(QLabel, "logRowTitle").text(), diagnostic)
            window._clear_log()
            window._toggle_log_detail()
            window._toggle_log_detail()
            self.assertEqual(window._log_entries, [])
            self.assertEqual(window.log_detail._rows, [])
            window.close()

    def test_legacy_worker_string_signal_retains_catalog_kind_when_queued(self):
        for language in i18n.LANGUAGES:
            i18n.initialize(self.app, selection=language)
            window = self.make_window()
            window._clear_log()
            worker = TransferWorker([], "/mock")
            worker.log.connect(window.append_log, Qt.ConnectionType.QueuedConnection)
            lines = [i18n.tr("开始传输 {p0} 项 → {p1}", p0=2, p1="/mock"),
                     "[1/2] 日本語 한글.txt", i18n.tr("已处理 {p0}/{p1} 个文件", p0=1, p1=2),
                     i18n.tr("刷新媒体库时出错：{p0}", p0="raw stderr")]
            for line in lines:
                worker.log.emit(line)
            self.app.processEvents()
            self.assertEqual(self.kinds(window.log_detail), ["transfer", "progress", "progress", "warning"])
            window._toggle_log_detail()
            self.assertEqual(self.kinds(window.log_detail), ["transfer", "progress", "progress", "warning"])
            self.assertEqual(window._log_lines, lines)
            window.close()

    def test_source_spec_versions_and_translation_manifest(self):
        root = Path(__file__).resolve().parents[1]
        tree = ast.parse((root / "PhoneTransfer.spec").read_text())
        bundle = next(node for node in ast.walk(tree) if isinstance(node, ast.Call)
                      and isinstance(node.func, ast.Name) and node.func.id == "BUNDLE")
        plist = ast.literal_eval(next(kw.value for kw in bundle.keywords if kw.arg == "info_plist"))
        self.assertEqual(plist["CFBundleVersion"], "1.1.0")
        self.assertEqual(plist["CFBundleShortVersionString"], "1.1.0")

    def test_entry_point_retains_compatibility_exports(self):
        import phone_transfer
        text = "12 files pushed, 1.2 MB/s"
        entry = phone_transfer._parse_adb_push_summary(text)
        self.assertEqual((entry.kind, entry.detail), ("success", text))
        self.assertIs(phone_transfer.parse_log_line, parse_log_line)


if __name__ == "__main__":
    unittest.main()
