"""Playback regressions and real Chromium checks with a local player fixture."""

import base64
import io
import json
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import wave

os.environ.setdefault('QTWEBENGINE_CHROMIUM_FLAGS', '--disable-gpu --disable-dev-shm-usage')

import test_player as existing
from PyQt6.QtCore import QObject, QCoreApplication, QUrl, pyqtSignal
from PyQt6.QtTest import QSignalSpy
import youtube_music_backend as backend

app, m, wait_for = existing.app, existing.m, existing.wait_for


class FakePage(QObject):
    loadingChanged = pyqtSignal(object)
    renderProcessTerminated = pyqtSignal(object, int)
    LifecycleState = backend.QWebEnginePage.LifecycleState

    def __init__(self, profile, parent):
        super().__init__(parent)
        self._url = QUrl()
        self.scripts = []
        self.loads = []
        self.muted = True

    def settings(self):
        return self

    def setAttribute(self, *_):
        pass

    def setLifecycleState(self, *_):
        pass

    def setVisible(self, *_):
        pass

    def setAudioMuted(self, muted):
        self.muted = muted

    def url(self):
        return self._url

    def load(self, url):
        self._url = QUrl(url)
        self.loads.append(QUrl(url))

    def runJavaScript(self, script, callback=None):
        self.scripts.append((script, callback))


class FakeSession(QObject):
    prepared = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.profile = object()
        self.ready = True
        self._players = []
        self.signatures = []

    def configure(self, signature, loader=None):
        self.signatures.append(signature)

    def shutdown(self):
        for player in self._players:
            player.shutdown()


class FakeView(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)

    def setAttribute(self, *_):
        pass

    setFocusPolicy = resize = move = setPage = show = close = setAttribute


class PlaybackIntegration(unittest.TestCase):
    setUp = existing.PlayerChanges.setUp
    tearDown = existing.PlayerChanges.tearDown
    local_track = existing.PlayerChanges.local_track
    youtube_track = staticmethod(existing.PlayerChanges.youtube_track)
    start = existing.PlayerChanges.start

    def browser_fixture(self):
        for fixture in (patch.object(m, 'YouTubeMusicSession', FakeSession),
                        patch.object(backend, 'QWebEnginePage', FakePage),
                        patch.object(backend, 'QWebEngineView', FakeView),
                        patch.object(self.w, 'prepare_next_track'),
                        patch.object(self.w, 'ensure_following_track_prepared')):
            fixture.start()
            self.addCleanup(fixture.stop)

    def snapshot(self, player, seconds=1, state=1, generation=None):
        generation = player._generation if generation is None else generation
        player._snapshot(generation, {'token': str(generation),
                         'videoId': player.source().query().partition('v=')[2],
                         'state': state, 'position': seconds, 'duration': 180,
                         'seekSerial': player._seek_serial})

    def test_youtube_uses_official_player_and_keeps_previous_audio_until_progress(self):
        self.start(self.local_track('old-before-youtube'))
        previous = self.w.player
        self.browser_fixture()
        track = self.youtube_track('newtrack001')
        visible = {id(w) for w in app.topLevelWidgets() if w.isVisible()}
        with patch.object(m, 'StreamWorker') as extract:
            self.w.play_track(track, -1)
            extract.assert_not_called()
        slot = self.w.pending_slot
        player = self.w.players[slot]
        self.assertIsInstance(player, backend.YouTubeMusicPlayer)
        self.assertEqual(player.source().toString(), 'https://music.youtube.com/watch?v=newtrack001')
        self.assertIs(self.w.player, previous)
        self.assertEqual(previous.playbackState(), m.QMediaPlayer.PlaybackState.PlayingState)
        self.assertEqual(self.w.audio_outputs[slot].volume(), 0)
        self.w._native_players[slot].positionChanged.emit(500)
        self.assertIs(self.w.player, previous)
        self.snapshot(player, state=3)
        self.assertIs(self.w.player, previous)
        self.snapshot(player)
        self.assertIs(self.w.player, player)
        self.assertEqual(self.w.current_track['video_id'], 'newtrack001')
        self.assertEqual(visible, {id(w) for w in app.topLevelWidgets() if w.isVisible()})

    def test_fast_selection_and_stop_ignore_old_browser_callbacks(self):
        self.browser_fixture()
        first, second = self.youtube_track('first000001'), self.youtube_track('second00001')
        self.w.play_track(first, -1)
        player = self.w.players[self.w.pending_slot]
        stale_generation = player._generation
        self.w.play_track(second, -1)
        self.snapshot(player, generation=stale_generation)
        self.assertIsNone(self.w.current_track)
        self.assertEqual(self.w.requested_track['video_id'], 'second00001')
        self.snapshot(player)
        self.assertEqual(self.w.current_track['video_id'], 'second00001')
        self.w.stop_all()
        self.snapshot(player, seconds=2)
        self.assertEqual(player.playbackState(), m.QMediaPlayer.PlaybackState.StoppedState)
        self.assertTrue(player.page.muted)

    def test_changing_the_track_keeps_the_first_youtube_page_booting(self):
        self.browser_fixture()
        self.w.play_track(self.youtube_track('first000001'), -1)
        player = self.w.players[self.w.pending_slot]
        first_loads = list(player.page.loads)
        self.w.play_track(self.youtube_track('second00001'), -1)
        self.assertIs(self.w.players[self.w.pending_slot], player)
        self.assertEqual(player.page.loads, first_loads)
        self.snapshot(player)
        self.assertEqual(self.w.current_track['video_id'], 'second00001')

    def test_pause_resume_volume_and_position_restore_use_existing_controls(self):
        self.browser_fixture()
        self.w.play_track(self.youtube_track('restore0001'), -1, start_position=4200)
        player = self.w.players[self.w.pending_slot]
        self.snapshot(player, seconds=1)
        self.assertIsNotNone(self.w.requested_track)
        self.assertEqual(player._seek_position, 4200)
        self.snapshot(player, seconds=4.2)
        self.assertIsNotNone(self.w.requested_track)
        self.snapshot(player, seconds=4.5)
        self.assertIs(self.w.player, player)
        self.w.volume_slider.setValue(37)
        self.assertEqual(player._volume(), 37)
        self.w.play_button.click()
        self.assertFalse(player._want_playing)
        self.assertTrue(player.page.muted)
        self.snapshot(player, seconds=5, state=2)
        self.assertEqual(player.playbackState(), m.QMediaPlayer.PlaybackState.PausedState)
        self.w.play_button.click()
        self.assertTrue(player._want_playing)
        self.w.seek_slider.setValue(12000)
        self.w.seek_released()
        self.assertEqual(player._seek_position, 12000)

    def test_failure_retries_once_and_keeps_old_track_playing(self):
        self.start(self.local_track('old-during-error'))
        previous = self.w.player
        self.browser_fixture()
        self.w.play_track(self.youtube_track('failure0001'), -1)
        player = self.w.players[self.w.pending_slot]
        player._fail('YouTube unavailable')
        self.assertTrue(self.w.pending_refreshed)
        player._fail('YouTube unavailable again')
        self.assertIsNone(self.w.requested_track)
        self.assertIsNone(self.w.pending_slot)
        self.assertFalse(self.w.pending_media_timer.isActive())
        self.assertIs(self.w.player, previous)
        self.assertEqual(previous.playbackState(), m.QMediaPlayer.PlaybackState.PlayingState)
        self.assertTrue(player.source().isEmpty())

    def test_offline_youtube_keeps_native_decoder_and_invalid_id_does_not_extract(self):
        self.browser_fixture()
        track = self.youtube_track('offline0001')
        track['local_path'] = self.local_track('offline-copy')['url']
        self.start(track)
        self.assertIsInstance(self.w.player, m.QMediaPlayer)
        self.assertTrue(self.w.player.source().isLocalFile())
        previous = self.w.player
        with patch.object(m, 'StreamWorker') as extract:
            self.w.play_track({'source': 'youtube', 'url': 'https://youtube.com/watch?v=bad'}, -1)
            extract.assert_not_called()
        self.assertIs(self.w.player, previous)
        self.assertIsNone(self.w.requested_track)

    def test_native_slot_can_be_reused_after_youtube_and_old_events_are_ignored(self):
        self.browser_fixture()
        self.w.play_track(self.youtube_track('native00001'), -1)
        browser = self.w.players[self.w.pending_slot]
        self.snapshot(browser)
        self.start(self.local_track('native-after-youtube'))
        wait_for(lambda: not self.w.fade_timer.isActive())
        self.start(self.local_track('native-reuses-browser-slot'))
        wait_for(lambda: not self.w.fade_timer.isActive())
        native = self.w.player
        self.assertIsInstance(native, m.QMediaPlayer)
        browser.positionChanged.emit(42000)
        browser.errorOccurred.emit(m.QMediaPlayer.Error.ResourceError, 'stale')
        self.assertIs(self.w.player, native)
        self.assertEqual(self.w.current_track['title'], 'native-reuses-browser-slot')

    def test_end_advances_existing_queue_once(self):
        self.browser_fixture()
        first = dict(self.youtube_track('queue000001'), duration=240)
        second = self.local_track('next-in-queue')
        self.w.queue_tracks = [first, second, self.local_track('third-in-queue')]
        self.w.refresh_queue_list()
        self.w.play_track(first, 0)
        player = self.w.players[self.w.pending_slot]
        self.snapshot(player)
        with patch.object(self.w, 'play_queue_index', wraps=self.w.play_queue_index) as next_track:
            self.snapshot(player, seconds=179.5)
            self.snapshot(player, seconds=180, state=0)
            wait_for(lambda: self.w.current_queue_index == 1)
            self.assertEqual(self.w.current_track['url'], second['url'])
            next_track.assert_called_once_with(1)

    def test_missing_browser_dependency_does_not_fall_back_to_native_youtube_playback(self):
        self.start(self.local_track('old-without-browser'))
        previous = self.w.player
        self.browser_fixture()
        with patch.object(backend, 'QWebEngineProfile', None), \
             patch.object(m, 'StreamWorker') as extractor:
            self.w.play_track(self.youtube_track('missing0001'), -1)
            extractor.assert_not_called()
        self.assertIsNone(self.w.requested_track)
        self.assertIsNone(self.w.pending_slot)
        self.assertIs(self.w.player, previous)
        self.assertEqual(previous.playbackState(), m.QMediaPlayer.PlaybackState.PlayingState)

    def test_old_web_driver_is_rejected_without_a_native_youtube_fallback(self):
        self.browser_fixture()
        with patch.object(backend, 'WEB_DRIVER_PROTOCOL', 1), patch.object(m, 'StreamWorker') as extractor:
            self.w.play_track(self.youtube_track('outdated001'), -1)
        extractor.assert_not_called()
        self.assertIsNone(self.w.requested_track)
        self.assertIsNone(self.w.pending_slot)

    def test_youtube_does_not_use_an_old_cached_stream_url(self):
        self.browser_fixture()
        track = self.youtube_track('cached00001')
        self.w.save_stream(track['url'], 'https://example.invalid/old-audio.m4a', 'Old cache')
        with patch.object(m, 'StreamWorker') as extractor:
            self.w.play_track(track, -1)
            extractor.assert_not_called()
        player = self.w.players[self.w.pending_slot]
        self.assertIsInstance(player, backend.YouTubeMusicPlayer)
        self.assertEqual(player.source().host(), 'music.youtube.com')
        self.snapshot(player)
        self.assertIs(self.w.player, player)


class BrowserPlayerContract(unittest.TestCase):
    def setUp(self):
        self.session = backend.YouTubeMusicSession()
        self.player = backend.YouTubeMusicPlayer(self.session)
        self.session.configure(())
        self.page = self.player.page

    def tearDown(self):
        self.session.shutdown()
        self.player.deleteLater()
        self.session.deleteLater()
        QCoreApplication.sendPostedEvents(None, m.QEvent.Type.DeferredDelete)
        app.processEvents()

    def javascript(self, code):
        result = []
        self.page.runJavaScript(code, result.append)
        wait_for(lambda: bool(result))
        return result[0]

    def document(self, html):
        spy = QSignalSpy(self.page.loadFinished)
        self.page.setHtml(html, QUrl('https://music.youtube.com/watch?v=browser0001'))
        wait_for(lambda: bool(spy))
        self.assertTrue(spy[0][0])

    def desired(self, **changes):
        return dict(token='1', videoId='browser0001', volume=0, playing=True,
                    stopped=False, position=None, seekSerial=0, commandSerial=1, **changes)

    def poll(self, desired=None):
        return self.javascript(backend._PLAYER_SCRIPT.replace('__DESIRED__', json.dumps(desired or self.desired())))

    def test_driver_waits_for_readiness_navigates_and_stops_youtube_autoplay(self):
        self.document('''<ytmusic-player-bar></ytmusic-player-bar><script>
          window.calls=[]; window.id='oldtrack001'; window.ready=false;
          const api={isReady:()=>ready, setVolume:v=>calls.push(['volume',v]),
            getPlayerResponse:()=>({videoDetails:{videoId:id},playabilityStatus:{status:'OK'}}),
            getPlayerState:()=>1, getCurrentTime:()=>2, getDuration:()=>180,
            playVideo:()=>calls.push(['play']), pauseVideo:()=>calls.push(['pause'])};
          document.querySelector('ytmusic-player-bar').playerApi=api;
          document.addEventListener('yt-navigate',e=>{calls.push(['navigate',e.detail.endpoint.watchEndpoint.videoId]);id=e.detail.endpoint.watchEndpoint.videoId;});
        </script>''')
        self.assertEqual(self.poll()['phase'], 'api_not_ready')
        self.assertEqual(self.javascript('calls'), [])
        self.javascript('ready=true')
        self.assertEqual(self.poll()['phase'], 'waiting_video')
        self.assertIn(['navigate', 'browser0001'], self.javascript('calls'))
        response = self.poll()
        self.assertEqual(response['videoId'], 'browser0001')
        self.assertIn(['play'], self.javascript('calls'))
        self.javascript("id='autonext001'")
        self.assertTrue(self.poll()['ended'])
        self.assertEqual(self.javascript('calls.at(-1)'), ['pause'])

    def test_browser_has_a_desktop_viewport_without_presenting_a_window(self):
        self.document('<!doctype html><title>Offscreen YTM host</title>')
        self.assertEqual(self.javascript('[innerWidth, innerHeight, document.visibilityState]'), [1280, 720, 'visible'])
        self.assertTrue(self.player.view.testAttribute(m.Qt.WidgetAttribute.WA_DontShowOnScreen))
        self.assertEqual(self.player.view.focusPolicy(), m.Qt.FocusPolicy.NoFocus)

    def test_play_is_sent_before_the_player_publishes_video_metadata(self):
        self.document('''<ytmusic-player-bar></ytmusic-player-bar><script>
          window.calls=[]; window.id=''; window.pending='browser0001'; window.state=5;
          document.querySelector('ytmusic-player-bar').playerApi={isReady:()=>true,
            getPlayerResponse:()=>id?{videoDetails:{videoId:id}}:{}, getPlayerState:()=>state,
            getCurrentTime:()=>1, getDuration:()=>180, setVolume:()=>{},
            playVideo:()=>{calls.push('play');id=pending;state=1;}, pauseVideo:()=>{},
            seekTo:()=>{}};
          document.addEventListener('yt-navigate',e=>{pending=e.detail.endpoint.watchEndpoint.videoId;});
        </script>''')
        self.poll()
        self.poll()
        self.assertIn('play', self.javascript('calls'))
        self.assertEqual(self.poll()['videoId'], 'browser0001')

    def test_play_is_sent_when_an_ad_is_waiting_for_the_initial_play_command(self):
        self.document('''<ytmusic-player-bar></ytmusic-player-bar><ytmusic-popup-container></ytmusic-popup-container><script>
          window.calls=[];
          document.querySelector('ytmusic-popup-container').store={getState:()=>({player:{adPlaying:true}})};
          document.querySelector('ytmusic-player-bar').playerApi={isReady:()=>true,
            getPlayerResponse:()=>({videoDetails:{videoId:'advert00001'}}), getPlayerState:()=>2,
            getCurrentTime:()=>0, getDuration:()=>30, setVolume:()=>{},
            playVideo:()=>calls.push('play'), pauseVideo:()=>calls.push('pause'), seekTo:()=>{}};
        </script>''')
        self.poll()
        self.poll()
        self.assertIn('play', self.javascript('calls'))

    def test_video_data_supplies_the_id_when_player_response_has_no_details(self):
        self.document('''<ytmusic-player-bar></ytmusic-player-bar><script>
          document.querySelector('ytmusic-player-bar').playerApi={isReady:()=>true,
            getPlayerResponse:()=>({playabilityStatus:{status:'OK'}}),
            getVideoData:()=>({video_id:'browser0001'}), getPlayerState:()=>1,
            getCurrentTime:()=>1, getDuration:()=>180, setVolume:()=>{},
            playVideo:()=>{}, pauseVideo:()=>{}, seekTo:()=>{}};
        </script>''')
        self.assertEqual(self.poll()['videoId'], 'browser0001')

    def test_javascript_error_is_reported_instead_of_a_silent_wait(self):
        self.document('''<ytmusic-player-bar></ytmusic-player-bar><script>
          document.querySelector('ytmusic-player-bar').playerApi={isReady:()=>true,
            getPlayerResponse:()=>({videoDetails:{videoId:'browser0001'}}),
            getPlayerState:()=>{throw new Error('state-unavailable');}, playVideo:()=>{},
            setVolume:()=>{}};
        </script>''')
        response = self.poll()
        self.assertEqual(response['phase'], 'script_error')
        self.assertIn('state-unavailable', response['error'])

    def test_unresponsive_renderer_has_a_bounded_callback_timeout(self):
        self.document('<!doctype html><title>Unresponsive renderer fixture</title>')
        self.player._source = QUrl('https://music.youtube.com/watch?v=browser0001')
        self.player.JAVASCRIPT_TIMEOUT_MS = 25
        errors = QSignalSpy(self.player.errorOccurred)
        with patch.object(self.page, 'runJavaScript'):
            self.player.play()
            wait_for(lambda: len(errors) == 1)
        self.assertTrue(self.player._failed)
        self.assertIn('не ответил', errors[0][1])

    def test_successful_page_load_accepts_added_query_parameters(self):
        self.player._source = QUrl('https://music.youtube.com/watch?v=browser0001')
        info = SimpleNamespace(
            status=lambda: backend.QWebEngineLoadingInfo.LoadStatus.LoadSucceededStatus,
            url=lambda: QUrl('https://music.youtube.com/watch?v=browser0001&feature=share'),
            errorCode=lambda: 0)
        with patch.object(self.player, '_poll') as poll:
            self.player._loading_changed(info)
        self.assertTrue(self.player._document_ready)
        poll.assert_called_once()

    def test_other_host_redirect_is_reported_instead_of_an_endless_wait(self):
        self.player._source = QUrl('https://music.youtube.com/watch?v=browser0001')
        errors = QSignalSpy(self.player.errorOccurred)
        info = SimpleNamespace(
            status=lambda: backend.QWebEngineLoadingInfo.LoadStatus.LoadSucceededStatus,
            url=lambda: QUrl('https://www.youtube.com/premium'), errorCode=lambda: 0)
        self.player._loading_changed(info)
        self.assertEqual(len(errors), 1)
        self.assertTrue(self.player._failed)

    def test_waiting_stage_is_visible_in_the_diagnostic_log(self):
        self.document('<!doctype html><title>Player not initialized</title>')
        self.player._source = QUrl('https://music.youtube.com/watch?v=browser0001')
        with self.assertLogs('aurora', level='INFO') as capture:
            self.player.play()
            wait_for(lambda: self.player._last_phase == 'waiting_player')
        self.assertIn('stage=waiting_player', '\n'.join(capture.output))
        self.assertIn('viewport=1280x720', '\n'.join(capture.output))
        self.assertIn('не подготовился', self.player.startup_timeout_message())

    def test_real_hidden_chromium_audio_advances_pauses_seeks_and_stops(self):
        sound = io.BytesIO()
        with wave.open(sound, 'wb') as stream:
            stream.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
            stream.writeframes(b'\x00\x00' * 16000 * 8)
        data = base64.b64encode(sound.getvalue()).decode('ascii')
        self.document('''<audio id="audio" src="data:audio/wav;base64,'''+data+'''"></audio>
          <ytmusic-player-bar></ytmusic-player-bar><script>
          const audio=document.querySelector('audio');
          document.querySelector('ytmusic-player-bar').playerApi={
            isReady:()=>audio.readyState>=2,
            getPlayerResponse:()=>({videoDetails:{videoId:'browser0001'},playabilityStatus:{status:'OK'}}),
            getPlayerState:()=>audio.ended?0:audio.paused?2:1,
            getCurrentTime:()=>audio.currentTime, getDuration:()=>audio.duration,
            setVolume:v=>{audio.volume=v/100;}, playVideo:()=>audio.play(), pauseVideo:()=>audio.pause(),
            seekTo:s=>{audio.currentTime=s;}
          };</script>''')
        wait_for(lambda: self.javascript('audio.readyState') >= 2)
        self.player._source = QUrl('https://music.youtube.com/watch?v=browser0001')
        self.player._generation = 1
        self.player.play()
        self.player._timer.start()
        wait_for(lambda: self.player.position() > 200)
        self.assertEqual(self.player.duration(), 8000)
        self.assertTrue(self.player.isSeekable())
        self.player.pause()
        wait_for(lambda: self.javascript('audio.paused') is True)
        self.player.setPosition(3500)
        wait_for(lambda: self.javascript('audio.currentTime') >= 3.5)
        wait_for(lambda: self.player.position() >= 3500)
        self.player.play()
        wait_for(lambda: self.player.position() > 3500)
        self.player.stop()
        wait_for(lambda: self.javascript('audio.paused') is True)
        self.assertEqual(self.player.playbackState(), m.QMediaPlayer.PlaybackState.StoppedState)
        self.assertTrue(self.page.isAudioMuted())

    def test_end_does_not_repeat_without_a_new_play_command_and_ads_do_not_commit(self):
        self.document('''<ytmusic-player-bar></ytmusic-player-bar><ytmusic-popup-container></ytmusic-popup-container><script>
          window.calls=[]; window.state=1; window.ad=false;
          document.querySelector('ytmusic-popup-container').store={getState:()=>({player:{adPlaying:ad}})};
          document.querySelector('ytmusic-player-bar').playerApi={isReady:()=>true,
            setVolume:()=>{}, getPlayerResponse:()=>({videoDetails:{videoId:'browser0001'}}),
            getPlayerState:()=>state, getCurrentTime:()=>180, getDuration:()=>180,
            playVideo:()=>calls.push('play'), pauseVideo:()=>calls.push('pause'), seekTo:()=>calls.push('seek')};
        </script>''')
        self.poll()
        self.javascript('state=0;calls=[]')
        self.assertEqual(self.poll()['state'], 0)
        self.assertEqual(self.javascript('calls'), [])
        desired = self.desired()
        desired.update(commandSerial=2, seekSerial=1, position=0)
        self.assertEqual(self.poll(desired)['phase'], 'seeking')
        self.poll(desired)
        self.assertEqual(self.javascript('calls'), ['seek', 'play'])
        self.javascript('ad=true')
        self.assertEqual(self.poll(desired)['phase'], 'advertisement')

    def test_cookie_import_finishes_before_navigation_and_disconnect_clears_session(self):
        self.session.configure(('account',), lambda: 'SAPISID=local-test; __Secure-3PAPISID=local-secure-test')
        self.assertFalse(self.session.ready)
        wait_for(lambda: self.session.ready)
        self.assertTrue(self.session.profile.isOffTheRecord())
        self.session.clear_account()
        self.assertTrue(self.session.ready)
        self.assertIsNone(self.session._signature)


class YouTubeUrls(unittest.TestCase):
    def test_playback_reuses_youtube_consent_without_changing_catalog_cookie_headers(self):
        pairs = [('.youtube.com', 'SAPISID', 'local-test'),
                 ('.youtube.com', 'SOCS', 'local-consent'),
                 ('.youtube.com', 'CONSENT', 'YES+local-test'),
                 ('.google.com', 'SOCS', 'wrong-domain')]
        catalog = m.YouTubeMusicAuth._cookie_header_from_pairs(pairs)
        playback = m.YouTubeMusicAuth._cookie_header_from_pairs(pairs, include_consent=True)
        self.assertNotIn('SOCS=', catalog)
        self.assertNotIn('CONSENT=', catalog)
        self.assertIn('SOCS=local-consent', playback)
        self.assertIn('CONSENT=YES+local-test', playback)
        self.assertNotIn('wrong-domain', playback)

    def test_watch_short_and_metadata_ids_use_the_same_canonical_url(self):
        expected = 'https://music.youtube.com/watch?v=browser0001'
        for url in ('https://youtu.be/browser0001?t=12',
                    'https://youtube.com/shorts/browser0001',
                    'https://music.youtube.com/watch?v=browser0001&list=PRIVATE'):
            self.assertEqual(m.youtube_music_url({'url': url}), expected)
        self.assertEqual(m.youtube_music_url({'source': 'youtube', 'video_id': 'browser0001'}), expected)
        for url in ('https://youtube.com.evil.invalid/watch?v=browser0001',
                    'https://soundcloud.com/test/song', 'https://youtube.com/watch?v=bad'):
            self.assertEqual(m.youtube_music_url({'url': url}), '')
