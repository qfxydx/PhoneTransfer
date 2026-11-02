"""Isolated no-device tests for PhoneTransfer file operation safety."""
import tempfile
import time
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import Mock, patch

from phonetransfer.adb import file_ops, transfer


class TestPathSafety(unittest.TestCase):
    def test_allowed_paths(self):
        for p in ("/sdcard/Download/test.txt", "/storage/emulated/0/DCIM/a.jpg",
                  "/storage/self/primary/Movies/a.mp4", "/storage/ABCD-1234/DCIM/a.jpg"):
            with self.subTest(path=p):
                self.assertEqual(file_ops.validate_remote_storage_path(p), p)

    def test_unsafe_paths(self):
        for p in ("/", "/sdcard", "/storage", "/storage/emulated/0",
                  "/storage/ABCD-1234", "/sdcard/../data/system",
                  "/sdcard/Download/../../data", "/sdcard/./Download/a",
                  "/sdcard//Download/a", "/data/local/tmp/x", "/system/bin",
                  "sdcard/Download/a", "/storage/private/file",
                  "/storage/emulated/0sibling/x", "/sdcard/a\x00b", "/sdcard/a\nb", ""):
            with self.subTest(path=p):
                with self.assertRaises(ValueError):
                    file_ops.validate_remote_storage_path(p)

    @patch.object(file_ops, "adb_shell")
    def test_reject_before_calling_device(self, shell):
        for path in ("/sdcard/../data", "/sdcard", "/data/file"):
            self.assertFalse(file_ops.remote_delete([path])[0])
        shell.assert_not_called()

    @patch.object(file_ops, "adb_shell")
    def test_delete_inside_shared_storage(self, shell):
        shell.side_effect = [
            CompletedProcess([], 0, "/storage/emulated/0/Download/test.txt\n", ""),
            CompletedProcess([], 0, "", ""),
        ]
        ok, err = file_ops.remote_delete(["/sdcard/Download/test.txt"])
        self.assertTrue(ok, err)
        self.assertEqual(shell.call_count, 2)
        self.assertIn("readlink -f", shell.call_args_list[0].args[0])
        self.assertIn("rm -rf", shell.call_args_list[1].args[0])

    @patch.object(file_ops, "adb_shell")
    def test_block_symlink_escape(self, shell):
        shell.return_value = CompletedProcess([], 0, "/data/system/critical\n", "")
        self.assertFalse(file_ops.remote_delete(["/sdcard/Download/redirect"])[0])
        self.assertEqual(shell.call_count, 1)

    @patch.object(file_ops, "adb_shell")
    def test_block_failed_resolution(self, shell):
        shell.return_value = CompletedProcess([], 1, "", "failed")
        self.assertFalse(file_ops.remote_delete(["/sdcard/Download/unknown"])[0])
        self.assertEqual(shell.call_count, 1)

    @patch.object(file_ops, "adb_shell")
    def test_mkdir_with_safe_parent(self, shell):
        shell.side_effect = [
            CompletedProcess([], 0, "/storage/emulated/0/Download\n", ""),
            CompletedProcess([], 0, "", ""),
        ]
        self.assertTrue(file_ops.remote_mkdir("/sdcard/Download/New Folder")[0])
        self.assertIn("mkdir -p", shell.call_args_list[1].args[0])

    @patch.object(file_ops, "adb_shell")
    def test_mkdir_directly_under_shared_storage_root(self, shell):
        shell.side_effect = [
            CompletedProcess([], 0, "/storage/emulated/0\\n".replace("\\n", "\n"), ""),
            CompletedProcess([], 0, "", ""),
        ]
        ok, err = file_ops.remote_mkdir("/sdcard/NewFolder")
        self.assertTrue(ok, err)
        self.assertEqual(shell.call_count, 2)
        self.assertIn("mkdir -p", shell.call_args_list[1].args[0])

    @patch.object(file_ops, "adb_shell")
    def test_rename_existing_name_never_invokes_mv(self, shell):
        shell.side_effect = [
            CompletedProcess([], 0, "/storage/emulated/0/Download\n", ""),
            CompletedProcess([], 0, "/storage/emulated/0/Download\n", ""),
            CompletedProcess([], 0, "", ""),
        ]
        ok, err = file_ops.remote_rename(
            "/sdcard/Download/old.txt", "/sdcard/Download/existing.txt")
        self.assertFalse(ok)
        self.assertIn("已存在", err)
        self.assertFalse(any("mv " in call.args[0] for call in shell.call_args_list))

    @patch.object(file_ops, "adb_shell")
    def test_rename_nonexisting_destination_uses_nonclobbering_mv(self, shell):
        shell.side_effect = [
            CompletedProcess([], 0, "/storage/emulated/0\n", ""),
            CompletedProcess([], 0, "/storage/emulated/0\n", ""),
            CompletedProcess([], 1, "", ""),
            CompletedProcess([], 0, "", ""),
        ]
        ok, err = file_ops.remote_rename("/sdcard/old.txt", "/sdcard/new.txt")
        self.assertTrue(ok, err)
        self.assertIn("mv -n", shell.call_args_list[-1].args[0])
        self.assertIn("test ! -e", shell.call_args_list[-1].args[0])

    @patch.object(file_ops, "adb_shell")
    def test_delete_storage_root_still_blocked(self, shell):
        ok, err = file_ops.remote_delete(["/sdcard"])
        self.assertFalse(ok)
        shell.assert_not_called()

    @patch.object(file_ops, "remote_is_dir", return_value=True)
    def test_upload_file_cannot_replace_existing_folder(self, _is_dir):
        with self.assertRaises(RuntimeError):
            file_ops.resolve_remote_path(
                "/sdcard/Download", "clash", False,
                lambda _: None, sync_mode="overwrite")

    @patch.object(file_ops, "adb_shell")
    def test_rename_unsafe_parent(self, shell):
        shell.side_effect = [
            CompletedProcess([], 0, "/storage/emulated/0/Download\n", ""),
            CompletedProcess([], 0, "/data/system\n", ""),
        ]
        self.assertFalse(file_ops.remote_rename("/sdcard/Download/a", "/sdcard/link/a")[0])
        self.assertEqual(shell.call_count, 2)


class TestTransferFailures(unittest.TestCase):
    @patch.object(transfer, "format_adb_failure", return_value="failed")
    @patch.object(transfer, "push_file_verified")
    def test_failed_parallel_transfer_not_counted_successful(self, mock_push, _):
        def fake_push(src, dst, check=None):
            if src.endswith("fail.txt"):
                time.sleep(0.02)  # Ensure deterministic completion order.
                return False, "bad"
            return True, "ok"
        mock_push.side_effect = fake_push
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            good, bad = root / "ok.txt", root / "fail.txt"
            good.write_text("good")
            bad.write_text("bad")
            progress = transfer.FileProgressTracker(7, 2, lambda *args: None)
            ok, _ = transfer._push_folder_files_parallel(
                [(good, "ok.txt"), (bad, "fail.txt")], "/sdcard/Download",
                root, lambda _: None, lambda: False, progress=progress)
            self.assertFalse(ok)
            self.assertEqual(progress.done_files, 1)
            self.assertEqual(progress.done_bytes, 4)

    @patch.object(transfer.subprocess, "Popen")
    def test_cancellation_kills_stalled_adb(self, popen):
        class Stalled:
            def __init__(self):
                self.timeouts = 0
                self.killed = False
                self.returncode = None

            def communicate(self, timeout=None):
                if self.killed:
                    return "", ""
                self.timeouts += 1
                raise transfer.subprocess.TimeoutExpired(["adb", "push"], timeout)

            def kill(self):
                self.killed = True
                self.returncode = -9

            def poll(self):
                return self.returncode

        proc = Stalled()
        popen.return_value = proc
        ok, message = transfer.run_adb_push_quiet(
            "/tmp/a", "/sdcard/Download/a", lambda: proc.timeouts >= 2)
        self.assertFalse(ok)
        self.assertEqual(message, "已取消")
        self.assertTrue(proc.killed)




class TestVerifiedTransferSafety(unittest.TestCase):
    @patch.object(transfer, "adb_shell")
    @patch.object(transfer, "remote_sha256", return_value="0" * 64)
    @patch.object(transfer, "run_adb_push_quiet", return_value=(True, "ok"))
    def test_upload_hash_mismatch_never_commits(self, _push, _sha, shell):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "test.txt"
            source.write_text("NEW CONTENT")
            ok, error = transfer.push_file_verified(
                str(source), "/sdcard/Download/test.txt", lambda: False
            )
            self.assertFalse(ok)
            self.assertIn("SHA-256", error)
            self.assertFalse(any("mv -f" in call.args[0] for call in shell.call_args_list))

    @patch.object(transfer, "adb_shell")
    @patch.object(transfer, "remote_sha256")
    @patch.object(transfer, "run_adb_push_quiet", return_value=(True, "ok"))
    def test_upload_valid_hash_commits(self, _push, remote_sha, shell):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "test.txt"
            source.write_text("VERIFIED CONTENT")
            remote_sha.return_value = transfer.local_sha256(source)
            shell.return_value = CompletedProcess([], 0, "", "")
            ok, _ = transfer.push_file_verified(
                str(source), "/sdcard/Download/test.txt", lambda: False
            )
            self.assertTrue(ok)
            self.assertEqual(sum("mv -f" in call.args[0] for call in shell.call_args_list), 1)

    @patch.object(transfer, "remote_sha256", return_value="0" * 64)
    @patch.object(transfer, "run_adb_pull")
    def test_download_bad_hash_preserves_existing_local(self, pull, _hash):
        def fake_pull(remote, local, log, cancel):
            Path(local).write_text("NEW CONTENT")
            return True, ["pulled"]
        pull.side_effect = fake_pull
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "test.txt"
            target.write_text("ORIGINAL")
            ok, errors = transfer.pull_file_verified(
                "/sdcard/Download/test.txt", target, lambda _: None, lambda: False
            )
            self.assertFalse(ok)
            self.assertEqual(target.read_text(), "ORIGINAL")
            self.assertFalse(list(Path(td).glob("*.pt-part-*")))

    @patch.object(transfer, "remote_sha256")
    @patch.object(transfer, "run_adb_pull")
    def test_download_good_hash_replaces_original(self, pull, remote_sha):
        def fake_pull(remote, local, log, cancel):
            Path(local).write_text("NEW VERIFIED")
            return True, ["pulled"]
        pull.side_effect = fake_pull
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "test.txt"
            target.write_text("ORIGINAL")
            expected = Path(td) / "expected"
            expected.write_text("NEW VERIFIED")
            remote_sha.return_value = transfer.local_sha256(expected)
            ok, _ = transfer.pull_file_verified(
                "/sdcard/Download/test.txt", target, lambda _: None, lambda: False
            )
            self.assertTrue(ok)
            self.assertEqual(target.read_text(), "NEW VERIFIED")



    @patch.object(transfer.subprocess, "Popen")
    def test_download_cancellation_kills_stalled_adb(self, popen):
        class Stalled:
            def __init__(self):
                self.attempts = 0
                self.killed = False
                self.returncode = None

            def communicate(self, timeout=None):
                if self.killed:
                    return "", ""
                self.attempts += 1
                raise transfer.subprocess.TimeoutExpired(["adb", "pull"], timeout)

            def kill(self):
                self.killed = True
                self.returncode = -9

            def poll(self):
                return self.returncode

        proc = Stalled()
        popen.return_value = proc
        ok, errors = transfer.run_adb_pull(
            "/sdcard/Download/file.txt", "/tmp/pt-test-file.txt",
            lambda _: None, lambda: proc.attempts >= 2,
        )
        self.assertFalse(ok)
        self.assertEqual(errors, ["已取消"])
        self.assertTrue(proc.killed)


class TestVerifiedFolderResume(unittest.TestCase):
    @patch.object(transfer, "push_file_verified", return_value=(True, "ok"))
    @patch.object(transfer, "remote_sha256")
    def test_completed_files_skipped_only_when_hashes_match(self, remote_hash, push):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            first, second = root / "first.txt", root / "second.txt"
            first.write_text("FIRST")
            second.write_text("SECOND")
            remote_hash.return_value = transfer.local_sha256(first)
            log = []
            progress = transfer.FileProgressTracker(11, 2, lambda *args: None)
            ok, _ = transfer._push_folder_files_parallel(
                [(first, "first.txt"), (second, "second.txt")],
                "/sdcard/Download", root, log.append, lambda: False,
                progress=progress, existing_files={"first.txt"},
            )
            self.assertTrue(ok)
            self.assertEqual(push.call_count, 1)
            self.assertTrue(push.call_args.args[0].endswith("second.txt"))
            self.assertTrue(any("复用已校验文件" in entry for entry in log))
            self.assertEqual(progress.done_files, 2)


class TestDeviceSelectionDuringTransfer(unittest.TestCase):
    @staticmethod
    def busy_window():
        win = Mock()
        win._busy = True
        win._closing = False
        win._device_gen = 9
        win._device_probe_busy = True
        return win

    def test_pending_device_success_does_not_switch_target(self):
        from phonetransfer.ui.main_window import MainWindow
        from phonetransfer.adb.core import get_active_serial, set_active_serial
        old = get_active_serial()
        try:
            set_active_serial("emulator-5554")
            win = self.busy_window()
            MainWindow._on_device_ok(win, {"devices": [
                {"serial": "other-device", "state": "device"}]}, 9)
            self.assertEqual(get_active_serial(), "emulator-5554")
            self.assertFalse(win._device_probe_busy)
        finally:
            set_active_serial(old)

    def test_pending_device_failure_does_not_clear_target(self):
        from phonetransfer.ui.main_window import MainWindow
        from phonetransfer.adb.core import get_active_serial, set_active_serial
        old = get_active_serial()
        try:
            set_active_serial("emulator-5554")
            win = self.busy_window()
            MainWindow._on_device_fail(win, "disconnected", 9)
            self.assertEqual(get_active_serial(), "emulator-5554")
            self.assertFalse(win._device_probe_busy)
        finally:
            set_active_serial(old)

    def test_manual_refresh_blocked_while_busy(self):
        from phonetransfer.ui.main_window import MainWindow
        win = self.busy_window()
        MainWindow.refresh_device(win, manual=True)
        win._device_worker.probe.assert_not_called()



if __name__ == "__main__":
    unittest.main()
