"""Local origins reproduce broken range responses without service accounts."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import re
import threading
import unittest
from unittest.mock import Mock, patch
from urllib.request import ProxyHandler, build_opener

import test_player as player_fixture
from test_player import m, QSignalSpy


class StreamTransport(unittest.TestCase):
    use_requests = True

    def setUp(self):
        self.payload = bytes(range(251)) * (m.BufferedStreamEntry.BLOCK_SIZE * 8 // 251 + 1)
        self.mode = "normal"
        self.ranges = []
        self.segment_requested = threading.Event()
        self.release_segment = threading.Event()
        owner = self

        class Origin(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_GET(self):
                if owner.mode == "segments":
                    if self.path == "/part1":
                        owner.segment_requested.set()
                        owner.release_segment.wait(timeout=3)
                        data = owner.payload[m.BufferedStreamEntry.BLOCK_SIZE:]
                    else:
                        data = owner.payload[:m.BufferedStreamEntry.BLOCK_SIZE]
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    try:
                        self.wfile.write(data)
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                    return
                match = re.fullmatch(r"bytes=(\d+)-(\d+)", self.headers.get("Range", ""))
                start, end = map(int, match.groups()) if match else (0, len(owner.payload) - 1)
                owner.ranges.append((start, end))
                total = len(owner.payload)
                if owner.mode == "virtual":
                    total = m.BufferedStreamEntry.BLOCK_SIZE * (m.BufferedStreamEntry.MAX_CACHED_BLOCKS + 6)
                if start >= total:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{total}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                end = min(end, total - 1)
                status = 206
                if owner.mode == "short" and len(owner.ranges) == 1:
                    end = min(end, start + m.BufferedStreamEntry.BLOCK_SIZE // 2 - 1)
                elif owner.mode == "wrong_offset":
                    start, end = 0, m.BufferedStreamEntry.BLOCK_SIZE - 1
                elif owner.mode == "ignore_range":
                    status, start, end = 200, 0, total - 1
                data = (bytes([start // m.BufferedStreamEntry.BLOCK_SIZE % 251]) * (end - start + 1)
                        if owner.mode == "virtual" else owner.payload[start:end + 1])
                self.send_response(status)
                self.send_header("Content-Length", str(len(data)))
                if status == 206:
                    self.send_header("Content-Range", f"bytes {start}-{end}/{total}")
                self.end_headers()
                if owner.mode == "cut" and len(owner.ranges) == 1:
                    data = data[:m.BufferedStreamEntry.BLOCK_SIZE * 3 // 2]
                try:
                    self.wfile.write(data)
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass
                self.close_connection = True

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Origin)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.entries = []
        factory = m._create_keepalive_stream_session

        def local_session(**kwargs):
            if not self.use_requests:
                return None
            session = factory(**kwargs)
            session.trust_env = False  # Only the local origin above is contacted.
            return session

        self.session_patch = patch.object(m, "_create_keepalive_stream_session", side_effect=local_session)
        self.session_patch.start()

    def tearDown(self):
        self.release_segment.set()
        for entry in self.entries:
            entry.close()
        self.session_patch.stop()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def entry(self):
        entry = m.BufferedStreamEntry(f"http://127.0.0.1:{self.server.server_port}/audio")
        entry._build_opener = lambda: build_opener(ProxyHandler({}))
        self.entries.append(entry)
        return entry

    def test_tail_probe_does_not_end_prefetching_the_middle_of_the_track(self):
        entry = self.entry()
        block = entry.BLOCK_SIZE
        entry._stream_span_into_blocks(0, 2)
        tail = (len(self.payload) - 1) // block
        entry._stream_span_into_blocks(tail, 1)
        self.assertFalse(entry.is_complete())
        self.assertFalse(entry.eof, "Reading the last block must not finish an incomplete buffer")

    def test_short_range_response_is_completed_before_its_block_is_served(self):
        self.mode = "short"
        entry = self.entry()
        data = entry._stream_span_into_blocks(0, 2)
        self.assertEqual(data, self.payload[:entry.BLOCK_SIZE])
        self.assertEqual(entry.blocks[0], self.payload[:entry.BLOCK_SIZE])
        self.assertGreater(len(self.ranges), 1)

    def test_connection_reset_does_not_leave_partial_blocks_in_the_cache(self):
        self.mode = "cut"
        entry = self.entry()
        entry._stream_span_into_blocks(0, 3)
        entry._stream_span_into_blocks(1, 2)
        data = b"".join(entry.blocks[index] for index in range(3))
        self.assertEqual(data, self.payload[:entry.BLOCK_SIZE * 3])
        self.assertGreater(len(self.ranges), 1)

    def test_response_for_the_wrong_byte_offset_never_poison_the_cache(self):
        self.mode = "wrong_offset"
        entry = self.entry()
        self.assertIsNone(entry._stream_span_into_blocks(1, 1))
        self.assertNotIn(1, entry.blocks)
        self.assertTrue(entry.failed)

    def test_ignored_range_returns_the_correct_bytes_without_false_eof(self):
        self.mode = "ignore_range"
        entry = self.entry()
        block = entry.BLOCK_SIZE
        data = entry._stream_span_into_blocks(1, 1)
        self.assertEqual(data, self.payload[block:block * 2])
        self.assertEqual(entry.total_size, len(self.payload))
        self.assertFalse(entry.eof)

    def test_range_416_sets_resource_size_without_ending_other_reads(self):
        entry = self.entry()
        past_end = len(self.payload) // entry.BLOCK_SIZE + 2
        self.assertEqual(entry._stream_span_into_blocks(past_end, 1), b"")
        self.assertEqual(entry.total_size, len(self.payload))
        self.assertFalse(entry.eof)

    def test_cache_capacity_does_not_limit_the_byte_offsets_that_can_be_read(self):
        self.mode = "virtual"
        entry = self.entry()
        index = entry.MAX_CACHED_BLOCKS + 3
        data = entry._stream_span_into_blocks(index, 1)
        self.assertEqual(data, bytes([index % 251]) * entry.BLOCK_SIZE)
        self.assertLessEqual(len(entry.blocks), entry.MAX_CACHED_BLOCKS)

    def start_hls(self, resume_position):
        self.mode = "segments"
        entry = self.entry()
        entry.protocol = "hls"
        base = f"http://127.0.0.1:{self.server.server_port}"
        entry.fragments = [{"url": base + "/part0"}, {"url": base + "/part1"}]
        worker = m.StreamWorker({"source": "soundcloud", "url": "https://example.invalid/track"},
                                resume_position_ms=resume_position)
        done, result = threading.Event(), []
        def wait():
            result.append(worker._wait_for_proxy(entry, timeout=2))
            done.set()
        thread = threading.Thread(target=wait, daemon=True)
        thread.start()
        self.assertTrue(self.segment_requested.wait(timeout=2))
        return entry, worker, thread, done, result

    def test_hls_recovery_waits_for_a_seekable_complete_buffer(self):
        entry, worker, thread, done, result = self.start_hls(120000)
        try:
            self.assertFalse(done.wait(.05), "A recovery must not open HLS with an unknown byte length")
        finally:
            self.release_segment.set()
            thread.join(timeout=2)
        self.assertTrue(done.is_set())
        self.assertEqual(result, [True])
        self.assertEqual(entry.total_size, len(self.payload))
        self.assertTrue(entry.is_complete())

    def test_normal_hls_playback_can_start_before_the_complete_download(self):
        entry, worker, thread, done, result = self.start_hls(0)
        try:
            self.assertTrue(done.wait(timeout=1))
            self.assertEqual(result, [True])
            self.assertIsNone(entry.total_size)
        finally:
            self.release_segment.set()
            thread.join(timeout=2)


class HLSFailures(unittest.TestCase):
    def test_missing_later_segment_never_counts_as_a_complete_song(self):
        entry = m.BufferedStreamEntry("https://example.invalid/hls", protocol="hls",
                                      fragments=[{"url": "https://example.invalid/0"}, {"url": "https://example.invalid/1"}])
        session = Mock()
        session.get.side_effect = lambda url, **_kwargs: (
            Mock(status_code=200, content=b"audio" * 10000) if url.endswith("/0") else Mock(status_code=503, content=b""))
        try:
            with patch.object(entry, "_get_session", return_value=session), patch.object(m.time, "sleep"):
                entry._download_hls(Mock())
            self.assertTrue(entry.hls_buffer)
            self.assertTrue(entry.failed)
            self.assertFalse(entry.is_complete())
            with patch.object(entry, "start"):
                self.assertFalse(entry.wait_for_initial_bytes())
        finally:
            entry.close()

    def test_query_range_content_length_is_not_the_length_of_the_entire_song(self):
        block = m.BufferedStreamEntry.BLOCK_SIZE
        total = block * 8
        entry = m.BufferedStreamEntry(f"https://r1.googlevideo.com/videoplayback?clen={total}&range=0-{block * 2 - 1}")
        response = Mock(status_code=200, headers={"Content-Length": str(block * 2)})
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.iter_content.return_value = iter([b"a" * block, b"b" * block])
        session = Mock()
        session.get.return_value = response
        try:
            with patch.object(entry, "_get_session", return_value=session):
                self.assertEqual(entry._stream_span_into_blocks(0, 2), b"a" * block)
            self.assertEqual(entry.total_size, total)
            self.assertFalse(entry.eof)
            self.assertFalse(entry.is_complete())
        finally:
            entry.close()


class StdlibStreamTransport(StreamTransport):
    use_requests = False


class ExtractionSafety(unittest.TestCase):
    def worker(self):
        return m.StreamWorker({"source": "youtube", "url": "https://www.youtube.com/watch?v=test0000001"})

    def test_a_different_format_is_never_used_as_a_byte_range_backup(self):
        worker = self.worker()
        entry = Mock()
        entry.wait_for_initial_bytes.return_value = True
        entry.canonical_url.return_value = "http://127.0.0.1/stream/test.webm"
        info = {"url": "https://example.invalid/251", "format_id": "251", "ext": "webm", "protocol": "https",
                "formats": [{"url": "https://example.invalid/250", "format_id": "250", "ext": "webm",
                             "protocol": "https", "acodec": "opus", "vcodec": "none"}]}
        with patch.object(m.LocalStreamProxy, "instance") as proxy:
            proxy.return_value.register_stream.return_value = ("proxy", entry)
            self.assertIsNotNone(worker._try_open_proxy_stream(info))
            self.assertFalse(proxy.return_value.register_stream.call_args.kwargs.get("backup_urls"))

    def test_youtube_first_uses_supported_yt_dlp_defaults(self):
        worker = self.worker()
        with patch.object(worker, "_is_real_extract", return_value=True), \
             patch.object(worker, "_resolve_fast_soundcloud_stream", return_value=None), \
             patch.object(worker, "_extract", return_value={"url": "https://example.invalid/audio"}) as extract:
            worker.run()
        self.assertNotIn("extractor_args", extract.call_args.args[0])

    def test_failed_extraction_does_not_reinstall_packages_or_replace_live_modules(self):
        import yt_dlp
        original = yt_dlp
        worker = self.worker()
        failed = QSignalSpy(worker.failed)
        with patch.dict(m.sys.modules), \
             patch.object(worker, "_is_real_extract", return_value=True), \
             patch.object(worker, "_resolve_fast_soundcloud_stream", return_value=None), \
             patch.object(worker, "_extract", side_effect=[RuntimeError("HTTP Error 403"), RuntimeError("HTTP Error 403"),
                                                          {"url": "https://example.invalid/audio"}]), \
             patch.object(m.subprocess, "run", return_value=Mock(returncode=0)) as command:
            m.sys.modules.pop("unittest", None)  # Exercise the same path as the running application.
            worker.run()
            command.assert_not_called()
            self.assertIs(m.sys.modules.get("yt_dlp"), original)
        self.assertEqual(len(failed), 1)


class PlaybackEOF(unittest.TestCase):
    def test_a_complete_byte_buffer_does_not_hide_an_audio_stream_cut_in_half(self):
        fixture = player_fixture.PlayerChanges()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.addCleanup(fixture.tearDown)
        fixture.remote_playback_fixture()
        w = fixture.w
        w.current_track["duration"] = 10
        w._last_progress_position = 4800
        w._last_duration = 10000
        cached = Mock(failed=False)
        cached.is_complete.return_value = True
        with patch.object(w.player, "duration", return_value=5000), \
             patch.object(w.player, "source", return_value=m.QUrl("http://127.0.0.1:12345/stream/test.wav")), \
             patch.object(m.LocalStreamProxy, "instance") as proxy:
            proxy.return_value.get_entry_by_url.return_value = cached
            self.assertTrue(w._ended_early())


if __name__ == "__main__":
    unittest.main()
