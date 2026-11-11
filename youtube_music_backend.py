"""Drive the real YouTube Music player without adding a browser to Aurora's UI.

Like ytmdesktop, this uses ytmusic-player-bar.playerApi in music.youtube.com.
The small QMediaPlayer-compatible adapter keeps Aurora's queue and two slots.
"""

import json
import math
import re
from urllib.parse import parse_qs, urlsplit

from PyQt6.QtCore import QObject, QThread, QTimer, QUrl, Qt, pyqtSignal
from PyQt6.QtMultimedia import QMediaPlayer
from PyQt6.QtNetwork import QNetworkCookie
from PyQt6.QtWidgets import QWidget

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
    const bar = document.querySelector('ytmusic-player-bar');
    const api = bar && bar.playerApi;
    if (!api || !api.isReady || !api.isReady()) return null;
    let control = window.__auroraPlayback;
    if (!control || control.token !== desired.token) {
        control = window.__auroraPlayback = {token: desired.token, matched: false, seek: -1};
        api.setVolume(0);
        const details = api.getPlayerResponse()?.videoDetails || {};
        if (details.videoId !== desired.videoId) {
            document.dispatchEvent(new CustomEvent('yt-navigate', {detail: {
                endpoint: {watchEndpoint: {videoId: desired.videoId}}
            }}));
            return null;
        }
    }
    const response = api.getPlayerResponse() || {};
    const details = response.videoDetails || {};
    const state = api.getPlayerState();
    const store = document.querySelector('ytmusic-popup-container')?.store;
    const ad = !!(bar.adPlaying || document.querySelector('.ad-showing') ||
                  store?.getState?.()?.player?.adPlaying);
    if (ad) return null;
    const playability = response.playabilityStatus || {};
    const currentId = details.videoId || api.getVideoData?.()?.video_id;
    if (playability.status && playability.status !== 'OK' &&
        (currentId === desired.videoId || (!currentId && new URL(location.href).searchParams.get('v') === desired.videoId))) {
        return {token: desired.token, error: String(playability.reason || 'Трек недоступен в YouTube Music').slice(0, 220)};
    }
    if (details.videoId !== desired.videoId) {
        // Aurora owns the queue. Never let YTM's radio replace the selected song.
        if (control.matched) {
            api.pauseVideo();
            return {token: desired.token, ended: true};
        }
        return null;
    }
    control.matched = true;
    if (api.getErrorCode && api.getErrorCode()) {
        return {token: desired.token, error: 'Ошибка плеера YouTube Music: ' + api.getErrorCode()};
    }
    api.setVolume(desired.volume);
    if (desired.volume > 0 && api.unMute) api.unMute();
    if (control.seek !== desired.seekSerial && desired.position !== null) {
        api.seekTo(desired.position / 1000, true);
        control.seek = desired.seekSerial;
        // A seek acknowledgement is not proof that playback has advanced.
        return null;
    }
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
    return {token: desired.token, videoId: details.videoId, state,
            position: api.getCurrentTime(), duration: api.getDuration(),
            live: !!details.isLiveContent, seekSerial: desired.seekSerial};
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
        self._seek_position = None
        self._seek_serial = 0
        self._command_serial = 0
        self._timer = QTimer(self)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self._poll)
        session.prepared.connect(self._navigate)
        session.failed.connect(lambda message: self._fail(message) if not self._document_ready else None)
        session._players.append(self)

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

    def setSource(self, url):
        self._generation += 1
        self._inflight = False
        self._source = QUrl(url)
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
            self._document_ready = False
            self.page.load(QUrl("about:blank"))
        else:
            self._timer.start()
            self._navigate()

    def _navigate(self):
        if self._closed or self._source.isEmpty() or not self.session.ready:
            return
        # Keep a loaded YTM document; the script uses yt-navigate for later songs.
        if self.page.url().host() != "music.youtube.com" or not self._document_ready:
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
        if host not in ("music.youtube.com", "consent.youtube.com", "accounts.google.com"):
            return
        if host == "music.youtube.com" and info.url().query() != self._source.query():
            return
        if host in ("consent.youtube.com", "accounts.google.com"):
            self._fail("Открой YouTube Music в выбранном браузере, подтверди вход и обнови cookies в настройках аккаунта.")
        elif status == QWebEngineLoadingInfo.LoadStatus.LoadFailedStatus:
            self._fail("Не удалось открыть YouTube Music. Проверь подключение и доступ к music.youtube.com.")
        else:
            self._document_ready = True
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
        desired = {"token": str(generation), "videoId": self._source.query().partition("v=")[2],
                   "volume": self._volume(), "playing": self._want_playing,
                   "stopped": self._stopped, "position": self._seek_position, "seekSerial": self._seek_serial,
                   "commandSerial": self._command_serial}
        self._inflight = True
        self.page.runJavaScript(_PLAYER_SCRIPT.replace("__DESIRED__", json.dumps(desired)),
                                lambda data, g=generation: self._snapshot(g, data))

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
        if self._failed or self._source.isEmpty() or not isinstance(data, dict) or data.get("token") != str(generation):
            return
        if data.get("error"):
            self._fail(str(data["error"]))
            return
        if data.get("ended"):
            self.page.setAudioMuted(True)
            self._set_state(QMediaPlayer.PlaybackState.StoppedState)
            self._set_status(QMediaPlayer.MediaStatus.EndOfMedia)
            return
        if data.get("videoId") != self._source.query().partition("v=")[2]:
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
        self.page.setAudioMuted(True)
        self._set_state(QMediaPlayer.PlaybackState.StoppedState)
        self._set_status(QMediaPlayer.MediaStatus.InvalidMedia)
        self.errorOccurred.emit(QMediaPlayer.Error.ResourceError, message)

    def shutdown(self):
        if self._closed:
            return
        self._closed = True
        self._timer.stop()
        self.page.setAudioMuted(True)
        self.view.close()
        self.view.deleteLater()
        self.page.deleteLater()
