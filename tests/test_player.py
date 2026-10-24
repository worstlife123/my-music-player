import importlib.util
import gc
from contextlib import contextmanager
import json
import math
import os
from pathlib import Path
import struct
import tempfile
import threading
import time
import unittest
import weakref
from unittest.mock import patch
import wave

ROOT = Path(__file__).resolve().parents[1]
FILENAME = 'player_aurora_smart_beautiful_fixed_ui_repaint.py'
state = tempfile.TemporaryDirectory(prefix='aurora-validation-')
for key, directory in [('XDG_CONFIG_HOME', 'config'), ('XDG_DATA_HOME', 'data'),
                       ('XDG_CACHE_HOME', 'cache'), ('XDG_RUNTIME_DIR', 'runtime')]:
    os.environ[key] = str(Path(state.name) / directory)
    Path(os.environ[key]).mkdir(mode=0o700)
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
spec = importlib.util.spec_from_file_location('aurora', ROOT / FILENAME)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
from PyQt6.QtTest import QSignalSpy, QTest
from PyQt6.QtCore import QAbstractAnimation, QCoreApplication, QEvent, QEventLoop, QSettings
from PyQt6.QtGui import QEnterEvent, QImage
app = m.QApplication([])
m.configure_application(app)
app.setStyle('Fusion')
m.setup_font(app)
app.setQuitOnLastWindowClosed(False)


def wait_for(predicate, seconds=4):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        loop = QEventLoop()
        m.QTimer.singleShot(20, loop.quit)
        loop.exec()
    raise AssertionError('Timed out waiting for media state')


class PlayerChanges(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=state.name)
        self.addCleanup(self.directory.cleanup)
        self.test_path = Path(self.directory.name)
        settings = QSettings(str(self.test_path / 'preferences.ini'), QSettings.Format.IniFormat)
        for name in ('app_data_directory', 'app_cache_directory'):
            fixture = patch.object(m, name, return_value=self.test_path)
            fixture.start()
            self.addCleanup(fixture.stop)
        fixture = patch.object(m, 'QSettings', return_value=settings)
        fixture.start()
        self.addCleanup(fixture.stop)
        self.w = m.MusicPlayer()
        for player in self.w.players:
            player.setAudioOutput(None)
        self.w.show()
        app.processEvents()

    def tearDown(self):
        self.w.stop_all()
        self.w._force_exit = True
        self.w.close()
        app.processEvents()
        self.w.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()

    def local_track(self, name):
        path = self.test_path / (name + '.wav')
        if not path.exists():
            with wave.open(str(path), 'wb') as out:
                out.setparams((1, 2, 44100, 0, 'NONE', 'not compressed'))
                second = b''.join(struct.pack('<h', int(1000 * math.sin(2 * math.pi * 440 * i / 44100)))
                                  for i in range(44100))
                out.writeframes(second * 10)
        return {'source': 'local', 'url': str(path), 'title': name, 'artist': 'Test'}

    def start(self, track):
        self.w.play_track(track, -1)
        wait_for(lambda: self.w.requested_track is None and self.w.current_track is not None and self.w.current_track['url'] == track['url'])

    def test_empty_play_shows_inline_guidance_without_a_modal(self):
        w = self.w
        with patch.object(m.QMessageBox, 'information') as dialog:
            for source in ('youtube', 'likes'):
                w.set_source(source)
                w.play_button.click()
                self.assertTrue(w.toast.isVisible())
                self.assertIn('Выбери трек', w.toast.text())
                self.assertTrue(all(player.source().isEmpty() for player in w.players))
                self.assertIsNone(w.requested_track)
            dialog.assert_not_called()
        w.set_source('youtube')
        w.play_button.click()
        self.assertTrue(w.search_input.hasFocus())

    def test_play_starts_first_queued_track_without_a_previous_selection(self):
        w = self.w
        track = self.local_track('first-play')
        w.add_to_queue(track)
        self.assertEqual(w.current_queue_index, -1)
        with patch.object(w, 'prepare_next_track'), patch.object(w, 'ensure_following_track_prepared'):
            w.play_button.click()
            wait_for(lambda: w.current_track is not None and w.requested_track is None)
        self.assertEqual(w.current_queue_index, 0)
        self.assertEqual(w.current_track['url'], track['url'])
        self.assertEqual(w.player.playbackState(), m.QMediaPlayer.PlaybackState.PlayingState)

    def test_likes_are_updated_before_list_rebuild(self):
        w = self.w
        track = {'source': 'youtube', 'video_id': 'abcdefghijk',
                 'url': 'https://music.youtube.com/watch?v=abcdefghijk', 'title': 'Test'}
        item = m.QListWidgetItem()
        item.setData(m.Qt.ItemDataRole.UserRole, track)
        row = m.TrackRow(track)
        item.setSizeHint(row.sizeHint())
        w.source_list.addItem(item)
        w.source_list.setItemWidget(item, row)
        w.start_cards_scroll.hide()
        w.source_list.show()
        app.processEvents()
        self.assertTrue(w.source_list.isVisible())
        w.current_track = track
        button = row.favorite_button
        original = w.refresh_likes_list
        for liked in (True, False):
            w._youtube_rating_pending.add('abcdefghijk')
            w._refresh_youtube_like_buttons('abcdefghijk')
            self.assertFalse(button.isEnabled())
            def rebuild(*args, **kwargs):
                self.assertEqual(button.isChecked(), liked)
                self.assertTrue(button.isEnabled())
                return original(*args, **kwargs)
            with patch.object(w, 'refresh_likes_list', side_effect=rebuild) as refresh, \
                 patch.object(button, 'repaint', wraps=button.repaint) as repaint, \
                 patch.object(w.source_list.viewport(), 'update', wraps=w.source_list.viewport().update) as update:
                w.on_youtube_music_like_result(track, liked, True, 'OK')
                refresh.assert_called_once()
                repaint.assert_called()
                update.assert_called()
            self.assertEqual(w.is_youtube_music_liked(track), liked)
            self.assertEqual(w.bottom_favorite_button.isChecked(), liked)
        with patch.object(m.QMessageBox, 'warning'):
            w.on_youtube_music_like_result(track, True, False, 'Rejected')
        self.assertFalse(button.isChecked())
        self.assertFalse(w.is_youtube_music_liked(track))

    def test_position_gate_rejects_stale_events_and_does_not_wait_for_loaded(self):
        w = self.w
        slot = w.idle_slot()
        track = self.local_track('gate')
        expected = m.QUrl.fromLocalFile(track['url'])
        w.players[slot].setSource(expected)
        w.pending_slot = slot
        w.pending_position_seen = False
        w.pending_ever_loaded = False
        w.pending_media_url = m.QUrl.fromLocalFile('/tmp/another-track.wav')
        with patch.object(w, 'commit_switch') as commit:
            w.on_slot_position(slot, 10)
            commit.assert_not_called()
            w.pending_media_url = expected
            w.on_slot_position(slot, 0)
            commit.assert_not_called()
            w.on_slot_position(slot, 10)
            commit.assert_called_once()
            w.on_slot_position(slot, 20)
            commit.assert_called_once()

    def test_first_track_starts_at_target_volume_without_fade(self):
        self.start(self.local_track('first'))
        self.assertIsNone(self.w.fade_old_slot)
        self.assertFalse(self.w.fade_timer.isActive())
        self.assertAlmostEqual(self.w.audio_output.volume(), self.w.volume, places=5)
        self.assertGreater(self.w.player.position(), 0)

    def test_playing_track_crossfades_and_releases_old_slot(self):
        self.start(self.local_track('old-playing'))
        old = self.w.active_slot
        self.start(self.local_track('new-playing'))
        self.assertEqual(self.w.fade_old_slot, old)
        self.assertTrue(self.w.fade_timer.isActive())
        self.assertEqual(self.w.players[old].playbackState(), m.QMediaPlayer.PlaybackState.PlayingState)
        wait_for(lambda: not self.w.fade_timer.isActive())
        self.assertTrue(self.w.players[old].source().isEmpty())
        self.assertAlmostEqual(self.w.audio_output.volume(), self.w.volume, places=5)
        self.assertEqual(self.w.player.playbackState(), m.QMediaPlayer.PlaybackState.PlayingState)

    def test_stopped_track_is_released_without_fade(self):
        self.start(self.local_track('old-stopped'))
        old = self.w.active_slot
        self.w.stop_all()
        self.assertFalse(self.w.players[old].source().isEmpty())
        self.start(self.local_track('new-after-stop'))
        self.assertFalse(self.w.fade_timer.isActive())
        self.assertIsNone(self.w.fade_old_slot)
        self.assertTrue(self.w.players[old].source().isEmpty())
        self.assertAlmostEqual(self.w.audio_output.volume(), self.w.volume, places=5)

    def test_preloaded_source_is_reused(self):
        track = self.local_track('preloaded')
        self.w.preload_in_qt(track, m.QUrl.fromLocalFile(track['url']))
        slot = self.w.idle_slot()
        changes = QSignalSpy(self.w.players[slot].sourceChanged)
        self.start(track)
        self.assertEqual(len(changes), 0)
        self.assertGreater(self.w.player.position(), 0)

    def test_both_themes_render(self):
        for theme in ('dark', 'light'):
            self.w.theme = theme
            self.w.apply_styles()
            app.processEvents()
            pixmap = self.w.grab()
            self.assertFalse(pixmap.isNull())
            self.assertTrue(pixmap.save(str(self.test_path / (theme + '.png'))))

    @staticmethod
    def youtube_track(video_id):
        return {'source': 'youtube', 'video_id': video_id,
                'url': 'https://music.youtube.com/watch?v=' + video_id,
                'title': video_id}

    def request_like(self, track, liked):
        # Keep real UI/caches/signals; only the authenticated network worker is mocked.
        with patch.object(self.w, 'youtube_auth_kwargs', return_value={'cookie_file': 'unused'}), \
             patch.object(m, 'YouTubeRatingWorker') as worker:
            self.w.set_youtube_music_like(track, liked)
            return worker

    def begin_sync(self):
        with patch.object(self.w, 'youtube_auth_kwargs', return_value={'cookie_file': 'unused'}), \
             patch.object(m, 'SearchWorker') as worker:
            self.w.sync_youtube_likes()
            return worker.return_value

    def confirmed_ids(self):
        return {self.w.youtube_video_id(track) for track in self.w.youtube_liked_tracks}

    def saved_ids(self):
        import json
        payload = json.loads(self.w.youtube_likes_file.read_text(encoding='utf-8'))
        tracks = payload
        return {self.w.youtube_video_id(track) for track in tracks}

    def test_optimistic_like_updates_all_rows_and_rolls_back_on_failure(self):
        track = self.youtube_track('optimistic1')
        self.w.current_track = track
        for i in range(2):
            self.w.add_result_to_list(self.w.source_list, track, i + 1)
        buttons = [self.w.source_list.itemWidget(self.w.source_list.item(i)).favorite_button
                   for i in range(2)]
        worker = self.request_like(track, True)
        worker.assert_called_once()
        self.assertTrue(all(button.isChecked() and not button.isEnabled() for button in buttons))
        self.assertTrue(self.w.bottom_favorite_button.isChecked())
        self.assertNotIn('optimistic1', self.confirmed_ids())
        self.w.save_youtube_likes()
        self.assertNotIn('optimistic1', self.saved_ids())
        # A second click/request cannot replace the in-flight intent.
        self.request_like(track, False).assert_not_called()
        with patch.object(m.QMessageBox, 'warning'):
            self.w.on_youtube_music_like_result(track, True, False, 'Rejected')
        self.assertTrue(all(not button.isChecked() and button.isEnabled() for button in buttons))
        self.assertFalse(self.w.bottom_favorite_button.isChecked())
        self.assertFalse(self.w._youtube_rating_targets)

    def test_optimistic_unlike_rolls_back_and_success_persists(self):
        track = self.youtube_track('optimistic2')
        self.w.youtube_liked_tracks = [track]
        self.w.current_track = track
        self.request_like(track, False)
        self.assertFalse(self.w.bottom_favorite_button.isChecked())
        self.assertIn('optimistic2', self.confirmed_ids())
        with patch.object(m.QMessageBox, 'warning'):
            self.w.on_youtube_music_like_result(track, False, False, 'Rejected')
        self.assertTrue(self.w.bottom_favorite_button.isChecked())
        self.request_like(track, False)
        self.w.on_youtube_music_like_result(track, False, True, 'OK')
        self.assertNotIn('optimistic2', self.saved_ids())
        self.assertFalse(self.w._youtube_rating_pending)
        self.assertFalse(self.w._youtube_rating_targets)

    def visible_youtube_ids(self):
        widget = self.w.youtube_likes_list
        return [self.w.youtube_video_id(widget.item(i).data(m.Qt.ItemDataRole.UserRole))
                for i in range(widget.count())]

    def test_soundcloud_home_only_opens_complete_likes_library(self):
        tracks = [{'source': 'soundcloud', 'url': f'https://soundcloud.com/test/track-{i}',
                   'title': f'SoundCloud {i}'} for i in range(3)]
        self.w.soundcloud_liked_tracks = tracks
        self.w.custom_playlists = [{'title': 'Saved playlist', 'url': 'https://soundcloud.com/test/sets/saved'}]
        self.w.likes_search_input.setText('no matching song')
        self.w.current_source = 'soundcloud'
        self.w.rebuild_start_cards()
        self.assertEqual([card.title for card in self.w.start_cards], ['Мои лайки'])
        self.assertEqual(self.w.start_cards[0].action_icon, 'open')
        self.assertFalse(any(isinstance(self.w.start_cards_layout.itemAt(i).widget(), m.QLabel)
                             for i in range(self.w.start_cards_layout.count())))
        self.assertEqual(self.w.home_tiles_layout.count(), 1)
        with patch.object(self.w, 'start_search') as search, \
             patch.object(self.w, 'start_playlist_url') as playlist, \
             patch.object(self.w, 'play_queue_index') as play:
            self.w.start_cards[0].click()
            self.assertEqual(self.w.current_source, 'likes')
            self.assertIs(self.w.view_stack.currentWidget(), self.w.likes_page)
            self.assertEqual(self.w.likes_tabs.currentIndex(), 1)
            self.assertEqual(self.w.likes_search_input.text(), '')
            self.assertEqual(self.w.soundcloud_likes_list.count(), 3)
            search.assert_not_called()
            playlist.assert_not_called()
            play.assert_not_called()
        self.assertEqual(self.w.custom_playlists[0]['title'], 'Saved playlist')

    def test_youtube_home_has_one_supermix_and_likes_actions(self):
        self.w.current_source = 'youtube'
        self.w.rebuild_start_cards()
        self.assertEqual([card.title for card in self.w.start_cards],
                         ['Мои лайки', 'Супермикс', 'Перемешать лайки'])
        self.w.likes_tabs.setCurrentIndex(1)
        self.w.likes_search_input.setText('old filter')
        with patch.object(self.w, 'start_search') as search, \
             patch.object(self.w, 'play_queue_index') as play:
            self.w.start_cards[0].click()
            self.assertEqual(self.w.current_source, 'likes')
            self.assertEqual(self.w.likes_tabs.currentIndex(), 0)
            self.assertEqual(self.w.likes_search_input.text(), '')
            search.assert_not_called()
            play.assert_not_called()

    def test_shuffle_card_uses_only_likes_and_next_stays_in_queue(self):
        liked = [self.youtube_track(f'liked{i:06}') for i in range(60)]
        self.w.youtube_liked_tracks = liked
        self.w.disliked_track_keys.add(self.w.radio_track_key(liked[-1]))
        self.w._finish_transition_pending = True
        self.w._finish_guard_url = 'stale transition'
        self.w.current_source = 'youtube'
        self.w.rebuild_start_cards()
        with patch.object(m.random, 'shuffle', side_effect=lambda tracks: tracks.reverse()), \
             patch.object(self.w, 'play_track') as play, \
             patch.object(self.w, 'start_search') as search:
            self.w.start_cards[2].click()
            self.assertEqual(len(self.w.queue_tracks), 50)
            self.assertEqual(self.w.queue_tracks[0]['url'], liked[-2]['url'])
            allowed = {track['url'] for track in liked[:-1]}
            self.assertTrue(all(track['url'] in allowed for track in self.w.queue_tracks))
            self.assertEqual(self.w.queue_mode, 'youtube_likes')
            self.assertFalse(self.w._finish_transition_pending)
            play.assert_called_once_with(self.w.queue_tracks[0], 0)
            self.w.current_track = self.w.queue_tracks[0]
            self.w.current_queue_index = 0
            self.w.source_results['youtube'] = [self.w.current_track, self.youtube_track('foreign00001')]
            play.reset_mock()
            self.w.play_next()
            play.assert_called_once_with(self.w.queue_tracks[1], 1)
            search.assert_not_called()
            self.w.current_track = self.w.queue_tracks[-1]
            self.w.current_queue_index = 49
            play.reset_mock()
            with patch.object(self.w, 'maybe_refill_radio') as radio:
                self.w.handle_track_finished()
                self.w.ensure_following_track_prepared()
                radio.assert_not_called()
            play.assert_not_called()

    def test_recent_history_records_only_started_tracks_and_survives_reload(self):
        queued = self.youtube_track('queued00001')
        with patch.object(self.w, 'play_queue_index'):
            self.w.add_to_queue(queued)
        self.assertEqual(self.w.recent_tracks, [])
        self.w.clear_queue()
        self.start(self.local_track('actually-started'))
        self.assertEqual(self.w.recent_tracks[0]['title'], 'actually-started')
        self.assertEqual(self.w.load_recent_tracks(), self.w.recent_tracks)

    def test_recent_history_is_bounded_deduplicated_and_contains_only_metadata(self):
        with patch.object(self.w, 'refresh_recent_tracks'):
            for i in range(45):
                self.w.record_recent_track(dict(self.youtube_track(f'history{i:04}'),
                                               cookie='secret', stream_url='ephemeral', queue_id='old'))
            repeated = dict(self.w.recent_tracks[-1], title='Updated title')
            self.w.record_recent_track(repeated)
        self.assertEqual(len(self.w.recent_tracks), 40)
        self.assertEqual(self.w.recent_tracks[0]['title'], 'Updated title')
        self.assertEqual(len({self.w.favorite_key(t) for t in self.w.recent_tracks}), 40)
        self.assertEqual(self.w.load_recent_tracks(), self.w.recent_tracks)
        saved = str(self.w.settings.value('recent_tracks_json'))
        self.assertNotIn('secret', saved)
        self.assertNotIn('ephemeral', saved)
        self.assertNotIn('queue_id', saved)
        self.w.settings.setValue('recent_tracks_json', '{invalid')
        self.assertEqual(self.w.load_recent_tracks(), [])

    def test_recent_history_expands_beyond_twelve_and_keeps_service_and_playback_state(self):
        w = self.w
        youtube = [self.youtube_track(f'recent{i:05}') for i in range(18)]
        soundcloud = [dict(track, source='soundcloud', url=f'https://soundcloud.com/test/recent-{i}')
                      for i, track in enumerate(youtube[:3])]
        w.recent_tracks = youtube + soundcloud
        w.disliked_track_keys.add(w.radio_track_key(youtube[2]))
        w.current_track = youtube[-1]
        w.rebuild_start_cards()
        self.assertEqual(len(w.recent_rows), 12)
        self.assertFalse(w.recent_more_button.isHidden())
        w.recent_more_button.click()
        self.assertEqual([row.track['url'] for row in w.recent_rows],
                         [t['url'] for i, t in enumerate(youtube) if i != 2])
        self.assertEqual(w.recent_more_button.text(), 'Свернуть')
        self.assertTrue(w.recent_rows[-1].property('playing'))
        with patch.object(w, 'add_to_queue') as play:
            w.recent_rows[-1].play_requested.emit(w.recent_rows[-1].track)
            play.assert_called_once_with(youtube[-1], True)
        w.set_source('soundcloud')
        self.assertEqual(len(w.recent_rows), 3)
        self.assertTrue(w.recent_more_button.isHidden())
        w.set_source('youtube')
        self.assertEqual(len(w.recent_rows), 17)
        w.recent_more_button.click()
        self.assertEqual(len(w.recent_rows), 12)

    def test_recent_preview_uses_twelve_likes_without_fabricating_history(self):
        w = self.w
        w.youtube_liked_tracks = [self.youtube_track(f'recent{i:05}') for i in range(20)]
        w.rebuild_start_cards()
        self.assertEqual(w.recent_heading.text(), 'Из твоих лайков')
        self.assertEqual(len(w.recent_rows), 12)
        self.assertTrue(w.recent_more_button.isHidden())
        self.assertEqual(w.recent_tracks, [])

    def test_application_icon_is_valid_at_shell_sizes_and_keeps_existing_data_location(self):
        original_name = app.applicationName()
        original_location = m.QStandardPaths.writableLocation(m.QStandardPaths.StandardLocation.AppDataLocation)
        m.configure_application(app)
        self.assertEqual(app.applicationName(), original_name)
        self.assertEqual(m.QStandardPaths.writableLocation(m.QStandardPaths.StandardLocation.AppDataLocation), original_location)
        for side in (16, 32, 48, 256):
            self.assertFalse(app.windowIcon().pixmap(side, side).isNull())
        self.assertEqual(self.w.windowIcon().cacheKey(), app.windowIcon().cacheKey())
        dialog = m.SettingsDialog(self.w)
        self.assertEqual(dialog.windowIcon().cacheKey(), app.windowIcon().cacheKey())
        data = (ROOT / 'assets' / 'aurora.ico').read_bytes()
        self.assertEqual(struct.unpack_from('<HHH', data), (0, 1, 7))
        sizes = []
        for index in range(7):
            width, height, _, _, _, bits, length, offset = struct.unpack_from('<BBBBHHII', data, 6 + 16 * index)
            width, height = width or 256, height or 256
            image = QImage.fromData(data[offset:offset + length])
            self.assertEqual(image.size(), m.QSize(width, height))
            self.assertEqual(bits, 32)
            sizes.append(width)
        self.assertEqual(sizes, [16, 24, 32, 48, 64, 128, 256])

    def test_windows_title_bar_colors_use_colorref_and_pointer_sized_handles(self):
        from types import SimpleNamespace
        calls = []
        def attribute(hwnd, number, pointer, size):
            calls.append((hwnd.value, number, pointer._obj.value, size))
            return 0
        from unittest.mock import Mock
        api = SimpleNamespace(DwmSetWindowAttribute=Mock(side_effect=attribute))
        with patch.object(m.sys, 'platform', 'win32'), \
             patch.object(self.w, 'effectiveWinId', return_value=0x123456789):
            self.assertTrue(m.apply_native_title_bar(self.w, 'dark', dwm_api=api))
            values = {number: value for _, number, value, _ in calls}
            self.assertEqual(values[20], 1)
            self.assertEqual(values[35], 0x100D0B)
            self.assertEqual(values[36], 0xF5EEE9)
            self.assertTrue(all(hwnd == 0x123456789 and size == 4 for hwnd, _, _, size in calls))
            calls.clear()
            self.assertTrue(m.apply_native_title_bar(self.w, 'light', dwm_api=api))
            values = {number: value for _, number, value, _ in calls}
            self.assertEqual(values[20], 0)
            self.assertEqual(values[35], 0xF2EDE9)

    def test_windows_caption_redraws_immediately_after_theme_change(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        dwm = SimpleNamespace(DwmSetWindowAttribute=Mock(return_value=0))
        redraw = Mock(return_value=1)
        dll = SimpleNamespace(user32=SimpleNamespace(RedrawWindow=redraw))
        with patch.object(m.sys, 'platform', 'win32'), \
             patch.object(self.w, 'effectiveWinId', return_value=123), \
             patch.object(m.ctypes, 'WinDLL', return_value=dwm, create=True), \
             patch.object(m.ctypes, 'windll', dll, create=True):
            self.assertTrue(m.apply_native_title_bar(self.w, 'dark'))
            self.assertEqual(redraw.call_args.args[0].value, 123)
            self.assertEqual(redraw.call_args.args[3], 0x0501)
            redraw.side_effect = OSError('redraw unavailable')
            self.assertTrue(m.apply_native_title_bar(self.w, 'light'))

    def test_windows_title_bar_falls_back_for_older_windows_and_ignores_unsupported_api(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        api = SimpleNamespace(DwmSetWindowAttribute=Mock(side_effect=lambda _h, n, _p, _s: 0 if n == 19 else -1))
        with patch.object(m.sys, 'platform', 'win32'), patch.object(self.w, 'effectiveWinId', return_value=123):
            self.assertTrue(m.apply_native_title_bar(self.w, 'dark', dwm_api=api))
            self.assertEqual([call.args[1] for call in api.DwmSetWindowAttribute.call_args_list][:2], [20, 19])
            api.DwmSetWindowAttribute.side_effect = OSError('unsupported')
            self.assertFalse(m.apply_native_title_bar(self.w, 'dark', dwm_api=api))

    def test_native_chrome_follows_owner_theme_and_keeps_mini_player_frameless(self):
        watcher = m.NativeTitleBarFilter(app)
        dialog = m.SettingsDialog(self.w)
        mini = m.MiniPlayer(self.w)
        with patch.object(m, 'apply_native_title_bar') as apply:
            watcher.eventFilter(dialog, QEvent(QEvent.Type.Show))
            apply.assert_called_once_with(dialog, 'dark')
            self.w.theme = 'light'
            watcher.eventFilter(dialog, QEvent(QEvent.Type.WinIdChange))
            apply.assert_called_with(dialog, 'light')
            apply.reset_mock()
            watcher.eventFilter(mini, QEvent(QEvent.Type.Show))
            apply.assert_not_called()
        self.assertTrue(mini.windowFlags() & m.Qt.WindowType.FramelessWindowHint)

    def test_windows_taskbar_identity_is_stable_and_optional_on_other_platforms(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        identity = Mock(return_value=0)
        dll = SimpleNamespace(shell32=SimpleNamespace(SetCurrentProcessExplicitAppUserModelID=identity))
        with patch.object(m.sys, 'platform', 'win32'), patch.object(m.ctypes, 'windll', dll, create=True):
            self.assertTrue(m.set_windows_app_id())
            identity.assert_called_once_with('AuroraLocal.MusicPlayer')
            identity.side_effect = OSError('unsupported')
            self.assertFalse(m.set_windows_app_id())
        with patch.object(m.sys, 'platform', 'linux'):
            self.assertFalse(m.set_windows_app_id())

    def test_bundled_font_supports_cyrillic(self):
        self.assertIn('Inter', app.font().family())
        metrics = m.QFontMetrics(app.font())
        self.assertTrue(all(metrics.inFontUcs4(ord(ch)) for ch in 'МузыкаЯё'))

    def test_search_keyboard_and_submit_work_inside_new_search_box(self):
        w = self.w
        w.search_input.setText('MF DOOM')
        w.search_debounce_timer.stop()
        w.sidebar_settings_button.setFocus()
        app.processEvents()
        QTest.keyClick(w.sidebar_settings_button, m.Qt.Key.Key_F, m.Qt.KeyboardModifier.ControlModifier)
        self.assertTrue(w.search_input.hasFocus())
        self.assertEqual(w.search_input.selectedText(), 'MF DOOM')
        self.assertTrue(w.search_shell.property('focused'))
        with patch.object(m, 'SearchWorker') as worker:
            QTest.keyClick(w.search_input, m.Qt.Key.Key_Return)
            self.assertEqual(worker.call_count, 1)
            self.assertEqual(worker.call_args.args[:2], ('MF DOOM', 'youtube'))
            worker.return_value.start.assert_called_once()
            w.search_button.setEnabled(True)
            w.search_button.click()
            self.assertEqual(worker.call_count, 2)
        w.search_worker = None
        w.sidebar_settings_button.setFocus()
        app.processEvents()
        self.assertFalse(w.search_shell.property('focused'))
        w.nav_buttons[1].click()
        self.assertEqual(w.current_source, 'soundcloud')
        self.assertEqual(w.sidebar.width(), 216)
        self.assertEqual(w.sidebar_settings_button.text(), 'Настройки')
        w.settings.setValue('sidebar_collapsed', True)
        with self.reopened_player() as restored:
            self.assertEqual(restored.sidebar.width(), 216)
            self.assertEqual(restored.sidebar_settings_button.text(), 'Настройки')

    def test_home_recent_tracks_are_scoped_to_service_and_play_the_selected_track(self):
        youtube = self.youtube_track('history0001')
        soundcloud = dict(youtube, source='soundcloud', url='https://soundcloud.com/test/recent')
        self.w.recent_tracks = [youtube, soundcloud]
        self.w.current_source = 'soundcloud'
        self.w.rebuild_start_cards()
        self.assertEqual(self.w.recent_heading.text(), 'Недавно слушал')
        self.assertEqual([row.track['source'] for row in self.w.recent_rows], ['soundcloud'])
        with patch.object(self.w, 'add_to_queue') as play:
            self.w.recent_rows[0].play_requested.emit(dict(soundcloud))
            play.assert_called_once_with(soundcloud, True)
        self.w.current_source = 'youtube'
        self.w.rebuild_start_cards()
        self.assertEqual([row.track['url'] for row in self.w.recent_rows], [youtube['url']])

    def test_home_without_history_uses_real_likes_and_excludes_dislikes(self):
        liked = [self.youtube_track('liked000001'), self.youtube_track('liked000002')]
        self.w.youtube_liked_tracks = liked
        self.w.disliked_track_keys.add(self.w.radio_track_key(liked[1]))
        self.w.rebuild_start_cards()
        self.assertEqual(self.w.recent_heading.text(), 'Из твоих лайков')
        self.assertEqual([row.track['video_id'] for row in self.w.recent_rows], ['liked000001'])
        self.assertFalse(self.w.recent_rows[0].remove_button.isVisible())

    def test_home_tiles_reflow_at_narrow_width_without_horizontal_scroll(self):
        self.w.resize(1380, 860)
        app.processEvents()
        self.w.rebuild_start_cards()
        app.processEvents()
        self.w.layout_home_tiles()
        cards = self.w.start_cards
        self.assertEqual(cards[0].y(), cards[2].y())
        self.assertGreater(cards[2].x(), cards[1].x())
        self.w.resize(1000, 650)
        if not self.w.queue_open:
            self.w.toggle_queue()
        wait_for(lambda: self.w.queue_animation.state() != m.QPropertyAnimation.State.Running)
        app.processEvents()
        self.w.layout_home_tiles()
        self.assertGreater(cards[2].y(), cards[0].y())
        self.assertLessEqual(cards[1].geometry().right(), self.w.start_cards_scroll.viewport().width())
        # The viewport's scroll ranges settle after its queued resize/reflow.
        wait_for(lambda: self.w.start_cards_scroll.horizontalScrollBar().maximum() == 0)
        self.w.resize(1380, 860)
        app.processEvents()
        self.w.layout_home_tiles()
        wait_for(lambda: cards[0].y() == cards[2].y())

    def test_likes_connections_live_in_settings_popover(self):
        self.w.set_source('likes')
        self.assertTrue(self.w.sync_account_button.isVisible())
        self.assertFalse(self.w.connect_account_button.isVisible())
        self.w.likes_settings_menu.popup(self.w.likes_settings_button.mapToGlobal(m.QPoint(0, 38)))
        app.processEvents()
        self.assertTrue(self.w.connect_account_button.isVisible())
        self.assertTrue(self.w.connect_soundcloud_button.isVisible())
        self.w.likes_settings_menu.hide()
        self.assertFalse(self.w.connect_account_button.isVisible())

    def test_queue_highlight_uses_position_identity_and_remove_is_available_on_hover(self):
        track = self.youtube_track('same0000001')
        with patch.object(self.w, 'prepare_next_track'):
            self.w.add_to_queue(track)
            self.w.add_to_queue(track)
        self.w.current_track = self.w.queue_tracks[1]
        self.w.current_queue_index = 1
        self.w.update_playing_row_highlight()
        first = self.w.queue_list.itemWidget(self.w.queue_list.item(0))
        second = self.w.queue_list.itemWidget(self.w.queue_list.item(1))
        self.assertFalse(first.property('playing'))
        self.assertTrue(second.property('playing'))
        self.assertFalse(second.now_playing.isHidden())
        second._reveal_queue_action(True)
        self.assertTrue(second.remove_button.property('revealed'))
        second._reveal_queue_action(False)
        self.assertFalse(second.remove_button.property('revealed'))
        with patch.object(self.w, 'prepare_next_track'):
            second.remove_button.click()
        self.assertEqual(len(self.w.queue_tracks), 1)

    def test_player_menu_keeps_stop_and_dislike_actions_working(self):
        self.start(self.local_track('menu-actions'))
        hidden_track = dict(self.w.current_track)
        self.w.dislike_action.trigger()
        self.assertTrue(self.w.is_disliked(hidden_track))
        self.assertIsNone(self.w.current_track)
        self.assertFalse(self.w.dislike_action.isEnabled())
        self.start(self.local_track('menu-stop'))
        self.w.stop_action.trigger()
        self.assertEqual(self.w.player.playbackState(), m.QMediaPlayer.PlaybackState.StoppedState)

    def test_supermix_card_tracks_real_playback_pause_resume_stop_and_rebuild(self):
        session = {'mix_id': 'RDTMAK5uy_fixture', 'seen': set(), 'anchor': '',
                   'waiting': False, 'failures': 0}
        with patch.object(self.w, 'maybe_refill_supermix'), \
             patch.object(self.w, 'prepare_next_track'), patch.object(m, 'SupermixWorker') as factory:
            self.w._start_music_queue([self.local_track('mix-card')], 'youtube', 'Ready',
                                      recommendations=True, supermix_session=session)
            wait_for(lambda: self.w.current_track is not None and self.w.requested_track is None)
            card = self.w.start_cards[1]
            self.assertEqual(card.playback_state, 'playing')
            self.assertTrue(card._equalizer_timer.isActive())
            beats = QSignalSpy(card._equalizer_timer.timeout)
            wait_for(lambda: len(beats) > 0)
            card.click()
            self.assertEqual(self.w.player.playbackState(), m.QMediaPlayer.PlaybackState.PausedState)
            self.assertEqual(card.playback_state, 'paused')
            self.assertFalse(card._equalizer_timer.isActive())
            self.assertIn('паузе', card.accessibleName())
            self.w.rebuild_start_cards()
            app.processEvents()
            card = self.w.start_cards[1]
            self.assertEqual(card.playback_state, 'paused')
            card.click()
            self.assertEqual(card.playback_state, 'playing')
            self.assertIs(self.w.supermix_session, session)
            factory.assert_not_called()
            self.w.toggle_playback()  # Bottom transport uses the same state updates.
            self.assertEqual(card.playback_state, 'paused')
            self.w.toggle_playback()
            self.assertEqual(card.playback_state, 'playing')
            self.w.stop_all()
            self.assertEqual(card.playback_state, 'idle')
            self.assertFalse(card._equalizer_timer.isActive())

    def test_supermix_card_animation_sleeps_when_hidden_and_manual_music_clears_indicator(self):
        session = {'mix_id': 'RDTMAK5uy_fixture', 'seen': set(), 'anchor': '',
                   'waiting': False, 'failures': 0}
        with patch.object(self.w, 'maybe_refill_supermix'), patch.object(self.w, 'prepare_next_track'):
            self.w._start_music_queue([self.local_track('mix-visibility')], 'youtube', 'Ready',
                                      recommendations=True, supermix_session=session)
            wait_for(lambda: self.w.current_track is not None and self.w.requested_track is None)
            card = self.w.start_cards[1]
            card.hide()
            self.assertFalse(card._equalizer_timer.isActive())
            self.assertEqual(card.playback_state, 'playing')
            card.show()
            self.assertTrue(card._equalizer_timer.isActive())
            self.start(self.local_track('manual-after-mix'))
            self.assertIsNone(self.w.supermix_session)
            self.assertEqual(card.playback_state, 'idle')
            self.assertFalse(card._equalizer_timer.isActive())

    def test_supermix_card_does_not_label_previous_audio_as_the_new_mix(self):
        self.start(self.local_track('previous-audio'))
        session = {'mix_id': 'RDTMAK5uy_fixture', 'seen': set(), 'anchor': '',
                   'waiting': False, 'failures': 0}
        with patch.object(self.w, 'play_track'), patch.object(self.w, 'prepare_next_track'):
            self.w._start_music_queue([self.youtube_track('newmix00001')], 'youtube', 'Ready',
                                      recommendations=True, supermix_session=session)
            self.w.refresh_supermix_card()
            self.assertNotEqual(self.w.start_cards[1].playback_state, 'playing')
            self.w.requested_track = dict(self.w.queue_tracks[0])
            self.w.requested_index = 0
            self.w.refresh_supermix_card()
            self.assertEqual(self.w.start_cards[1].playback_state, 'loading')
            with patch.object(self.w, 'toggle_playback') as previous_audio:
                self.w.start_cards[1].click()
                previous_audio.assert_not_called()
            self.w.cancel_pending_request()
            session['waiting'] = True
            with patch.object(self.w, 'maybe_refill_supermix') as refill, patch.object(self.w, 'play_supermix') as restart:
                self.w.start_cards[1].click()
                refill.assert_called_once()
                restart.assert_not_called()

    def test_likes_sync_button_dispatches_to_selected_service_and_hides_for_local(self):
        self.w.youtube_auth_mode = 'browser'
        self.w.soundcloud_profile_url = 'https://soundcloud.com/fixture'
        self.w.refresh_connection_badge()
        with patch.object(self.w, 'sync_youtube_likes') as youtube, \
             patch.object(self.w, 'load_soundcloud_account_content') as soundcloud:
            self.w.sync_account_button.click()
            youtube.assert_called_once()
            soundcloud.assert_not_called()
            self.w.likes_tabs.setCurrentIndex(1)
            self.assertIn('SoundCloud', self.w.sync_account_button.text())
            self.assertIn('SoundCloud', self.w.sync_account_button.toolTip())
            self.assertIn('SoundCloud', self.w.connection_badge.toolTip())
            self.assertNotIn('YouTube', self.w.sync_account_button.text())
            self.w.sync_account_button.click()
            soundcloud.assert_called_once_with(force=True)
            youtube.assert_called_once()
            self.w.likes_tabs.setCurrentIndex(2)
            self.assertTrue(self.w.sync_account_button.isHidden())
            self.assertIn('устройстве', self.w.connection_badge.text())
            self.w.sync_selected_likes()
            soundcloud.assert_called_once()
            youtube.assert_called_once()

    def test_likes_sync_enabled_state_is_independent_for_each_service(self):
        self.w.youtube_auth_mode = 'browser'
        self.w.soundcloud_profile_url = 'https://soundcloud.com/fixture'
        self.w.youtube_sync_worker = object()
        self.w.refresh_connection_badge()
        self.assertFalse(self.w.sync_account_button.isEnabled())
        self.w.likes_tabs.setCurrentIndex(1)
        self.assertTrue(self.w.sync_account_button.isEnabled())
        self.w._soundcloud_likes_loading = True
        self.w.soundcloud_profile_workers['likes'] = object()
        self.w.refresh_connection_badge()
        self.assertFalse(self.w.sync_account_button.isEnabled())
        self.w.youtube_sync_worker = None
        self.w.likes_tabs.setCurrentIndex(0)
        self.assertTrue(self.w.sync_account_button.isEnabled())
        self.w.soundcloud_profile_workers.clear()
        self.w._soundcloud_likes_loading = False

    def test_likes_sync_badge_does_not_use_other_services_connection(self):
        self.w.youtube_auth_mode = 'browser'
        self.w.refresh_connection_badge()
        self.assertTrue(self.w.connection_badge.property('connected'))
        self.w.likes_tabs.setCurrentIndex(1)
        self.assertFalse(self.w.connection_badge.property('connected'))
        self.assertFalse(self.w.sync_account_button.isEnabled())
        self.assertIn('SoundCloud', self.w.connection_badge.toolTip())

    def test_background_youtube_finish_does_not_relabel_or_enable_busy_soundcloud(self):
        self.w.youtube_auth_mode = 'browser'
        self.w.soundcloud_profile_url = 'https://soundcloud.com/fixture'
        youtube_worker = object()
        soundcloud_worker = type('Worker', (), {'pagination_done': True})()
        self.w.youtube_sync_worker = youtube_worker
        self.w.soundcloud_profile_workers['likes'] = soundcloud_worker
        self.w._soundcloud_likes_loading = True
        self.w.likes_tabs.setCurrentIndex(1)
        self.w.on_youtube_likes_finished(youtube_worker)
        self.assertIn('SoundCloud', self.w.sync_account_button.text())
        self.assertFalse(self.w.sync_account_button.isEnabled())
        self.w.on_soundcloud_account_finished('likes', soundcloud_worker)
        self.assertTrue(self.w.sync_account_button.isEnabled())
        self.assertIn('SoundCloud', self.w.sync_account_button.text())

    def test_old_soundcloud_finish_cannot_clear_new_sync_state(self):
        self.w.soundcloud_profile_url = 'https://soundcloud.com/fixture'
        self.w.likes_tabs.setCurrentIndex(1)
        current = object()
        self.w.soundcloud_profile_workers['likes'] = current
        self.w._soundcloud_likes_loading = True
        self.w.refresh_connection_badge()
        self.w.on_soundcloud_account_finished('likes', object())
        self.assertIs(self.w.soundcloud_profile_workers['likes'], current)
        self.assertTrue(self.w._soundcloud_likes_loading)
        self.assertFalse(self.w.sync_account_button.isEnabled())
        self.w.soundcloud_profile_workers.clear()
        self.w._soundcloud_likes_loading = False

    def test_soundcloud_sync_uses_existing_worker_and_lifecycle_updates_selected_button(self):
        self.w.soundcloud_profile_url = 'https://soundcloud.com/fixture'
        self.w.likes_tabs.setCurrentIndex(1)
        with patch.object(m, 'SearchWorker') as factory:
            self.w.sync_account_button.click()
            worker = factory.return_value
            worker.start.assert_called_once()
            self.assertEqual(factory.call_args.args[1], 'soundcloud')
            self.assertEqual(factory.call_args.kwargs['direct_url'], 'https://soundcloud.com/fixture/likes')
            self.assertTrue(factory.call_args.kwargs['paginate_all'])
            self.assertFalse(self.w.sync_account_button.isEnabled())
            self.w.sync_selected_likes()
            factory.assert_called_once()
            self.w.on_soundcloud_account_error('likes', worker, 'Temporary failure')
            self.assertFalse(self.w.sync_account_button.isEnabled())
            self.w.on_soundcloud_account_finished('likes', worker)
            self.assertTrue(self.w.sync_account_button.isEnabled())

    def test_supermix_fetches_in_background_and_keeps_recommendations_unliked(self):
        self.w.youtube_auth_mode = "browser"
        liked = dict(self.youtube_track('likedseed001'), artist='Artist')
        recommended = self.youtube_track('freshsong001')
        self.w.youtube_liked_tracks = [liked]
        self.w.queue_tracks = [liked]
        self.w.rebuild_start_cards()
        with patch.object(m, 'SupermixWorker') as factory, \
             patch.object(self.w, 'play_track') as play:
            worker = factory.return_value
            self.w.start_cards[1].click()
            factory.assert_called_once()
            self.assertEqual(factory.call_args.args[0], 'browser')
            self.assertEqual(factory.call_args.kwargs['browser_spec'], 'chrome')
            worker.start.assert_called_once()
            self.assertEqual(self.w.queue_tracks, [liked])
            self.assertFalse(self.w.start_cards[1].isEnabled())
            play.assert_not_called()
            self.w.on_supermix_ready(worker, [recommended], {'mix_id': 'RDTMAK5uy_personal'})
            self.assertEqual(self.w.queue_mode, 'supermix')
            self.assertEqual(self.w.queue_tracks[0]['video_id'], 'freshsong001')
            self.assertFalse(self.w.queue_tracks[0].get('youtube_music_like'))
            self.assertFalse(self.w.is_youtube_music_liked(recommended))
            self.assertEqual(self.w.youtube_liked_tracks, [liked])
            play.assert_called_once_with(self.w.queue_tracks[0], 0)
            self.assertTrue(self.w.start_cards[1].isEnabled())

    def test_supermix_cover_loads_cached_artwork_into_card(self):
        cover_url = 'https://i.ytimg.com/supermix-fixture.jpg'
        cover = m.QPixmap(64, 64)
        cover.fill(m.QColor('#237ABC'))
        self.w.pixmap_cache[cover_url] = cover
        self.w.supermix_cover_url = cover_url
        self.w._update_supermix_cover()
        card = self.w.start_cards[1]
        self.assertEqual(card.property('requested_image'), cover_url)
        self.assertIsNotNone(card._cover_pixmap)
        self.assertEqual(card._cover_pixmap.toImage().pixelColor(32, 32), m.QColor('#237ABC'))

    def test_supermix_cover_queues_uncached_image_and_keeps_generated_artwork(self):
        cover_url = 'https://i.ytimg.com/new-supermix-fixture.jpg'
        self.w.supermix_cover_url = cover_url
        card = self.w.start_cards[1]
        original_artwork = card._artwork.cacheKey()
        with patch.object(self.w, 'pump_images') as pump:
            self.w._update_supermix_cover()
            pump.assert_called_once()
        self.assertEqual(card.property('requested_image'), cover_url)
        self.assertEqual([reference() for reference in self.w.image_waiters[cover_url]], [card])
        self.assertIn(cover_url, self.w.image_backlog)
        self.assertIsNone(card._cover_pixmap)
        self.assertEqual(card._artwork.cacheKey(), original_artwork)

    def test_supermix_background_thread_delivers_recommendations_to_player(self):
        self.w.youtube_auth_mode = "browser"
        seed = dict(self.youtube_track('likedseed001'), artist='Artist')
        self.w.youtube_liked_tracks = [seed]
        cover_url = 'https://i.ytimg.com/supermix-fixture.jpg'
        cover = m.QPixmap(64, 64)
        cover.fill(m.QColor('#237ABC'))
        self.w.pixmap_cache[cover_url] = cover
        with patch('ytmusicapi.YTMusic') as client, patch.object(self.w, 'play_track') as play, \
             patch.object(m.SupermixWorker, '_auth_headers', return_value={}):
            client.return_value.get_home.return_value = [{'contents': [{
                'playlistId': 'RDTMAK5uy_personal', 'title': 'My Supermix',
                'thumbnails': [{'url': cover_url}]}]}]
            client.return_value.get_watch_playlist.return_value = {
                'tracks': [{'videoId': 'freshsong001', 'title': 'Fresh recommendation',
                            'artists': [{'name': 'Artist'}]}]
            }
            self.w.play_supermix()
            finished = QSignalSpy(self.w.supermix_worker.finished)
            wait_for(lambda: len(finished) == 1 and play.call_count == 1)
            self.assertEqual(self.w.queue_mode, 'supermix')
            self.assertEqual([track['video_id'] for track in self.w.queue_tracks], ['freshsong001'])
            self.assertIsNone(self.w.supermix_worker)
            self.assertEqual(self.w.youtube_liked_tracks, [seed])
            self.assertEqual(self.w.start_cards[1]._cover_pixmap.toImage().pixelColor(32, 32),
                             m.QColor('#237ABC'))

    def test_stale_supermix_result_cannot_override_manual_playback(self):
        self.w.youtube_auth_mode = "browser"
        seed = self.youtube_track('likedseed001')
        self.w.youtube_liked_tracks = [seed]
        with patch.object(m, 'SupermixWorker') as factory:
            self.w.play_supermix()
            worker = factory.return_value
            self.w.stop_all()
            worker.cancel.assert_called()
            with patch.object(self.w, 'play_track') as play:
                self.w.on_supermix_ready(worker, [self.youtube_track('freshsong001')], {'mix_id': 'RDTMAK5uy_personal'})
                play.assert_not_called()
                self.assertEqual(self.w.queue_tracks, [])

    def test_supermix_rechecks_new_likes_and_dislikes_when_results_arrive(self):
        self.w.youtube_auth_mode = "browser"
        seed = self.youtube_track('likedseed001')
        fresh = self.youtube_track('freshsong001')
        now_liked = self.youtube_track('nowliked0001')
        now_disliked = self.youtube_track('nowhidden001')
        self.w.youtube_liked_tracks = [seed]
        with patch.object(m, 'SupermixWorker') as factory, patch.object(self.w, 'play_track'):
            self.w.play_supermix()
            self.w.youtube_liked_tracks.append(now_liked)
            self.w.disliked_track_keys.add('youtube|https://youtu.be/nowhidden001')
            self.w.on_supermix_ready(factory.return_value, [now_liked, now_disliked, fresh, fresh], {'mix_id': 'RDTMAK5uy_personal'})
        self.assertEqual([track['video_id'] for track in self.w.queue_tracks], ['nowliked0001', 'freshsong001'])

    def test_supermix_error_preserves_queue_and_does_not_shuffle_likes(self):
        self.w.youtube_auth_mode = "browser"
        seed = self.youtube_track('likedseed001')
        self.w.youtube_liked_tracks = [seed]
        self.w.queue_tracks = [seed]
        with patch.object(m, 'SupermixWorker') as factory, \
             patch.object(self.w, 'show_toast') as toast, \
             patch.object(self.w, 'play_track') as play:
            self.w.play_supermix()
            self.w.on_supermix_error(factory.return_value, 'Service unavailable')
            self.w.on_supermix_finished(factory.return_value)
            toast.assert_called_once()
            self.assertEqual(self.w.queue_tracks, [seed])
            self.assertIsNone(self.w.supermix_worker)
            play.assert_not_called()

    def test_recommendation_queue_does_not_switch_to_generic_search(self):
        tracks = [self.youtube_track('freshsong001'), self.youtube_track('freshsong002')]
        with patch.object(self.w, 'play_track') as play:
            self.w._start_music_queue(tracks, 'youtube', 'Ready', recommendations=True)
            self.w.current_track = self.w.queue_tracks[0]
            self.w.current_queue_index = 0
            self.w.source_results['youtube'] = [self.w.current_track, self.youtube_track('unrelated001')]
            play.reset_mock()
            self.w.play_next()
            play.assert_called_once_with(self.w.queue_tracks[1], 1)
            self.w.current_track = self.w.queue_tracks[1]
            self.w.current_queue_index = 1
            play.reset_mock()
            with patch.object(self.w, 'maybe_refill_radio') as radio:
                self.w.handle_track_finished()
                self.w.ensure_following_track_prepared()
                radio.assert_not_called()
            play.assert_not_called()

    def test_supermix_without_auth_preserves_current_queue(self):
        existing = self.youtube_track('alreadyplay1')
        self.w.queue_tracks = [existing]
        with patch.object(self.w, 'connect_youtube_account') as message, \
             patch.object(self.w, 'start_search') as search, \
             patch.object(self.w, 'play_track') as play:
            self.w.play_supermix()
            message.assert_called_once()
            search.assert_not_called()
            play.assert_not_called()
        self.assertEqual(self.w.queue_tracks, [existing])

    def native_session(self, count=8):
        # Queue lifecycle tests must not start real yt-dlp prefetch requests.
        prefetch = patch.object(self.w, 'prepare_next_track')
        prefetch.start()
        self.addCleanup(prefetch.stop)
        tracks = [self.youtube_track(f'native{i:05}') for i in range(count)]
        session = {'mix_id': 'RDTMAK5uy_personal', 'seen': {t['video_id'] for t in tracks},
                   'anchor': '', 'waiting': False, 'failures': 0}
        with patch.object(self.w, 'play_track'):
            self.w._start_music_queue(tracks, 'youtube', 'Ready', recommendations=True,
                                      supermix_session=session)
        self.w.current_queue_index = 0
        self.w.current_track = self.w.queue_tracks[0]
        return session

    def test_supermix_refills_before_end_and_keeps_one_request_in_flight(self):
        session = self.native_session()
        with patch.object(self.w, '_make_supermix_worker') as factory:
            self.w.current_queue_index = 1  # six remaining: wait
            self.w.maybe_refill_supermix()
            factory.assert_not_called()
            session['anchor'] = self.w.queue_tracks[1]['video_id']
            self.w.current_queue_index = 2  # five remaining: prefetch
            self.w.ensure_following_track_prepared()
            self.w.maybe_refill_supermix()
            factory.assert_called_once_with(mix_id=session['mix_id'], anchor=session['anchor'],
                                             excluded_ids=session['seen'])
            factory.return_value.start.assert_called_once()

    def test_supermix_refill_survives_track_switch_and_appends_without_reordering(self):
        session = self.native_session(4)
        initial = list(self.w.queue_tracks)
        fresh = self.youtube_track('fresh000001')
        blocked = self.youtube_track('blocked0001')
        with patch.object(self.w, '_make_supermix_worker') as factory, patch.object(self.w, 'play_queue_index') as play:
            self.w.maybe_refill_supermix()
            worker = factory.return_value
            self.w.cancel_pending_request()  # called during ordinary track preparation
            self.w.current_queue_index = 1
            self.w.current_track = initial[1]
            self.w.disliked_track_keys.add(self.w.radio_track_key(blocked))
            self.w.on_supermix_refill_ready(worker, session, [initial[0], blocked, fresh, fresh])
            self.assertEqual(self.w.queue_tracks[:4], initial)
            self.assertEqual([t['video_id'] for t in self.w.queue_tracks[4:]], ['fresh000001'])
            self.assertEqual(self.w.current_queue_index, 1)
            self.assertIn('fresh000001', session['seen'])
            worker.cancel.assert_not_called()
            play.assert_not_called()

    def test_supermix_empty_queue_waits_and_resumes_when_next_batch_arrives(self):
        session = self.native_session(2)
        self.w.current_queue_index = 1
        self.w.current_track = self.w.queue_tracks[1]
        self.w._finish_transition_pending = True
        self.w._finish_guard_url = self.w.current_track['url']
        with patch.object(self.w, '_make_supermix_worker') as factory, \
             patch.object(self.w, 'play_queue_index') as play, \
             patch.object(self.w, 'search_neighbor_track') as generic:
            self.w.handle_track_finished()
            self.assertTrue(session['waiting'])
            self.assertFalse(self.w._finish_transition_pending)
            self.assertEqual(session['anchor'], self.w.current_track['video_id'])
            factory.assert_called_once()
            self.w.on_slot_status(self.w.active_slot, m.QMediaPlayer.MediaStatus.EndOfMedia)
            app.processEvents()
            factory.assert_called_once()
            play.assert_not_called()
            generic.assert_not_called()
            self.w.on_supermix_refill_ready(factory.return_value, session, [self.youtube_track('next0000001')])
            play.assert_called_once_with(2)
            self.assertFalse(session['waiting'])
            self.assertTrue(self.w._finish_transition_pending)  # stream failure can still advance
            self.w.on_slot_status(self.w.active_slot, m.QMediaPlayer.MediaStatus.EndOfMedia)
            play.assert_called_once()  # no second launch from the same end event

    def test_supermix_manual_next_at_end_waits_without_changing_completed_anchor(self):
        session = self.native_session(1)
        session['anchor'] = 'completed01'
        with patch.object(self.w, '_make_supermix_worker') as factory:
            self.w.play_next()
            self.assertTrue(session['waiting'])
            self.assertEqual(factory.call_args.kwargs['anchor'], 'completed01')

    def test_supermix_stale_refill_after_stop_cannot_restart_music(self):
        session = self.native_session(2)
        with patch.object(self.w, '_make_supermix_worker') as factory:
            self.w.maybe_refill_supermix()
            worker = factory.return_value
            self.w.stop_all()
            worker.cancel.assert_called_once()
            with patch.object(self.w, 'play_queue_index') as play:
                self.w.on_supermix_refill_ready(worker, session, [self.youtube_track('late0000001')])
                self.w.on_supermix_refill_error(worker, session, 'Late error')
                self.w.on_supermix_refill_finished(worker, session)
                play.assert_not_called()
                self.assertEqual(len(self.w.queue_tracks), 2)
                self.assertFalse(self.w.supermix_retry_timer.isActive())
                self.assertIsNone(self.w.supermix_session)

    def test_supermix_manual_queue_change_cancels_refill_and_ignores_late_answer(self):
        session = self.native_session(2)
        with patch.object(self.w, '_make_supermix_worker') as factory:
            self.w.maybe_refill_supermix()
            worker = factory.return_value
            self.w.add_to_queue(self.youtube_track('chosen00001'))
            self.w.on_supermix_refill_ready(worker, session, [self.youtube_track('late0000001')])
            worker.cancel.assert_called_once()
            self.assertEqual(len(self.w.queue_tracks), 3)
            self.assertEqual(self.w.queue_mode, 'manual')

    def test_supermix_old_session_cannot_append_to_new_supermix(self):
        old = self.native_session(2)
        with patch.object(self.w, '_make_supermix_worker') as factory:
            self.w.maybe_refill_supermix()
            worker = factory.return_value
            new = self.native_session(3)
            self.w.on_supermix_refill_ready(worker, old, [self.youtube_track('late0000001')])
            self.w.on_supermix_refill_finished(worker, old)
            self.assertIs(self.w.supermix_session, new)
            self.assertEqual(len(self.w.queue_tracks), 3)

    def test_supermix_transient_failure_and_duplicate_batch_use_delayed_retry(self):
        session = self.native_session(2)
        with patch.object(self.w, '_make_supermix_worker') as factory:
            self.w.maybe_refill_supermix()
            worker = factory.return_value
            self.w.on_supermix_refill_error(worker, session, 'Temporary network problem')
            self.w.on_supermix_refill_finished(worker, session)
            self.assertTrue(self.w.supermix_retry_timer.isActive())
            self.assertEqual(self.w.supermix_retry_timer.interval(), 5000)
            self.w.maybe_refill_supermix()
            factory.assert_called_once()
            self.w.supermix_retry_timer.stop()
            self.w.supermix_retry_timer.timeout.emit()
            self.assertEqual(factory.call_count, 2)
            self.w.on_supermix_refill_ready(worker, session, [self.w.queue_tracks[0]])
            self.w.on_supermix_refill_finished(worker, session)
            self.assertEqual(self.w.supermix_retry_timer.interval(), 15000)
            self.w.supermix_retry_timer.stop()
            self.w.maybe_refill_supermix()
            self.w.on_supermix_refill_ready(worker, session, [self.youtube_track('fresh000001')])
            self.assertEqual(session['failures'], 0)
            self.assertFalse(self.w.supermix_retry_timer.isActive())

    def test_supermix_real_thread_refills_and_resumes_after_last_track(self):
        session = self.native_session(1)
        self.w.youtube_auth_mode = 'browser'
        with patch('ytmusicapi.YTMusic') as client, patch.object(self.w, 'play_track') as play, \
             patch.object(m.SupermixWorker, '_auth_headers', return_value={}):
            client.return_value.get_watch_playlist.return_value = {
                'tracks': [{'videoId': f'next{i:07}', 'title': 'Next'} for i in range(7)]}
            self.w.handle_track_finished()
            finished = QSignalSpy(self.w.supermix_refill_worker.finished)
            self.assertTrue(session['waiting'])
            wait_for(lambda: len(finished) == 1 and play.call_count == 1)
            self.assertFalse(session['waiting'])
            self.assertEqual(len(self.w.queue_tracks), 8)
            self.assertEqual(play.call_args.args[1], 1)
            self.assertIsNone(self.w.supermix_refill_worker)
            client.return_value.get_home.assert_not_called()
            client.return_value.get_watch_playlist.assert_called_once_with(
                playlistId=session['mix_id'], videoId='native00000', radio=True, limit=25)

    def test_supermix_media_continues_when_refill_arrives_after_track_end(self):
        import threading
        release = threading.Event()
        self.addCleanup(release.set)
        self.w.youtube_auth_mode = 'browser'
        first = self.youtube_track('native00000')
        first_path = self.local_track('native-last')['url']
        next_path = self.local_track('native-continuation')['url']
        session = {'mix_id': 'RDTMAK5uy_personal', 'seen': {'native00000'},
                   'anchor': '', 'waiting': False, 'failures': 0}
        with patch('ytmusicapi.YTMusic') as client, \
             patch.object(m.SupermixWorker, '_auth_headers', return_value={}), \
             patch.object(self.w, 'offline_path_for', side_effect=lambda t: first_path if t.get('video_id') == 'native00000' else next_path):
            def slow_refill(**kwargs):
                if not release.wait(4):
                    raise TimeoutError('Test did not release refill')
                return {'tracks': [{'videoId': f'next{i:07}', 'title': 'Next'} for i in range(7)]}
            client.return_value.get_watch_playlist.side_effect = slow_refill
            self.w._start_music_queue([first], 'youtube', 'Ready', recommendations=True,
                                       supermix_session=session)
            wait_for(lambda: self.w.current_track is not None and self.w.supermix_refill_worker is not None)
            finished = QSignalSpy(self.w.supermix_refill_worker.finished)
            self.w.player.setPosition(9500)
            wait_for(lambda: self.w.player.position() >= 10000 and session['waiting'])
            # Without an audio device this Qt backend reaches the end position
            # but does not emit EndOfMedia. Exercise that handler explicitly.
            self.w.on_slot_status(self.w.active_slot, m.QMediaPlayer.MediaStatus.EndOfMedia)
            self.assertTrue(session['waiting'])
            self.assertEqual(len(finished), 0)
            release.set()
            wait_for(lambda: self.w.current_track.get('video_id') == 'next0000000'
                     and self.w.player.position() > 0 and len(finished) == 1)
            self.assertEqual(self.w.player.playbackState(), m.QMediaPlayer.PlaybackState.PlayingState)
            self.assertEqual(self.w.current_queue_index, 1)
            self.assertEqual(len(self.w.queue_tracks), 8)
            self.assertFalse(session['waiting'])

    def test_shuffle_without_likes_does_not_search_for_generic_music(self):
        self.w.current_source = 'youtube'
        with patch.object(m.QMessageBox, 'information') as message, \
             patch.object(self.w, 'start_search') as search, \
             patch.object(self.w, 'play_track') as play:
            self.w.play_personal_mix('youtube')
            message.assert_called_once()
            search.assert_not_called()
            play.assert_not_called()
        self.assertEqual(self.w.queue_tracks, [])

    def test_soundcloud_refresh_fetches_likes_without_playlist_links(self):
        self.w.soundcloud_profile_url = 'https://soundcloud.com/example'
        with patch.object(m, 'SearchWorker') as worker:
            self.w.load_soundcloud_account_content(force=True)
            worker.assert_called_once()
            self.assertEqual(worker.call_args.kwargs['direct_url'], 'https://soundcloud.com/example/likes')
            self.assertTrue(worker.call_args.kwargs['paginate_all'])
            worker.return_value.start.assert_called_once()

    def test_new_youtube_like_appears_at_top_without_sync(self):
        self.w._likes_render_batch = 5
        self.w.youtube_liked_tracks = [self.youtube_track(f'existing{i:05}') for i in range(180)]
        self.w.refresh_likes_list(force_rebuild=True)
        self.assertFalse(self.w.youtube_likes_list.isVisible())
        new = self.youtube_track('justliked01')
        self.request_like(new, True)
        self.w.on_youtube_music_like_result(new, True, True, 'OK')
        with patch.object(self.w, 'sync_youtube_likes') as sync:
            self.w.set_source('likes')
            app.processEvents()
            self.assertEqual(self.visible_youtube_ids()[0], 'justliked01')
            self.assertLess(self.w.youtube_likes_list.count(), len(self.w.youtube_liked_tracks))
            sync.assert_not_called()
        self.assertIn('justliked01', self.saved_ids())

    def test_pending_like_appears_in_library_and_failure_removes_it(self):
        self.w._likes_render_batch = 5
        self.w.youtube_liked_tracks = [self.youtube_track(f'existing{i:05}') for i in range(12)]
        self.w.refresh_likes_list(force_rebuild=True)
        new = self.youtube_track('pendingview1')
        self.request_like(new, True)
        self.w.set_source('likes')
        self.assertEqual(self.visible_youtube_ids()[0], 'pendingview1')
        row = self.w.youtube_likes_list.itemWidget(self.w.youtube_likes_list.item(0))
        self.assertTrue(row.favorite_button.isChecked())
        self.assertFalse(row.favorite_button.isEnabled())
        self.w.save_youtube_likes()
        self.assertNotIn('pendingview1', self.saved_ids())
        with patch.object(m.QMessageBox, 'warning'):
            self.w.on_youtube_music_like_result(new, True, False, 'Rejected')
        self.assertNotIn('pendingview1', self.visible_youtube_ids())
        self.assertEqual(self.visible_youtube_ids()[0], 'existing00000')

    def test_pending_unlike_hides_library_row_and_failure_restores_it(self):
        track = self.youtube_track('restoredrow1')
        self.w.youtube_liked_tracks = [track, self.youtube_track('secondrow001')]
        self.w.refresh_likes_list(force_rebuild=True)
        self.request_like(track, False)
        self.w.set_source('likes')
        self.assertNotIn('restoredrow1', self.visible_youtube_ids())
        with patch.object(m.QMessageBox, 'warning'):
            self.w.on_youtube_music_like_result(track, False, False, 'Rejected')
        self.assertEqual(self.visible_youtube_ids()[0], 'restoredrow1')
        row = self.w.youtube_likes_list.itemWidget(self.w.youtube_likes_list.item(0))
        self.assertTrue(row.favorite_button.isChecked())
        self.assertTrue(row.favorite_button.isEnabled())

    def test_library_refresh_replaces_changed_middle_row(self):
        original = [self.youtube_track(f'original{i:05}') for i in range(3)]
        self.w.youtube_liked_tracks = original
        self.w.refresh_likes_list(force_rebuild=True)
        self.w.youtube_liked_tracks = [original[0], self.youtube_track('replacement1'), original[2]]
        self.w.refresh_likes_list()
        self.assertEqual(self.visible_youtube_ids(), ['original00000', 'replacement1', 'original00002'])

    def test_library_tail_pagination_preserves_existing_rows(self):
        original = [self.youtube_track(f'original{i:05}') for i in range(3)]
        self.w.youtube_liked_tracks = list(original)
        self.w.refresh_likes_list(force_rebuild=True)
        first = self.w.youtube_likes_list.itemWidget(self.w.youtube_likes_list.item(0))
        self.w.youtube_liked_tracks.extend(self.youtube_track(f'added{i:05}') for i in range(2))
        self.w.refresh_likes_list()
        self.w.set_source('likes')
        app.processEvents()
        self.w.maybe_load_more_likes(self.w.youtube_likes_list)
        self.assertIs(first, self.w.youtube_likes_list.itemWidget(self.w.youtube_likes_list.item(0)))
        self.assertEqual(len(self.visible_youtube_ids()), 5)

    def large_library_fixture(self, count=600):
        w = self.w
        tracks = [self.youtube_track(f'window{i:05}') for i in range(count)]
        w.youtube_liked_tracks = tracks
        w.refresh_likes_list(force_rebuild=True)
        w.set_source('likes')
        while w._likes_rendered_counts['youtube'] < count:
            w._append_likes_rows(w.youtube_likes_list)
        app.processEvents()
        return tracks

    def settle_row_deletions(self):
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()

    def test_large_library_keeps_all_items_but_only_visible_nearby_widgets(self):
        w = self.w
        tracks = self.large_library_fixture()
        lw = w.youtube_likes_list
        for index in (400, 100, 599, 0):
            lw.scrollToItem(lw.item(index), m.QListWidget.ScrollHint.PositionAtTop)
            self.settle_row_deletions()
            self.assertEqual(lw.count(), len(tracks))
            self.assertLess(len(lw.findChildren(m.TrackRow)), 45)
            row = lw.itemWidget(lw.item(index))
            self.assertIsInstance(row, m.TrackRow)
            self.assertEqual(row.track['video_id'], tracks[index]['video_id'])
            for y in range(8, lw.viewport().height() - 8, 76):
                item = lw.itemAt(m.QPoint(10, y))
                if item is not None:
                    self.assertIsInstance(lw.itemWidget(item), m.TrackRow)
            with patch.object(w, 'play_youtube_likes_from') as play:
                row.play_button.click()
                play.assert_called_once_with(tracks[index])
        self.assertEqual(self.visible_youtube_ids(), [t['video_id'] for t in tracks])

    def test_offscreen_current_and_loading_rows_restore_state_when_recreated(self):
        w = self.w
        tracks = self.large_library_fixture()
        lw = w.youtube_likes_list
        w.current_track = tracks[400]
        w.requested_track = tracks[500]
        for index in (400, 500, 0, 400, 500):
            lw.scrollToItem(lw.item(index), m.QListWidget.ScrollHint.PositionAtTop)
            self.settle_row_deletions()
            row = lw.itemWidget(lw.item(index))
            if index == 400:
                self.assertTrue(row._is_current)
                self.assertFalse(row._loading)
            elif index == 500:
                self.assertTrue(row._loading)
                self.assertEqual(row.index_label.text(), '⏳')

    def test_virtual_library_search_and_unlike_failure_restore_the_correct_track(self):
        w = self.w
        tracks = self.large_library_fixture()
        target = tracks[400]
        w.likes_search_input.setText(target['title'])
        self.settle_row_deletions()
        lw = w.youtube_likes_list
        self.assertEqual(lw.count(), 1)
        self.assertEqual(lw.itemWidget(lw.item(0)).track, target)
        self.request_like(target, False)
        self.assertEqual(lw.count(), 0)
        with patch.object(m.QMessageBox, 'warning'):
            w.on_youtube_music_like_result(target, False, False, 'Network failure')
        self.settle_row_deletions()
        self.assertEqual(lw.count(), 1)
        self.assertEqual(lw.itemWidget(lw.item(0)).track['video_id'], target['video_id'])
        self.assertTrue(lw.itemWidget(lw.item(0)).favorite_button.isChecked())
        w.likes_search_input.clear()
        self.settle_row_deletions()
        self.assertEqual(lw.count(), w._likes_render_batch)
        self.assertLess(len(lw.findChildren(m.TrackRow)), 45)

    def test_soundcloud_and_local_library_rows_are_windowed_and_dispatch_actions(self):
        w = self.w
        with patch.object(w, 'queue_artwork_lookup'):
            for source, lw, tab in (('soundcloud', w.soundcloud_likes_list, 1), ('local', w.likes_list, 2)):
                tracks = [{'source': source, 'url': f'https://example.invalid/{source}/{i}',
                           'title': f'{source} {i}'} for i in range(350)]
                if source == 'soundcloud':
                    w.soundcloud_liked_tracks = tracks
                else:
                    w.favorites = {w.favorite_key(t): t for t in tracks}
                w.refresh_likes_list(force_rebuild=True)
                w.set_source('likes')
                w.likes_tabs.setCurrentIndex(tab)
                kind = w._likes_kind_for_widget(lw)
                while w._likes_rendered_counts[kind] < len(tracks):
                    w._append_likes_rows(lw)
                lw.scrollToItem(lw.item(300), m.QListWidget.ScrollHint.PositionAtTop)
                self.settle_row_deletions()
                row = lw.itemWidget(lw.item(300))
                self.assertIsInstance(row, m.TrackRow)
                self.assertLess(len(lw.findChildren(m.TrackRow)), 45)
                method = 'play_soundcloud_likes_from' if source == 'soundcloud' else 'add_to_queue'
                with patch.object(w, method) as play:
                    row.play_button.click()
                    self.assertEqual(play.call_args.args[0]['url'], tracks[300]['url'])

    @staticmethod
    def encoded_image(width=2048, height=1024, color='#426699', fmt='JPEG'):
        image = QImage(width, height, QImage.Format.Format_RGB32)
        image.fill(m.QColor(color))
        buffer = m.QBuffer()
        buffer.open(m.QIODevice.OpenModeFlag.WriteOnly)
        assert image.save(buffer, fmt)
        return bytes(buffer.data())

    def test_wallpaper_picker_save_restores_owned_copy_and_reuses_render_cache(self):
        w = self.w
        source = self.test_path / 'my-photo.jpg'
        source.write_bytes(self.encoded_image(3072, 1536, '#426699'))
        dialog = m.SettingsDialog(w)
        with patch.object(m.QFileDialog, 'getOpenFileName', return_value=(str(source), '')):
            dialog.choose_wallpaper()
        self.assertFalse(w.backdrop.has_wallpaper)
        self.assertEqual(dialog.wallpaper_draft.size(), m.QSize(2048, 1024))
        dialog.wallpaper_dim_slider.setValue(73)
        dialog.save_changes()
        self.assertTrue(w.backdrop.has_wallpaper)
        owned = Path(w.wallpaper_path)
        self.assertNotEqual(owned, source)
        self.assertTrue(owned.is_file())
        source.unlink()
        with self.reopened_player() as restored:
            self.assertTrue(restored.backdrop.has_wallpaper)
            self.assertEqual(restored.backdrop.image.size(), m.QSize(2048, 1024))
            self.assertEqual(restored.wallpaper_dim, 73)
            restored.backdrop.grab()
            cache_key = restored.backdrop._cache.cacheKey()
            restored.backdrop.grab()
            self.assertEqual(restored.backdrop._cache.cacheKey(), cache_key)
            restored.toggle_theme()
            restored.backdrop.grab()
            self.assertNotEqual(restored.backdrop._cache.cacheKey(), cache_key)
            self.assertLessEqual(max(restored.backdrop._cache.width(), restored.backdrop._cache.height()), 2048)

    def test_wallpaper_cancel_and_invalid_selection_leave_player_unchanged(self):
        w = self.w
        image = QImage(512, 256, QImage.Format.Format_RGB32)
        image.fill(m.QColor('red'))
        self.assertTrue(w.set_wallpaper_image(image))
        old_bytes = Path(w.wallpaper_path).read_bytes()
        old_key = w.backdrop.image.cacheKey()
        source = self.test_path / 'replacement.png'
        source.write_bytes(self.encoded_image(256, 128, '#426699', 'PNG'))
        dialog = m.SettingsDialog(w)
        with patch.object(m.QFileDialog, 'getOpenFileName', return_value=(str(source), '')):
            dialog.choose_wallpaper()
        dialog.wallpaper_dim_slider.setValue(10)
        dialog.reject()
        self.assertEqual(w.backdrop.image.cacheKey(), old_key)
        self.assertEqual(Path(w.wallpaper_path).read_bytes(), old_bytes)
        self.assertEqual(w.wallpaper_dim, 55)
        bad = self.test_path / 'bad.png'
        bad.write_bytes(b'not an image')
        other = m.SettingsDialog(w)
        with patch.object(m.QFileDialog, 'getOpenFileName', return_value=(str(bad), '')):
            other.choose_wallpaper()
        self.assertFalse(other.wallpaper_dirty)
        self.assertIn('Не удалось', other.wallpaper_message.text())
        self.assertEqual(w.backdrop.image.cacheKey(), old_key)

    def test_wallpaper_remove_deletes_only_app_copy_and_survives_restart(self):
        w = self.w
        original = self.test_path / 'original.png'
        original.write_bytes(self.encoded_image(256, 128, '#426699', 'PNG'))
        self.assertTrue(w.set_wallpaper_image(m.read_wallpaper_image(str(original))))
        owned = Path(w.wallpaper_path)
        dialog = m.SettingsDialog(w)
        dialog.remove_wallpaper()
        self.assertTrue(w.backdrop.has_wallpaper)
        dialog.save_changes()
        self.assertTrue(original.exists())
        self.assertFalse(owned.exists())
        self.assertFalse(w.backdrop.has_wallpaper)
        with self.reopened_player() as restored:
            self.assertFalse(restored.backdrop.has_wallpaper)
            self.assertEqual(restored.wallpaper_path, '')
            restored.backdrop.grab()
            self.assertIsNone(restored.backdrop._cache)

    def test_failed_wallpaper_save_keeps_previous_file_and_missing_wallpaper_does_not_block_startup(self):
        w = self.w
        image = QImage(256, 128, QImage.Format.Format_RGB32)
        image.fill(m.QColor('red'))
        self.assertTrue(w.set_wallpaper_image(image))
        previous = Path(w.wallpaper_path).read_bytes()
        key = w.backdrop.image.cacheKey()
        dialog = m.SettingsDialog(w)
        dialog.wallpaper_dirty = True
        dialog.wallpaper_draft = image
        with patch.object(m, 'QSaveFile') as output:
            output.return_value.open.return_value = False
            dialog.save_changes()
        self.assertEqual(dialog.result(), 0)
        self.assertIn('Не удалось сохранить', dialog.wallpaper_message.text())
        self.assertEqual(Path(w.wallpaper_path).read_bytes(), previous)
        self.assertEqual(w.backdrop.image.cacheKey(), key)
        with patch.object(m, 'app_data_directory', side_effect=OSError('unavailable')):
            self.assertFalse(w.set_wallpaper_image(image))
        self.assertEqual(w.backdrop.image.cacheKey(), key)
        w.settings.setValue('wallpaper_path', str(self.test_path / 'missing.png'))
        w.settings.setValue('wallpaper_dim', 'invalid')
        with self.reopened_player() as restored:
            self.assertFalse(restored.backdrop.has_wallpaper)
            self.assertEqual(restored.wallpaper_dim, 55)
        with patch.object(m, 'QImageReader') as reader:
            reader.return_value.size.return_value = m.QSize(10000, 10000)
            self.assertTrue(m.read_wallpaper_image(w.wallpaper_path).isNull())
            reader.return_value.read.assert_not_called()

    def test_large_artwork_is_decoded_to_display_resolution_and_bad_images_are_ignored(self):
        w = self.w
        pixmap = w._decode_artwork(self.encoded_image())
        self.assertEqual(pixmap.size(), m.QSize(768, 384))
        self.assertIsNone(w._decode_artwork(b'not an image'))
        self.assertIsNone(w._decode_artwork(b''))
        with patch.object(m, 'QImageReader') as reader:
            reader.return_value.size.return_value = m.QSize(10000, 10000)
            self.assertIsNone(w._decode_artwork(b'header'))
            reader.return_value.read.assert_not_called()

    def test_artwork_cache_is_bounded_by_bytes_and_preserves_recently_used_entries(self):
        w = self.w
        cache = w.pixmap_cache
        cache.clear()
        image = m.QPixmap(32, 32)
        image.fill(m.QColor('blue'))
        size = w._pixmap_bytes(image)
        for key in ('a', 'b'):
            w._cache_pixmap(cache, key, image, size * 2, 250)
        cache.move_to_end('a')
        w._cache_pixmap(cache, 'c', image, size * 2, 250)
        self.assertEqual(list(cache), ['a', 'c'])
        w._cache_pixmap(cache, 'c', image, size * 2, 250)
        self.assertLessEqual(sum(w._pixmap_bytes(p) for p in cache.values()), size * 2)
        for index in range(260):
            w._cache_pixmap(cache, str(index), None, size * 2, 250)
        self.assertEqual(len(cache), 250)

    def test_repeated_album_thumbnails_share_pixels_and_respect_high_dpi(self):
        w = self.w
        labels = [m.QLabel(), m.QLabel()]
        source = m.QPixmap(512, 512)
        source.fill(m.QColor('blue'))
        for label in labels:
            label.setFixedSize(44, 44)
            with patch.object(label, 'devicePixelRatioF', return_value=2.0):
                w.set_pixmap_safe(label, source)
        self.assertEqual(labels[0].pixmap().cacheKey(), labels[1].pixmap().cacheKey())
        # Mocking the Python DPI accessor doesn't change QLabel's native DPI.
        # Inspect the prepared bitmap before Qt adapts it for this 1x test screen.
        rendered = w.thumbnail_cache[(source.cacheKey(), 44, 2.0, False)]
        self.assertEqual(rendered.devicePixelRatioF(), 2)
        self.assertEqual(rendered.size(), m.QSize(88, 88))
        self.assertEqual(rendered.toImage().pixelColor(44, 44), m.QColor('blue'))

    def test_completed_image_still_reaches_target_when_it_exceeds_cache_budget(self):
        w = self.w
        label = m.QLabel()
        label.setFixedSize(44, 44)
        url = 'https://example.invalid/cover.jpg'
        data = self.encoded_image(128, 128, '#124599', 'PNG')
        class Reply:
            deleted = False
            def readAll(self): return data
            def deleteLater(self): self.deleted = True
        reply = Reply()
        with patch.object(w, 'pump_images'):
            w.request_image(url, label)
            w.ARTWORK_CACHE_BYTES = 1
            w.image_finished(url, reply)
        self.assertNotIn(url, w.pixmap_cache)
        self.assertEqual(label.pixmap().toImage().pixelColor(22, 22), m.QColor('#124599'))
        self.assertTrue(reply.deleted)

    def test_cancelled_artwork_targets_are_not_retained_or_downloaded(self):
        w = self.w
        label = m.QLabel()
        url = 'https://example.invalid/unneeded.jpg'
        with patch.object(w, 'pump_images'):
            w.request_image(url, label)
        reference = weakref.ref(label)
        del label
        gc.collect()
        self.assertIsNone(reference())
        with patch.object(w.network_manager, 'get') as request:
            w.pump_images()
            request.assert_not_called()
        self.assertNotIn(url, w.image_waiters)
        self.assertFalse(w.image_backlog)

    def test_late_artwork_cannot_replace_a_newer_image_request(self):
        w = self.w
        label = m.QLabel()
        label.setFixedSize(44, 44)
        old_url = 'https://example.invalid/old.jpg'
        new_url = 'https://example.invalid/new.jpg'
        data = self.encoded_image(128, 128, 'red', 'PNG')
        class Reply:
            def readAll(self): return data
            def deleteLater(self): pass
        with patch.object(w, 'pump_images'):
            w.request_image(old_url, label)
            w.request_image(new_url, label)
            expected = label.pixmap().cacheKey()
            w.image_finished(old_url, Reply())
        self.assertEqual(label.property('requested_image'), new_url)
        self.assertEqual(label.pixmap().cacheKey(), expected)

    def test_real_http_artwork_download_is_bounded_and_displays_valid_image(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        w = self.w
        encoded = self.encoded_image(128, 128, '#124599', 'PNG')
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                data = encoded if self.path == '/valid.png' else b'x' * 8192
                self.send_response(200)
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                try:
                    self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError):
                    pass
            def log_message(self, *args): pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        normal, oversized = m.QLabel(), m.QLabel()
        normal.setFixedSize(44, 44)
        oversized.setFixedSize(44, 44)
        w.ARTWORK_MAX_DOWNLOAD = 1024
        try:
            # Production normalizes HTTP artwork URLs to HTTPS. This fixture is
            # a plain loopback HTTP server; leave TLS policy itself unchanged.
            with patch.object(m, 'normalize_artwork_url', side_effect=lambda url: url), \
                 patch.object(w.network_manager, 'get', wraps=w.network_manager.get) as get:
                w.request_image(base + '/valid.png', normal)
                w.request_image(base + '/oversized.png', oversized)
                wait_for(lambda: w.active_images == 0)
                self.assertEqual(get.call_count, 2)
                self.assertTrue(all(call.args[0].transferTimeout() == 10000 for call in get.call_args_list))
            self.assertEqual(normal.pixmap().toImage().pixelColor(22, 22), m.QColor('#124599'))
            self.assertIsNone(w.pixmap_cache[base + '/oversized.png'])
            self.assertFalse(w.image_waiters)
            self.assertFalse(w.image_backlog)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)

    def test_home_counts_follow_sync_pages_without_replacing_supermix_card(self):
        w = self.w
        mix = w.start_cards[1]
        likes_card = w.start_cards[0]
        worker = self.begin_sync()
        self.assertIn('обновление', likes_card.subtitle)
        tracks = [self.youtube_track(f'page{i:07}') for i in range(7)]
        w.on_youtube_likes_results(worker, tracks[:3], '__SC_LIKES_PAGE__:3')
        self.assertEqual(likes_card.subtitle, '3 трека · обновление…')
        self.assertIn('3', w.likes_tabs.tabText(0))
        w.on_youtube_likes_results(worker, tracks[3:], '__SC_LIKES_PAGE__:7')
        self.assertIn('7 треков', likes_card.subtitle)
        w.on_youtube_likes_results(worker, [], '__SC_LIKES_DONE__:7')
        w.on_youtube_likes_finished(worker)
        self.assertEqual(likes_card.subtitle, '7 любимых треков')
        self.assertIs(w.start_cards[1], mix)
        self.assertIs(w.start_cards[0], likes_card)

    def test_home_counts_include_pending_likes_and_rollback_for_both_services(self):
        w = self.w
        track = self.youtube_track('countlike01')
        self.request_like(track, True)
        self.assertEqual(w.start_cards[0].subtitle, '1 любимый трек')
        self.assertIn('1', w.likes_tabs.tabText(0))
        with patch.object(m.QMessageBox, 'warning'):
            w.on_youtube_music_like_result(track, True, False, 'Rejected')
        self.assertEqual(w.start_cards[0].subtitle, 'Вся твоя любимая музыка')
        w.set_source('soundcloud')
        w.soundcloud_liked_tracks = [{'source': 'soundcloud', 'url': 'https://example.invalid/a', 'title': 'A'}]
        w._soundcloud_likes_loading = True
        w.refresh_likes_status_only()
        self.assertEqual(w.start_cards[0].subtitle, '1 трек · обновление…')
        self.assertIn('1', w.likes_tabs.tabText(1))
        w._soundcloud_likes_loading = False
        w.refresh_likes_status_only()
        self.assertEqual(w.start_cards[0].subtitle, '1 любимый трек')

    def test_first_sync_page_replaces_a_scrolled_virtual_library(self):
        w = self.w
        self.large_library_fixture()
        lw = w.youtube_likes_list
        lw.scrollToBottom()
        self.settle_row_deletions()
        worker = self.begin_sync()
        tracks = [self.youtube_track('newpage0001'), self.youtube_track('newpage0002')]
        w.on_youtube_likes_results(worker, tracks, '__SC_LIKES_PAGE__:2')
        self.settle_row_deletions()
        self.assertEqual(self.visible_youtube_ids(), [t['video_id'] for t in tracks])
        self.assertEqual(len(lw.findChildren(m.TrackRow)), 2)
        self.assertEqual(lw.itemWidget(lw.item(0)).track['video_id'], 'newpage0001')

    def test_soundcloud_home_busy_count_follows_sync_start_error_and_finish(self):
        w = self.w
        w.set_source('soundcloud')
        w.soundcloud_profile_url = 'https://soundcloud.com/example'
        with patch.object(m, 'SearchWorker') as worker:
            w.load_soundcloud_account_content(force=True)
            self.assertEqual(w.start_cards[0].subtitle, '0 треков · обновление…')
            w.on_soundcloud_account_error('likes', worker.return_value, 'Temporary failure')
            self.assertEqual(w.start_cards[0].subtitle, 'Вся твоя любимая музыка')
            w.on_soundcloud_account_finished('likes', worker.return_value)
            w.load_soundcloud_account_content(force=True)
            self.assertIn('обновление', w.start_cards[0].subtitle)
            w.on_soundcloud_account_finished('likes', worker.return_value)
            self.assertEqual(w.start_cards[0].subtitle, 'Вся твоя любимая музыка')

    def test_sync_pages_preserve_new_likes_and_unlikes(self):
        a, b, c = [self.youtube_track(key) for key in ('newlike0001', 'removed0001', 'remote00001')]
        self.w.youtube_liked_tracks = [b]
        worker = self.begin_sync()
        for track, liked in ((a, True), (b, False)):
            self.request_like(track, liked)
            self.w.on_youtube_music_like_result(track, liked, True, 'OK')
        for tracks in ([b], [b, c]):
            self.w.on_youtube_likes_results(worker, tracks, '__SC_LIKES_PAGE__:1')
            self.assertIn('newlike0001', self.confirmed_ids())
            self.assertNotIn('removed0001', self.confirmed_ids())
            self.assertEqual(self.visible_youtube_ids()[0], 'newlike0001')
        self.w.on_youtube_likes_results(worker, [], '__SC_LIKES_DONE__:2')
        self.w.on_youtube_likes_finished(worker)
        self.assertEqual(self.confirmed_ids(), {'newlike0001', 'remote00001'})
        self.assertEqual(self.saved_ids(), self.confirmed_ids())
        self.assertFalse(self.w._youtube_sync_rating_changes)

    def test_latest_confirmed_click_wins_during_sync(self):
        track = self.youtube_track('toggle00001')
        self.w.youtube_liked_tracks = [track]
        worker = self.begin_sync()
        for liked in (False, True, False):
            self.request_like(track, liked)
            self.w.on_youtube_music_like_result(track, liked, True, 'OK')
            self.w.on_youtube_likes_results(worker, [track], '__SC_LIKES_PAGE__:1')
            self.assertEqual(self.w.is_youtube_music_liked(track), liked)
        self.w.on_youtube_likes_finished(worker)
        self.assertNotIn('toggle00001', self.saved_ids())

    def test_failed_sync_restores_snapshot_and_preserves_confirmed_clicks(self):
        a, b, c, d = [self.youtube_track(key) for key in
                      ('newlike0001', 'removed0001', 'partial0001', 'restore0001')]
        self.w.youtube_liked_tracks = [b, d]
        worker = self.begin_sync()
        for track, liked in ((a, True), (b, False)):
            self.request_like(track, liked)
            self.w.on_youtube_music_like_result(track, liked, True, 'OK')
        self.w.on_youtube_likes_results(worker, [c], '__SC_LIKES_PAGE__:1')
        self.w.on_youtube_likes_error(worker, 'Temporary failure')
        self.w.on_youtube_likes_finished(worker)
        self.assertEqual(self.confirmed_ids(), {'newlike0001', 'restore0001'})
        self.assertEqual(self.saved_ids(), self.confirmed_ids())

    def test_sync_finish_does_not_drop_pending_intent(self):
        track = self.youtube_track('pending0001')
        worker = self.begin_sync()
        self.request_like(track, True)
        self.w.on_youtube_likes_results(worker, [], '')
        self.w.on_youtube_likes_finished(worker)
        self.assertTrue(self.w.is_youtube_music_liked(track))
        self.assertNotIn('pending0001', self.saved_ids())
        self.w.on_youtube_music_like_result(track, True, True, 'OK')
        self.assertIn('pending0001', self.saved_ids())

    def test_empty_sync_preserves_only_new_confirmed_likes(self):
        old = self.youtube_track('oldlike0001')
        new = self.youtube_track('newlike0001')
        self.w.youtube_liked_tracks = [old]
        worker = self.begin_sync()
        self.request_like(new, True)
        self.w.on_youtube_music_like_result(new, True, True, 'OK')
        self.w.on_youtube_likes_results(worker, [], '__SC_LIKES_DONE__:0')
        self.w.on_youtube_likes_finished(worker)
        self.assertEqual(self.saved_ids(), {'newlike0001'})

    def test_stalled_local_media_times_out_without_stopping_old_track(self):
        self.start(self.local_track('still-playing'))
        old = self.w.player
        self.w.PENDING_MEDIA_TIMEOUT_MS = 25
        next_track = self.local_track('never-started')
        slot = self.w.idle_slot()
        with patch.object(self.w.players[slot], 'play'):
            self.w.play_track(next_track, -1)
            self.assertTrue(self.w.pending_media_timer.isActive())
            wait_for(lambda: self.w.requested_track is None)
        self.assertIs(self.w.player, old)
        self.assertEqual(old.playbackState(), m.QMediaPlayer.PlaybackState.PlayingState)
        self.assertIsNone(self.w.pending_slot)
        self.assertFalse(self.w.pending_media_timer.isActive())
        self.assertTrue(self.w.players[slot].source().isEmpty())

    def test_remote_timeout_retries_only_once(self):
        self.start(self.local_track('old-for-retry'))
        old = self.w.player
        track = self.youtube_track('retry000001')
        self.w.requested_track = track
        self.w.pending_refreshed = False
        self.w.PENDING_MEDIA_TIMEOUT_MS = 25
        slot = self.w.idle_slot()
        with patch.object(self.w.players[slot], 'setSource'), \
             patch.object(self.w.players[slot], 'play'), \
             patch.object(self.w, 'start_stream_extraction') as extract:
            self.w.start_pending_media(m.QUrl('https://example.invalid/audio'), 'test')
            wait_for(lambda: extract.call_count == 1)
            self.assertIsNotNone(self.w.requested_track)
            self.w.start_pending_media(m.QUrl('https://example.invalid/refreshed'), 'retry')
            wait_for(lambda: self.w.requested_track is None)
            extract.assert_called_once_with(track)
        self.assertIs(self.w.player, old)
        self.assertEqual(old.playbackState(), m.QMediaPlayer.PlaybackState.PlayingState)
        self.assertFalse(self.w.pending_media_timer.isActive())

    def test_cancel_and_commit_disarm_media_timeout(self):
        self.start(self.local_track('commit'))
        self.assertFalse(self.w.pending_media_timer.isActive())
        slot = self.w.idle_slot()
        with patch.object(self.w.players[slot], 'play'):
            self.w.play_track(self.local_track('cancel'), -1)
            self.assertTrue(self.w.pending_media_timer.isActive())
            self.w.cancel_pending_request()
        self.assertFalse(self.w.pending_media_timer.isActive())
        current = self.w.current_track
        self.w.on_pending_media_timeout()
        self.assertIs(self.w.current_track, current)

    @contextmanager
    def reopened_player(self):
        reopened = m.MusicPlayer()
        for player in reopened.players:
            player.setAudioOutput(None)
        reopened.show()
        app.processEvents()
        try:
            yield reopened
        finally:
            reopened.stop_all()
            reopened._force_exit = True
            reopened.close()
            reopened.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            app.processEvents()

    def saved_local_session(self):
        w = self.w
        tracks = [{**self.local_track(name), 'queue_id': name}
                  for name in ('session-a', 'session-b', 'session-duplicate')]
        tracks[2]['url'] = tracks[0]['url']
        w.queue_tracks = tracks
        w.refresh_queue_list()
        with patch.object(w, 'prepare_next_track'), patch.object(w, 'ensure_following_track_prepared'):
            w.play_track(tracks[1], 1)
            wait_for(lambda: w.current_track is not None and w.current_queue_index == 1)
        w.player.setPosition(2600)
        w.player.pause()
        w.save_playback_session()
        return tracks

    def test_large_saved_queue_restores_all_data_with_few_row_widgets(self):
        w = self.w
        tracks = [{**self.youtube_track(f'start{i:06}'), 'queue_id': f'q{i}'} for i in range(2500)]
        w.queue_tracks = tracks
        w.current_track = tracks[-1]
        w.current_queue_index = len(tracks) - 1
        w.refresh_queue_list()
        w.save_playback_session()
        with self.reopened_player() as restored:
            self.assertEqual([t['queue_id'] for t in restored.queue_tracks],
                             [t['queue_id'] for t in tracks])
            self.assertEqual(restored.queue_list.count(), 2500)
            self.assertLess(len(restored.queue_list.findChildren(m.TrackRow)), 45)
            self.assertEqual(restored.current_queue_index, 2499)
            self.assertTrue(all(player.source().isEmpty() for player in restored.players))
            restored.toggle_queue_if_hidden()
            wait_for(lambda: restored.queue_animation.state() == QAbstractAnimation.State.Stopped)
            restored.queue_list.scrollToItem(restored.queue_list.item(2499))
            self.settle_row_deletions()
            row = restored.queue_list.itemWidget(restored.queue_list.item(2499))
            self.assertTrue(row.property('playing'))
            self.assertEqual(row.track['queue_id'], 'q2499')
            self.assertLess(len(restored.queue_list.findChildren(m.TrackRow)), 45)

    def test_queue_window_scroll_actions_and_duplicate_identity_survive_reordering(self):
        w = self.w
        tracks = [{**self.youtube_track(f'queue{i:06}'), 'queue_id': f'q{i}'} for i in range(600)]
        tracks[400]['url'] = tracks[0]['url']
        w.queue_tracks = tracks
        w.current_track = tracks[400]
        w.current_queue_index = 400
        w.refresh_queue_list()
        w.toggle_queue_if_hidden()
        wait_for(lambda: w.queue_animation.state() == QAbstractAnimation.State.Stopped)
        lw = w.queue_list
        for index in (400, 100, 599, 0, 400):
            lw.scrollToItem(lw.item(index), m.QListWidget.ScrollHint.PositionAtTop)
            self.settle_row_deletions()
            self.assertEqual(lw.count(), 600)
            self.assertLess(len(lw.findChildren(m.TrackRow)), 45)
            row = lw.itemWidget(lw.item(index))
            self.assertEqual(row.track['queue_id'], f'q{index}')
            self.assertEqual(bool(row.property('playing')), index == 400)
            for y in range(8, lw.viewport().height() - 8, 68):
                item = lw.itemAt(m.QPoint(10, y))
                if item is not None:
                    self.assertIsInstance(lw.itemWidget(item), m.TrackRow)
            with patch.object(w, 'play_queue_index') as play:
                row.play_requested.emit(row.track)
                play.assert_called_once_with(index)
        # A row created after scrolling must remove its own position, even with duplicates.
        lw.scrollToItem(lw.item(100), m.QListWidget.ScrollHint.PositionAtTop)
        self.settle_row_deletions()
        with patch.object(w, 'prepare_next_track'):
            lw.itemWidget(lw.item(100)).remove_button.click()
            self.assertEqual(w.current_queue_index, 399)
            w.move_queue_index(399, 1)
            self.settle_row_deletions()
        self.assertEqual(w.current_queue_index, 400)
        self.assertNotIn('q100', [track['queue_id'] for track in w.queue_tracks])
        lw.scrollToItem(lw.item(400), m.QListWidget.ScrollHint.PositionAtTop)
        self.settle_row_deletions()
        row = lw.itemWidget(lw.item(400))
        self.assertEqual(row.track['queue_id'], 'q400')
        self.assertTrue(row.property('playing'))
        with patch.object(w, 'play_queue_index') as play:
            row.play_requested.emit(row.track)
            play.assert_called_once_with(400)

    def test_queue_window_can_be_cleared_and_replaced(self):
        w = self.w
        w.add_to_queue(self.youtube_track('clear000001'))
        w.clear_queue()
        w.add_to_queue(self.youtube_track('clear000002'))
        self.settle_row_deletions()
        row = w.queue_list.itemWidget(w.queue_list.item(0))
        self.assertEqual(row.track['video_id'], 'clear000002')
        with patch.object(w, 'play_queue_index') as play:
            row.play_requested.emit(row.track)
            play.assert_called_once_with(0)
        row.remove_button.click()
        self.assertEqual(w.queue_tracks, [])
        self.assertEqual(w._queue_live_rows, {})

    def test_session_restores_duplicate_queue_positions_without_starting_audio(self):
        tracks = self.saved_local_session()
        with self.reopened_player() as w:
            self.assertEqual([t['queue_id'] for t in w.queue_tracks], [t['queue_id'] for t in tracks])
            self.assertEqual(w.current_queue_index, 1)
            self.assertEqual(w.current_track['url'], tracks[1]['url'])
            self.assertEqual(w._restored_playback['position'], 2600)
            self.assertEqual(w.position_label.text(), '00:02')
            self.assertEqual(w.duration_label.text(), '00:10')
            self.assertTrue(all(p.source().isEmpty() for p in w.players))
            self.assertEqual(w.player.playbackState(), m.QMediaPlayer.PlaybackState.StoppedState)
            self.assertIsNone(w.stream_worker)

    def test_resume_saved_session_seeks_real_media_before_making_it_audible(self):
        self.saved_local_session()
        with self.reopened_player() as w, \
             patch.object(w, 'prepare_next_track'), patch.object(w, 'ensure_following_track_prepared'):
            w.toggle_playback()
            wait_for(lambda: w.requested_track is None and w._restored_playback is None)
            self.assertGreater(w.player.position(), 2600)
            self.assertEqual(w.current_queue_index, 1)
            self.assertEqual(w.current_track['queue_id'], 'session-b')
            self.assertGreater(w.audio_output.volume(), 0)

    def test_checkpoint_updates_position_without_rewriting_large_queue_file(self):
        self.saved_local_session()
        w = self.w
        original = w.session_file.read_bytes()
        w.player.setPosition(4000)
        w.save_playback_checkpoint()
        saved = json.loads(w.settings.value('playback_checkpoint_json'))
        self.assertEqual(saved['position'], 4000)
        self.assertEqual(w.session_file.read_bytes(), original)
        with patch.object(w.settings, 'setValue') as set_value:
            w.save_playback_checkpoint()
            set_value.assert_not_called()

    def test_queue_reorder_is_saved_after_debounce(self):
        self.saved_local_session()
        w = self.w
        w.move_queue_index(0, 1)
        self.assertTrue(w.session_save_timer.isActive())
        wait_for(lambda: not w._session_queue_dirty)
        queue = json.loads(w.session_file.read_text(encoding='utf-8'))['queue']
        self.assertEqual([t['queue_id'] for t in queue], ['session-b', 'session-a', 'session-duplicate'])

    def test_session_save_failure_preserves_previous_file_and_can_retry(self):
        self.saved_local_session()
        w = self.w
        original = w.session_file.read_bytes()
        w.queue_tracks.reverse()
        w._session_queue_dirty = True
        with patch.object(Path, 'replace', side_effect=OSError('Disk unavailable')):
            w.save_playback_session()
        self.assertEqual(w.session_file.read_bytes(), original)
        self.assertTrue(w._session_queue_dirty)
        w.save_playback_session()
        self.assertFalse(w._session_queue_dirty)
        self.assertNotEqual(w.session_file.read_bytes(), original)

    def test_session_keeps_current_track_even_after_queue_is_cleared(self):
        self.start(self.local_track('orphan-session'))
        self.w.player.setPosition(2300)
        self.w.player.pause()
        self.w.clear_queue()
        self.w.save_playback_session()
        with self.reopened_player() as w:
            self.assertEqual(w.queue_tracks, [])
            self.assertEqual(w.current_track['title'], 'orphan-session')
            self.assertEqual(w.current_queue_index, -1)
            self.assertEqual(w._restored_playback['position'], 2300)

    def test_session_allowlist_removes_stream_urls_and_credentials(self):
        w = self.w
        track = {**self.youtube_track('persist0001'), 'queue_id': 'q',
                 'url': 'https://music.youtube.com/watch?v=persist0001&cookie=SECRET',
                 'stream_url': 'https://server.invalid/SECRET', 'headers': {'Cookie': 'SECRET'},
                 'cookie_file': '/SECRET/cookies.txt', 'authorization': 'SECRET'}
        w.queue_tracks = [track]
        w.current_track = track
        w._session_queue_dirty = True
        w.save_playback_session()
        saved = w.session_file.read_text(encoding='utf-8') + w.settings.value('playback_checkpoint_json')
        self.assertNotIn('SECRET', saved)
        queue = json.loads(w.session_file.read_text(encoding='utf-8'))['queue']
        self.assertEqual(queue[0]['url'], 'https://music.youtube.com/watch?v=persist0001')
        self.assertNotIn('stream_url', queue[0])

    def test_invalid_session_and_stale_checkpoint_do_not_resume_wrong_position(self):
        tracks = self.saved_local_session()
        w = self.w
        valid = w.session_file.read_text(encoding='utf-8')
        w.settings.setValue('playback_checkpoint_json', json.dumps({'revision': 'stale', 'position': 9000}))
        with self.reopened_player() as restored:
            self.assertEqual(restored.current_track['queue_id'], tracks[0]['queue_id'])
            self.assertEqual(restored._restored_playback['position'], 0)
        w.session_file.write_text('{broken JSON', encoding='utf-8')
        with self.reopened_player() as restored:
            self.assertEqual(restored.queue_tracks, [])
            self.assertIsNone(restored.current_track)
        w.session_file.write_text(valid, encoding='utf-8')
        w.settings.setValue('playback_checkpoint_json', '{broken checkpoint')
        with self.reopened_player() as restored:
            self.assertEqual(len(restored.queue_tracks), len(tracks))
            self.assertEqual(restored._restored_playback['position'], 0)

    def test_manual_track_selection_cancels_saved_resume_offset(self):
        self.saved_local_session()
        with self.reopened_player() as w, \
             patch.object(w, 'prepare_next_track'), patch.object(w, 'ensure_following_track_prepared'):
            track = self.local_track('new-manual-session')
            w.play_track(track, -1)
            wait_for(lambda: w.requested_track is None and w.current_track['url'] == track['url'])
            self.assertIsNone(w._restored_playback)
            self.assertLess(w.player.position(), 1200)

    def test_supermix_session_is_restored_only_when_user_resumes_with_auth(self):
        w = self.w
        track = {**self.youtube_track('persistmix1'), 'queue_id': 'native-position'}
        w.queue_tracks = [track]
        w.current_track = track
        w.queue_mode = 'supermix'
        w.supermix_session = {'mix_id': 'RDTMAK5uy_saved', 'anchor': 'anchor00001', 'seen': {'persistmix1'}}
        w._restored_playback = {'position': 4200, 'mode': 'supermix', 'supermix': w.supermix_session}
        w._session_queue_dirty = True
        w.save_playback_session()
        with self.reopened_player() as restored, \
             patch.object(restored, 'youtube_auth_kwargs', return_value={'cookie_file': 'unused'}), \
             patch.object(restored, 'start_stream_extraction') as extract:
            self.assertIsNone(restored.supermix_session)
            self.assertIsNone(restored.stream_worker)
            restored.toggle_playback()
            self.assertEqual(restored.supermix_session['mix_id'], 'RDTMAK5uy_saved')
            self.assertEqual(restored.supermix_session['anchor'], 'anchor00001')
            self.assertIn('persistmix1', restored.supermix_session['seen'])
            self.assertEqual(restored._requested_start_position, 4200)
            extract.assert_called_once()
            restored.toggle_playback()
            self.assertIsNone(restored.requested_track)
            self.assertIsNotNone(restored._restored_playback)

    def test_mini_player_reuses_audio_and_closing_it_restores_main_window(self):
        self.start(self.local_track('mini-audio'))
        w = self.w
        active = w.player
        w.show_mini_player()
        mini = w.mini_player
        app.processEvents()
        self.assertTrue(mini.isVisible())
        self.assertFalse(w.isVisible())
        self.assertTrue(mini.windowFlags() & m.Qt.WindowType.WindowStaysOnTopHint)
        self.assertEqual(len(w.findChildren(m.QMediaPlayer)), 2)
        self.assertIs(w.player, active)
        self.assertEqual(active.playbackState(), m.QMediaPlayer.PlaybackState.PlayingState)
        mini.close()
        app.processEvents()
        self.assertTrue(w.isVisible())
        self.assertFalse(mini.isVisible())
        self.assertIs(w.player, active)
        self.assertEqual(active.playbackState(), m.QMediaPlayer.PlaybackState.PlayingState)
        self.assertIsNotNone(w.settings.value('mini_geometry'))

    def test_mini_player_pause_resume_volume_seek_and_favorite_share_state(self):
        self.start(self.local_track('mini-controls'))
        w = self.w
        w.show_mini_player()
        mini = w.mini_player
        mini.play_button.click()
        self.assertEqual(w.player.playbackState(), m.QMediaPlayer.PlaybackState.PausedState)
        self.assertEqual(mini.status.text(), 'На паузе')
        mini.play_button.click()
        self.assertEqual(w.player.playbackState(), m.QMediaPlayer.PlaybackState.PlayingState)
        self.assertEqual(mini.status.text(), 'Сейчас играет')
        w.volume_slider.setValue(23)
        self.assertEqual(mini.volume_slider.value(), 23)
        mini.volume_slider.setValue(41)
        self.assertEqual(w.volume_slider.value(), 41)
        self.assertAlmostEqual(w.audio_output.volume(), .41, places=5)
        mini.seek_slider.setValue(3500)
        mini.seek_released()
        self.assertGreaterEqual(w.player.position(), 3500)
        mini.favorite_button.click()
        self.assertTrue(w.is_favorite(w.current_track))
        self.assertEqual(mini.favorite_button.icon().cacheKey(), w.bottom_favorite_button.icon().cacheKey())

    def test_mini_player_next_previous_actions_and_themes(self):
        w = self.w
        with patch.object(w, 'play_next') as next_track, patch.object(w, 'play_previous') as previous:
            w.show_mini_player()
            w.mini_player.next_button.click()
            w.mini_player.previous_button.click()
            next_track.assert_called_once()
            previous.assert_called_once()
        for theme in ('dark', 'light'):
            w.theme = theme
            w.apply_styles()
            self.assertEqual(w.mini_player.theme, theme)
            image = w.mini_player.grab().toImage()
            base = image.pixelColor(210, 195)
            self.assertEqual(base.alpha(), 255)
            self.assertTrue(base.lightness() < 100 if theme == 'dark' else base.lightness() > 180)

    def test_saved_session_is_visible_in_mini_without_starting_playback(self):
        self.saved_local_session()
        with self.reopened_player() as w:
            w.show_mini_player()
            self.assertEqual(w.mini_player.status.text(), 'Продолжить прослушивание')
            self.assertEqual(w.mini_player.position_label.text(), '00:02')
            self.assertTrue(w.player.source().isEmpty())

    def test_exit_with_mini_player_does_not_show_main_window_again(self):
        w = self.w
        w.show_mini_player()
        with patch.object(m.QApplication, 'quit') as quit_app:
            w.request_app_exit()
        self.assertFalse(w.mini_player.isVisible())
        self.assertFalse(w.isVisible())
        self.assertFalse(w.checkpoint_timer.isActive())
        quit_app.assert_called_once()

    def test_empty_mini_play_opens_full_player_without_an_error_dialog(self):
        self.w.show_mini_player()
        with patch.object(m.QMessageBox, 'information') as message:
            self.w.mini_player.play_button.click()
        self.assertTrue(self.w.isVisible())
        self.assertFalse(self.w.mini_player.isVisible())
        message.assert_not_called()

    def remote_playback_fixture(self):
        # Decode/play real WAV files while supplying controlled network failures.
        # No external account or network is used by these recovery tests.
        w = self.w
        for method in ('prepare_next_track', 'ensure_following_track_prepared',
                       'maybe_refill_supermix'):
            fixture = patch.object(w, method)
            fixture.start()
            self.addCleanup(fixture.stop)
        self.start(self.local_track('remote-original'))
        fixture = patch.object(w, '_remote_playback', return_value=True)
        fixture.start()
        self.addCleanup(fixture.stop)
        track = {**self.youtube_track('recover0001'), 'queue_id': 'stable-position'}
        w.current_track = track
        w.queue_tracks = [track]
        w.current_queue_index = 0
        w.queue_mode = 'supermix'
        w.supermix_session = {'anchor': 'previous-song', 'waiting': False}
        w.player.setPosition(2600)
        w._last_progress_position = 2600
        w._last_duration = 10000
        w._playback_wanted = True
        return track

    def test_network_recovery_resumes_real_media_without_restarting_supermix(self):
        w = self.w
        track = self.remote_playback_fixture()
        session = w.supermix_session
        history = list(w.recent_tracks)
        w.save_stream(track['url'], 'https://example.invalid/expired', 'Old')
        with patch.object(w, 'start_stream_extraction') as extract, \
             patch.object(w, 'record_recent_track') as record:
            self.assertTrue(w.recover_current_stream('test disconnect'))
            extract.assert_called_once_with(track)
            self.assertIsNone(w.get_cached_stream(track['url']))
            self.assertEqual(w.requested_index, 0)
            fresh = self.local_track('remote-refreshed')
            w.stream_ready(track['url'], m.QUrl.fromLocalFile(fresh['url']).toString(), 'Fresh', .1)
            wait_for(lambda: w.requested_track is None)
            self.assertGreater(w.player.position(), 2600)
            self.assertEqual(w.current_track, track)
            self.assertEqual(w.current_queue_index, 0)
            self.assertIs(w.supermix_session, session)
            self.assertEqual(session['anchor'], 'previous-song')
            self.assertEqual(w.queue_tracks, [track])
            self.assertEqual(w.recent_tracks, history)
            record.assert_not_called()
            self.assertIsNone(w._network_recovery)
            self.assertEqual(w._network_recovery_attempts, 1)

    def test_shortened_remote_duration_cannot_advance_at_the_middle_for_either_service(self):
        w = self.w
        track = self.remote_playback_fixture()
        track['duration'] = 10
        for source in ('youtube', 'soundcloud'):
            with self.subTest(source=source), patch.object(w.player, 'duration', return_value=5000), \
                 patch.object(w, 'handle_track_finished') as advance, \
                 patch.object(w, 'start_stream_extraction') as extract:
                track['source'] = source
                w.current_track = track
                w.player.setSource(m.QUrl.fromLocalFile(self.local_track('duration-reopen')['url']))
                w.player.play()
                w._network_recovery_attempts = 0
                w.on_slot_duration(w.active_slot, 5000)
                self.assertEqual(w.playback_duration_ms(), 10000)
                self.assertEqual(w.seek_slider.maximum(), 10000)
                w.on_slot_position(w.active_slot, 4800)
                self.assertFalse(w._finish_transition_pending)
                w.on_slot_status(w.active_slot, m.QMediaPlayer.MediaStatus.EndOfMedia)
                extract.assert_called_once_with(track)
                self.assertEqual(w._network_recovery['duration'], 10000)
                self.assertEqual(w._network_recovery['position'], 4800)
                advance.assert_not_called()
                w.cancel_pending_request(cancel_supermix=False)

    def test_watchdog_still_recovers_when_qt_claims_a_shorter_duration(self):
        w = self.w
        track = self.remote_playback_fixture()
        track['duration'] = 10
        w._last_duration = 5000
        w._last_progress_position = 5000
        w._last_progress_at = time.monotonic() - 20
        with patch.object(w, 'recover_current_stream') as recover:
            w.check_playback_health()
            recover.assert_called_once()

    def test_recovery_seek_uses_full_duration_not_partial_qt_duration(self):
        w = self.w
        track = self.remote_playback_fixture()
        track['duration'] = 10
        w._last_progress_position = 7000
        with patch.object(w, 'start_stream_extraction'):
            w.recover_current_stream('truncated stream')
        slot = w.idle_slot()
        media = m.QUrl('https://example.invalid/refreshed')
        w.pending_slot = slot
        w.pending_media_url = media
        with patch.object(w.players[slot], 'source', return_value=media), \
             patch.object(w.players[slot], 'duration', return_value=5000), \
             patch.object(w.players[slot], 'isSeekable', return_value=True), \
             patch.object(w.players[slot], 'setPosition') as seek:
            w._apply_recovery_seek(slot)
            seek.assert_called_once_with(7000)
        self.assertEqual(w._network_recovery['position'], 7000)

    def test_extracted_duration_updates_request_and_queue_without_signed_urls(self):
        w = self.w
        track = {**self.youtube_track('metadata001'), 'queue_id': 'stable'}
        w.requested_track = dict(track)
        w.queue_tracks = [dict(track)]
        worker = m.StreamWorker(track)
        metadata = QSignalSpy(worker.metadata_ready)
        events = []
        worker.metadata_ready.connect(lambda data: (events.append('metadata'), w.accept_stream_metadata(track['url'], data)))
        worker.stream_ready.connect(lambda *_args: events.append('stream'))
        info = {'url': 'https://r1.googlevideo.com/videoplayback?sig=PRIVATE',
                'duration': 180, 'title': 'Test', 'format_id': '140', 'protocol': 'https'}
        with patch.object(worker, '_extract', return_value=info):
            worker.run()
        self.assertEqual(events, ['metadata', 'stream'])
        self.assertEqual(w.requested_track['duration'], 180)
        self.assertEqual(w.queue_tracks[0]['duration'], 180)
        self.assertEqual(w.queue_tracks[0]['queue_id'], 'stable')
        self.assertEqual(metadata[0][0]['hostname'], 'r1.googlevideo.com')
        self.assertNotIn('PRIVATE', str(metadata[0]))

    def test_recovery_format_selector_chooses_an_alternative_and_keeps_single_format_tracks_playable(self):
        for source, format_id in (('youtube', '140'), ('soundcloud', 'http_mp3_128')):
            with self.subTest(source=source):
                track = dict(self.youtube_track('format00001'), source=source)
                worker = m.StreamWorker(track, avoid_format_id=format_id)
                with patch.object(worker, '_extract', return_value={'url': 'https://example.invalid/audio'}) as extract:
                    worker.run()
                options = extract.call_args.args[0]
                self.assertFalse(options['nocheckcertificate'])
                formats = [
                    {'format_id': format_id, 'url': 'https://example.invalid/old', 'acodec': 'aac',
                     'vcodec': 'none', 'ext': 'm4a', 'protocol': 'https', 'abr': 128},
                    {'format_id': '251', 'url': 'https://example.invalid/new', 'acodec': 'opus',
                     'vcodec': 'none', 'ext': 'webm', 'protocol': 'https', 'abr': 160},
                ]
                with m.YoutubeDL({'quiet': True}) as downloader:
                    selector = downloader.build_format_selector(options['format'])
                    selected = list(selector({'formats': formats, 'has_merged_format': False, 'incomplete_formats': False}))
                    self.assertEqual(selected[0]['format_id'], '251')
                    selected = list(selector({'formats': formats[:1], 'has_merged_format': False, 'incomplete_formats': False}))
                    self.assertEqual(selected[0]['format_id'], format_id)

    def test_network_recovery_seek_event_alone_cannot_commit_playback(self):
        w = self.w
        self.remote_playback_fixture()
        with patch.object(w, 'start_stream_extraction'), \
             patch.object(w, 'commit_switch') as commit:
            w.recover_current_stream('test')
            slot = w.idle_slot()
            url = m.QUrl.fromLocalFile(self.local_track('seek-gate')['url'])
            w.players[slot].setSource(url)
            w.pending_slot = slot
            w.pending_media_url = url
            w.pending_position_seen = False
            w._recovery_seek_applied = True
            for position in (0, 100, 2600):
                w.on_slot_position(slot, position)
            commit.assert_not_called()
            w.on_slot_position(slot, 2700)
            commit.assert_called_once()

    def test_stalled_network_watchdog_ignores_pause_selection_and_healthy_progress(self):
        w = self.w
        self.remote_playback_fixture()
        with patch.object(w, 'recover_current_stream') as recover:
            w._last_progress_at = time.monotonic() - 20
            w._playback_wanted = False
            w.check_playback_health()
            w._playback_wanted = True
            w.requested_track = self.youtube_track('another0001')
            w.check_playback_health()
            w.requested_track = None
            w.player.pause()
            w.check_playback_health()
            w.player.play()
            w.on_slot_position(w.active_slot, 2700)
            w.check_playback_health()
            recover.assert_not_called()
            w._last_progress_at = time.monotonic() - 20
            w.check_playback_health()
            recover.assert_called_once()
            # A freeze a couple of seconds before the end still needs recovery.
            recover.reset_mock()
            w._last_progress_position = 8000
            w.check_playback_health()
            recover.assert_called_once()

    def test_early_network_end_recovers_instead_of_marking_mix_song_completed(self):
        w = self.w
        track = self.remote_playback_fixture()
        with patch.object(w, 'start_stream_extraction') as extract, \
             patch.object(w, 'handle_track_finished') as advance:
            w.on_slot_status(w.active_slot, m.QMediaPlayer.MediaStatus.EndOfMedia)
            extract.assert_called_once_with(track)
            advance.assert_not_called()
            self.assertEqual(w.supermix_session['anchor'], 'previous-song')
            self.assertFalse(w._finish_transition_pending)

    def test_normal_end_still_advances_and_local_playback_never_recovers(self):
        self.start(self.local_track('normal-end'))
        w = self.w
        w._last_duration = 10000
        w._last_progress_position = 5000
        with patch.object(w, 'start_stream_extraction') as extract:
            self.assertFalse(w.recover_current_stream('local file'))
            extract.assert_not_called()
        w._last_progress_position = 10000
        with patch.object(w, 'handle_track_finished') as advance, \
             patch.object(w, 'recover_current_stream') as recover:
            w.on_slot_status(w.active_slot, m.QMediaPlayer.MediaStatus.EndOfMedia)
            wait_for(lambda: advance.call_count == 1)
            recover.assert_not_called()

    def test_active_network_error_and_retry_budget_do_not_skip_the_song(self):
        w = self.w
        self.remote_playback_fixture()
        with patch.object(w, 'start_stream_extraction') as extract, \
             patch.object(w, 'handle_track_finished') as advance:
            for attempt in range(w.MAX_STREAM_RECOVERIES):
                w.player.setSource(m.QUrl.fromLocalFile(self.local_track('budget-reopen')['url']))
                w.on_slot_error(w.active_slot, m.QMediaPlayer.Error.NetworkError, 'disconnected')
                self.assertEqual(w._network_recovery_attempts, attempt + 1)
                w.requested_track = None
                w._network_recovery = None
            w.player.setSource(m.QUrl.fromLocalFile(self.local_track('budget-reopen')['url']))
            w.on_slot_error(w.active_slot, m.QMediaPlayer.Error.NetworkError, 'disconnected again')
            self.assertEqual(extract.call_count, w.MAX_STREAM_RECOVERIES)
            self.assertFalse(w._playback_wanted)
            self.assertFalse(w.playback_watchdog.isActive())
            advance.assert_not_called()

    def test_stop_pause_or_manual_selection_cancels_network_recovery(self):
        w = self.w
        self.remote_playback_fixture()
        with patch.object(w, 'start_stream_extraction'):
            w.recover_current_stream('first')
            w.toggle_playback()
            self.assertIsNone(w.requested_track)
            self.assertIsNone(w._network_recovery)
            self.assertFalse(w._playback_wanted)
            w._playback_wanted = True
            w.recover_current_stream('second')
            w.stop_all()
            self.assertIsNone(w.requested_track)
            self.assertIsNone(w._network_recovery)
            self.assertFalse(w.playback_watchdog.isActive())
        self.start(self.local_track('manual-after-recovery'))
        self.assertEqual(w._network_recovery_attempts, 0)
        self.assertIsNone(w.supermix_session)

    def test_demux_error_releases_both_sources_and_late_errors_cannot_flood_or_cancel_recovery(self):
        w = self.w
        track = self.remote_playback_fixture()
        w.standby_key = 'standby'
        w.players[w.idle_slot()].setSource(m.QUrl.fromLocalFile(self.local_track('prefetch-release')['url']))
        with patch.object(w, 'start_stream_extraction') as extract, \
             patch.object(w, 'show_toast') as toast, self.assertLogs('aurora', level='INFO') as logs:
            w.on_slot_error(w.active_slot, m.QMediaPlayer.Error.FormatError, 'Demuxing failed')
            self.assertTrue(all(player.source().isEmpty() for player in w.players))
            self.assertEqual(w._network_recovery['position'], 2600)
            for _ in range(200):
                w.on_slot_error(w.active_slot, m.QMediaPlayer.Error.FormatError, 'Demuxing failed')
                w.on_slot_status(w.active_slot, m.QMediaPlayer.MediaStatus.EndOfMedia)
                w.on_slot_position(w.active_slot, 0)
            extract.assert_called_once_with(track)
            toast.assert_not_called()
            self.assertEqual(w._last_progress_position, 2600)
            self.assertIsNotNone(w.requested_track)
        self.assertEqual(sum('Ошибка Qt слота' in line for line in logs.output), 1)

    def test_failed_recovery_checkpoint_and_manual_play_keep_interrupted_position(self):
        w = self.w
        track = self.remote_playback_fixture()
        with patch.object(w, 'start_stream_extraction'):
            w.recover_current_stream('disconnect')
            w.stream_error(track['url'], 'network unavailable')
        w.save_playback_checkpoint()
        checkpoint = json.loads(w.settings.value('playback_checkpoint_json'))
        self.assertEqual(checkpoint['position'], 2600)
        self.assertTrue(w.player.source().isEmpty())
        with patch.object(w, 'play_track') as play:
            w.toggle_playback()
            play.assert_called_once_with(track, 0, start_position=2600)
        w.stop_all()
        checkpoint = json.loads(w.settings.value('playback_checkpoint_json'))
        self.assertEqual(checkpoint['position'], 0)

    def test_error_in_previous_song_does_not_cancel_the_user_selected_next_song(self):
        w = self.w
        self.remote_playback_fixture()
        next_track = self.local_track('next-after-error')
        slot = w.idle_slot()
        with patch.object(w.players[slot], 'play'):
            w.play_track(next_track, -1)
            w.on_slot_error(w.active_slot, m.QMediaPlayer.Error.FormatError, 'Demuxing failed')
            self.assertEqual(w.requested_track['url'], next_track['url'])
            self.assertEqual(w.pending_slot, slot)
            self.assertTrue(w.player.source().isEmpty())
        w.players[slot].play()
        wait_for(lambda: w.current_track['url'] == next_track['url'] and w.requested_track is None)

    def test_truncated_http_audio_recovers_on_a_new_connection_at_the_saved_position(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        w = self.w
        track = self.remote_playback_fixture()
        track['duration'] = 10
        payload = Path(self.local_track('http-recovery')['url']).read_bytes()
        w.PLAYBACK_STALL_SECONDS = 1
        cut = threading.Event()
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args): pass
            def do_GET(self):
                if self.path == '/broken' and cut.is_set():
                    self.send_error(503)
                    return
                value = self.headers.get('Range', 'bytes=0-').removeprefix('bytes=')
                start, _, end = value.partition('-')
                start = int(start or 0)
                end = min(int(end) if end else len(payload) - 1, len(payload) - 1)
                data = payload[start:end + 1]
                self.send_response(206 if 'Range' in self.headers else 200)
                self.send_header('Content-Type', 'audio/wav')
                self.send_header('Accept-Ranges', 'bytes')
                self.send_header('Content-Length', str(len(data)))
                if 'Range' in self.headers:
                    self.send_header('Content-Range', f'bytes {start}-{end}/{len(payload)}')
                self.end_headers()
                try:
                    if self.path == '/broken':
                        self.wfile.write(data[:len(data) // 3])
                        self.wfile.flush()
                        self.close_connection = True
                    else:
                        self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError):
                    pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        def refresh(_track):
            w.start_pending_media(m.QUrl(base + '/full'), 'test reconnect')
        try:
            with patch.object(w, 'start_stream_extraction', side_effect=refresh) as extract:
                w.requested_track = dict(track)
                w.requested_index = 0
                w.request_started = time.perf_counter()
                w.start_pending_media(m.QUrl(base + '/broken'), 'test truncated HTTP')
                wait_for(lambda: w.requested_track is None and w.player.source().path() == '/broken', seconds=8)
                wait_for(lambda: w.player.position() >= 500)
                initial_position = w.player.position()
                cut.set()
                # Windows in the supplied log reports FormatError repeatedly. Linux
                # with a disconnected audio output may keep its clock advancing
                # after early EOF, so inject that exact callback on real HTTP media.
                w.on_slot_error(w.active_slot, m.QMediaPlayer.Error.FormatError, 'Demuxing failed')
                wait_for(lambda: w.requested_track is None and w.player.source().path() == '/full', seconds=8)
                self.assertGreater(w.player.position(), initial_position)
                self.assertEqual(w.current_track['queue_id'], track['queue_id'])
                self.assertEqual(extract.call_count, 1)
                self.assertIsNone(w._network_recovery)
        finally:
            cut.set()
            w.stop_all()
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_soundcloud_search_and_artwork_reuse_the_stream_extractor_client_id_cache(self):
        from yt_dlp.extractor.soundcloud import SoundcloudSearchIE
        search = m.SearchWorker('cache test', 'soundcloud', 'relevance', limit=3)
        with patch.object(m, 'YoutubeDL') as constructor:
            constructor.return_value.__enter__.return_value.extract_info.return_value = {'entries': []}
            search._fetch(3)
            options = constructor.call_args.args[0]
        self.assertIsNone(options['cachedir'])
        artwork = m.TrackArtworkWorker({'source': 'soundcloud', 'url': 'https://soundcloud.com/test/song'})
        with patch.object(m, 'YoutubeDL') as constructor:
            constructor.return_value.__enter__.return_value.extract_info.return_value = {'thumbnail': 'https://example.invalid/cover.jpg'}
            artwork.run()
            self.assertIsNone(constructor.call_args.args[0]['cachedir'])
        with patch.dict(os.environ, {'XDG_CACHE_HOME': str(self.test_path / 'extractor-cache')}):
            with m.YoutubeDL({'quiet': True}) as seed:
                seed.cache.store('soundcloud', 'client_id', 'A' * 32)
            with m.YoutubeDL(options) as downloader:
                extractor = SoundcloudSearchIE(downloader)
                with patch.object(extractor, '_update_client_id', side_effect=AssertionError('unnecessary webpage request')):
                    extractor._initialize_pre_login()
                self.assertEqual(extractor._CLIENT_ID, 'A' * 32)

    def test_failed_recovery_does_not_retry_forever_or_skip_track(self):
        w = self.w
        track = self.remote_playback_fixture()
        with patch.object(w, 'start_stream_extraction') as extract:
            w.recover_current_stream('test')
            w.stream_error(track['url'], 'test network failure')
            w.check_playback_health()
            self.assertIsNone(w.requested_track)
            self.assertIsNone(w._network_recovery)
            self.assertFalse(w._playback_wanted)
            extract.assert_called_once()

    def test_new_track_selection_discards_pending_recovery_position(self):
        w = self.w
        track = self.remote_playback_fixture()
        slot = w.idle_slot()
        with patch.object(w, 'start_stream_extraction'), \
             patch.object(w.players[slot], 'play'):
            w.recover_current_stream('disconnect')
            fresh = m.QUrl.fromLocalFile(self.local_track('pending-recovery')['url'])
            w.stream_ready(track['url'], fresh.toString(), 'Fresh', .1)
            self.assertIsNotNone(w._network_recovery)
            self.assertEqual(w.pending_slot, slot)
        manual = self.local_track('manual-selection')
        self.start(manual)
        self.assertIsNone(w._network_recovery)
        self.assertIsNone(w.supermix_session)
        self.assertEqual(w.current_track, manual)
        self.assertLess(w.player.position(), 1500)

    def test_recovery_timeout_does_not_loop_or_restart_at_beginning(self):
        w = self.w
        track = self.remote_playback_fixture()
        w.PENDING_MEDIA_TIMEOUT_MS = 25
        slot = w.idle_slot()
        with patch.object(w, 'start_stream_extraction') as extract, \
             patch.object(w.players[slot], 'play'):
            w.recover_current_stream('disconnect')
            fresh = m.QUrl.fromLocalFile(self.local_track('recovery-never-starts')['url'])
            w.stream_ready(track['url'], fresh.toString(), 'Fresh', .1)
            wait_for(lambda: w.requested_track is None)
            self.assertIsNone(w._network_recovery)
            self.assertFalse(w._playback_wanted)
            self.assertFalse(w.pending_media_timer.isActive())
            extract.assert_called_once()

    def test_latest_search_selection_starts_before_cancelled_extraction_finishes(self):
        w = self.w
        tracks = [self.youtube_track('select0000' + str(i)) for i in range(3)]
        started = {track['url']: threading.Event() for track in tracks}
        release = {track['url']: threading.Event() for track in tracks}
        opened = []
        workers = []
        def controlled_extract(worker, options):
            started[worker.track['url']].set()
            release[worker.track['url']].wait(5)
            return {'url': 'https://example.invalid/' + worker.track['video_id'], 'title': 'Test'}
        def opened_media(url, origin):
            opened.append(url.toString())
            w.pending_slot = w.idle_slot()
        with patch.object(m.StreamWorker, '_extract', controlled_extract), \
             patch.object(w, 'start_pending_media', side_effect=opened_media):
            try:
                w.play_track(tracks[0], -1)
                wait_for(started[tracks[0]['url']].is_set)
                workers.append(w.stream_worker)
                w.play_track(tracks[1], -1)
                wait_for(started[tracks[1]['url']].is_set)
                workers.append(w.stream_worker)
                w.play_track(tracks[2], -1)
                self.assertEqual(len(w._stream_workers), 2)
                self.assertFalse(started[tracks[2]['url']].is_set())
                release[tracks[0]['url']].set()
                wait_for(started[tracks[2]['url']].is_set)
                workers.append(w.stream_worker)
                # Simulate a queued success from a superseded request.
                workers[1].stream_ready.emit('https://example.invalid/stale', 'Stale', 1)
                app.processEvents()
                self.assertEqual(opened, [])
                release[tracks[2]['url']].set()
                wait_for(lambda: len(opened) == 1)
                self.assertTrue(opened[0].endswith(tracks[2]['video_id']))
                release[tracks[1]['url']].set()
                wait_for(lambda: not w._stream_workers)
                self.assertEqual(len(opened), 1)
            finally:
                w.cancel_pending_request()
                for event in release.values():
                    event.set()
                for worker in workers:
                    try:
                        worker.wait(6000)
                    except RuntimeError:
                        pass  # Already deleted after finished.
                app.processEvents()

    def test_card_hover_has_no_animation_tail_and_reuses_scaled_cover(self):
        card = self.w.start_cards[1]
        self.w.resize(1380, 900)
        app.processEvents()
        card.grab()
        initial = card._scaled_cover[1].cacheKey()
        card.enterEvent(QEnterEvent(m.QPointF(10, 10), m.QPointF(10, 10), m.QPointF(10, 10)))
        self.assertEqual(card._hover, 1)
        self.assertFalse(card._hover_animation.state() == QAbstractAnimation.State.Running)
        card.grab()
        self.assertEqual(card._scaled_cover[1].cacheKey(), initial)
        card.leaveEvent(QEvent(QEvent.Type.Leave))
        self.assertEqual(card._hover, 0)
        self.assertFalse(card._hover_animation.state() == QAbstractAnimation.State.Running)
        replacement = m.QPixmap(1024, 1024)
        replacement.fill(m.QColor('red'))
        card.set_cover(replacement)
        card.grab()
        self.assertNotEqual(card._scaled_cover[1].cacheKey(), initial)

    def test_fade_uses_elapsed_time_and_volume_changes_keep_balance(self):
        self.start(self.local_track('old-fade'))
        old = self.w.active_slot
        self.w.fade_duration_ms = 300
        self.start(self.local_track('new-fade'))
        # Delay the next timer callback and change settings during the transition.
        self.w.fade_started_at = 100.0
        self.w.fade_duration_ms = 3000
        with patch.object(m.time, 'monotonic', return_value=100.15):
            self.w.fade_step()
            self.assertAlmostEqual(self.w.audio_output.volume(), self.w.volume / 2, places=4)
            self.assertAlmostEqual(self.w.audio_outputs[old].volume(), self.w.volume / 2, places=4)
            self.w.set_volume(40)
            self.assertAlmostEqual(self.w.audio_output.volume(), 0.2, places=4)
            self.assertAlmostEqual(self.w.audio_outputs[old].volume(), 0.2, places=4)
        # A late callback completes immediately, without replaying missed steps.
        with patch.object(m.time, 'monotonic', return_value=100.7):
            self.w.fade_step()
        self.assertFalse(self.w.fade_timer.isActive())
        self.assertTrue(self.w.players[old].source().isEmpty())
        self.assertAlmostEqual(self.w.audio_output.volume(), 0.4, places=4)

    def test_fade_default_and_legacy_settings_migration(self):
        self.assertEqual(self.w.fade_duration_ms, 300)
        self.w.settings.clear()
        self.w.settings.setValue('fade_steps', 60)
        other = m.MusicPlayer()
        try:
            self.assertEqual(other.fade_duration_ms, 1800)
            other.save_preferences()
            self.assertEqual(other.settings.value('fade_duration_ms', type=int), 1800)
        finally:
            other._force_exit = True
            other.close()
        self.w.settings.setValue('fade_duration_ms', 450)
        self.w.settings.setValue('fade_steps', 70)
        other = m.MusicPlayer()
        try:
            self.assertEqual(other.fade_duration_ms, 450)
        finally:
            other._force_exit = True
            other.close()


class NativeSupermix(unittest.TestCase):
    MIX_ID = 'RDTMAK5uy_personal_account_mix'

    @staticmethod
    def entry(video_id, **extra):
        return dict(videoId=video_id, title='Song ' + video_id,
                    artists=[{'name': 'Artist'}], length='3:25',
                    thumbnail=[{'url': 'https://i.ytimg.com/cover.jpg'}], **extra)

    def collect(self, entries, *, home=None, **kwargs):
        worker = m.SupermixWorker('file', **kwargs)
        ready, failed = QSignalSpy(worker.result_ready), QSignalSpy(worker.failed)
        with patch('ytmusicapi.YTMusic') as factory, patch.object(worker, '_auth_headers', return_value={'cookie': 'fixture'}):
            factory.return_value.get_home.return_value = home if home is not None else [
                {'contents': [{'playlistId': self.MIX_ID, 'title': 'My Supermix',
                               'thumbnails': [{'url': 'https://lh3.googleusercontent.com/cover=w544-h544'}]}]}]
            if isinstance(entries, Exception):
                factory.return_value.get_watch_playlist.side_effect = entries
            else:
                factory.return_value.get_watch_playlist.return_value = {'tracks': entries}
            worker.run()
        return worker, ready, failed, factory

    def test_discovers_account_supermix_across_shelves_and_keeps_its_order(self):
        home = [{'contents': [{'playlistId': 'RDCLAK5uy_editorial', 'title': 'My Supermix'}]},
                {'contents': [{'playlistId': 'RDTMAK5uy_daily', 'title': 'My Mix 1'}]},
                {'contents': [{'playlistId': self.MIX_ID, 'title': 'My Supermix'}]}]
        _, ready, failed, factory = self.collect([self.entry('familiar001', likeStatus='LIKE'),
                                                  self.entry('discovery01')], home=home)
        self.assertFalse(failed)
        self.assertEqual([t['video_id'] for t in ready[0][0]], ['familiar001', 'discovery01'])
        self.assertTrue(ready[0][0][0]['youtube_music_like'])
        self.assertFalse(ready[0][0][1].get('youtube_music_like'))
        self.assertEqual(ready[0][1]['mix_id'], self.MIX_ID)
        self.assertEqual(ready[0][0][0]['duration'], 205)
        factory.assert_called_once()
        self.assertEqual(factory.call_args.args[0], {'cookie': 'fixture'})
        self.assertEqual(factory.call_args.kwargs['language'], 'en')
        client = factory.return_value
        client.get_home.assert_called_once_with(limit=20)
        client.get_watch_playlist.assert_called_once_with(playlistId=self.MIX_ID, limit=25)
        client.add_history_item.assert_not_called()
        client.rate_song.assert_not_called()

    def test_native_cover_is_returned(self):
        _, ready, failed, _ = self.collect([self.entry('familiar001')])
        self.assertFalse(failed)
        self.assertIn('googleusercontent.com', ready[0][1]['cover_url'])

    def test_refill_retains_mix_and_uses_last_finished_anchor(self):
        _, ready, failed, factory = self.collect([self.entry('new00000001')],
                                                mix_id=self.MIX_ID, anchor='lastgood001')
        self.assertFalse(failed)
        self.assertEqual(len(ready), 1)
        factory.return_value.get_home.assert_not_called()
        factory.return_value.get_watch_playlist.assert_called_once_with(
            playlistId=self.MIX_ID, videoId='lastgood001', radio=True, limit=25)

    def test_refill_without_completed_track_keeps_mix(self):
        _, _, failed, factory = self.collect([self.entry('new00000001')], mix_id=self.MIX_ID)
        self.assertFalse(failed)
        factory.return_value.get_watch_playlist.assert_called_once_with(
            playlistId=self.MIX_ID, radio=True, limit=25)

    def test_filters_unavailable_disliked_duplicates_and_already_served_tracks(self):
        entries = [self.entry('previous001'), self.entry('blocked0001'), self.entry('hidden00001', likeStatus='DISLIKE'),
                   self.entry('private0001', isAvailable=False), self.entry('unplayable1', isPlayable=False),
                   self.entry('allowed0001', likeStatus='LIKE'), self.entry('allowed0001'), {}]
        _, ready, failed, _ = self.collect(entries, mix_id=self.MIX_ID, excluded_ids={'previous001', 'blocked0001'})
        self.assertFalse(failed)
        self.assertEqual([t['video_id'] for t in ready[0][0]], ['allowed0001'])

    def test_missing_native_mix_does_not_fall_back_to_track_radio(self):
        _, ready, failed, factory = self.collect([], home=[{'contents': [
            {'playlistId': 'RDTMAK5uy_daily', 'title': 'My Mix 1'}]}])
        self.assertFalse(ready)
        self.assertIn('не найден My Supermix', failed[0][0])
        factory.return_value.get_watch_playlist.assert_not_called()

    def test_empty_initial_is_error_but_empty_refill_is_retryable_result(self):
        _, ready, failed, _ = self.collect([])
        self.assertFalse(ready)
        self.assertEqual(len(failed), 1)
        _, ready, failed, _ = self.collect([], mix_id=self.MIX_ID)
        self.assertFalse(failed)
        self.assertEqual(ready[0][0], [])

    def test_failure_does_not_leak_server_response_or_credentials(self):
        _, ready, failed, _ = self.collect(RuntimeError('HTTP 403 cookie=private-fixture'))
        self.assertFalse(ready)
        self.assertEqual(len(failed), 1)
        self.assertNotIn('private-fixture', failed[0][0])
        self.assertIn('cookies', failed[0][0])

    def test_cancel_before_start_and_during_request_discards_results(self):
        worker = m.SupermixWorker('file')
        worker.cancel()
        with patch('ytmusicapi.YTMusic') as factory:
            worker.run()
            factory.assert_not_called()
        worker = m.SupermixWorker('file', mix_id=self.MIX_ID)
        ready, failed = QSignalSpy(worker.result_ready), QSignalSpy(worker.failed)
        with patch.object(worker, '_auth_headers', return_value={}), patch('ytmusicapi.YTMusic') as factory:
            def response(**kwargs):
                worker.cancel()
                return {'tracks': [self.entry('fresh000001')]}
            factory.return_value.get_watch_playlist.side_effect = response
            worker.run()
        self.assertFalse(ready)
        self.assertFalse(failed)

    def test_file_and_browser_auth_reuse_filtered_cookie_headers(self):
        with tempfile.TemporaryDirectory(dir=state.name) as directory:
            path = Path(directory) / 'cookies.txt'
            path.write_text('# Netscape HTTP Cookie File\n'
                            '.youtube.com\tTRUE\t/\tTRUE\t0\t__Secure-3PAPISID\ttestfixture\n'
                            '.google.com\tTRUE\t/\tTRUE\t0\tSID\tnot-for-youtube\n')
            worker = m.SupermixWorker('file', cookie_file=str(path))
            headers = worker._auth_headers()
            self.assertEqual(headers['cookie'], '__Secure-3PAPISID=testfixture')
            self.assertTrue(headers['authorization'].startswith('SAPISIDHASH '))
            self.assertEqual(headers['origin'], 'https://music.youtube.com')
        worker = m.SupermixWorker('browser', browser_spec='firefox|test-profile')
        with patch.object(worker, '_cookies_from_browser', return_value='__Secure-3PAPISID=browserfixture') as read:
            headers = worker._auth_headers()
            read.assert_called_once()
            self.assertEqual(headers['cookie'], '__Secure-3PAPISID=browserfixture')
        with patch.object(worker, '_cookies_from_browser', return_value=''):
            with self.assertRaises(RuntimeError):
                worker._auth_headers()

    def test_network_calls_have_timeouts_keep_tls_and_honor_cancellation(self):
        import requests
        worker = m.SupermixWorker('file', mix_id=self.MIX_ID)
        ready = QSignalSpy(worker.result_ready)
        with patch.object(requests, 'Session') as session_factory, patch('ytmusicapi.YTMusic') as client_factory, \
             patch.object(worker, '_auth_headers', return_value={}):
            session = session_factory.return_value.__enter__.return_value
            original_request = session.request
            def recommend(**kwargs):
                session.request('POST', 'https://music.youtube.com/youtubei/v1/next')
                return {'tracks': [self.entry('fresh000001')]}
            client_factory.return_value.get_watch_playlist.side_effect = recommend
            worker.run()
            self.assertEqual(len(ready), 1)
            timeout = original_request.call_args.kwargs['timeout']
            self.assertGreater(timeout[0], 0)
            self.assertLessEqual(timeout[0], 3)
            self.assertLessEqual(timeout[1], 5)
            self.assertNotIn('verify', original_request.call_args.kwargs)
            worker.cancel()
            with self.assertRaises(TimeoutError):
                session.request('POST', 'https://music.youtube.com/youtubei/v1/next')


class HttpsVerification(unittest.TestCase):
    def search_options(self):
        worker = m.SearchWorker('test', 'youtube', 'relevance', 1)
        with patch.object(m, 'YoutubeDL') as downloader:
            downloader.return_value.__enter__.return_value.extract_info.return_value = {'entries': []}
            worker._fetch(1)
        return downloader.call_args.args[0]

    def test_search_keeps_certificate_verification_enabled(self):
        self.assertFalse(self.search_options().get('nocheckcertificate'))

    def test_explicit_ca_configuration_keeps_verification(self):
        with patch.dict(os.environ, {'SSL_CERT_FILE': '/configured/ca.pem', 'SSL_CERT_DIR': ''}):
            options = m.yt_dlp_tls_options()
            self.assertFalse(options['nocheckcertificate'])
            self.assertIn('no-certifi', options['compat_opts'])
        with patch.dict(os.environ, {'SSL_CERT_FILE': '', 'SSL_CERT_DIR': ''}):
            options = m.yt_dlp_tls_options()
            self.assertFalse(options['nocheckcertificate'])
            self.assertNotIn('no-certifi', options.get('compat_opts', set()))

    def test_search_transport_rejects_untrusted_certificate(self):
        import http.server
        import shutil
        import ssl
        import subprocess
        import threading
        openssl = shutil.which('openssl')
        if not openssl:
            self.skipTest('openssl is required to generate a local untrusted test certificate')
        with tempfile.TemporaryDirectory(dir=state.name) as directory:
            cert = Path(directory) / 'cert.pem'
            key = Path(directory) / 'key.pem'
            subprocess.run([openssl, 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                            '-keyout', str(key), '-out', str(cert), '-days', '1',
                            '-subj', '/CN=localhost', '-addext', 'subjectAltName=DNS:localhost'],
                           check=True, capture_output=True)
            class Handler(http.server.BaseHTTPRequestHandler):
                def do_GET(self):
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'verified')

                def log_message(self, *args):
                    pass

            server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(str(cert), str(key))
            server.socket = context.wrap_socket(server.socket, server_side=True)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                options = self.search_options()
                options.update(proxy='', socket_timeout=2)
                from yt_dlp.networking.exceptions import CertificateVerifyError
                with m.YoutubeDL(options) as downloader:
                    with self.assertRaises(CertificateVerifyError):
                        downloader.urlopen('https://localhost:' + str(server.server_port) + '/')
                # Trust this CA explicitly, preserving hostname and chain verification.
                with patch.dict(os.environ, {'SSL_CERT_FILE': str(cert), 'SSL_CERT_DIR': ''}):
                    trusted_options = self.search_options()
                    trusted_options.update(proxy='', socket_timeout=2)
                    self.assertFalse(trusted_options['nocheckcertificate'])
                    with m.YoutubeDL(trusted_options) as downloader:
                        with downloader.urlopen('https://localhost:' + str(server.server_port) + '/') as response:
                            self.assertEqual(response.status, 200)
                            self.assertEqual(response.read(), b'verified')
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)


if __name__ == '__main__':
    unittest.main(verbosity=2)
