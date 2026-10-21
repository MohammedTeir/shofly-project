"""Offline tests for aria2c validation and retention; no external downloads."""
import hashlib
import json
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from shofly_worker.aria2_downloader import download_aria2
from shofly_worker.errors import WorkerError
from shofly_worker.retention import cleanup, job_dir, mark_final


class FakeProcess:
    returncode = 0

    def poll(self):
        return 0


class Aria2Tests(unittest.TestCase):
    def test_allowlist_required(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(WorkerError) as ctx:
                download_aria2("https://example.com/video.mp4", Path(root) / "file", 100, 5, None)
            self.assertEqual(ctx.exception.code, "ARIA2_ALLOWLIST_REQUIRED")

    def test_private_address_blocked(self):
        with tempfile.TemporaryDirectory() as root:
            with patch("shofly_worker.aria2_downloader.check_url", side_effect=__import__("shofly_worker.ssrf", fromlist=["UnsafeURL"]).UnsafeURL("private")):
                with self.assertRaises(WorkerError) as ctx:
                    download_aria2("https://example.com/a", Path(root) / "file", 100, 5, {"example.com"})
                self.assertEqual(ctx.exception.code, "UNSAFE_SOURCE")

    def test_invalid_config(self):
        with tempfile.TemporaryDirectory() as root:
            with patch("shofly_worker.aria2_downloader.check_url"):
                with self.assertRaises(WorkerError) as ctx:
                    download_aria2("https://example.com/a", Path(root) / "file", 100, 5, {"example.com"}, connections=9)
                self.assertEqual(ctx.exception.code, "INVALID_DOWNLOAD_CONFIG")

    def test_success_hash_and_parallel_flags(self):
        with tempfile.TemporaryDirectory() as root:
            dest = Path(root) / "source.bin"
            dest.write_bytes(b"authorized-test-content")
            with patch("shofly_worker.aria2_downloader.check_url"), patch("shofly_worker.aria2_downloader.subprocess.Popen", return_value=FakeProcess()) as popen:
                size, digest = download_aria2("https://example.com/a", dest, 100, 5, {"example.com"}, connections=4)
            self.assertEqual(size, len(b"authorized-test-content"))
            self.assertEqual(digest, hashlib.sha256(b"authorized-test-content").hexdigest())
            cmd = popen.call_args.args[0]
            self.assertIn("--split=4", cmd)
            self.assertIn("--continue=true", cmd)
            self.assertIn("--max-redirect=0", cmd)

    def test_oversize_file(self):
        with tempfile.TemporaryDirectory() as root:
            dest = Path(root) / "source.bin"
            dest.write_bytes(b"x" * 11)
            with patch("shofly_worker.aria2_downloader.check_url"), patch("shofly_worker.aria2_downloader.subprocess.Popen", return_value=FakeProcess()):
                with self.assertRaises(WorkerError) as ctx:
                    download_aria2("https://example.com/a", dest, 10, 5, {"example.com"})
            self.assertEqual(ctx.exception.code, "FILE_TOO_LARGE")


class RetentionTests(unittest.TestCase):
    def test_final_retained_then_expired(self):
        with tempfile.TemporaryDirectory() as root:
            jid = "11111111-1111-4111-8111-111111111111"
            folder = job_dir(root, jid)
            folder.mkdir()
            mark_final(folder)
            self.assertEqual(cleanup(root, now=time.time() + 47 * 3600), 0)
            self.assertEqual(cleanup(root, now=time.time() + 49 * 3600), 1)
            self.assertFalse(folder.exists())

    def test_orphan_and_unrelated_folder(self):
        with tempfile.TemporaryDirectory() as root:
            jid = "22222222-2222-4222-8222-222222222222"
            folder = job_dir(root, jid)
            folder.mkdir()
            other = Path(root) / "keep-me"
            other.mkdir()
            old = time.time() - 8 * 86400
            import os
            os.utime(folder, (old, old))
            self.assertEqual(cleanup(root), 1)
            self.assertTrue(other.exists())

    def test_invalid_job_id(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError):
                job_dir(root, "../outside")


if __name__ == "__main__":
    unittest.main()
