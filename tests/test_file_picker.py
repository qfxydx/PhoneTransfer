"""macOS file chooser regression tests; no phone, filesystem mutation or GUI clicks."""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from phonetransfer import utils
from phonetransfer.ui.main_window import MainWindow


class TestFilePicker(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @patch.object(utils, "QFileDialog")
    @patch.object(utils, "_run_picker_process", return_value=(0, "", ""))
    @patch.object(utils, "picker_helper_path", return_value=Path("/tmp/unused-picker"))
    def test_mac_cancel_does_not_open_second_dialog(self, _path, _run, dialog):
        with patch.object(utils.sys, "platform", "darwin"):
            self.assertEqual(utils.pick_files_and_folders(), [])
        dialog.assert_not_called()

    @patch.object(utils, "QFileDialog")
    @patch.object(utils, "_run_picker_process", return_value=(0, "/tmp/a.txt\n/tmp/b.txt\n", ""))
    @patch.object(utils, "picker_helper_path", return_value=Path("/tmp/unused-picker"))
    def test_mac_success_returns_multiple_files(self, _path, _run, dialog):
        with patch.object(utils.sys, "platform", "darwin"):
            paths = utils.pick_files_and_folders()
        self.assertEqual(paths, ["/tmp/a.txt", "/tmp/b.txt"])
        dialog.assert_not_called()

    @patch.object(utils, "QFileDialog")
    @patch.object(utils, "_run_picker_process", return_value=(2, "", "selection error"))
    @patch.object(utils, "picker_helper_path", return_value=Path("/tmp/unused-picker"))
    def test_helper_failure_reports_error_instead_of_nested_qt_dialog(self, _path, _run, dialog):
        with patch.object(utils.sys, "platform", "darwin"):
            with self.assertRaisesRegex(RuntimeError, "selection error"):
                utils.pick_files_and_folders()
        dialog.assert_not_called()

    @patch.object(utils, "QFileDialog")
    @patch.object(utils, "picker_helper_path", return_value=None)
    def test_missing_helper_does_not_launch_different_dialog(self, _path, dialog):
        with patch.object(utils.sys, "platform", "darwin"):
            with self.assertRaisesRegex(RuntimeError, "组件缺失"):
                utils.pick_files_and_folders()
        dialog.assert_not_called()

    def test_real_qprocess_fast_exit_does_not_hang(self):
        code, stdout, stderr = utils._run_picker_process("/usr/bin/true", [])
        self.assertEqual(code, 0)
        self.assertEqual(stdout, "")

    def test_real_qprocess_stdout_and_exit_error(self):
        code, stdout, _ = utils._run_picker_process("/bin/echo", ["fast-exit-ok"])
        self.assertEqual(code, 0)
        self.assertEqual(stdout.strip(), "fast-exit-ok")
        code, _, _ = utils._run_picker_process("/usr/bin/false", [])
        self.assertNotEqual(code, 0)

    def test_real_qprocess_missing_executable(self):
        code, _, _ = utils._run_picker_process("/tmp/no-such-pt-picker-binary-098231", [])
        self.assertNotEqual(code, 0)

    def test_button_handler_keeps_window_visible_and_reenables_button(self):
        fake_window = Mock()
        fake_window._picking = False
        fake_window._busy = False
        with patch("phonetransfer.ui.main_window.pick_files_and_folders", return_value=[]):
            MainWindow.pick_items(fake_window)
        self.assertFalse(fake_window._picking)
        fake_window.hide.assert_not_called()
        fake_window.show.assert_not_called()
        fake_window.source_card.btn_pick.setEnabled.assert_any_call(False)
        fake_window.source_card.btn_pick.setEnabled.assert_any_call(True)

    def test_button_handler_recovers_after_picker_failure(self):
        fake_window = Mock()
        fake_window._picking = False
        fake_window._busy = False
        with patch("phonetransfer.ui.main_window.pick_files_and_folders",
                   side_effect=RuntimeError("picker failed")), \
             patch("phonetransfer.ui.main_window.QMessageBox.warning"):
            MainWindow.pick_items(fake_window)
        self.assertFalse(fake_window._picking)
        fake_window.source_card.btn_pick.setEnabled.assert_any_call(True)
        fake_window.append_log.assert_called_once()


if __name__ == "__main__":
    unittest.main()
