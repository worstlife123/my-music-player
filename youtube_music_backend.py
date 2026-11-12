"""Drive the real YouTube Music player without adding a browser to Aurora's UI.

Like ytmdesktop, this uses ytmusic-player-bar.playerApi in music.youtube.com.
The small QMediaPlayer-compatible adapter keeps Aurora's queue and two slots.
"""

import json
import logging
import math
import re
from urllib.parse import parse_qs, urlsplit

from PyQt6.QtCore import QObject, QThread, QTimer, QUrl, Qt, pyqtSignal
from PyQt6.QtMultimedia import QMediaPlayer
from PyQt6.QtNetwork import QNetworkCookie
from PyQt6.QtWidgets import QWidget

WEB_DRIVER_PROTOCOL = 2

try:
    # Import before QApplication is constructed, including in frozen builds.
    from PyQt6.QtWebEngineCore import QWebEngineLoadingInfo, QWebEnginePage, QWebEngineProfile, QWebEngineSettings
    from PyQt6.QtWebEngineWidgets import QWebEngineView
except ImportError:
    QWebEnginePage = QWebEngineProfile = QWebEngineSettings = QWebEngineView = None


def youtube_music_url(track):
    """Accept YouTube IDs/watch URLs, never a direct stream or an arbitrary host."""
    raw_url = str(track.get("url") or "").strip()
    parsed = urlsplit(raw_url)
    host = (parsed.hostname or "").lower()
    youtube_host = host in ("youtube.com", "youtu.be") or host.endswith(".youtube.com")
    if track.get("source") != "youtube" and not youtube_host:
        return ""
    video_id = str(track.get("video_id") or track.get("videoId") or "").strip()
    if not video_id and youtube_host:
        if host == "youtu.be":
            video_id = parsed.path.strip("/").split("/")[0]
        elif parsed.path.startswith(("/shorts/", "/embed/")):
            video_id = parsed.path.split("/")[2]
        else:
            video_id = parse_qs(parsed.query).get("v", [""])[0]
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        return ""
    return "https://music.youtube.com/watch?v=" + video_id


class _CookieReader(QThread):
    result = pyqtSignal(str)

    def __init__(self, loader, parent):
        super().__init__(parent)
        self.loader = loader

    def run(self):
        try:
            header = self.loader()
        except Exception:
            # A closed browser or missing cookies must not block public songs.
            header = ""
        self.result.emit(header)


class YouTubeMusicSession(QObject):
    """Share one in-memory browser session between the two playback slots.

    Account settings already persist in Aurora. Cookies are imported from that
    source, without creating another persistent account store on disk.
    """

    prepared = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        if QWebEngineProfile is None:
            raise RuntimeError("Для запуска YouTube Music установи PyQt6-WebEngine: python -m pip install -U PyQt6-WebEngine")
        self.profile = QWebEngineProfile(self)
        self.profile.setHttpUserAgent(re.sub(r"\sQtWebEngine/\S+", "", self.profile.httpUserAgent()))
        self.ready = False
        self._signature = None
        self._generation = 0
        self._cookies = set()
        self._players = []
        self._closed = False
        self._cookie_timer = QTimer(self)
        self._cookie_timer.setSingleShot(True)
        self._cookie_timer.timeout.connect(self._cookie_timeout)
        self.profile.cookieStore().cookieAdded.connect(self._cookie_added)

    def configure(self, signature, cookie_loader=None):
        if self._closed or signature == self._signature:
            return
        self._signature = signature
        self._generation += 1
        generation = self._generation
        self.ready = False
        self._cookies.clear()
        self._cookie_timer.stop()
        self.profile.cookieStore().deleteAllCookies()
        if cookie_loader is None:
            self._import_cookies(generation, "")
            return
        worker = _CookieReader(cookie_loader, self)
        worker.result.connect(lambda header, g=generation: self._import_cookies(g, header))
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _import_cookies(self, generation, header):
        if self._closed or generation != self._generation:
            return
        cookies = []
        for component in header.split("; "):
            name, separator, value = component.partition("=")
            if separator and name and value:
                cookie = QNetworkCookie(name.encode("ascii"), value.encode("utf-8"))
                cookie.setDomain(".youtube.com")
                cookie.setPath("/")
                cookie.setSecure(True)
                cookies.append(cookie)
        self._cookies = {(bytes(c.name()), bytes(c.value())) for c in cookies}
        if not self._cookies:
            self.ready = True
            self.prepared.emit()
            return
        # Do not navigate before Chromium has actually accepted the account.
        self._cookie_timer.start(5000)
        for cookie in cookies:
            self.profile.cookieStore().setCookie(cookie, QUrl("https://music.youtube.com/"))

    def _cookie_added(self, cookie):
        key = (bytes(cookie.name()), bytes(cookie.value()))
        if self._closed or key not in self._cookies:
            return
        self._cookies.discard(key)
        if not self._cookies:
            self._cookie_timer.stop()
            self.ready = True
            self.prepared.emit()

    def _cookie_timeout(self):
        self._cookies.clear()
        self._signature = None
        self.ready = True
        self.failed.emit("Не удалось подключить сессию YouTube Music. Проверь cookies в настройках аккаунта.")

    def clear_account(self):
        self._signature = None
        self._generation += 1
        self._cookies.clear()
        self._cookie_timer.stop()
        self.profile.cookieStore().deleteAllCookies()
        # The signed-out player can keep processing pause/stop and Aurora's queue.
        self.ready = True
        self.prepared.emit()

    def shutdown(self):
        self._closed = True
        self._generation += 1
        self._cookie_timer.stop()
        for player in self._players:
            player.shutdown()
        # Pages must be destroyed before their profile.
        self.profile.deleteLater()


# All values are passed as JSON. No bridge exposing Python to the website is
# installed. Each document/request has its own token, checked on both sides.
_PLAYER_SCRIPT = r"""
(() => {
    const desired = __DESIRED__;
    const report = (phase, extra = {}) => ({token: desired.token, phase,
        visibility: document.visibilityState, width: innerWidth, height: innerHeight, ...extra});
    try {
    const bar = document.querySelector('ytmusic-player-bar');
    if (!bar) return report('waiting_player');
    let api;
    try { api = bar.playerApi; } catch (_) { return report('waiting_api'); }
    if (!api || typeof api.isReady !== 'function' || typeof api.playVideo !== 'function')
        return report('waiting_api');
    let response = {};
    try { response = api.getPlayerResponse?.() || {}; } catch (_) {}
    const details = response.videoDetails || {};
    let currentId = details.videoId;
    if (!currentId) {
        try { currentId = api.getVideoData?.()?.video_id; } catch (_) {}
    }
    const playability = response.playabilityStatus || {};
    if (playability.status && playability.status !== 'OK' &&
        (currentId === desired.videoId || (!currentId && new URL(location.href).searchParams.get('v') === desired.videoId))) {
        return report('playability_error', {error: String(playability.reason || 'Трек недоступен в YouTube Music').slice(0, 220)});
    }
    let ready = false;
    try { ready = api.isReady(); } catch (_) {}
    if (!ready) return report('api_not_ready');
    let control = window.__auroraPlayback;
    if (!control || control.token !== desired.token) {
        control = window.__auroraPlayback = {token: desired.token, matched: false, seek: -1, navigated: false};
        api.setVolume(0);
    }
    const state = Number(api.getPlayerState());
    const store = document.querySelector('ytmusic-popup-container')?.store;
    const ad = !!(bar.adPlaying || document.querySelector('.ad-showing') ||
                  store?.getState?.()?.player?.adPlaying);
    if (control.matched && currentId && currentId !== desired.videoId && !ad) {
        // Aurora owns the queue. Do not start the site's automatically chosen song.
        api.pauseVideo();
        return report('ended', {ended: true});
    }
    const errorCode = typeof api.getErrorCode === 'function' ? api.getErrorCode() : 0;
    if (Number(errorCode) > 0 && (ad || !currentId || currentId === desired.videoId)) {
        return report('player_error', {error: 'Ошибка плеера YouTube Music: ' + errorCode});
    }
    if (!control.matched && !control.navigated && currentId !== desired.videoId && !ad) {
        control.navigated = true;
        document.dispatchEvent(new CustomEvent('yt-navigate', {detail: {
            endpoint: {watchEndpoint: {videoId: desired.videoId}}
        }}));
    }
    api.setVolume(desired.volume);
    if (desired.volume > 0 && api.unMute) api.unMute();
    if (!ad && currentId === desired.videoId) {
        control.matched = true;
        if (control.seek !== desired.seekSerial && desired.position !== null) {
            api.seekTo(desired.position / 1000, true);
            control.seek = desired.seekSerial;
            // A seek acknowledgement is not proof that playback has advanced.
            return report('seeking');
        }
    }
    // Start the official player before waiting for content metadata. The first
    // player response and a preroll can both require this initial Play command.
    if (control.command !== desired.commandSerial) {
        control.command = desired.commandSerial;
        if (desired.playing && !desired.stopped) api.playVideo();
        else api.pauseVideo();
    } else if (desired.stopped) {
        api.pauseVideo();
    } else if (desired.playing && [-1, 2, 5].includes(state)) {
        api.playVideo();
    } else if (!desired.playing && [1, 3].includes(state)) {
        api.pauseVideo();
    }
    if (ad) return report('advertisement', {state});
    if (currentId !== desired.videoId) return report('waiting_video', {state});
    return report(state === 1 ? 'playing' : state === 3 ? 'buffering' : state === 0 ? 'ended' : 'paused',
           {videoId: currentId, state,
            position: api.getCurrentTime(), duration: api.getDuration(),
            live: !!details.isLiveContent, seekSerial: desired.seekSerial});
    } catch (error) {
        return report('script_error', {error: 'Ошибка управления плеером YouTube Music: ' + String(error.message || error).slice(0, 180)});
    }
})()
"""


class YouTubeMusicPlayer(QObject):
    """Aurora's existing media API with an offscreen browser rendering surface."""

    positionChanged = pyqtSignal(int)
    durationChanged = pyqtSignal(int)
    playbackStateChanged = pyqtSignal(object)
    mediaStatusChanged = pyqtSignal(object)
    errorOccurred = pyqtSignal(object, str)
    seekableChanged = pyqtSignal(bool)
    JAVASCRIPT_TIMEOUT_MS = 10_000

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session
        self.page = QWebEnginePage(session.profile, self)
        # A page without a view has a 0x0 viewport and remains hidden to the
        # website. Give YTM a real desktop viewport, without presenting a window,
        # painting over Aurora, joining a layout, or taking keyboard focus.
        self.view = QWebEngineView(parent if isinstance(parent, QWidget) else None)
        self.view.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        self.view.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.view.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.view.resize(1280, 720)
        self.view.move(-16384, -16384)
        self.view.setPage(self.page)
        self.view.show()
        self.page.settings().setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False)
        self.page.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, False)
        # Keep audio/timers active while the browser has no visible widget.
        self.page.setLifecycleState(QWebEnginePage.LifecycleState.Active)
        self.page.setVisible(True)
        self.page.setAudioMuted(True)
        self.page.loadingChanged.connect(self._loading_changed)
        self.page.renderProcessTerminated.connect(lambda *_: self._fail("Плеер YouTube Music завершился. Нажми ▶ для повторного запуска."))
        self._source = QUrl()
        self._generation = 0
        self._inflight = False
        self._output = None
        self._position = self._duration = 0
        self._state = QMediaPlayer.PlaybackState.StoppedState
        self._status = QMediaPlayer.MediaStatus.NoMedia
        self._seekable = False
        self._want_playing = False
        self._stopped = True
        self._failed = False
        self._closed = False
        self._document_ready = False
        self._page_loading = False
        self._page_load_url = QUrl()
        self._page_load_signature = None
        self._last_phase = ''
        self._last_document_state = None
        self._last_api_state = None
        self._seek_position = None
        self._seek_serial = 0
        self._command_serial = 0
        self._timer = QTimer(self)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self._poll)
        self._javascript_timer = QTimer(self)
        self._javascript_timer.setSingleShot(True)
        self._javascript_timer.timeout.connect(lambda: self._fail(
            "Встроенный плеер YouTube Music не ответил. Этап загрузки записан в player.log."))
        session.prepared.connect(self._navigate)
        session.failed.connect(lambda message: self._fail(message) if not self._document_ready else None)
        session._players.append(self)
        logging.getLogger('aurora').info('YouTube Music: web_driver=%d; initialized', WEB_DRIVER_PROTOCOL)

    def _set_phase(self, phase):
        if isinstance(phase, str) and re.fullmatch(r'[a-z_]{1,32}', phase) and phase != self._last_phase:
            self._last_phase = phase
            # Do not log page contents, cookies or URL query parameters.
            logging.getLogger('aurora').info('YouTube Music: stage=%s; host=%s', phase, self.page.url().host())

    def startup_timeout_message(self):
        if self._last_phase == 'waiting_session':
            return 'Не удалось подключить сессию YouTube Music. Проверь настройки аккаунта.'
        if self._last_phase in ('loading_page', 'created'):
            return 'Не удалось загрузить YouTube Music. Проверь открытие music.youtube.com в браузере.'
        if self._last_phase in ('waiting_player', 'waiting_api', 'api_not_ready'):
            return 'Страница YouTube Music открылась, но её плеер не подготовился. Этап записан в player.log.'
        if self._last_phase == 'waiting_video':
            return 'YouTube Music не подтвердил открытие выбранного трека. Проверь его доступность на сайте.'
        if self._last_phase == 'advertisement':
            return 'Не удалось дождаться начала трека после рекламы YouTube Music.'
        return 'YouTube Music не начал передавать аудио. Этап загрузки записан в player.log.'

    def source(self):
        return QUrl(self._source)

    def position(self):
        return self._position

    def duration(self):
        return self._duration

    def playbackState(self):
        return self._state

    def mediaStatus(self):
        return self._status

    def isSeekable(self):
        return self._seekable

    def audioOutput(self):
        return self._output

    def _set_state(self, state):
        if self._state != state:
            self._state = state
            self.playbackStateChanged.emit(state)

    def _set_status(self, status):
        if self._status != status:
            self._status = status
            self.mediaStatusChanged.emit(status)

    def setAudioOutput(self, output):
        if self._output is not None:
            self._output.volumeChanged.disconnect(self._sync_volume)
            self._output.mutedChanged.disconnect(self._sync_volume)
        self._output = output
        if output is not None:
            output.volumeChanged.connect(self._sync_volume)
            output.mutedChanged.connect(self._sync_volume)
        self._sync_volume()

    def _volume(self):
        return (round(self._output.volume() * 100)
                if self._output is not None and not self._output.isMuted() else 0)

    def _sync_volume(self, *_):
        if self._closed:
            return
        volume = self._volume()
        self.page.setAudioMuted(self._stopped or volume == 0 or self._failed or self._source.isEmpty())
        # Fade updates arrive more often than position polls.
        token = json.dumps(str(self._generation))
        self.page.runJavaScript(
            "(() => { const c = window.__auroraPlayback; const a = document.querySelector('ytmusic-player-bar')?.playerApi; "
            f"if (a && c?.token === {token}) a.setVolume({volume}); }})()"
        )

    def setSource(self, url, preserve_document=False):
        self._generation += 1
        self._inflight = False
        self._javascript_timer.stop()
        self._source = QUrl(url)
        self._last_api_state = None
        self._failed = False
        self._want_playing = False
        self._stopped = True
        self._seek_position = None
        self._seek_serial += 1
        self._position = self._duration = 0
        self._seekable = False
        self.page.setAudioMuted(True)
        self._set_state(QMediaPlayer.PlaybackState.StoppedState)
        self._set_status(QMediaPlayer.MediaStatus.NoMedia if url.isEmpty() else QMediaPlayer.MediaStatus.LoadingMedia)
        if url.isEmpty():
            self._timer.stop()
            if not preserve_document:
                self._document_ready = False
                self._page_loading = False
                self._page_load_url = QUrl()
                self.page.load(QUrl("about:blank"))
        else:
            self._timer.start()
            self._navigate()

    def _navigate(self):
        if self._closed or self._source.isEmpty():
            return
        if not self.session.ready:
            self._set_phase('waiting_session')
            return
        if self._page_loading and self._page_load_signature == getattr(self.session, '_signature', None):
            # Retarget the command after readiness; do not restart the website's
            # bootstrap on every click while its scripts are still loading.
            self._set_phase('loading_page')
            return
        # Keep a loaded YTM document; the script uses yt-navigate for later songs.
        if self.page.url().host() != "music.youtube.com" or not self._document_ready:
            self._set_phase('loading_page')
            self._page_loading = True
            self._page_load_url = QUrl(self._source)
            self._page_load_signature = getattr(self.session, '_signature', None)
            self.page.load(self._source)
        else:
            self._poll()

    def _loading_changed(self, info):
        if self._closed or self._source.isEmpty():
            return
        # A superseded load emits an aborted/stop event after the next selection.
        status = info.status()
        if status not in (QWebEngineLoadingInfo.LoadStatus.LoadSucceededStatus,
                          QWebEngineLoadingInfo.LoadStatus.LoadFailedStatus) or info.errorCode() == -3:
            return
        host = info.url().host()
        if not host:
            return
        if host == "music.youtube.com" and self._video_id(info.url()) not in (
                '', self._video_id(self._source), self._video_id(self._page_load_url)):
            return
        self._page_loading = False
        logging.getLogger('aurora').info('YouTube Music: page_status=%s; host=%s; network_error=%d',
                                       status.name, host, info.errorCode())
        if host in ("consent.youtube.com", "accounts.google.com"):
            self._fail("Открой YouTube Music в выбранном браузере, подтверди вход и обнови cookies в настройках аккаунта.")
        elif host != 'music.youtube.com':
            self._fail('YouTube Music перенаправил на другую страницу. Открой music.youtube.com в браузере и проверь вход и доступность сервиса.')
        elif status == QWebEngineLoadingInfo.LoadStatus.LoadFailedStatus:
            self._fail("Не удалось открыть YouTube Music. Проверь подключение и доступ к music.youtube.com.")
        else:
            self._document_ready = True
            self._set_phase('page_loaded')
            self._poll()

    def play(self):
        if self._source.isEmpty() or self._failed:
            return
        self._stopped = False
        self._want_playing = True
        self._command_serial += 1
        self._sync_volume()
        self._poll()

    def pause(self):
        self._want_playing = False
        self._command_serial += 1
        # Mute immediately; the observed state still comes from the real player.
        self.page.setAudioMuted(True)
        self._poll()

    def stop(self):
        self._want_playing = False
        self._stopped = True
        self._command_serial += 1
        self.page.setAudioMuted(True)
        self._seek_position = 0
        self._seek_serial += 1
        self._position = 0
        self._set_state(QMediaPlayer.PlaybackState.StoppedState)
        self._poll()

    def setPosition(self, position):
        self._seek_position = max(0, int(position))
        self._seek_serial += 1
        self._poll()

    def _poll(self):
        if (self._closed or self._failed or self._source.isEmpty() or self._inflight
                or not self.session.ready or self.page.url().host() != "music.youtube.com"):
            return
        generation = self._generation
        desired = {"token": str(generation), "videoId": self._video_id(self._source),
                   "volume": self._volume(), "playing": self._want_playing,
                   "stopped": self._stopped, "position": self._seek_position, "seekSerial": self._seek_serial,
                   "commandSerial": self._command_serial}
        self._inflight = True
        self._javascript_timer.start(self.JAVASCRIPT_TIMEOUT_MS)
        self.page.runJavaScript(_PLAYER_SCRIPT.replace("__DESIRED__", json.dumps(desired)),
                                lambda data, g=generation: self._snapshot(g, data))

    @staticmethod
    def _video_id(url):
        return parse_qs(url.query()).get('v', [''])[0]

    @staticmethod
    def _milliseconds(value):
        try:
            value = float(value)
            return int(value * 1000) if math.isfinite(value) and 0 <= value <= 604800 else 0
        except (ValueError, TypeError, OverflowError):
            return 0

    def _snapshot(self, generation, data):
        if self._closed or generation != self._generation:
            return
        self._inflight = False
        self._javascript_timer.stop()
        if self._failed or self._source.isEmpty() or not isinstance(data, dict) or data.get("token") != str(generation):
            return
        self._set_phase(data.get('phase'))
        visibility, width, height = data.get('visibility'), data.get('width'), data.get('height')
        if visibility in ('visible', 'hidden', 'prerender') and isinstance(width, int) and isinstance(height, int):
            document_state = (visibility, width, height)
            if document_state != self._last_document_state:
                self._last_document_state = document_state
                logging.getLogger('aurora').info('YouTube Music: visibility=%s; viewport=%dx%d', visibility, width, height)
        state = data.get('state')
        if state in (-1, 0, 1, 2, 3, 5) and state != self._last_api_state:
            self._last_api_state = state
            logging.getLogger('aurora').info('YouTube Music: player_state=%d; stage=%s', state, self._last_phase)
        if data.get("error"):
            self._fail(str(data["error"]))
            return
        if data.get("ended"):
            self.page.setAudioMuted(True)
            self._set_state(QMediaPlayer.PlaybackState.StoppedState)
            self._set_status(QMediaPlayer.MediaStatus.EndOfMedia)
            return
        if data.get("videoId") != self._video_id(self._source):
            return
        duration = self._milliseconds(data.get("duration"))
        if duration != self._duration:
            self._duration = duration
            self.durationChanged.emit(duration)
        seekable = bool(duration and not data.get("live"))
        if seekable != self._seekable:
            self._seekable = seekable
            self.seekableChanged.emit(seekable)
        state = data.get("state")
        status = {0: QMediaPlayer.MediaStatus.EndOfMedia, 1: QMediaPlayer.MediaStatus.BufferedMedia,
                  3: QMediaPlayer.MediaStatus.BufferingMedia}.get(state, QMediaPlayer.MediaStatus.LoadedMedia)
        self._set_status(status)
        # Status callbacks may cancel/replace this source or request a restore seek.
        if generation != self._generation or self._failed or self._source.isEmpty():
            return
        playback = (QMediaPlayer.PlaybackState.StoppedState if self._stopped or state == 0 else
                    QMediaPlayer.PlaybackState.PlayingState if state in (1, 3) and self._want_playing else
                    QMediaPlayer.PlaybackState.PausedState)
        self._set_state(playback)
        position_observed = ((state == 1 and self._want_playing)
                             or (state == 2 and not self._want_playing and not self._stopped))
        if position_observed and data.get("seekSerial") == self._seek_serial:
            position = self._milliseconds(data.get("position"))
            if position != self._position:
                self._position = position
                self.positionChanged.emit(position)

    def _fail(self, message):
        if self._closed or self._failed or self._source.isEmpty():
            return
        self._failed = True
        self._document_ready = False
        self._timer.stop()
        self._javascript_timer.stop()
        logging.getLogger('aurora').warning('YouTube Music: failure_stage=%s; message=%s', self._last_phase, message)
        self.page.setAudioMuted(True)
        self._set_state(QMediaPlayer.PlaybackState.StoppedState)
        self._set_status(QMediaPlayer.MediaStatus.InvalidMedia)
        self.errorOccurred.emit(QMediaPlayer.Error.ResourceError, message)

    def shutdown(self):
        if self._closed:
            return
        self._closed = True
        self._timer.stop()
        self._javascript_timer.stop()
        self.page.setAudioMuted(True)
        self.view.close()
        self.view.deleteLater()
        self.page.deleteLater()
