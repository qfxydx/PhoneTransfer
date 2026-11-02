"""QuickLook cache isolation and integrity tests (no Android device required)."""
from pathlib import Path
from subprocess import CompletedProcess
import tempfile
import unittest
from unittest.mock import patch

from phonetransfer.ui.quicklook import QuickLookManager
from phonetransfer.workers.preview_worker import RemotePreviewWorker


class TestPreviewCache(unittest.TestCase):
    def test_device_and_remote_path_isolation(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.object(QuickLookManager, "preview_cache_dir", return_value=Path(td)):
                a = QuickLookManager.get_preview_cache_path("/sdcard/DCIM/a.jpg", "device-a")
                b = QuickLookManager.get_preview_cache_path("/sdcard/Download/a.jpg", "device-a")
                c = QuickLookManager.get_preview_cache_path("/sdcard/DCIM/a.jpg", "device-b")
                self.assertEqual(len({a, b, c}), 3)
                self.assertEqual(a.name, "a.jpg")

    def _worker(self, cache: Path, content: bytes, signature: str):
        w = RemotePreviewWorker("/sdcard/DCIM/a.jpg", len(content), str(cache), serial="emulator-5554")
        events = {"ready": [], "failed": []}
        w.ready.connect(events["ready"].append)
        w.failed.connect(events["failed"].append)
        return w, events

    @patch("phonetransfer.workers.preview_worker.reclaim_qobject_to_main")
    def test_cache_reuse_only_with_matching_metadata(self, _reclaim):
        with tempfile.TemporaryDirectory() as td:
            cache = Path(td) / "photo.jpg"
            pulled = []

            def pull(command, **kwargs):
                pulled.append(command)
                Path(command[-1]).write_bytes(b"ABCD")
                return CompletedProcess(command, 0, "", "")

            with patch.object(RemotePreviewWorker, "_remote_signature", return_value=(4, "v1")), \
                 patch("phonetransfer.workers.preview_worker.subprocess.run", side_effect=pull):
                w, e = self._worker(cache, b"ABCD", "v1")
                w.run()
                self.assertEqual(e["failed"], [])
                self.assertEqual(cache.read_bytes(), b"ABCD")
                w2, e2 = self._worker(cache, b"ABCD", "v1")
                w2.run()
                self.assertEqual(e2["failed"], [])
                self.assertEqual(len(pulled), 1)

    @patch("phonetransfer.workers.preview_worker.reclaim_qobject_to_main")
    def test_changed_same_size_invalidates_cache(self, _reclaim):
        with tempfile.TemporaryDirectory() as td:
            cache = Path(td) / "photo.jpg"
            cache.write_bytes(b"OLD!")
            meta = cache.with_name(cache.name + ".ptmeta")
            meta.write_text("4|old", encoding="utf-8")

            def pull(command, **kwargs):
                Path(command[-1]).write_bytes(b"NEW!")
                return CompletedProcess(command, 0, "", "")

            with patch.object(RemotePreviewWorker, "_remote_signature", return_value=(4, "new")), \
                 patch("phonetransfer.workers.preview_worker.subprocess.run", side_effect=pull):
                w, e = self._worker(cache, b"NEW!", "new")
                w.run()
                self.assertEqual(e["failed"], [])
                self.assertEqual(cache.read_bytes(), b"NEW!")
                self.assertEqual(meta.read_text(), "4|new")

    @patch("phonetransfer.workers.preview_worker.reclaim_qobject_to_main")
    def test_failed_pull_preserves_existing_cache(self, _reclaim):
        with tempfile.TemporaryDirectory() as td:
            cache = Path(td) / "photo.jpg"
            cache.write_bytes(b"OLD!")
            with patch.object(RemotePreviewWorker, "_remote_signature", return_value=(4, "new")), \
                 patch("phonetransfer.workers.preview_worker.subprocess.run",
                       return_value=CompletedProcess([], 1, "", "disconnected")):
                w, e = self._worker(cache, b"NEW!", "new")
                w.run()
                self.assertTrue(e["failed"])
                self.assertEqual(cache.read_bytes(), b"OLD!")
                self.assertEqual(len(list(Path(td).glob("*.pt-preview-*"))), 0)

    @patch("phonetransfer.workers.preview_worker.reclaim_qobject_to_main")
    def test_incomplete_pull_is_rejected(self, _reclaim):
        with tempfile.TemporaryDirectory() as td:
            cache = Path(td) / "photo.jpg"
            def pull(command, **kwargs):
                Path(command[-1]).write_bytes(b"A")
                return CompletedProcess(command, 0, "", "")
            with patch.object(RemotePreviewWorker, "_remote_signature", return_value=(4, "new")), \
                 patch("phonetransfer.workers.preview_worker.subprocess.run", side_effect=pull):
                w, e = self._worker(cache, b"NEW!", "new")
                w.run()
                self.assertTrue(e["failed"])
                self.assertFalse(cache.exists())


if __name__ == "__main__":
    unittest.main()
