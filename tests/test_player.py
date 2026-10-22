import importlib.util
import math
import os
from pathlib import Path
import struct
import tempfile
import time
import unittest
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
from PyQt6.QtTest import QSignalSpy
from PyQt6.QtCore import QEventLoop, QSettings
app = m.QApplication([])
app.setStyle('Fusion')
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
        self.w.deleteLater()
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
        self.assertEqual(self.w.start_cards_layout.count(), 2)
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
                         ['Мои лайки', 'Супермикс', 'Перемешать мои лайки'])
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

    def test_supermix_fetches_in_background_and_keeps_recommendations_unliked(self):
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
            self.assertEqual(factory.call_args.args[0], [liked])
            worker.start.assert_called_once()
            self.assertEqual(self.w.queue_tracks, [liked])
            self.assertFalse(self.w.start_cards[1].isEnabled())
            play.assert_not_called()
            self.w.on_supermix_ready(worker, [recommended], 'Recommendations ready')
            self.assertEqual(self.w.queue_mode, 'supermix')
            self.assertEqual(self.w.queue_tracks[0]['video_id'], 'freshsong001')
            self.assertFalse(self.w.queue_tracks[0].get('youtube_music_like'))
            self.assertFalse(self.w.is_youtube_music_liked(recommended))
            self.assertEqual(self.w.youtube_liked_tracks, [liked])
            play.assert_called_once_with(self.w.queue_tracks[0], 0)
            self.assertTrue(self.w.start_cards[1].isEnabled())

    def test_supermix_background_thread_delivers_recommendations_to_player(self):
        seed = dict(self.youtube_track('likedseed001'), artist='Artist')
        self.w.youtube_liked_tracks = [seed]
        with patch('ytmusicapi.YTMusic') as client, patch.object(self.w, 'play_track') as play:
            client.return_value.get_watch_playlist.return_value = {
                'tracks': [{'videoId': 'freshsong001', 'title': 'Fresh recommendation',
                            'artists': [{'name': 'Artist'}]}]
            }
            self.w.play_supermix()
            finished = QSignalSpy(self.w.supermix_worker.finished)
            wait_for(lambda: len(finished) == 1 and play.call_count == 1)
            self.assertEqual(self.w.queue_mode, 'supermix')
            self.assertEqual([track['video_id'] for track in self.w.queue_tracks], ['likedseed001', 'freshsong001'])
            self.assertIsNone(self.w.supermix_worker)
            self.assertEqual(self.w.youtube_liked_tracks, [seed])

    def test_stale_supermix_result_cannot_override_manual_playback(self):
        seed = self.youtube_track('likedseed001')
        self.w.youtube_liked_tracks = [seed]
        with patch.object(m, 'SupermixWorker') as factory:
            self.w.play_supermix()
            worker = factory.return_value
            self.w.stop_all()
            worker.cancel.assert_called()
            with patch.object(self.w, 'play_track') as play:
                self.w.on_supermix_ready(worker, [self.youtube_track('freshsong001')], 'Late')
                play.assert_not_called()
                self.assertEqual(self.w.queue_tracks, [])

    def test_supermix_rechecks_new_likes_and_dislikes_when_results_arrive(self):
        seed = self.youtube_track('likedseed001')
        fresh = self.youtube_track('freshsong001')
        now_liked = self.youtube_track('nowliked0001')
        now_disliked = self.youtube_track('nowhidden001')
        self.w.youtube_liked_tracks = [seed]
        with patch.object(m, 'SupermixWorker') as factory, patch.object(self.w, 'play_track'):
            self.w.play_supermix()
            self.w.youtube_liked_tracks.append(now_liked)
            self.w.disliked_track_keys.add('youtube|https://youtu.be/nowhidden001')
            self.w.on_supermix_ready(factory.return_value, [now_liked, now_disliked, fresh, fresh], 'Ready')
        self.assertEqual([track['video_id'] for track in self.w.queue_tracks], ['nowliked0001', 'freshsong001'])

    def test_supermix_error_preserves_queue_and_does_not_shuffle_likes(self):
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

    def test_supermix_without_likes_preserves_current_queue(self):
        existing = self.youtube_track('alreadyplay1')
        self.w.queue_tracks = [existing]
        with patch.object(m.QMessageBox, 'information') as message, \
             patch.object(self.w, 'start_search') as search, \
             patch.object(self.w, 'play_track') as play:
            self.w.play_supermix()
            message.assert_called_once()
            search.assert_not_called()
            play.assert_not_called()
        self.assertEqual(self.w.queue_tracks, [existing])

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


class SupermixRecommendations(unittest.TestCase):
    @staticmethod
    def liked(video_id, artist='Artist'):
        return {'source': 'youtube', 'video_id': video_id, 'artist': artist,
                'url': 'https://music.youtube.com/watch?v=' + video_id, 'title': video_id}

    @staticmethod
    def entry(video_id, artist='Artist', **extra):
        return dict(videoId=video_id, title='Recommended ' + video_id,
                    artists=[{'name': artist}], length='3:25',
                    thumbnail=[{'url': 'https://i.ytimg.com/cover.jpg'}], **extra)

    def collect(self, liked, responses, disliked=(), limit=30):
        worker = m.SupermixWorker(liked, disliked, limit=limit)
        ready, failed = QSignalSpy(worker.result_ready), QSignalSpy(worker.failed)
        with patch('ytmusicapi.YTMusic') as factory, patch.object(m.random, 'shuffle'):
            factory.return_value.get_watch_playlist.side_effect = responses
            worker.run()
            calls = factory.return_value.get_watch_playlist.call_args_list
        return ready, failed, calls

    def test_new_recommendations_exclude_known_and_blocked_tracks(self):
        liked = [self.liked('seed0000001', 'Artist'), self.liked('seed0000002', 'Beta')]
        responses = [
            {'tracks': [self.entry('seed0000001'), self.entry('blocked0001'), self.entry('fresh000001'),
                        self.entry('fresh000002'), self.entry('private0001', isAvailable=False)]},
            {'tracks': [self.entry('fresh000001'), self.entry('fresh000003'),
                        self.entry('serverhide1', likeStatus='DISLIKE'), self.entry('serverliked1', likeStatus='LIKE')]},
        ]
        ready, failed, calls = self.collect(liked, responses, {'blocked0001'})
        self.assertEqual(len(ready), 1)
        self.assertEqual(len(failed), 0)
        tracks = ready[0][0]
        self.assertEqual([track['video_id'] for track in tracks if not track.get('supermix_favorite')], ['fresh000001'])
        self.assertEqual(next(track['duration'] for track in tracks if not track.get('supermix_favorite')), 205)
        self.assertTrue(all(not track.get('youtube_music_like') for track in tracks))
        self.assertEqual({call.kwargs['videoId'] for call in calls}, {'seed0000001', 'seed0000002'})
        self.assertTrue(all(call.kwargs['radio'] is True for call in calls))

    def test_seeds_cover_different_artists_and_ignore_duplicate_video_ids(self):
        worker = m.SupermixWorker([self.liked('a0000000001', 'Alpha'), self.liked('a0000000002', 'Alpha'),
                                  self.liked('b0000000001', 'Beta'), self.liked('c0000000001', 'Gamma'),
                                  self.liked('a0000000001', 'Alpha')])
        with patch.object(m.random, 'shuffle'):
            seeds = worker._select_seeds()
        self.assertEqual({track['artist'] for track in seeds}, {'Alpha', 'Beta', 'Gamma'})
        self.assertEqual(len(seeds), 3)

    def test_mix_is_mostly_favorites_with_a_small_discovery_share(self):
        liked = [self.liked(f'favorite{i:04}') for i in range(40)]
        radio = {'tracks': [self.entry(f'discovery{i:03}') for i in range(20)]}
        ready, failed, _ = self.collect(liked, [radio, radio, radio])
        self.assertFalse(failed)
        tracks = ready[0][0]
        self.assertEqual(len(tracks), 30)
        self.assertEqual(sum(bool(track.get('supermix_favorite')) for track in tracks), 21)
        self.assertTrue(tracks[0].get('supermix_favorite'))
        self.assertEqual(len({track['video_id'] for track in tracks}), 30)
        self.assertFalse(any(not a.get('supermix_favorite') and not b.get('supermix_favorite')
                             for a, b in zip(tracks, tracks[1:])))

    def test_scarce_good_recommendations_are_replaced_with_more_favorites(self):
        liked = [self.liked(f'favorite{i:04}') for i in range(40)]
        radio = {'tracks': [self.entry('onlynew0001')]}
        ready, failed, _ = self.collect(liked, [radio, radio, radio])
        self.assertFalse(failed)
        tracks = ready[0][0]
        self.assertEqual(len(tracks), 30)
        self.assertEqual(sum(bool(track.get('supermix_favorite')) for track in tracks), 29)

    def test_unfamiliar_artist_from_one_radio_is_not_used_as_filler(self):
        liked = [self.liked(f'favorite{i:04}') for i in range(40)]
        first = {'tracks': [self.entry('unrelated01', artist='Unrelated pop artist')]
                           + [self.entry(f'nearby{i:05}') for i in range(11)]}
        other = {'tracks': [self.entry(f'nearby{i:05}') for i in range(11)]}
        ready, failed, _ = self.collect(liked, [first, other, other])
        self.assertFalse(failed)
        self.assertNotIn('unrelated01', {track['video_id'] for track in ready[0][0]})

    def test_discovery_artists_need_multiple_radios_and_stay_a_small_minority(self):
        liked = [self.liked(f'favorite{i:04}') for i in range(40)]
        first = {'tracks': [self.entry(f'close{i:05}') for i in range(4)]
                           + [self.entry('newartist01', artist='Related new artist')]
                           + [self.entry(f'close{i:05}') for i in range(4, 11)]}
        second = {'tracks': [self.entry('newartist02', artist='Related new artist')]
                            + [self.entry(f'close{i:05}') for i in range(11)]}
        ready, failed, _ = self.collect(liked, [first, second, second])
        self.assertFalse(failed)
        tracks = ready[0][0]
        strangers = [track for track in tracks if track['artist'] == 'Related new artist']
        self.assertLessEqual(len(strangers), 3)
        self.assertGreater(len(strangers), 0)
        self.assertGreaterEqual(sum(bool(t.get('supermix_favorite')) for t in tracks), 21)

    def test_seed_selection_favors_established_taste_over_a_single_outlier(self):
        liked = [self.liked(f'{artist}{i:06}', artist) for artist, count in
                 [('Alpha', 10), ('Beta', 8), ('Gamma', 6), ('Outlier', 1)] for i in range(count)]
        worker = m.SupermixWorker(liked)
        with patch.object(m.random, 'shuffle'):
            seeds = worker._select_seeds()
        self.assertEqual({track['artist'] for track in seeds}, {'Alpha', 'Beta', 'Gamma'})

    def test_topic_suffix_and_artist_spacing_do_not_hide_familiar_music(self):
        liked = [self.liked('favorite001', 'MF DOOM - Topic')]
        ready, failed, _ = self.collect(liked, [{'tracks': [self.entry('newdoom0001', artist='MFDOOM')]}])
        self.assertFalse(failed)
        self.assertIn('newdoom0001', {track['video_id'] for track in ready[0][0]})

    def test_partial_service_failure_still_returns_available_recommendations(self):
        ready, failed, _ = self.collect([self.liked('seed0000001', 'Alpha'), self.liked('seed0000002', 'Beta')],
                                        [RuntimeError('Timeout'), {'tracks': [self.entry('fresh000001', artist='Beta')]}])
        self.assertEqual(len(ready), 1)
        self.assertEqual(len(failed), 0)
        self.assertIn('Часть рекомендаций', ready[0][1])

    def test_service_failure_never_falls_back_to_liked_tracks(self):
        ready, failed, _ = self.collect([self.liked('seed0000001')], [RuntimeError('HTTP 403')])
        self.assertEqual(len(ready), 0)
        self.assertEqual(len(failed), 1)
        self.assertIn('403', failed[0][0])

    def test_already_known_recommendations_return_no_fake_supermix(self):
        ready, failed, _ = self.collect([self.liked('seed0000001')],
                                        [{'tracks': [self.entry('seed0000001')]}])
        self.assertEqual(len(ready), 0)
        self.assertEqual(len(failed), 1)

    def test_limit_and_cancellation(self):
        ready, failed, _ = self.collect([self.liked('seed0000001')],
                                        [{'tracks': [self.entry(f'new{i:08}') for i in range(20)]}], limit=7)
        self.assertLessEqual(len(ready[0][0]), 7)
        self.assertEqual(sum(bool(track.get('supermix_favorite')) for track in ready[0][0]), 1)
        self.assertFalse(failed)
        worker = m.SupermixWorker([self.liked('seed0000001')])
        worker.cancel()
        with patch('ytmusicapi.YTMusic') as factory:
            worker.run()
            factory.assert_not_called()

    def test_network_calls_have_timeouts_and_keep_tls_verification(self):
        import requests
        worker = m.SupermixWorker([self.liked('seed0000001')])
        ready = QSignalSpy(worker.result_ready)
        with patch.object(requests, 'Session') as session_factory, patch('ytmusicapi.YTMusic') as client_factory:
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
            self.assertLessEqual(timeout[0], 4)
            self.assertLessEqual(timeout[1], 7)
            self.assertNotIn('verify', original_request.call_args.kwargs)


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
