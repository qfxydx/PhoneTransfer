"""No-device tests: Wi-Fi ADB safety, APK installer defaults and honest progress."""
import os
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from phonetransfer.workers.wifi_worker import WifiActionWorker
from phonetransfer.workers.apk_worker import ApkInstallWorker
from phonetransfer.adb.transfer import FileProgressTracker
from phonetransfer.ui.dialogs.wifi_dialog import WifiConnectDialog
from phonetransfer.adb.core import set_active_serial, get_active_serial
from PySide6.QtWidgets import QApplication, QMessageBox


def result(stdout="", rc=0, stderr=""):
    return CompletedProcess([], rc, stdout, stderr)


class TestWifiSafety(unittest.TestCase):
    def setUp(self):
        self.original = get_active_serial()

    def tearDown(self):
        set_active_serial(self.original)

    def test_target_validation(self):
        self.assertTrue(WifiActionWorker._classic_wifi_target("192.168.1.3:5555"))
        self.assertFalse(WifiActionWorker._classic_wifi_target("192.168.1.3:37123"))
        self.assertFalse(WifiActionWorker._classic_wifi_target("emulator-5554"))
        self.assertFalse(WifiActionWorker._classic_wifi_target("foobar:5555"))

    @patch("phonetransfer.workers.wifi_worker.subprocess.run")
    def test_disable_no_real_device_call_on_bad_target(self, run):
        worker = WifiActionWorker("disable_tcpip", {"serial": "emulator-5554"})
        events = []
        worker.action_finished.connect(lambda *args: events.append(args))
        worker._run_disable_tcpip()
        self.assertEqual(events[0][1], False)
        run.assert_not_called()

    @patch("phonetransfer.workers.wifi_worker.subprocess.run")
    def test_disable_requires_confirmed_usb_reset(self, run):
        run.side_effect = [result("restarting in USB mode\n"), result("disconnected")]
        worker = WifiActionWorker("disable_tcpip", {"serial": "192.168.1.2:5555"})
        events = []
        worker.action_finished.connect(lambda *args: events.append(args))
        worker._run_disable_tcpip()
        self.assertTrue(events[0][1])
        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args_list[0].args[0][-2:], ["192.168.1.2:5555", "usb"])
        self.assertEqual(run.call_args_list[1].args[0][-2:], ["disconnect", "192.168.1.2:5555"])

    @patch("phonetransfer.workers.wifi_worker.subprocess.run")
    def test_disable_failure_does_not_claim_safety(self, run):
        run.return_value = result("error: device offline", 1)
        worker = WifiActionWorker("disable_tcpip", {"serial": "192.168.1.2:5555"})
        events = []
        worker.action_finished.connect(lambda *args: events.append(args))
        worker._run_disable_tcpip()
        self.assertFalse(events[0][1])
        self.assertIn("无法确认", events[0][2])
        self.assertEqual(run.call_count, 1)  # Must not only disconnect.

    @patch("phonetransfer.workers.wifi_worker.subprocess.run")
    def test_two_usb_devices_never_auto_select(self, run):
        run.return_value = result(
            "List of devices attached\nUSB-A\tdevice model:a\nUSB-B\tdevice model:b\n")
        worker = WifiActionWorker("usb_to_wifi", {})
        events = []
        worker.action_finished.connect(lambda *args: events.append(args))
        worker._run_usb_to_wifi()
        self.assertFalse(events[0][1])
        self.assertIn("多台", events[0][2])
        self.assertEqual(run.call_count, 1)

    @patch("phonetransfer.workers.wifi_worker.subprocess.run")
    def test_ambiguous_tcpip_attempt_rollback(self, run):
        run.side_effect = [
            result("List of devices attached\nUSB-A\tdevice model:a\n"),
            result("2: wlan0: inet 192.168.1.10/24"),
            result("", 0),  # May have enabled TCP; response is inconclusive.
            result("restarting in USB mode\n"),
        ]
        worker = WifiActionWorker("usb_to_wifi", {"serial": "USB-A"})
        events = []
        worker.action_finished.connect(lambda *args: events.append(args))
        worker._run_usb_to_wifi()
        self.assertFalse(events[0][1])
        self.assertIn("切回 USB", events[0][2])
        self.assertEqual(run.call_args_list[-1].args[0][-1], "usb")

    @patch("phonetransfer.workers.wifi_worker.time.sleep")
    @patch("phonetransfer.workers.wifi_worker.subprocess.run")
    def test_selected_usb_target_only(self, run, _sleep):
        run.side_effect = [
            result("List of devices attached\\nUSB-A\\tdevice\\nUSB-B\\tdevice\\n".replace("\\n", "\n").replace("\\t", "\t")),
            result("inet 192.168.1.19/24"),
            result("restarting in TCP mode port: 5555"),
            result("connected to 192.168.1.19:5555"),
        ]
        worker = WifiActionWorker("usb_to_wifi", {"serial": "USB-B"})
        events = []
        worker.action_finished.connect(lambda *args: events.append(args))
        worker._run_usb_to_wifi()
        self.assertTrue(events[0][1])
        self.assertEqual(run.call_args_list[1].args[0][2], "USB-B")
        self.assertEqual(run.call_args_list[2].args[0][2], "USB-B")
        self.assertEqual(run.call_count, 4)

    @patch("phonetransfer.workers.wifi_worker.time.sleep")
    @patch("phonetransfer.workers.wifi_worker.subprocess.run")
    def test_connect_failure_rolls_back_after_tcpip(self, run, _sleep):
        run.side_effect = [
            result("List of devices attached\nUSB-A\tdevice\n"),
            result("inet 192.168.1.19/24"),
            result("restarting in TCP mode port: 5555"),
            result("unable to connect to 192.168.1.19:5555", 1),
            result("restarting in USB mode"),
        ]
        worker = WifiActionWorker("usb_to_wifi", {"serial": "USB-A"})
        events = []
        worker.action_finished.connect(lambda *args: events.append(args))
        worker._run_usb_to_wifi()
        self.assertFalse(events[0][1])
        self.assertIn("切回 USB", events[0][2])
        self.assertEqual(run.call_args_list[-1].args[0][-1], "usb")

    @patch("phonetransfer.workers.wifi_worker.subprocess.run")
    def test_connect_failure_not_mistaken_for_success(self, run):
        run.return_value = result("not connected to 192.168.1.10:5555\n", 0)
        worker = WifiActionWorker("connect", {"ip": "192.168.1.10", "port": 5555})
        events = []
        worker.action_finished.connect(lambda *args: events.append(args))
        worker._run_connect()
        self.assertFalse(events[0][1])


class TestApkInstaller(unittest.TestCase):
    @patch("phonetransfer.workers.apk_worker.reclaim_qobject_to_main")
    @patch("phonetransfer.workers.apk_worker.subprocess.run")
    def test_default_install_never_downgrades(self, run, reclaim):
        with tempfile.TemporaryDirectory() as td:
            apk = Path(td) / "test.apk"
            apk.write_bytes(b"not-a-real-apk-only-mocked")
            run.return_value = result("Success")
            worker = ApkInstallWorker([str(apk)], serial="FAKE-DEVICE")
            completed = []
            worker.finished.connect(lambda *args: completed.append(args))
            worker.run()
            args = run.call_args.args[0]
            self.assertEqual(args[1:3], ["-s", "FAKE-DEVICE"])
            self.assertIn("-r", args)
            self.assertNotIn("-d", args)
            self.assertNotIn("-t", args)
            self.assertEqual(completed[0][0], 1)


class TestProgressHonesty(unittest.TestCase):
    def test_no_estimated_bytes_before_success(self):
        events = []
        tracker = FileProgressTracker(2048, 1, lambda *args: events.append(args))
        def during_transfer():
            self.assertEqual(tracker.done_bytes, 0)
            self.assertEqual(tracker.done_files, 0)
            self.assertTrue(all(x[0] == 0 for x in events))
            return True, []
        ok, _ = tracker.bulk_push("file.bin", 1, 2048, lambda: False, during_transfer)
        self.assertTrue(ok)
        self.assertEqual(tracker.done_bytes, 2048)
        self.assertEqual(tracker.done_files, 1)

    def test_failure_keeps_confirmed_progress_unchanged(self):
        events = []
        tracker = FileProgressTracker(1024, 1, lambda *args: events.append(args))
        ok, _ = tracker.bulk_push("file.bin", 1, 1024, lambda: False, lambda: (False, ["fail"]))
        self.assertFalse(ok)
        self.assertEqual(tracker.done_bytes, 0)


class TestWifiDialog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_legacy_wireless_requires_explicit_confirmation(self):
        dialog = WifiConnectDialog()
        with patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.No), \
             patch.object(dialog, "_start_worker") as start:
            dialog._do_usb_to_wifi()
            start.assert_not_called()
        dialog.close()

    def test_close_does_not_terminate_active_worker(self):
        dialog = WifiConnectDialog()
        worker = Mock()
        worker.isRunning.return_value = True
        dialog._worker = worker
        with patch.object(dialog, "closeEvent", wraps=dialog.closeEvent):
            dialog.reject()
        worker.terminate.assert_not_called()
        dialog._worker = None
        dialog.close()


class TestStartupSafety(unittest.TestCase):
    def test_launcher_does_not_kill_unrelated_processes(self):
        path = Path(__file__).resolve().parents[1] / "启动PhoneTransfer.command"
        text = path.read_text(encoding="utf-8")
        self.assertNotIn("pkill -f", text)
        self.assertNotIn("lsof -ti", text)
        self.assertNotIn("kill -9", text)


if __name__ == "__main__":
    unittest.main()
