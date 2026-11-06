"""Exercise the real yt-dlp extraction pipeline without external services."""

from contextlib import ExitStack
from http.cookiejar import Cookie, MozillaCookieJar
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from yt_dlp.extractor.common import InfoExtractor
from test_player import m, QSignalSpy


class OfflineAudioIE(InfoExtractor):
    _VALID_URL = r"aurora-test:(?P<id>[a-z]+)"

    def _real_extract(self, url):
        return {
            "id": self._match_id(url), "title": "Offline audio", "duration": 30,
            "url": "https://example.invalid/audio.mp3", "ext": "mp3",
            "acodec": "mp3", "vcodec": "none",
        }


class YtdlpContext(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.directory = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.stack.enter_context(patch.object(m.StreamWorker, "_SHARED_YDL", None))
        self.stack.enter_context(patch.object(m.StreamWorker, "get_soundcloud_client_id", return_value=None))
        self.stack.enter_context(patch.object(m.SearchWorker, "_SOUNDCLOUD_CACHED_CLIENT_ID", None))
        original = m.YoutubeDL
        self.contexts = []

        def create(options):
            # Only the input extractor is replaced; yt-dlp still initializes,
            # processes formats, builds headers and handles cookies itself.
            ydl = original(options, auto_init=False)
            ydl.add_info_extractor(OfflineAudioIE())
            self.contexts.append(ydl)
            return ydl

        self.stack.enter_context(patch.object(m, "YoutubeDL", side_effect=create))
        self.addCleanup(self.close_contexts)

    def close_contexts(self):
        for ydl in self.contexts:
            ydl.close()

    def worker(self, name="first"):
        return m.StreamWorker({"source": "youtube", "url": f"aurora-test:{name}"})

    def extract(self, name="first", **overrides):
        options = {
            **m.yt_dlp_tls_options(), "quiet": True, "no_warnings": True,
            "format": "bestaudio/best", "skip_download": True,
            "noplaylist": True, "cachedir": False, "ignoreconfig": True,
        }
        options.update(overrides)
        return self.worker(name)._extract(options)

    def test_first_track_keeps_constructor_http_headers(self):
        info = self.extract()
        self.assertEqual(info["url"], "https://example.invalid/audio.mp3")
        self.assertTrue(info["http_headers"]["User-Agent"])

    def test_first_track_after_prewarm_keeps_constructor_defaults(self):
        m.StreamWorker._warmup_shared_ydl()
        info = self.extract()
        self.assertTrue(info["http_headers"]["User-Agent"])

    def test_headers_from_previous_track_do_not_leak(self):
        m.StreamWorker._warmup_shared_ydl()
        first = self.extract(http_headers={"User-Agent": "Aurora-Test", "X-Aurora-Track": "first"})
        self.assertEqual(first["http_headers"]["X-Aurora-Track"], "first")
        second = self.extract("second")
        self.assertTrue(second["http_headers"]["User-Agent"])
        self.assertNotIn("X-Aurora-Track", second["http_headers"])

    def test_cookie_file_applies_to_its_request_without_leaking_to_the_next(self):
        path = Path(self.directory) / "cookies.txt"
        jar = MozillaCookieJar(str(path))
        jar.set_cookie(Cookie(
            version=0, name="aurora_fixture", value="authorized", port=None,
            port_specified=False, domain="example.invalid", domain_specified=True,
            domain_initial_dot=False, path="/", path_specified=True, secure=True,
            expires=int(time.time()) + 3600, discard=False, comment=None,
            comment_url=None, rest={}, rfc2109=False,
        ))
        jar.save()
        m.StreamWorker._warmup_shared_ydl()
        first = self.extract(cookiefile=str(path), http_headers={"User-Agent": "Aurora-Test"})
        self.assertIn("aurora_fixture=authorized", first["http_headers"].get("Cookie", ""))
        second = self.extract("second", http_headers={"User-Agent": "Aurora-Anonymous-Test"})
        self.assertNotIn("aurora_fixture", second["http_headers"].get("Cookie", ""))

    def test_player_prepares_the_track_through_the_real_extraction_pipeline(self):
        m.StreamWorker._warmup_shared_ydl()
        worker = self.worker()
        ready, failed = QSignalSpy(worker.stream_ready), QSignalSpy(worker.failed)
        worker.run()
        self.assertEqual(list(failed), [])
        self.assertEqual(len(ready), 1)
        self.assertEqual(ready[0][0], "https://example.invalid/audio.mp3")


if __name__ == "__main__":
    unittest.main()
