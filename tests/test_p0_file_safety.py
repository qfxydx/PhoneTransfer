"""Isolated no-device tests for PhoneTransfer file operation safety."""
import tempfile
import time
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

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
    def test_rename_unsafe_parent(self, shell):
        shell.side_effect = [
            CompletedProcess([], 0, "/storage/emulated/0/Download\n", ""),
            CompletedProcess([], 0, "/data/system\n", ""),
        ]
        self.assertFalse(file_ops.remote_rename("/sdcard/Download/a", "/sdcard/link/a")[0])
        self.assertEqual(shell.call_count, 2)


class TestTransferFailures(unittest.TestCase):
    @patch.object(transfer, "format_adb_failure", return_value="failed")
    @patch.object(transfer, "run_adb_push_quiet")
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




if __name__ == "__main__":
    unittest.main()
