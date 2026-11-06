import hashlib
from io import BytesIO
import importlib.util
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
import zipfile

from test_player import m, QSignalSpy


class UpdateChecks(unittest.TestCase):
    def release(self, version="0.2.1.42", *, checksum=True, **extra):
        names = ["AuroraMusicPlayer.exe"]
        if checksum:
            names.append("AuroraMusicPlayer.exe.sha256.txt")
        return dict(tag_name="v" + version, assets=[
            {"name": name, "browser_download_url": "https://github.com/owner/repo/releases/download/v" + version + "/" + name}
            for name in names
        ], **extra)

    def check(self, responses):
        worker = m.AppUpdateCheckerWorker(current_version="0.2.0")
        ready = QSignalSpy(worker.update_checked)
        with patch.object(m.sys, "frozen", True, create=True), \
             patch.object(worker, "_http_get_json", side_effect=responses), \
             patch.object(worker, "_http_get_text") as source:
            worker.run()
        source.assert_not_called()
        self.assertEqual(len(ready), 1)
        return ready[0][0]

    def test_ready_release_updates_the_installed_exe(self):
        info = self.check([self.release()])
        self.assertTrue(info["is_newer"])
        self.assertEqual(info["latest_version"], "0.2.1.42")
        self.assertTrue(info["exe_url"].endswith("/AuroraMusicPlayer.exe"))
        self.assertTrue(info["exe_sha256_url"].endswith(".sha256.txt"))

    def test_unfinished_release_does_not_offer_an_unavailable_update(self):
        info = self.check([self.release(checksum=False), []])
        self.assertFalse(info["is_newer"])
        self.assertTrue(info["no_releases_yet"])
        self.assertEqual(info["exe_url"], "")

    def test_drafts_and_prereleases_are_skipped(self):
        draft, preview = self.release("0.3.0", draft=True), self.release("0.4.0", prerelease=True)
        info = self.check([draft, [draft, preview, self.release()]])
        self.assertEqual(info["latest_version"], "0.2.1.42")

    def test_same_version_is_not_offered_again(self):
        info = self.check([self.release("0.2.0")])
        self.assertFalse(info["is_newer"])

    def test_api_failure_does_not_report_the_app_as_up_to_date(self):
        info = self.check([OSError("unavailable"), OSError("unavailable")])
        self.assertFalse(info["ok"])
        self.assertFalse(info["is_newer"])
        self.assertTrue(info["error"])


class UpdateInstallation(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="aurora-update-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.exe = self.root / "AuroraMusicPlayer.exe"
        self.exe.write_bytes(b"MZ current version")
        self.payload = b"MZ new version"
        self.worker = m.AppUpdateInstallerWorker({
            "latest_version": "0.2.1.42",
            "exe_url": "https://github.com/owner/repo/releases/download/v0.2.1.42/AuroraMusicPlayer.exe",
            "exe_sha256_url": "https://github.com/owner/repo/releases/download/v0.2.1.42/AuroraMusicPlayer.exe.sha256.txt",
        })
        self.ready, self.failed = QSignalSpy(self.worker.update_ready_to_restart), QSignalSpy(self.worker.update_failed)

    def opener(self, body):
        opener = Mock()
        opener.open.return_value = BytesIO(body)
        return patch.object(m, "build_opener", return_value=opener)

    def install(self, checksum):
        def download(url, destination, label):
            destination.write_bytes(self.payload)
        context = m._create_stream_ssl_context()
        with patch.object(m.sys, "frozen", True, create=True), \
             patch.object(m.sys, "platform", "win32"), \
             patch.object(m.sys, "executable", str(self.exe)), \
             patch.object(m, "app_cache_directory", return_value=self.root / "cache"), \
             patch.object(m, "_create_stream_ssl_context", return_value=context), \
             patch.object(self.worker, "_download_file", side_effect=download), \
             self.opener(checksum):
            self.worker.run()

    def test_downloaded_exe_is_verified_and_staged_without_overwriting_the_running_app(self):
        self.install((hashlib.sha256(self.payload).hexdigest() + "  AuroraMusicPlayer.exe\n").encode())
        self.assertFalse(self.failed, list(self.failed))
        self.assertEqual(len(self.ready), 1)
        self.assertEqual(self.exe.read_bytes(), b"MZ current version")
        self.assertEqual(self.exe.with_suffix(".new.exe").read_bytes(), self.payload)
        script = Path(self.ready[0][0]).read_text(encoding="utf-8")
        self.assertIn("goto copy_loop", script)
        self.assertIn("if not errorlevel 1 goto restart", script)

    def test_checksum_mismatch_preserves_the_installed_app_and_removes_the_bad_download(self):
        self.install(b"0" * 64)
        self.assertFalse(self.ready)
        self.assertEqual(len(self.failed), 1)
        self.assertIn("SHA256", self.failed[0][0])
        self.assertEqual(self.exe.read_bytes(), b"MZ current version")
        self.assertFalse(self.exe.with_suffix(".new.exe").exists())

    def test_folder_release_is_verified_and_extracted_before_restarting(self):
        (self.exe.parent / "_internal").mkdir()
        archive = BytesIO()
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("AuroraMusicPlayer/AuroraMusicPlayer.exe", self.payload)
            bundle.writestr("AuroraMusicPlayer/_internal/runtime.dll", b"new runtime")
        self.payload = archive.getvalue()
        self.worker.update_info.update(zip_url="https://github.com/update.zip", zip_sha256_url="https://github.com/update.zip.sha256.txt")
        self.install(hashlib.sha256(self.payload).hexdigest().encode())
        self.assertFalse(self.failed, list(self.failed))
        self.assertEqual(len(self.ready), 1)
        root = self.root / "cache/updater/extracted/AuroraMusicPlayer"
        self.assertEqual((root / "_internal/runtime.dll").read_bytes(), b"new runtime")
        self.assertEqual(self.exe.read_bytes(), b"MZ current version")

    @unittest.skipUnless(sys.platform == "win32", "Windows replacement and file-lock semantics")
    def test_windows_helper_retries_a_locked_file_then_replaces_and_restarts_it(self):
        import ctypes
        from ctypes import wintypes
        directory = self.root / "Музыка 100% !"
        directory.mkdir()
        current = directory / f"AuroraUpdateTest{time.time_ns()}.exe"
        payload = current.with_suffix(".new.exe")
        current.write_bytes(b"old version")
        shutil.copyfile(shutil.which("cmd.exe"), payload)
        expected = hashlib.sha256(payload.read_bytes()).digest()
        script = self.root / "apply_update.bat"
        self.worker._write_windows_update_script(script, current, payload)
        script.write_bytes(script.read_bytes().replace(b"@echo off", b"@echo on", 1))
        create = ctypes.windll.kernel32.CreateFileW
        create.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                           wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
        create.restype = wintypes.HANDLE
        close = ctypes.windll.kernel32.CloseHandle
        close.argtypes = (wintypes.HANDLE,)

        class ProcessEntry(ctypes.Structure):
            _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                        ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                        ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                        ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
                        ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260)]

        snapshot = ctypes.windll.kernel32.CreateToolhelp32Snapshot
        snapshot.argtypes, snapshot.restype = (wintypes.DWORD, wintypes.DWORD), wintypes.HANDLE
        first, following = ctypes.windll.kernel32.Process32FirstW, ctypes.windll.kernel32.Process32NextW
        for function in (first, following):
            function.argtypes, function.restype = (wintypes.HANDLE, ctypes.POINTER(ProcessEntry)), wintypes.BOOL

        def running_pids():
            handle = snapshot(2, 0)
            if handle == ctypes.c_void_p(-1).value:
                raise ctypes.WinError()
            try:
                entry = ProcessEntry()
                entry.dwSize = ctypes.sizeof(entry)
                valid, found = first(handle, ctypes.byref(entry)), []
                while valid:
                    if entry.szExeFile.casefold() == current.name.casefold():
                        found.append(entry.th32ProcessID)
                    valid = following(handle, ctypes.byref(entry))
                return found
            finally:
                close(handle)

        handle = create(str(current), 0x80000000, 1, None, 3, 0, None)
        self.assertNotEqual(handle, ctypes.c_void_p(-1).value)
        process = None
        try:
            trace = self.root / "trace.log"
            with trace.open("wb") as output:
                process = m._launch_windows_update_script(script, stdout=output, stderr=subprocess.STDOUT)
            log = self.root / "update.log"
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                if log.exists() and len(log.read_bytes()) > 40:
                    break
                time.sleep(.05)
            self.assertIsNone(process.poll(), "Updater exited instead of retrying the locked file")
            self.assertEqual(current.read_bytes(), b"old version")
            close(handle)
            handle = None
            try:
                code = process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self.fail("Updater did not finish:\n" + log.read_text(encoding="utf-8", errors="replace")
                          + "\nCommands:\n" + trace.read_text(encoding="utf-8", errors="replace"))
            self.assertEqual(code, 0, log.read_text(encoding="utf-8", errors="replace"))
            deadline = time.monotonic() + 10
            while not running_pids() and time.monotonic() < deadline:
                time.sleep(.05)
            self.assertTrue(running_pids(), "Updated EXE was not restarted")
            self.assertEqual(hashlib.sha256(current.read_bytes()).digest(), expected)
            self.assertFalse(payload.exists())
        finally:
            if handle is not None:
                close(handle)
            if process is not None and process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            for pid in running_pids():
                try:
                    m.os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            deadline = time.monotonic() + 5
            while running_pids() and time.monotonic() < deadline:
                time.sleep(.05)

    def test_invalid_and_missing_checksums_block_installation(self):
        for value in (b"", b"not a checksum", b"<html>not found</html>"):
            with self.subTest(checksum=value), self.opener(value):
                with self.assertRaisesRegex(RuntimeError, "SHA256"):
                    self.worker._verify_sha256(self.exe, "https://github.com/hash")
        with self.assertRaisesRegex(RuntimeError, "SHA256"):
            self.worker._verify_sha256(self.exe, "")

    def test_checksum_download_failure_blocks_installation(self):
        with patch.object(m, "build_opener") as factory:
            factory.return_value.open.side_effect = OSError("offline")
            with self.assertRaisesRegex(RuntimeError, "SHA256"):
                self.worker._verify_sha256(self.exe, "https://github.com/hash")

    def test_frozen_app_never_replaces_an_unpacked_python_script_when_no_exe_is_ready(self):
        self.worker.update_info = {"source_url": "https://raw.githubusercontent.com/owner/repo/main/player.py"}
        with patch.object(m.sys, "frozen", True, create=True), \
             patch.object(m.sys, "platform", "win32"), \
             patch.object(m.sys, "executable", str(self.exe)), \
             patch.object(self.worker, "_download_file") as download:
            self.worker.run()
        download.assert_not_called()
        self.assertFalse(self.ready)
        self.assertEqual(len(self.failed), 1)

    def test_incomplete_http_download_is_rejected(self):
        response = BytesIO(b"short")
        response.headers = {"Content-Length": "100"}
        with patch.object(m, "build_opener") as factory:
            factory.return_value.open.return_value = response
            with self.assertRaisesRegex(RuntimeError, "не полностью"):
                self.worker._download_file("https://github.com/file", self.root / "partial", "Test")


class ReleaseVersions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / "tools" / "prepare_release.py"
        spec = importlib.util.spec_from_file_location("prepare_release", path)
        cls.release = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.release)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.source = Path(self.directory.name) / "player.py"
        self.source.write_text('APP_VERSION = "0.2.1"\nOTHER = "unchanged"\n', encoding="utf-8")

    def test_successive_builds_are_newer_without_editing_the_base_version(self):
        first = self.release.prepare_release(self.source, "41")
        second = self.release.prepare_release(self.source, "42")
        self.assertEqual(first, "0.2.1.41")
        self.assertGreater(m._parse_version_tuple(second), m._parse_version_tuple(first))
        self.assertIn('OTHER = "unchanged"', self.source.read_text())

    def test_tag_version_matches_the_version_embedded_in_the_exe(self):
        self.assertEqual(self.release.prepare_release(self.source, "42", "v0.3.0"), "0.3.0")
        self.assertIn('APP_VERSION = "0.3.0"', self.source.read_text())

    def test_invalid_release_inputs_leave_the_source_unchanged(self):
        before = self.source.read_bytes()
        for number, tag in (("0", ""), ("invalid", ""), ("42", "v1.2.3-beta")):
            with self.subTest(number=number, tag=tag), self.assertRaises(ValueError):
                self.release.prepare_release(self.source, number, tag)
            self.assertEqual(self.source.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
