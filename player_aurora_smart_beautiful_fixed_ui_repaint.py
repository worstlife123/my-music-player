# Music Player Green Edition — Spotify-inspired redesign, artist profiles and track radio.
# Пока новый трек запускается в тихом плеере, старый продолжает играть.
# Когда позиция нового потока начинает двигаться, звук плавно переключается.
# Важно: Manrope загружается из установленных шрифтов Windows либо из папки fonts/.
# Сам файл шрифта в проект не включён.

import sys
import logging
import ctypes
import weakref
import hashlib
from logging.handlers import RotatingFileHandler
import os
import shutil
import subprocess
import time
import random
import json
import threading
import math
import re
import unicodedata
import configparser
from uuid import uuid4
from collections import deque, OrderedDict
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, QUrl, QSize, QRect, QRectF, QTimer, QSettings, QPointF, QPoint, QEvent, QEasingCurve, QPropertyAnimation, QVariantAnimation, pyqtSignal, pyqtProperty, QStandardPaths, QAbstractNativeEventFilter
from PyQt6.QtGui import (
    QShortcut, QKeySequence, QBrush, QColor, QFont, QFontDatabase, QLinearGradient,
    QPainter, QPen, QPixmap, QPalette, QIcon, QPolygonF, QPainterPath, QDesktopServices, QFontMetrics, QRadialGradient,
)
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkDiskCache
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox,
    QPushButton, QSizePolicy, QSlider, QVBoxLayout, QWidget,
    QDialog, QTabWidget, QCheckBox, QFormLayout, QStyle, QStyleOptionSlider, QStackedWidget, QGraphicsOpacityEffect, QGraphicsDropShadowEffect, QGridLayout, QComboBox, QScrollArea, QSystemTrayIcon, QTextEdit, QPlainTextEdit, QAbstractSpinBox,
)
from yt_dlp import YoutubeDL


def yt_dlp_tls_options():
    """Проверяет HTTPS и учитывает явно настроенное системное хранилище CA."""
    options = {"nocheckcertificate": False}
    # yt-dlp по умолчанию выбирает certifi и игнорирует SSL_CERT_FILE/SSL_CERT_DIR.
    # Поддерживаем доверенные CA пользователя/прокси без отключения проверки TLS.
    if os.environ.get("SSL_CERT_FILE") or os.environ.get("SSL_CERT_DIR"):
        options["compat_opts"] = {"no-certifi"}
    return options


# -------------------------------------------------------------
# Загрузка шрифта Manrope, установленного пользователем.
# Можно установить его в Windows ИЛИ положить .ttf/.otf в fonts/.
# Если Manrope не найден, приложение остаётся рабочим с Segoe UI.
# -------------------------------------------------------------

def setup_font(app):
    fonts_dir = Path(__file__).resolve().parent / "fonts"
    if fonts_dir.is_dir():
        for font_path in list(fonts_dir.glob("*.ttf")) + list(fonts_dir.glob("*.otf")):
            QFontDatabase.addApplicationFont(str(font_path))

    families = QFontDatabase.families()
    manrope = next((family for family in families if family.lower() == "manrope"), None)
    family = manrope or app.font().family()
    app.setFont(QFont(family, 10))
    return family


def human_time(seconds):
    if not seconds:
        return ""
    try:
        seconds = int(float(seconds))
        if seconds <= 0:
            return ""
        minutes, remainder = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        return f"{hours}:{minutes:02d}:{remainder:02d}" if hours else f"{minutes}:{remainder:02d}"
    except (ValueError, TypeError):
        return ""


def extract_date(entry):
    """Дата в yt-dlp может быть timestamp или строкой YYYYMMDD."""
    timestamp = entry.get("release_timestamp") or entry.get("timestamp")
    if timestamp:
        try:
            return int(timestamp)
        except (TypeError, ValueError):
            pass
    for key in ("release_date", "upload_date"):
        raw = entry.get(key)
        if raw:
            try:
                return int(datetime.strptime(str(raw), "%Y%m%d").timestamp())
            except (TypeError, ValueError):
                continue
    return 0


def normalize_artwork_url(raw_url):
    """Приводит CDN-ссылки обложек к URL, который понимает QtNetwork."""
    url = str(raw_url or "").strip()
    if url.startswith("//"):
        url = "https:" + url
    elif url.startswith("http://"):
        # SoundCloud CDN поддерживает HTTPS; это также помогает избежать
        # блокировки смешанного содержимого и проблем с редиректами.
        url = "https://" + url[7:]
    return url


def app_cache_directory():
    """Возвращает пользовательскую папку кэша, не зависящую от каталога приложения."""
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache"))
    cache_dir = base / "AuroraMusicPlayer"
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir
    except OSError:
        # Запасной путь полезен для портативных сборок и ограниченных профилей.
        fallback = Path.home() / ".aurora_music_player_cache"
        try:
            fallback.mkdir(parents=True, exist_ok=True)
        except OSError:
            # В таком случае постоянный кэш просто будет недоступен; поиск должен работать.
            pass
        return fallback


def app_data_directory():
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    path = Path(base) if base else Path.home() / ".local" / "share"
    if path.name.casefold() != "auroramusicplayer":
        path /= "AuroraMusicPlayer"
    path.mkdir(parents=True, exist_ok=True)
    return path


def migrate_legacy_data(filename):
    destination = app_data_directory() / filename
    legacy = Path(__file__).resolve().parent / filename
    marker = destination.with_suffix(destination.suffix + ".migrated")
    if marker.exists():
        return destination
    if destination.exists():
        try:
            marker.touch(exist_ok=True)
        except OSError as exc:
            logging.getLogger("aurora").warning("Маркер миграции %s: %s", filename, exc)
        return destination
    if legacy.is_file():
        try:
            shutil.copy2(legacy, destination)
            marker.touch(exist_ok=True)
        except OSError as exc:
            logging.getLogger("aurora").warning("Миграция %s: %s", filename, exc)
            return destination if destination.exists() else legacy
    return destination


def setup_logging():
    logger = logging.getLogger("aurora")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(threadName)s | %(message)s")
        file_handler = RotatingFileHandler(app_cache_directory() / "player.log", maxBytes=5*1024*1024,
                                           backupCount=3, encoding="utf-8")
        console = logging.StreamHandler(sys.stdout)
        for handler in (file_handler, console):
            handler.setFormatter(fmt)
            logger.addHandler(handler)
    return logger


def style_dialog_for_theme(dialog, object_name, theme):
    """Задаёт диалогу читаемую палитру в обеих темах приложения."""
    dialog.setObjectName(object_name)
    dialog.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    dialog.setAutoFillBackground(True)
    palette = dialog.palette()
    if theme == "light":
        palette.setColor(QPalette.ColorRole.Window, QColor("#F5F5F7"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#222222"))
        palette.setColor(QPalette.ColorRole.Base, QColor("#FFFFFF"))
        palette.setColor(QPalette.ColorRole.Text, QColor("#222222"))
        palette.setColor(QPalette.ColorRole.Button, QColor("#E8E8EE"))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor("#222222"))
        dialog.setPalette(palette)
        dialog.setStyleSheet("""
            QDialog { background: #F5F5F7; color: #222222; }
            QDialog QWidget { color: #222222; }
            QDialog QLabel { color: #222222; background: transparent; }
            QDialog QLabel#settingsTitle { color: #202027; font-size: 22pt; font-weight: 800; }
            QDialog QLabel#settingsHint, QDialog QLabel#mutedText { color: #626270; }
            QDialog QLineEdit, QDialog QComboBox {
                background: #FFFFFF; color: #222222; border: 1px solid #D2D2DA;
                border-radius: 9px; padding: 8px 10px; min-height: 20px;
                selection-background-color: #1DB954; selection-color: #101010;
            }
            QDialog QComboBox QAbstractItemView {
                background: #FFFFFF; color: #222222; selection-background-color: #E1F4E7;
                selection-color: #16883D; border: 1px solid #D2D2DA;
            }
            QDialog QPushButton {
                background: #E8E8EE; color: #24242B; border: 1px solid #D5D5DE;
                border-radius: 9px; padding: 9px 14px;
            }
            QDialog QPushButton:hover { background: #FFFFFF; border-color: #1DB954; }
            QDialog QPushButton#accentButton {
                background: #1DB954; color: #101010; border: none; font-weight: 800;
            }
            QDialog QPushButton#accentButton:hover { background: #16883D; color: #FFFFFF; }
            QMessageBox { background: #F5F5F7; color: #222222; }
            QMessageBox QLabel { color: #222222; min-width: 280px; }
            QMessageBox QPushButton { background: #E8E8EE; color: #222222; }
        """)
    else:
        palette.setColor(QPalette.ColorRole.Window, QColor("#181818"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#F5F5F5"))
        palette.setColor(QPalette.ColorRole.Base, QColor("#242424"))
        palette.setColor(QPalette.ColorRole.Text, QColor("#F5F5F5"))
        palette.setColor(QPalette.ColorRole.Button, QColor("#282828"))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor("#FFFFFF"))
        dialog.setPalette(palette)
        dialog.setStyleSheet("""
            QDialog { background: #181818; color: #F5F5F5; }
            QDialog QWidget { color: #F5F5F5; }
            QDialog QLabel { color: #F5F5F5; background: transparent; }
            QDialog QLabel#settingsTitle { color: #FFFFFF; font-size: 22pt; font-weight: 800; }
            QDialog QLabel#settingsHint, QDialog QLabel#mutedText { color: #B3B3B3; }
            QDialog QLineEdit, QDialog QComboBox {
                background: #242424; color: #FFFFFF; border: 1px solid #3A3A3A;
                border-radius: 9px; padding: 8px 10px; min-height: 20px;
                selection-background-color: #1DB954; selection-color: #101010;
            }
            QDialog QComboBox QAbstractItemView {
                background: #242424; color: #FFFFFF; selection-background-color: #1DB954;
                selection-color: #101010; border: 1px solid #3A3A3A;
            }
            QDialog QPushButton {
                background: #282828; color: #F5F5F5; border: 1px solid #3A3A3A;
                border-radius: 9px; padding: 9px 14px;
            }
            QDialog QPushButton:hover { background: #333333; border-color: #1DB954; }
            QDialog QPushButton#accentButton {
                background: #1DB954; color: #101010; border: none; font-weight: 800;
            }
            QDialog QPushButton#accentButton:hover { background: #1ED760; }
            QMessageBox { background: #181818; color: #FFFFFF; }
            QMessageBox QLabel { color: #FFFFFF; min-width: 280px; }
            QMessageBox QPushButton { background: #282828; color: #FFFFFF; }
        """)


def _waterfox_profile_dirs():
    """Находит профили Waterfox в стандартных каталогах Windows."""
    appdata = os.environ.get("APPDATA", "")
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    bases = []
    if appdata:
        bases.append(Path(appdata) / "Waterfox")
    if local_appdata:
        bases.append(Path(local_appdata) / "Waterfox")
    # Поддержка portable/нестандартных установок: если в APPDATA профилей нет,
    # их путь всё равно можно передать вручную через поле «Профиль».
    found = []
    for base in bases:
        profiles_root = base / "Profiles"
        if profiles_root.is_dir():
            found.extend(path for path in profiles_root.iterdir() if path.is_dir())
        if base.is_dir():
            found.extend(path for path in base.iterdir()
                         if path.is_dir() and (path / "cookies.sqlite").is_file())
    # Сохраняем порядок, убирая дубликаты.
    unique = []
    seen = set()
    for path in found:
        key = str(path.resolve()).casefold()
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return bases, unique


def resolve_waterfox_profile(profile=None):
    """Возвращает путь профиля Waterfox, который yt-dlp может читать как Firefox."""
    raw = str(profile or "").strip().strip('"')
    bases, candidates = _waterfox_profile_dirs()

    # Полный путь, скопированный из about:profiles.
    if raw:
        expanded = Path(os.path.expandvars(raw)).expanduser()
        if expanded.is_dir():
            return str(expanded.resolve())
        # Имя папки профиля или имя профиля из profiles.ini.
        for candidate in candidates:
            if candidate.name.casefold() == raw.casefold():
                return str(candidate.resolve())
        for base in bases:
            ini = base / "profiles.ini"
            if not ini.is_file():
                continue
            parser = configparser.ConfigParser()
            try:
                parser.read(ini, encoding="utf-8")
            except (OSError, configparser.Error):
                continue
            for section in parser.sections():
                values = parser[section]
                path_value = values.get("path", "").strip()
                name_value = values.get("name", "").strip()
                if raw.casefold() not in (name_value.casefold(), Path(path_value).name.casefold()):
                    continue
                if not path_value:
                    continue
                target = Path(path_value)
                if values.get("isrelative", "1").strip() == "1":
                    target = base / target
                if target.is_dir():
                    return str(target.resolve())
        # Оставляем переданное значение: yt-dlp вернёт диагностичную ошибку.
        return raw

    # Сначала читаем profiles.ini и выбираем профиль по умолчанию.
    for base in bases:
        ini = base / "profiles.ini"
        if not ini.is_file():
            continue
        parser = configparser.ConfigParser()
        try:
            parser.read(ini, encoding="utf-8")
        except (OSError, configparser.Error):
            continue
        default_path = ""
        for section in parser.sections():
            values = parser[section]
            if section.casefold().startswith("profile") and values.get("default", "0").strip() == "1":
                default_path = values.get("path", "").strip()
                if default_path:
                    if values.get("isrelative", "1").strip() == "1":
                        default_path = str((base / default_path).resolve())
                    break
        if not default_path:
            for section in parser.sections():
                if section.casefold().startswith("install"):
                    default_path = parser[section].get("default", "").strip()
                    if default_path:
                        if not Path(default_path).is_absolute():
                            default_path = str((base / default_path).resolve())
                        break
        if default_path and (Path(default_path) / "cookies.sqlite").is_file():
            return str(Path(default_path).resolve())

    # Если profiles.ini не помечает Default, выбираем профиль с существующей
    # базой cookies.sqlite и самой свежей датой изменения.
    with_cookies = [path for path in candidates if (path / "cookies.sqlite").is_file()]
    if with_cookies:
        newest = max(with_cookies, key=lambda path: (path / "cookies.sqlite").stat().st_mtime)
        return str(newest.resolve())
    return ""


def parse_cookies_from_browser(value):
    """Преобразует browser или browser|profile в формат yt-dlp cookiesfrombrowser.

    Waterfox использует формат профиля Firefox, но хранит профили в отдельной
    папке. Поэтому передаём yt-dlp явный путь к профилю Waterfox.
    """
    spec = str(value or "").strip()
    if not spec:
        return None
    if "|" in spec:
        browser, profile = spec.split("|", 1)
        browser = browser.strip().casefold()
        profile = profile.strip() or None
    else:
        browser, profile = spec.casefold(), None
    if not browser:
        return None
    if browser == "waterfox":
        resolved = resolve_waterfox_profile(profile)
        if not resolved:
            raise RuntimeError(
                "Не найден профиль Waterfox. Открой Waterfox, войди в Google, затем укажи полный путь профиля "
                "из about:profiles или используй свежий cookies.txt."
            )
        browser, profile = "firefox", resolved
    return (browser, profile, None, None)



def draw_vector_icon(painter, kind, rect, color="#FFFFFF", accent=None):
    """Рисует интерфейсные значки средствами Qt: не зависит от emoji-шрифтов Windows."""
    color = QColor(color)
    accent = QColor(accent) if accent else QColor(color)
    painter.save()
    painter.translate(rect.center())
    side = max(1.0, min(float(rect.width()), float(rect.height())))
    painter.scale(side / 32.0, side / 32.0)
    pen = QPen(color, 2.35)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    def star_path(cx, cy, outer, inner):
        points = []
        for i in range(8):
            angle = -math.pi / 2 + i * math.pi / 4
            radius = outer if i % 2 == 0 else inner
            points.append(QPointF(cx + math.cos(angle) * radius,
                                  cy + math.sin(angle) * radius))
        path = QPainterPath()
        path.addPolygon(QPolygonF(points))
        path.closeSubpath()
        return path

    kind = str(kind or "music").casefold().replace("_", "-")
    if kind in ("play", "youtube"):
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawPolygon(QPolygonF([QPointF(-6, -10), QPointF(-6, 10), QPointF(10, 0)]))
    elif kind in ("arrow-right", "open"):
        painter.setPen(QPen(color, 3, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawLine(QPointF(-10, 0), QPointF(10, 0))
        painter.drawLine(QPointF(3, -7), QPointF(10, 0))
        painter.drawLine(QPointF(3, 7), QPointF(10, 0))
    elif kind in ("cloud", "soundcloud"):
        path = QPainterPath()
        path.moveTo(-12, 7)
        path.cubicTo(-15, 7, -16, 3, -14, 0)
        path.cubicTo(-13, -3, -10, -4, -7, -3)
        path.cubicTo(-5, -11, 6, -12, 9, -5)
        path.cubicTo(16, -5, 17, 3, 13, 6)
        path.cubicTo(12, 7, 10, 7, 8, 7)
        path.closeSubpath()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawPath(path)
    elif kind in ("heart", "likes", "favorite", "heart-filled"):
        path = QPainterPath()
        path.moveTo(0, 13)
        path.cubicTo(-2, 11, -13, 3, -13, -4)
        path.cubicTo(-13, -12, -4, -14, 0, -7)
        path.cubicTo(4, -14, 13, -12, 13, -4)
        path.cubicTo(13, 3, 2, 11, 0, 13)
        path.closeSubpath()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawPath(path)
    elif kind in ("heart-outline", "favorite-outline"):
        path = QPainterPath()
        path.moveTo(0, 13)
        path.cubicTo(-2, 11, -13, 3, -13, -4)
        path.cubicTo(-13, -12, -4, -14, 0, -7)
        path.cubicTo(4, -14, 13, -12, 13, -4)
        path.cubicTo(13, 3, 2, 11, 0, 13)
        path.closeSubpath()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(pen)
        painter.drawPath(path)
    elif kind in ("headphones", "daily-mix"):
        path = QPainterPath()
        path.moveTo(-11, 5)
        path.cubicTo(-12, -13, 12, -13, 11, 5)
        painter.setPen(QPen(color, 3.0, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawPath(path)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(accent)
        painter.drawRoundedRect(QRectF(-15, 1, 6, 12), 2, 2)
        painter.drawRoundedRect(QRectF(9, 1, 6, 12), 2, 2)
        painter.setBrush(color)
        painter.drawRoundedRect(QRectF(-13, 3, 2, 8), 1, 1)
        painter.drawRoundedRect(QRectF(11, 3, 2, 8), 1, 1)
    elif kind in ("wand", "supermix", "magic"):
        painter.setPen(QPen(color, 3.0, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawLine(QPointF(-11, 12), QPointF(10, -9))
        painter.setPen(QPen(accent, 1.7, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawLine(QPointF(-13, 10), QPointF(-9, 14))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(accent)
        painter.drawPath(star_path(11, -12, 4.2, 1.8))
        painter.drawPath(star_path(-12, -8, 3.0, 1.2))
        painter.drawPath(star_path(11, 8, 2.7, 1.1))
    elif kind in ("sparkle", "discover", "new", "✨"):
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawPath(star_path(-2, 1, 12, 4.1))
        painter.setBrush(accent)
        painter.drawPath(star_path(10, -10, 5.0, 1.8))
        painter.drawPath(star_path(-11, 10, 4.2, 1.5))
    elif kind in ("moon", "chill", "☾"):
        path = QPainterPath()
        path.moveTo(7, -13)
        path.cubicTo(-5, -10, -8, 5, 3, 12)
        path.cubicTo(-7, 13, -14, 5, -13, -3)
        path.cubicTo(-12, -11, -2, -16, 7, -13)
        path.closeSubpath()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawPath(path)
    elif kind in ("flame", "fire", "🔥"):
        path = QPainterPath()
        path.moveTo(0, 14)
        path.cubicTo(-10, 13, -13, 4, -7, -3)
        path.cubicTo(-7, 3, -2, 2, -3, -8)
        path.cubicTo(5, -3, 8, 2, 6, 6)
        path.cubicTo(12, 1, 9, -5, 9, -6)
        path.cubicTo(18, 3, 11, 14, 0, 14)
        path.closeSubpath()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawPath(path)
        inner = QPainterPath()
        inner.moveTo(0, 10)
        inner.cubicTo(-4, 7, -2, 3, 1, 0)
        inner.cubicTo(5, 4, 5, 7, 0, 10)
        inner.closeSubpath()
        painter.setBrush(accent)
        painter.drawPath(inner)
    elif kind in ("mixer", "equalizer", "🎛"):
        painter.setPen(QPen(color, 2.2, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        for x, y in ((-8, -5), (0, 5), (8, -1)):
            painter.drawLine(QPointF(x, -12), QPointF(x, 12))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(accent)
            painter.drawEllipse(QPointF(x, y), 3.0, 3.0)
            painter.setPen(QPen(color, 2.2, Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    elif kind in ("plus", "add"):
        painter.setPen(QPen(color, 2.8, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawLine(QPointF(-9, 0), QPointF(9, 0))
        painter.drawLine(QPointF(0, -9), QPointF(0, 9))
    else:  # универсальная нота — надёжная замена отсутствующему символу
        painter.setPen(QPen(color, 2.6, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawLine(QPointF(5, -12), QPointF(5, 7))
        painter.drawLine(QPointF(5, -12), QPointF(12, -14))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(QRectF(-8, 5, 10, 7))
        painter.drawEllipse(QRectF(1, 3, 9, 7))
    painter.restore()


class SpotifyPlaylistCard(QPushButton):
    """Карточка быстрого старта с рисуемым градиентом и мягкой подсветкой."""
    def __init__(self, title, subtitle, symbol, color_a, color_b, parent=None, cover_url="", action_icon="play", artwork_style=""):
        super().__init__(parent)
        self.title = title
        self.subtitle = subtitle
        self.action_icon = action_icon
        self.artwork_style = artwork_style
        self._artwork = self._make_artwork(artwork_style) if artwork_style else None
        self.symbol = symbol
        self.color_a = QColor(color_a)
        self.color_b = QColor(color_b)
        self._hover = 0.0
        self.cover_url = cover_url
        self._cover_pixmap = None
        self.setObjectName("startCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(172)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAccessibleName(f"{title}: {subtitle}")
        self.setToolTip(f"{title} — {subtitle}")
        self.setStyleSheet("QPushButton#startCard { background: transparent; border: none; padding: 0; }")
        self._hover_animation = QVariantAnimation(self)
        self._hover_animation.setDuration(190)
        self._hover_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._hover_animation.valueChanged.connect(self._set_hover)

    def set_cover(self, pixmap):
        self._cover_pixmap = pixmap if pixmap is not None and not pixmap.isNull() else None
        self.update()

    def _set_hover(self, value):
        self._hover = float(value)
        self.update()

    def enterEvent(self, event):
        self._hover_animation.stop()
        self._hover_animation.setStartValue(self._hover)
        self._hover_animation.setEndValue(1.0)
        self._hover_animation.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover_animation.stop()
        self._hover_animation.setStartValue(self._hover)
        self._hover_animation.setEndValue(0.0)
        self._hover_animation.start()
        super().leaveEvent(event)

    @staticmethod
    def _blend(a, b, amount):
        amount = max(0.0, min(1.0, amount))
        return QColor(
            round(a.red() * (1 - amount) + b.red() * amount),
            round(a.green() * (1 - amount) + b.green() * amount),
            round(a.blue() * (1 - amount) + b.blue() * amount),
            round(a.alpha() * (1 - amount) + b.alpha() * amount),
        )

    @staticmethod
    def _make_artwork(style):
        """Квадратная обложка рисуется один раз и работает без внешних картинок."""
        size = 384
        image = QPixmap(size, size)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(0, 0, size, size)
        clip = QPainterPath()
        clip.addRoundedRect(rect, 24, 24)
        painter.setClipPath(clip)
        colors = {
            "likes": ("#352684", "#AD65EF"),
            "soundcloud-likes": ("#FD5C26", "#712657"),
            "supermix": ("#EC412B", "#F5AF45"),
            "shuffle": ("#123959", "#29CEBA"),
        }
        first, last = colors.get(style, colors["likes"])
        gradient = QLinearGradient(0, 0, size, size)
        gradient.setColorAt(0, QColor(first))
        gradient.setColorAt(1, QColor(last))
        painter.fillRect(rect, gradient)
        painter.setPen(Qt.PenStyle.NoPen)
        glow = QRadialGradient(QPointF(300, 50), 330)
        glow.setColorAt(0, QColor(255, 255, 255, 100))
        glow.setColorAt(1, QColor(255, 255, 255, 0))
        painter.fillRect(rect, glow)

        if style == "supermix":
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for index in range(9):
                painter.setPen(QPen(QColor(80, 13, 40, 130), 11))
                radius = 46 + index * 31
                painter.drawEllipse(QPointF(340, 45), radius, radius)
            painter.setPen(QColor("#FFF5E8"))
            font = QFont("Arial", 60, QFont.Weight.Black)
            painter.setFont(font)
            painter.drawText(QRectF(24, 122, 342, 96), Qt.AlignmentFlag.AlignLeft, "SUPER")
            painter.drawText(QRectF(24, 202, 342, 96), Qt.AlignmentFlag.AlignLeft, "MIX")
        elif style == "shuffle":
            painter.save()
            painter.translate(190, 190)
            painter.rotate(-28)
            for index in range(7):
                shade = QColor("#B8FFE8") if index % 2 == 0 else QColor("#117C87")
                shade.setAlpha(125)
                painter.setBrush(shade)
                painter.drawRoundedRect(QRectF(-280, -230 + index * 67, 560, 37), 18, 18)
            painter.restore()
            draw_vector_icon(painter, "headphones", QRectF(100, 96, 184, 184), "#FFFFFF")
        else:
            painter.setBrush(QColor(255, 255, 255, 16))
            for center, radius in ((QPointF(25, 370), 180), (QPointF(340, 25), 126)):
                painter.drawEllipse(center, radius, radius)
            draw_vector_icon(painter, "heart", QRectF(102, 92, 180, 180), "#FFFFFF")

        painter.setPen(QColor(255, 255, 255, 205))
        painter.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        footer = {"likes": "LIKED MUSIC", "soundcloud-likes": "YOUR LIKES",
                  "supermix": "MADE FROM YOUR LIKES", "shuffle": "ON REPEAT"}.get(style, "MUSIC")
        painter.drawText(QRectF(26, 333, 340, 26), Qt.AlignmentFlag.AlignLeft, footer)
        painter.end()
        return image

    def _paint_artwork_card(self):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if not self.isEnabled():
            painter.setOpacity(0.6)
        bounds = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(bounds, 14, 14)
        painter.fillPath(path, QColor("#242427" if self._hover > 0 else "#1E1E21"))
        painter.setPen(QPen(QColor(255, 255, 255, int(15 + 32 * self._hover)), 1))
        painter.drawPath(path)
        side = min(112.0, bounds.height() - 28)
        cover = QRectF(bounds.left() + 14, bounds.center().y() - side / 2, side, side)
        painter.drawPixmap(cover, self._artwork, QRectF(self._artwork.rect()))
        left = cover.right() + 22
        width = max(24.0, bounds.right() - left - 74)
        title_font = QFont(self.font().family(), 15, QFont.Weight.Bold)
        painter.setFont(title_font)
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(QRectF(left, bounds.center().y() - 29, width, 32),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         QFontMetrics(title_font).elidedText(self.title, Qt.TextElideMode.ElideRight, int(width)))
        detail_font = QFont(self.font().family(), 9)
        painter.setFont(detail_font)
        painter.setPen(QColor("#B8B8BE"))
        painter.drawText(QRectF(left, bounds.center().y() + 9, width, 23),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         QFontMetrics(detail_font).elidedText(self.subtitle, Qt.TextElideMode.ElideRight, int(width)))
        button = QRectF(bounds.right() - 56, bounds.center().y() - 20, 40, 40)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawEllipse(button)
        draw_vector_icon(painter, self.action_icon, button.adjusted(11, 11, -11, -11), "#171719")
        painter.end()

    def paintEvent(self, event):
        if self._artwork is not None:
            self._paint_artwork_card()
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        bounds = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
        radius = 16.0
        # Цвет подсветки соответствует источнику/плейлисту: зелёный для YouTube,
        # огненно-оранжевый для SoundCloud и собственный акцент для личных карточек.
        accent = self.color_a
        start = self._blend(self.color_a, QColor("#FFFFFF"), 0.02 + 0.10 * self._hover)
        end = self._blend(self.color_b, accent, 0.04 + 0.12 * self._hover)
        gradient = QLinearGradient(bounds.topLeft(), bounds.bottomRight())
        gradient.setColorAt(0.0, start)
        gradient.setColorAt(0.58, self._blend(start, end, 0.58))
        gradient.setColorAt(1.0, end)
        path = QPainterPath()
        path.addRoundedRect(bounds, radius, radius)
        painter.fillPath(path, QBrush(gradient))
        if self._cover_pixmap is not None and not self._cover_pixmap.isNull():
            painter.save()
            painter.setClipPath(path)
            source = self._cover_pixmap
            target = source.scaled(int(bounds.width()), int(bounds.height()),
                                   Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                   Qt.TransformationMode.SmoothTransformation)
            image_rect = QRectF(bounds.center().x() - target.width() / 2,
                                bounds.center().y() - target.height() / 2,
                                target.width(), target.height())
            painter.drawPixmap(image_rect, target, QRectF(target.rect()))
            overlay = QLinearGradient(bounds.bottomLeft(), bounds.topLeft())
            overlay.setColorAt(0.0, QColor(0, 0, 0, 210))
            overlay.setColorAt(0.5, QColor(0, 0, 0, 60))
            overlay.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.fillPath(path, QBrush(overlay))
            painter.restore()

        # Мягкое свечение в верхнем правом углу — без тяжёлых эффектов графической сцены.
        glow = QRadialGradient(QPointF(bounds.right() - 8, bounds.top() + 5), bounds.width() * 0.78)
        glow.setColorAt(0.0, QColor(255, 255, 255, int(15 + 22 * self._hover)))
        glow.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.fillPath(path, QBrush(glow))

        border = QColor(accent.red(), accent.green(), accent.blue(), int(65 + 170 * self._hover))
        painter.setPen(QPen(border, 1.0 + self._hover * 1.15))
        painter.drawPath(path)

        # Иконки рисуются векторно самим Qt. Emoji-шрифт Windows часто отсутствует
        # или не умеет отображать цветные глифы в QPainter, из-за чего появлялись □.
        icon_size = 62.0
        icon_rect = QRectF(bounds.left() + 20, bounds.center().y() - icon_size / 2,
                           icon_size, icon_size)
        icon_bg = QColor(0, 0, 0, int(35 + 22 * self._hover))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(icon_bg)
        painter.drawRoundedRect(icon_rect, 15, 15)
        symbol = str(self.symbol or "")
        if symbol in ("🪄", "wand", "magic"):
            icon_kind = "wand"
        elif symbol in ("🎧", "headphones"):
            icon_kind = "headphones"
        elif symbol in ("✨", "sparkle"):
            icon_kind = "sparkle"
        elif symbol in ("☾", "🌙", "moon"):
            icon_kind = "moon"
        elif symbol in ("♥", "♡", "❤️", "heart"):
            icon_kind = "heart"
        elif symbol in ("🔥", "fire", "flame"):
            icon_kind = "flame"
        elif symbol in ("🎛", "mixer", "equalizer"):
            icon_kind = "mixer"
        elif symbol in ("＋", "+", "add"):
            icon_kind = "plus"
        else:
            icon_kind = "music"
        draw_vector_icon(painter, icon_kind, icon_rect.adjusted(13, 13, -13, -13),
                         "#FFFFFF", accent=accent)

        text_x = icon_rect.right() + 18
        text_width = max(60.0, bounds.right() - text_x - 52)
        title_font = QFont(self.font().family(), 15)
        title_font.setWeight(QFont.Weight.Bold)
        painter.setFont(title_font)
        painter.setPen(QColor("#FFFFFF"))
        title_rect = QRectF(text_x, bounds.center().y() - 20, text_width, 30)
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         QFontMetrics(title_font).elidedText(self.title, Qt.TextElideMode.ElideRight, int(text_width)))

        subtitle_font = QFont(self.font().family(), 9)
        painter.setFont(subtitle_font)
        painter.setPen(QColor(242, 246, 243, 210))
        subtitle_rect = QRectF(text_x, bounds.center().y() + 12, text_width, 22)
        painter.drawText(subtitle_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         QFontMetrics(subtitle_font).elidedText(self.subtitle, Qt.TextElideMode.ElideRight, int(text_width)))

        # Круглая кнопка Play появляется с мягким контрастом при наведении.
        play_alpha = int(165 + 90 * self._hover)
        play_rect = QRectF(bounds.right() - 48, bounds.center().y() - 19, 38, 38)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(accent.red(), accent.green(), accent.blue(), play_alpha))
        painter.drawEllipse(play_rect)
        draw_vector_icon(painter, self.action_icon, play_rect.adjusted(10, 10, -10, -10), "#102016")
        painter.end()

# -------------------------------------------------------------
# Фоновый поиск: по умолчанию просим 50 результатов вместо 12.
# scsearchN и ytsearchN/ytsearchdateN поддерживаются yt-dlp.
# Фактическое число может оказаться меньше, если сайт ограничил выдачу.
# -------------------------------------------------------------

class SearchWorker(QThread):
    """Поиск в фоне: сначала быстрые результаты, затем расширенная выдача.

    Важно: поиск не может заставить YouTube/SoundCloud отвечать быстрее, но
    небольшой первый запрос уменьшает время до первых видимых результатов.
    """
    results_ready = pyqtSignal(list, str)
    failed = pyqtSignal(str)

    # Быстрый кэш в памяти и постоянный кэш метаданных на диске.
    # Сохраняются только карточки треков (web URL/название/артист/обложка),
    # но не временные аудиоссылки, cookies или данные авторизации.
    _cache = {}
    _disk_cache = {}
    _cache_lock = threading.RLock()
    _cache_ttl = 600
    _disk_cache_ttl = 30 * 60
    _disk_cache_max_entries = 250
    _disk_cache_loaded = False
    _disk_cache_version = 1

    def __init__(self, query, source, sort_mode, limit, parent=None,
                 direct_url=None, cookie_file=None, cookies_from_browser=None,
                 cache_enabled=True, paginate_all=False, max_total=10000,
                 artist_filter=None, artist_catalog=False):
        super().__init__(parent)
        self.query = str(query or "").strip()
        self.source = source
        self.sort_mode = sort_mode
        self.limit = max(1, int(limit))
        self.direct_url = str(direct_url or "").strip()
        self.cookie_file = str(cookie_file or "").strip()
        self.cookies_from_browser = str(cookies_from_browser or "").strip()
        self.cache_enabled = bool(cache_enabled) and not bool(self.direct_url)
        self.paginate_all = bool(paginate_all)
        self.max_total = max(self.limit, int(max_total or 10000))
        self.artist_filter = str(artist_filter or "").strip()
        # Для профилей YouTube используем каталог YouTube Music (ytmusicapi),
        # а не /videos у канала: там могут быть перезаливы и посторонние ролики.
        self.artist_catalog = bool(artist_catalog and source == "youtube" and self.artist_filter)
        self.pagination_done = False
        self.pagination_count = 0
        self.pagination_note = ""
        self._cancel_requested = False

    def cancel(self):
        # yt-dlp не всегда можно прервать посреди сетевого запроса,
        # но worker проверит флаг сразу после его завершения.
        self._cancel_requested = True

    def _prefix(self, limit):
        query = self.query.strip()
        if self.source == "soundcloud":
            return f"scsearch{limit}:{query}"
        if self.sort_mode == "latest":
            return f"ytsearchdate{limit}:{query}"
        return f"ytsearch{limit}:{query}"

    def _cache_key(self):
        # Профиль каталога, запасной поиск и обычная выдача — разные кэши.
        return (self.source, self.direct_url or self.query.casefold(), self.sort_mode,
                self.artist_filter.casefold(), self.artist_catalog)

    @classmethod
    def _ensure_disk_cache_loaded(cls):
        """Однократно читает сохранённые результаты; вызывается из фонового worker."""
        with cls._cache_lock:
            if cls._disk_cache_loaded:
                return
            try:
                cache_file = app_cache_directory() / "search_cache_v1.json"
                payload = json.loads(cache_file.read_text(encoding="utf-8"))
                cls._disk_cache_loaded = True
                if not isinstance(payload, dict) or payload.get("version") != cls._disk_cache_version:
                    return
                now = time.time()
                for entry in payload.get("entries", []):
                    if not isinstance(entry, dict):
                        continue
                    raw_key = entry.get("key")
                    raw_tracks = entry.get("tracks")
                    try:
                        key = tuple(raw_key)
                        limit = max(1, int(entry.get("limit", 1)))
                        saved_at = float(entry.get("saved_at", 0))
                    except (TypeError, ValueError):
                        continue
                    age = now - saved_at
                    if (len(key) != 5 or age < 0 or age > cls._disk_cache_ttl
                            or not isinstance(raw_tracks, list)):
                        continue
                    tracks = [dict(track) for track in raw_tracks
                              if isinstance(track, dict) and str(track.get("url") or "").startswith(("https://", "http://"))]
                    if not tracks:
                        continue
                    cls._disk_cache[key] = {
                        "tracks": tracks,
                        "limit": limit,
                        "saved_at_wall": saved_at,
                    }
                if len(cls._disk_cache) > cls._disk_cache_max_entries:
                    newest = sorted(cls._disk_cache.items(),
                                    key=lambda pair: pair[1].get("saved_at_wall", 0), reverse=True)
                    cls._disk_cache = dict(newest[:cls._disk_cache_max_entries])
            except FileNotFoundError:
                cls._disk_cache_loaded = True
                return
            except (OSError, json.JSONDecodeError, TypeError, ValueError) as error:
                logging.getLogger("aurora").info(f"[Music Player] Не удалось прочитать постоянный кэш поиска: {error}")

    def _read_cache(self):
        cls = self.__class__
        cls._ensure_disk_cache_loaded()
        key = self._cache_key()
        now_mono = time.monotonic()
        now_wall = time.time()
        with cls._cache_lock:
            cached = cls._cache.get(key)
            if cached:
                age = now_mono - cached.get("saved_at", 0)
                if 0 <= age <= cls._cache_ttl:
                    return {"tracks": [dict(track) for track in cached["tracks"]],
                            "limit": cached["limit"], "is_fresh": True}
                cls._cache.pop(key, None)

            cached = cls._disk_cache.get(key)
            if not cached:
                return None
            age = now_wall - cached.get("saved_at_wall", 0)
            if age < 0 or age > cls._disk_cache_ttl:
                cls._disk_cache.pop(key, None)
                return None

            # Возвращаем даже более старый (но ещё допустимый) кэш сразу,
            # а затем run() обновит его в фоне. Возраст памяти не обнуляется.
            cls._cache[key] = {
                "tracks": [dict(track) for track in cached["tracks"]],
                "limit": cached["limit"],
                "saved_at": now_mono - age,
            }
            return {"tracks": [dict(track) for track in cached["tracks"]],
                    "limit": cached["limit"], "is_fresh": age <= cls._cache_ttl}

    def _write_cache(self, tracks, fetched_limit):
        cls = self.__class__
        cls._ensure_disk_cache_loaded()
        clean_tracks = [dict(track) for track in tracks
                        if isinstance(track, dict) and str(track.get("url") or "").startswith(("https://", "http://"))]
        if not clean_tracks:
            return
        key = self._cache_key()
        now_mono = time.monotonic()
        now_wall = time.time()
        cache_file = app_cache_directory() / "search_cache_v1.json"
        with cls._cache_lock:
            cls._cache[key] = {
                "tracks": [dict(track) for track in clean_tracks],
                "limit": int(fetched_limit),
                "saved_at": now_mono,
            }
            cls._disk_cache[key] = {
                "tracks": [dict(track) for track in clean_tracks],
                "limit": int(fetched_limit),
                "saved_at_wall": now_wall,
            }
            # Ограничиваем объём и памяти, и файла кэша.
            if len(cls._cache) > cls._disk_cache_max_entries:
                oldest_key = min(cls._cache, key=lambda cache_key: cls._cache[cache_key].get("saved_at", 0))
                cls._cache.pop(oldest_key, None)
            if len(cls._disk_cache) > cls._disk_cache_max_entries:
                oldest_key = min(cls._disk_cache, key=lambda cache_key: cls._disk_cache[cache_key].get("saved_at_wall", 0))
                cls._disk_cache.pop(oldest_key, None)

            entries = [{
                "key": list(cache_key),
                "tracks": value["tracks"],
                "limit": value["limit"],
                "saved_at": value["saved_at_wall"],
            } for cache_key, value in cls._disk_cache.items()]
            payload = {"version": cls._disk_cache_version, "entries": entries}
            try:
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                temp_file = cache_file.with_suffix(".tmp")
                temp_file.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                                     encoding="utf-8")
                temp_file.replace(cache_file)
            except (OSError, TypeError, ValueError) as error:
                # Поиск остаётся рабочим даже если профиль пользователя read-only.
                logging.getLogger("aurora").info(f"[Music Player] Не удалось сохранить постоянный кэш поиска: {error}")

    def _make_track(self, entry, visited):
        if not isinstance(entry, dict):
            return None
        identifier = str(entry.get("id") or "")
        url = str(entry.get("webpage_url") or entry.get("permalink_url")
                  or entry.get("original_url") or entry.get("url") or "")
        if self.source == "youtube":
            if not url.startswith(("https://", "http://")):
                url = f"https://www.youtube.com/watch?v={identifier or url}"
        elif "soundcloud:tracks:" in url or not url.startswith(("https://", "http://")):
            return None
        if not url.startswith(("https://", "http://")) or url in visited:
            return None
        visited.add(url)

        thumbnails = entry.get("thumbnails") or []
        thumbnail = (entry.get("thumbnail") or entry.get("artwork_url")
                     or entry.get("image") or entry.get("cover_url") or "")
        if not thumbnail:
            # В некоторых версиях yt-dlp обложка приходит только в thumbnails.
            usable = [image for image in thumbnails
                      if isinstance(image, dict) and image.get("url")]
            if usable:
                usable.sort(key=lambda image: (image.get("width") or 0) * (image.get("height") or 0))
                thumbnail = usable[-1].get("url", "")
        thumbnail = normalize_artwork_url(thumbnail)
        if not thumbnail and self.source == "youtube" and identifier:
            thumbnail = f"https://i.ytimg.com/vi/{identifier}/mqdefault.jpg"

        # Keep true artist credits separate from channel/uploader metadata.  In flat
        # YouTube results, uploader is often only the channel that uploaded a track.
        explicit_artist = entry.get("artist") or entry.get("artists")

        def names_from(value):
            if value is None or value == "":
                return []
            if isinstance(value, dict):
                value = value.get("username") or value.get("name") or value.get("artist") or value.get("title")
                return [str(value).strip()] if value else []
            if isinstance(value, (list, tuple, set)):
                output = []
                for part in value:
                    if isinstance(part, dict):
                        part = part.get("name") or part.get("artist") or part.get("title")
                    if part:
                        output.append(str(part).strip())
                return list(dict.fromkeys(output))
            return [str(value).strip()] if str(value).strip() else []

        explicit_artist_names = names_from(explicit_artist)
        uploader_name = str(entry.get("uploader") or entry.get("username") or "").strip()
        channel_name = str(entry.get("channel") or "").strip()
        creator_name = str(entry.get("creator") or "").strip()
        display_artist = (", ".join(explicit_artist_names) if explicit_artist_names else
                          uploader_name or channel_name or creator_name or
                          str(entry.get("uploader_id") or entry.get("channel_id") or "Исполнитель неизвестен"))

        views = entry.get("view_count")
        if views is None:
            views = entry.get("play_count", entry.get("playback_count"))
        try:
            views = int(views) if views is not None else None
        except (TypeError, ValueError):
            views = None

        return {
            "title": entry.get("title") or "Без названия",
            "video_id": identifier if self.source == "youtube" else "",
            "artist": str(display_artist),
            # Metadata used for reliable artist-profile matching.  These fields are
            # deliberately not merged: an uploader/channel is not always the artist.
            "artist_metadata": explicit_artist_names,
            "uploader": uploader_name,
            "channel": channel_name,
            "creator": creator_name,
            "artist_id": str(entry.get("artist_id") or ""),
            "artist_url": str(entry.get("artist_url") or ""),
            "uploader_id": str(entry.get("uploader_id") or ""),
            "uploader_url": str(entry.get("uploader_url") or ""),
            "channel_id": str(entry.get("channel_id") or ""),
            "channel_url": str(entry.get("channel_url") or ""),
            "url": url,
            "thumbnail": thumbnail,
            "artist_thumbnail": normalize_artwork_url(
                entry.get("channel_thumbnail") or entry.get("uploader_thumbnail")
                or entry.get("uploader_avatar") or entry.get("avatar_url") or ""
            ),
            "duration": entry.get("duration") or 0,
            "view_count": views,
            "timestamp": extract_date(entry),
            "source": self.source,
        }

    @staticmethod
    def _normalize_artist_name(value):
        """Нормализует имя для сопоставления без регистра и суффиксов каналов."""
        text = unicodedata.normalize("NFKC", str(value or "")).casefold().strip()
        text = re.sub(r"\s*[-–—|]\s*(topic|official|vevo)(?:\s+.*)?$", " ", text)
        text = re.sub(r"\b(official audio|official video|music video|lyrics video|lyrics|audio|video|topic|vevo)\b", " ", text)
        text = text.replace("&", " and ")
        text = re.sub(r"[^\w]+", " ", text, flags=re.UNICODE)
        return " ".join(text.split())

    @staticmethod
    def _artist_credit_parts(value):
        """Splits explicit collaboration credits into individual artist names."""
        value = str(value or "").strip()
        if not value:
            return []
        parts = re.split(r"\s*(?:,|&|\band\b|\bfeat(?:uring)?\.?\b|\bft\.?\b|\bwith\b)\s*", value, flags=re.IGNORECASE)
        return [part.strip() for part in parts if part.strip()]

    def _matches_artist_filter(self, track):
        """Strict profile matching: prefer artist credits and exact channel names.

        Never accept an arbitrary substring of the uploader or title.  That old
        behavior is what let unrelated uploads leak into artist pages.
        """
        requested = self._normalize_artist_name(self.artist_filter)
        if not requested:
            return True

        def is_exact_name(value):
            normalized = self._normalize_artist_name(value)
            if not normalized:
                return False
            if normalized == requested:
                return True
            # Match only a complete artist inside an explicit collaboration credit.
            return any(self._normalize_artist_name(part) == requested
                       for part in self._artist_credit_parts(value))

        # Explicit artist / artists metadata is the strongest evidence.
        explicit_names = track.get("artist_metadata") or []
        if isinstance(explicit_names, str):
            explicit_names = [explicit_names]
        for name in explicit_names:
            if is_exact_name(name):
                return True

        # Flat extractors often expose the artist only as a Topic/official channel.
        # Normalize known suffixes, but require an exact channel/uploader match.
        for key in ("artist", "channel", "uploader", "creator"):
            value = track.get(key, "")
            if value and value != "Исполнитель неизвестен" and is_exact_name(value):
                return True

        # Title-only matching is weaker, so allow it only when the title begins with
        # a complete artist credit followed by a clear separator ("Artist - Track").
        raw_title = str(track.get("title") or "").strip()
        credit = re.split(r"\s+[–—|:]\s+|\s+-\s+", raw_title, maxsplit=1)[0].strip()
        if credit and is_exact_name(credit):
            return True
        return False

    def _fetch_youtube_music_artist_catalog(self, limit):
        """Загружает песни из каталога артиста YouTube Music, а не из /videos.

        ytmusicapi — необязательная зависимость. Если она отсутствует или каталог
        временно недоступен, run() использует строгий запасной поиск yt-dlp и
        обязательно сообщает об этом в статусе, не выдавая его за каталог YTM.
        """
        from ytmusicapi import YTMusic

        requested_name = str(self.artist_filter or self.query or "").strip()
        requested_norm = self._normalize_artist_name(requested_name)
        if not requested_norm:
            raise RuntimeError("Не задано имя исполнителя для каталога YouTube Music.")

        ytm = YTMusic()
        artist_results = ytm.search(requested_name, filter="artists", limit=15) or []

        def result_artist_name(item):
            return str(item.get("artist") or item.get("title") or item.get("name") or "").strip()

        # Не берём первого похожего артиста: нужен нормализованный точный матч.
        exact = [item for item in artist_results
                 if self._normalize_artist_name(result_artist_name(item)) == requested_norm
                 and item.get("browseId")]
        if not exact:
            available = ", ".join(result_artist_name(item) for item in artist_results[:5]
                                  if result_artist_name(item))
            detail = f" Найдены варианты: {available}." if available else ""
            raise LookupError(
                f"В каталоге YouTube Music не найдено точного совпадения для «{requested_name}»." + detail
            )

        selected_artist = exact[0]
        artist_browse_id = str(selected_artist.get("browseId") or "").strip()
        artist_info = ytm.get_artist(artist_browse_id) or {}
        canonical_name = str(artist_info.get("name") or result_artist_name(selected_artist) or requested_name).strip()
        songs_section = artist_info.get("songs") if isinstance(artist_info.get("songs"), dict) else {}
        raw_entries = list(songs_section.get("results") or [])
        note = ""

        # `songs.browseId` ведёт на официальный список песен артиста. Запрашиваем
        # его расширенную версию, сохраняя порядок каталога (обычно популярность).
        songs_browse_id = str(songs_section.get("browseId") or "").strip()
        if songs_browse_id:
            try:
                playlist_data = ytm.get_playlist(songs_browse_id, limit=max(1, min(int(limit), 200))) or {}
                playlist_tracks = playlist_data.get("tracks") if isinstance(playlist_data, dict) else None
                if playlist_tracks:
                    raw_entries = list(playlist_tracks)
                elif raw_entries:
                    note = "Каталог вернул только верхние песни артиста; полный список недоступен."
            except Exception as error:
                if raw_entries:
                    note = "Не удалось раскрыть полный список песен; показаны песни из шапки каталога."
                else:
                    raise RuntimeError(f"Не удалось загрузить песни артиста из YouTube Music: {error}") from error

        if not raw_entries:
            raise LookupError(f"YouTube Music не вернул список песен для артиста «{canonical_name}».")

        def pick_thumbnail(value):
            if isinstance(value, dict):
                value = value.get("thumbnails") or value.get("thumbnail") or []
            if isinstance(value, str):
                return normalize_artwork_url(value)
            if not isinstance(value, (list, tuple)):
                return ""
            candidates = [item for item in value if isinstance(item, dict) and item.get("url")]
            if not candidates:
                return ""
            candidates.sort(key=lambda item: (item.get("width") or 0) * (item.get("height") or 0))
            return normalize_artwork_url(candidates[-1].get("url"))

        def duration_seconds(entry):
            raw_seconds = entry.get("duration_seconds")
            try:
                if raw_seconds is not None:
                    return max(0, int(float(raw_seconds)))
            except (TypeError, ValueError):
                pass
            raw = str(entry.get("duration") or "").strip()
            if raw and re.fullmatch(r"\d{1,2}:\d{2}(?::\d{2})?", raw):
                try:
                    parts = [int(part) for part in raw.split(":")]
                    if len(parts) == 2:
                        return parts[0] * 60 + parts[1]
                    return parts[0] * 3600 + parts[1] * 60 + parts[2]
                except (TypeError, ValueError):
                    pass
            return 0

        def artist_names(entry):
            raw = entry.get("artists") or entry.get("artist") or []
            if isinstance(raw, str):
                return [raw.strip()] if raw.strip() else []
            if isinstance(raw, dict):
                name = raw.get("name") or raw.get("artist") or raw.get("title")
                return [str(name).strip()] if name else []
            if isinstance(raw, (list, tuple)):
                names = []
                for item in raw:
                    if isinstance(item, dict):
                        item = item.get("name") or item.get("artist") or item.get("title")
                    if item and str(item).strip():
                        names.append(str(item).strip())
                return list(dict.fromkeys(names))
            return []

        def parse_count(value):
            if value is None or isinstance(value, bool):
                return None
            if isinstance(value, (int, float)):
                return max(0, int(value)) if math.isfinite(value) else None
            raw = unicodedata.normalize("NFKC", str(value)).casefold().replace("\u00a0", " ").replace("\u202f", " ").strip()
            match = re.search(r"(?<!\w)(\d[\d\s.,]*)\s*(млрд\.?|млн\.?|тыс\.?|billion|million|thousand|[kmb])?(?=\W|$)", raw)
            if not match:
                return None
            number = re.sub(r"\s+", "", match.group(1))
            suffix = (match.group(2) or "").rstrip(".")
            multiplier = {"k": 1000, "тыс": 1000, "thousand": 1000,
                          "m": 1000000, "млн": 1000000, "million": 1000000,
                          "b": 1000000000, "млрд": 1000000000, "billion": 1000000000}.get(suffix, 1)
            if "," in number and "." in number:
                decimal = "," if number.rfind(",") > number.rfind(".") else "."
                number = number.replace("." if decimal == "," else ",", "").replace(decimal, ".")
            elif "," in number or "." in number:
                sep = "," if "," in number else "."
                parts = number.split(sep)
                number = "".join(parts) if not suffix and len(parts) > 1 and all(len(x) == 3 for x in parts[1:]) else number.replace(sep, ".")
            try:
                return max(0, int(float(number) * multiplier))
            except (ValueError, OverflowError):
                return None

        artist_thumbnail = pick_thumbnail(artist_info.get("thumbnails")) or pick_thumbnail(selected_artist.get("thumbnails"))
        profile_url = f"https://music.youtube.com/channel/{artist_browse_id}"
        tracks = []
        seen_video_ids = set()
        for entry in raw_entries:
            if not isinstance(entry, dict):
                continue
            video_id = str(entry.get("videoId") or entry.get("video_id") or "").strip()
            if not video_id or video_id in seen_video_ids:
                continue
            seen_video_ids.add(video_id)
            title = str(entry.get("title") or "").strip()
            if not title:
                continue
            credited_artists = artist_names(entry)
            album_value = entry.get("album")
            if isinstance(album_value, dict):
                album_name = str(album_value.get("name") or album_value.get("title") or "").strip()
            else:
                album_name = str(album_value or "").strip()
            thumbnail = pick_thumbnail(entry.get("thumbnails"))
            if not thumbnail:
                thumbnail = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
            duration = duration_seconds(entry)
            tracks.append({
                "title": title,
                # В профиле артиста оставляем ссылку на канонического исполнителя.
                # Реальные кредиты сохраняются отдельно для подсказки/будущих функций.
                "artist": canonical_name,
                "artist_display": ", ".join(credited_artists) if credited_artists else canonical_name,
                "artist_credit": credited_artists,
                "artist_metadata": credited_artists or [canonical_name],
                "uploader": canonical_name,
                "channel": canonical_name,
                "creator": canonical_name,
                "artist_id": artist_browse_id,
                "artist_url": profile_url,
                "uploader_id": artist_browse_id,
                "uploader_url": profile_url,
                "channel_id": artist_browse_id,
                "channel_url": profile_url,
                "url": f"https://music.youtube.com/watch?v={video_id}",
                "video_id": video_id,
                "thumbnail": thumbnail,
                "artist_thumbnail": artist_thumbnail,
                "profile_artist_name": canonical_name,
                "profile_artist_id": artist_browse_id,
                "profile_artist_thumbnail": artist_thumbnail,
                "album": album_name,
                "duration": duration,
                "view_count": parse_count(entry.get("views") or entry.get("view_count")),
                "timestamp": 0,
                "source": "youtube",
                "official_catalog": True,
            })
            if len(tracks) >= int(limit):
                break

        if not tracks:
            raise LookupError(f"В каталоге YouTube Music нет доступных треков для «{canonical_name}».")
        summary = f"Каталог YouTube Music: {len(tracks)} треков артиста «{canonical_name}»; порядок сохранён из каталога."
        if note:
            summary += " " + note
        return tracks, summary

    def _sort_tracks(self, tracks):
        tracks = list(tracks)
        note = ""
        if self.sort_mode == "popular":
            if sum(track["view_count"] is not None for track in tracks) >= 2:
                tracks.sort(key=lambda track: track["view_count"] if track["view_count"] is not None else -1,
                            reverse=True)
                note = "Сортировка по доступной статистике, а не официальный рейтинг."
            else:
                note = "Источник не вернул статистику популярности; сохранён исходный порядок."
        elif self.sort_mode == "latest":
            if self.source == "soundcloud":
                if sum(bool(track["timestamp"]) for track in tracks) >= 2:
                    tracks.sort(key=lambda track: track["timestamp"], reverse=True)
                else:
                    note = "SoundCloud не передал даты для точной сортировки."
            else:
                note = "YouTube: поиск с приоритетом недавних публикаций."
        return tracks, note

    def _fetch(self, limit, mode="in_playlist", emit_progress=False, force_search=False, playlist_start=1):
        # Один сетевой запрос вместо отдельного запроса на 12 результатов и
        # повторного запроса на 25/50/100. Плоская выдача не открывает каждое видео.
        extract_flat_mode = mode
        if self.source == "soundcloud" and not self.paginate_all and not self.direct_url:
            # Обычному поиску SoundCloud достаточно плоской выдачи без структуры плейлиста.
            extract_flat_mode = True
        options = {
            **yt_dlp_tls_options(),
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "extract_flat": extract_flat_mode,
            "lazy_playlist": True,
            "ignoreerrors": True,
            "noplaylist": False,
            # playliststart/end позволяют получать следующую страницу лайков,
            # а не каждый раз останавливаться на первых 100 элементах.
            "playliststart": max(1, int(playlist_start)),
            "playlistend": max(1, int(playlist_start)) + int(limit) - 1,
            "socket_timeout": 8 if self.paginate_all else (2 if self.source == "soundcloud" else 3),
            "retries": 0 if self.source == "soundcloud" else (1 if self.paginate_all else 0),
            "extractor_retries": 0 if self.source == "soundcloud" else (1 if self.paginate_all else 0),
            "cachedir": False,
            "ignoreconfig": True,
            "youtube_include_dash_manifest": False,
            "youtube_include_hls_manifest": False,
            "no_color": True,
        }
        # Некоторые страницы SoundCloud Charts отдают HTML-страницу без списка
        # entries. Для запасного прохода разрешаем явно перейти на scsearch.
        target = self._prefix(limit) if force_search else (self.direct_url or self._prefix(limit))

        # ВАЖНО: обычный поиск и стартовые карточки публичные — cookies им не нужны.
        # Если передавать cookies браузера каждому запросу, yt-dlp может завершиться
        # с ошибкой "failed to load cookies" (например, если профиль занят браузером).
        # Авторизацию применяем только к прямым URL плейлистов/личных данных.
        auth_options = {}
        if self.direct_url and not force_search:
            if self.cookie_file:
                auth_options["cookiefile"] = self.cookie_file
            elif self.cookies_from_browser:
                auth_options["cookiesfrombrowser"] = parse_cookies_from_browser(self.cookies_from_browser)
        options.update(auth_options)

        try:
            with YoutubeDL(options) as ydl:
                data = ydl.extract_info(target, download=False)
        except Exception as error:
            error_text = str(error).casefold()
            cookie_load_failed = (
                "failed to load cookies" in error_text
                or "could not copy chrome cookie database" in error_text
                or "could not find chrome cookies database" in error_text
                or "could not find firefox cookies database" in error_text
                or "could not find browser cookies database" in error_text
                or "cookies database" in error_text
                or "cookie database" in error_text
                or "could not find firefox profile" in error_text
            )
            is_youtube_likes = (
                self.source == "youtube"
                and "list=lm" in target.casefold()
            )
            # Публичный пользовательский плейлист можно попробовать открыть без
            # cookies. Для приватного плейлиста LM не делаем вид, что импорт удался.
            if is_youtube_likes and auth_options and cookie_load_failed:
                raise RuntimeError(
                    "yt-dlp не смог прочитать cookies выбранного браузера. "
                    "Проверь, что вошёл в YouTube Music именно в этом браузере, "
                    "полностью закрой его окна и фоновые процессы, затем повтори синхронизацию. "
                    "Если профиль не найден, выбери правильный профиль браузера или используй cookies.txt. "
                    f"Подробности: {str(error).replace(chr(10), ' ')[:260]}"
                ) from error
            if not (auth_options and cookie_load_failed and not is_youtube_likes):
                raise
            fallback_options = dict(options)
            fallback_options.pop("cookiefile", None)
            fallback_options.pop("cookiesfrombrowser", None)
            with YoutubeDL(fallback_options) as ydl:
                data = ydl.extract_info(target, download=False)

        if not isinstance(data, dict) or data.get("entries") is None:
            return [], "Источник не вернул список результатов."

        tracks, visited = [], set()
        filtered_out = 0
        progress_sent = False
        progress_threshold = min(3 if self.source == "soundcloud" else 8, max(1, int(limit)))
        for entry in data.get("entries") or []:
            if self._cancel_requested:
                return tracks, "Поиск заменён новым запросом."
            track = self._make_track(entry, visited)
            if track:
                if self.artist_filter and not self._matches_artist_filter(track):
                    filtered_out += 1
                    continue
                tracks.append(track)
                # Lazy playlist может отдавать элементы постепенно. Показываем
                # первые несколько результатов до завершения полной выдачи.
                if emit_progress and not progress_sent and len(tracks) >= progress_threshold and len(tracks) < limit:
                    progress_sent = True
                    self.results_ready.emit(
                        [dict(item) for item in tracks],
                        f"Первые {len(tracks)} результатов готовы; загружаю остальные…"
                    )
        sorted_tracks, sort_note = self._sort_tracks(tracks)
        if self.artist_filter and filtered_out:
            filter_note = f"Профиль «{self.artist_filter}»: исключено {filtered_out} результатов, не совпавших с исполнителем."
            sort_note = f"{filter_note} {sort_note}".strip()
        return sorted_tracks, sort_note

    def _fetch_with_fallback(self, limit, emit_progress=False, playlist_start=1):
        # YouTube's date-search extractor can fail or return an empty playlist on
        # some yt-dlp versions. Never make the artist page unusable just because
        # the date-specific endpoint failed: retry with the normal search prefix.
        try:
            tracks, note = self._fetch(
                limit, "in_playlist", emit_progress=emit_progress, playlist_start=playlist_start
            )
        except Exception as error:
            if self.source == "youtube" and self.sort_mode == "latest" and not self.direct_url:
                tracks, note = [], str(error)
            else:
                raise

        if tracks or self._cancel_requested:
            return tracks, note

        # A channel/profile page is the most precise artist source, but some
        # extractors do not expose it as a playlist. Fall back to search while
        # keeping the strict artist metadata filter active.
        if self.direct_url and self.artist_filter and not self._cancel_requested:
            try:
                fallback_tracks, fallback_note = self._fetch(
                    limit, "in_playlist", emit_progress=emit_progress,
                    force_search=True, playlist_start=playlist_start
                )
            except Exception as error:
                fallback_tracks, fallback_note = [], str(error)
            if fallback_tracks:
                return fallback_tracks, "Профиль не отдал список напрямую; показаны совпадения по метаданным артиста."
            note = fallback_note or note

        if self.source == "youtube" and self.sort_mode == "latest" and not self.direct_url:
            original_sort = self.sort_mode
            try:
                # _prefix() now builds ytsearchN instead of ytsearchdateN.
                self.sort_mode = "relevance"
                fallback_tracks, fallback_note = self._fetch(
                    limit, "in_playlist", emit_progress=emit_progress,
                    force_search=True, playlist_start=playlist_start
                )
            except Exception as error:
                fallback_tracks, fallback_note = [], str(error)
            finally:
                self.sort_mode = original_sort

            if fallback_tracks:
                dated = [track for track in fallback_tracks if track.get("timestamp")]
                if len(dated) >= 2:
                    fallback_tracks.sort(
                        key=lambda track: track.get("timestamp") or 0, reverse=True
                    )
                    fallback_note = "Поиск по дате недоступен; результаты отсортированы по доступным датам."
                else:
                    fallback_note = "YouTube не вернул выдачу по дате; показан обычный поиск."
                return fallback_tracks, fallback_note
            # If both methods failed, report the original useful error rather than
            # pretending that a successful empty result was returned.
            note = fallback_note or note

        if self.source != "soundcloud":
            return tracks, note

        # У SoundCloud страницы /charts/top и /charts/new в некоторых версиях
        # yt-dlp распознаются как обычная веб-страница, а не плейлист. Повторный
        # запрос с тем же URL бесполезен — переключаемся на реальный scsearch.
        if self.direct_url and "/charts/" in self.direct_url.casefold():
            if self._cancel_requested:
                return [], note
            fallback_tracks, fallback_note = self._fetch(
                limit, "in_playlist", emit_progress=emit_progress, force_search=True,
                playlist_start=playlist_start
            )
            if fallback_tracks:
                return fallback_tracks, "Страница чарта недоступна в yt-dlp; показаны результаты поиска по теме."
            return [], fallback_note or note

        # Для обычного поиска SoundCloud не запускаем второй сетевой запрос:
        # он дублирует ожидание и редко приносит дополнительные результаты.
        return tracks, note

    def _run_paginated(self):
        """Последовательно читает страницы большого плейлиста и отдаёт новые треки пачками."""
        seen_urls = set()
        total = 0
        start = 1
        last_note = ""
        normal_end = True
        while start <= self.max_total and not self._cancel_requested:
            page_limit = min(self.limit, self.max_total - start + 1)
            if page_limit <= 0:
                break
            page, note = self._fetch_with_fallback(
                page_limit, emit_progress=False, playlist_start=start
            )
            last_note = note or last_note
            if self._cancel_requested:
                normal_end = False
                break
            if not page:
                if note and "не вернул список" in note.casefold():
                    normal_end = False
                break
            fresh = []
            for track in page:
                url = str(track.get("url") or "")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                fresh.append(track)
            if not fresh:
                # Если extractor игнорирует playliststart и возвращает ту же страницу,
                # прекращаем цикл, чтобы не крутить бесконечный запрос.
                break
            total += len(fresh)
            self.pagination_count = total
            self.results_ready.emit(
                [dict(track) for track in fresh], f"__SC_LIKES_PAGE__:{total}"
            )
            # Двигаемся по фактическому размеру страницы: некоторые версии
            # SoundCloud возвращают 50 записей, хотя запрошено 100.
            start += max(1, len(page))
            if total >= self.max_total:
                last_note = f"Достигнут защитный лимит {self.max_total} треков."
                break
        self.pagination_done = bool(total > 0 and normal_end and not self._cancel_requested)
        self.pagination_count = total
        self.pagination_note = last_note
        if total == 0 and not self._cancel_requested:
            self.failed.emit(last_note or "SoundCloud не вернул список лайков.")
        elif not self._cancel_requested:
            self.results_ready.emit([], f"__SC_LIKES_DONE__:{total}")

    def run(self):
        try:
            if self.paginate_all:
                self._run_paginated()
                return
            # Кэш показывает прошлую выдачу сразу; кэш каталога артиста отделён
            # от обычного yt-dlp поиска по тому же тексту.
            cached = self._read_cache() if self.cache_enabled else None
            if cached and cached["tracks"]:
                cache_needs_refresh = cached["limit"] < self.limit or not cached.get("is_fresh", True)
                self.results_ready.emit(
                    cached["tracks"][:self.limit],
                    "Результаты из кэша — обновляю в фоне…" if cache_needs_refresh
                    else "Результаты из кэша — быстрый повторный поиск."
                )
                if cached["limit"] >= self.limit and not cache_needs_refresh:
                    return

            if self._cancel_requested:
                return

            if self.artist_catalog and self.source == "youtube":
                # Не подменяем официальный каталог выдачей обычного YouTube поиска:
                # если каталог недоступен, лучше явно сообщить об этом, чем показать
                # чужие видео как песни артиста.
                try:
                    tracks, note = self._fetch_youtube_music_artist_catalog(self.limit)
                except ImportError:
                    if not self._cancel_requested:
                        self.failed.emit(
                            "Для точной карточки артиста нужна библиотека ytmusicapi. "
                            "Установи её командой: py -m pip install -U ytmusicapi"
                        )
                    return
                except Exception as error:
                    if not self._cancel_requested:
                        self.failed.emit(
                            "Не удалось загрузить точный каталог YouTube Music для артиста. "
                            "Проверь соединение и повтори попытку. Подробности: "
                            + str(error).replace("\n", " ")[:500]
                        )
                    return
                if self._cancel_requested:
                    return
                if not tracks:
                    self.failed.emit("YouTube Music не вернул песни для выбранного артиста.")
                    return
                if self.cache_enabled:
                    self._write_cache(tracks, self.limit)
                self.results_ready.emit(tracks, note or "Каталог YouTube Music загружен.")
                return
            else:
                tracks, note = self._fetch_with_fallback(self.limit, emit_progress=True)

            if self._cancel_requested:
                return
            if tracks:
                if self.cache_enabled:
                    self._write_cache(tracks, self.limit)
                self.results_ready.emit(tracks, note or "Результаты готовы.")
            elif cached and cached["tracks"]:
                # При сбое обновления не теряем уже показанный кэш.
                return
            else:
                self.results_ready.emit([], note or "Источник не вернул подходящих результатов.")
        except Exception as error:
            if not self._cancel_requested:
                self.failed.emit(str(error))


class YouTubeRatingWorker(QThread):
    """Отправляет настоящий лайк/снятие лайка в YouTube Music в фоне."""
    result_ready = pyqtSignal(object, bool, bool, str)

    def __init__(self, track, liked, auth_mode, cookie_file="", browser_spec="", parent=None):
        super().__init__(parent)
        self.track = dict(track or {})
        self.liked = bool(liked)
        self.auth_mode = str(auth_mode or "file")
        self.cookie_file = str(cookie_file or "").strip()
        self.browser_spec = str(browser_spec or "").strip()

    @staticmethod
    def _cookie_header_from_pairs(pairs):
        """Оставляет только cookies авторизации для music.youtube.com.

        Пары: (domain, name, value[, path, include_subdomains]).
        Google cookies не принадлежат домену YouTube и не должны туда отправляться.
        """
        # Приоритет важен: сначала cookies самой сессии, затем дополнительные.
        allowed = (
            "__Secure-3PAPISID", "__Secure-3PSID", "SID", "SAPISID",
            "APISID", "HSID", "SSID", "__Secure-3PSIDTS",
            "__Secure-3PSIDCC", "__Secure-1PAPISID", "__Secure-1PSID",
            "__Secure-1PSIDTS", "__Secure-1PSIDCC", "SIDCC",
        )
        selected = {}
        api_path = "/youtubei/v1/like/like"

        for pair in pairs:
            domain, name, value = pair[:3]
            path = str(pair[3] or "/") if len(pair) > 3 else "/"
            raw_domain = str(domain or "").strip().lower()
            host = raw_domain.lstrip(".")
            include_subdomains = (bool(pair[4]) if len(pair) > 4
                                  else raw_domain.startswith("."))

            # music.youtube.com получает только доменные cookies .youtube.com
            # или cookies своего собственного хоста, но не www.youtube.com,
            # accounts.google.com и т.д.
            if not (host == "music.youtube.com" or
                    (host == "youtube.com" and (include_subdomains or raw_domain.startswith(".")))):
                continue
            if not path.startswith("/") or not api_path.startswith(path):
                continue

            name = str(name or "").strip()
            value = str(value or "").strip()
            if name not in allowed or not value or len(value) > 2048:
                continue
            if any(ord(ch) < 33 or ord(ch) == 127 or ch in ";\r\n" for ch in value):
                continue

            # Cookie, установленная непосредственно для music.youtube.com,
            # имеет приоритет над общей cookie youtube.com с тем же именем.
            specificity = 1 if host == "music.youtube.com" else 0
            if name not in selected or specificity > selected[name][0]:
                selected[name] = (specificity, value)

        components = []
        total_bytes = 0
        max_cookie_bytes = 4096   # защитный лимит, а не объявленный лимит YouTube
        for name in allowed:
            if name not in selected:
                continue
            component = f"{name}={selected[name][1]}"
            addition = len(("; " if components else "").encode("ascii")) + len(component.encode("utf-8"))
            if total_bytes + addition > max_cookie_bytes:
                continue
            components.append(component)
            total_bytes += addition
        return "; ".join(components)

    def _cookies_from_file(self):
        cookie_path = Path(self.cookie_file).expanduser()
        if not cookie_path.is_file():
            raise RuntimeError("Файл cookies.txt не найден. Подключи актуальный файл авторизации YouTube Music.")
        try:
            lines = cookie_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError as error:
            raise RuntimeError(f"Не удалось прочитать cookies.txt: {error}") from error

        pairs = []
        for raw_line in lines:
            line = raw_line.strip()
            if line.startswith("#HttpOnly_"):
                line = line[len("#HttpOnly_"):]
            elif not line or line.startswith("#"):
                continue
            fields = line.split("\t", 6)
            if len(fields) != 7:
                continue
            domain, include_subdomains, path, _secure, expires, name, value = fields
            try:
                if expires and expires != "0" and float(expires) < time.time():
                    continue
            except ValueError:
                continue
            pairs.append((domain, name, value, path, include_subdomains.upper() == "TRUE"))
        return self._cookie_header_from_pairs(pairs)

    def _cookies_from_browser(self):
        if not self.browser_spec:
            raise RuntimeError("Не выбран браузерный профиль YouTube Music.")
        try:
            from yt_dlp.cookies import extract_cookies_from_browser
            browser, profile, keyring, container = parse_cookies_from_browser(self.browser_spec)
            cookie_jar = extract_cookies_from_browser(
                browser, profile, keyring=keyring, container=container
            )
            pairs = [
                (cookie.domain, cookie.name, cookie.value, cookie.path,
                 cookie.domain_initial_dot)
                for cookie in cookie_jar
                if not cookie.is_expired()
            ]
            return self._cookie_header_from_pairs(pairs)
        except Exception as error:
            raise RuntimeError(
                "Не удалось прочитать cookies выбранного браузера. Полностью закрой Waterfox и его фоновые "
                "процессы, проверь путь профиля и повтори. Если ошибка останется, подключи свежий cookies.txt. "
                f"Подробности: {str(error)[:240]}"
            ) from error

    @staticmethod
    def _video_id(track):
        if not isinstance(track, dict):
            return ""
        explicit = str(track.get("video_id") or track.get("videoId") or "").strip()
        if explicit:
            return explicit
        url = str(track.get("url") or "").strip()
        patterns = (
            r"[?&]v=([A-Za-z0-9_-]{6,})",
            r"youtu\.be/([A-Za-z0-9_-]{6,})",
            r"/(?:shorts|embed)/([A-Za-z0-9_-]{6,})",
        )
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return ""

    def run(self):
        last_http_response = {}
        try:
            video_id = self._video_id(self.track)
            if not video_id:
                raise RuntimeError("Не удалось определить YouTube video ID у выбранного трека.")

            cookie_header = (self._cookies_from_browser() if self.auth_mode == "browser"
                             else self._cookies_from_file())
            if "__Secure-3PAPISID=" not in cookie_header:
                raise RuntimeError(
                    "В cookies для music.youtube.com нет __Secure-3PAPISID. "
                    "Обнови cookies из браузера, где выполнен вход в YouTube Music."
                )
            cookie_size = len(cookie_header.encode("utf-8"))
            if cookie_size > 4096:
                raise RuntimeError(f"Слишком большой заголовок Cookie ({cookie_size} байт).")

            import requests
            from ytmusicapi import YTMusic, LikeStatus
            from ytmusicapi.helpers import get_authorization, sapisid_from_cookie, initialize_headers

            origin = "https://music.youtube.com"
            sapisid = sapisid_from_cookie(cookie_header)
            # ytmusicapi ожидает одновременно Cookie и начальный Authorization,
            # чтобы распознать BROWSER auth; затем библиотека сама обновляет
            # SAPISIDHASH при каждом обращении через client.rate_song().
            headers = {
                "user-agent": initialize_headers().get("user-agent", "Mozilla/5.0"),
                "accept": "*/*",
                "content-type": "application/json",
                "origin": origin,
                "x-origin": origin,
                "referer": origin + "/",
                "x-goog-authuser": "0",
                "cookie": cookie_header,
                "authorization": get_authorization(f"{sapisid} {origin}"),
            }
            # Не передаём вручную content-encoding, content-length,
            # x-goog-visitor-id и другие заголовки браузера.

            with requests.Session() as session:
                original_request = session.request

                def tracked_request(method, url, *args, **kwargs):
                    response = original_request(method, url, *args, **kwargs)
                    if str(method).upper() == "POST":
                        last_http_response["response"] = response
                    return response

                session.request = tracked_request
                client = YTMusic(headers, requests_session=session)
                rating = LikeStatus.LIKE if self.liked else LikeStatus.INDIFFERENT
                client.rate_song(video_id, rating)

            message = ("Лайк отправлен в аккаунт YouTube Music." if self.liked
                       else "Лайк снят в аккаунте YouTube Music.")
            self.result_ready.emit(dict(self.track), self.liked, True, message)
        except Exception as error:
            detail = str(error).replace("\n", " ")[:500]
            response = last_http_response.get("response")
            if isinstance(error, json.JSONDecodeError) and response is not None:
                if response.status_code == 413:
                    detail = (
                        "YouTube Music отклонил запрос: HTTP 413. "
                        "Заголовки или тело запроса превысили допустимый размер. "
                        "Если ошибка сохранилась после фильтрации cookies, обнови ytmusicapi "
                        "и проверь HTTP-запрос через диагностический лог."
                    )
                else:
                    body_excerpt = " ".join(str(response.text or "").split())[:180]
                    detail = (
                        f"YouTube Music вернул не-JSON ответ: HTTP {response.status_code}, "
                        f"Content-Type={response.headers.get('Content-Type', 'не указан')}; "
                        f"ответ={body_excerpt!r}"
                    )
            self.result_ready.emit(
                dict(self.track), self.liked, False,
                "Не удалось изменить лайк YouTube Music. Проверь cookies/вход в аккаунт и обнови ytmusicapi. "
                f"Подробности: {detail}"
            )


class SupermixWorker(QThread):
    """Получает рекомендации YouTube Music по нескольким понравившимся песням."""
    result_ready = pyqtSignal(list, str)
    failed = pyqtSignal(str)
    MAX_SEEDS = 3
    REQUEST_BUDGET_SECONDS = 30
    MAX_RADIO_DEPTH = 12

    def __init__(self, liked_tracks, disliked_ids=None, parent=None, limit=30):
        super().__init__(parent)
        self.liked_tracks = [dict(track) for track in liked_tracks if isinstance(track, dict)]
        self.disliked_ids = set(disliked_ids or ())
        self.limit = max(2, min(30, int(limit)))
        self._cancelled = threading.Event()

    def cancel(self):
        self._cancelled.set()

    @staticmethod
    def _artist_keys(track):
        names = track.get("artist_metadata") or []
        if isinstance(names, str):
            names = [names]
        names = [item.get("name", "") if isinstance(item, dict) else str(item) for item in names]
        names.append(str(track.get("artist") or ""))
        keys = set()
        for name in names:
            name = unicodedata.normalize("NFKC", name).casefold().strip()
            name = re.sub(r"\s*[-–—]?\s*topic$", "", name)
            key = re.sub(r"[^\w]", "", name)
            if key and key not in ("исполнительнеизвестен", "unknownartist", "variousartists"):
                keys.add(key)
        return keys

    def _artist_profile(self):
        profile, seen = {}, set()
        for track in self.liked_tracks:
            video_id = YouTubeRatingWorker._video_id(track)
            if not video_id or video_id in seen or video_id in self.disliked_ids:
                continue
            seen.add(video_id)
            for artist in self._artist_keys(track):
                profile[artist] = profile.get(artist, 0) + 1
        return profile

    def _select_seeds(self):
        candidates, seen = [], set()
        for track in self.liked_tracks:
            video_id = YouTubeRatingWorker._video_id(track)
            if video_id and video_id not in seen and video_id not in self.disliked_ids:
                candidates.append(track)
                seen.add(video_id)
        random.shuffle(candidates)
        profile = self._artist_profile()
        candidates.sort(key=lambda track: max((profile.get(key, 0) for key in self._artist_keys(track)),
                                               default=0), reverse=True)
        selected, artists = [], set()
        for track in candidates:
            artist = max(sorted(self._artist_keys(track)), key=lambda key: profile.get(key, 0), default="")
            if artist not in artists:
                selected.append(track)
                artists.add(artist)
            if len(selected) == self.MAX_SEEDS:
                return selected
        for track in candidates:
            if track not in selected:
                selected.append(track)
            if len(selected) == self.MAX_SEEDS:
                break
        return selected

    @staticmethod
    def _normalize_track(entry):
        if not isinstance(entry, dict) or entry.get("isAvailable") is False or entry.get("isPlayable") is False or entry.get("likeStatus") in ("DISLIKE", "LIKE"):
            return None
        video_id = str(entry.get("videoId") or "").strip()
        title = str(entry.get("title") or "").strip()
        if not video_id or not title:
            return None
        artists = entry.get("artists") or []
        names = [str(artist.get("name") or "").strip() for artist in artists if isinstance(artist, dict)]
        thumbnails = entry.get("thumbnail") or entry.get("thumbnails") or []
        thumbnails = [item for item in thumbnails if isinstance(item, dict) and item.get("url")]
        thumbnail = normalize_artwork_url(thumbnails[-1]["url"]) if thumbnails else ""
        duration = 0
        try:
            parts = str(entry.get("length") or "").split(":")
            for part in parts:
                duration = duration * 60 + int(part)
        except (ValueError, TypeError):
            duration = 0
        return {"source": "youtube", "video_id": video_id,
                "url": f"https://music.youtube.com/watch?v={video_id}",
                "title": title, "artist": ", ".join(filter(None, names)) or "Исполнитель неизвестен",
                "artist_metadata": list(filter(None, names)),
                "thumbnail": thumbnail, "duration": duration}

    def _rank_recommendations(self, groups):
        """Сначала знакомые исполнители; новые — только при согласии нескольких радио."""
        profile = self._artist_profile()
        candidates, artist_support = {}, {}
        for group_index, group in enumerate(groups):
            for track, position in group:
                video_id = track["video_id"]
                evidence = candidates.setdefault(video_id, {"track": track, "position": position, "sources": set()})
                evidence["position"] = min(evidence["position"], position)
                evidence["sources"].add(group_index)
                for artist in self._artist_keys(track):
                    artist_support.setdefault(artist, set()).add(group_index)
        familiar, discovery = [], []
        for evidence in candidates.values():
            keys = self._artist_keys(evidence["track"])
            weight = max((profile.get(key, 0) for key in keys), default=0)
            evidence["weight"] = weight
            if weight:
                familiar.append(evidence)
            elif evidence["position"] < 5 and any(len(artist_support[key]) >= 2 for key in keys):
                discovery.append(evidence)
        familiar.sort(key=lambda item: (-len(item["sources"]), -item["weight"], item["position"]))
        discovery.sort(key=lambda item: (-len(item["sources"]), item["position"]))
        # Не заполняем очередь случайными артистами, если близких песен мало.
        new_count = min(3, self.limit // 5, len(familiar) // 4, len(discovery))
        familiar = familiar[:self.limit - new_count]
        discovery = deque(discovery[:new_count])
        result = []
        for index, evidence in enumerate(familiar):
            result.append(evidence["track"])
            if (index + 1) % 4 == 0 and discovery:
                result.append(discovery.popleft()["track"])
        return result

    def _blend_with_favorites(self, recommendations):
        """Смешивает любимые песни с небольшой порцией близких рекомендаций."""
        favorites, seen = [], set()
        for track in self.liked_tracks:
            video_id = YouTubeRatingWorker._video_id(track)
            if video_id and video_id not in seen and video_id not in self.disliked_ids:
                favorites.append(dict(track, supermix_favorite=True))
                seen.add(video_id)
        random.shuffle(favorites)
        new_count = min(len(recommendations), max(1, self.limit * 3 // 10),
                        max(1, len(favorites) * 3 // 7))
        favorites = deque(favorites[:self.limit - new_count])
        discoveries = deque(recommendations[:new_count])
        result, inserted = [], 0
        favorite_count, discovery_count = len(favorites), len(discoveries)
        for index, track in enumerate(favorites):
            result.append(track)
            expected = (index + 1) * discovery_count // favorite_count
            while inserted < expected and discoveries:
                result.append(discoveries.popleft())
                inserted += 1
        return result

    def run(self):
        if self._cancelled.is_set():
            return
        try:
            import requests
            from ytmusicapi import YTMusic
            seeds = self._select_seeds()
            if not seeds:
                raise RuntimeError("В лайках нет доступных треков YouTube Music для рекомендаций.")
            excluded = self.disliked_ids | {YouTubeRatingWorker._video_id(track) for track in self.liked_tracks}
            deadline = time.monotonic() + self.REQUEST_BUDGET_SECONDS
            groups, errors = [], []
            with requests.Session() as session:
                original_request = session.request

                def bounded_request(method, url, *args, **kwargs):
                    remaining = deadline - time.monotonic()
                    if self._cancelled.is_set() or remaining <= 0:
                        raise TimeoutError("Истекло время ожидания рекомендаций.")
                    kwargs["timeout"] = (min(4, remaining), min(7, remaining))
                    # requests сохраняет проверку TLS и учитывает REQUESTS_CA_BUNDLE.
                    return original_request(method, url, *args, **kwargs)

                session.request = bounded_request
                client = YTMusic(requests_session=session)
                for seed in seeds:
                    if self._cancelled.is_set():
                        return
                    if time.monotonic() >= deadline:
                        break
                    try:
                        playlist = client.get_watch_playlist(
                            videoId=YouTubeRatingWorker._video_id(seed), radio=True, limit=25
                        )
                        group = []
                        for position, entry in enumerate((playlist or {}).get("tracks", [])):
                            if position >= self.MAX_RADIO_DEPTH:
                                break
                            track = self._normalize_track(entry)
                            if track and track["video_id"] not in excluded:
                                group.append((track, position))
                        groups.append(group)
                    except Exception as error:
                        errors.append(str(error).replace("\n", " ")[:180])
            if self._cancelled.is_set():
                return
            result = self._rank_recommendations(groups)
            if not result:
                if errors:
                    detail = errors[0].casefold()
                    if "403" in detail:
                        message = "Доступ к рекомендациям YouTube Music отклонён (403). Проверь доступ к сервису и повтори."
                    elif "certificate" in detail:
                        message = "Не удалось проверить HTTPS-сертификат YouTube Music. Проверь доверенные сертификаты системы."
                    elif "timeout" in detail or "timed out" in detail:
                        message = "YouTube Music не ответил вовремя. Попробуй собрать Супермикс позже."
                    else:
                        message = "Не удалось получить рекомендации YouTube Music. Проверь соединение и повтори."
                    raise RuntimeError(message)
                raise RuntimeError("Не нашлось достаточно близких новых песен. Попробуй собрать Супермикс позже или добавь больше любимых исполнителей.")
            result = self._blend_with_favorites(result)
            new_count = sum(not track.get("supermix_favorite") for track in result)
            note = f"Супермикс: {len(result)} треков · новых: {new_count}."
            if errors:
                note += " Часть рекомендаций временно недоступна."
            self.result_ready.emit(result, note)
        except ImportError:
            if not self._cancelled.is_set():
                self.failed.emit("Для рекомендаций нужна ytmusicapi: python -m pip install -U ytmusicapi")
        except Exception as error:
            if not self._cancelled.is_set():
                self.failed.emit(str(error).replace("\n", " ")[:500])


class StreamWorker(QThread):
    # Ссылка, название и время её получения (секунды).
    stream_ready = pyqtSignal(str, str, float)
    failed = pyqtSignal(str)

    def __init__(self, track, parent=None, cookie_file=None, cookies_from_browser=None, audio_quality="auto"):
        super().__init__(parent)
        self.track = dict(track)
        self.cookie_file = str(cookie_file or "").strip()
        self.cookies_from_browser = str(cookies_from_browser or "").strip()
        self.audio_quality = str(audio_quality or "auto")
        self._cancel_requested = False

    def cancel(self):
        """Подавляет результат устаревшего запроса после завершения сетевого вызова."""
        self._cancel_requested = True

    @staticmethod
    def _auth_may_help(error):
        """True для ошибок, где авторизация реально может помочь."""
        message = str(error or "").casefold()
        markers = (
            "sign in", "login required", "age-restricted", "age restricted",
            "members-only", "members only", "private video", "private video",
            "confirm you're not a bot", "confirm you’re not a bot",
            "cookies are required", "http error 403", "403 forbidden",
        )
        return any(marker in message for marker in markers)

    def _extract(self, options):
        with YoutubeDL(options) as ydl:
            return ydl.extract_info(self.track["url"], download=False)

    def run(self):
        started = time.perf_counter()
        # ВАЖНО: сначала извлекаем публичный трек БЕЗ cookies. Иначе любая
        # неверная настройка Firefox/Chrome ломает даже обычные публичные миксы.
        format_options = {
            "auto": "bestaudio[protocol=https][ext=m4a]/bestaudio[protocol=https]/bestaudio/best",
            "high": "bestaudio[abr>=192]/bestaudio/best",
            "economy": "bestaudio[abr<=128]/bestaudio/best",
            "compatibility": "bestaudio[protocol=https][ext=m4a]/bestaudio[protocol=https][ext=mp3]/bestaudio[protocol=https]/bestaudio[protocol=http]/bestaudio/best",
        }
        options = {
            **yt_dlp_tls_options(),
            "format": format_options.get(self.audio_quality, format_options["auto"]),
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "socket_timeout": 12,
            "retries": 1,
            "extractor_retries": 1,
            "ignoreconfig": True,
        }
        try:
            try:
                info = self._extract(options)
                if self._cancel_requested:
                    return
            except Exception as public_error:
                if self._cancel_requested:
                    return
                # Cookies пробуем ТОЛЬКО если YouTube действительно требует вход.
                # Сбой чтения базы браузера больше не мешает публичным трекам.
                auth_options = {}
                if self.cookie_file and Path(self.cookie_file).is_file():
                    auth_options["cookiefile"] = self.cookie_file
                elif self.cookies_from_browser:
                    auth_options["cookiesfrombrowser"] = parse_cookies_from_browser(self.cookies_from_browser)
                if not auth_options or not self._auth_may_help(public_error):
                    raise
                retry_options = dict(options)
                retry_options.update(auth_options)
                try:
                    info = self._extract(retry_options)
                    if self._cancel_requested:
                        return
                except Exception as auth_error:
                    auth_message = str(auth_error).casefold()
                    cookie_db_error = any(token in auth_message for token in (
                        "could not find", "cookies database", "failed to load cookies",
                        "could not copy", "cookie database",
                    ))
                    if cookie_db_error:
                        raise RuntimeError(
                            f"YouTube запросил авторизацию, но yt-dlp не смог прочитать cookies браузера. "
                            f"Открой выбранный браузер, проверь профиль или подключи корректный cookies.txt. "
                            f"Исходная ошибка: {public_error}"
                        ) from auth_error
                    raise

            if self._cancel_requested:
                return
            if not info:
                raise RuntimeError("Информация о треке отсутствует.")
            if info.get("_type") in ("playlist", "multi_video"):
                info = next((e for e in info.get("entries", []) if e), None)
                if info is None:
                    raise RuntimeError("Не найден доступный трек.")

            stream_url = info.get("url")
            if not stream_url:
                formats = info.get("requested_formats") or info.get("formats") or []
                selected = next((f for f in formats if f.get("url") and f.get("acodec") not in (None, "none")), None)
                stream_url = selected.get("url") if selected else None

            if not stream_url:
                raise RuntimeError("Не удалось получить аудиопоток: YouTube не вернул прямую ссылку.")
            title = info.get("title") or self.track.get("title") or "Трек"
            if self._cancel_requested:
                return
            self.stream_ready.emit(stream_url, title, time.perf_counter() - started)
        except Exception as error:
            if not self._cancel_requested:
                self.failed.emit(str(error))


class TrackArtworkWorker(QThread):
    """Достаёт полные метаданные одного SoundCloud-трека только по запросу видимой строки."""
    metadata_ready = pyqtSignal(str, dict)
    failed = pyqtSignal(str, str)

    def __init__(self, track, parent=None, cookies_from_browser=None):
        super().__init__(parent)
        self.track = dict(track)
        self.cookies_from_browser = str(cookies_from_browser or "").strip()

    def run(self):
        url = str(self.track.get("url") or "")
        try:
            options = {
                **yt_dlp_tls_options(),
                "quiet": True,
                "no_warnings": True,
                "skip_download": True,
                "noplaylist": True,
                "extract_flat": False,
                "socket_timeout": 6,
                "retries": 1,
                "extractor_retries": 1,
                "cachedir": False,
                "ignoreconfig": True,
                "youtube_include_dash_manifest": False,
                "youtube_include_hls_manifest": False,
            }
            try:
                # Для публичных треков браузерные cookies не нужны и иногда сами
                # вызывают ошибку чтения занятой базы браузера.
                with YoutubeDL(options) as ydl:
                    info = ydl.extract_info(url, download=False)
            except Exception as public_error:
                if not self.cookies_from_browser:
                    raise
                retry_options = dict(options)
                retry_options["cookiesfrombrowser"] = parse_cookies_from_browser(self.cookies_from_browser)
                try:
                    with YoutubeDL(retry_options) as ydl:
                        info = ydl.extract_info(url, download=False)
                except Exception:
                    raise public_error
            if not isinstance(info, dict):
                raise RuntimeError("SoundCloud не вернул метаданные трека")
            thumbnail = info.get("thumbnail") or info.get("artwork_url") or ""
            thumbs = info.get("thumbnails") or []
            if not thumbnail:
                usable = [item for item in thumbs if isinstance(item, dict) and item.get("url")]
                if usable:
                    usable.sort(key=lambda item: (item.get("width") or 0) * (item.get("height") or 0))
                    thumbnail = usable[-1].get("url", "")
            artist = info.get("artist") or info.get("uploader") or info.get("channel") or ""
            if isinstance(artist, dict):
                artist = artist.get("username") or artist.get("name") or ""
            data = {
                "thumbnail": normalize_artwork_url(thumbnail),
                "artist": str(artist or ""),
                "duration": info.get("duration") or 0,
                "title": info.get("title") or self.track.get("title") or "",
            }
            if not data["thumbnail"]:
                raise RuntimeError("В метаданных SoundCloud нет обложки")
            self.metadata_ready.emit(url, data)
        except Exception as error:
            self.failed.emit(url, str(error))


# -------------------------------------------------------------
# Строка найденного трека с миниатюрой.
# Используем обычные Qt-виджеты, никакого HTML и браузера.
# -------------------------------------------------------------

class ClickableLabel(QLabel):
    """QLabel с сигналом клика — используется для обложки и названия трека."""
    clicked = pyqtSignal()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)


class AnimatedNavButton(QPushButton):
    """Кнопка боковой навигации с собственной отрисовкой и плавным цветом текста."""
    def __init__(self, icon_text, title, parent=None):
        super().__init__(parent)
        self.setObjectName("navButton")
        self.setCheckable(True)
        self.setMinimumHeight(48)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._nav_icon = icon_text
        self._nav_title = title
        self._collapsed = False
        self._theme = "dark"
        self._base_color = QColor("#B3B3B3")
        self._hover_color = QColor("#FFFFFF")
        self._active_color = QColor("#1DB954")
        self._text_color = QColor(self._base_color)
        self._color_animation = QVariantAnimation(self)
        self._color_animation.setDuration(180)
        self._color_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._color_animation.valueChanged.connect(self._set_animated_color)
        self.toggled.connect(self._checked_changed)
        self.setAccessibleName(title)
        self.setToolTip(title)
        self.setStyleSheet("QPushButton#navButton { border: none; padding: 0; background: transparent; }")

    def set_collapsed(self, collapsed):
        self._collapsed = bool(collapsed)
        self.setText(self._nav_icon if self._collapsed else f"{self._nav_icon}    {self._nav_title}")
        self.update()

    def set_theme(self, theme):
        self._theme = "light" if theme == "light" else "dark"
        if self._theme == "light":
            self._base_color = QColor("#555555")
            self._hover_color = QColor("#111111")
            self._active_color = QColor("#16883D")
        else:
            self._base_color = QColor("#B3B3B3")
            self._hover_color = QColor("#FFFFFF")
            self._active_color = QColor("#1DB954")
        self._animate_color(self._active_color if self.isChecked() else
                            (self._hover_color if self.underMouse() else self._base_color))
        self.update()

    def _set_animated_color(self, color):
        if isinstance(color, QColor):
            self._text_color = color
            self.update()

    def _animate_color(self, target):
        self._color_animation.stop()
        self._color_animation.setStartValue(QColor(self._text_color))
        self._color_animation.setEndValue(QColor(target))
        self._color_animation.start()

    def _checked_changed(self, checked):
        self._animate_color(self._active_color if checked else
                            (self._hover_color if self.underMouse() else self._base_color))

    def enterEvent(self, event):
        self._animate_color(self._active_color if self.isChecked() else self._hover_color)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._animate_color(self._active_color if self.isChecked() else self._base_color)
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        if self.isChecked() or self.underMouse() or self.isDown():
            painter.setPen(Qt.PenStyle.NoPen)
            if self._theme == "light":
                background = QColor("#E1F4E7" if self.isChecked() else ("#DDDDDD" if self.isDown() else "#EEEEEE"))
            else:
                background = QColor("#202020" if self.isChecked() else ("#333333" if self.isDown() else "#282828"))
            painter.setBrush(background)
            painter.drawRoundedRect(rect, 9, 9)
        if self.isChecked():
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#1DB954"))
            painter.drawRoundedRect(rect.left(), rect.top() + 9, 3, max(12, rect.height() - 18), 1.5, 1.5)
        painter.setPen(self._text_color)
        title_key = self._nav_title.casefold()
        if "youtube" in title_key:
            icon_kind = "play"
        elif "soundcloud" in title_key:
            icon_kind = "cloud"
        elif "лайк" in title_key or "like" in title_key:
            icon_kind = "heart"
        else:
            icon_kind = "music"
        if self._collapsed:
            icon_rect = QRectF(rect.center().x() - 13, rect.center().y() - 13, 26, 26)
            draw_vector_icon(painter, icon_kind, icon_rect, self._text_color, self._active_color)
        else:
            icon_rect = QRectF(rect.left() + 14, rect.center().y() - 12, 24, 24)
            draw_vector_icon(painter, icon_kind, icon_rect, self._text_color, self._active_color)
            text_rect = QRect(rect.left() + 49, rect.top(), max(0, rect.width() - 56), rect.height())
            painter.setFont(QFont(self.font().family(), 10, QFont.Weight.DemiBold))
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._nav_title)
        painter.end()


class MarqueeLabel(QLabel):
    """Текстовая бегущая строка: длинные названия плавно прокручиваются внизу."""
    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._full_text = ""
        self._offset = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(35)
        self._timer.timeout.connect(self._advance_marquee)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.setText(text)

    def setText(self, text):
        self._full_text = str(text or "")
        super().setText(self._full_text)
        self._offset = 0.0
        self._update_marquee_timer()
        self.update()

    def _loop_text(self):
        return self._full_text + "     •     "

    def _update_marquee_timer(self):
        if not hasattr(self, "_timer"):
            return
        fm = QFontMetrics(self.font())
        if self._full_text and fm.horizontalAdvance(self._full_text) > max(10, self.contentsRect().width()):
            if not self._timer.isActive():
                self._timer.start()
        else:
            self._timer.stop()
            self._offset = 0.0

    def _advance_marquee(self):
        if not self._full_text:
            return
        self._offset += 1.1
        cycle = max(1, QFontMetrics(self.font()).horizontalAdvance(self._loop_text()))
        if self._offset >= cycle:
            self._offset = 0.0
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_marquee_timer()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        rect = self.contentsRect()
        painter.setClipRect(rect)
        painter.setFont(self.font())
        painter.setPen(self.palette().color(QPalette.ColorRole.WindowText))
        fm = QFontMetrics(self.font())
        baseline = rect.top() + (rect.height() - fm.height()) // 2 + fm.ascent()
        text_width = fm.horizontalAdvance(self._full_text)
        if text_width <= rect.width():
            painter.drawText(rect.left(), baseline, self._full_text)
        else:
            loop_text = self._loop_text()
            cycle = max(1, fm.horizontalAdvance(loop_text))
            x = rect.left() - int(self._offset % cycle)
            while x < rect.right():
                painter.drawText(x, baseline, loop_text)
                x += cycle
        painter.end()


class TrackRow(QWidget):
    """Строка трека в стиле Spotify: номер, обложка, название, источник и действия."""
    play_requested = pyqtSignal(object)
    artist_requested = pyqtSignal(object)

    def __init__(self, track, compact=False, is_favorite=False, index=0, parent=None, show_source=True):
        super().__init__(parent)
        self.setObjectName("trackRow")
        self.track = dict(track)
        self._full_title = str(track.get("title") or "Без названия")
        self._full_artist = str(track.get("artist_display") or track.get("artist") or "Исполнитель неизвестен")
        self.compact = compact
        self._is_playing = False
        self._is_current = False
        self._loading = False
        self._original_index = str(index) if index else "•"
        self._eq_phase = 0
        self._eq_timer = QTimer(self)
        self._eq_timer.setInterval(320)
        self._eq_timer.timeout.connect(self._animate_equalizer)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)

        if not compact:
            self.index_label = QLabel(self._original_index)
            self.index_label.setObjectName("trackIndex")
            self.index_label.setProperty("playing", False)
            self.index_label.setFixedWidth(22)
            self.index_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.index_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            layout.addWidget(self.index_label)

        side = 40 if compact else 44
        self.thumbnail_label = ClickableLabel()
        self.thumbnail_label.setObjectName("rowCover")
        self.thumbnail_label.setFixedSize(side, side)
        self.thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumbnail_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.thumbnail_label.clicked.connect(lambda: self.play_requested.emit(dict(self.track)))
        layout.addWidget(self.thumbnail_label)

        text_column = QVBoxLayout()
        text_column.setContentsMargins(0, 0, 0, 0)
        text_column.setSpacing(2)
        self.title_label = ClickableLabel(self.track.get("title", "Без названия"))
        self.title_label.setObjectName("trackTitle")
        self.title_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.title_label.setToolTip(self.track.get("title", ""))
        self.title_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.title_label.clicked.connect(lambda: self.play_requested.emit(dict(self.track)))
        display_artist = self.track.get("artist_display") or self.track.get("artist", "")
        if compact:
            self.artist_label = QLabel(display_artist)
            self.artist_label.setObjectName("trackArtist")
            self.artist_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        else:
            self.artist_label = QPushButton(display_artist)
            self.artist_label.setObjectName("trackArtistLink")
            self.artist_label.setFlat(True)
            self.artist_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
            self.artist_label.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self.artist_label.setCursor(Qt.CursorShape.PointingHandCursor)
            self.artist_label.setToolTip("Открыть профиль исполнителя")
            self.artist_label.clicked.connect(
                lambda checked=False: self.artist_requested.emit(dict(self.track))
            )
        self.artist_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.artist_label.setMinimumHeight(17)
        text_column.addWidget(self.title_label)
        text_column.addWidget(self.artist_label)
        layout.addLayout(text_column, 1)

        if compact:
            self.remove_button = QPushButton("×")
            self.remove_button.setObjectName("rowRemove")
            self.remove_button.setFixedSize(28, 28)
            self.remove_button.setToolTip("Удалить из очереди")
            layout.addWidget(self.remove_button)
        else:
            self.source_label = QLabel("YouTube Music" if self.track.get("source") == "youtube" else
                                       "SoundCloud" if self.track.get("source") == "soundcloud" else "Файл")
            self.source_label.setObjectName("sourceText")
            self.source_label.setFixedWidth(94)
            self.source_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.source_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            layout.addWidget(self.source_label)
            if not show_source:
                self.source_label.hide()
                self.source_label.setFixedWidth(0)
            self.duration_label = QLabel(human_time(self.track.get("duration")) or "—")
            self.duration_label.setObjectName("durationText")
            self.duration_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.duration_label.setFixedWidth(45)
            self.duration_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            layout.addWidget(self.duration_label)
            self.play_button = QPushButton("▶")
            self.play_button.setObjectName("rowPlay")
            self.play_button.setFixedSize(32, 32)
            self.play_button.setToolTip("Воспроизвести")
            self.favorite_button = QPushButton("")
            self.favorite_button.setObjectName("rowFavorite")
            self.favorite_button.setIcon(control_icon("heart" if is_favorite else "heart-outline",
                                                      "#1DB954" if is_favorite else "#B3B3B3", 24))
            self.favorite_button.setIconSize(QSize(22, 22))
            self.favorite_button.setFixedSize(36, 36)
            self.favorite_button.setCheckable(True)
            self.favorite_button.setChecked(bool(is_favorite))
            self.favorite_button.setToolTip("Убрать из лайков" if is_favorite else "Добавить в лайки")
            layout.addWidget(self.play_button)
            layout.addWidget(self.favorite_button)

    def set_playing(self, current, animate=None):
        """Текущая строка остаётся выделенной и на паузе; эквалайзер движется только при Play."""
        current = bool(current)
        if animate is None:
            animate = current
        animate = bool(animate and current)
        if self.compact:
            self.setProperty("playing", current)
            self.style().unpolish(self)
            self.style().polish(self)
            self.update()
            return
        current_changed = self._is_current != current
        animation_changed = self._is_playing != animate
        if not current_changed and not animation_changed:
            return
        self._is_current = current
        self._is_playing = animate
        self.setProperty("playing", current)
        self.title_label.setProperty("playing", current)
        self.index_label.setProperty("playing", current)
        for widget in (self, self.title_label, self.index_label):
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            widget.update()
        if self._loading:
            self._eq_timer.stop()
            self.index_label.setText("⏳")
            return
        if animate:
            if current_changed or not self._eq_timer.isActive():
                self._eq_phase = 0
                self._animate_equalizer()
            self._eq_timer.start()
        else:
            self._eq_timer.stop()
            if current:
                self.index_label.setText("♫")
            else:
                self.index_label.setText(self._original_index)

    def set_loading(self, loading: bool):
        """Показывает, что выбранный трек ещё подготавливается к запуску."""
        self._loading = bool(loading)
        if self.compact or not hasattr(self, "index_label"):
            return
        if self._loading:
            self._eq_timer.stop()
            self.index_label.setText("⏳")
            return
        if self._is_current:
            self.index_label.setText("♫")
            if self._is_playing:
                self._eq_phase = 0
                self._animate_equalizer()
                self._eq_timer.start()
            else:
                self._eq_timer.stop()
        else:
            self._eq_timer.stop()
            self.index_label.setText(self._original_index)

    def _animate_equalizer(self):
        if not self._is_playing or self.compact or self._loading:
            return
        frames = ("▂▄▆", "▅▂▇", "▆▃▅", "♫")
        self.index_label.setText(frames[self._eq_phase % len(frames)])
        self._eq_phase += 1

    def mousePressEvent(self, event):
        # Кнопки действий должны обрабатывать нажатие самостоятельно:
        # иначе клик по Play/лайку/удалению может запустить строку повторно.
        if event.button() == Qt.MouseButton.LeftButton:
            child = self.childAt(event.position().toPoint())
            action_buttons = tuple(
                button for button in (
                    getattr(self, "play_button", None),
                    getattr(self, "favorite_button", None),
                    getattr(self, "remove_button", None),
                ) if button is not None
            )
            if child is None:
                self.play_requested.emit(dict(self.track))
                event.accept()
                return
            if child in action_buttons:
                super().mousePressEvent(event)
                return
            self.play_requested.emit(dict(self.track))
            event.accept()
            return
        super().mousePressEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        for label, full in ((self.title_label, self._full_title),
                            (self.artist_label, self._full_artist)):
            width = max(0, label.contentsRect().width() - 3)
            shortened = label.fontMetrics().elidedText(full, Qt.TextElideMode.ElideRight, width)
            if label.text() != shortened:
                label.setText(shortened)


def make_placeholder(side=240):
    pixmap = QPixmap(side, side)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    grad = QLinearGradient(0, 0, side, side)
    grad.setColorAt(0, QColor("#1DB954"))
    grad.setColorAt(0.5, QColor("#14532D"))
    grad.setColorAt(1, QColor("#121212"))
    p.setBrush(QBrush(grad))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(QRect(0, 0, side, side), 15, 15)
    p.setPen(QPen(QColor(255, 255, 255, 65), max(1, side // 110)))
    p.setBrush(Qt.BrushStyle.NoBrush)
    for ratio in (0.30, 0.40):
        r = int(side * ratio)
        p.drawEllipse(QRect((side-r)//2, (side-r)//2, r, r))
    inset = side * 0.32
    draw_vector_icon(p, "music", QRectF(inset, inset, side - 2 * inset, side - 2 * inset), "#FFFFFF")
    p.end()
    return pixmap


def rounded_pixmap(source, size, radius=11):
    """Квадратная обложка с обрезкой по центру и скруглёнными углами."""
    scaled = source.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
    result = QPixmap(size, size)
    result.fill(Qt.GlobalColor.transparent)
    p = QPainter(result)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    from PyQt6.QtGui import QPainterPath
    clip = QPainterPath()
    clip.addRoundedRect(0, 0, size, size, radius, radius)
    p.setClipPath(clip)
    x = (scaled.width() - size) // 2
    y = (scaled.height() - size) // 2
    p.drawPixmap(0, 0, scaled, x, y, size, size)
    p.end()
    return result


def circular_pixmap(source, size):
    """Обрезает изображение в круг — для аватара исполнителя и радио."""
    scaled = source.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                           Qt.TransformationMode.SmoothTransformation)
    result = QPixmap(size, size)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addEllipse(0, 0, size, size)
    painter.setClipPath(path)
    x = (scaled.width() - size) // 2
    y = (scaled.height() - size) // 2
    painter.drawPixmap(0, 0, scaled, x, y, size, size)
    painter.end()
    return result



# -------------------------------------------------------------
# Аккуратные иконки, нарисованные самим Qt.
# Внешних файлов или библиотек иконок не требуется.
# -------------------------------------------------------------

def control_icon(name, color="#D4CDD5", side=32):
    pix = QPixmap(side, side)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(side / 32.0, side / 32.0)
    pen = QPen(QColor(color), 2.3)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)

    def polygon(*points):
        p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in points]))

    if name in ("play", "next", "previous"):
        p.setBrush(QColor(color))
        if name == "play":
            polygon((11, 7), (11, 25), (25, 16))
        elif name == "previous":
            p.drawLine(9, 8, 9, 24)
            polygon((23, 8), (23, 24), (11, 16))
        else:
            p.drawLine(23, 8, 23, 24)
            polygon((9, 8), (9, 24), (21, 16))
    elif name == "pause":
        p.setBrush(QColor(color))
        p.drawRoundedRect(9, 8, 5, 16, 1, 1)
        p.drawRoundedRect(18, 8, 5, 16, 1, 1)
    elif name == "stop":
        p.setBrush(QColor(color))
        p.drawRoundedRect(10, 10, 12, 12, 2, 2)
    elif name == "menu":
        for y in (10, 16, 22):
            p.drawLine(8, y, 24, y)
    elif name == "queue":
        for y in (10, 16, 22):
            p.drawEllipse(QPointF(8, y), 1, 1)
            p.drawLine(13, y, 24, y)
    elif name == "shuffle":
        p.drawLine(6, 9, 10, 9)
        p.drawLine(10, 9, 22, 23)
        p.drawLine(22, 23, 26, 23)
        p.drawLine(6, 23, 10, 23)
        p.drawLine(10, 23, 22, 9)
        p.drawLine(22, 9, 26, 9)
        p.drawLine(23, 6, 26, 9)
        p.drawLine(23, 12, 26, 9)
        p.drawLine(23, 20, 26, 23)
        p.drawLine(23, 26, 26, 23)
    elif name == "repeat":
        p.drawLine(8, 12, 8, 10)
        p.drawLine(8, 10, 23, 10)
        p.drawLine(23, 10, 20, 7)
        p.drawLine(23, 10, 20, 13)
        p.drawLine(24, 20, 24, 22)
        p.drawLine(24, 22, 9, 22)
        p.drawLine(9, 22, 12, 19)
        p.drawLine(9, 22, 12, 25)
    elif name == "volume":
        p.setBrush(QColor(color))
        polygon((7, 13), (11, 13), (16, 9), (16, 23), (11, 19), (7, 19))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(13, 9, 13, 14, -55 * 16, 110 * 16)
    elif name in ("heart", "heart-outline"):
        path = QPainterPath()
        path.moveTo(16, 27)
        path.cubicTo(13, 24, 4, 17, 4, 10)
        path.cubicTo(4, 3, 13, 2, 16, 8)
        path.cubicTo(19, 2, 28, 3, 28, 10)
        path.cubicTo(28, 17, 19, 24, 16, 27)
        path.closeSubpath()
        if name == "heart":
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(color))
            p.drawPath(path)
        else:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(pen)
            p.drawPath(path)
    elif name in ("thumb-down", "thumb-down-outline"):
        path = QPainterPath()
        path.moveTo(6, 5)
        path.lineTo(11, 5)
        path.lineTo(14, 10)
        path.cubicTo(15, 11, 16, 12, 16, 14)
        path.lineTo(16, 21)
        path.cubicTo(16, 23, 14, 26, 12, 26)
        path.cubicTo(10, 26, 10, 23, 9, 21)
        path.lineTo(7, 17)
        path.lineTo(5, 17)
        path.closeSubpath()
        p.drawPath(path)
        p.drawRoundedRect(18, 5, 8, 12, 2, 2)
        p.drawLine(18, 8, 15, 11)
        p.drawLine(18, 14, 15, 16)
        if name == "thumb-down":
            p.setBrush(QColor(color))
            p.drawPath(path)
            p.drawRoundedRect(18, 5, 8, 12, 2, 2)
    p.end()
    return QIcon(pix)



# -------------------------------------------------------------
# Кликабельная шкала.
# Обычный QSlider в Windows может двигать значение лишь на шаг
# при клике на дорожку. Эта версия сразу переходит в точку клика.
# При этом перетаскивание за круглую ручку остаётся обычным.
# -------------------------------------------------------------

class ClickSlider(QSlider):
    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or not self.isEnabled():
            return super().mousePressEvent(event)
        option = QStyleOptionSlider()
        self.initStyleOption(option)
        handle = self.style().subControlRect(QStyle.ComplexControl.CC_Slider, option,
                                             QStyle.SubControl.SC_SliderHandle, self)
        if handle.contains(event.position().toPoint()):
            return super().mousePressEvent(event)
        groove = self.style().subControlRect(QStyle.ComplexControl.CC_Slider, option,
                                             QStyle.SubControl.SC_SliderGroove, self)
        horizontal = self.orientation() == Qt.Orientation.Horizontal
        extent = handle.width() if horizontal else handle.height()
        start = (groove.x() if horizontal else groove.y()) + extent // 2
        span = max(1, (groove.width() if horizontal else groove.height()) - extent)
        position = (event.position().x() if horizontal else event.position().y()) - start
        position = max(0, min(span, round(position)))
        upside_down = self.invertedAppearance() if horizontal else not self.invertedAppearance()
        value = QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), position, span, upside_down)
        self.sliderPressed.emit()
        self.setSliderDown(True)
        self.setSliderPosition(value)
        self.setValue(value)
        self.setSliderDown(False)
        self.sliderReleased.emit()
        event.accept()


class MenuChoice(QPushButton):
    valueChanged = pyqtSignal(object)

    def __init__(self, options, initial, width=175, parent=None, suffix=""):
        super().__init__(parent)
        self.options = list(options)
        self._value = initial
        self.suffix = suffix
        self.setObjectName("settingsPicker")
        self.setMinimumHeight(42)
        # Фиксируем аккуратную ширину поля, чтобы оно не растягивалось
        # на всю строку и не закрывало соседние настройки при выборе.
        self.setFixedWidth(width)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.menu_popup = QMenu(self)
        self.menu_popup.setObjectName("settingsDarkMenu")
        self.menu_popup.setStyleSheet("""
            QMenu {
                background: #282828; color: #FFFFFF;
                border: 1px solid #3B3B3B; padding: 7px;
            }
            QMenu::item {
                padding: 11px 24px 11px 13px; border: none;
                margin: 2px 1px; border-radius: 8px;
                background: transparent;
            }
            QMenu::item:selected { background: #3A3A3A; color: #1ED760; }
            QMenu::separator { height: 0px; }
        """)
        palette = self.menu_popup.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor('#282828'))
        palette.setColor(QPalette.ColorRole.Base, QColor('#282828'))
        palette.setColor(QPalette.ColorRole.Text, QColor('#FFFFFF'))
        self.menu_popup.setPalette(palette)
        for title, value in self.options:
            action = self.menu_popup.addAction(title)
            action.triggered.connect(
                lambda checked=False, new_value=value: self.set_value(new_value, emit=True)
            )
        # Не используем setMenu: встроенный popup Qt подбирает ширину
        # по короткому тексту пункта и получается уже самой кнопки.
        # Вместо этого открываем QMenu вручную с шириной поля.
        self.clicked.connect(self.open_popup)
        self.set_value(initial)

    def open_popup(self, checked=False):
        # Меню открывается по ширине поля, а не по длине надписи.
        self.menu_popup.setMinimumWidth(self.width())
        self.menu_popup.popup(self.mapToGlobal(QPoint(0, self.height() + 3)))

    def set_value(self, value, emit=False):
        self._value = value
        title = next((title for title, v in self.options if v == value), None)
        if title is None:
            title = f"{value}{self.suffix}"
        self.setText(f"{title}   ▾")
        if emit:
            self.valueChanged.emit(value)

    def value(self):
        return self._value

    def currentData(self):
        return self._value



class RotatingCover(QLabel):
    """Круглая обложка с вращением для окна радио."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._rotation = 0.0
        self.setFixedSize(156, 156)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setProperty("circular_image", True)
        self.setPixmap(circular_pixmap(make_placeholder(200), 150))

    def get_rotation(self):
        return self._rotation

    def set_rotation(self, value):
        self._rotation = float(value)
        self.update()

    rotation = pyqtProperty(float, fget=get_rotation, fset=set_rotation)

    def paintEvent(self, event):
        pix = self.pixmap()
        if pix is None or pix.isNull():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.translate(self.width() / 2, self.height() / 2)
        painter.rotate(self._rotation)
        size = min(self.width(), self.height()) - 6
        painter.drawPixmap(QRect(-size // 2, -size // 2, size, size), pix)
        painter.end()


class WaveRings(QWidget):
    """Зелёные звуковые волны с анимированным радиусом."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._phase = 0.0
        self.setMinimumSize(280, 210)
        self.animation = QPropertyAnimation(self, b"phase", self)
        self.animation.setDuration(1700)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutSine)
        self.animation.setLoopCount(-1)
        self.animation.start()

    def get_phase(self):
        return self._phase

    def set_phase(self, value):
        self._phase = float(value)
        self.update()

    phase = pyqtProperty(float, fget=get_phase, fset=set_phase)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        center = self.rect().center()
        max_radius = min(self.width(), self.height()) * 0.43
        for index in range(3):
            phase = (self._phase + index / 3.0) % 1.0
            radius = 30 + phase * max_radius
            alpha = int(130 * (1.0 - phase))
            pen = QPen(QColor(29, 185, 84, alpha), 2.0)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(center.x(), center.y()), radius, radius)
        painter.end()


class RadioDialog(QDialog):
    """Полупрозрачное окно радио с вращающейся обложкой и Fade In/Out."""
    def __init__(self, parent, track):
        super().__init__(parent)
        self.track = dict(track)
        self._after_close = None
        self.setObjectName("radioDialog")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setModal(False)
        self.setGeometry(parent.geometry())
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(0.0)

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 28, 28, 28)
        root.addStretch(1)
        content = QFrame()
        content.setObjectName("radioCard")
        content.setMaximumWidth(460)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(30, 28, 30, 30)
        content_layout.setSpacing(8)
        brand = QLabel("RADIO MIX")
        brand.setObjectName("radioBrand")
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content_layout.addWidget(brand)
        self.waves = WaveRings()
        wave_layout = QVBoxLayout(self.waves)
        wave_layout.setContentsMargins(0, 0, 0, 0)
        wave_layout.addStretch(1)
        cover_row = QHBoxLayout()
        cover_row.addStretch(1)
        self.cover = RotatingCover()
        cover_row.addWidget(self.cover)
        cover_row.addStretch(1)
        wave_layout.addLayout(cover_row)
        wave_layout.addStretch(1)
        content_layout.addWidget(self.waves)
        self.track_title = QLabel(self.track.get("title", "Выбранный трек"))
        self.track_title.setObjectName("radioTrackTitle")
        self.track_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.track_title.setWordWrap(True)
        content_layout.addWidget(self.track_title)
        self.status_label = QLabel("Ищем похожую музыку…")
        self.status_label.setObjectName("radioStatus")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content_layout.addWidget(self.status_label)
        center = QHBoxLayout()
        center.addStretch(1)
        center.addWidget(content)
        center.addStretch(1)
        root.addLayout(center)
        root.addStretch(1)

        self.rotation_animation = QPropertyAnimation(self.cover, b"rotation", self)
        self.rotation_animation.setDuration(9000)
        self.rotation_animation.setStartValue(0.0)
        self.rotation_animation.setEndValue(360.0)
        self.rotation_animation.setLoopCount(-1)
        self.rotation_animation.setEasingCurve(QEasingCurve.Type.Linear)
        self.rotation_animation.start()
        self.fade_animation = QPropertyAnimation(self.opacity_effect, b"opacity", self)
        self.fade_animation.setDuration(320)
        self.fade_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(10, 10, 10, 224))
        painter.end()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.fade_out()
            event.accept()
            return
        super().keyPressEvent(event)

    def show_animated(self):
        self.setGeometry(self.parentWidget().geometry())
        self.show()
        self.raise_()
        self.fade_animation.stop()
        self.fade_animation.setStartValue(0.0)
        self.fade_animation.setEndValue(1.0)
        self.fade_animation.start()

    def fade_out(self, callback=None):
        if callback is not None:
            self._after_close = callback
        self.fade_animation.stop()
        self.fade_animation.setStartValue(self.opacity_effect.opacity())
        self.fade_animation.setEndValue(0.0)
        try:
            self.fade_animation.finished.disconnect()
        except TypeError:
            pass
        self.fade_animation.finished.connect(self._finish_close)
        self.fade_animation.start()

    def _finish_close(self):
        self.close()
        callback = self._after_close
        self._after_close = None
        if callable(callback):
            QTimer.singleShot(0, callback)
        self.deleteLater()


class SettingsDialog(QDialog):
    """Настройки с Manrope, удобными пресетами и настоящим сохранением."""

    def __init__(self, player):
        super().__init__(player)
        self.player_window = player
        self.setWindowTitle("Настройки — Music Player")
        self.setObjectName("settingsDialog")
        # Чтобы Qt точно прорисовывал фон всего окна, а не только вкладок.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumSize(630, 560)
        self.resize(680, 620)
        self.setModal(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 20)
        root.setSpacing(14)

        heading = QLabel("Настройки")
        heading.setObjectName("settingsTitle")
        root.addWidget(heading)
        subtitle = QLabel("Управление воспроизведением и внешним видом")
        subtitle.setObjectName("settingsHint")
        root.addWidget(subtitle)

        tabs = QTabWidget()
        tabs.setObjectName("settingsTabs")
        root.addWidget(tabs, 1)

        # ------------------ Общие ------------------
        general = QWidget()
        general.setObjectName("settingsGeneral")
        general_layout = QVBoxLayout(general)
        general_layout.setContentsMargins(15, 19, 15, 16)
        general_layout.setSpacing(13)
        self._add_group_label(general_layout, "ПОИСК")

        self.result_count = MenuChoice(
            [("25 треков", 25), ("50 треков", 50), ("100 треков", 100)],
            player.result_limit, width=214, suffix=" треков"
        )
        general_layout.addLayout(self._form_row("Количество результатов", self.result_count))
        general_layout.addSpacing(6)
        self._add_group_label(general_layout, "ВНЕШНИЙ ВИД")
        self.theme_choice = MenuChoice(
            [("Тёмная тема", "dark"), ("Светлая тема", "light")],
            player.theme, width=214
        )
        general_layout.addLayout(self._form_row("Тема оформления", self.theme_choice))
        self._add_group_label(general_layout, "ПАНЕЛИ")
        self.compact_sidebar = QCheckBox("Сворачивать меню слева")
        self.compact_sidebar.setChecked(player.sidebar_collapsed)
        general_layout.addWidget(self.compact_sidebar)
        self.minimize_to_tray = QCheckBox("При закрытии окна сворачивать плеер в системный трей")
        self.minimize_to_tray.setChecked(player.minimize_to_tray)
        self.hide_on_minimize = QCheckBox("Скрывать окно в трей при нажатии кнопки сворачивания")
        self.hide_on_minimize.setChecked(player.hide_on_minimize)
        general_layout.addWidget(self.minimize_to_tray)
        general_layout.addWidget(self.hide_on_minimize)
        # Очередь больше не занимает правую колонку постоянно.
        self._add_hint(general_layout, "Очередь открывается по кнопке ≡ внизу плеера. Для выхода используй меню значка в трее.")
        general_layout.addStretch(1)
        self._add_hint(
            general_layout,
            "Manrope берётся из шрифтов Windows или из папки fonts рядом с программой."
        )
        tabs.addTab(general, "Общие")

        # ------------------ Воспроизведение ------------------
        playback = QWidget()
        playback.setObjectName("settingsPlayback")
        play_layout = QVBoxLayout(playback)
        play_layout.setContentsMargins(15, 19, 15, 16)
        play_layout.setSpacing(15)
        self._add_group_label(play_layout, "ЗВУК И ПЕРЕКЛЮЧЕНИЕ")
        self.audio_quality = MenuChoice(
            [("Авто · рекомендуемое", "auto"), ("Высокое качество", "high"),
             ("Экономия трафика", "economy"), ("Совместимость", "compatibility")],
            player.audio_quality, width=230
        )
        play_layout.addLayout(self._form_row("Качество аудио", self.audio_quality))

        # Громкость: по шкале можно кликать, а справа выбрать пресет.
        self.volume = ClickSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(int(round(player.volume * 100)))
        self.volume.setToolTip("Нажми в любую точку или перетащи ручку")
        self.volume_choice = MenuChoice(
            [(f"{v} %", v) for v in (0, 10, 25, 50, 75, 100)],
            self.volume.value(), width=110, suffix=" %"
        )
        self.volume.valueChanged.connect(self.volume_choice.set_value)
        self.volume_choice.valueChanged.connect(self.volume.setValue)
        volume_row = QHBoxLayout()
        volume_row.setSpacing(12)
        volume_row.addWidget(self.volume, 1)
        volume_row.addWidget(self.volume_choice)
        play_layout.addLayout(self._form_row("Громкость", volume_row))

        self.fade = MenuChoice(
            [(f"{ms} мс", ms) for ms in (120, 180, 240, 300, 450, 600, 900, 1200, 1500, 1800, 2400, 3000)],
            player.fade_duration_ms, width=214, suffix=" мс"
        )
        play_layout.addLayout(self._form_row("Плавный переход", self.fade))

        self.repeat = MenuChoice(
            [("Без повтора", "off"), ("Повтор очереди", "all"),
             ("Повтор трека", "one")],
            player.repeat_mode, width=214
        )
        play_layout.addLayout(self._form_row("Повтор", self.repeat))

        self.shuffle = QCheckBox("Перемешивать треки")
        self.shuffle.setChecked(player.shuffle_enabled)
        play_layout.addWidget(self.shuffle)
        self.autoplay_playlists = QCheckBox("Автоматически запускать первый трек плейлиста или микса")
        self.autoplay_playlists.setChecked(player.autoplay_playlists)
        self.autoplay_playlists.setToolTip(
            "Если выключено, подборка загрузится в список, но музыка не начнёт играть сама."
        )
        play_layout.addWidget(self.autoplay_playlists)
        play_layout.addStretch(1)
        self._add_hint(
            play_layout,
            "Нажми на значение, чтобы выбрать готовый вариант. "
            "На громкости также работает клик по шкале."
        )
        tabs.addTab(playback, "Воспроизведение")

        # ------------------ Сервисы ------------------
        services = QWidget()
        services.setObjectName("settingsServices")
        services_layout = QVBoxLayout(services)
        services_layout.setContentsMargins(15, 19, 15, 16)
        services_layout.setSpacing(13)
        self._add_group_label(services_layout, "АККАУНТЫ И СИНХРОНИЗАЦИЯ")
        self._add_hint(services_layout, "Подключение выполняется через сессию браузера или cookies-файл. Пароли сервисов приложение не запрашивает.")
        self.service_status = QLabel(self._service_status_text())
        self.service_status.setObjectName("settingsHint")
        self.service_status.setWordWrap(True)
        services_layout.addWidget(self.service_status)
        yt_row = QHBoxLayout()
        self.service_youtube_button = QPushButton("Настроить YouTube Music")
        self.service_youtube_button.setObjectName("settingsPicker")
        self.service_youtube_sync_button = QPushButton("Синхронизировать лайки")
        self.service_youtube_sync_button.setObjectName("settingsPicker")
        yt_row.addWidget(self.service_youtube_button, 1)
        yt_row.addWidget(self.service_youtube_sync_button, 1)
        services_layout.addLayout(yt_row)
        sc_row = QHBoxLayout()
        self.service_soundcloud_button = QPushButton("Настроить SoundCloud")
        self.service_soundcloud_button.setObjectName("settingsPicker")
        self.service_soundcloud_sync_button = QPushButton("Обновить плейлисты и лайки")
        self.service_soundcloud_sync_button.setObjectName("settingsPicker")
        sc_row.addWidget(self.service_soundcloud_button, 1)
        sc_row.addWidget(self.service_soundcloud_sync_button, 1)
        services_layout.addLayout(sc_row)
        self.service_youtube_button.clicked.connect(lambda: self._defer_service_action(player.connect_youtube_account))
        self.service_youtube_sync_button.clicked.connect(lambda: self._defer_service_action(player.sync_youtube_likes))
        self.service_soundcloud_button.clicked.connect(lambda: self._defer_service_action(player.connect_soundcloud_account))
        self.service_soundcloud_sync_button.clicked.connect(
            lambda: self._defer_service_action(
                (lambda: player.load_soundcloud_account_content(force=True))
                if player.soundcloud_is_connected()
                else player.connect_soundcloud_account
            )
        )
        services_layout.addStretch(1)
        self._add_hint(services_layout, "Качество аудио применяется к новым запросам аудиопотока. Уже играющий поток не перезапускается.")
        tabs.addTab(services, "Сервисы")

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Отмена")
        cancel.setObjectName("settingsCancel")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Сохранить")
        save.setObjectName("settingsSave")
        save.clicked.connect(self.save_changes)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        root.addLayout(buttons)

        self.setStyleSheet("""
            /* Делаем фон диалога сплошным, убираем чёрные поля Windows. */
            QDialog#settingsDialog {
                background-color: #121212;
                color: #F6F0F7;
            }
            QWidget { color: #F3EEF5; }
            QLabel, QTabWidget#settingsTabs { background: transparent; }
            QWidget#settingsGeneral,
            QWidget#settingsPlayback,
            QWidget#settingsServices {
                background-color: #181818;
            }
            QLabel#settingsTitle { font-size: 24px; font-weight: 800; color: #FFF8FA; }
            QLabel#settingsHint { color: #AFA4B9; font-size: 10pt; }
            QLabel#settingsGroup { color: #1DB954; font-size: 10pt; font-weight: 800; }
            QLabel#settingsField { font-size: 10pt; color: #DAD0E0; }
            QTabWidget::pane {
                border: 1px solid #333333;
                background: #181818; border-radius: 12px;
            }
            QTabBar { background: transparent; }
            QTabBar::tab {
                background: transparent; color: #B3B3B3;
                border: none; padding: 11px 18px; margin-right: 6px;
            }
            QTabBar::tab:hover { color: #FFFFFF; }
            QTabBar::tab:selected {
                background: #282828; color: #1DB954;
                border-radius: 9px; font-weight: 700;
            }
            QPushButton#settingsPicker {
                text-align: left; background: #242424;
                border: 1px solid #3A3A3A; border-radius: 10px;
                color: #FFFFFF; padding: 9px 12px; font-weight: 650;
            }
            QPushButton#settingsPicker:hover {
                background: #303030; border-color: #1DB954;
            }
            QPushButton#settingsPicker::menu-indicator { image: none; width: 0; }
            QCheckBox { spacing: 10px; color: #E9E0ED; }
            QCheckBox::indicator {
                width: 18px; height: 18px;
                background: #282828; border: 1px solid #666666;
                border-radius: 5px;
            }
            QCheckBox::indicator:checked {
                background: #1DB954; border: 1px solid #1DB954;
            }
            QSlider::groove:horizontal {
                height: 6px; background: #535353; border-radius: 3px;
            }
            QSlider::sub-page:horizontal { background: #1DB954; border-radius: 3px; }
            QSlider::handle:horizontal {
                background: #1ED760; width: 16px;
                margin: -6px 0; border-radius: 8px;
            }
            QPushButton#settingsCancel, QPushButton#settingsSave {
                border: none; border-radius: 10px;
                padding: 12px 20px; font-weight: 700;
                background: #282828; color: #FFFFFF;
            }
            QPushButton#settingsSave { background: #1DB954; color: #25160F; }
            QPushButton#settingsCancel:hover { background: #333333; }
            QPushButton#settingsSave:hover { background: #1ED760; }
        """)
        if player.theme == "light":
            self.setStyleSheet(self.styleSheet() + """
                QDialog#settingsDialog { background: #F5F5F7; color: #202027; }
                QWidget { color: #25252C; }
                QWidget#settingsGeneral, QWidget#settingsPlayback, QWidget#settingsServices,
                QTabWidget#settingsTabs::pane { background: #FFFFFF; border-color: #DADAE2; }
                QLabel#settingsTitle { color: #202027; }
                QLabel#settingsHint { color: #666675; }
                QLabel#settingsGroup { color: #16883D; }
                QLabel#settingsField { color: #393943; }
                QTabWidget::pane { border-color: #DADAE2; background: #FFFFFF; }
                QTabBar::tab { color: #656574; }
                QTabBar::tab:selected { background: #E1F4E7; color: #16883D; }
                QPushButton#settingsPicker { background: #F4F4F7; border-color: #D7D6E0; color: #24242B; }
                QPushButton#settingsPicker:hover { background: #FFFFFF; border-color: #1DB954; }
                QCheckBox { color: #30303A; }
                QCheckBox::indicator { background: #FFFFFF; border-color: #BDBDC9; }
                QSlider::groove:horizontal { background: #D5D5DE; }
                QSlider::sub-page:horizontal { background: #1DB954; }
                QSlider::handle:horizontal { background: #1DB954; }
                QPushButton#settingsCancel { background: #E8E8EE; color: #30303A; }
                QPushButton#settingsCancel:hover { background: #DCDCE5; }
            """)
            light_menu = """QMenu { background: #FFFFFF; color: #24242B; border: 1px solid #D7D6E0; padding: 6px; }
                QMenu::item { padding: 10px 20px; border: none; border-radius: 6px; }
                QMenu::item:selected { background: #E1F4E7; color: #16883D; }"""
            for popup in self.findChildren(QMenu):
                popup.setStyleSheet(light_menu)

    def _service_status_text(self):
        player = self.player_window
        yt = "подключён" if player.youtube_auth_kwargs() else "не подключён"
        sc = "подключён" if player.soundcloud_is_connected() else "не подключён"
        return f"YouTube Music: {yt}\nSoundCloud: {sc}\nЛайки сервисов хранятся раздельно; локальные сердечки не меняют лайки на сайтах."

    def _defer_service_action(self, callback):
        # Закрываем настройки перед показом отдельного диалога авторизации.
        self.accept()
        QTimer.singleShot(0, callback)

    @staticmethod
    def _add_group_label(layout, text):
        lbl = QLabel(text)
        lbl.setObjectName("settingsGroup")
        layout.addWidget(lbl)

    @staticmethod
    def _add_hint(layout, text):
        lbl = QLabel(text)
        lbl.setObjectName("settingsHint")
        lbl.setWordWrap(True)
        layout.addWidget(lbl)

    @staticmethod
    def _form_row(label, widget_or_layout):
        row = QHBoxLayout()
        row.setSpacing(12)
        field = QLabel(label)
        field.setObjectName("settingsField")
        field.setMinimumWidth(162)
        row.addWidget(field)
        if isinstance(widget_or_layout, QHBoxLayout):
            row.addLayout(widget_or_layout, 1)
        else:
            # Прижимаем компактные выпадающие поля к правому краю.
            row.addStretch(1)
            row.addWidget(widget_or_layout, 0)
        return row

    def save_changes(self):
        player = self.player_window
        player.change_limit(int(self.result_count.value()))
        player.volume_slider.setValue(self.volume.value())
        player.audio_quality = str(self.audio_quality.currentData())
        new_theme = str(self.theme_choice.currentData())
        if new_theme in ("dark", "light") and new_theme != player.theme:
            player.theme = new_theme
            player.update_theme_button()
            player.apply_styles()
        player.minimize_to_tray = self.minimize_to_tray.isChecked()
        player.hide_on_minimize = self.hide_on_minimize.isChecked()
        player.fade_duration_ms = max(120, min(6000, int(self.fade.value())))
        player.repeat_mode = self.repeat.currentData()
        player.refresh_repeat_button()
        player.shuffle_button.setChecked(self.shuffle.isChecked())
        player.autoplay_playlists = self.autoplay_playlists.isChecked()
        if player.sidebar_collapsed != self.compact_sidebar.isChecked():
            player.toggle_sidebar()
        player.save_preferences()
        self.accept()


class Toast(QLabel):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWordWrap(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setStyleSheet("background: rgba(30,30,35,235); color: white; border-radius: 10px; padding: 12px;")
        self.opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity)
        self.animation = QPropertyAnimation(self.opacity, b"opacity", self)
        self.animation.setDuration(450)
        self.animation.setStartValue(1.0)
        self.animation.setEndValue(0.0)
        self.animation.finished.connect(self.hide)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.animation.start)
        self.hide()

    def show_message(self, message, duration=3500):
        self.timer.stop()
        self.animation.stop()
        self.opacity.setOpacity(1.0)
        self.setText(str(message))
        self.setFixedWidth(min(420, max(180, self.parentWidget().width() - 40)))
        self.setMinimumHeight(self.fontMetrics().lineSpacing() * 2 + 24)
        self.adjustSize()
        self.move(max(0, self.parentWidget().width() - self.width() - 20),
                  max(0, self.parentWidget().height() - self.height() - 20))
        self.show()
        self.raise_()
        self.timer.start(duration)


class WindowsMediaKeyFilter(QAbstractNativeEventFilter):
    def __init__(self, player):
        super().__init__()
        self.player_ref = weakref.ref(player)

    def nativeEventFilter(self, event_type, message):
        if sys.platform != "win32" or bytes(event_type) != b"windows_generic_MSG":
            return False, 0
        class MSG(ctypes.Structure):
            _fields_ = [("hwnd", ctypes.c_void_p), ("message", ctypes.c_uint),
                        ("wParam", ctypes.c_size_t), ("lParam", ctypes.c_size_t),
                        ("time", ctypes.c_uint), ("pt_x", ctypes.c_long), ("pt_y", ctypes.c_long)]
        msg = MSG.from_address(int(message))
        if msg.message != 0x0319:
            return False, 0
        method = {14: "toggle_playback", 11: "play_next", 12: "play_previous", 13: "stop_all"}.get((msg.lParam >> 16) & 0x0FFF)
        player = self.player_ref()
        if not method or player is None:
            return False, 0
        getattr(player, method)()
        return True, 1


class DownloadWorker(QThread):
    progress = pyqtSignal(int)
    completed = pyqtSignal(dict, str)
    failed = pyqtSignal(str)

    def __init__(self, track, parent=None):
        super().__init__(parent)
        self.track = dict(track)

    def run(self):
        try:
            url = str(self.track.get("url") or "")
            if not url.startswith(("https://", "http://")):
                raise ValueError("Нет адреса для скачивания")
            folder = app_cache_directory() / "downloads"
            folder.mkdir(parents=True, exist_ok=True)
            from urllib.parse import urlparse, parse_qs
            video_id = str(self.track.get("video_id") or "")
            if not video_id and self.track.get("source") == "youtube":
                video_id = parse_qs(urlparse(url).query).get("v", [""])[0]
            video_id = video_id or hashlib.sha256(url.encode()).hexdigest()[:24]
            source = re.sub(r"[^A-Za-z0-9_-]", "_", str(self.track.get("source") or "web"))
            video_id = re.sub(r"[^A-Za-z0-9_-]", "_", video_id)[:120]
            stem = f"{source}_{video_id}"
            def hook(status):
                if status.get("status") == "downloading":
                    total = status.get("total_bytes") or status.get("total_bytes_estimate") or 0
                    if total:
                        self.progress.emit(min(100, int(status.get("downloaded_bytes", 0) * 100 / total)))
            options = {**yt_dlp_tls_options(), "format": "bestaudio/best", "outtmpl": str(folder / (stem + ".%(ext)s")),
                       "noplaylist": True, "quiet": True, "no_warnings": True, "progress_hooks": [hook]}
            with YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=True)
                if not info:
                    raise RuntimeError("yt-dlp не вернул файл")
                path = Path(ydl.prepare_filename(info))
            if not path.is_file():
                candidates = [p for p in folder.glob(stem + ".*") if p.is_file() and p.suffix not in (".part", ".ytdl", ".temp")]
                if not candidates:
                    raise FileNotFoundError("Скачанный файл не найден")
                path = max(candidates, key=lambda p: p.stat().st_mtime)
            self.progress.emit(100)
            self.completed.emit(self.track, str(path.resolve()))
        except Exception as exc:
            self.failed.emit(str(exc))


class MusicPlayer(QMainWindow):
    PENDING_MEDIA_TIMEOUT_MS = 20_000

    def install_shortcuts(self):
        self._shortcuts = []
        def bind(keys, callback):
            shortcut = QShortcut(QKeySequence(keys), self)
            shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
            shortcut.activated.connect(callback)
            self._shortcuts.append(shortcut)
        def toggle():
            focus = QApplication.focusWidget()
            if isinstance(focus, (QLineEdit, QComboBox, QTextEdit, QPlainTextEdit, QAbstractSpinBox)):
                return
            if isinstance(focus, QListWidget) and focus.currentItem() is not None:
                track = focus.currentItem().data(Qt.ItemDataRole.UserRole)
                if isinstance(track, dict):
                    self.add_to_queue(track, True)
                    return
            self.toggle_playback()
        bind("Space", toggle)
        bind("Ctrl+Right", self.play_next)
        bind("Ctrl+Left", self.play_previous)
        def focus_search():
            if not self.search_row.isVisible():
                return
            self.search_input.setFocus()
            self.search_input.selectAll()
        bind("Ctrl+F", focus_search)
        bind("Ctrl+L", self.like_current_shortcut)
        bind("Ctrl+Q", self.request_app_exit)
        bind("Escape", self.escape_shortcut)

    def like_current_shortcut(self):
        track = self.current_track or self.requested_track
        if track:
            if track.get("source") == "youtube":
                self.set_youtube_music_like(track, not self.is_youtube_music_liked(track))
            else:
                self.toggle_favorite(track)

    def escape_shortcut(self):
        if self.queue_open:
            self.toggle_queue()
        elif self.radio_dialog is not None and self.radio_dialog.isVisible():
            dialog = self.radio_dialog
            self.radio_dialog = None
            dialog.fade_out()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            focus = QApplication.focusWidget()
            if not isinstance(focus, (QLineEdit, QComboBox, QListWidget, QSlider)) and self.source_list.count():
                row = self.source_list.currentRow()
                row = min(self.source_list.count() - 1, row + 1) if event.key() == Qt.Key.Key_Down else max(0, row - 1)
                self.source_list.setCurrentRow(row)
                self.source_list.scrollToItem(self.source_list.item(row))
                self.source_list.setFocus()
                event.accept()
                return
        super().keyPressEvent(event)

    def show_toast(self, message, duration=3500):
        if hasattr(self, "toast"):
            self.toast.show_message(message, duration)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        toast = getattr(self, "toast", None)
        if toast is not None and toast.isVisible():
            toast.move(max(0, self.width() - toast.width() - 20),
                       max(0, self.height() - toast.height() - 20))

    def offline_path_for(self, track):
        if not isinstance(track, dict):
            return None
        key = self.favorite_key(track)
        indexed = self._download_index.get(key)
        for candidate in (track.get("local_path"), indexed):
            if not candidate:
                continue
            path = Path(candidate)
            if not path.is_absolute():
                path = app_cache_directory() / "downloads" / path
            try:
                if path.is_file() and path.stat().st_size > 0:
                    return str(path)
            except OSError:
                continue
        if key in self._download_index:
            del self._download_index[key]
            self._download_index_dirty = True
            if not self._download_index_flush_scheduled:
                self._download_index_flush_scheduled = True
                QTimer.singleShot(1000, self._flush_download_index)
        return None

    def _flush_download_index(self):
        self._download_index_flush_scheduled = False
        if not self._download_index_dirty:
            return
        try:
            temp = self._download_index_file.with_suffix(".tmp")
            temp.write_text(json.dumps(self._download_index, ensure_ascii=False, indent=2), encoding="utf-8")
            temp.replace(self._download_index_file)
            self._download_index_dirty = False
        except OSError:
            logging.getLogger("aurora").exception("Не удалось сохранить индекс загрузок")
            if not self._download_index_flush_scheduled:
                self._download_index_flush_scheduled = True
                QTimer.singleShot(1000, self._flush_download_index)

    def download_track(self, track):
        if track.get("source") not in ("youtube", "soundcloud"):
            self.show_toast("Офлайн-доступно только для YouTube и SoundCloud")
            return
        if self.offline_path_for(track):
            self.show_toast("Трек уже доступен офлайн")
            return
        key = self.favorite_key(track)
        if any(self.favorite_key(w.track) == key for w in self._download_workers):
            self.show_toast("Трек уже скачивается")
            return
        worker = DownloadWorker(track, self)
        self._download_workers.add(worker)
        worker.progress.connect(lambda percent: self.set_status(f"Скачивание {percent}%"))
        worker.completed.connect(self.on_download_completed)
        worker.failed.connect(lambda message: self.show_toast("Ошибка скачивания: " + message[:200], 4500))
        worker.finished.connect(lambda w=worker: self._download_workers.discard(w))
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def on_download_completed(self, track, path):
        key = self.favorite_key(track)
        self._download_index[key] = path
        if key in self.favorites:
            self.favorites[key]["local_path"] = path
            self.save_favorites()
        for collection in (self.queue_tracks, self.youtube_liked_tracks, self.soundcloud_liked_tracks):
            for item in collection:
                if self.favorite_key(item) == key:
                    item["local_path"] = path
        if self.current_track and self.favorite_key(self.current_track) == key:
            self.current_track["local_path"] = path
        self._download_index_dirty = True
        self._flush_download_index()
        self.set_status("Трек скачан для офлайна")
        self.show_toast("Скачано: " + str(track.get("title") or "трек"))

    def __init__(self):
        super().__init__()
        # QSettings сохраняет предпочтения между запусками на Windows.
        self.settings = QSettings("AuroraLocal", "MusicPlayer")
        self.theme = str(self.settings.value("spotify_theme", "dark"))
        if self.theme not in ("dark", "light"):
            self.theme = "dark"
        self.audio_quality = str(self.settings.value("audio_quality", "auto") or "auto")
        if self.audio_quality not in ("auto", "high", "economy", "compatibility"):
            self.audio_quality = "auto"
        self.minimize_to_tray = self.settings.value("minimize_to_tray", True, type=bool)
        self.hide_on_minimize = self.settings.value("hide_on_minimize", False, type=bool)
        self._force_exit = False
        self._tray_notice_shown = False
        self.tray_icon = None
        self.favorites_file = migrate_legacy_data("favorites.json")
        self.favorites = self.load_favorites()
        raw_disliked = self.settings.value("disliked_track_keys", [], type=list) or []
        self.disliked_track_keys = {str(key) for key in raw_disliked if str(key)}
        self.youtube_likes_file = migrate_legacy_data("youtube_likes_cache.json")
        self.youtube_cookie_file = str(self.settings.value("youtube_cookie_file", "") or "")
        self.youtube_auth_mode = str(self.settings.value("youtube_auth_mode", "file") or "file")
        self.youtube_auth_browser = str(self.settings.value("youtube_auth_browser", "chrome") or "chrome")
        self.youtube_auth_profile = str(self.settings.value("youtube_auth_profile", "") or "").strip()
        self.youtube_liked_tracks = self.load_youtube_likes()
        self._youtube_rating_workers = set()
        self._youtube_rating_pending = set()
        # Оптимистическое состояние кнопок не попадает в подтверждённый кэш.
        self._youtube_rating_targets = {}
        self._youtube_rating_tracks = {}
        self._youtube_sync_rating_changes = {}
        # SoundCloud: сессия браузера для личных данных либо публичный URL профиля.
        self.soundcloud_auth_mode = str(self.settings.value("soundcloud_auth_mode", "profile") or "profile")
        self.soundcloud_browser = str(self.settings.value("soundcloud_browser", "chrome") or "chrome")
        self.soundcloud_profile_url = str(self.settings.value("soundcloud_profile_url", "") or "").strip().rstrip("/")
        self.soundcloud_likes_file = migrate_legacy_data("soundcloud_likes_cache.json")
        self._soundcloud_likes_synced_at = 0.0
        self._soundcloud_cache_profile = ""
        self._soundcloud_cached_playlists = []
        self.soundcloud_liked_tracks = self.load_soundcloud_likes()
        self.soundcloud_account_playlists = list(self._soundcloud_cached_playlists)
        self.soundcloud_profile_workers = {}
        self._soundcloud_last_profile_load = 0.0
        self._soundcloud_profile_status = ""
        self._soundcloud_likes_loading = False
        self._soundcloud_likes_sync_started = False
        self._soundcloud_sync_tracks = []
        self._soundcloud_sync_seen = set()
        # Не создаём сразу тысячи сложных TrackRow-виджетов: список лайков
        # визуализируется небольшими порциями по мере прокрутки.
        self._likes_render_batch = 150
        self._likes_rendered_counts = {"youtube": 0, "soundcloud": 0, "local": 0}
        self._likes_list_signatures = {}
        self._likes_loading_more = set()
        self._soundcloud_queue_waiting = False
        self._soundcloud_queue_anchor_url = ""
        self.queue_mode = "manual"  # manual, soundcloud_likes или radio
        # Недостающие SoundCloud-обложки разрешаются только для видимых строк,
        # чтобы не делать тысячи сетевых запросов сразу.
        self.artwork_workers = {}
        self.artwork_backlog = deque()
        self.artwork_pending_urls = set()
        self.artwork_failed_until = {}
        self.artwork_max_workers = 3
        self._visible_artwork_timers = {}
        self.custom_playlists = self.load_custom_playlists()
        self._pending_direct_url = ""
        self._radio_retry_scheduled = False
        self.youtube_sync_worker = None
        self._youtube_sync_error = ""
        self._youtube_sync_had_results = False
        self._youtube_likes_before_sync = []
        self.repeat_mode = str(self.settings.value("repeat_mode", "off"))
        # Автозапуск плейлистов/миксов отключён по умолчанию, чтобы нажатие
        # карточки только загружало подборку, не начиная воспроизведение само.
        self.autoplay_playlists = self.settings.value("autoplay_playlists", False, type=bool)
        if self.repeat_mode not in ("off", "all", "one"):
            self.repeat_mode = "off"
        self.shuffle_enabled = self.settings.value("shuffle", False, type=bool)
        self.shuffle_future = None
        self._shuffle_history = deque(maxlen=min(20, 200))
        self._shuffle_weights_cache = {}
        self.saved_sidebar = self.settings.value("sidebar_collapsed", False, type=bool)
        self.setWindowTitle("Music Player · Green Edition")
        self.resize(1380, 860)
        self.setMinimumSize(1000, 650)

        self.current_source = "youtube"
        self.current_track = None
        self.current_queue_index = -1
        self.queue_tracks = []
        self.source_results = {"youtube": [], "soundcloud": [], "likes": []}
        self.source_statuses = {"youtube": "Найди любимые треки.", "soundcloud": "Найди треки или исполнителя.", "likes": "Аккаунт YouTube Music не подключён."}
        self.saved_queries = {"youtube": "", "soundcloud": ""}
        self.search_submitted_queries = {"youtube": "", "soundcloud": ""}
        try:
            self._youtube_last_sync_at = float(self.settings.value("youtube_last_sync_at", 0.0) or 0.0)
        except (TypeError, ValueError):
            self._youtube_last_sync_at = 0.0
        self.sort_mode = "relevance"
        self.result_limit = max(25, min(100, int(self.settings.value("search_limit", 50))))
        self.sidebar_collapsed = False
        self.queue_open = False
        self._download_workers = set()
        self._download_index_dirty = False
        self._download_index_flush_scheduled = False
        self._last_radio_refill_check = 0.0
        self._download_index_file = app_data_directory() / "downloads_index.json"
        try:
            self._download_index = json.loads(self._download_index_file.read_text(encoding="utf-8"))
            if not isinstance(self._download_index, dict):
                self._download_index = {}
        except (OSError, ValueError):
            self._download_index = {}
        self.is_seeking = False
        self.search_worker = None
        self.stream_worker = None
        self.search_source = None
        self.artist_profile_query = ""
        self.active_artist_profile = ""
        self.active_artist_profile_url = ""
        self.search_artist_target = ""
        # Карточка артиста открывается только явным нажатием на ник исполнителя.
        # Совпадение обычного поискового запроса с именем автора не открывает профиль.
        self.artist_profile_open = False
        self.radio_worker = None
        self.radio_dialog = None
        self.radio_candidates = []
        self.radio_note = ""
        self.supermix_worker = None
        self.radio_mode_active = False
        self.radio_refill_worker = None
        self.radio_refill_attempt_key = ""
        self.radio_refill_added_urls = set()
        self.radio_refill_next_allowed_at = 0.0
        self.radio_refill_round = 0
        self.radio_refill_added_count = 0
        self.radio_refill_last_error = ""
        self._radio_refill_failed_attempts = 0
        self.radio_artist_context = ""
        self.radio_seen_urls = set()
        self._radio_waiting_for_tracks = False
        self._finish_transition_pending = False
        self._finish_guard_url = ""
        self._auto_failed_tracks = set()
        self.auto_play_next_search = False
        self.auto_play_generation = -1
        self.start_cards = []

        # Прямые ссылки временные и могут истекать; сохраняем их на 8 минут.
        self.stream_cache = {}
        self.stream_cache_ttl = 8 * 60
        self.prefetch_worker = None
        self.prefetch_target = None
        self.prefetch_failed_until = {}     # Не повторяем сбой каждую секунду.
        self.stream_worker = None
        self.stream_target = None
        self.stream_pending_track = None

        # Два QMediaPlayer с отдельными QAudioOutput: основной и резервный.
        # Резервный можно открывать и буферизовать, не прерывая основной.
        self.players = [QMediaPlayer(self), QMediaPlayer(self)]
        self.audio_outputs = [QAudioOutput(self), QAudioOutput(self)]
        self.volume = max(0.0, min(1.0, self.settings.value("volume", 70, type=int) / 100.0))
        for player, output in zip(self.players, self.audio_outputs):
            player.setAudioOutput(output)
            output.setVolume(0.0)

        self.active_slot = 0                 # Тот, чей звук слышит пользователь.
        self.player = self.players[0]         # Совместимо с кнопками и перемоткой UI.
        self.audio_output = self.audio_outputs[0]
        self.audio_output.setVolume(self.volume)
        self.current_track = None            # Реально играющая композиция.
        self.current_queue_index = -1
        self.requested_track = None          # Трек, который пользователь выбрал.
        self.requested_index = -1
        self.request_started = None
        self.request_origin = ""
        self.request_id = 0                   # Игнорируем устаревшие запросы.
        self.pending_slot = None              # Плеер, в котором запускаем новую песню.
        self.pending_started = None
        self.pending_media_timer = QTimer(self)
        self.pending_media_timer.setSingleShot(True)
        self.pending_media_timer.timeout.connect(self.on_pending_media_timeout)
        self.pending_media_url = None
        self.pending_position_seen = False
        self.pending_ever_loaded = False
        self.pending_refreshed = False
        self.standby_key = None               # URL трека, предварительно загруженного Qt.
        self.standby_ready = False
        self.standby_started = None

        # Плавное изменение громкости после готовности нового потока.
        self.fade_timer = QTimer(self)
        self.fade_timer.setInterval(30)
        self.fade_timer.timeout.connect(self.fade_step)
        self.fade_old_slot = None
        self.fade_started_at = None
        # Старые настройки шагов сохраняют выбранную пользователем длительность.
        legacy_fade_ms = max(4, min(200, int(self.settings.value("fade_steps", 10)))) * 30
        self.fade_duration_ms = max(120, min(6000, int(
            self.settings.value("fade_duration_ms", legacy_fade_ms)
        )))
        self.fade_active_duration_ms = self.fade_duration_ms
        self.last_switch_seconds = None

        # Обложки кэшируются в памяти (LRU) и на диске между запусками.
        # Это сокращает повторные HTTP-запросы при открытии больших библиотек.
        self.network_manager = QNetworkAccessManager(self)
        self.image_disk_cache = QNetworkDiskCache(self)
        try:
            image_cache_dir = app_cache_directory() / "images"
            image_cache_dir.mkdir(parents=True, exist_ok=True)
            self.image_disk_cache.setCacheDirectory(str(image_cache_dir))
            self.image_disk_cache.setMaximumCacheSize(100 * 1024 * 1024)
            self.network_manager.setCache(self.image_disk_cache)
        except OSError as error:
            # Недоступный диск-кэш не должен мешать обычной загрузке обложек.
            logging.getLogger("aurora").info(f"[Music Player] Дисковый кэш обложек недоступен: {error}")
        self.pixmap_cache = OrderedDict()
        self.image_waiters = {}  # URL -> список QLabel
        self.image_backlog = deque()
        self.active_images = 0
        self.image_limit = 6
        self.fallback_cover = make_placeholder()

        self._likes_search_query = ""
        self.build_ui()
        self.rebuild_start_cards()
        self.sort_button.hide()
        self.back_button.hide()
        self.apply_styles()
        self.update_theme_button()
        self.connect_signals()
        self.setup_system_tray()
        self.set_source("youtube")
        self.update_browse_empty_state()
        self.refresh_likes_list()
        self.show_cover("")
        if self.saved_sidebar:
            self.toggle_sidebar()
        self.refresh_repeat_button()
        self.shuffle_button.setChecked(self.shuffle_enabled)
        self.set_volume(int(round(self.volume * 100)))

    # ---------------------------------------------------------
    # Интерфейс. Две постоянные колонки + выдвижная очередь.
    # ---------------------------------------------------------

    def setup_system_tray(self):
        """Создаёт значок системного трея с управлением воспроизведением."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_icon = None
            return
        icon = QIcon(control_icon("play", "#1DB954").pixmap(32, 32))
        self.tray_icon = QSystemTrayIcon(icon, self)
        self.tray_icon.setToolTip("Music Player · Green Edition")
        menu = QMenu(self)
        menu.setObjectName("darkMenu")
        open_action = menu.addAction("Открыть плеер")
        open_action.triggered.connect(self.restore_from_tray)
        menu.addSeparator()
        play_action = menu.addAction("Пауза / Продолжить")
        play_action.triggered.connect(self.toggle_playback)
        next_action = menu.addAction("Следующий трек")
        next_action.triggered.connect(self.play_next)
        menu.addAction("Настройки…", self.open_settings)
        menu.addSeparator()
        exit_action = menu.addAction("Выйти")
        exit_action.triggered.connect(self.request_app_exit)
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self.on_tray_activated)
        self.tray_icon.show()

    def on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.DoubleClick):
            self.restore_from_tray()

    def restore_from_tray(self):
        self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()

    def request_app_exit(self):
        """Аккуратно завершает приложение после завершения/отмены фоновых потоков."""
        self._force_exit = True
        self._exit_attempts = 0
        for worker in self.findChildren(QThread):
            if worker.isRunning() and hasattr(worker, "cancel"):
                try:
                    worker.cancel()
                except RuntimeError:
                    pass
        self._poll_app_exit()

    def _poll_app_exit(self):
        self._exit_attempts = getattr(self, "_exit_attempts", 0) + 1
        if self._exit_attempts > 40:
            QApplication.quit()
            return
        working = [worker for worker in self.findChildren(QThread) if worker.isRunning()]
        if working:
            QTimer.singleShot(250, self._poll_app_exit)
            return
        self.close()
        QApplication.quit()

    def changeEvent(self, event):
        super().changeEvent(event)
        tray_icon = getattr(self, "tray_icon", None)
        if (event.type() == QEvent.Type.WindowStateChange and self.isMinimized()
                and getattr(self, "hide_on_minimize", False) and tray_icon is not None):
            QTimer.singleShot(0, self.hide)
            tray_icon.show()
            if not getattr(self, "_tray_notice_shown", False):
                tray_icon.showMessage(
                    "Music Player работает в фоне",
                    "Плеер продолжает воспроизведение. Нажми значок в трее, чтобы открыть окно.",
                    QSystemTrayIcon.MessageIcon.Information, 2500
                )
                self._tray_notice_shown = True

    def build_ui(self):
        root_widget = QWidget()
        root_widget.setObjectName("root")
        root = QVBoxLayout(root_widget)
        root.setContentsMargins(14, 14, 14, 12)
        root.setSpacing(12)

        # Две постоянные колонки: навигация и каталог.
        # Очередь — выдвижная панель, которая изначально имеет ширину 0.
        columns = QHBoxLayout()
        columns.setSpacing(12)
        columns.addWidget(self.create_sidebar())
        columns.addWidget(self.create_center(), 1)
        self.queue_panel = self.create_queue()
        self.queue_panel.setMinimumWidth(0)
        self.queue_panel.setMaximumWidth(0)
        columns.addWidget(self.queue_panel)
        root.addLayout(columns, 1)
        root.addWidget(self.create_bottom_bar())
        self.setCentralWidget(root_widget)

        # Анимация ширины не создаёт второго окна и не перекрывает звук.
        self.queue_animation = QPropertyAnimation(self.queue_panel, b"maximumWidth", self)
        self.queue_animation.setDuration(240)
        self.queue_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.page_animation = None
        self._animated_page = None
        self.last_library_page = self.browse_page
        self.toast = Toast(self)
        self.install_shortcuts()

    def create_sidebar(self):
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(210)
        side_layout = QVBoxLayout(self.sidebar)
        side_layout.setContentsMargins(12, 14, 12, 14)
        side_layout.setSpacing(10)

        top = QHBoxLayout()
        self.menu_hint = QLabel("МУЗЫКА")
        self.menu_hint.setObjectName("eyebrow")
        self.sidebar_toggle = QPushButton("‹")
        self.sidebar_toggle.setObjectName("iconButton")
        self.sidebar_toggle.setToolTip("Свернуть меню")
        self.sidebar_toggle.setFixedSize(34, 34)
        top.addWidget(self.menu_hint)
        top.addStretch(1)
        top.addWidget(self.sidebar_toggle)
        side_layout.addLayout(top)
        side_layout.addSpacing(9)

        self.nav_buttons = []
        self.nav_data = [
            ("▶", "YouTube Music", "youtube"),
            ("☁", "SoundCloud", "soundcloud"),
            ("♥", "Лайки", "likes"),
        ]
        for icon, title, _ in self.nav_data:
            btn = AnimatedNavButton(icon, title)
            side_layout.addWidget(btn)
            self.nav_buttons.append(btn)

        side_layout.addStretch(1)
        return self.sidebar

    def create_center(self):
        panel = QFrame()
        panel.setObjectName("centerPanel")
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(20, 16, 20, 15)
        outer.setSpacing(0)

        # Три внутренних экрана: каталог, полноразмерная обложка, лайки.
        self.view_stack = QStackedWidget()
        outer.addWidget(self.view_stack, 1)

        self.browse_page = QWidget()
        browse = QVBoxLayout(self.browse_page)
        browse.setContentsMargins(0, 0, 0, 0)
        browse.setSpacing(12)

        title_row = QHBoxLayout()
        self.page_title = QLabel("YouTube Music")
        self.page_title.setObjectName("pageTitle")
        self.page_description = QLabel("Музыка на одном экране")
        self.page_description.setObjectName("mutedText")
        title_row.addWidget(self.page_title)
        title_row.addStretch(1)
        title_row.addWidget(self.page_description)
        self.theme_button = QPushButton("☀")
        self.theme_button.setObjectName("themeButton")
        self.theme_button.setFixedSize(42, 38)
        self.theme_button.setToolTip("Переключить светлую / тёмную тему")
        title_row.addWidget(self.theme_button)
        browse.addLayout(title_row)

        self.search_row = QWidget()
        search_layout = QHBoxLayout(self.search_row)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.setSpacing(9)
        self.back_button = QPushButton("‹")
        self.back_button.setObjectName("backButton")
        self.back_button.setFixedSize(44, 44)
        self.back_button.setToolTip("Назад к подборкам")
        self.back_button.setAccessibleName("Назад к подборкам")
        self.back_button.hide()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("⌕   Трек или исполнитель...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setMinimumHeight(44)

        # Переключатель сортировки убран из интерфейса: профиль показывает
        # обычную выдачу исполнителя без меню «Популярные / Сначала новые».
        # Атрибут оставлен скрытым, чтобы старые внутренние вызовы не ломались.
        self.sort_button = QPushButton(self)
        self.sort_button.setObjectName("filterButton")
        self.sort_button.hide()
        self.sort_menu = None

        # Количество результатов теперь только в настройках.
        self.search_button = QPushButton("Найти")
        self.search_button.setObjectName("accentButton")
        self.search_button.setMinimumHeight(44)
        self.search_button.setFixedWidth(90)
        search_layout.addWidget(self.back_button)
        search_layout.addWidget(self.search_input, 1)
        # Фильтр сортировки находится в карточке исполнителя, а не в поисковой строке.
        search_layout.addWidget(self.search_button)
        browse.addWidget(self.search_row)

        # Стартовый экран строится динамически: супермикс, плейлисты аккаунта,
        # пользовательские ссылки и кнопка добавления своей подборки.
        self.start_cards_widget = QWidget()
        self.start_cards_widget.setObjectName("startCardsWidget")
        self.start_cards_layout = QVBoxLayout(self.start_cards_widget)
        self.start_cards_layout.setContentsMargins(0, 4, 0, 2)
        self.start_cards_layout.setSpacing(13)
        self.start_cards_layout.addStretch(1)
        self.start_cards_scroll = QScrollArea()
        self.start_cards_scroll.setObjectName("startCardsScroll")
        self.start_cards_scroll.setWidgetResizable(True)
        self.start_cards_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.start_cards_scroll.setWidget(self.start_cards_widget)
        browse.addWidget(self.start_cards_scroll, 1)

        # Компактная шапка профиля в духе YouTube Music: аватар и данные артиста,
        # без фоновой фотографии на весь блок и без кнопки подписки.
        self.artist_header = QFrame()
        self.artist_header.setObjectName("artistHeader")
        self.artist_header.setMinimumHeight(188)
        self.artist_header.setMaximumHeight(212)
        artist_layout = QHBoxLayout(self.artist_header)
        artist_layout.setContentsMargins(22, 14, 22, 14)
        artist_layout.setSpacing(22)
        self.artist_avatar = QLabel()
        self.artist_avatar.setObjectName("artistAvatar")
        self.artist_avatar.setFixedSize(124, 124)
        self.artist_avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.artist_avatar.setProperty("circular_image", True)
        artist_layout.addWidget(self.artist_avatar, 0, Qt.AlignmentFlag.AlignVCenter)

        artist_text = QVBoxLayout()
        artist_text.setContentsMargins(0, 0, 0, 0)
        artist_text.setSpacing(3)
        self.artist_verified = QLabel("ИСПОЛНИТЕЛЬ")
        self.artist_verified.setObjectName("artistVerified")
        self.artist_verified.setToolTip("Страница исполнителя")
        artist_text.addWidget(self.artist_verified)

        # Имя артиста остаётся кликабельным и повторно открывает его профиль.
        self.artist_name_label = QPushButton("Исполнитель")
        self.artist_name_label.setObjectName("artistNameLink")
        self.artist_name_label.setFlat(True)
        self.artist_name_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.artist_name_label.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.artist_name_label.setToolTip("Обновить треки этого исполнителя")
        self.artist_name_label.setAccessibleName("Открыть профиль исполнителя")
        self.artist_name_label.setMinimumHeight(40)
        self.artist_name_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        artist_text.addWidget(self.artist_name_label)

        self.artist_popular_label = QLabel("Треки исполнителя")
        self.artist_popular_label.setObjectName("artistPopular")
        artist_text.addWidget(self.artist_popular_label)
        self.artist_source_label = QLabel("Исполнитель · YouTube Music")
        self.artist_source_label.setObjectName("artistMeta")
        artist_text.addWidget(self.artist_source_label)

        artist_actions = QHBoxLayout()
        artist_actions.setContentsMargins(0, 3, 0, 0)
        artist_actions.setSpacing(8)
        self.artist_shuffle_button = QPushButton("Перемешать")
        self.artist_shuffle_button.setObjectName("artistShuffleButton")
        self.artist_shuffle_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.artist_shuffle_button.setIcon(control_icon("shuffle", "#101010", 20))
        self.artist_shuffle_button.setIconSize(QSize(18, 18))
        self.artist_shuffle_button.setMinimumHeight(32)
        self.artist_shuffle_button.setToolTip("Перемешать треки этого исполнителя и начать воспроизведение")
        self.artist_mix_button = QPushButton("Микс")
        self.artist_mix_button.setObjectName("artistMixButton")
        self.artist_mix_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.artist_mix_button.setMinimumHeight(32)
        self.artist_mix_button.setToolTip("Запустить радио на основе треков этого исполнителя")
        artist_actions.addWidget(self.artist_shuffle_button, 0)
        artist_actions.addWidget(self.artist_mix_button, 0)
        artist_actions.addStretch(1)
        artist_text.addLayout(artist_actions)
        artist_layout.addLayout(artist_text, 1)

        # В профиле больше нет отдельного меню сортировки.
        self.sort_button.hide()
        self.artist_header.hide()
        browse.addWidget(self.artist_header)

        results_header = QHBoxLayout()
        self.results_label = QLabel("РЕЗУЛЬТАТЫ ПОИСКА")
        self.results_label.setObjectName("eyebrow")
        self.source_status = QLabel("")
        self.source_status.setObjectName("statusText")
        self.source_status.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.source_status.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.source_status.setToolTip("▶ — играть, + — добавить в очередь")
        results_header.addWidget(self.results_label)
        results_header.addWidget(self.source_status, 1)
        self.browser_search_button = QPushButton("Открыть на сайте ↗")
        self.browser_search_button.setObjectName("textButton")
        self.browser_search_button.clicked.connect(self.open_soundcloud_search_in_browser)
        self.browser_search_button.hide()
        results_header.addWidget(self.browser_search_button)
        browse.addLayout(results_header)

        self.table_header = QFrame()
        self.table_header.setObjectName("tableHeader")
        table_layout = QHBoxLayout(self.table_header)
        table_layout.setContentsMargins(18, 3, 116, 3)
        table_layout.setSpacing(10)
        table_num = QLabel("#")
        table_num.setFixedWidth(22)
        table_num.setAlignment(Qt.AlignmentFlag.AlignCenter)
        table_title = QLabel("Название")
        table_source = QLabel("Источник")
        table_source.setFixedWidth(94)
        table_duration = QLabel("Длительность")
        table_duration.setFixedWidth(45)
        table_duration.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        for label in (table_num, table_title, table_source, table_duration):
            label.setObjectName("tableHeaderText")
        table_layout.addWidget(table_num)
        table_layout.addWidget(table_title, 1)
        table_layout.addWidget(table_source)
        table_layout.addWidget(table_duration)
        browse.addWidget(self.table_header)

        self.source_list = QListWidget()
        self.source_list.setObjectName("trackList")
        self.source_list.setSpacing(2)
        self.source_list.setMinimumHeight(135)
        self.source_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.source_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        browse.addWidget(self.source_list, 1)
        self.view_stack.addWidget(self.browse_page)

        # Лайки: локальное избранное + импортированные лайки YouTube Music.
        self.likes_page = QWidget()
        likes = QVBoxLayout(self.likes_page)
        likes.setContentsMargins(8, 8, 8, 8)
        likes.setSpacing(12)

        likes_header = QHBoxLayout()
        likes_title = QLabel("♥  Лайки")
        likes_title.setObjectName("pageTitle")
        likes_header.addWidget(likes_title)
        likes_header.addStretch(1)
        self.connect_account_button = QPushButton("Подключить аккаунт YouTube Music")
        self.connect_account_button.setObjectName("accentButton")
        self.connect_soundcloud_button = QPushButton("Подключить аккаунт SoundCloud")
        self.connect_soundcloud_button.setObjectName("filterButton")
        self.sync_account_button = QPushButton("⟳  Синхронизировать")
        self.sync_account_button.setObjectName("filterButton")
        self.disconnect_account_button = QPushButton("Отключить")
        self.disconnect_account_button.setObjectName("textButton")
        likes_header.addWidget(self.connect_account_button)
        likes_header.addWidget(self.connect_soundcloud_button)
        likes_header.addWidget(self.sync_account_button)
        likes_header.addWidget(self.disconnect_account_button)
        likes.addLayout(likes_header)

        account_card = QFrame()
        account_card.setObjectName("likesAccountCard")
        account_layout = QHBoxLayout(account_card)
        account_layout.setContentsMargins(16, 12, 16, 12)
        account_layout.setSpacing(12)
        account_icon = QLabel("♥")
        account_icon.setObjectName("likesAccountIcon")
        account_icon.setFixedSize(48, 48)
        account_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        account_layout.addWidget(account_icon)
        account_text = QVBoxLayout()
        account_text.setSpacing(3)
        self.likes_account_title = QLabel("YouTube Music")
        self.likes_account_title.setObjectName("trackTitle")
        self.likes_account_status = QLabel("Аккаунт не подключён. Подключи cookies браузера, чтобы импортировать реальные лайки.")
        self.likes_account_status.setObjectName("mutedText")
        self.likes_account_status.setWordWrap(True)
        account_text.addWidget(self.likes_account_title)
        account_text.addWidget(self.likes_account_status)
        self.soundcloud_account_status = QLabel("SoundCloud: аккаунт не подключён.")
        self.soundcloud_account_status.setObjectName("mutedText")
        self.soundcloud_account_status.setWordWrap(True)
        account_text.addWidget(self.soundcloud_account_status)
        account_layout.addLayout(account_text, 1)
        likes.addWidget(account_card)

        self.likes_title = QLabel("Избранное по источникам")
        self.likes_title.setObjectName("artistPopular")
        likes.addWidget(self.likes_title)
        self.likes_search_input = QLineEdit()
        self.likes_search_input.setPlaceholderText("⌕   Поиск в избранном...")
        self.likes_search_input.setClearButtonEnabled(True)
        self.likes_search_input.setMinimumHeight(38)
        likes.addWidget(self.likes_search_input)
        self.likes_tabs = QTabWidget()
        self.likes_tabs.setObjectName("likesSourceTabs")
        self.youtube_likes_list = QListWidget()
        self.soundcloud_likes_list = QListWidget()
        self.likes_list = QListWidget()  # Локальные сердечки: favorites.json.
        for list_widget in (self.youtube_likes_list, self.soundcloud_likes_list, self.likes_list):
            list_widget.setObjectName("trackList")
            list_widget.setSpacing(2)
            list_widget.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
            list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            list_widget.customContextMenuRequested.connect(
                lambda point, lw=list_widget: self.open_likes_menu(point, lw)
            )
        self.likes_tabs.addTab(self.youtube_likes_list, "YouTube Music · 0")
        self.likes_tabs.addTab(self.soundcloud_likes_list, "SoundCloud · 0")
        self.likes_tabs.addTab(self.likes_list, "Мои лайки · 0")
        likes.addWidget(self.likes_tabs, 1)
        likes_hint = QLabel("Лайки YouTube Music и SoundCloud импортируются раздельно. Сердечки в результатах сохраняют локальное избранное в favorites.json.")
        likes_hint.setObjectName("mutedText")
        likes_hint.setWordWrap(True)
        likes.addWidget(likes_hint)
        self.view_stack.addWidget(self.likes_page)
        return panel

    def create_queue(self):
        self.queue_panel = QFrame()
        self.queue_panel.setObjectName("queuePanel")
        self.queue_panel.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(self.queue_panel)
        layout.setContentsMargins(12, 14, 12, 14)
        layout.setSpacing(10)

        header = QHBoxLayout()
        self.queue_toggle = QPushButton("×")
        self.queue_toggle.setObjectName("iconButton")
        self.queue_toggle.setFixedSize(34, 34)
        self.queue_toggle.setToolTip("Закрыть очередь")
        self.queue_heading = QLabel("Очередь")
        self.queue_heading.setObjectName("queueTitle")
        self.clear_queue_button = QPushButton("Очистить")
        self.clear_queue_button.setObjectName("textButton")
        header.addWidget(self.queue_toggle)
        header.addWidget(self.queue_heading)
        header.addStretch(1)
        header.addWidget(self.clear_queue_button)
        layout.addLayout(header)

        self.queue_count = QLabel("0 треков")
        self.queue_count.setObjectName("mutedText")
        layout.addWidget(self.queue_count)
        self.queue_list = QListWidget()
        self.queue_list.setObjectName("queueList")
        self.queue_list.setSpacing(2)
        self.queue_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.queue_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        layout.addWidget(self.queue_list, 1)
        self.queue_hint = QLabel("Правый клик — порядок и удаление · × — закрыть")
        self.queue_hint.setObjectName("mutedText")
        self.queue_hint.setWordWrap(True)
        layout.addWidget(self.queue_hint)
        return self.queue_panel

    def create_bottom_bar(self):
        """Нижняя панель с единственной обложкой текущего трека."""
        bar = QFrame()
        bar.setObjectName("playerBar")
        bar_shadow = QGraphicsDropShadowEffect(bar)
        bar_shadow.setBlurRadius(24)
        bar_shadow.setOffset(0, -4)
        bar_shadow.setColor(QColor(0, 0, 0, 120))
        bar.setGraphicsEffect(bar_shadow)
        base = QVBoxLayout(bar)
        base.setContentsMargins(14, 9, 14, 10)
        base.setSpacing(6)

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(0)
        # Левая и правая зоны одинаковой ширины: транспорт строго в центре.
        track_info = QWidget()
        track_info.setFixedWidth(380)
        info = QHBoxLayout(track_info)
        info.setContentsMargins(0, 0, 0, 0)
        info.setSpacing(6)
        self.bottom_cover = QLabel()
        self.bottom_cover.setObjectName("bottomCover")
        self.bottom_cover.setFixedSize(64, 64)
        cover_shadow = QGraphicsDropShadowEffect(self.bottom_cover)
        cover_shadow.setBlurRadius(16)
        cover_shadow.setOffset(0, 2)
        cover_shadow.setColor(QColor(0, 0, 0, 100))
        self.bottom_cover.setGraphicsEffect(cover_shadow)
        info.addWidget(self.bottom_cover)
        labels = QVBoxLayout()
        labels.setSpacing(0)
        self.bottom_title = MarqueeLabel("Ничего не играет")
        self.bottom_title.setObjectName("bottomTitle")
        self.bottom_title.setToolTip("Текущий трек")
        self.bottom_artist = QLabel("Выбери песню")
        self.bottom_artist.setObjectName("bottomArtist")
        labels.addWidget(self.bottom_title)
        labels.addWidget(self.bottom_artist)
        info.addLayout(labels, 1)
        self.bottom_favorite_button = QPushButton()
        self.bottom_favorite_button.setObjectName("bottomFavorite")
        self.bottom_favorite_button.setIcon(control_icon("heart-outline", "#B3B3B3", 22))
        self.bottom_favorite_button.setIconSize(QSize(20, 20))
        self.bottom_favorite_button.setFixedSize(30, 30)
        self.bottom_favorite_button.setCheckable(True)
        self.bottom_favorite_button.setEnabled(False)
        self.bottom_favorite_button.setToolTip("Добавить в локальные лайки")
        info.addWidget(self.bottom_favorite_button)
        self.bottom_dislike_button = QPushButton()
        self.bottom_dislike_button.setObjectName("bottomDislike")
        self.bottom_dislike_button.setIcon(control_icon("thumb-down-outline", "#B3B3B3", 22))
        self.bottom_dislike_button.setIconSize(QSize(20, 20))
        self.bottom_dislike_button.setFixedSize(30, 30)
        self.bottom_dislike_button.setCheckable(True)
        self.bottom_dislike_button.setEnabled(False)
        self.bottom_dislike_button.setToolTip("Не показывать этот трек в будущих миксах и радио")
        info.addWidget(self.bottom_dislike_button)
        controls.addWidget(track_info)
        controls.addStretch(1)

        def tool_button(name, tooltip, object_name="transportButton", icon_color="#CEC3CC"):
            button = QPushButton()
            button.setObjectName(object_name)
            button.setIcon(control_icon(name, icon_color))
            button.setIconSize(QSize(24, 24))
            button.setFixedSize(38, 38)
            button.setToolTip(tooltip)
            return button

        central_controls = QWidget()
        center_row = QHBoxLayout(central_controls)
        center_row.setContentsMargins(0, 0, 0, 0)
        center_row.setSpacing(4)
        self.shuffle_button = tool_button("shuffle", "Перемешивание: выкл.")
        self.shuffle_button.setCheckable(True)
        self.previous_button = tool_button("previous", "Предыдущий трек")
        self.play_button = tool_button("play", "Воспроизведение / пауза", "playButton", "#FFFFFF")
        self.play_button.setFixedSize(50, 50)
        self.play_button.setIconSize(QSize(28, 28))
        self.next_button = tool_button("next", "Следующий трек")
        self.repeat_button = tool_button("repeat", "Повтор: выкл.")
        self.repeat_button.setCheckable(True)
        self.stop_button = tool_button("stop", "Остановить")
        for button in (
            self.shuffle_button, self.previous_button, self.play_button,
            self.next_button, self.repeat_button, self.stop_button,
        ):
            center_row.addWidget(button)
        controls.addWidget(central_controls)
        controls.addStretch(1)

        right_tools = QWidget()
        right_tools.setFixedWidth(330)
        right_row = QHBoxLayout(right_tools)
        right_row.setContentsMargins(0, 0, 0, 0)
        right_row.setSpacing(8)
        right_row.addStretch(1)
        self.bottom_queue_button = tool_button("queue", "Показать / скрыть очередь")
        self.menu_button = tool_button("menu", "Меню — настройки")
        right_row.addWidget(self.bottom_queue_button)
        right_row.addWidget(self.menu_button)
        controls.addWidget(right_tools)
        base.addLayout(controls)

        timeline = QHBoxLayout()
        timeline.setSpacing(10)
        self.position_label = QLabel("0:00")
        self.position_label.setObjectName("timeText")
        self.seek_slider = ClickSlider(Qt.Orientation.Horizontal)
        self.seek_slider.setRange(0, 0)
        self.seek_slider.setEnabled(False)
        self.seek_slider.setToolTip("Нажми в любую точку для перемотки")
        self.duration_label = QLabel("0:00")
        self.duration_label.setObjectName("timeText")
        volume_icon = QLabel()
        volume_icon.setPixmap(control_icon("volume", "#C7BDC7").pixmap(20, 20))
        self.volume_slider = ClickSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(int(round(self.volume * 100)))
        self.volume_slider.setFixedWidth(116)
        self.volume_value_label = QLabel(f"{int(round(self.volume * 100))}%")
        self.volume_value_label.setObjectName("timeText")
        self.volume_value_label.setFixedWidth(33)
        self.volume_value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        timeline.addWidget(self.position_label)
        timeline.addWidget(self.seek_slider, 1)
        timeline.addWidget(self.duration_label)
        timeline.addSpacing(10)
        timeline.addWidget(volume_icon)
        timeline.addWidget(self.volume_slider)
        timeline.addWidget(self.volume_value_label)
        base.addLayout(timeline)

        self.options_menu = QMenu(self)
        self.options_menu.setObjectName("darkMenu")
        self.options_menu.addAction("Настройки…", self.open_settings)
        self.options_menu.addAction("О программе", self.show_about)
        self.options_menu.addSeparator()
        self.options_menu.addAction("Выход", self.close)
        self.menu_button.setMenu(self.options_menu)
        return bar

    # ---------------------------------------------------------
    # Единая палитра, Manrope берётся из QApplication.font().
    # Все QLabel прозрачные: никаких тёмных полос за надписями.
    # ---------------------------------------------------------

    def apply_styles(self):
        """Spotify-inspired palette: matte black, graphite panels, Spotify green."""
        # Диалоги ошибок тоже тёмные: белый текст больше не будет на белом фоне.
        dark_styles = r"""
            QMainWindow, QWidget#root { background: #121212; }
            QWidget { color: #F5F5F5; font-size: 10pt; }
            QLabel { background: transparent; border: none; }

            QFrame#sidebar { background: #181818; border: none; border-radius: 8px; }
            QFrame#queuePanel { background: #181818; border: none; border-radius: 8px; }
            QFrame#centerPanel { background: #181818; border: none; border-radius: 8px; }
            QFrame#playerBar { background: #181818; border: none; border-radius: 8px; }

            QLabel#bottomCover, QLabel#rowCover { background: #282828; border-radius: 6px; }
            QLabel#bottomArtist, QLabel#mutedText, QLabel#trackArtist, QLabel#statusText,
            QLabel#durationText, QLabel#sourceText, QLabel#artistMeta { color: #A7A7A7; }
            QLabel#bottomTitle, QLabel#pageTitle, QLabel#trackTitle, QLabel#queueTitle { color: #FFFFFF; font-weight: 700; }

            QWidget#trackRow[playing="true"] { background: rgba(29, 185, 84, 0.15); border: 1px solid #1DB954; border-radius: 8px; }
            QLabel#trackTitle[playing="true"] { color: #1DB954; font-weight: 800; }
            QLabel#trackIndex[playing="true"] { color: #1DB954; font-weight: 900; }
            QLabel#pageTitle { font-size: 24px; font-weight: 800; letter-spacing: -0.5px; }
            QLabel#queueTitle { font-size: 17px; }
            QLabel#eyebrow { color: #A7A7A7; font-size: 9pt; font-weight: 700; letter-spacing: 1px; }
            QLabel#timeText { color: #A7A7A7; font-size: 9pt; }
            QLabel#trackIndex, QLabel#tableHeaderText { color: #A7A7A7; font-size: 9pt; }

            QFrame#artistHeader { background: #232323; border: none; border-radius: 12px; }
            QLabel#artistAvatar { background: #282828; border-radius: 62px; }
            QLabel#artistVerified { color: #1DB954; font-size: 9pt; font-weight: 800; letter-spacing: 1px; }
            QPushButton#artistNameLink { color: #FFFFFF; background: transparent; border: none; text-align: left; padding: 0; margin: 0; font-size: 27pt; font-weight: 800; }
            QPushButton#artistNameLink:hover { color: #1DB954; background: transparent; }
            QLabel#artistPopular { color: #FFFFFF; font-size: 11pt; font-weight: 700; }

            QPushButton#artistShuffleButton { background: #1DB954; color: #101010; border: none; border-radius: 17px; padding: 5px 14px; font-weight: 800; min-height: 30px; }
            QPushButton#artistShuffleButton:hover { background: #1ED760; }
            QPushButton#artistMixButton { background: #232323; color: #F5F5F5; border: 1px solid #3E3E3E; border-radius: 17px; padding: 5px 14px; font-weight: 700; min-height: 30px; }
            QPushButton#artistMixButton:hover { background: #2A2A2A; border-color: #1DB954; color: #1DB954; }

            QFrame#tableHeader { background: transparent; border-bottom: 1px solid #2A2A2A; }
            QFrame#likesAccountCard { background: #232323; border: none; border-radius: 12px; }
            QLabel#likesAccountIcon { color: #1DB954; background: #1A2E22; border: none; border-radius: 12px; font-size: 24px; font-weight: 800; }

            QScrollArea#startCardsScroll { background: #181818; border: none; }
            QScrollArea#startCardsScroll QWidget#qt_scrollarea_viewport { background: #181818; border: none; }
            QWidget#startCardsWidget { background: #181818; border: none; }
            QScrollBar:vertical { background: #121212; width: 9px; margin: 2px; border: none; }
            QScrollBar::handle:vertical { background: #4D4D4D; min-height: 28px; border-radius: 4px; }
            QScrollBar::handle:vertical:hover { background: #A7A7A7; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }

            QLabel#startSectionTitle { color: #FFFFFF; font-size: 17pt; font-weight: 800; padding: 2px 0; }
            QPushButton#addPlaylistCard { background: #181818; color: #A7A7A7; border: 1px dashed #4D4D4D; border-radius: 12px; font-size: 13pt; font-weight: 700; padding: 18px; }
            QPushButton#addPlaylistCard:hover { background: #232323; color: #FFFFFF; border: 1px dashed #1DB954; }

            QPushButton { background: transparent; color: #F5F5F5; border: none; border-radius: 8px; padding: 7px 10px; }
            QPushButton:hover { background: #232323; }
            QPushButton#navButton { color: #A7A7A7; text-align: left; padding: 0; border: none; background: transparent; }
            QPushButton#iconButton, QPushButton#transportButton { background: transparent; color: #A7A7A7; border-radius: 8px; padding: 4px; }
            QPushButton#iconButton:hover, QPushButton#transportButton:hover { background: #232323; color: #1DB954; }
            QPushButton#transportButton:checked { color: #1DB954; background: #232323; }

            QPushButton#bottomFavorite, QPushButton#bottomDislike { background: transparent; border: none; border-radius: 6px; padding: 2px; }
            QPushButton#bottomFavorite:hover, QPushButton#bottomDislike:hover { background: #232323; }
            QPushButton#bottomFavorite:checked { background: #1A2E22; }
            QPushButton#bottomDislike:checked { background: #361F1F; }

            QPushButton#playButton { background: #1DB954; color: #FFFFFF; border: none; border-radius: 25px; padding: 0; }
            QPushButton#playButton:hover { background: #1ED760; }
            QPushButton#playButton:pressed { background: #169C46; }

            QPushButton#rowPlay, QPushButton#rowFavorite, QPushButton#rowRemove { background: #232323; color: #A7A7A7; border-radius: 8px; font-size: 13px; padding: 2px; font-weight: 700; }
            QPushButton#rowPlay:hover { background: #1DB954; color: #121212; }
            QPushButton#rowFavorite { font-size: 21px; color: #A7A7A7; }
            QPushButton#rowFavorite:checked { color: #1DB954; background: #1A2E22; }
            QPushButton#rowFavorite:hover, QPushButton#rowRemove:hover { background: #2A2A2A; color: #1ED760; }

            QPushButton#trackArtistLink { color: #A7A7A7; background: transparent; border: none; text-align: left; padding: 0; margin: 0; font-size: 9pt; font-weight: 500; }
            QPushButton#trackArtistLink:hover { color: #FFFFFF; text-decoration: underline; }

            QPushButton#themeButton { background: #232323; color: #1DB954; border: 1px solid #3E3E3E; border-radius: 8px; font-size: 17px; padding: 3px; }
            QPushButton#themeButton:hover { background: #2A2A2A; border-color: #1DB954; }
            QPushButton#accentButton { background: #1DB954; color: #101010; border: none; border-radius: 8px; padding: 10px 18px; font-weight: 800; }
            QPushButton#accentButton:hover { background: #1ED760; }
            QPushButton#textButton { color: #1DB954; background: transparent; font-size: 9pt; padding: 5px; }
            QPushButton#textButton:hover { color: #1ED760; background: #232323; }
            QPushButton#filterButton { color: #F5F5F5; background: #232323; border: 1px solid #3E3E3E; text-align: left; }
            QPushButton#filterButton:hover { border: 1px solid #1DB954; background: #2A2A2A; }
            QPushButton:disabled { background: #232323; color: #6A6A6A; }

            QLineEdit { background: #232323; color: #FFFFFF; border: 1px solid #3E3E3E; border-radius: 8px; padding: 10px 13px; selection-background-color: #1DB954; }
            QLineEdit:hover, QLineEdit:focus { border: 1px solid #1DB954; background: #2A2A2A; }

            QListWidget { background: #121212; color: #F5F5F5; border: none; border-radius: 8px; outline: 0; padding: 4px; }
            QListWidget::item { background: transparent; border: 1px solid transparent; border-radius: 8px; padding: 0; }
            QListWidget::item:hover { background: #232323; }
            QListWidget::item:selected { background: #232323; border: 1px solid #1DB954; }

            QWidget#trackRow { background: transparent; border: none; border-radius: 8px; }
            QWidget#trackRow:hover { background: #232323; }
            QWidget#trackRow[playing="true"]:hover { background: rgba(29, 185, 84, 0.25); border: 1px solid #1DB954; }

            QSlider::groove:horizontal { background: #4D4D4D; height: 4px; border-radius: 2px; }
            QSlider::sub-page:horizontal { background: #1DB954; border-radius: 2px; }
            QSlider::handle:horizontal { background: #FFFFFF; width: 12px; margin: -4px 0; border-radius: 6px; }
            QSlider::handle:horizontal:hover { background: #1ED760; }
            QSlider:disabled::handle:horizontal { background: #4D4D4D; }

            QMenu#darkMenu, QMenu { background: #232323; color: #FFFFFF; border: 1px solid #3E3E3E; padding: 7px; border-radius: 8px; }
            QMenu#darkMenu::item, QMenu::item { background: transparent; color: #FFFFFF; padding: 10px 22px 10px 14px; border: none; margin: 1px; border-radius: 6px; }
            QMenu#darkMenu::item:selected, QMenu::item:selected { background: #3E3E3E; color: #1DB954; }
            QMenu#darkMenu::separator, QMenu::separator { height: 1px; background: #3E3E3E; margin: 5px 10px; }

            QTabWidget::pane { border: 1px solid #2A2A2A; background: #181818; border-radius: 8px; }
            QTabBar::tab { background: #232323; color: #A7A7A7; padding: 10px 16px; border-radius: 6px; margin-right: 4px; border: none; }
            QTabBar::tab:selected { background: #1DB954; color: #101010; font-weight: 700; }
            QTabBar::tab:hover:!selected { background: #2A2A2A; color: #FFFFFF; }

            QCheckBox { spacing: 9px; }
            QCheckBox::indicator { width: 17px; height: 17px; }
            QCheckBox::indicator:checked { background: #1DB954; border: 1px solid #1DB954; border-radius: 4px; }
            QCheckBox::indicator:unchecked { background: #232323; border: 1px solid #4D4D4D; border-radius: 4px; }

            QFrame#radioCard { background: #181818; border: 1px solid #3E3E3E; border-radius: 24px; }
            QLabel#radioBrand { color: #1DB954; font-size: 10pt; font-weight: 800; letter-spacing: 2px; }
            QLabel#radioTrackTitle { color: #FFFFFF; font-size: 15pt; font-weight: 800; }
            QLabel#radioStatus { color: #A7A7A7; font-size: 10pt; }
        """
        light_styles = r"""
            QMainWindow, QWidget#root { background: #F5F5F7; }
            QWidget { color: #222222; }
            QMessageBox { background: #F5F5F7; color: #222222; }
            QMessageBox QLabel { background: transparent; color: #222222; min-width: 280px; }
            QMessageBox QPushButton { background: #E7E7EB; color: #222222; border: 1px solid #D0D0D5; border-radius: 8px; padding: 7px 18px; min-width: 72px; }
            QMessageBox QPushButton:hover { background: #DDEFE2; border-color: #1DB954; }
            QFrame#sidebar, QFrame#queuePanel, QFrame#playerBar, QFrame#centerPanel { background: #FFFFFF; border-color: #DDDDDD; }
            QFrame#artistHeader { background: #FFFFFF; border-color: #DDDDDD; }
            QLabel#artistAvatar { background: #EEEEEE; }
            QPushButton#artistShuffleButton { background: #1DB954; color: #FFFFFF; border: none; border-radius: 17px; padding: 5px 14px; font-weight: 800; min-height: 30px; }
            QPushButton#artistShuffleButton:hover { background: #16883D; }
            QPushButton#artistMixButton { background: #EEEEEE; color: #222222; border: 1px solid #D7D7D7; border-radius: 17px; padding: 5px 14px; font-weight: 700; min-height: 30px; }
            QPushButton#artistMixButton:hover { background: #E1F4E7; border-color: #1DB954; color: #16883D; }
            QFrame#likesAccountCard { background: #FFFFFF; border-color: #DDDDDD; }
            QLabel#likesAccountIcon { color: #16883D; background: #E1F4E7; border-color: #1DB954; }
            QPushButton#startCard { color: #FFFFFF; }
            QScrollArea#startCardsScroll { background: #F5F5F7; border: none; }
            QScrollArea#startCardsScroll QWidget#qt_scrollarea_viewport { background: #F5F5F7; border: none; }
            QWidget#startCardsWidget { background: #F5F5F7; border: none; }
            QScrollBar:vertical { background: #F5F5F7; width: 9px; margin: 2px; border: none; }
            QScrollBar::handle:vertical { background: #C5C5C5; min-height: 28px; border-radius: 4px; }
            QScrollBar::handle:vertical:hover { background: #1DB954; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
            QLabel#startSectionTitle { color: #181818; font-size: 17pt; font-weight: 800; padding: 2px 0; }
            QPushButton#addPlaylistCard { background: #FFFFFF; color: #555555; border: 1px dashed #BBBBBB; border-radius: 16px; font-size: 13pt; font-weight: 700; padding: 18px; }
            QPushButton#addPlaylistCard:hover { background: #E1F4E7; color: #16883D; border: 1px dashed #1DB954; }
            QLabel#pageTitle, QLabel#trackTitle, QLabel#bottomTitle, QLabel#queueTitle { color: #181818; }
            QPushButton#artistNameLink { color: #181818; background: transparent; border: none; text-align: left; padding: 0; margin: 0; font-size: 27pt; font-weight: 800; }
            QPushButton#artistNameLink:hover { color: #16883D; background: transparent; }
            QLabel#mutedText, QLabel#bottomArtist, QLabel#trackArtist, QLabel#durationText, QLabel#sourceText, QLabel#artistMeta { color: #555555; }
            QLabel#artistVerified, QLabel#artistPopular { color: #16883D; }
            QLabel#trackIndex, QLabel#tableHeaderText { color: #666666; }
            QWidget#trackRow[playing="true"] { background: #E1F4E7; border: 1px solid #1DB954; border-radius: 10px; }
            QWidget#trackRow[playing="true"]:hover { background: #D7F0DF; border: 1px solid #1DB954; }
            QLabel#trackTitle[playing="true"] { color: #16883D; font-weight: 800; }
            QLabel#trackIndex[playing="true"] { color: #16883D; font-weight: 900; }
            QPushButton#navButton { color: #555555; }
            QPushButton#navButton:hover, QWidget#trackRow:hover, QListWidget::item:hover { background: #EEEEEE; color: #111111; }
            QPushButton#navButton:checked { background: #E1F4E7; color: #16883D; border-left: 3px solid #1DB954; }
            QPushButton#playButton, QPushButton#accentButton { background: #1DB954; color: #FFFFFF; }
            QPushButton#playButton:hover, QPushButton#accentButton:hover { background: #16883D; }
            QPushButton#bottomFavorite, QPushButton#bottomDislike { background: transparent; border: none; border-radius: 8px; padding: 2px; }
            QPushButton#bottomFavorite:hover, QPushButton#bottomDislike:hover { background: #EEEEEE; }
            QPushButton#bottomFavorite:checked { background: #E1F4E7; }
            QPushButton#bottomDislike:checked { background: #F5E5E5; }
            QPushButton#rowPlay, QPushButton#rowFavorite, QPushButton#rowRemove, QPushButton#filterButton, QPushButton#themeButton { background: #EEEEEE; color: #333333; border-color: #D7D7D7; }
            QPushButton#rowFavorite:checked { color: #16883D; background: #E1F4E7; }
            QPushButton#trackArtistLink { color: #555555; }
            QPushButton#trackArtistLink:hover, QPushButton#textButton { color: #16883D; }
            QLineEdit, QListWidget { background: #FFFFFF; color: #222222; border-color: #D7D7D7; }
            QListWidget::item:selected { background: #E1F4E7; border-color: #1DB954; }
            QSlider::groove:horizontal { background: #D2D2D2; }
            QSlider::sub-page:horizontal { background: #1DB954; }
            QSlider::handle:horizontal { background: #1DB954; }
            QMenu#darkMenu, QMenu { background: #FFFFFF; color: #222222; border-color: #DDDDDD; }
            QMenu#darkMenu::item, QMenu::item { color: #222222; }
            QMenu#darkMenu::item:selected, QMenu::item:selected { background: #E1F4E7; color: #16883D; }
            QFrame#radioCard { background: #FFFFFF; border-color: #DDDDDD; }
            QLabel#radioTrackTitle { color: #181818; }
            QLabel#radioStatus { color: #555555; }
            QDialog#settingsDialog { background: #F5F5F7; }
        """
        self.setStyleSheet(dark_styles if self.theme == "dark" else dark_styles + light_styles)
        if hasattr(self, "artist_header"):
            self.artist_header.setStyleSheet("")
            avatar_url = self.artist_avatar.property("requested_image") if hasattr(self, "artist_avatar") else ""
            if self.theme == "dark" and avatar_url in getattr(self, "pixmap_cache", {}):
                pixmap = self.pixmap_cache[avatar_url]
                if pixmap is not None:
                    self._apply_artist_header_color(pixmap)
        for button in getattr(self, "nav_buttons", []):
            if isinstance(button, AnimatedNavButton):
                button.set_theme(self.theme)
        for menu in (getattr(self, "sort_menu", None), getattr(self, "options_menu", None)):
            if menu is None:
                continue
            if self.theme == "dark":
                menu.setStyleSheet("QMenu{background:#282828;color:#fff;border:1px solid #3b3b3b;padding:7px;} QMenu::item{padding:10px 22px 10px 14px;border-radius:7px;} QMenu::item:selected{background:#3a3a3a;color:#1DB954;}")
            else:
                menu.setStyleSheet("QMenu{background:#fff;color:#222;border:1px solid #ddd;padding:7px;} QMenu::item{padding:10px 22px 10px 14px;border-radius:7px;} QMenu::item:selected{background:#e1f4e7;color:#16883d;}")

    # ---------------------------------------------------------
    # Все сигналы.
    # ---------------------------------------------------------

    def connect_signals(self):
        for i, button in enumerate(self.nav_buttons):
            button.clicked.connect(lambda checked=False, index=i: self.set_source(self.nav_data[index][2]))

        self.sidebar_toggle.clicked.connect(self.toggle_sidebar)
        self.queue_toggle.clicked.connect(self.toggle_queue)
        self.search_button.clicked.connect(self.start_search)
        self.back_button.clicked.connect(self.return_to_start_screen)
        self.artist_name_label.clicked.connect(
            lambda checked=False: self.search_artist_name(self.active_artist_profile, self.current_source)
        )
        self.artist_shuffle_button.clicked.connect(self.shuffle_artist_tracks)
        self.artist_mix_button.clicked.connect(self.start_artist_mix)
        self.search_input.returnPressed.connect(self.start_search)
        self.search_input.textEdited.connect(self.on_search_text_edited)
        self.search_input.textChanged.connect(self.update_browse_empty_state)
        self.search_debounce_timer = QTimer(self)
        self.search_debounce_timer.setSingleShot(True)
        self.search_debounce_timer.setInterval(450)
        self.search_debounce_timer.timeout.connect(self.start_search)

        def schedule_live_search(text):
            source = self.current_source
            query = str(text or "").strip()
            submitted = self.search_submitted_queries.get(source, "")
            if source in ("youtube", "soundcloud") and len(query) >= 3 and query != submitted:
                self.search_debounce_timer.start()
            else:
                self.search_debounce_timer.stop()

        self.search_input.textChanged.connect(schedule_live_search)
        self.theme_button.clicked.connect(self.toggle_theme)
        self.connect_account_button.clicked.connect(self.connect_youtube_account)
        self.connect_soundcloud_button.clicked.connect(self.connect_soundcloud_account)
        self.sync_account_button.clicked.connect(self.sync_youtube_likes)
        self.disconnect_account_button.clicked.connect(self.disconnect_youtube_account)
        # Строки TrackRow сами обрабатывают один клик; не подключаем itemClicked,
        # чтобы одно нажатие не добавляло одну песню в очередь дважды.
        self.source_list.customContextMenuRequested.connect(self.open_result_menu)
        self.likes_tabs.currentChanged.connect(self.on_likes_tab_changed)
        self.likes_search_input.textChanged.connect(self.on_likes_search_changed)
        for list_widget in (self.source_list, self.youtube_likes_list,
                            self.soundcloud_likes_list, self.likes_list, self.queue_list):
            list_widget.verticalScrollBar().valueChanged.connect(
                lambda value, lw=list_widget: self.on_list_scroll(lw, value)
            )
        for list_widget in (self.youtube_likes_list, self.soundcloud_likes_list, self.likes_list):
            list_widget.verticalScrollBar().rangeChanged.connect(
                lambda _minimum, _maximum, lw=list_widget:
                    QTimer.singleShot(0, lambda lw=lw: self.maybe_load_more_likes(lw))
            )
        self.queue_list.customContextMenuRequested.connect(self.open_queue_menu)
        self.clear_queue_button.clicked.connect(self.clear_queue)

        self.previous_button.clicked.connect(self.play_previous)
        self.play_button.clicked.connect(self.toggle_playback)
        self.bottom_favorite_button.clicked.connect(
            lambda checked=False: self.toggle_current_favorite()
        )
        self.bottom_dislike_button.clicked.connect(
            lambda checked=False: self.dislike_current_track()
        )
        self.next_button.clicked.connect(lambda: self.play_next())
        self.stop_button.clicked.connect(self.stop_all)
        self.bottom_queue_button.clicked.connect(self.toggle_queue)
        self.shuffle_button.toggled.connect(self.on_shuffle_changed)
        self.repeat_button.clicked.connect(self.cycle_repeat)
        self.volume_slider.valueChanged.connect(self.set_volume)
        self.seek_slider.sliderPressed.connect(self.seek_pressed)
        self.seek_slider.sliderReleased.connect(self.seek_released)

        # Каждый плеер сообщает номер своего слота. Это необходимо,
        # чтобы движение старой песни не считалось началом новой.
        for index, player in enumerate(self.players):
            player.positionChanged.connect(
                lambda position, i=index: self.on_slot_position(i, position)
            )
            player.durationChanged.connect(
                lambda duration, i=index: self.on_slot_duration(i, duration)
            )
            player.playbackStateChanged.connect(
                lambda state, i=index: self.on_slot_playback_state(i, state)
            )
            player.mediaStatusChanged.connect(
                lambda status, i=index: self.on_slot_status(i, status)
            )
            player.errorOccurred.connect(
                lambda error, message, i=index: self.on_slot_error(i, error, message)
            )

    # ---------------------------------------------------------
    # Меню и настройки. Все элементы сохраняются через QSettings.
    # ---------------------------------------------------------

    def update_theme_button(self):
        self.theme_button.setText("☀" if self.theme == "dark" else "☾")
        self.theme_button.setToolTip(
            "Переключить на светлую тему" if self.theme == "dark"
            else "Переключить на тёмную тему"
        )

    def toggle_theme(self):
        self.theme = "light" if self.theme == "dark" else "dark"
        self.settings.setValue("theme", self.theme)
        self.update_theme_button()
        self.apply_styles()
        self.save_preferences()

    def open_settings(self):
        dialog = SettingsDialog(self)
        dialog.exec()

    def show_about(self):
        QMessageBox.about(
            self, "О программе",
            "Music Player · Green Edition\nPython + PyQt6 + yt-dlp\n\n"
            "Локальные лайки хранятся в favorites.json. Импорт YouTube Music использует cookie-файл или сессию браузера; пароль Google приложение не запрашивает."
        )

    def save_preferences(self):
        self.settings.setValue("volume", int(round(self.volume * 100)))
        self.settings.setValue("search_limit", self.result_limit)
        self.settings.setValue("audio_quality", self.audio_quality)
        self.settings.setValue("minimize_to_tray", self.minimize_to_tray)
        self.settings.setValue("hide_on_minimize", self.hide_on_minimize)
        self.settings.setValue("fade_duration_ms", self.fade_duration_ms)
        self.settings.setValue("fade_steps", round(self.fade_duration_ms / 30))
        self.settings.setValue("sidebar_collapsed", self.sidebar_collapsed)
        self.settings.setValue("repeat_mode", self.repeat_mode)
        self.settings.setValue("shuffle", self.shuffle_enabled)
        self.settings.setValue("autoplay_playlists", self.autoplay_playlists)
        self.settings.setValue("theme", self.theme)
        self.settings.setValue("spotify_theme", self.theme)
        self.settings.setValue("youtube_cookie_file", self.youtube_cookie_file)
        self.settings.setValue("youtube_auth_mode", self.youtube_auth_mode)
        self.settings.setValue("youtube_auth_browser", self.youtube_auth_browser)
        self.settings.sync()

    def on_shuffle_changed(self, enabled):
        self.shuffle_enabled = bool(enabled)
        self.shuffle_future = None
        if not self.shuffle_enabled:
            self._shuffle_history.clear()
        self.shuffle_button.setIcon(control_icon(
            "shuffle", "#1DB954" if self.shuffle_enabled else "#CEC3CC"))
        self.shuffle_button.setToolTip(
            "Перемешивание: вкл." if self.shuffle_enabled else "Перемешивание: выкл.")
        if self.current_track is not None:
            self.prepare_next_track()

    def cycle_repeat(self):
        modes = ("off", "all", "one")
        self.repeat_mode = modes[(modes.index(self.repeat_mode) + 1) % len(modes)]
        self._finish_guard_url = ""
        self.refresh_repeat_button()
        self.shuffle_future = None
        if self.current_track is not None:
            self.prepare_next_track()

    def refresh_repeat_button(self):
        labels = {"off": "Повтор: выкл.", "all": "Повтор всей очереди", "one": "Повтор одного трека"}
        self.repeat_button.setChecked(self.repeat_mode != "off")
        self.repeat_button.setIcon(control_icon(
            "repeat", "#1DB954" if self.repeat_mode != "off" else "#CEC3CC"))
        self.repeat_button.setText("1" if self.repeat_mode == "one" else "")
        self.repeat_button.setToolTip(labels[self.repeat_mode])

    def peek_next_index(self):
        """Один и тот же выбор используется для предзагрузки и кнопки Next."""
        count = len(self.queue_tracks)
        current = (self.requested_index if self.requested_track is not None
                   else self.current_queue_index)
        if count == 0:
            return None
        # Кнопка «Следующий» пропускает трек даже в режиме повтора одного.
        # Автоповтор текущего трека отдельно обрабатывает handle_track_finished().
        if self.shuffle_enabled:
            if count == 1:
                return 0 if self.repeat_mode == "all" else None
            if (self.shuffle_future is not None
                    and 0 <= self.shuffle_future < count and self.shuffle_future != current):
                return self.shuffle_future
            self.shuffle_future = self._smart_shuffle_choice(current)
            return self.shuffle_future
        index = current + 1
        if index < count:
            return index
        if self.repeat_mode == "all":
            return 0
        return None

    @staticmethod
    def _track_energy_hint(track):
        """Энергии/BPM у нас нет: используем грубую эвристику по длительности."""
        try:
            seconds = float(track.get("duration") or 0)
        except (ValueError, TypeError):
            seconds = 0
        if seconds <= 0:
            return 0.5
        for limit, energy in ((120, 0.9), (180, 0.7), (240, 0.55),
                              (360, 0.4), (480, 0.3)):
            if seconds < limit:
                return energy
        return 0.2

    def _smart_shuffle_choice(self, current_index):
        tracks = self.queue_tracks
        history = set(self._shuffle_history)
        def eligible(index, allow_history=False):
            track = tracks[index]
            return (index != current_index and isinstance(track, dict)
                    and bool(track.get("url")) and not self.is_disliked(track)
                    and (allow_history or track.get("queue_id") not in history))

        candidates = [i for i in range(len(tracks)) if eligible(i)]
        if not candidates:
            candidates = [i for i in range(len(tracks)) if eligible(i, True)]
        if not candidates:
            candidates = [i for i in range(len(tracks)) if i != current_index]
        if not candidates:
            return None

        current = (tracks[current_index] if 0 <= current_index < len(tracks)
                   and isinstance(tracks[current_index], dict) else {})
        energy = self._track_energy_hint(current)
        artist = str(current.get("artist") or "").strip().casefold()
        weights = []
        for index in candidates:
            track = tracks[index]
            if not isinstance(track, dict):
                weights.append(0.05)
                continue
            weight = 1.0 + 0.6 * (1.0 - abs(self._track_energy_hint(track) - energy))
            if self.is_favorite(track):
                weight += 0.3
            candidate_artist = str(track.get("artist") or "").strip().casefold()
            if artist and candidate_artist == artist:
                weight -= 0.4
            weights.append(max(0.05, weight))
        total = sum(weights)
        if total <= 0:
            return random.choice(candidates)
        threshold = random.uniform(0, total)
        cumulative = 0.0
        for index, weight in zip(candidates, weights):
            cumulative += weight
            if cumulative >= threshold:
                return index
        return candidates[-1]

    def _is_youtube_likes_playback(self):
        """Определяет воспроизведение лайков, даже если общий обработчик сменил queue_mode."""
        if self.radio_mode_active or self.queue_mode == "radio":
            return False
        if self.queue_mode == "youtube_likes":
            return True
        for track in (self.requested_track, self.current_track):
            if isinstance(track, dict) and track.get("youtube_music_like"):
                return True
        return False

    def ensure_following_track_prepared(self):
        """Заранее готовит следующий трек или начинает искать радио до тишины."""
        if (self.current_track is None or self.requested_track is not None
                or self.pending_slot is not None):
            return

        if self.radio_mode_active:
            self.maybe_refill_radio()
            return

        next_index = self.peek_next_index()
        if next_index is not None:
            QTimer.singleShot(0, self.prepare_next_track)
            return

        # SoundCloud likes продолжают собственную пагинацию; не подменяем её
        # поиском соседних результатов, пока импорт ещё может продолжиться.
        if self.queue_mode == "soundcloud_likes" and self._soundcloud_likes_loading:
            return
        if self.queue_mode == "supermix" or self._is_youtube_likes_playback():
            return

        candidate = None
        if self.queue_mode != "soundcloud_likes":
            candidate = self.search_neighbor_track(1)
        if candidate is not None:
            candidate_url = str(candidate.get("url") or "")
            candidate_source = str(candidate.get("source") or "")
            already_queued = any(
                str(item.get("url") or "") == candidate_url
                and str(item.get("source") or "") == candidate_source
                for item in self.queue_tracks
            )
            if not already_queued:
                queued = dict(candidate)
                queued["queue_id"] = uuid4().hex
                self.queue_tracks.append(queued)
                self.append_queue_item(queued, len(self.queue_tracks) - 1)
                self.update_queue_count()
                QTimer.singleShot(0, self.prepare_next_track)
                return
            # Если кандидат уже был в проигранной части очереди, не запускаем его
            # повторно только потому, что поиск вернул ту же запись.

        current = self.current_track
        source = str((current or {}).get("source") or "")
        if source not in ("youtube", "soundcloud"):
            return

        # Радио запускается заранее, пока текущая песня ещё звучит, а не после
        # EndOfMedia. Поэтому у поиска есть почти вся длительность текущего трека.
        self.radio_mode_active = True
        self.queue_mode = "radio"
        self.radio_artist_context = str(
            getattr(self, "active_artist_profile", "") or ""
        ).strip() if self.artist_profile_open else ""
        self.radio_seen_urls = {
            self.radio_track_key(item) for item in self.queue_tracks if isinstance(item, dict)
        }
        self.radio_seen_urls.add(self.radio_track_key(current))
        self.radio_refill_attempt_key = ""
        self.radio_refill_next_allowed_at = 0.0
        self._radio_refill_failed_attempts = 0
        self._radio_waiting_for_tracks = False
        self.set_status(
            "Следующий трек не найден в текущем списке — заранее подбираю похожую музыку…",
            source
        )
        QTimer.singleShot(0, lambda: self.maybe_refill_radio(force=True)
                          if self.radio_mode_active else None)

    def handle_track_finished(self):
        """Один автопереход на окончание потока; сначала соблюдаем очередь."""
        # Если следующий трек уже запрошен/загружается, commit_switch сам сбросит
        # защиту. Не сбрасываем её здесь, иначе EndOfMedia может вызвать дубль.
        if self.requested_track is not None or self.pending_slot is not None:
            return

        if self.repeat_mode == "one" and self.current_track is not None:
            self._finish_transition_pending = False
            self._finish_guard_url = ""
            self.player.setPosition(0)
            self.player.play()
            return

        if self.queue_mode == "supermix" or self._is_youtube_likes_playback():
            next_index = self.peek_next_index()
            if next_index is not None:
                self.play_queue_index(next_index)
                return
            # Не переключаемся на похожие результаты поиска после последнего лайка.
            self._finish_transition_pending = False
            self._finish_guard_url = str((self.current_track or {}).get("url") or "")
            self.set_status("Супермикс закончился — собери новый по своим лайкам."
                            if self.queue_mode == "supermix" else "Лайки YouTube Music закончились.", "youtube")
            return

        if self.queue_mode == "soundcloud_likes":
            next_index = self.peek_next_index()
            if next_index is not None:
                self.play_queue_index(next_index)
                return
            if self._soundcloud_likes_loading:
                self._finish_transition_pending = False
                self._soundcloud_queue_waiting = True
                self.set_status("SoundCloud: догружаю следующую страницу лайков…", "soundcloud")
                return

        if self.radio_mode_active:
            next_index = self.peek_next_index()
            if next_index is None:
                # Радио уже ищется заранее. Если поиск ещё идёт, ждём его; если
                # закончился без результатов, on_radio_refill_finished повторит попытку.
                self._finish_transition_pending = False
                self._radio_waiting_for_tracks = True
                self.maybe_refill_radio(force=True)
                return
            self.play_queue_index(next_index)
            return

        # Очередь пользователя/плейлиста всегда приоритетнее результатов поиска.
        # Старый порядок сначала брал search_neighbor_track и мог перескочить
        # на другой трек из устаревшей выдачи вместо выбранной очереди.
        next_index = self.peek_next_index()
        if next_index is not None:
            self.play_queue_index(next_index)
            return

        candidate = None if self.queue_mode == "soundcloud_likes" else self.search_neighbor_track(1)
        if candidate is not None:
            self.play_candidate_track(candidate)
            return

        # Ещё раз проверяем актуальную выдачу: она могла обновиться в момент
        # завершения трека, пока Qt сообщал EndOfMedia.
        if not self.queue_tracks and self.current_source in ("youtube", "soundcloud"):
            active_track = self.current_track or self.requested_track
            active_url = str((active_track or {}).get("url") or "")
            source_tracks = self.source_results.get(self.current_source, [])
            current_in_results = bool(active_url and any(
                isinstance(item, dict)
                and str(item.get("url") or "") == active_url
                and str(item.get("source") or "") == self.current_source
                for item in source_tracks
            ))
            if not source_tracks or not current_in_results:
                candidate = self.search_neighbor_track(1)
                if candidate is not None:
                    self.play_candidate_track(candidate)
                    return

        # Если очередь закончилась, радио должно было начать искаться заранее.
        # Оставляем запасной путь для очень коротких треков/медленной сети.
        last_track = self.current_track or self.requested_track
        if isinstance(last_track, dict) and last_track.get("source") in ("youtube", "soundcloud"):
            if self.queue_tracks:
                queued_last = self.queue_tracks[-1]
                if (isinstance(queued_last, dict)
                        and self.radio_track_key(queued_last) != self.radio_track_key(last_track)):
                    self.play_queue_index(len(self.queue_tracks) - 1)
                    return
            self.radio_mode_active = True
            self.queue_mode = "radio"
            self.radio_seen_urls = {
                self.radio_track_key(item) for item in self.queue_tracks if isinstance(item, dict)
            }
            self.radio_seen_urls.add(self.radio_track_key(last_track))
            self.radio_refill_attempt_key = ""
            self.radio_refill_next_allowed_at = 0.0
            self._radio_refill_failed_attempts = 0
            self._radio_waiting_for_tracks = True
            self._finish_transition_pending = False
            self._finish_guard_url = str(last_track.get("url", ""))
            self.set_status("Подбираю похожую музыку для продолжения радио…", last_track.get("source"))
            self.maybe_refill_radio(force=True)
            return

        self._finish_transition_pending = False
        self._finish_guard_url = str((self.current_track or {}).get("url", ""))

    # ---------------------------------------------------------
    # Сворачивание меню и показ очереди по требованию.
    # ---------------------------------------------------------

    def toggle_sidebar(self):
        self.sidebar_collapsed = not self.sidebar_collapsed
        collapsed = self.sidebar_collapsed
        self.sidebar.setFixedWidth(65 if collapsed else 210)
        self.sidebar.layout().setContentsMargins(8 if collapsed else 12, 14, 8 if collapsed else 12, 14)
        self.menu_hint.setVisible(not collapsed)
        self.sidebar_toggle.setText("›" if collapsed else "‹")
        self.sidebar_toggle.setToolTip("Развернуть меню" if collapsed else "Свернуть меню")
        for button, (icon, title, _) in zip(self.nav_buttons, self.nav_data):
            if isinstance(button, AnimatedNavButton):
                button.set_collapsed(collapsed)
            else:
                button.setText(icon if collapsed else f"{icon}    {title}")

    def toggle_queue(self):
        """Выдвигает очередь в самом приложении, не создавая новое окно."""
        self.queue_open = not self.queue_open
        self.queue_animation.stop()
        self.queue_animation.setStartValue(self.queue_panel.maximumWidth())
        self.queue_animation.setEndValue(285 if self.queue_open else 0)
        self.queue_animation.start()
        self.bottom_queue_button.setToolTip(
            "Скрыть очередь" if self.queue_open else "Открыть очередь"
        )
        self.bottom_queue_button.setIcon(control_icon(
            "queue", "#1DB954" if self.queue_open else "#CEC3CC"
        ))

    def fade_to_page(self, page):
        """Короткое затухание при смене внутреннего экрана (без отдельного окна)."""
        if self.page_animation is not None:
            self.page_animation.stop()
            self.page_animation.deleteLater()
            if self._animated_page is not None:
                self._animated_page.setGraphicsEffect(None)
            self.page_animation = None
        self.view_stack.setCurrentWidget(page)
        effect = QGraphicsOpacityEffect(page)
        page.setGraphicsEffect(effect)
        effect.setOpacity(0.0)
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(260)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.finished.connect(lambda p=page, a=animation: self.end_page_animation(p, a))
        animation.finished.connect(animation.deleteLater)
        self.page_animation = animation
        self._animated_page = page
        animation.start()

    def end_page_animation(self, page, animation):
        if self.page_animation is animation:
            # QGraphicsEffect принадлежит виджету, поэтому снимаем его
            # только когда анимация завершилась.
            page.setGraphicsEffect(None)
            self.page_animation = None
            self._animated_page = None

    # ---------------------------------------------------------
    # Смена источника и параметры поиска.
    # ---------------------------------------------------------

    def change_sort(self, mode, title, refresh=True):
        """Внутренний совместимый обработчик; сортировка больше не показывается в UI."""
        self.sort_mode = mode
        self.sort_button.setText(title + "  ▾")
        self.sort_button.setToolTip("Сортировка треков исполнителя: популярность или дата публикации.")
        if hasattr(self, "artist_popular_label"):
            self.artist_popular_label.setText("Треки исполнителя")
        if not refresh:
            return
        artist = str(getattr(self, "active_artist_profile", "") or "").strip()
        if (artist and not self.artist_header.isHidden()
                and self.current_source in ("youtube", "soundcloud")):
            # В профиле сортируем именно треки артиста, даже если исходный запрос
            # был написан с дополнительными словами. Повторный клик «Найти» не нужен.
            if self.search_input.text().strip().casefold() != artist.casefold():
                self.search_input.setText(artist)
            self.artist_profile_query = artist
            self.search_artist_target = artist
            self.start_search()

    def change_limit(self, value):
        # Выбор количества результатов находится только в настройках.
        self.result_limit = value

    def set_source(self, source):
        if self.current_source in self.saved_queries:
            self.saved_queries[self.current_source] = self.search_input.text()
        self.current_source = source
        # Профиль артиста не открывается автоматически при смене вкладки.
        self.artist_profile_query = ""
        self.active_artist_profile = ""
        self.active_artist_profile_url = ""
        self.search_artist_target = ""
        self.artist_profile_open = False
        self.artist_header.hide()
        self.sort_button.hide()
        for button, (_, _, button_source) in zip(self.nav_buttons, self.nav_data):
            button.setChecked(button_source == source)

        if source == "likes":
            self.search_row.hide()
            self.artist_header.hide()
            self.start_cards_scroll.hide()
            self.browser_search_button.hide()
            self.refresh_likes_list()
            self.last_library_page = self.likes_page
            self.fade_to_page(self.likes_page)
            # SoundCloud-кэш сразу показывается из файла; сеть нужна только при
            # первом импорте/устаревшем кэше. Явное обновление доступно в настройках.
            if self.youtube_auth_kwargs() and time.time() - self._youtube_last_sync_at > 60:
                if self.youtube_sync_worker is None or not self.youtube_sync_worker.isRunning():
                    QTimer.singleShot(0, self.sync_youtube_likes)
            if self.soundcloud_is_connected() and not self.soundcloud_cache_is_fresh():
                QTimer.singleShot(0, self.load_soundcloud_account_content)
            return

        self.search_row.show()
        self.rebuild_start_cards()
        self.page_title.setText("YouTube Music" if source == "youtube" else "SoundCloud")
        self.page_description.setText("Музыка на одном экране")
        self.results_label.setText("РЕЗУЛЬТАТЫ ПОИСКА")
        self.search_input.setText(self.saved_queries[source])
        self.source_status.setText(self.source_statuses[source])
        tracks = self.source_results[source]
        self.browser_search_button.setVisible(source == "soundcloud" and not tracks
                                               and bool(self.saved_queries["soundcloud"]))
        self.source_list.clear()
        # При возврате на вкладку показываем обычные результаты. Профиль артиста
        # открывается только по клику на имя исполнителя в строке трека.
        self.artist_header.hide()
        self.sort_button.hide()
        self.active_artist_profile = ""
        for track in tracks:
            self.add_result(track)
        self.update_playing_row_highlight()
        self.last_library_page = self.browse_page
        self.update_browse_empty_state()
        self.fade_to_page(self.browse_page)
        if source == "soundcloud" and not self.search_input.text().strip() and self.soundcloud_is_connected():
            if not self.soundcloud_cache_is_fresh():
                QTimer.singleShot(0, self.load_soundcloud_account_content)

    def set_status(self, message, source=None):
        source = source or self.current_source
        self.source_statuses[source] = message
        if self.current_source == source:
            self.source_status.setText(message)
            self.source_status.setToolTip(message)
        if source == "likes" and hasattr(self, "likes_account_status"):
            self.likes_account_status.setText(message)

    # ---------------------------------------------------------
    # Поиск выполняется в фоне: окно не зависает.
    # ---------------------------------------------------------

    def on_search_text_edited(self, _text):
        """Ручной ввод нового запроса закрывает профиль артиста и его сортировку."""
        if self.artist_profile_open or not self.artist_header.isHidden():
            self.artist_profile_open = False
            self.artist_profile_query = ""
            self.search_artist_target = ""
            self.active_artist_profile = ""
            self.active_artist_profile_url = ""
            self.artist_header.hide()
            self.sort_button.hide()
        self.update_browse_empty_state()

    def update_browse_empty_state(self, *_):
        """Показывает стартовые карточки или результаты в зависимости от запроса."""
        if not hasattr(self, "start_cards_widget"):
            return
        query = self.search_input.text().strip()
        query_empty = not query
        show_cards = query_empty and self.current_source in ("youtube", "soundcloud")
        self.start_cards_scroll.setVisible(show_cards)
        self.results_label.setVisible(not show_cards)
        self.source_status.setVisible(not show_cards)
        self.table_header.setVisible(not show_cards)
        self.source_list.setVisible(not show_cards)
        self.back_button.setVisible(not show_cards and bool(query))

        # И карточка артиста, и сортировка существуют только в режиме профиля,
        # который активируется нажатием на ник исполнителя.
        if show_cards:
            self.artist_header.hide()
            self.sort_button.hide()
            self.back_button.hide()
        elif query_empty and not self.artist_profile_open:
            self.artist_header.hide()
            self.sort_button.hide()
        profile_visible = (
            self.artist_profile_open
            and not show_cards
            and not self.artist_header.isHidden()
            and bool(str(getattr(self, "active_artist_profile", "") or "").strip())
        )
        self.sort_button.hide()

    def return_to_start_screen(self):
        """Возвращает к стартовым карточкам активного сервиса, не останавливая музыку."""
        if self.current_source not in ("youtube", "soundcloud"):
            self.set_source("youtube")
        source = self.current_source
        if self.search_worker is not None and self.search_worker.isRunning():
            self.search_worker.cancel()
        self.artist_profile_query = ""
        self.search_artist_target = ""
        self.artist_profile_open = False
        self.active_artist_profile = ""
        self.active_artist_profile_url = ""
        self.auto_play_next_search = False
        self.auto_play_generation = -1
        self._pending_direct_url = ""
        self.search_input.blockSignals(True)
        self.search_input.clear()
        self.search_input.blockSignals(False)
        self.saved_queries[source] = ""
        self.search_submitted_queries[source] = ""
        self.source_results[source] = []
        self.source_list.clear()
        self.artist_header.hide()
        self.browser_search_button.hide()
        self.rebuild_start_cards()
        self.set_status("Открой свои лайки или введи название трека/исполнителя.", source)
        self.update_browse_empty_state()
        self.fade_to_page(self.browse_page)
        if source == "soundcloud" and self.soundcloud_is_connected():
            QTimer.singleShot(0, self.load_soundcloud_account_content)

    def start_quick_start(self, query):
        """Карточка быстрого старта: ищет подборку и запускает первый найденный трек."""
        if self.current_source not in ("youtube", "soundcloud"):
            self.set_source("youtube")
        self.artist_profile_query = ""
        self.search_artist_target = ""
        self.artist_profile_open = False
        self.active_artist_profile = ""
        self.active_artist_profile_url = ""
        self._pending_direct_url = ""
        # Не запускаем трек автоматически, если пользователь не включил это
        # поведение в настройках. Работает одинаково для YouTube и SoundCloud.
        self.auto_play_next_search = bool(self.autoplay_playlists)
        self.search_input.setText(query)
        self.start_search()

    def _eligible_mix_tracks(self, source):
        if source == "youtube":
            candidates = self.youtube_liked_tracks
        elif source == "soundcloud":
            candidates = self.soundcloud_liked_tracks
        else:
            candidates = list(self.favorites.values())
        tracks, seen = [], set()
        for track in candidates:
            if not isinstance(track, dict) or not track.get("url") or self.is_disliked(track):
                continue
            key = self.youtube_video_id(track) if source == "youtube" else self.favorite_key(track)
            key = key or self.favorite_key(track)
            if key not in seen:
                tracks.append(dict(track))
                seen.add(key)
        return tracks

    def play_personal_mix(self, source=None):
        """Создаёт персональный микс из уже импортированных лайков."""
        source = source or self.current_source
        tracks = self._eligible_mix_tracks(source)
        if not tracks:
            QMessageBox.information(self, "Нет любимых треков",
                                    "Открой «Мои лайки» и добавь любимые треки или синхронизируй библиотеку.")
            return
        random.shuffle(tracks)
        mix_tracks = tracks[:50]
        self._start_music_queue(mix_tracks, source, f"Перемешаны твои лайки: {len(mix_tracks)} треков.")

    def _set_supermix_busy(self, busy):
        for card in self.start_cards:
            if card.title == "Супермикс":
                card.setEnabled(not busy)
                card.subtitle = ("Ищу новые треки по твоим лайкам…" if busy
                                 else "Твои любимые треки · немного близкой новой музыки")
                card.setCursor(Qt.CursorShape.BusyCursor if busy else Qt.CursorShape.PointingHandCursor)
                card.update()

    def _cancel_supermix(self):
        if self.supermix_worker is not None:
            self.supermix_worker.cancel()
            self.supermix_worker = None
            self._set_supermix_busy(False)

    def _youtube_disliked_video_ids(self):
        return {self.youtube_video_id({"url": key.split("|", 1)[1]})
                for key in self.disliked_track_keys if key.startswith("youtube|")}

    def play_supermix(self):
        """Запрашивает новые песни по лайкам, сохраняя текущую музыку до результата."""
        tracks = self._eligible_mix_tracks("youtube")
        if not tracks:
            QMessageBox.information(self, "Супермикс",
                                    "Сначала добавь треки в «Мои лайки» YouTube Music.")
            return
        self._cancel_supermix()
        worker = SupermixWorker(tracks, self._youtube_disliked_video_ids(), self)
        self.supermix_worker = worker
        worker.result_ready.connect(lambda result, note, w=worker: self.on_supermix_ready(w, result, note))
        worker.failed.connect(lambda message, w=worker: self.on_supermix_error(w, message))
        worker.finished.connect(lambda w=worker: self.on_supermix_finished(w))
        worker.finished.connect(worker.deleteLater)
        self._set_supermix_busy(True)
        self.set_status("Супермикс: подбираю новые треки по твоим лайкам…", "youtube")
        worker.start()

    def on_supermix_ready(self, worker, tracks, note):
        if worker is not self.supermix_worker or self._force_exit:
            return
        excluded = self._youtube_disliked_video_ids()
        result, seen = [], set(excluded)
        for track in tracks:
            video_id = self.youtube_video_id(track)
            if track.get("supermix_favorite") and not self.is_youtube_music_liked(track):
                continue
            if video_id and video_id not in seen and not self.is_disliked(track):
                result.append(dict(track))
                seen.add(video_id)
        if not result:
            self.on_supermix_error(worker, "Найденные песни больше недоступны в твоём миксе. Попробуй собрать Супермикс ещё раз.")
            return
        new_count = sum(not self.is_youtube_music_liked(track) for track in result)
        message = f"Супермикс: {len(result)} треков · новых: {new_count}."
        if "Часть рекомендаций" in note:
            message += " Часть рекомендаций временно недоступна."
        self._start_music_queue(result, "youtube", message, recommendations=True)

    def on_supermix_error(self, worker, message):
        if worker is not self.supermix_worker or self._force_exit:
            return
        self.set_status(message, "youtube")
        self.show_toast(message, 6000)
        self._set_supermix_busy(False)

    def on_supermix_finished(self, worker):
        if worker is self.supermix_worker:
            self.supermix_worker = None
            self._set_supermix_busy(False)

    def _start_music_queue(self, tracks, source, message, recommendations=False):
        self.cancel_pending_request()
        self.queue_tracks = []
        self.queue_list.clear()
        self.current_queue_index = -1
        self.shuffle_future = None
        self.radio_mode_active = False
        # Кнопки Next и автопереход остаются внутри очереди лайков.
        self.queue_mode = "supermix" if recommendations else ("youtube_likes" if source == "youtube" else "manual")
        self._finish_transition_pending = False
        self._finish_guard_url = ""
        self._auto_failed_tracks.clear()
        self._radio_waiting_for_tracks = False
        self._shuffle_history.clear()
        self._soundcloud_queue_waiting = False
        for track in tracks:
            queued_track = dict(track)
            queued_track["queue_id"] = uuid4().hex
            if source == "youtube" and not recommendations:
                queued_track["youtube_music_like"] = True
            elif recommendations:
                queued_track.pop("youtube_music_like", None)
            self.queue_tracks.append(queued_track)

        self.refresh_queue_list()
        self.toggle_queue_if_hidden()
        self.set_status(message, source)
        self.play_queue_index(0)

    def start_playlist_url(self, title, url, source=None):
        """Открывает прямую ссылку на плейлист через фоновый SearchWorker."""
        url = str(url or "").strip()
        if not url.startswith(("https://", "http://")):
            QMessageBox.warning(self, "Плейлист", "У этой карточки нет корректной ссылки.")
            return
        detected_source = source or ("soundcloud" if "soundcloud.com" in url.lower() else "youtube")
        if detected_source not in ("youtube", "soundcloud"):
            detected_source = "youtube"
        if self.current_source != detected_source:
            self.set_source(detected_source)

        # yt-dlp не во всех версиях распознаёт SoundCloud Charts как плейлисты:
        # страница может вернуться без entries. Поэтому карточки Top 50 / New & Hot
        # запускают поиск через штатный scsearch, а личные /sets и /likes по-прежнему
        # открываются по прямой ссылке.
        if detected_source == "soundcloud" and "/charts/" in url.casefold():
            title_lower = str(title or "").casefold()
            if "new" in title_lower or "hot" in title_lower or "/charts/new" in url.casefold():
                query = "new trending music"
            else:
                query = "popular music hits"
            self.start_quick_start(query)
            return

        self.artist_profile_query = ""
        self.search_artist_target = ""
        self.artist_profile_open = False
        self.active_artist_profile = ""
        self._pending_direct_url = url
        # Загрузка плейлиста не должна сама запускать первый трек по умолчанию.
        self.auto_play_next_search = bool(self.autoplay_playlists)
        self.search_input.setText(str(title or "Мой плейлист"))
        self.start_search()

    def youtube_auth_kwargs(self):
        """Возвращает локальный источник сессии для yt-dlp; секреты не передаются наружу."""
        if self.youtube_auth_mode == "browser" and self.youtube_auth_browser:
            browser_spec = self.youtube_auth_browser
            if self.youtube_auth_profile:
                browser_spec = f"{browser_spec}|{self.youtube_auth_profile}"
            return {"cookies_from_browser": browser_spec}
        if self.youtube_cookie_file and Path(self.youtube_cookie_file).is_file():
            return {"cookie_file": self.youtube_cookie_file}
        return {}

    # ---------------------------------------------------------
    # SoundCloud: подключение сессии и импорт личных данных.
    # ---------------------------------------------------------

    def soundcloud_auth_kwargs(self):
        """Параметры сессии SoundCloud для yt-dlp; пароль не хранится в приложении."""
        if self.soundcloud_auth_mode == "browser" and self.soundcloud_browser:
            return {"cookies_from_browser": self.soundcloud_browser}
        return {}

    def soundcloud_is_connected(self):
        return bool(self.soundcloud_profile_url) or (
            self.soundcloud_auth_mode == "browser" and bool(self.soundcloud_browser)
        )

    @staticmethod
    def normalize_soundcloud_profile_url(raw):
        from urllib.parse import urlparse
        raw = str(raw or "").strip().rstrip("/")
        if not raw:
            return ""
        if not raw.startswith(("https://", "http://")):
            raw = "https://" + raw
        parsed = urlparse(raw)
        if parsed.netloc.lower() not in ("soundcloud.com", "www.soundcloud.com"):
            return ""
        path = parsed.path.rstrip("/")
        for suffix in ("/likes", "/sets", "/tracks", "/albums"):
            if path.lower().endswith(suffix):
                path = path[:-len(suffix)].rstrip("/")
        if not path or path == "/you":
            return "https://soundcloud.com/you"
        return "https://soundcloud.com" + path

    def soundcloud_cache_identity(self):
        """Идентификатор профиля, к которому привязан локальный кэш."""
        if self.soundcloud_auth_mode == "browser" and self.soundcloud_browser:
            return f"browser:{self.soundcloud_browser.casefold()}"
        return str(self.soundcloud_profile_url or "").strip().rstrip("/").casefold()

    def soundcloud_cache_is_fresh(self, max_age=24 * 60 * 60):
        """Не скачивает тысячи лайков заново при каждом запуске; обновление доступно вручную."""
        synced_at = float(getattr(self, "_soundcloud_likes_synced_at", 0.0) or 0.0)
        if synced_at <= 0:
            return False
        age = time.time() - synced_at
        if age < -300 or age > max_age:
            return False
        saved_identity = str(getattr(self, "_soundcloud_cache_profile", "") or "").casefold()
        current_identity = self.soundcloud_cache_identity()
        if saved_identity and current_identity and saved_identity != current_identity.casefold():
            return False
        return True

    def load_soundcloud_likes(self):
        try:
            if self.soundcloud_likes_file.exists():
                raw = json.loads(self.soundcloud_likes_file.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self._soundcloud_likes_synced_at = float(raw.get("synced_at") or 0.0)
                    self._soundcloud_cache_profile = str(raw.get("profile") or "")
                    playlists = raw.get("playlists", [])
                    self._soundcloud_cached_playlists = [dict(item) for item in playlists if isinstance(item, dict)] if isinstance(playlists, list) else []
                    tracks = raw.get("tracks", [])
                    current_identity = self.soundcloud_cache_identity()
                    if (self._soundcloud_cache_profile and current_identity
                            and self._soundcloud_cache_profile.casefold() != current_identity.casefold()):
                        # Не показываем лайки другого явно выбранного профиля.
                        self._soundcloud_likes_synced_at = 0.0
                        self._soundcloud_cached_playlists = []
                        return []
                elif isinstance(raw, list):
                    # Поддержка старого формата: первый запуск новой версии
                    # использует прежний кэш сразу, затем сохранит метаданные.
                    tracks = raw
                    self._soundcloud_likes_synced_at = 0.0
                else:
                    tracks = []
                if isinstance(tracks, list):
                    return [dict(track, source="soundcloud", soundcloud_like=True)
                            for track in tracks if isinstance(track, dict) and track.get("url")]
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as error:
            logging.getLogger("aurora").info(f"[Music Player] Не удалось прочитать кэш лайков SoundCloud: {error}")
        return []

    def save_soundcloud_likes(self, immediate=False):
        """Планирует сохранение кэша или записывает его немедленно по запросу."""
        timer = getattr(self, "_soundcloud_likes_save_timer", None)
        if immediate:
            if timer is not None:
                timer.stop()
            self._write_soundcloud_likes_file()
            return
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.setInterval(2000)
            timer.timeout.connect(self._write_soundcloud_likes_file)
            self._soundcloud_likes_save_timer = timer
        timer.start()

    def _write_soundcloud_likes_file(self):
        """Атомарно записывает кэш лайков SoundCloud на диск."""
        try:
            temporary = self.soundcloud_likes_file.with_suffix(".tmp")
            payload = {
                "version": 2,
                "profile": self.soundcloud_cache_identity(),
                "synced_at": float(self._soundcloud_likes_synced_at or 0.0),
                "tracks": self.soundcloud_liked_tracks,
                "playlists": self.soundcloud_account_playlists,
            }
            temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            temporary.replace(self.soundcloud_likes_file)
            self._soundcloud_cache_profile = payload["profile"]
            self._soundcloud_cached_playlists = list(self.soundcloud_account_playlists)
        except OSError as error:
            logging.getLogger("aurora").info(f"[Music Player] Не удалось сохранить кэш лайков SoundCloud: {error}")

    def connect_soundcloud_account(self):
        """Диалог сессии браузера или публичной ссылки на профиль SoundCloud."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Подключить SoundCloud")
        dialog.setMinimumWidth(570)
        style_dialog_for_theme(dialog, "soundcloudAuthDialog", self.theme)
        root = QVBoxLayout(dialog)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(12)
        title = QLabel("Подключение SoundCloud")
        title.setObjectName("settingsTitle")
        root.addWidget(title)
        hint = QLabel(
            "Сессия браузера нужна для личных данных, которые доступны только после входа. "
            "Ссылка на профиль позволяет читать только публичные плейлисты и лайки. "
            "Пароль SoundCloud не вводится в плеере."
        )
        hint.setObjectName("settingsHint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        mode = QComboBox()
        mode.addItem("Сессия браузера (для личных лайков)", "browser")
        mode.addItem("Публичная ссылка на профиль", "profile")
        mode.setCurrentIndex(0 if self.soundcloud_auth_mode == "browser" else 1)
        root.addWidget(mode)

        browser_row = QHBoxLayout()
        browser_label = QLabel("Браузер")
        browser_combo = QComboBox()
        for label, value in (("Google Chrome", "chrome"), ("Microsoft Edge", "edge"),
                             ("Firefox", "firefox"), ("Waterfox", "waterfox"),
                             ("Brave", "brave"), ("Opera", "opera")):
            browser_combo.addItem(label, value)
        idx = browser_combo.findData(self.soundcloud_browser)
        if idx >= 0:
            browser_combo.setCurrentIndex(idx)
        browser_row.addWidget(browser_label)
        browser_row.addWidget(browser_combo, 1)
        root.addLayout(browser_row)

        profile_label = QLabel("Ссылка на свой профиль SoundCloud")
        profile_input = QLineEdit(self.soundcloud_profile_url if self.soundcloud_profile_url != "https://soundcloud.com/you" else "")
        profile_input.setPlaceholderText("https://soundcloud.com/ваш_никнейм")
        root.addWidget(profile_label)
        root.addWidget(profile_input)
        profile_hint = QLabel("Рекомендуется указать профиль даже при выборе браузера, чтобы плеер знал, какие личные разделы загружать.")
        profile_hint.setObjectName("mutedText")
        profile_hint.setWordWrap(True)
        root.addWidget(profile_hint)

        def update_mode_fields():
            is_browser = mode.currentData() == "browser"
            browser_label.setEnabled(is_browser)
            browser_combo.setEnabled(is_browser)
            profile_input.setEnabled(True)
        mode.currentIndexChanged.connect(update_mode_fields)
        update_mode_fields()

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Отмена")
        save = QPushButton("Сохранить и загрузить")
        save.setObjectName("accentButton")
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        root.addLayout(buttons)
        cancel.clicked.connect(dialog.reject)

        def save_connection():
            old_identity = self.soundcloud_cache_identity()
            selected_mode = mode.currentData()
            profile = self.normalize_soundcloud_profile_url(profile_input.text())
            if profile_input.text().strip() and not profile:
                QMessageBox.warning(dialog, "Некорректная ссылка", "Введи ссылку вида https://soundcloud.com/имя_профиля")
                return
            for old_worker in list(self.soundcloud_profile_workers.values()):
                if old_worker.isRunning():
                    old_worker.cancel()
            self.soundcloud_profile_workers.clear()
            self.soundcloud_auth_mode = selected_mode
            self.soundcloud_browser = str(browser_combo.currentData())
            self.soundcloud_profile_url = profile
            self.settings.setValue("soundcloud_auth_mode", self.soundcloud_auth_mode)
            self.settings.setValue("soundcloud_browser", self.soundcloud_browser)
            self.settings.setValue("soundcloud_profile_url", self.soundcloud_profile_url)
            self.settings.sync()
            new_identity = self.soundcloud_cache_identity()
            if old_identity and new_identity and old_identity.casefold() != new_identity.casefold():
                self.soundcloud_liked_tracks = []
                self.soundcloud_account_playlists = []
                self._soundcloud_cached_playlists = []
                self._soundcloud_cache_profile = new_identity
                self._likes_list_signatures.pop("soundcloud", None)
            self._soundcloud_likes_synced_at = 0.0
            self._soundcloud_last_profile_load = 0.0
            dialog.accept()
            self.refresh_likes_list(force_rebuild=True)
            if self.current_source == "soundcloud":
                self.rebuild_start_cards()
                self.update_browse_empty_state()
            QTimer.singleShot(0, lambda: self.load_soundcloud_account_content(force=True))

        save.clicked.connect(save_connection)
        dialog.exec()

    def soundcloud_profile_base(self):
        return self.soundcloud_profile_url or "https://soundcloud.com/you"

    def load_soundcloud_account_content(self, force=False):
        """Использует сохранённые лайки сразу и синхронизирует их не чаще раза в сутки."""
        if not self.soundcloud_is_connected():
            self.soundcloud_account_status.setText("SoundCloud: подключи сессию браузера или публичный профиль.")
            return
        if any(worker.isRunning() for worker in self.soundcloud_profile_workers.values()):
            return
        if not force and self.soundcloud_cache_is_fresh():
            self._soundcloud_last_profile_load = time.monotonic()
            self._soundcloud_likes_loading = False
            stamp = datetime.fromtimestamp(self._soundcloud_likes_synced_at).strftime("%d.%m %H:%M")
            self.soundcloud_account_status.setText(
                f"SoundCloud: кэш загружен · {len(self.soundcloud_liked_tracks)} лайков · обновлено {stamp}. "
                "Для обновления открой Настройки → Сервисы."
            )
            if self.current_source == "soundcloud" and not self.search_input.text().strip():
                self.rebuild_start_cards()
            self.refresh_likes_status_only()
            return
        base = self.soundcloud_profile_base().rstrip("/")
        self._soundcloud_last_profile_load = time.monotonic()
        self._soundcloud_likes_loading = True
        self._soundcloud_likes_sync_started = False
        self._soundcloud_sync_tracks = []
        self._soundcloud_sync_seen = set()
        self.soundcloud_account_status.setText(
            f"SoundCloud: обновляю лайки в фоне · сохранено {len(self.soundcloud_liked_tracks)} треков…"
        )
        auth = self.soundcloud_auth_kwargs()
        for kind, url in (("likes", base + "/likes"),):
            worker = SearchWorker(
                "", "soundcloud", "relevance", 100, self,
                direct_url=url, cache_enabled=False,
                paginate_all=(kind == "likes"), max_total=10000, **auth
            )
            self.soundcloud_profile_workers[kind] = worker
            worker.results_ready.connect(lambda tracks, note, k=kind, w=worker: self.on_soundcloud_account_results(k, w, tracks, note))
            worker.failed.connect(lambda error, k=kind, w=worker: self.on_soundcloud_account_error(k, w, error))
            worker.finished.connect(lambda k=kind, w=worker: self.on_soundcloud_account_finished(k, w))
            worker.finished.connect(worker.deleteLater)
            worker.start()

    def on_soundcloud_account_results(self, kind, worker, tracks, note):
        if self.soundcloud_profile_workers.get(kind) is not worker:
            return
        note = str(note or "")
        if kind == "likes":
            page_marker = note.startswith("__SC_LIKES_PAGE__:")
            done_marker = note.startswith("__SC_LIKES_DONE__:")
            if page_marker:
                if not self._soundcloud_likes_sync_started:
                    self._soundcloud_likes_sync_started = True
                    self._soundcloud_sync_tracks = []
                    self._soundcloud_sync_seen = set()
                cached_by_key = {
                    self.favorite_key(item): item for item in self.soundcloud_liked_tracks
                    if isinstance(item, dict)
                }
                newly_added = []
                for track in tracks:
                    if not isinstance(track, dict) or not track.get("url"):
                        continue
                    item = dict(track, source="soundcloud", soundcloud_like=True)
                    key = self.favorite_key(item)
                    if key not in self._soundcloud_sync_seen:
                        self._soundcloud_sync_seen.add(key)
                        self._soundcloud_sync_tracks.append(item)
                    old_track = cached_by_key.get(key)
                    if old_track is not None:
                        old_track.update({k: v for k, v in item.items() if v not in (None, "")})
                        continue
                    cached_by_key[key] = item
                    self.soundcloud_liked_tracks.append(item)
                    newly_added.append(item)
                # Не сериализуем все 2100 записей на каждом шаге. Сохраним один
                # раз после полного успешного прохода; старый кэш остаётся нетронутым,
                # если приложение закроется или сеть оборвётся посередине.
                if newly_added:
                    self.refresh_likes_list(append_soundcloud_tracks=newly_added)
                    self.append_soundcloud_likes_to_active_queue(newly_added)
                self.soundcloud_account_status.setText(
                    f"SoundCloud: обновляю список · проверено {len(self._soundcloud_sync_tracks)} лайков…"
                )
            elif done_marker:
                self._soundcloud_likes_loading = False
                if getattr(worker, "pagination_done", False) and self._soundcloud_sync_tracks:
                    # Полный синк заменяет кэш актуальным упорядоченным списком.
                    self.soundcloud_liked_tracks = [
                        dict(track, source="soundcloud", soundcloud_like=True)
                        for track in self._soundcloud_sync_tracks
                    ]
                    self._soundcloud_likes_synced_at = time.time()
                    self._soundcloud_cache_profile = self.soundcloud_cache_identity()
                    self.save_soundcloud_likes(immediate=True)
                    self._likes_list_signatures.pop("soundcloud", None)
                    self.refresh_likes_list(force_rebuild=True)
                self.soundcloud_account_status.setText(
                    f"SoundCloud: синхронизировано {len(self.soundcloud_liked_tracks)} лайков."
                )
                self._soundcloud_sync_tracks = []
                self._soundcloud_sync_seen = set()
                if self._soundcloud_queue_waiting:
                    self._soundcloud_queue_waiting = False
                    next_index = self.peek_next_index()
                    if next_index is not None:
                        QTimer.singleShot(0, lambda i=next_index: self.play_queue_index(i))
                    elif self.current_track is not None:
                        QTimer.singleShot(0, self.handle_track_finished)
        elif kind == "playlists":
            entries, seen = [], set()
            for track in tracks:
                if not isinstance(track, dict) or not track.get("url"):
                    continue
                url = str(track.get("url", ""))
                if not url.startswith("https://soundcloud.com/") or url in seen:
                    continue
                seen.add(url)
                entries.append({
                    "title": str(track.get("title") or "Плейлист SoundCloud"),
                    "subtitle": str(track.get("artist") or "Личный плейлист"),
                    "url": url,
                    "source": "soundcloud",
                    "color_a": "#FF5500",
                    "color_b": "#24172E",
                    "symbol": "🎧",
                    "cover_url": normalize_artwork_url(track.get("thumbnail", "")),
                })
            self.soundcloud_account_playlists = entries
            self._soundcloud_cached_playlists = list(entries)
            # Дата синхронизации лайков не меняется до завершения /likes.
            self.save_soundcloud_likes(immediate=True)
            if self.current_source == "soundcloud" and not self.search_input.text().strip():
                self.rebuild_start_cards()
        self.refresh_likes_status_only()

    def refresh_likes_status_only(self):
        """Обновляет подписи источников без перестройки всех списков."""
        if not hasattr(self, "likes_tabs"):
            return
        youtube_count = len(self.youtube_liked_tracks)
        soundcloud_count = len(self.soundcloud_liked_tracks)
        local_count = len(self.favorites)
        combined_count = len(self.get_combined_likes())
        self.likes_tabs.setTabText(0, f"YouTube Music · {youtube_count}")
        self.likes_tabs.setTabText(1, f"SoundCloud · {soundcloud_count}")
        self.likes_tabs.setTabText(2, f"Мои лайки · {local_count}")
        self.likes_title.setText(f"Избранное · всего {combined_count} треков")

    def on_soundcloud_account_error(self, kind, worker, error):
        if self.soundcloud_profile_workers.get(kind) is not worker:
            return
        self._soundcloud_profile_status = str(error or "Не удалось загрузить данные SoundCloud")
        if kind == "likes":
            self._soundcloud_likes_loading = False
        self.soundcloud_account_status.setText(
            "SoundCloud: не удалось загрузить личные данные. Проверь профиль/сессию браузера. "
            + self._soundcloud_profile_status[:220]
        )

    def on_soundcloud_account_finished(self, kind, worker):
        if self.soundcloud_profile_workers.get(kind) is worker:
            self.soundcloud_profile_workers.pop(kind, None)
        if kind == "likes":
            self._soundcloud_likes_loading = False
            total = len(self.soundcloud_liked_tracks)
            done = bool(getattr(worker, "pagination_done", False))
            suffix = "" if done else " · синхронизация остановлена; показаны загруженные треки"
            self.soundcloud_account_status.setText(
                f"SoundCloud: {'синхронизировано' if done else 'доступно'} {total} лайков{suffix}."
            )
            if self._soundcloud_queue_waiting:
                self._soundcloud_queue_waiting = False
                next_index = self.peek_next_index()
                if next_index is not None:
                    QTimer.singleShot(0, lambda i=next_index: self.play_queue_index(i))
                elif self.current_track is not None:
                    QTimer.singleShot(0, self.handle_track_finished)

    def load_custom_playlists(self):
        raw = self.settings.value("custom_playlists_json", "[]")
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(data, list):
                return [item for item in data if isinstance(item, dict) and item.get("url") and item.get("title")]
        except (TypeError, json.JSONDecodeError):
            pass
        return []

    def save_custom_playlists(self):
        self.settings.setValue("custom_playlists_json", json.dumps(self.custom_playlists, ensure_ascii=False))
        self.settings.sync()

    def add_custom_playlist_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Добавить свой плейлист")
        dialog.setMinimumWidth(520)
        style_dialog_for_theme(dialog, "customPlaylistDialog", self.theme)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)
        heading = QLabel("Добавить свой плейлист")
        heading.setObjectName("settingsTitle")
        layout.addWidget(heading)
        name_input = QLineEdit()
        name_input.setPlaceholderText("Название плейлиста")
        url_input = QLineEdit()
        url_input.setPlaceholderText("https://music.youtube.com/playlist?list=… или https://soundcloud.com/…")
        layout.addWidget(QLabel("Название"))
        layout.addWidget(name_input)
        layout.addWidget(QLabel("Ссылка"))
        layout.addWidget(url_input)
        hint = QLabel("Сохраняется только название и ссылка. Личные данные из аккаунтов не экспортируются.")
        hint.setObjectName("mutedText")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Отмена")
        add = QPushButton("Добавить плейлист")
        add.setObjectName("accentButton")
        buttons.addWidget(cancel)
        buttons.addWidget(add)
        layout.addLayout(buttons)
        cancel.clicked.connect(dialog.reject)

        palette = [("#315C91", "#171B32"), ("#6E3C82", "#21162C"),
                   ("#9A5A2C", "#2B1D1B"), ("#246A61", "#142522"),
                   ("#7A334C", "#291923"), ("#6C6330", "#232217")]

        def do_add():
            title = name_input.text().strip()
            url = url_input.text().strip()
            if not title or not url.startswith(("https://", "http://")):
                QMessageBox.warning(dialog, "Заполни поля", "Укажи название и полную ссылку https://…")
                return
            lower = url.lower()
            if "soundcloud.com/" in lower:
                source = "soundcloud"
                if not url.startswith("https://soundcloud.com/"):
                    QMessageBox.warning(dialog, "Ссылка SoundCloud", "Используй ссылку вида https://soundcloud.com/…")
                    return
            elif any(host in lower for host in ("youtube.com/", "music.youtube.com/", "youtu.be/")):
                source = "youtube"
            else:
                QMessageBox.warning(dialog, "Неподдерживаемая ссылка", "Поддерживаются ссылки YouTube Music/YouTube и SoundCloud.")
                return
            color_a, color_b = random.choice(palette)
            self.custom_playlists.append({"title": title, "url": url, "source": source,
                                          "subtitle": "Твоя подборка", "symbol": "♫",
                                          "color_a": color_a, "color_b": color_b})
            self.save_custom_playlists()
            self.rebuild_start_cards()
            self.update_browse_empty_state()
            dialog.accept()

        add.clicked.connect(do_add)
        dialog.exec()

    def open_likes_library(self, source):
        """Открывает все сохранённые лайки сервиса без запуска музыки и поиска."""
        self.likes_search_input.clear()
        self.likes_tabs.setCurrentIndex(1 if source == "soundcloud" else 0)
        self.set_source("likes")

    def _add_likes_start_card(self, source):
        service = "SoundCloud" if source == "soundcloud" else "YouTube Music"
        tracks = self.soundcloud_liked_tracks if source == "soundcloud" else self._youtube_likes_for_display()
        count = len(tracks)
        subtitle = f"Все лайки {service} · треков: {count}" if count else f"Открыть мои лайки {service}"
        accent = "#FF5500" if source == "soundcloud" else "#1DB954"
        card = SpotifyPlaylistCard(
            "Мои лайки", subtitle, "♥", accent, "#181818", self.start_cards_widget,
            action_icon="open", artwork_style="soundcloud-likes" if source == "soundcloud" else "likes"
        )
        card.setFixedHeight(148)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        card.clicked.connect(lambda checked=False, src=source: self.open_likes_library(src))
        self.start_cards.append(card)
        self.start_cards_layout.addWidget(card)

    def rebuild_start_cards(self):
        """Показывает библиотеку сервиса и действия с настоящими лайками пользователя."""
        if not hasattr(self, "start_cards_layout"):
            return
        while self.start_cards_layout.count():
            item = self.start_cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        self.start_cards = []
        source = self.current_source if self.current_source in ("youtube", "soundcloud") else "youtube"
        self._add_likes_start_card(source)

        if source == "youtube":
            supermix = SpotifyPlaylistCard(
                "Супермикс", "Твои любимые треки · немного близкой новой музыки",
                "🪄", "#EC412B", "#F5AF45", self.start_cards_widget, artwork_style="supermix"
            )
            supermix.setFixedHeight(148)
            supermix.clicked.connect(lambda checked=False: self.play_supermix())
            self.start_cards.append(supermix)
            self.start_cards_layout.addWidget(supermix)
            self._set_supermix_busy(self.supermix_worker is not None)
            mix = SpotifyPlaylistCard(
                "Перемешать мои лайки", "До 50 треков из твоих лайков в случайном порядке",
                "🎧", "#315C62", "#171C22", self.start_cards_widget, artwork_style="shuffle"
            )
            mix.setFixedHeight(148)
            mix.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            mix.clicked.connect(lambda checked=False, src=source: self.play_personal_mix(src))
            self.start_cards.append(mix)
            self.start_cards_layout.addWidget(mix)
        self.start_cards_layout.addStretch(1)

    def start_search(self):
        if hasattr(self, "search_debounce_timer"):
            self.search_debounce_timer.stop()
        if self.current_source not in ("youtube", "soundcloud"):
            return
        query = self.search_input.text().strip()
        if not query:
            self.set_status("Открой свои лайки или введи название трека/исполнителя.")
            self.update_browse_empty_state()
            return
        # Новый запрос не должен ждать завершения долгой догрузки предыдущего.
        # Отмену отмечаем флагом; блокирующий запрос yt-dlp завершится по тайм-ауту.
        if self.search_worker is not None and self.search_worker.isRunning():
            self.search_worker.cancel()

        source = self.current_source
        sort = self.sort_mode
        # Быстрый старт не должен урезать весь микс до 12 треков.
        # Обычный поиск использует лимит из настроек. В профиле артиста запрашиваем
        # до 100 записей: строгая фильтрация убирает чужие загрузки, поэтому нужен
        # больший пул кандидатов, чтобы в итоге оставалось достаточно его треков.
        limit = max(self.result_limit, 100) if (self.artist_profile_open and self.search_artist_target) else self.result_limit
        if source == "soundcloud" and not self.artist_profile_open:
            limit = min(self.result_limit, 30)
        self.saved_queries[source] = query
        self.search_submitted_queries[source] = query
        self.back_button.show()
        if not (self.artist_profile_open
                and self.artist_profile_query
                and query.casefold() == self.artist_profile_query.casefold()):
            self.search_artist_target = ""
        else:
            self.search_artist_target = self.artist_profile_query
        self.search_button.setEnabled(False)
        self.browser_search_button.hide()
        self.set_status(f"Ищу до {limit} результатов…", source)
        self.source_list.clear()
        self.source_results[source] = []
        if not self.search_artist_target:
            self.artist_header.hide()
            self.sort_button.hide()
        self.update_browse_empty_state()
        self.search_source = source
        self.search_generation = getattr(self, "search_generation", 0) + 1
        generation = self.search_generation
        if self.auto_play_next_search and self.autoplay_playlists:
            self.auto_play_generation = generation
        else:
            # Сбрасываем старую цель автозапуска, чтобы быстрые клики по карточкам
            # не могли случайно включить трек из предыдущего запроса.
            self.auto_play_generation = -1
        self.auto_play_next_search = False

        direct_url = self._pending_direct_url
        self._pending_direct_url = ""
        auth_kwargs = self.youtube_auth_kwargs() if source == "youtube" else self.soundcloud_auth_kwargs()
        worker = SearchWorker(
            query, source, sort, limit, self, direct_url=direct_url,
            artist_filter=(self.search_artist_target if self.search_artist_target else None),
            artist_catalog=bool(source == "youtube" and self.artist_profile_open and self.search_artist_target),
            **auth_kwargs
        )
        self.search_worker = worker
        worker.results_ready.connect(
            lambda tracks, note, s=source, n=limit, g=generation: self.show_results(s, tracks, note, n, g)
            if g == getattr(self, "search_generation", -1) else None
        )
        worker.failed.connect(
            lambda error, s=source, g=generation: self.on_search_error(s, error)
            if g == getattr(self, "search_generation", -1) else None
        )
        worker.finished.connect(lambda w=worker, g=generation: self.search_finished_for(w, g))
        worker.finished.connect(worker.deleteLater)
        worker.start()
        if source == "soundcloud":
            QTimer.singleShot(
                7000,
                lambda s=source, g=generation: self.set_status(
                    "SoundCloud отвечает долго… Проверьте соединение или откройте поиск на сайте.", s
                ) if (self.search_worker is not None
                      and self.search_source == s
                      and g == getattr(self, "search_generation", -1)) else None
            )

    @staticmethod
    def _track_identity(track):
        return (track.get("url"), track.get("source"), track.get("title"))

    def _source_list_matches(self, tracks):
        """Проверяет, совпадает ли текущий UI-список с выдачей без пересоздания QWidget-строк."""
        if not hasattr(self, "source_list") or self.source_list.count() != len(tracks):
            return False
        for index, track in enumerate(tracks):
            item = self.source_list.item(index)
            existing = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
            if not isinstance(existing, dict) or self._track_identity(existing) != self._track_identity(track):
                return False
        return True

    def show_results(self, source, tracks, note, requested, generation=None):
        # Если кэш показал часть выдачи, а новый запрос уже отдаёт первые элементы,
        # объединяем их до получения полной выдачи — список не прыгает и не уменьшается.
        note_lower = str(note or "").lower()
        if tracks and ("загружаю остальные" in note_lower or "обновляю в фоне" in note_lower):
            merged = []
            seen_urls = set()
            for candidate in list(self.source_results.get(source, [])) + list(tracks):
                url = str(candidate.get("url", ""))
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    merged.append(candidate)
            tracks = merged
        if source in ("youtube", "soundcloud"):
            tracks = [track for track in tracks
                      if isinstance(track, dict) and not self.is_disliked(track)]
        self.source_results[source] = tracks
        query = self.saved_queries.get(source, "").strip()
        requested_artist = (
            self.search_artist_target
            if self.artist_profile_open
            and self.search_artist_target
            and query.casefold() == self.search_artist_target.casefold()
            else ""
        )
        if requested_artist and tracks:
            canonical_artist = next((str(track.get("profile_artist_name") or "").strip()
                                     for track in tracks if track.get("profile_artist_name")), "")
            if canonical_artist:
                requested_artist = canonical_artist
        # Важно: не угадываем профиль по тексту запроса или совпадению автора.
        # Обычный поиск остаётся обычным списком, даже если введено имя артиста.
        self.update_artist_profile(requested_artist, tracks, source)
        message = f"Найдено: {len(tracks)} из запрошенных {requested}"
        if note:
            message += ". " + note
        if not tracks:
            message = ("SoundCloud не вернул треки. Проверь соединение, обнови yt-dlp "
                       "или открой поиск на сайте." if source == "soundcloud"
                       else "По этому запросу ничего не найдено. Попробуй другие слова.")
            if note:
                logging.getLogger("aurora").info("%s", " ".join(map(str, ["[Music Player] Подробности поиска SoundCloud:", note])))
        self.set_status(message, source)
        # Когда уже есть первые результаты, разрешаем новый запрос,
        # не дожидаясь медленной догрузки оставшихся треков.
        if note and ("загружаю остальные" in note.lower() or "обновляю выдачу" in note.lower()):
            self.search_button.setEnabled(True)
        if self.current_source == source:
            self.browser_search_button.setVisible(source == "soundcloud" and not tracks)
            # Кэш может вернуть те же самые треки, что и предыдущий поиск.
            # В таком случае оставляем готовые TrackRow/обложки на месте вместо
            # очистки и повторного создания десятков QWidget.
            if not self._source_list_matches(tracks):
                self.source_list.setUpdatesEnabled(False)
                try:
                    self.source_list.clear()
                    for track in tracks:
                        self.add_result(track)
                finally:
                    self.source_list.setUpdatesEnabled(True)
            self.schedule_visible_artwork(self.source_list)
            self.update_playing_row_highlight()
            self.update_browse_empty_state()
            if (tracks and generation is not None
                    and self.auto_play_generation == generation):
                self.auto_play_generation = -1
                QTimer.singleShot(0, lambda t=dict(tracks[0]): self.add_to_queue(t, True))

    @staticmethod
    def detect_artist_profile(query, tracks):
        """Определяет поиск исполнителя, если запрос совпал с полем автора."""
        query_norm = " ".join(str(query or "").casefold().split())
        if not query_norm or not tracks:
            return ""
        artists = [str(track.get("artist", "")).strip() for track in tracks]
        for artist in artists:
            artist_norm = " ".join(artist.casefold().split())
            if artist_norm and artist_norm != "исполнитель неизвестен" and (
                    artist_norm == query_norm or query_norm in artist_norm):
                return artist
        return ""

    @staticmethod
    def dominant_color(pixmap):
        if pixmap is None or pixmap.isNull():
            return QColor("#1DB954")
        image = pixmap.scaled(16, 16, Qt.AspectRatioMode.IgnoreAspectRatio,
                              Qt.TransformationMode.SmoothTransformation).toImage()
        red = green = blue = count = 0
        for y in range(image.height()):
            for x in range(image.width()):
                pixel = image.pixelColor(x, y)
                if pixel.alpha() > 0:
                    red += pixel.red()
                    green += pixel.green()
                    blue += pixel.blue()
                    count += 1
        return QColor(red // count, green // count, blue // count) if count else QColor("#1DB954")

    def _apply_artist_header_color(self, pixmap):
        if self.theme != "dark":
            self.artist_header.setStyleSheet("")
            return
        color = self.dominant_color(pixmap).lighter(140)
        self.artist_header.setStyleSheet(
            "QFrame#artistHeader { background: qlineargradient("
            "x1:0, y1:0, x2:1, y2:1, "
            f"stop:0 {color.name()}, stop:1 #1E1E1E); "
            "border: 1px solid #2A2A2A; border-radius: 16px; }"
        )

    def update_artist_profile(self, artist, tracks, source):
        artist = str(artist or "").strip()
        if not self.artist_profile_open or not artist:
            self.active_artist_profile = ""
            self.artist_header.hide()
            self.sort_button.hide()
            self.table_header.show()
            return
        self.active_artist_profile = artist
        self.artist_name_label.setText(artist)
        self.artist_name_label.setToolTip(f"Открыть популярные треки: {artist}")
        service = "YouTube Music" if source == "youtube" else "SoundCloud"
        self.artist_source_label.setText(f"Исполнитель · {service}")
        self.artist_popular_label.setText("Треки исполнителя")
        avatar = next((track.get("profile_artist_thumbnail") or track.get("artist_thumbnail") or track.get("thumbnail")
                       for track in tracks if track.get("profile_artist_thumbnail") or track.get("artist_thumbnail") or track.get("thumbnail")), "")
        self.artist_header.setStyleSheet("")
        if self.theme == "dark" and avatar in self.pixmap_cache:
            cached_avatar = self.pixmap_cache[avatar]
            if cached_avatar is not None:
                self._apply_artist_header_color(cached_avatar)
        self.artist_avatar.setProperty("requested_image", "")
        self.set_pixmap_safe(self.artist_avatar, self.fallback_cover)
        if avatar:
            self.request_image(avatar, self.artist_avatar)
        self.artist_header.show()
        self.table_header.show()
        self.sort_button.hide()

    def on_search_error(self, source, error):
        error_text = str(error or "Неизвестная ошибка")
        lower_error = error_text.casefold()
        self.set_status("Не удалось выполнить поиск. Подробности показаны в сообщении.", source)
        self.browser_search_button.setVisible(self.current_source == "soundcloud" and source == "soundcloud")

        # Даём понятную подсказку для частой ошибки cookies и не показываем белое
        # стандартное окно, текст которого плохо читается на тёмной теме.
        if "ytmusicapi" in lower_error:
            readable_error = (
                "Для точной карточки артиста приложение использует каталог YouTube Music.\n\n"
                "Открой CMD в папке проекта и выполни:\n"
                "py -m pip install -U ytmusicapi\n\n"
                "Затем перезапусти player.py. Обычный поиск и воспроизведение работают и без этой библиотеки.\n\n"
                "Подробности: " + error_text[:500]
            )
        elif "failed to load cookies" in lower_error or "cookie database" in lower_error:
            readable_error = (
                "Не удалось прочитать cookies браузера. Для обычного поиска и стартовых "
                "миксов вход в аккаунт не нужен — повтори поиск после обновления player.py.\n\n"
                "Если ты открываешь личные лайки, закрой браузер и попробуй снова либо "
                "подключи свежий cookies.txt.\n\nПодробности: " + error_text[:650]
            )
        else:
            readable_error = error_text[:850] + "\n\nПопробуй обновить yt-dlp командой: py -m pip install -U yt-dlp"

        logging.getLogger("aurora").warning("Ошибка поиска [%s]: %s", source, error_text)
        self.show_toast("Ошибка поиска: " + readable_error[:220], 4500)

    def search_finished_for(self, worker, generation):
        # Старый worker не должен разблокировать кнопку нового поиска.
        if generation != getattr(self, "search_generation", -1):
            return
        if self.search_worker is worker:
            self.search_button.setEnabled(True)
            self.search_worker = None
            self.search_source = None

    def search_finished(self):
        # Совместимость со старыми связями, если они где-то используются.
        self.search_button.setEnabled(True)
        self.search_worker = None
        self.search_source = None

    def add_result(self, track):
        self.add_result_to_list(self.source_list, track, self.source_list.count() + 1)

    def play_youtube_likes_from(self, track):
        """Строит очередь из YouTube Music-лайков начиная с выбранного трека."""
        url = str((track or {}).get("url") or "")
        if not url:
            return
        all_tracks = list(self.youtube_liked_tracks)
        start_index = next((i for i, item in enumerate(all_tracks)
                            if str(item.get("url") or "") == url), -1)
        if start_index < 0:
            # Если строка была создана из старого кэша, всё равно запускаем выбранный трек.
            all_tracks = [dict(track)] + [
                item for item in all_tracks
                if str(item.get("url") or "") != url
            ]
            start_index = 0
        selected_tracks = all_tracks[start_index:]
        # Ручной выбор из лайков должен отменить любой незавершённый автопереход
        # старого трека, иначе устаревший EndOfMedia может выбрать соседний поиск.
        self._finish_transition_pending = False
        self._finish_guard_url = ""
        self.cancel_pending_request()
        self.queue_tracks = []
        self.queue_list.clear()
        self.current_queue_index = -1
        self.shuffle_future = None
        self.radio_mode_active = False
        self.queue_mode = "youtube_likes"
        self._soundcloud_queue_waiting = False
        self._soundcloud_queue_anchor_url = ""
        self._radio_waiting_for_tracks = False
        for item in selected_tracks:
            if not isinstance(item, dict) or not item.get("url"):
                continue
            queued = dict(item)
            queued["source"] = "youtube"
            queued["youtube_music_like"] = True
            queued["queue_id"] = uuid4().hex
            self.queue_tracks.append(queued)
        self.refresh_queue_list()
        self.update_queue_count()
        self.toggle_queue_if_hidden()
        if self.queue_tracks:
            self.set_status(
                f"Воспроизведение лайков YouTube Music · в очереди {len(self.queue_tracks)} треков",
                "youtube"
            )
            self.play_queue_index(0)
        else:
            self.set_status("В лайках YouTube Music нет доступных треков.", "likes")

    def play_soundcloud_likes_from(self, track):
        """Строит очередь из SoundCloud-лайков начиная с выбранного трека."""
        url = str((track or {}).get("url") or "")
        if not url:
            return
        all_tracks = list(self.soundcloud_liked_tracks)
        start_index = next((i for i, item in enumerate(all_tracks)
                            if str(item.get("url") or "") == url), 0)
        selected_tracks = all_tracks[start_index:]
        self.cancel_pending_request()
        self.queue_tracks = []
        self.queue_list.clear()
        self.current_queue_index = -1
        self.shuffle_future = None
        self.radio_mode_active = False
        self.queue_mode = "soundcloud_likes"
        self._soundcloud_queue_waiting = False
        self._soundcloud_queue_anchor_url = url
        for item in selected_tracks:
            queued = dict(item)
            queued["queue_id"] = uuid4().hex
            self.queue_tracks.append(queued)
        self.refresh_queue_list()
        self.update_queue_count()
        if self.queue_tracks:
            self.set_status(
                f"Воспроизведение лайков SoundCloud · в очереди {len(self.queue_tracks)} треков"
                + (" · остальные загружаются в фоне" if self._soundcloud_likes_loading else ""),
                "soundcloud"
            )
            self.play_queue_index(0)
        elif self._soundcloud_likes_loading:
            self._soundcloud_queue_waiting = True
            self.set_status("SoundCloud: жду первую страницу лайков…", "soundcloud")

    def append_soundcloud_likes_to_active_queue(self, tracks):
        if self.queue_mode != "soundcloud_likes" or not tracks:
            return
        known = {str(item.get("url") or "") for item in self.queue_tracks}
        # Если пользователь начал слушать кэш с середины списка до окончания
        # синхронизации, не дописываем в конец треки, стоящие ДО выбранного.
        last_queued_url = str(self.queue_tracks[-1].get("url") or "") if self.queue_tracks else ""
        last_loaded_index = next((i for i, item in enumerate(self.soundcloud_liked_tracks)
                                  if str(item.get("url") or "") == last_queued_url), -1)
        anchor_index = next((i for i, item in enumerate(self.soundcloud_liked_tracks)
                             if str(item.get("url") or "") == self._soundcloud_queue_anchor_url), -1)
        added = []
        for track in tracks:
            url = str(track.get("url") or "")
            if not url or url in known:
                continue
            track_index = next((i for i, item in enumerate(self.soundcloud_liked_tracks)
                                if str(item.get("url") or "") == url), -1)
            if anchor_index >= 0 and track_index >= 0 and track_index < anchor_index:
                continue
            if last_loaded_index >= 0 and track_index >= 0 and track_index <= last_loaded_index:
                continue
            known.add(url)
            queued = dict(track)
            queued["queue_id"] = uuid4().hex
            self.queue_tracks.append(queued)
            added.append(queued)
        if added:
            old_count = self.queue_list.count()
            for offset, queued in enumerate(added):
                self.append_queue_item(queued, old_count + offset)
            self.update_queue_count()
            self.schedule_visible_artwork(self.queue_list)
        if self._soundcloud_queue_waiting and self.requested_track is None and self.pending_slot is None:
            next_index = self.peek_next_index()
            if next_index is not None:
                self._soundcloud_queue_waiting = False
                QTimer.singleShot(0, lambda i=next_index: self.play_queue_index(i))

    def add_result_to_list(self, list_widget, track, index_number):
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, dict(track))
        item.setSizeHint(QSize(200, 72))
        list_widget.addItem(item)
        # TrackRow отображает artist_display (кредиты каталога), но сигнал клика
        # передаёт исходный track, где artist остаётся канонической целью профиля.
        youtube_rating_row = (
            str(track.get("source") or "") == "youtube"
            and list_widget is not self.likes_list
        )
        row = TrackRow(
            track,
            is_favorite=(self.is_youtube_music_liked(track) if youtube_rating_row else self.is_favorite(track)),
            index=index_number,
            show_source=not (
                list_widget is self.youtube_likes_list
                or list_widget is self.soundcloud_likes_list
                or list_widget is self.likes_list
            ),
        )
        list_widget.setItemWidget(item, row)
        if list_widget is getattr(self, "soundcloud_likes_list", None):
            row.play_button.clicked.connect(lambda checked=False, t=dict(track): self.play_soundcloud_likes_from(t))
            row.play_requested.connect(lambda t: self.play_soundcloud_likes_from(t))
        elif (list_widget is getattr(self, "youtube_likes_list", None)
              or bool(track.get("youtube_music_like"))):
            # Лайкнутые треки должны запускать очередь лайков даже если строка
            # была создана из сохранённого кэша/другого представления списка.
            row.play_button.clicked.connect(
                lambda checked=False, t=dict(track): self.play_youtube_likes_from(t)
            )
            row.play_requested.connect(lambda t: self.play_youtube_likes_from(t))
        else:
            row.play_button.clicked.connect(lambda checked=False, t=dict(track): self.add_to_queue(t, True))
            row.play_requested.connect(lambda t: self.add_to_queue(t, True))
        row.artist_requested.connect(lambda artist_data, src=track.get("source"): self.search_artist_name(artist_data, src))
        if youtube_rating_row:
            row.favorite_button.clicked.connect(
                lambda checked=False, t=dict(track), b=row.favorite_button:
                    self.set_youtube_music_like(t, bool(checked), b)
            )
            row.favorite_button.setToolTip(
                "Снять лайк в YouTube Music" if self.is_youtube_music_liked(track)
                else "Поставить настоящий лайк в аккаунте YouTube Music"
            )
            if self.youtube_video_id(track) in self._youtube_rating_pending:
                row.favorite_button.setEnabled(False)
                row.favorite_button.setToolTip("Отправляю изменение в YouTube Music…")
        else:
            row.favorite_button.clicked.connect(
                lambda checked=False, t=dict(track), b=row.favorite_button: self.toggle_favorite(t, b)
            )
            row.favorite_button.setToolTip("Локальное избранное — не меняет лайки в аккаунтах")
        self.set_pixmap_safe(row.thumbnail_label, self.fallback_cover)

    def update_playing_row_highlight(self):
        """Подсветка сверяется по URL+источнику; на паузе строка остаётся зелёной."""
        current = self.current_track
        current_url = str((current or {}).get("url", ""))
        current_source = str((current or {}).get("source", ""))
        is_actually_playing = bool(
            current and self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        )
        for list_widget in (getattr(self, "source_list", None), getattr(self, "youtube_likes_list", None),
                             getattr(self, "soundcloud_likes_list", None), getattr(self, "likes_list", None)):
            if list_widget is None:
                continue
            for index in range(list_widget.count()):
                item = list_widget.item(index)
                track = item.data(Qt.ItemDataRole.UserRole)
                row = list_widget.itemWidget(item)
                if not isinstance(row, TrackRow) or not isinstance(track, dict):
                    continue
                matches = bool(
                    current_url and current_source
                    and str(track.get("url", "")) == current_url
                    and str(track.get("source", "")) == current_source
                )
                row.set_playing(matches, animate=(matches and is_actually_playing))

    def on_result_activated(self, item):
        # Один клик по строке запускает трек; кнопки в строке также работают отдельно.
        track = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(track, dict):
            self.add_to_queue(track, True)

    def load_youtube_likes(self):
        """Загружает последний успешный импорт лайков, чтобы он был виден офлайн."""
        try:
            if self.youtube_likes_file.exists():
                raw = json.loads(self.youtube_likes_file.read_text(encoding="utf-8"))
                if isinstance(raw, list):
                    return [dict(track, source="youtube", youtube_music_like=True)
                            for track in raw if isinstance(track, dict) and track.get("url")]
        except (OSError, json.JSONDecodeError) as error:
            logging.getLogger("aurora").info(f"[Music Player] Не удалось прочитать кэш лайков YouTube: {error}")
        return []

    def save_youtube_likes(self):
        try:
            temp = self.youtube_likes_file.with_suffix(".tmp")
            temp.write_text(json.dumps(self.youtube_liked_tracks, ensure_ascii=False, indent=2), encoding="utf-8")
            temp.replace(self.youtube_likes_file)
        except OSError as error:
            logging.getLogger("aurora").info(f"[Music Player] Не удалось сохранить кэш лайков YouTube: {error}")

    def _youtube_likes_for_display(self):
        """Показывает ожидающие лайки сразу, сохраняя подтверждённый кэш отдельно."""
        pending = [track for video_id, track in reversed(self._youtube_rating_tracks.items())
                   if self._youtube_rating_targets.get(video_id)]
        tracks, seen = [], set()
        for track in (*pending, *self.youtube_liked_tracks):
            if not isinstance(track, dict) or not track.get("url"):
                continue
            video_id = self.youtube_video_id(track)
            if self._youtube_rating_targets.get(video_id) is False:
                continue
            key = video_id or self.favorite_key(track)
            if key not in seen:
                tracks.append(track)
                seen.add(key)
        return tracks

    def get_combined_likes(self):
        combined = []
        seen = set()
        for track in self._youtube_likes_for_display() + list(self.soundcloud_liked_tracks) + list(self.favorites.values()):
            if not isinstance(track, dict) or not track.get("url"):
                continue
            key = self.favorite_key(track)
            if key in seen:
                continue
            seen.add(key)
            combined.append(dict(track))
        return combined

    def _likes_kind_for_widget(self, list_widget):
        if list_widget is self.youtube_likes_list:
            return "youtube"
        if list_widget is self.soundcloud_likes_list:
            return "soundcloud"
        if list_widget is self.likes_list:
            return "local"
        return ""

    def _likes_tracks_for_kind(self, kind):
        if kind == "youtube":
            tracks = self._youtube_likes_for_display()
        elif kind == "soundcloud":
            tracks = self.soundcloud_liked_tracks
        elif kind == "local":
            tracks = list(self.favorites.values())
        else:
            tracks = []

        tracks = [
            track for track in tracks
            if isinstance(track, dict) and track.get("url")
        ]
        query = str(getattr(self, "_likes_search_query", "") or "").strip().casefold()
        if not query:
            return tracks
        return [
            track for track in tracks
            if query in str(track.get("title") or "").casefold()
            or query in str(track.get("artist") or "").casefold()
        ]

    def on_likes_search_changed(self, text):
        self._likes_search_query = str(text or "").strip().casefold()
        self.refresh_likes_list(force_rebuild=True)

    @staticmethod
    def human_relative_time(timestamp):
        try:
            timestamp = float(timestamp or 0)
            if timestamp <= 0:
                return "никогда"
            diff = max(0.0, time.time() - timestamp)
            if diff < 60:
                return "только что"
            if diff < 3600:
                return f"{int(diff // 60)} мин назад"
            if diff < 86400:
                return f"{int(diff // 3600)} ч назад"
            if diff < 86400 * 7:
                return f"{int(diff // 86400)} дн назад"
            return datetime.fromtimestamp(timestamp).strftime("%d.%m.%Y")
        except (ValueError, TypeError, OSError, OverflowError):
            return "никогда"

    @staticmethod
    def _likes_signature(tracks):
        if not tracks:
            return (0, "", "")
        return (len(tracks), str(tracks[0].get("url") or ""), str(tracks[-1].get("url") or ""))

    @staticmethod
    def _likes_widget_matches_prefix(list_widget, tracks):
        """Новые страницы дописываются, а вставки и замены обновляют готовые строки."""
        count = list_widget.count()
        return count <= len(tracks) and all(
            list_widget.item(index).data(Qt.ItemDataRole.UserRole) == tracks[index]
            for index in range(count)
        )

    def _rebuild_likes_widget(self, list_widget, tracks, kind):
        self._likes_loading_more.add(kind)
        list_widget.setUpdatesEnabled(False)
        list_widget.clear()
        end = min(len(tracks), self._likes_render_batch)
        for index in range(end):
            self.add_result_to_list(list_widget, tracks[index], index + 1)
        self._likes_rendered_counts[kind] = end
        self._likes_list_signatures[kind] = self._likes_signature(tracks)
        list_widget.setUpdatesEnabled(True)
        self._likes_loading_more.discard(kind)
        if end:
            self.schedule_visible_artwork(list_widget)

    def _append_likes_rows(self, list_widget):
        kind = self._likes_kind_for_widget(list_widget)
        if not kind or kind in self._likes_loading_more:
            return
        tracks = self._likes_tracks_for_kind(kind)
        start = self._likes_rendered_counts.get(kind, 0)
        if start >= len(tracks):
            return
        end = min(len(tracks), start + self._likes_render_batch)
        self._likes_loading_more.add(kind)
        list_widget.setUpdatesEnabled(False)
        for index in range(start, end):
            self.add_result_to_list(list_widget, tracks[index], index + 1)
        list_widget.setUpdatesEnabled(True)
        self._likes_rendered_counts[kind] = end
        self._likes_list_signatures[kind] = self._likes_signature(tracks)
        self._likes_loading_more.discard(kind)
        self.schedule_visible_artwork(list_widget)

    def maybe_load_more_likes(self, list_widget):
        kind = self._likes_kind_for_widget(list_widget)
        if not kind or kind in self._likes_loading_more:
            return
        tracks = self._likes_tracks_for_kind(kind)
        if self._likes_rendered_counts.get(kind, 0) >= len(tracks):
            return
        # Пустой виджет сразу получает первую порцию: скролл для этого не нужен.
        if list_widget.count() == 0:
            self._append_likes_rows(list_widget)
            return
        if not list_widget.isVisible():
            return
        scrollbar = list_widget.verticalScrollBar()
        maximum = scrollbar.maximum()
        value = scrollbar.value()
        threshold = max(120, list_widget.viewport().height())
        near_bottom = maximum - value <= threshold
        passed_halfway = list_widget.isVisible() and maximum > 0 and value >= maximum * 0.35
        if near_bottom or passed_halfway:
            self._append_likes_rows(list_widget)

    def on_list_scroll(self, list_widget, value):
        self.schedule_visible_artwork(list_widget)
        if list_widget in (self.youtube_likes_list, self.soundcloud_likes_list, self.likes_list):
            self.maybe_load_more_likes(list_widget)

    def refresh_likes_list(self, append_soundcloud_tracks=None, force_rebuild=False):
        """Обновляет счётчики и создаёт строки лайков порциями по 150 штук."""
        if not hasattr(self, "likes_list"):
            return
        youtube_tracks = self._youtube_likes_for_display()
        soundcloud_tracks = [track for track in self.soundcloud_liked_tracks if isinstance(track, dict) and track.get("url")]
        local_tracks = [track for track in self.favorites.values() if isinstance(track, dict) and track.get("url")]
        # Порции SoundCloud обновляют объединение инкрементально, без повторного
        # обхода всех лайков YouTube и локального избранного.
        if (append_soundcloud_tracks is not None and not force_rebuild
                and hasattr(self, "_combined_likes_keys")):
            combined = self.source_results.get("likes", [])
            seen = self._combined_likes_keys
            for track in append_soundcloud_tracks:
                if not isinstance(track, dict) or not track.get("url"):
                    continue
                key = self.favorite_key(track)
                if key not in seen:
                    seen.add(key)
                    combined.append(dict(track))
        else:
            combined = []
            seen = set()
            for track in (*youtube_tracks, *soundcloud_tracks, *local_tracks):
                key = self.favorite_key(track)
                if key not in seen:
                    seen.add(key)
                    combined.append(dict(track))
            self._combined_likes_keys = seen
        self.source_results["likes"] = combined
        display_tracks = {
            "youtube": self._likes_tracks_for_kind("youtube"),
            "soundcloud": self._likes_tracks_for_kind("soundcloud"),
            "local": self._likes_tracks_for_kind("local"),
        }

        if append_soundcloud_tracks is None:
            for list_widget, tracks, kind in (
                (self.youtube_likes_list, display_tracks["youtube"], "youtube"),
                (self.soundcloud_likes_list, display_tracks["soundcloud"], "soundcloud"),
                (self.likes_list, display_tracks["local"], "local"),
            ):
                signature = self._likes_signature(tracks)
                previous_signature = self._likes_list_signatures.get(kind)
                previous_length = (previous_signature[0]
                                   if isinstance(previous_signature, tuple) and previous_signature
                                   else 0)
                if force_rebuild:
                    self._rebuild_likes_widget(list_widget, tracks, kind)
                elif list_widget.count() == 0:
                    self._rebuild_likes_widget(list_widget, tracks, kind)
                elif len(tracks) < previous_length:
                    # Если источник стал короче, убираем устаревшие строки.
                    self._rebuild_likes_widget(list_widget, tracks, kind)
                elif not self._likes_widget_matches_prefix(list_widget, tracks):
                    self._rebuild_likes_widget(list_widget, tracks, kind)
                elif len(tracks) > self._likes_rendered_counts.get(kind, 0):
                    # Новые страницы пока остаются в модели данных. Виджеты создаём
                    # только когда пользователь прокрутил список ближе к середине/концу.
                    scrollbar = list_widget.verticalScrollBar()
                    maximum = scrollbar.maximum()
                    value = scrollbar.value()
                    threshold = max(120, list_widget.viewport().height())
                    should_append = (
                        list_widget.count() == 0
                        or maximum <= threshold
                        or maximum - value <= threshold
                        or (maximum > 0 and value >= maximum * 0.35)
                    )
                    if should_append and list_widget.isVisible():
                        self._append_likes_rows(list_widget)
                    else:
                        self._likes_list_signatures[kind] = signature
                else:
                    self._likes_list_signatures[kind] = signature
        else:
            # При пагинации SoundCloud дописываем только новые строки; принудительное
            # обновление и уменьшение источника по-прежнему полностью перестраивают список.
            soundcloud_display_tracks = display_tracks["soundcloud"]
            signature = self._likes_signature(soundcloud_display_tracks)
            previous_signature = self._likes_list_signatures.get("soundcloud")
            previous_length = (previous_signature[0]
                               if isinstance(previous_signature, tuple) and previous_signature
                               else 0)
            if force_rebuild:
                for list_widget, tracks, kind in (
                    (self.youtube_likes_list, display_tracks["youtube"], "youtube"),
                    (self.soundcloud_likes_list, display_tracks["soundcloud"], "soundcloud"),
                    (self.likes_list, display_tracks["local"], "local"),
                ):
                    self._rebuild_likes_widget(list_widget, tracks, kind)
            elif self.soundcloud_likes_list.count() == 0:
                self._rebuild_likes_widget(
                    self.soundcloud_likes_list, soundcloud_display_tracks, "soundcloud")
            elif len(soundcloud_display_tracks) < previous_length:
                self._rebuild_likes_widget(
                    self.soundcloud_likes_list, soundcloud_display_tracks, "soundcloud")
            elif not self._likes_widget_matches_prefix(self.soundcloud_likes_list, soundcloud_display_tracks):
                self._rebuild_likes_widget(
                    self.soundcloud_likes_list, soundcloud_display_tracks, "soundcloud")
            elif len(soundcloud_display_tracks) > self._likes_rendered_counts.get("soundcloud", 0):
                self._append_likes_rows(self.soundcloud_likes_list)
            else:
                self._likes_list_signatures["soundcloud"] = signature
                self.schedule_visible_artwork(self.soundcloud_likes_list)

        self.likes_tabs.setTabText(0, f"YouTube Music · {len(youtube_tracks)}")
        self.likes_tabs.setTabText(1, f"SoundCloud · {len(soundcloud_tracks)}")
        self.likes_tabs.setTabText(2, f"Мои лайки · {len(local_tracks)}")
        self.likes_title.setText(f"Избранное · всего {len(combined)} треков")

        if self.youtube_auth_mode == "browser" and self.youtube_auth_browser:
            profile_suffix = f" · профиль {self.youtube_auth_profile}" if self.youtube_auth_profile else ""
            auth_label = f"Браузер: {self.youtube_auth_browser}{profile_suffix}"
        elif self.youtube_cookie_file:
            auth_label = f"Файл сессии: {Path(self.youtube_cookie_file).name}"
        else:
            auth_label = "Аккаунт не подключён"
        has_auth = bool(self.youtube_auth_kwargs())
        sync_running = bool(self.youtube_sync_worker is not None and self.youtube_sync_worker.isRunning())
        self.connect_account_button.setText("Настроить подключение" if has_auth else "Подключить аккаунт YouTube Music")
        if self._youtube_rating_pending:
            self.likes_account_title.setText("YouTube Music")
            self.likes_account_status.setText("Сохраняю изменения лайков в YouTube Music…")
        elif self.youtube_liked_tracks and has_auth:
            self.likes_account_title.setText("YouTube Music · аккаунт подключён")
            self.likes_account_status.setText(
                f"Синхронизировано с YouTube Music: {len(youtube_tracks)} треков · "
                f"обновлено {self.human_relative_time(self._youtube_last_sync_at)} · {auth_label}"
            )
        elif self.youtube_liked_tracks:
            self.likes_account_title.setText("YouTube Music · сохранённый импорт")
            self.likes_account_status.setText(
                f"На компьютере сохранено {len(youtube_tracks)} ранее импортированных треков. "
                "Аккаунт сейчас не подключён; подключи его, чтобы обновить список."
            )
        else:
            self.likes_account_title.setText("YouTube Music")
            self.likes_account_status.setText(
                f"{auth_label}. Подключи сессию и нажми «Синхронизировать», чтобы импортировать реальные лайки."
            )
        self.sync_account_button.setEnabled(has_auth and not sync_running)
        self.disconnect_account_button.setEnabled(has_auth)

        sc_connected = self.soundcloud_is_connected()
        if self.soundcloud_auth_mode == "browser":
            sc_label = f"сессия браузера: {self.soundcloud_browser}"
            sc_kind = "сессия подключена" if sc_connected else "не подключён"
        elif self.soundcloud_profile_url:
            sc_label = self.soundcloud_profile_url
            sc_kind = "публичный профиль добавлен"
        else:
            sc_label = "Не подключён"
            sc_kind = "аккаунт не подключён"
        self.connect_soundcloud_button.setText("Настроить SoundCloud" if sc_connected else "Подключить аккаунт SoundCloud")
        if self._soundcloud_likes_loading:
            self.soundcloud_account_status.setText(
                f"SoundCloud: обновляю в фоне · показано {len(soundcloud_tracks)} сохранённых лайков…"
            )
        elif self.soundcloud_cache_is_fresh():
            stamp = self.human_relative_time(self._soundcloud_likes_synced_at)
            self.soundcloud_account_status.setText(
                f"SoundCloud: кэш актуален · {len(soundcloud_tracks)} лайков · обновлено {stamp} · {sc_label}"
            )
        else:
            self.soundcloud_account_status.setText(
                f"SoundCloud: {sc_kind} · {len(soundcloud_tracks)} сохранённых лайков · {sc_label}"
            )
        self.update_playing_row_highlight()

    def connect_youtube_account(self):
        """Подключение YouTube Music через браузерную сессию или запасной cookies.txt."""
        dialog = QDialog(self)
        dialog.setObjectName("youtubeAuthDialog")
        dialog.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        dialog.setAutoFillBackground(True)
        dialog.setWindowTitle("Подключить YouTube Music")
        dialog.setMinimumWidth(600)
        auth_palette = dialog.palette()
        if self.theme == "light":
            auth_palette.setColor(QPalette.ColorRole.Window, QColor("#F5F5F7"))
            auth_palette.setColor(QPalette.ColorRole.WindowText, QColor("#222222"))
            auth_palette.setColor(QPalette.ColorRole.Base, QColor("#FFFFFF"))
            auth_palette.setColor(QPalette.ColorRole.Text, QColor("#222222"))
            auth_palette.setColor(QPalette.ColorRole.Button, QColor("#EEEEF2"))
            auth_palette.setColor(QPalette.ColorRole.ButtonText, QColor("#222222"))
        else:
            auth_palette.setColor(QPalette.ColorRole.Window, QColor("#181818"))
            auth_palette.setColor(QPalette.ColorRole.WindowText, QColor("#F5F5F5"))
            auth_palette.setColor(QPalette.ColorRole.Base, QColor("#242424"))
            auth_palette.setColor(QPalette.ColorRole.Text, QColor("#F5F5F5"))
            auth_palette.setColor(QPalette.ColorRole.Button, QColor("#282828"))
            auth_palette.setColor(QPalette.ColorRole.ButtonText, QColor("#FFFFFF"))
        dialog.setPalette(auth_palette)

        root = QVBoxLayout(dialog)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(12)
        title = QLabel("Подключение YouTube Music")
        title.setObjectName("settingsTitle")
        root.addWidget(title)

        hint = QLabel(
            "Рекомендуемый способ — браузерная сессия. Открой YouTube Music, войди в Google "
            "в выбранном браузере, затем закрой его окна и нажми «Сохранить и синхронизировать». "
            "Плеер не запрашивает и не сохраняет пароль: yt-dlp читает cookies локально на компьютере.\n\n"
            "Если браузер не позволяет прочитать профиль, можно выбрать запасной вариант — свежий cookies.txt. "
            "Файл oauth.json для этого способа не подходит."
        )
        hint.setObjectName("settingsHint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        mode = QComboBox()
        mode.addItem("Войти через браузер (рекомендуется)", "browser")
        mode.addItem("Использовать файл cookies.txt", "file")
        mode.setCurrentIndex(0 if self.youtube_auth_mode == "browser" or not self.youtube_cookie_file else 1)
        root.addWidget(mode)

        browser_group = QWidget(dialog)
        browser_layout = QVBoxLayout(browser_group)
        browser_layout.setContentsMargins(0, 0, 0, 0)
        browser_layout.setSpacing(8)

        browser_row = QHBoxLayout()
        browser_label = QLabel("Браузер")
        browser_combo = QComboBox()
        for label, value in (("Google Chrome", "chrome"), ("Microsoft Edge", "edge"),
                             ("Firefox", "firefox"), ("Waterfox", "waterfox"),
                             ("Brave", "brave"), ("Opera", "opera")):
            browser_combo.addItem(label, value)
        browser_index = browser_combo.findData(self.youtube_auth_browser)
        if browser_index >= 0:
            browser_combo.setCurrentIndex(browser_index)
        browser_row.addWidget(browser_label)
        browser_row.addWidget(browser_combo, 1)
        browser_layout.addLayout(browser_row)

        profile_row = QHBoxLayout()
        profile_label = QLabel("Профиль")
        profile_input = QLineEdit(self.youtube_auth_profile)
        profile_input.setPlaceholderText("Waterfox: можно оставить пустым или указать путь профиля")
        profile_row.addWidget(profile_label)
        profile_row.addWidget(profile_input, 1)
        browser_layout.addLayout(profile_row)
        profile_hint = QLabel(
            "Chrome/Edge/Firefox: можно указать имя профиля. Waterfox: оставь поле пустым для автоопределения "
            "профиля или вставь полный путь из about:profiles → Root Directory. Если профилей несколько, "
            "выбери тот, в котором выполнен вход в Google."
        )
        profile_hint.setObjectName("settingsHint")
        profile_hint.setWordWrap(True)
        browser_layout.addWidget(profile_hint)

        browser_actions = QHBoxLayout()
        open_browser_button = QPushButton("Открыть YouTube Music для входа")
        open_browser_button.setObjectName("filterButton")
        browser_actions.addWidget(open_browser_button)
        browser_actions.addStretch(1)
        browser_layout.addLayout(browser_actions)
        root.addWidget(browser_group)

        file_group = QWidget(dialog)
        file_layout = QHBoxLayout(file_group)
        file_layout.setContentsMargins(0, 0, 0, 0)
        file_path = QLineEdit(self.youtube_cookie_file)
        file_path.setPlaceholderText("Путь к cookies.txt")
        browse = QPushButton("Выбрать…")
        browse.setObjectName("filterButton")
        file_layout.addWidget(file_path, 1)
        file_layout.addWidget(browse)
        root.addWidget(file_group)

        def update_auth_fields():
            browser_mode = mode.currentData() == "browser"
            browser_group.setVisible(browser_mode)
            file_group.setVisible(not browser_mode)

        mode.currentIndexChanged.connect(update_auth_fields)
        update_auth_fields()

        def choose_file():
            selected, _ = QFileDialog.getOpenFileName(
                dialog, "Выбрать cookies.txt", str(Path.home()), "Cookie files (*.txt);;Все файлы (*)"
            )
            if selected:
                file_path.setText(selected)
        browse.clicked.connect(choose_file)

        def open_selected_browser():
            browser = str(browser_combo.currentData() or "chrome")
            url = "https://music.youtube.com/"
            env = os.environ
            local = env.get("LOCALAPPDATA", "")
            program_files = env.get("PROGRAMFILES", "")
            program_files_x86 = env.get("PROGRAMFILES(X86)", "")
            candidates = {
                "chrome": [
                    str(Path(local) / "Google/Chrome/Application/chrome.exe") if local else "",
                    str(Path(program_files) / "Google/Chrome/Application/chrome.exe") if program_files else "",
                    str(Path(program_files_x86) / "Google/Chrome/Application/chrome.exe") if program_files_x86 else "",
                ],
                "edge": [
                    str(Path(program_files_x86) / "Microsoft/Edge/Application/msedge.exe") if program_files_x86 else "",
                    str(Path(program_files) / "Microsoft/Edge/Application/msedge.exe") if program_files else "",
                    str(Path(local) / "Microsoft/Edge/Application/msedge.exe") if local else "",
                ],
                "firefox": [
                    str(Path(program_files) / "Mozilla Firefox/firefox.exe") if program_files else "",
                    str(Path(program_files_x86) / "Mozilla Firefox/firefox.exe") if program_files_x86 else "",
                    str(Path(local) / "Mozilla Firefox/firefox.exe") if local else "",
                ],
                "waterfox": [
                    str(Path(program_files) / "Waterfox/waterfox.exe") if program_files else "",
                    str(Path(program_files_x86) / "Waterfox/waterfox.exe") if program_files_x86 else "",
                    str(Path(local) / "Programs/Waterfox/waterfox.exe") if local else "",
                    str(Path(local) / "Waterfox/waterfox.exe") if local else "",
                ],
                "brave": [
                    str(Path(local) / "BraveSoftware/Brave-Browser/Application/brave.exe") if local else "",
                    str(Path(program_files) / "BraveSoftware/Brave-Browser/Application/brave.exe") if program_files else "",
                    str(Path(program_files_x86) / "BraveSoftware/Brave-Browser/Application/brave.exe") if program_files_x86 else "",
                ],
                "opera": [
                    str(Path(local) / "Programs/Opera/launcher.exe") if local else "",
                    str(Path(program_files) / "Opera/launcher.exe") if program_files else "",
                    str(Path(program_files_x86) / "Opera/launcher.exe") if program_files_x86 else "",
                ],
            }
            commands = {
                "chrome": ("chrome.exe", "chrome", "google-chrome", "google-chrome-stable"),
                "edge": ("msedge.exe", "msedge", "microsoft-edge"),
                "firefox": ("firefox.exe", "firefox"),
                "waterfox": ("waterfox.exe", "waterfox"),
                "brave": ("brave.exe", "brave", "brave-browser"),
                "opera": ("opera.exe", "opera"),
            }
            executable = next((path for path in candidates.get(browser, []) if path and Path(path).is_file()), "")
            if not executable:
                for command in commands.get(browser, ()):
                    executable = shutil.which(command) or ""
                    if executable:
                        break
            try:
                if executable:
                    subprocess.Popen(
                        [executable, url], stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        close_fds=True,
                    )
                else:
                    opened = QDesktopServices.openUrl(QUrl(url))
                    if not opened:
                        raise RuntimeError("Не удалось открыть браузер по умолчанию.")
                    QMessageBox.information(
                        dialog, "Браузер открыт",
                        "Открылся браузер по умолчанию. Выбери в настройке выше именно тот браузер, "
                        "в котором вошёл в Google, иначе yt-dlp не найдёт его cookies."
                    )
            except Exception as error:
                QMessageBox.warning(dialog, "Не удалось открыть браузер", str(error))
                return
            self.set_status("Войди в Google в открывшемся браузере, затем закрой его и вернись в плеер.", "likes")

        open_browser_button.clicked.connect(open_selected_browser)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Отмена")
        save = QPushButton("Сохранить и синхронизировать")
        save.setObjectName("accentButton")
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        root.addLayout(buttons)
        cancel.clicked.connect(dialog.reject)

        def save_auth():
            selected_mode = mode.currentData()
            if selected_mode == "file":
                path_text = file_path.text().strip().strip('"')
                cookie_path = Path(path_text).expanduser() if path_text else None
                if not cookie_path or not cookie_path.is_file():
                    QMessageBox.warning(dialog, "Файл не найден", "Выбери существующий файл cookies.txt.")
                    return
                if cookie_path.suffix.lower() == ".json":
                    QMessageBox.warning(
                        dialog, "Неподходящий файл",
                        "oauth.json не подходит как cookie-файл yt-dlp. Выбери cookies.txt или профиль браузера."
                    )
                    return
                try:
                    content_head = cookie_path.read_text(encoding="utf-8", errors="ignore")[:250000]
                except OSError as error:
                    QMessageBox.warning(dialog, "Не удалось прочитать файл", str(error))
                    return
                if "youtube.com" not in content_head and "google.com" not in content_head:
                    QMessageBox.warning(
                        dialog, "Похоже, это не cookies YouTube",
                        "В файле не найдено доменов youtube.com/google.com. Экспортируй свежий cookies.txt из сессии, где открыт YouTube Music."
                    )
                    return
                self.youtube_auth_mode = "file"
                self.youtube_cookie_file = str(cookie_path.resolve())
                self.youtube_auth_profile = ""
                self.settings.setValue("youtube_cookie_file", self.youtube_cookie_file)
                self.settings.setValue("youtube_auth_mode", "file")
                self.settings.setValue("youtube_auth_browser", browser_combo.currentData())
                self.settings.setValue("youtube_auth_profile", "")
            else:
                self.youtube_auth_mode = "browser"
                self.youtube_auth_browser = str(browser_combo.currentData() or "chrome")
                self.youtube_auth_profile = profile_input.text().strip()
                self.youtube_cookie_file = ""
                self.settings.setValue("youtube_cookie_file", "")
                self.settings.setValue("youtube_auth_mode", "browser")
                self.settings.setValue("youtube_auth_browser", self.youtube_auth_browser)
                self.settings.setValue("youtube_auth_profile", self.youtube_auth_profile)
            self.settings.sync()
            dialog.accept()
            self.refresh_likes_list()
            QTimer.singleShot(0, self.sync_youtube_likes)

        save.clicked.connect(save_auth)

        # QDialog является отдельным верхнеуровневым окном: не полагаемся на
        # палитру главного окна, а явно задаём фон и контраст всем его контролам.
        if self.theme == "light":
            dialog.setStyleSheet("""
                QDialog#youtubeAuthDialog { background-color: #F5F5F7; color: #222222; }
                QDialog#youtubeAuthDialog QWidget { color: #222222; }
                QDialog#youtubeAuthDialog QLabel { color: #222222; background: transparent; }
                QDialog#youtubeAuthDialog QLabel#settingsTitle { color: #202027; font-size: 22pt; font-weight: 800; }
                QDialog#youtubeAuthDialog QLabel#settingsHint { color: #626270; }
                QDialog#youtubeAuthDialog QLineEdit, QDialog#youtubeAuthDialog QComboBox {
                    background: #FFFFFF; color: #222222; border: 1px solid #D2D2DA;
                    border-radius: 9px; padding: 8px 10px; min-height: 20px;
                    selection-background-color: #1DB954; selection-color: #101010;
                }
                QDialog#youtubeAuthDialog QComboBox QAbstractItemView {
                    background: #FFFFFF; color: #222222; selection-background-color: #E1F4E7;
                    selection-color: #16883D; border: 1px solid #D2D2DA;
                }
                QDialog#youtubeAuthDialog QPushButton {
                    background: #E8E8EE; color: #24242B; border: 1px solid #D5D5DE;
                    border-radius: 9px; padding: 9px 14px;
                }
                QDialog#youtubeAuthDialog QPushButton:hover { background: #FFFFFF; border-color: #1DB954; }
                QDialog#youtubeAuthDialog QPushButton#accentButton {
                    background: #1DB954; color: #101010; border: none; font-weight: 800;
                }
                QDialog#youtubeAuthDialog QPushButton#accentButton:hover { background: #16883D; color: #FFFFFF; }
                QDialog#youtubeAuthDialog QMessageBox { background: #F5F5F7; color: #222222; }
                QDialog#youtubeAuthDialog QMessageBox QLabel { color: #222222; min-width: 280px; }
                QDialog#youtubeAuthDialog QMessageBox QPushButton { background: #E8E8EE; color: #222222; }
            """)
        else:
            dialog.setStyleSheet("""
                QDialog#youtubeAuthDialog { background-color: #181818; color: #F5F5F5; }
                QDialog#youtubeAuthDialog QWidget { color: #F5F5F5; }
                QDialog#youtubeAuthDialog QLabel { color: #F5F5F5; background: transparent; }
                QDialog#youtubeAuthDialog QLabel#settingsTitle { color: #FFFFFF; font-size: 22pt; font-weight: 800; }
                QDialog#youtubeAuthDialog QLabel#settingsHint { color: #B3B3B3; }
                QDialog#youtubeAuthDialog QLineEdit, QDialog#youtubeAuthDialog QComboBox {
                    background: #242424; color: #FFFFFF; border: 1px solid #3A3A3A;
                    border-radius: 9px; padding: 8px 10px; min-height: 20px;
                    selection-background-color: #1DB954; selection-color: #101010;
                }
                QDialog#youtubeAuthDialog QComboBox QAbstractItemView {
                    background: #242424; color: #FFFFFF; selection-background-color: #1DB954;
                    selection-color: #101010; border: 1px solid #3A3A3A;
                }
                QDialog#youtubeAuthDialog QPushButton {
                    background: #282828; color: #F5F5F5; border: 1px solid #3A3A3A;
                    border-radius: 9px; padding: 9px 14px;
                }
                QDialog#youtubeAuthDialog QPushButton:hover { background: #333333; border-color: #1DB954; }
                QDialog#youtubeAuthDialog QPushButton#accentButton {
                    background: #1DB954; color: #101010; border: none; font-weight: 800;
                }
                QDialog#youtubeAuthDialog QPushButton#accentButton:hover { background: #1ED760; }
                QDialog#youtubeAuthDialog QMessageBox { background: #181818; color: #FFFFFF; }
                QDialog#youtubeAuthDialog QMessageBox QLabel { color: #FFFFFF; min-width: 280px; }
                QDialog#youtubeAuthDialog QMessageBox QPushButton { background: #282828; color: #FFFFFF; }
            """)
        dialog.exec()

    def disconnect_youtube_account(self):
        answer = QMessageBox.question(
            self, "Отключить YouTube Music",
            "Удалить сохранённые настройки доступа? Уже импортированный список останется на компьютере.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.youtube_cookie_file = ""
        self.youtube_auth_mode = "file"
        self.youtube_auth_browser = "chrome"
        self.youtube_auth_profile = ""
        for key in ("youtube_cookie_file", "youtube_auth_mode", "youtube_auth_browser", "youtube_auth_profile"):
            self.settings.remove(key)
        self.settings.sync()
        self.refresh_likes_list()
        self.set_status("Доступ к аккаунту отключён. Локальный кэш лайков сохранён.", "likes")

    def sync_youtube_likes(self):
        """Импортирует системный плейлист YouTube Music LM в отдельном QThread."""
        auth_kwargs = self.youtube_auth_kwargs()
        if not auth_kwargs:
            self.connect_youtube_account()
            return
        if self.youtube_sync_worker is not None and self.youtube_sync_worker.isRunning():
            self.set_status("Синхронизация уже выполняется…", "likes")
            return
        self._youtube_likes_before_sync = [dict(track) for track in self.youtube_liked_tracks]
        self._youtube_sync_rating_changes = {}
        self._youtube_sync_error = ""
        self._youtube_sync_had_results = False
        self.sync_account_button.setEnabled(False)
        self.set_status("Подключаюсь к YouTube Music и загружаю плейлист «Понравившиеся»…", "likes")
        self._youtube_sync_page_seen = False
        worker = SearchWorker(
            "", "youtube", "relevance", 100, self,
            direct_url="https://music.youtube.com/playlist?list=LM",
            cache_enabled=False, paginate_all=True, max_total=10000, **auth_kwargs
        )
        self.youtube_sync_worker = worker
        worker.results_ready.connect(lambda tracks, note, w=worker: self.on_youtube_likes_results(w, tracks, note))
        worker.failed.connect(lambda error, w=worker: self.on_youtube_likes_error(w, error))
        worker.finished.connect(lambda w=worker: self.on_youtube_likes_finished(w))
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _merge_youtube_sync_rating_changes(self, tracks):
        """Свежие подтверждённые клики имеют приоритет над снимком плейлиста LM."""
        changes = self._youtube_sync_rating_changes
        recent = [dict(track) for track, liked in reversed(changes.values()) if liked]
        return recent + [dict(track) for track in tracks if isinstance(track, dict)
                         and self.youtube_video_id(track) not in changes]

    def on_youtube_likes_results(self, worker, tracks, note):
        if worker is not self.youtube_sync_worker:
            return

        note = str(note or "")
        is_page = note.startswith("__SC_LIKES_PAGE__:")
        is_done = note.startswith("__SC_LIKES_DONE__:")
        if is_done:
            if not self._youtube_sync_page_seen:
                self.youtube_liked_tracks = self._merge_youtube_sync_rating_changes([])
            self._youtube_sync_had_results = bool(self.youtube_liked_tracks)
            self.set_status(
                f"Получено {len(self.youtube_liked_tracks)} треков из YouTube Music…", "likes"
            )
            return

        normalized = []
        seen = set()
        if is_page:
            # Первая страница начинает новую синхронизацию. Если она завершится
            # ошибкой, on_youtube_likes_finished восстановит прежний успешный кэш.
            if not getattr(self, "_youtube_sync_page_seen", False):
                self._youtube_sync_page_seen = True
                self.youtube_liked_tracks = []
                self._likes_rendered_counts["youtube"] = 0
                self._likes_list_signatures.pop("youtube", None)
                self.youtube_likes_list.clear()
            for existing in self.youtube_liked_tracks:
                if isinstance(existing, dict) and existing.get("url"):
                    seen.add(self.favorite_key(existing))
        else:
            # Совместимость с обычным worker, если источник вернул весь список за раз.
            self.youtube_liked_tracks = []

        for track in tracks:
            if not isinstance(track, dict) or not track.get("url"):
                continue
            saved = dict(track)
            saved["source"] = "youtube"
            saved["youtube_music_like"] = True
            key = self.favorite_key(saved)
            if key not in seen:
                seen.add(key)
                normalized.append(saved)

        if is_page:
            self.youtube_liked_tracks.extend(normalized)
        else:
            self.youtube_liked_tracks = normalized

        if normalized:
            self._youtube_sync_had_results = True
        self.youtube_liked_tracks = self._merge_youtube_sync_rating_changes(self.youtube_liked_tracks)
        self.refresh_likes_list()
        self._refresh_youtube_like_buttons()
        self.set_status(f"Получено {len(self.youtube_liked_tracks)} треков из YouTube Music…", "likes")

    def on_youtube_likes_error(self, worker, error):
        if worker is not self.youtube_sync_worker:
            return
        self._youtube_sync_error = str(error or "Неизвестная ошибка синхронизации")

    def on_youtube_likes_finished(self, worker):
        if worker is not self.youtube_sync_worker:
            return
        self.youtube_sync_worker = None
        self.sync_account_button.setEnabled(True)
        if self._youtube_sync_error:
            # При неудачном обновлении сохраняем последний удачный импорт,
            # даже если worker успел показать промежуточную порцию.
            self.youtube_liked_tracks = self._merge_youtube_sync_rating_changes(self._youtube_likes_before_sync)
            self._youtube_sync_rating_changes.clear()
            self.save_youtube_likes()
            self.refresh_likes_list()
            self._refresh_youtube_like_buttons()
            raw_error = self._youtube_sync_error.replace("\n", " ")
            if any(token in raw_error.casefold() for token in (
                "не смог прочитать cookies", "cookies database", "cookie database",
                "could not find firefox", "failed to load cookies", "could not copy",
            )):
                guidance = (
                    "Не удалось прочитать cookies выбранного браузера. Для Waterfox проверь, что выбран профиль "
                    "из about:profiles → Root Directory, и полностью закрой Waterfox перед повтором. "
                    "Для других браузеров проверь выбранный профиль и закрой его фоновые процессы. "
                    "Если не поможет — используй свежий cookies.txt. "
                )
            else:
                guidance = "Не удалось синхронизировать YouTube Music. Проверь вход и доступ к плейлисту «Понравившиеся». "
            message = guidance + raw_error[:260]
            self.set_status(message, "likes")
            return
        if self._youtube_sync_had_results or not self._youtube_sync_error:
            if not self._youtube_sync_had_results:
                self.youtube_liked_tracks = []
            self.youtube_liked_tracks = self._merge_youtube_sync_rating_changes(self.youtube_liked_tracks)
            self._youtube_sync_rating_changes.clear()
            self._youtube_last_sync_at = time.time()
            self.settings.setValue("youtube_last_sync_at", self._youtube_last_sync_at)
            self.save_youtube_likes()
            count = len(self.youtube_liked_tracks)
            self.set_status(f"Синхронизировано с YouTube Music: {count} треков", "likes")
            self.refresh_likes_list()
            self._refresh_youtube_like_buttons()
        else:
            self.set_status("YouTube Music не вернул лайки. Проверь авторизацию и доступ к плейлисту LM.", "likes")

    def open_likes_menu(self, point, list_widget=None):
        list_widget = list_widget or self.likes_list
        item = list_widget.itemAt(point)
        if item is None:
            return
        track = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(track, dict):
            return
        menu = self.make_context_menu()
        if track.get("source") != "local":
            menu.addAction("⬇   Скачать офлайн", lambda t=dict(track): self.download_track(t))
        menu.addAction("▶   Воспроизвести", lambda t=dict(track): self.add_to_queue(t, True))
        menu.addAction("＋   Добавить в очередь", lambda t=dict(track): self.add_to_queue(t, False))
        if track.get("source") in ("youtube", "soundcloud"):
            menu.addAction("♫   Запустить радио по треку", lambda t=dict(track): self.start_radio(t))
        menu.exec(list_widget.viewport().mapToGlobal(point))

    @staticmethod
    def favorite_key(track):
        return f"{track.get('source', 'unknown')}|{track.get('url', '')}"

    def load_favorites(self):
        try:
            if self.favorites_file.exists():
                raw = json.loads(self.favorites_file.read_text(encoding="utf-8"))
                if isinstance(raw, list):
                    result = {}
                    for track in raw:
                        if isinstance(track, dict) and track.get("url"):
                            result[self.favorite_key(track)] = track
                    return result
                if isinstance(raw, dict):
                    return {str(k): v for k, v in raw.items() if isinstance(v, dict) and v.get("url")}
        except (OSError, json.JSONDecodeError) as error:
            logging.getLogger("aurora").info(f"[Music Player] Не удалось прочитать favorites.json: {error}")
        return {}

    def save_favorites(self):
        try:
            temporary = self.favorites_file.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(list(self.favorites.values()), ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            temporary.replace(self.favorites_file)
        except OSError as error:
            QMessageBox.warning(self, "Не удалось сохранить лайки",
                                f"Проверь права на запись в папку программы.\n\n{error}")

    @staticmethod
    def youtube_video_id(track):
        """Возвращает video ID из метаданных или URL YouTube."""
        if not isinstance(track, dict):
            return ""
        explicit = str(track.get("video_id") or track.get("videoId") or "").strip()
        if explicit:
            return explicit
        url = str(track.get("url") or "").strip()
        for pattern in (
            r"[?&]v=([A-Za-z0-9_-]{6,})",
            r"youtu\.be/([A-Za-z0-9_-]{6,})",
            r"/(?:shorts|embed)/([A-Za-z0-9_-]{6,})",
        ):
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return ""

    def is_youtube_music_liked(self, track):
        """Состояние сердечка для YouTube берётся из отдельного кэша LM, не из favorites.json."""
        video_id = self.youtube_video_id(track)
        if not video_id:
            return bool(isinstance(track, dict) and track.get("youtube_music_like"))
        if video_id in self._youtube_rating_targets:
            return self._youtube_rating_targets[video_id]
        return any(self.youtube_video_id(saved) == video_id for saved in self.youtube_liked_tracks
                   if isinstance(saved, dict))

    def _refresh_youtube_like_buttons(self, video_id=None):
        """Обновляет сердечки YouTube во всех видимых списках и нижней панели."""
        if video_id == "":
            self.update_bottom_track_actions()
            return

        liked_ids = {self.youtube_video_id(saved) for saved in self.youtube_liked_tracks
                     if isinstance(saved, dict)}

        for list_widget in (
            getattr(self, "source_list", None),
            getattr(self, "youtube_likes_list", None),
            getattr(self, "soundcloud_likes_list", None),
            getattr(self, "queue_list", None),
        ):
            if list_widget is None:
                continue

            for index in range(list_widget.count()):
                item = list_widget.item(index)
                row = list_widget.itemWidget(item)
                row_track = row.track if isinstance(row, TrackRow) else None

                if not isinstance(row_track, dict) or not hasattr(row, "favorite_button"):
                    continue
                if str(row_track.get("source") or "") != "youtube":
                    continue
                row_video_id = self.youtube_video_id(row_track)
                if not row_video_id or (video_id is not None and row_video_id != video_id):
                    continue

                liked = self._youtube_rating_targets.get(row_video_id, row_video_id in liked_ids)
                pending = row_video_id in self._youtube_rating_pending
                button = row.favorite_button
                signals_were_blocked = button.blockSignals(True)
                try:
                    button.setChecked(liked)
                    button.setIcon(control_icon(
                        "heart" if liked else "heart-outline",
                        "#1DB954" if liked else "#B3B3B3", 24
                    ))
                    button.setIconSize(QSize(22, 22))
                    button.setEnabled(not pending)
                    button.setToolTip(
                        "Отправляю изменение в YouTube Music…" if pending else
                        ("Снять лайк в YouTube Music" if liked
                         else "Поставить настоящий лайк в аккаунте YouTube Music")
                    )

                    # Применяем стиль и запрашиваем перерисовку только ПОСЛЕ
                    # установки всех свойств кнопки.
                    button.update()
                    button.style().unpolish(button)
                    button.style().polish(button)
                    button.repaint()
                finally:
                    button.blockSignals(signals_were_blocked)

        self.update_bottom_track_actions()

    def set_youtube_music_like(self, track, liked, button=None):
        """Отправляет настоящий rating через ytmusicapi, не трогая локальное избранное."""
        if not isinstance(track, dict) or str(track.get("source") or "") != "youtube":
            self.set_status("Настоящие лайки аккаунта доступны только для треков YouTube Music.", self.current_source)
            return
        video_id = self.youtube_video_id(track)
        if not video_id:
            self.set_status("У трека нет YouTube video ID — лайк аккаунта поставить нельзя.", "youtube")
            return
        if not self.youtube_auth_kwargs():
            self.connect_youtube_account()
            return
        if video_id in self._youtube_rating_pending:
            self.set_status("Запрос лайка для этого трека уже выполняется…", "youtube")
            return
        liked = bool(liked)
        if liked == self.is_youtube_music_liked(track):
            self._refresh_youtube_like_buttons(video_id)
            return

        self._youtube_rating_pending.add(video_id)
        self._youtube_rating_targets[video_id] = liked
        self._youtube_rating_tracks[video_id] = dict(
            track, source="youtube", video_id=video_id, youtube_music_like=True
        )
        self._refresh_youtube_like_buttons(video_id)
        self.refresh_likes_list()
        browser_spec = ""
        if self.youtube_auth_mode == "browser":
            browser_spec = self.youtube_auth_browser
            if self.youtube_auth_profile:
                browser_spec = f"{browser_spec}|{self.youtube_auth_profile}"
        worker = YouTubeRatingWorker(
            track, liked, self.youtube_auth_mode, self.youtube_cookie_file, browser_spec, self
        )
        self._youtube_rating_workers.add(worker)
        worker.result_ready.connect(self.on_youtube_music_like_result)
        worker.finished.connect(lambda w=worker: self._youtube_rating_workers.discard(w))
        worker.finished.connect(worker.deleteLater)
        self.set_status("Отправляю лайк в аккаунт YouTube Music…" if liked
                        else "Снимаю лайк в аккаунте YouTube Music…", "youtube")
        worker.start()

    def on_youtube_music_like_result(self, track, liked, success, message):
        """Применяет изменение кэша только после успешного ответа YouTube Music."""
        video_id = self.youtube_video_id(track)
        self._youtube_rating_pending.discard(video_id)
        self._youtube_rating_targets.pop(video_id, None)
        self._youtube_rating_tracks.pop(video_id, None)
        if success:
            if liked:
                saved = dict(track)
                saved["source"] = "youtube"
                saved["video_id"] = video_id
                saved["youtube_music_like"] = True
                # Последний поставленный лайк сразу виден в начале библиотеки.
                self.youtube_liked_tracks = [saved] + [
                    item for item in self.youtube_liked_tracks
                    if not isinstance(item, dict) or self.youtube_video_id(item) != video_id
                ]
            else:
                self.youtube_liked_tracks = [
                    item for item in self.youtube_liked_tracks
                    if not isinstance(item, dict) or self.youtube_video_id(item) != video_id
                ]
            if self.youtube_sync_worker is not None:
                saved_change = dict(track, source="youtube", video_id=video_id, youtube_music_like=True)
                self._youtube_sync_rating_changes.pop(video_id, None)
                self._youtube_sync_rating_changes[video_id] = (saved_change, bool(liked))
            self._youtube_last_sync_at = time.time()
            self.settings.setValue("youtube_last_sync_at", self._youtube_last_sync_at)
            self.settings.sync()
            self.save_youtube_likes()
            # Сначала обновляем видимые сердечки в поиске, лайках и очереди.
            self._refresh_youtube_like_buttons(video_id)
            if self.source_list.isVisible():
                self.source_list.viewport().update()
            # Затем перестраиваем списки лайков и синхронизируем нижнюю панель.
            self.refresh_likes_list()
            self.update_bottom_track_actions()
            self.set_status(message, "likes" if self.current_source == "likes" else "youtube")
        else:
            # Запрос завершился ошибкой: возвращаем видимым кнопкам
            # фактическое состояние лайка из кэша.
            self._refresh_youtube_like_buttons(video_id)
            self.refresh_likes_list()
            self.set_status(message, "youtube")
            QMessageBox.warning(self, "Не удалось изменить лайк YouTube Music", message)

    def is_favorite(self, track):
        return self.favorite_key(track) in self.favorites

    def is_disliked(self, track):
        return bool(isinstance(track, dict) and track.get("url")
                    and self.radio_track_key(track) in self.disliked_track_keys)

    def update_bottom_track_actions(self):
        """Синхронизирует лайк и дизлайк нижней панели с текущей песней."""
        track = self.current_track if isinstance(self.current_track, dict) else None
        available = bool(track and track.get("url"))
        if not hasattr(self, "bottom_favorite_button") or not hasattr(self, "bottom_dislike_button"):
            return
        youtube_track = bool(available and str(track.get("source") or "") == "youtube")
        favorite = bool(available and (
            self.is_youtube_music_liked(track) if youtube_track else self.is_favorite(track)
        ))
        video_id = self.youtube_video_id(track) if youtube_track else ""
        rating_pending = bool(video_id and video_id in self._youtube_rating_pending)
        disliked = bool(available and self.is_disliked(track))
        self.bottom_favorite_button.blockSignals(True)
        self.bottom_favorite_button.setEnabled(available and not rating_pending)
        self.bottom_favorite_button.setChecked(favorite)
        self.bottom_favorite_button.setIcon(control_icon(
            "heart" if favorite else "heart-outline",
            "#1DB954" if favorite else "#B3B3B3", 22
        ))
        self.bottom_favorite_button.setToolTip(
            ("Снять лайк в YouTube Music" if favorite else "Поставить настоящий лайк в YouTube Music")
            if youtube_track else ("Убрать из локальных лайков" if favorite else "Добавить в локальные лайки")
        )
        self.bottom_favorite_button.blockSignals(False)
        self.bottom_dislike_button.blockSignals(True)
        self.bottom_dislike_button.setEnabled(available)
        self.bottom_dislike_button.setChecked(disliked)
        self.bottom_dislike_button.setIcon(control_icon(
            "thumb-down" if disliked else "thumb-down-outline",
            "#1DB954" if disliked else "#B3B3B3", 22
        ))
        self.bottom_dislike_button.setToolTip(
            "Этот трек скрыт из будущих миксов" if disliked
            else "Скрыть трек из будущих миксов и радио"
        )
        self.bottom_dislike_button.blockSignals(False)

    def toggle_current_favorite(self):
        track = self.current_track
        if not isinstance(track, dict) or not track.get("url"):
            return
        if str(track.get("source") or "") == "youtube":
            self.set_youtube_music_like(
                track, not self.is_youtube_music_liked(track), self.bottom_favorite_button
            )
        else:
            self.toggle_favorite(track, self.bottom_favorite_button)

    def dislike_current_track(self):
        """Скрывает текущую песню в приложении и пропускает её в текущем миксе."""
        track = self.current_track
        if not isinstance(track, dict) or not track.get("url"):
            return
        key = self.radio_track_key(track)
        if key in self.disliked_track_keys:
            self.set_status("Этот трек уже скрыт из будущих миксов.", track.get("source"))
            self.update_bottom_track_actions()
            return

        self.disliked_track_keys.add(key)
        self.settings.setValue("disliked_track_keys", sorted(self.disliked_track_keys))
        self.settings.sync()
        self.radio_seen_urls.add(key)
        self.radio_candidates = [candidate for candidate in self.radio_candidates
                                 if not self.is_disliked(candidate)]

        source = str(track.get("source") or "")
        if source in self.source_results:
            self.source_results[source] = [candidate for candidate in self.source_results[source]
                                           if not self.is_disliked(candidate)]
            if self.current_source == source:
                self.source_list.setUpdatesEnabled(False)
                try:
                    self.source_list.clear()
                    for candidate in self.source_results[source]:
                        self.add_result(candidate)
                finally:
                    self.source_list.setUpdatesEnabled(True)
                self.schedule_visible_artwork(self.source_list)

        # Убираем все копии из очереди, в том числе текущую. Индекс оставляем
        # на позиции перед следующим треком, чтобы Next не перепрыгнул через него.
        current_uid = str(track.get("queue_id") or "")
        old_current_index = self.index_for_uid(current_uid) if current_uid else self.current_queue_index
        old_queue = list(self.queue_tracks)
        removed_indices = [index for index, item in enumerate(old_queue)
                           if self.radio_track_key(item) == key]
        current_was_removed = (0 <= old_current_index < len(old_queue)
                               and self.radio_track_key(old_queue[old_current_index]) == key)
        if removed_indices:
            if current_was_removed:
                new_current_index = old_current_index - sum(
                    1 for index in removed_indices if index <= old_current_index
                )
            else:
                new_current_index = old_current_index - sum(
                    1 for index in removed_indices if index < old_current_index
                )
            self.queue_tracks = [item for item in old_queue if self.radio_track_key(item) != key]
            self.refresh_queue_list()
            self.current_queue_index = new_current_index

        self.update_bottom_track_actions()
        self.set_status(
            f"Скрыто из рекомендаций: {track.get('title') or 'Трек'}. "
            "Он не будет добавляться в будущие миксы и радио.", source
        )

        next_index = self.peek_next_index()
        if next_index is not None:
            self.play_queue_index(next_index)
        elif self.radio_mode_active:
            # Если это был последний трек очереди радио, просим новую подборку.
            self.player.stop()
            self._radio_waiting_for_tracks = True
            self.radio_refill_attempt_key = ""
            self.radio_refill_next_allowed_at = 0.0
            QTimer.singleShot(0, lambda: self.maybe_refill_radio(force=True)
                              if self.radio_mode_active else None)
        else:
            # Нет следующей песни — останавливаем скрытый трек, не оставляя его играть.
            self.player.stop()
            self.current_track = None
            self.current_queue_index = -1
            self.bottom_title.setText("Ничего не играет")
            self.bottom_title.setToolTip("Текущий трек")
            self.bottom_artist.setText("Выбери песню")
            self.bottom_artist.setToolTip("")
            self.show_cover("")
            self.play_button.setIcon(control_icon("play", "#FFFFFF"))
            self.update_bottom_track_actions()

    def toggle_favorite(self, track, button=None):
        key = self.favorite_key(track)
        if key in self.favorites:
            self.favorites.pop(key, None)
            is_saved = False
        else:
            # Храним только метаданные и URL, аудио не скачивается.
            self.favorites[key] = {
                "title": track.get("title", "Без названия"),
                "artist": track.get("artist", "Исполнитель неизвестен"),
                "url": track.get("url", ""),
                "thumbnail": track.get("thumbnail", ""),
                "artist_thumbnail": track.get("artist_thumbnail", ""),
                "duration": track.get("duration", 0),
                "view_count": track.get("view_count"),
                "timestamp": track.get("timestamp", 0),
                "source": track.get("source", self.current_source),
                "local_path": self.offline_path_for(track) or "",
            }
            is_saved = True
        self.save_favorites()
        if button is not None:
            button.setChecked(is_saved)
            button.setIcon(control_icon("heart" if is_saved else "heart-outline",
                                        "#1DB954" if is_saved else "#B3B3B3", 24))
            button.setIconSize(QSize(22, 22))
            button.setToolTip("Убрать из лайков" if is_saved else "Добавить в лайки")
        if self.current_source == "likes":
            self.refresh_likes_list()
            self.set_status(f"Лайки обновлены · локально сохранено {len(self.favorites)} треков.", "likes")
        else:
            self.set_status("Добавлено в лайки ♥" if is_saved else "Удалено из лайков", self.current_source)
        self.update_bottom_track_actions()

    def shuffle_artist_tracks(self):
        """Перемешивает текущую выдачу профиля артиста и запускает её с начала."""
        source = self.current_source
        tracks = [dict(track) for track in self.source_results.get(source, [])
                  if isinstance(track, dict) and track.get("url")]
        if not tracks:
            self.set_status("Сначала дождись загрузки треков исполнителя.", source)
            return
        random.shuffle(tracks)
        self.cancel_pending_request()
        self.queue_tracks = []
        self.queue_list.clear()
        self.current_queue_index = -1
        self.shuffle_future = None
        self.radio_mode_active = False
        self.queue_mode = "manual"
        self._soundcloud_queue_waiting = False
        for track in tracks:
            queued = dict(track)
            queued["queue_id"] = uuid4().hex
            self.queue_tracks.append(queued)
        self.refresh_queue_list()
        self.toggle_queue_if_hidden()
        self.set_status(f"Перемешанный микс исполнителя: {len(tracks)} треков.", source)
        self.play_queue_index(0)

    def start_artist_mix(self):
        """Запускает бесконечное радио с приоритетом текущего артиста."""
        source = self.current_source
        tracks = [track for track in self.source_results.get(source, [])
                  if isinstance(track, dict) and track.get("url")]
        if not tracks:
            self.set_status("Сначала дождись загрузки треков исполнителя.", source)
            return
        artist = str(getattr(self, "active_artist_profile", "") or "").strip()
        artist_key = artist.casefold()
        seed = next((track for track in tracks
                     if str(track.get("artist", "")).casefold() == artist_key), tracks[0])
        self.start_radio(dict(seed), artist_context=artist or str(seed.get("artist") or ""))

    def search_artist_name(self, artist, source):
        """Открывает профиль артиста через музыкальный каталог, не через видео канала."""
        track_data = dict(artist) if isinstance(artist, dict) else None
        if track_data:
            source = str(track_data.get("source") or source or "")
            # В каталоге артиста используем каноническое имя. В обычной выдаче,
            # если yt-dlp вернул список кредитов через запятую, берём первый
            # явно указанный credit вместо поиска по строке нескольких артистов.
            if source == "youtube" and track_data.get("profile_artist_name"):
                artist_name = str(track_data.get("profile_artist_name") or "").strip()
            elif source == "youtube":
                credits = track_data.get("artist_metadata") or []
                if isinstance(credits, str):
                    credits = [credits]
                artist_name = str((credits[0] if credits else track_data.get("artist")) or "").strip()
            else:
                artist_name = str(track_data.get("artist") or "").strip()
        else:
            artist_name = str(artist or "").strip()
        if source not in ("youtube", "soundcloud") or not artist_name:
            return
        if artist_name.casefold() in ("исполнитель неизвестен", "unknown artist"):
            return
        if self.current_source != source:
            self.set_source(source)

        profile_url = ""
        if source == "soundcloud":
            # Для SoundCloud прямой URL профиля полезен: yt-dlp может взять его
            # набор треков/плейлистов. Для YouTube это намеренно не используется.
            if track_data:
                profile_url = str(track_data.get("artist_url") or "").strip()
                wanted = SearchWorker._normalize_artist_name(artist_name)
                channel = str(track_data.get("channel") or "").strip()
                uploader = str(track_data.get("uploader") or "").strip()
                channel_url = str(track_data.get("channel_url") or "").strip()
                uploader_url = str(track_data.get("uploader_url") or "").strip()
                if not profile_url:
                    if channel_url and SearchWorker._normalize_artist_name(channel) == wanted:
                        profile_url = channel_url
                    elif uploader_url and SearchWorker._normalize_artist_name(uploader) == wanted:
                        profile_url = uploader_url
            if not profile_url:
                profile_url = str(self.active_artist_profile_url or "").strip()
            self.active_artist_profile_url = profile_url
            self._pending_direct_url = profile_url
        else:
            # Критический фикс: больше не открываем https://youtube.com/channel/.../videos.
            # Этот список содержит ролики канала, а не песни из карточки YouTube Music.
            self.active_artist_profile_url = ""
            self._pending_direct_url = ""

        self.artist_profile_open = True
        self.artist_profile_query = artist_name
        self.active_artist_profile = artist_name
        self.search_artist_target = artist_name
        self.search_input.setText(artist_name)
        self.sort_mode = "relevance"
        self.artist_popular_label.setText("Треки исполнителя")
        self.start_search()

    def start_radio(self, track, artist_context=None):
        """Запускает радио; для профиля артиста сохраняет контекст для будущих пополнений."""
        self._cancel_supermix()
        if track.get("source") not in ("youtube", "soundcloud"):
            QMessageBox.information(self, "Радио", "Радио доступно для треков YouTube и SoundCloud.")
            return
        if self.radio_worker is not None and self.radio_worker.isRunning():
            self.radio_worker.cancel()
        if self.radio_refill_worker is not None and self.radio_refill_worker.isRunning():
            self.radio_refill_worker.cancel()
        self.radio_refill_worker = None
        self.radio_mode_active = False
        self.radio_refill_attempt_key = ""
        self.radio_refill_added_urls = set()
        self.radio_refill_added_count = 0
        self.radio_refill_last_error = ""
        self._radio_refill_failed_attempts = 0
        self.radio_refill_round = 0
        self.radio_refill_next_allowed_at = 0.0
        self.radio_artist_context = str(artist_context or "").strip()
        self.radio_seen_urls = set()
        self._radio_waiting_for_tracks = False
        self._radio_retry_scheduled = False
        if self.radio_dialog is not None:
            self.radio_dialog.hide()
            self.radio_dialog.deleteLater()
            self.radio_dialog = None
        artist = str(track.get("artist") or "").strip()
        title = str(track.get("title") or "").strip()
        query = (f"{self.radio_artist_context} mix" if self.radio_artist_context
                 else f"{artist} {title} mix").strip()
        if not query:
            query = title or artist or "popular music mix"
        self.radio_candidates = []
        self.radio_note = ""
        dialog = RadioDialog(self, track)
        self.radio_dialog = dialog
        if track.get("thumbnail"):
            self.request_image(track.get("thumbnail"), dialog.cover)
        dialog.show_animated()
        self.set_status(f"Радио: ищу похожие треки по запросу «{query}»…", track.get("source"))
        auth_kwargs = self.youtube_auth_kwargs() if track.get("source") == "youtube" else self.soundcloud_auth_kwargs()
        # Радио не использует кэш поисковой выдачи: повтор запроса должен находить
        # новые треки, иначе в бесконечном режиме приходят одни и те же URL.
        worker = SearchWorker(query, track.get("source"), "relevance", 75, self,
                              cache_enabled=False, **auth_kwargs)
        self.radio_worker = worker
        worker.results_ready.connect(lambda results, note, w=worker: self.on_radio_results(w, results, note))
        worker.failed.connect(lambda error, w=worker: self.on_radio_error(w, error))
        worker.finished.connect(lambda w=worker: self.on_radio_worker_finished(w))
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def on_radio_results(self, worker, tracks, note):
        if worker is not self.radio_worker:
            return
        if tracks:
            # Последняя эмиссия будет полной выдачей; скрытые дизлайком треки
            # не должны попадать ни в начальный микс, ни в следующие пополнения.
            self.radio_candidates = [dict(track) for track in tracks
                                     if isinstance(track, dict) and not self.is_disliked(track)][:75]
            self.radio_note = note or ""
            if self.radio_dialog is not None:
                self.radio_dialog.status_label.setText(f"Найдено {len(self.radio_candidates)} треков…")

    def on_radio_error(self, worker, error):
        if worker is self.radio_worker:
            self.radio_note = str(error or "Не удалось получить радио-микс.")

    def on_radio_worker_finished(self, worker):
        if worker is not self.radio_worker:
            return
        self.radio_worker = None
        dialog = self.radio_dialog
        tracks = self.radio_candidates[:75]
        if not tracks:
            if dialog is not None:
                dialog.fade_out(lambda: self.show_toast(
                    "Не удалось найти похожие треки. " + self.radio_note[:250], 5000
                ))
            self.radio_dialog = None
            return
        if dialog is not None:
            dialog.status_label.setText(f"Готово: {len(tracks)} треков. Запускаю радио…")
            dialog.fade_out(lambda items=tracks: self.replace_queue_with_radio(items))
            self.radio_dialog = None
        else:
            self.replace_queue_with_radio(tracks)

    def replace_queue_with_radio(self, tracks):
        """Заменяет очередь найденным миксом и запускает первый трек."""
        tracks = [dict(track) for track in tracks
                  if isinstance(track, dict) and track.get("url") and not self.is_disliked(track)]
        if not tracks:
            self.set_status("В радио не осталось доступных треков: все найденные композиции скрыты.")
            return
        self.cancel_pending_request()
        self.queue_tracks = []
        self.queue_list.clear()
        self.current_queue_index = -1
        self.shuffle_future = None
        self.radio_mode_active = True
        self.queue_mode = "radio"
        self.radio_seen_urls = set()
        self.radio_refill_attempt_key = ""
        self.radio_refill_added_count = 0
        self.radio_refill_next_allowed_at = 0.0
        self._radio_refill_failed_attempts = 0
        self._radio_waiting_for_tracks = False
        for track in tracks[:75]:
            queued = dict(track)
            queued["queue_id"] = uuid4().hex
            self.queue_tracks.append(queued)
            self.radio_seen_urls.add(self.radio_track_key(queued))
        self.refresh_queue_list()
        self.update_queue_count()
        self.toggle_queue_if_hidden()
        self.set_status(f"Радио готово: {len(self.queue_tracks)} похожих треков. Включаю первый.")
        self.play_queue_index(0)

    @staticmethod
    def radio_track_key(track):
        return f"{track.get('source', '')}|{track.get('url', '')}"

    def maybe_refill_radio(self, force=False):
        """Заранее пополняет радио, пока в очереди осталось не более 8 треков."""
        if not self.radio_mode_active:
            return
        cooldown_remaining = getattr(self, "radio_refill_next_allowed_at", 0.0) - time.monotonic()
        if cooldown_remaining > 0:
            if force and not self._radio_retry_scheduled:
                self._radio_retry_scheduled = True
                QTimer.singleShot(max(100, int(cooldown_remaining * 1000) + 100), self._retry_radio_refill)
            return
        current_index = self.current_queue_index
        if current_index < 0 and self.requested_track is not None:
            current_index = self.requested_index
        remaining = len(self.queue_tracks) - current_index - 1 if current_index >= 0 else len(self.queue_tracks)
        if not force and remaining > 8:
            return
        if self.radio_refill_worker is not None and self.radio_refill_worker.isRunning():
            return
        seed = self.requested_track or self.current_track or (self.queue_tracks[-1] if self.queue_tracks else None)
        if not isinstance(seed, dict):
            return
        source = str(seed.get("source", ""))
        if source not in ("youtube", "soundcloud"):
            return
        anchor_key = self.radio_track_key(seed)
        if anchor_key == self.radio_refill_attempt_key:
            return
        self.radio_refill_attempt_key = anchor_key
        query = f"{str(seed.get('artist') or '').strip()} {str(seed.get('title') or '').strip()} mix".strip()
        if not query:
            return
        seed_artist = str(seed.get("artist") or "").strip()
        seed_title = str(seed.get("title") or "").strip()
        artist_context = str(getattr(self, "radio_artist_context", "") or "").strip()
        if artist_context:
            query_variants = [
                f"{artist_context} mix",
                f"{artist_context} popular songs",
                f"{artist_context} songs",
                f"{artist_context} related artists mix",
                f"{seed_artist} {seed_title} mix",
                f"songs similar to {seed_title} {seed_artist}",
            ]
        else:
            query_variants = [
                f"{seed_artist} {seed_title} mix",
                f"{seed_artist} related songs",
                f"songs similar to {seed_title} {seed_artist}",
                f"{seed_artist} popular songs",
                f"{seed_title} similar tracks",
            ]
        query_variants = [query.strip() for query in query_variants if query.strip()]
        if not query_variants:
            query_variants = [seed_title or seed_artist or "popular music mix"]
        self.radio_refill_round += 1
        query = query_variants[(self.radio_refill_round - 1) % len(query_variants)]
        auth_kwargs = self.youtube_auth_kwargs() if source == "youtube" else self.soundcloud_auth_kwargs()
        # Каждая попытка делает свежий запрос: кэш радио часто возвращает только
        # предыдущую подборку, которая уже полностью присутствует в очереди.
        worker = SearchWorker(query, source, "relevance", 75, self,
                              cache_enabled=False, **auth_kwargs)
        self.radio_refill_worker = worker
        self.radio_refill_added_urls = set()
        self.radio_refill_added_count = 0
        self.radio_refill_last_error = ""
        worker.results_ready.connect(lambda tracks, note, w=worker: self.on_radio_refill_results(w, tracks, note))
        worker.failed.connect(lambda error, w=worker: self.on_radio_refill_error(w, error))
        worker.finished.connect(lambda w=worker: self.on_radio_refill_finished(w))
        worker.finished.connect(worker.deleteLater)
        self.set_status("Радио: незаметно ищу следующую подборку…", source)
        worker.start()

    def _retry_radio_refill(self):
        self._radio_retry_scheduled = False
        if self.radio_mode_active:
            self.maybe_refill_radio(force=True)

    def radio_can_advance_now(self):
        """True only when the radio track ended or is within a tiny safety margin."""
        if self.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState:
            return True
        duration = self.player.duration()
        return duration > 0 and duration - self.player.position() <= 180

    def on_radio_refill_results(self, worker, tracks, note):
        if worker is not self.radio_refill_worker or not self.radio_mode_active:
            return
        added = 0
        for track in tracks:
            if not isinstance(track, dict) or self.is_disliked(track):
                continue
            key = self.radio_track_key(track)
            if not track.get("url") or key in self.radio_seen_urls:
                continue
            self.radio_seen_urls.add(key)
            self.radio_refill_added_urls.add(key)
            queued = dict(track)
            queued["queue_id"] = uuid4().hex
            self.queue_tracks.append(queued)
            self.append_queue_item(queued, len(self.queue_tracks) - 1)
            added += 1
        if added:
            self.radio_refill_added_count += added
            self.radio_refill_next_allowed_at = 0.0
            self.update_queue_count()
            self.set_status(f"Радио: добавлено ещё {added} треков в очередь.", worker.source)
            # Подготовка следующего потока запускается сразу, пока текущая песня играет.
            QTimer.singleShot(0, self.prepare_next_track)
            if (self._radio_waiting_for_tracks and self.peek_next_index() is not None
                    and self.radio_can_advance_now()):
                self._radio_waiting_for_tracks = False
                QTimer.singleShot(0, self.play_next)

    def on_radio_refill_error(self, worker, error):
        if worker is self.radio_refill_worker:
            self.radio_refill_last_error = str(error or "Не удалось продолжить радио.")
            self.radio_note = self.radio_refill_last_error
            self.radio_refill_next_allowed_at = max(
                self.radio_refill_next_allowed_at, time.monotonic() + 3.0
            )

    def on_radio_refill_finished(self, worker):
        if worker is not self.radio_refill_worker:
            return
        self.radio_refill_worker = None
        next_index = self.peek_next_index()
        if (self._radio_waiting_for_tracks and next_index is not None
                and self.radio_can_advance_now()):
            self._radio_waiting_for_tracks = False
            QTimer.singleShot(0, self.play_next)

        # Важный случай: поиск мог вернуть только дубликаты уже проигранной
        # подборки. Разрешаем повторить запрос с ДРУГИМ вариантом, даже если
        # текущая песня ещё играет и до конца очереди остаётся несколько треков.
        if self.radio_refill_added_count <= 0 and self.radio_mode_active:
            self.radio_refill_attempt_key = ""
            if self._radio_waiting_for_tracks and next_index is None:
                self._radio_refill_failed_attempts = getattr(
                    self, "_radio_refill_failed_attempts", 0) + 1
                if self._radio_refill_failed_attempts >= 5:
                    self._radio_waiting_for_tracks = False
                    self._radio_retry_scheduled = False
                    self.radio_mode_active = False
                    self.radio_refill_next_allowed_at = 0.0
                    message = (
                        "Не удалось подобрать следующий трек. Проверьте соединение "
                        "или выберите другой трек."
                    )
                    self.set_status(message, worker.source)
                    self.show_toast(message, 5000)
                    return
                # Когда очередь уже закончилась, повторяем поиск каждые 3 секунды.
                self.radio_refill_next_allowed_at = 0.0
                self.set_status(
                    f"Радио: не удалось найти следующий трек. "
                    f"Повторная попытка {self._radio_refill_failed_attempts}/5 через 3 секунды.",
                    worker.source
                )
                if not self._radio_retry_scheduled:
                    self._radio_retry_scheduled = True
                    QTimer.singleShot(3000, self._retry_radio_refill)
                return

            retry_delay = max(3.0, self.radio_refill_next_allowed_at - time.monotonic())
            self.radio_refill_next_allowed_at = time.monotonic() + retry_delay
            self.set_status("Радио: в выдаче были повторы, ищу другие треки…", worker.source)
            if not self._radio_retry_scheduled:
                self._radio_retry_scheduled = True
                QTimer.singleShot(int(retry_delay * 1000) + 100, self._retry_radio_refill)
        elif self.radio_mode_active:
            # Свежие треки добавлены. Сбрасываем счётчик ошибок и продолжаем
            # заранее пополнять очередь на следующей композиции.
            self._radio_refill_failed_attempts = 0
            self.radio_refill_next_allowed_at = 0.0
            if self._radio_waiting_for_tracks and self.peek_next_index() is None:
                self.radio_refill_attempt_key = ""
                self._radio_waiting_for_tracks = True
                QTimer.singleShot(0, lambda: self.maybe_refill_radio(force=True)
                                  if self.radio_mode_active else None)

    def toggle_queue_if_hidden(self):
        if not self.queue_open:
            self.toggle_queue()

    def make_context_menu(self):
        """Единое контекстное меню в графитовых тонах с зелёным выделением."""
        menu = QMenu(self)
        menu.setObjectName("darkMenu")
        if self.theme == "dark":
            menu.setStyleSheet("QMenu{background:#282828;color:#fff;border:1px solid #3b3b3b;padding:7px;} QMenu::item{padding:10px 22px 10px 14px;border-radius:7px;margin:1px;} QMenu::item:selected{background:#3a3a3a;color:#1DB954;} QMenu::separator{height:1px;background:#444;margin:5px 10px;}")
        else:
            menu.setStyleSheet("QMenu{background:#fff;color:#222;border:1px solid #ddd;padding:7px;} QMenu::item{padding:10px 22px 10px 14px;border-radius:7px;margin:1px;} QMenu::item:selected{background:#e1f4e7;color:#16883d;} QMenu::separator{height:1px;background:#ddd;margin:5px 10px;}")
        return menu

    def open_result_menu(self, point):
        item = self.source_list.itemAt(point)
        if item is None:
            return
        track = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(track, dict):
            return
        menu = self.make_context_menu()
        if track.get("source") != "local":
            menu.addAction("⬇   Скачать офлайн", lambda t=dict(track): self.download_track(t))
        menu.addAction("▶   Воспроизвести", lambda t=dict(track): self.add_to_queue(t, True))
        menu.addAction("＋   Добавить в очередь", lambda t=dict(track): self.add_to_queue(t, False))
        if track.get("source") in ("youtube", "soundcloud"):
            menu.addAction("♫   Запустить радио по треку", lambda t=dict(track): self.start_radio(t))
        artist = track.get("artist", "")
        if track.get("source") != "local" and artist and artist != "Исполнитель неизвестен":
            menu.addSeparator()
            menu.addAction("⌕   Найти треки исполнителя", lambda t=dict(track): self.find_artist(t))
        if str(track.get("url", "")).startswith(("https://", "http://")):
            menu.addAction("↗   Открыть на сайте", lambda t=dict(track): self.open_track_website(t))
        menu.exec(self.source_list.viewport().mapToGlobal(point))

    def find_artist(self, track):
        """Ищем популярные треки по клику на исполнителя."""
        self.search_artist_name(track.get("artist", ""), track.get("source"))

    def open_soundcloud_search_in_browser(self):
        """Запасной вариант, если API SoundCloud не отвечает."""
        from urllib.parse import quote_plus
        query = self.search_input.text().strip()
        QDesktopServices.openUrl(QUrl("https://soundcloud.com/search/sounds?q=" + quote_plus(query)))

    def open_track_website(self, track):
        url = str(track.get("url", ""))
        if url.startswith(("https://", "http://")):
            QDesktopServices.openUrl(QUrl(url))

    # ---------------------------------------------------------
    # Асинхронная загрузка обложек через QtNetwork.
    # ---------------------------------------------------------

    def on_likes_tab_changed(self, index):
        lists = (self.youtube_likes_list, self.soundcloud_likes_list, self.likes_list)
        if 0 <= int(index) < len(lists):
            list_widget = lists[int(index)]
            self.schedule_visible_artwork(list_widget)
            QTimer.singleShot(0, lambda lw=list_widget: self.maybe_load_more_likes(lw))

    def schedule_visible_artwork(self, list_widget):
        """Небольшой debounce: загружаем обложки только у видимых строк списка."""
        if list_widget is None:
            return
        key = id(list_widget)
        timer = self._visible_artwork_timers.get(key)
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda lw=list_widget: self.load_visible_artwork(lw))
            self._visible_artwork_timers[key] = timer
            list_widget.destroyed.connect(
                lambda _obj=None, k=key, t=timer: (t.stop(), self._visible_artwork_timers.pop(k, None))
            )
        timer.start(70)

    def load_visible_artwork(self, list_widget):
        if list_widget is None or not list_widget.isVisible():
            return
        viewport = list_widget.viewport()
        if viewport is None or viewport.width() <= 0 or viewport.height() <= 0:
            return
        count = list_widget.count()
        if count <= 0:
            return
        # indexAt/itemAt ограничивают обход только видимыми строками. Старый
        # цикл обходил все 2100 элементов на каждое движение полосы прокрутки.
        top_item = list_widget.itemAt(QPoint(10, 8))
        bottom_item = list_widget.itemAt(QPoint(10, max(8, viewport.height() - 8)))
        top_index = list_widget.row(top_item) if top_item is not None else max(
            0, list_widget.indexAt(QPoint(10, 0)).row()
        )
        bottom_index = list_widget.row(bottom_item) if bottom_item is not None else min(
            count - 1, top_index + max(1, viewport.height() // 66) + 2
        )
        top_index = max(0, top_index - 1)
        bottom_index = min(count - 1, max(top_index, bottom_index + 1))
        for index in range(top_index, bottom_index + 1):
            item = list_widget.item(index)
            row = list_widget.itemWidget(item) if item is not None else None
            if not isinstance(row, TrackRow):
                continue
            # Работаем с треком текущей видимой строки. Здесь нельзя использовать
            # переменную `track`: в этой функции она не определена и вызывала краш.
            track = row.track
            thumbnail = normalize_artwork_url(track.get("thumbnail", ""))
            if thumbnail:
                if row.thumbnail_label.property("requested_image") != thumbnail:
                    self.request_image(thumbnail, row.thumbnail_label)
            elif track.get("source") == "soundcloud":
                # Если в кэше нет обложки SoundCloud, пробуем получить метаданные
                # в фоновом потоке; сам интерфейс при этом не блокируется.
                self.queue_artwork_lookup(track)

    def queue_artwork_lookup(self, track):
        url = str(track.get("url") or "")
        if not url or url in self.artwork_pending_urls:
            return
        if self.artwork_failed_until.get(url, 0.0) > time.monotonic():
            return
        self.artwork_pending_urls.add(url)
        self.artwork_backlog.append(dict(track))
        self.pump_artwork_workers()

    def pump_artwork_workers(self):
        while len(self.artwork_workers) < self.artwork_max_workers and self.artwork_backlog:
            track = self.artwork_backlog.popleft()
            url = str(track.get("url") or "")
            if not url:
                continue
            worker = TrackArtworkWorker(
                track, self,
                cookies_from_browser=(self.soundcloud_browser
                                      if self.soundcloud_auth_mode == "browser" else "")
            )
            self.artwork_workers[url] = worker
            worker.metadata_ready.connect(self.on_track_artwork_metadata)
            worker.failed.connect(self.on_track_artwork_failed)
            worker.finished.connect(lambda u=url, w=worker: self.on_track_artwork_finished(u, w))
            worker.finished.connect(worker.deleteLater)
            worker.start()

    def on_track_artwork_metadata(self, url, metadata):
        url = str(url or "")
        updates = dict(metadata or {})
        if updates.get("thumbnail"):
            updates["thumbnail"] = normalize_artwork_url(updates["thumbnail"])
        found = False
        current_track_collection = [self.current_track] if isinstance(self.current_track, dict) else []
        requested_track_collection = [self.requested_track] if isinstance(self.requested_track, dict) else []
        for collection in (
            self.soundcloud_liked_tracks,
            list(self.favorites.values()),
            self.source_results.get("soundcloud", []),
            self.queue_tracks,
            current_track_collection,
            requested_track_collection,
        ):
            for track in collection:
                if isinstance(track, dict) and str(track.get("url") or "") == url:
                    track.update({key: value for key, value in updates.items() if value not in (None, "")})
                    found = True
        # Обновляем элементы списка и их TrackRow, включая уже добавленные в очередь.
        for list_widget in (self.source_list, self.youtube_likes_list,
                            self.soundcloud_likes_list, self.likes_list):
            for index in range(list_widget.count()):
                item = list_widget.item(index)
                track = item.data(Qt.ItemDataRole.UserRole)
                if not isinstance(track, dict) or str(track.get("url") or "") != url:
                    continue
                track.update({key: value for key, value in updates.items() if value not in (None, "")})
                item.setData(Qt.ItemDataRole.UserRole, dict(track))
                row = list_widget.itemWidget(item)
                if isinstance(row, TrackRow):
                    row.track.update(track)
                    if updates.get("artist"):
                        row._full_artist = str(updates["artist"])
                        row.artist_label.setText(row.artist_label.fontMetrics().elidedText(
                            row._full_artist, Qt.TextElideMode.ElideRight,
                            max(0, row.artist_label.contentsRect().width() - 3)))
                    if updates.get("title"):
                        row._full_title = str(updates["title"])
                        row.title_label.setText(row.title_label.fontMetrics().elidedText(
                            row._full_title, Qt.TextElideMode.ElideRight,
                            max(0, row.title_label.contentsRect().width() - 3)))
                    if hasattr(row, "duration_label") and updates.get("duration"):
                        row.duration_label.setText(human_time(updates["duration"]) or "—")
                    if (updates.get("thumbnail") and
                            row.thumbnail_label.property("requested_image") != updates["thumbnail"]):
                        self.request_image(updates["thumbnail"], row.thumbnail_label)
        for index in range(self.queue_list.count()):
            row = self.queue_list.itemWidget(self.queue_list.item(index))
            if isinstance(row, TrackRow) and str(row.track.get("url") or "") == url:
                row.track.update(updates)
                if updates.get("artist"):
                    row._full_artist = str(updates["artist"])
                    row.artist_label.setText(row.artist_label.fontMetrics().elidedText(
                        row._full_artist, Qt.TextElideMode.ElideRight,
                        max(0, row.artist_label.contentsRect().width() - 3)))
                if updates.get("title"):
                    row._full_title = str(updates["title"])
                    row.title_label.setText(row.title_label.fontMetrics().elidedText(
                        row._full_title, Qt.TextElideMode.ElideRight,
                        max(0, row.title_label.contentsRect().width() - 3)))
                if (updates.get("thumbnail") and
                        row.thumbnail_label.property("requested_image") != updates["thumbnail"]):
                    self.request_image(updates["thumbnail"], row.thumbnail_label)
        if found:
            self.save_soundcloud_likes()
            self.refresh_likes_status_only()
            if (str((self.current_track or {}).get("url") or "") == url
                    and updates.get("thumbnail")):
                self.show_cover(updates["thumbnail"])

    def on_track_artwork_failed(self, url, error):
        url = str(url or "")
        self.artwork_failed_until[url] = time.monotonic() + 900
        # Ошибка обложки не влияет на воспроизведение трека.
        logging.getLogger("aurora").info(f"[Music Player] Не удалось получить обложку SoundCloud: {error}")

    def on_track_artwork_finished(self, url, worker):
        if self.artwork_workers.get(url) is worker:
            self.artwork_workers.pop(url, None)
        self.artwork_pending_urls.discard(url)
        self.pump_artwork_workers()

    def set_pixmap_safe(self, label, image):
        try:
            side = max(1, min(label.width(), label.height()))
            if bool(label.property("circular_image")):
                label.setPixmap(circular_pixmap(image, side))
            else:
                label.setPixmap(rounded_pixmap(image, side, 13 if side >= 140 else 8))
        except RuntimeError:
            # Пользователь сменил вкладку, QLabel уже удалён Qt.
            pass

    def request_image(self, url, label):
        url = normalize_artwork_url(url)
        label.setProperty("requested_image", url or "")
        self.set_pixmap_safe(label, self.fallback_cover)
        if not url or not str(url).startswith(("https://", "http://")):
            return
        if url in self.pixmap_cache:
            self.pixmap_cache.move_to_end(url)
            if self.pixmap_cache[url] is not None:
                self.set_pixmap_safe(label, self.pixmap_cache[url])
            return
        if url in self.image_waiters:
            self.image_waiters[url].append(label)
        else:
            self.image_waiters[url] = [label]
            self.image_backlog.append(url)
        self.pump_images()

    def request_card_cover(self, url, card):
        url = normalize_artwork_url(url)
        if not url or not url.startswith(("https://", "http://")):
            return
        card.setProperty("requested_image", url)
        if url in self.pixmap_cache:
            self.pixmap_cache.move_to_end(url)
            card.set_cover(self.pixmap_cache[url])
            return
        if url in self.image_waiters:
            self.image_waiters[url].append(card)
        else:
            self.image_waiters[url] = [card]
            self.image_backlog.append(url)
        self.pump_images()

    def pump_images(self):
        while self.active_images < self.image_limit and self.image_backlog:
            url = self.image_backlog.popleft()
            self.active_images += 1
            request = QNetworkRequest(QUrl(url))
            request.setRawHeader(b"User-Agent", b"Mozilla/5.0")
            reply = self.network_manager.get(request)
            reply.finished.connect(lambda r=reply, u=url: self.image_finished(u, r))

    def image_finished(self, url, reply):
        pixmap = QPixmap()
        try:
            data = bytes(reply.readAll())
            if 0 < len(data) < 5_000_000 and pixmap.loadFromData(data):
                self.pixmap_cache[url] = pixmap
            else:
                self.pixmap_cache[url] = None
            self.pixmap_cache.move_to_end(url)
            while len(self.pixmap_cache) > 250:
                self.pixmap_cache.popitem(last=False)
            for label in self.image_waiters.pop(url, []):
                # Проверяем URL, чтобы старая загрузка не заменила новую обложку.
                try:
                    is_current = label.property("requested_image") == url
                except RuntimeError:
                    continue
                if is_current and self.pixmap_cache[url] is not None:
                    if isinstance(label, SpotifyPlaylistCard):
                        label.set_cover(pixmap)
                    else:
                        self.set_pixmap_safe(label, pixmap)
                    if label is getattr(self, "artist_avatar", None):
                        self._apply_artist_header_color(pixmap)
        finally:
            reply.deleteLater()
            self.active_images = max(0, self.active_images - 1)
            # LRU уже удерживает кэш в заданном размере, не сбрасывая все обложки сразу.
            self.pump_images()

    def show_cover(self, url):
        # Изображение текущего трека показывается только в нижней панели.
        for label in (self.bottom_cover,):
            if not url:
                label.setProperty("requested_image", "")
                self.set_pixmap_safe(label, self.fallback_cover)
            else:
                self.request_image(url, label)

    # ---------------------------------------------------------
    # Очередь. Она не исчезает при сворачивании правой колонки.
    # ---------------------------------------------------------

    def add_to_queue(self, track, play_now=False):
        self.queue_mode = "manual"
        self._soundcloud_queue_waiting = False
        self._soundcloud_queue_anchor_url = ""
        queued = dict(track)
        # Уникальный идентификатор позиции: одинаковые песни могут стоять
        # в очереди несколько раз, но удаление не собьёт текущий трек.
        queued["queue_id"] = uuid4().hex
        self.radio_mode_active = False
        self.queue_tracks.append(queued)
        self.append_queue_item(queued, len(self.queue_tracks) - 1)
        self.update_queue_count()
        if play_now:
            self.play_queue_index(len(self.queue_tracks) - 1)
        elif self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.prepare_next_track()

    def append_queue_item(self, queued, index):
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, index)
        item.setSizeHint(QSize(190, 64))
        self.queue_list.addItem(item)
        row = TrackRow(queued, compact=True)
        row.setCursor(Qt.CursorShape.PointingHandCursor)
        self.queue_list.setItemWidget(item, row)
        uid = queued.get("queue_id")
        row.remove_button.clicked.connect(lambda checked=False, u=uid: self.remove_queue_uid(u))
        # Обложка и название — кликабельные элементы TrackRow. Разрешаем
        # воспроизведение по одному клику и ищем позицию по queue_id, чтобы
        # перестановка/удаление строк не запускали неверный трек.
        row.play_requested.connect(
            lambda _track, u=uid: self.play_queue_index(self.index_for_uid(u))
        )
        self.set_pixmap_safe(row.thumbnail_label, self.fallback_cover)
        self.schedule_visible_artwork(self.queue_list)

    def refresh_queue_list(self):
        """Перерисовываем после удаления или смены порядка."""
        self.queue_list.clear()
        for index, track in enumerate(self.queue_tracks):
            self.append_queue_item(track, index)
        self.schedule_visible_artwork(self.queue_list)
        self.update_queue_count()
        if self.current_track is not None:
            self.current_queue_index = self.index_for_uid(self.current_track.get("queue_id"))
        else:
            self.current_queue_index = -1
        if self.requested_track is not None:
            self.requested_index = self.index_for_uid(self.requested_track.get("queue_id"))
        if 0 <= self.current_queue_index < self.queue_list.count():
            self.queue_list.setCurrentRow(self.current_queue_index)
        self.shuffle_future = None

    def index_for_uid(self, uid):
        if not uid:
            return -1
        return next((i for i, t in enumerate(self.queue_tracks)
                     if t.get("queue_id") == uid), -1)

    def remove_queue_uid(self, uid):
        index = self.index_for_uid(uid)
        if index >= 0:
            self.remove_queue_index(index)

    def remove_queue_index(self, index):
        if not (0 <= index < len(self.queue_tracks)):
            return
        uid = self.queue_tracks[index].get("queue_id")
        if self.requested_track and self.requested_track.get("queue_id") == uid:
            self.cancel_pending_request()
        del self.queue_tracks[index]
        self.shuffle_future = None
        self.refresh_queue_list()
        self.set_status("Трек удалён из очереди. Играющая музыка не прерывается.")
        if self.current_track is not None:
            QTimer.singleShot(0, self.prepare_next_track)

    def move_queue_index(self, index, step):
        other = index + step
        if not (0 <= index < len(self.queue_tracks) and 0 <= other < len(self.queue_tracks)):
            return
        self.queue_tracks[index], self.queue_tracks[other] = (
            self.queue_tracks[other], self.queue_tracks[index])
        self.shuffle_future = None
        self.refresh_queue_list()
        if self.current_track is not None:
            QTimer.singleShot(0, self.prepare_next_track)

    def open_queue_menu(self, point):
        item = self.queue_list.itemAt(point)
        if item is None:
            return
        index = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(index, int) or not 0 <= index < len(self.queue_tracks):
            return
        uid = self.queue_tracks[index].get("queue_id")
        menu = self.make_context_menu()
        menu.addAction("▶   Воспроизвести", lambda u=uid: self.play_queue_index(self.index_for_uid(u)))
        menu.addAction("×   Удалить из очереди", lambda u=uid: self.remove_queue_uid(u))
        queued_track = self.queue_tracks[index]
        if queued_track.get("source") != "local":
            menu.addAction("⬇   Скачать офлайн", lambda t=dict(queued_track): self.download_track(t))
        if queued_track.get("source") in ("youtube", "soundcloud"):
            menu.addAction("♫   Запустить радио по треку", lambda t=dict(queued_track): self.start_radio(t))
        menu.addSeparator()
        up = menu.addAction("↑   Переместить выше", lambda u=uid: self.move_queue_index(self.index_for_uid(u), -1))
        down = menu.addAction("↓   Переместить ниже", lambda u=uid: self.move_queue_index(self.index_for_uid(u), 1))
        up.setEnabled(index > 0)
        down.setEnabled(index < len(self.queue_tracks) - 1)
        menu.exec(self.queue_list.viewport().mapToGlobal(point))

    def update_queue_count(self):
        count = len(self.queue_tracks)
        self.queue_count.setText(f"{count} треков")

    def clear_queue(self):
        # Сохраняем уже воспроизводимый трек; новая очередь будет пустой.
        self.queue_mode = "manual"
        self._soundcloud_queue_waiting = False
        self._soundcloud_queue_anchor_url = ""
        self.cancel_pending_request()
        self.queue_tracks.clear()
        self._shuffle_history.clear()
        self.queue_list.clear()
        self.current_queue_index = -1
        self.shuffle_future = None
        self.radio_mode_active = False
        self.update_queue_count()
        self.set_status("Очередь очищена.")

    def on_queue_activated(self, item):
        index = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(index, int):
            self.play_queue_index(index)

    def play_queue_index(self, index):
        if not 0 <= index < len(self.queue_tracks):
            return
        self.queue_list.setCurrentRow(index)
        target = self.queue_tracks[index]
        target_url = str(target.get("url") or "")
        target_source = str(target.get("source") or "")
        self.play_track(target, index)
        # play_track() отменяет старый запрос и очищает старые индикаторы.
        # После этого отмечаем именно выбранный трек, пока готовится его поток.
        if isinstance(self.requested_track, dict) and self._key(self.requested_track) == target_url:
            for list_widget in (self.source_list, self.youtube_likes_list,
                                self.soundcloud_likes_list, self.likes_list, self.queue_list):
                for row_index in range(list_widget.count()):
                    row = list_widget.itemWidget(list_widget.item(row_index))
                    if not isinstance(row, TrackRow):
                        continue
                    row_track = row.track
                    if (str(row_track.get("url") or "") == target_url
                            and str(row_track.get("source") or "") == target_source):
                        row.set_loading(True)

    def search_neighbor_track(self, direction=1):
        """Соседний трек из выдачи; пропускает источники, которые только что упали при автопереходе."""
        current = self.requested_track or self.current_track
        if not isinstance(current, dict):
            return None
        source = current.get("source")
        if source not in ("youtube", "soundcloud"):
            return None
        tracks = self.source_results.get(source, [])
        if not tracks:
            return None
        url = current.get("url", "")
        index = next((i for i, track in enumerate(tracks)
                      if track.get("url") == url and track.get("source") == source), -1)
        if index < 0:
            return None
        failed = getattr(self, "_auto_failed_tracks", set())
        if self.shuffle_enabled:
            candidates = [track for track in tracks
                          if track.get("url") != url
                          and self.radio_track_key(track) not in failed]
            if candidates:
                return random.choice(candidates)
            return None
        for step in range(1, len(tracks) + 1):
            target = index + direction * step
            if self.repeat_mode == "all":
                target %= len(tracks)
            elif target < 0 or target >= len(tracks):
                break
            candidate = tracks[target]
            if candidate.get("url") == url:
                continue
            if self.radio_track_key(candidate) in failed:
                continue
            return candidate
        return None

    def play_candidate_track(self, track):
        """Проигрывает трек из результатов, добавляя его в очередь только при необходимости."""
        if not track:
            return
        self.radio_mode_active = False
        url = track.get("url", "")
        source = track.get("source", "")
        index = next((i for i, queued in enumerate(self.queue_tracks)
                      if queued.get("url") == url and queued.get("source") == source), -1)
        if index < 0:
            self.add_to_queue(track, False)
            index = len(self.queue_tracks) - 1
        self.play_queue_index(index)

    def play_next(self):
        # В режиме радио приоритет имеет очередь из радио-микса; в обычном режиме
        # можно переходить по соседним результатам поиска.
        if (not self.radio_mode_active
                and self.queue_mode not in ("soundcloud_likes", "youtube_likes", "supermix")
                and not self._is_youtube_likes_playback()):
            candidate = self.search_neighbor_track(1)
            if candidate is not None:
                self.shuffle_future = None
                self.play_candidate_track(candidate)
                return
        index = self.peek_next_index()
        if index is None:
            if self.queue_mode == "soundcloud_likes" and self._soundcloud_likes_loading:
                self._soundcloud_queue_waiting = True
                self.set_status("SoundCloud: загружаю следующую страницу лайков…", "soundcloud")
            elif self.radio_mode_active:
                self._radio_waiting_for_tracks = True
                self.maybe_refill_radio(force=True)
            return
        self.shuffle_future = None
        self.play_queue_index(index)

    def play_previous(self):
        if self.requested_track is None and self.player.position() > 5000:
            self.player.setPosition(0)
            return
        if (not self.radio_mode_active
                and self.queue_mode not in ("soundcloud_likes", "youtube_likes", "supermix")
                and not self._is_youtube_likes_playback()):
            candidate = self.search_neighbor_track(-1)
            if candidate is not None:
                self.shuffle_future = None
                self.play_candidate_track(candidate)
                return
        current = self.requested_index if self.requested_track is not None else self.current_queue_index
        if current > 0:
            self.shuffle_future = None
            self.play_queue_index(current - 1)
        elif self.queue_tracks and self.repeat_mode == "all":
            self.shuffle_future = None
            self.play_queue_index(len(self.queue_tracks) - 1)

    # ---------------------------------------------------------
    # Интернет-аудио: короткий кэш и подготовка следующего трека.
    # Время ожидания показываем отдельно для yt-dlp и Qt.
    # ---------------------------------------------------------

    def get_cached_stream(self, track_url):
        cached = self.stream_cache.get(track_url)
        if not cached:
            return None
        if time.monotonic() - cached["saved"] > self.stream_cache_ttl:
            self.stream_cache.pop(track_url, None)
            return None
        return cached

    def save_stream(self, track_url, stream_url, title):
        if not track_url:
            return
        self.stream_cache[track_url] = {
            "url": stream_url, "title": title, "saved": time.monotonic()
        }
        # Простой ограниченный кэш, чтобы память не росла без конца.
        if len(self.stream_cache) > 50:
            oldest = min(self.stream_cache, key=lambda k: self.stream_cache[k]["saved"])
            self.stream_cache.pop(oldest, None)

    def _key(self, track):
        return track.get("url", "") if track else ""

    def idle_slot(self):
        return 1 - self.active_slot

    def stop_fade(self):
        """Перед новым запросом завершаем старую анимацию переключения."""
        if not self.fade_timer.isActive():
            return
        self.fade_timer.stop()
        if self.fade_old_slot is not None:
            old = self.fade_old_slot
            self.players[old].stop()
            self.audio_outputs[old].setVolume(0.0)
            self.players[old].setSource(QUrl())
            self.fade_old_slot = None
        self.fade_started_at = None
        self.audio_outputs[self.active_slot].setVolume(self.volume)

    def _clear_loading_indicators(self):
        """Снимает индикатор загрузки со строк во всех списках приложения."""
        for list_widget in (
            getattr(self, "source_list", None),
            getattr(self, "youtube_likes_list", None),
            getattr(self, "soundcloud_likes_list", None),
            getattr(self, "likes_list", None),
            getattr(self, "queue_list", None),
        ):
            if list_widget is None:
                continue
            for index in range(list_widget.count()):
                row = list_widget.itemWidget(list_widget.item(index))
                if isinstance(row, TrackRow) and getattr(row, "_loading", False):
                    row.set_loading(False)

    def cancel_pending_request(self):
        """Отменяем запуск неактуального трека, оставляя текущий звук."""
        self._cancel_supermix()
        self.request_id += 1
        self.requested_track = None
        self.requested_index = -1
        self.stream_pending_track = None
        self.stop_fade()
        self.pending_media_timer.stop()
        if self.pending_slot is not None:
            slot = self.pending_slot
            self.pending_slot = None
            self.pending_media_url = None
            self.players[slot].stop()
            self.players[slot].setSource(QUrl())
            self.audio_outputs[slot].setVolume(0.0)
            self.standby_key = None
            self.standby_ready = False
        self._clear_loading_indicators()

    def prepare_next_track(self):
        """Находим следующую песню и прогреваем её вторым QMediaPlayer.

        Сначала yt-dlp получает временную ссылку в отдельном QThread,
        затем неактивный QMediaPlayer открывает источник БЕЗ воспроизведения.
        На Windows реальная буферизация может начаться только при play().
        """
        if self.requested_track is not None or self.pending_slot is not None:
            return
        if self.fade_timer.isActive():
            return
        if self.prefetch_worker is not None:
            return
        next_index = self.peek_next_index()
        if next_index is None or self.repeat_mode == "one":
            return
        track = self.queue_tracks[next_index]
        key = self._key(track)
        if not key or self.prefetch_failed_until.get(key, 0) > time.monotonic():
            return
        if self.standby_key == key and self.players[self.idle_slot()].source() != QUrl():
            return
        offline_path = self.offline_path_for(track)
        if offline_path:
            self.preload_in_qt(track, QUrl.fromLocalFile(offline_path))
            return
        if track.get("source") == "local":
            self.preload_in_qt(track, QUrl.fromLocalFile(key))
            return
        cached = self.get_cached_stream(key)
        if cached:
            self.preload_in_qt(track, QUrl(cached["url"]))
            return

        self.prefetch_target = key
        worker = StreamWorker(track, self, audio_quality=self.audio_quality,
                              **(self.youtube_auth_kwargs() if track.get("source") == "youtube" else {}))
        self.prefetch_worker = worker
        worker.stream_ready.connect(
            lambda stream, title, elapsed, k=key:
                self.prefetch_ready(k, stream, title, elapsed)
        )
        worker.failed.connect(lambda error, k=key: self.prefetch_failed(k, error))
        worker.finished.connect(self.prefetch_finished)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def preload_in_qt(self, track, media_url):
        """Загружаем источник в резервном проигрывателе, не включая звук."""
        if self.requested_track is not None or self.pending_slot is not None:
            return
        if self.fade_timer.isActive():
            QTimer.singleShot(120, self.prepare_next_track)
            return
        slot = self.idle_slot()
        player = self.players[slot]
        key = self._key(track)
        if self.standby_key == key and player.source() == media_url:
            return
        player.stop()
        self.audio_outputs[slot].setVolume(0.0)
        self.standby_key = key
        self.standby_ready = False
        self.standby_started = time.perf_counter()
        player.setSource(media_url)
        logging.getLogger("aurora").info(f"[Music Player] Предзагрузка Qt: {track.get('title', 'трек')}")

    def prefetch_ready(self, key, stream_url, title, elapsed):
        self.save_stream(key, stream_url, title)
        logging.getLogger("aurora").info(f"[Music Player] yt-dlp следующего трека: {elapsed:.1f} с")
        if self.requested_track is not None and self._key(self.requested_track) == key:
            # Пользователь уже выбрал именно трек, который готовился.
            if self.pending_slot is None:
                self.start_pending_media(QUrl(stream_url), "предзагруженная ссылка")
            return
        next_index = self.peek_next_index()
        if (self.requested_track is None and next_index is not None
                and self._key(self.queue_tracks[next_index]) == key):
            self.preload_in_qt(self.queue_tracks[next_index], QUrl(stream_url))

    def prefetch_failed(self, key, error):
        # Без ограничителя неудачный трек запускал бы бесконечные запросы.
        self.prefetch_failed_until[key] = time.monotonic() + 120
        logging.getLogger("aurora").info(f"[Music Player] yt-dlp предзагрузки: {error}")
        if self.requested_track is not None and self._key(self.requested_track) == key:
            self.start_stream_extraction(self.requested_track)

    def prefetch_finished(self):
        self.prefetch_worker = None
        self.prefetch_target = None
        # Если предзагрузка закончилась не тем ключом — можно готовить актуальный.
        if self.requested_track is None:
            QTimer.singleShot(0, self.prepare_next_track)

    def start_stream_extraction(self, track):
        """Запрос аудиоссылки не блокирует Qt и текущий звук."""
        key = self._key(track)
        if self.stream_worker is not None:
            if self.stream_target == key:
                self.set_status("Аудиоссылка для выбранного трека уже запрашивается…")
                return
            # Сохраняем последнюю выбранную песню. Текущий сетевой запрос нельзя
            # жёстко прервать внутри yt-dlp, но его результат уже будет отброшен.
            self.stream_pending_track = dict(track)
            self.stream_worker.cancel()
            self.set_status("Отменяю устаревший запрос и готовлю выбранный трек…")
            return
        self.stream_target = key
        self.set_status("Получаю ссылку на новый трек, предыдущий пока играет…")
        worker = StreamWorker(track, self, audio_quality=self.audio_quality,
                              **(self.youtube_auth_kwargs() if track.get("source") == "youtube" else {}))
        self.stream_worker = worker
        key = self.stream_target
        worker.stream_ready.connect(
            lambda stream, title, elapsed, k=key: self.stream_ready(k, stream, title, elapsed)
        )
        worker.failed.connect(lambda message, k=key: self.stream_error(k, message))
        worker.finished.connect(self.stream_finished)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def play_track(self, track, index):
        """Запоминаем запрос и подготавливаем музыку на другом QMediaPlayer."""
        self.cancel_pending_request()
        self.requested_track = dict(track)
        self.requested_index = index
        self.request_started = time.perf_counter()
        self.pending_refreshed = False
        key = self._key(track)
        if not key:
            self.set_status("В выбранном треке нет ссылки.")
            self.requested_track = None
            return

        offline_path = self.offline_path_for(track)
        if offline_path:
            self.requested_track["local_path"] = offline_path
            self.start_pending_media(QUrl.fromLocalFile(offline_path), "офлайн-файл")
            return
        if track.get("source") == "local":
            self.start_pending_media(QUrl.fromLocalFile(key), "локальный файл")
            return

        # Повторно используем предварительно ОТКРЫТЫЙ в Qt источник.
        standby = self.players[self.idle_slot()]
        if self.standby_key == key and not standby.source().isEmpty():
            self.start_pending_media(standby.source(), "предзагрузка Qt")
            return

        cached = self.get_cached_stream(key)
        if cached:
            self.start_pending_media(QUrl(cached["url"]), "кэш ссылки")
            return

        if self.prefetch_worker is not None and self.prefetch_target == key:
            self.set_status("Ожидаю аудиоссылку, которая уже предзагружается…")
            return
        self.start_stream_extraction(track)

    def stream_ready(self, key, stream_url, title, extraction_seconds):
        self.save_stream(key, stream_url, title)
        logging.getLogger("aurora").info(f"[Music Player] yt-dlp ({title}): {extraction_seconds:.1f} с")
        if self.requested_track is not None and self._key(self.requested_track) == key:
            self.start_pending_media(QUrl(stream_url), f"yt-dlp {extraction_seconds:.1f} с")

    def recover_auto_transition_failure(self, failed_track, failed_index=-1):
        """После ошибки следующего потока пробует следующий кандидат вместо остановки."""
        if not self._finish_transition_pending:
            return False
        failed_track = dict(failed_track or {})
        if failed_track.get("url"):
            self._auto_failed_tracks.add(self.radio_track_key(failed_track))
        if (0 <= failed_index < len(self.queue_tracks)
                and failed_index != self.current_queue_index
                and self.queue_tracks[failed_index].get("url") == failed_track.get("url")
                and self.queue_tracks[failed_index].get("source") == failed_track.get("source")):
            del self.queue_tracks[failed_index]
            self.refresh_queue_list()
        self._finish_transition_pending = False
        self._finish_guard_url = ""
        # Запускаем обработчик после возврата в event loop, чтобы текущий поток
        # продолжал играть, пока новый кандидат подготавливается.
        QTimer.singleShot(0, self.handle_track_finished)
        return True

    def stream_error(self, key, message):
        # Не прерываем старую композицию, если не удалось открыть следующую.
        if self.requested_track is not None and self._key(self.requested_track) == key:
            failed_track = dict(self.requested_track)
            failed_index = self.requested_index
            failed_url = str(failed_track.get("url") or "")
            failed_source = str(failed_track.get("source") or "")
            for list_widget in (self.source_list, self.youtube_likes_list,
                                self.soundcloud_likes_list, self.likes_list, self.queue_list):
                for row_index in range(list_widget.count()):
                    row = list_widget.itemWidget(list_widget.item(row_index))
                    if (isinstance(row, TrackRow) and getattr(row, "_loading", False)
                            and str(row.track.get("url") or "") == failed_url
                            and str(row.track.get("source") or "") == failed_source):
                        row.set_loading(False)
            auto_transition = self._finish_transition_pending
            self.requested_track = None
            self.requested_index = -1
            self.set_status("Не удалось получить аудиопоток. Предыдущий трек продолжает играть.")
            logging.getLogger("aurora").warning("Ошибка аудиопотока: %s", message)
            self.show_toast("Не удалось подготовить трек: " + str(message)[:180], 4500)
            if auto_transition:
                self.recover_auto_transition_failure(failed_track, failed_index)
        else:
            logging.getLogger("aurora").info(f"[Music Player] Старая ошибка извлечения: {message}")

    def stream_finished(self):
        self.stream_worker = None
        self.stream_target = None
        pending_track = self.stream_pending_track
        self.stream_pending_track = None
        if pending_track is not None:
            if (self.requested_track is not None
                    and self._key(self.requested_track) == self._key(pending_track)):
                self.start_stream_extraction(pending_track)
                return
        # Если пользователь во время yt-dlp выбрал другой трек — начнём его.
        if self.requested_track is not None and self.pending_slot is None:
            key = self._key(self.requested_track)
            cached = self.get_cached_stream(key)
            if cached:
                self.start_pending_media(QUrl(cached["url"]), "кэш")
            elif self.prefetch_worker is not None and self.prefetch_target == key:
                pass
            else:
                self.start_stream_extraction(self.requested_track)

    def start_pending_media(self, media_url, origin):
        """Начинаем новый трек без звука, ожидая фактического движения позиции.

        Пока Qt буферизует резервный поток, основной продолжает звучать.
        Только после готовности начинаем плавный переход громкости.
        """
        if self.requested_track is None or media_url.isEmpty():
            return
        self.stop_fade()
        slot = self.idle_slot()
        player = self.players[slot]
        self.pending_slot = slot
        self.pending_started = time.perf_counter()
        self.pending_media_url = media_url
        self.pending_ever_loaded = player.mediaStatus() in (
            QMediaPlayer.MediaStatus.LoadedMedia,
            QMediaPlayer.MediaStatus.BufferingMedia,
            QMediaPlayer.MediaStatus.BufferedMedia,
        ) and player.source() == media_url
        self.pending_position_seen = False
        self.pending_media_timer.start(self.PENDING_MEDIA_TIMEOUT_MS)
        self.request_origin = origin
        self.audio_outputs[slot].setVolume(0.0)
        if player.source() != media_url:
            player.stop()
            self.standby_key = None
            self.standby_ready = False
            player.setSource(media_url)
        # Запускаем сразу, не ожидая LoadedMedia; звук переключится по движению позиции.
        if self.pending_slot != slot or self.requested_track is None:
            return
        player.play()
        if self.pending_slot == slot:
            self.set_status("Загружаю звук на втором плеере; предыдущий продолжает играть…")
        logging.getLogger("aurora").info(f"[Music Player] Qt запускает второй поток ({origin})")

    def on_pending_media_timeout(self):
        """Ограничивает ожидание Qt; обработчик ошибки сохраняет старый трек."""
        if self.pending_slot is None or self.requested_track is None:
            return
        self.on_slot_error(
            self.pending_slot, QMediaPlayer.Error.ResourceError,
            "Новый трек не начал воспроизведение за отведённое время. Попробуй ещё раз."
        )

    def on_slot_position(self, slot, position):
        """Отслеживает позицию обоих плееров и безопасно запускает автопереход."""
        if slot == self.pending_slot:
            if (position > 0 and not self.pending_position_seen
                    and self.players[slot].source() == self.pending_media_url):
                self.pending_position_seen = True
                elapsed = time.perf_counter() - (self.request_started or time.perf_counter())
                qt_elapsed = time.perf_counter() - (self.pending_started or time.perf_counter())
                logging.getLogger("aurora").info(f"[Music Player] Новый поток начал менять позицию: всего {elapsed:.1f} с; Qt: {qt_elapsed:.1f} с")
                self.commit_switch(elapsed, qt_elapsed)
            return
        if slot != self.active_slot:
            return
        if not self.is_seeking:
            self.seek_slider.setValue(position)
        self.position_label.setText(self.format_position(position))

        # Пополняем радио заранее, пока текущая композиция ещё звучит.
        if self.radio_mode_active:
            now = time.monotonic()
            if now - self._last_radio_refill_check > 4.0:
                self._last_radio_refill_check = now
                self.maybe_refill_radio()

        duration = self.player.duration()
        playing = self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        current_url = str((self.current_track or {}).get("url", ""))
        near_end = duration > 0 and position > 0 and 0 <= duration - position < 800
        if (playing and near_end and current_url
                and self.requested_track is None and self.pending_slot is None
                and not self._finish_transition_pending
                and current_url != self._finish_guard_url
                and self._has_next_for_finish()):
            self._finish_transition_pending = True
            self._finish_guard_url = current_url
            # Не ставим старую песню на паузу заранее: извлечение следующего потока
            # может занять секунды. Два плеера сохраняют звук до готовности нового.
            QTimer.singleShot(0, self.handle_track_finished)

    def _has_next_for_finish(self):
        if self.repeat_mode in ("all", "one"):
            return self.current_track is not None or bool(self.queue_tracks)
        if self.queue_mode == "soundcloud_likes" and self._soundcloud_likes_loading:
            return True
        if self.queue_mode == "supermix" or self._is_youtube_likes_playback():
            return self.peek_next_index() is not None
        if self.radio_mode_active:
            return self.peek_next_index() is not None or bool(self.current_track)
        return self.search_neighbor_track(1) is not None or self.peek_next_index() is not None

    def on_slot_duration(self, slot, duration):
        if slot != self.active_slot:
            return
        self.seek_slider.setRange(0, max(0, duration))
        self.seek_slider.setEnabled(duration > 0 and self.player.isSeekable())
        self.duration_label.setText(self.format_position(duration))

    def on_slot_status(self, slot, status):
        if slot == self.pending_slot:
            if status in (QMediaPlayer.MediaStatus.LoadedMedia,
                          QMediaPlayer.MediaStatus.BufferingMedia,
                          QMediaPlayer.MediaStatus.BufferedMedia):
                self.pending_ever_loaded = True
            elif status == QMediaPlayer.MediaStatus.StalledMedia:
                self.set_status("Новый поток ждёт данные; старая музыка продолжает играть…")
        elif slot != self.active_slot:
            if status in (QMediaPlayer.MediaStatus.LoadedMedia,
                          QMediaPlayer.MediaStatus.BufferingMedia,
                          QMediaPlayer.MediaStatus.BufferedMedia):
                if self.standby_key is not None:
                    self.standby_ready = True
            return
        else:
            if status == QMediaPlayer.MediaStatus.EndOfMedia:
                # Если радио уже догрузило новые треки, переходим к ним даже при guard
                # от ранней проверки позиции. В остальных режимах guard блокирует дубль.
                current_url = str((self.current_track or {}).get("url", ""))
                radio_ready = (self.radio_mode_active and self._radio_waiting_for_tracks
                               and self.peek_next_index() is not None)
                likes_waiting = (self.queue_mode == "soundcloud_likes"
                                 and self._soundcloud_queue_waiting)
                youtube_likes_ready = (
                    self._is_youtube_likes_playback() and self.peek_next_index() is not None
                )
                if (self.requested_track is None and self.pending_slot is None
                        and not self._finish_transition_pending
                        and (radio_ready or likes_waiting or youtube_likes_ready
                             or self._is_youtube_likes_playback()
                             or current_url != self._finish_guard_url)
                        and (self.queue_tracks or self.current_track is not None)):
                    self._finish_transition_pending = True
                    self._finish_guard_url = current_url
                    QTimer.singleShot(0, self.handle_track_finished)
            elif status == QMediaPlayer.MediaStatus.StalledMedia:
                self.set_status("Буферизация текущего трека…")

    def on_slot_playback_state(self, slot, state):
        if slot != self.active_slot:
            return
        self.play_button.setIcon(control_icon(
            "pause" if state == QMediaPlayer.PlaybackState.PlayingState else "play", "#FFFFFF"
        ))
        self.update_playing_row_highlight()

    def commit_switch(self, elapsed, qt_elapsed):
        """Второй плеер уже начал проигрывать — можно переключать звук."""
        if self.pending_slot is None or self.requested_track is None:
            return
        self.pending_media_timer.stop()
        new = self.pending_slot
        old = self.active_slot
        self.active_slot = new
        self.player = self.players[new]
        self.audio_output = self.audio_outputs[new]
        self.current_track = self.requested_track
        if self.shuffle_enabled and isinstance(self.current_track, dict):
            uid = self.current_track.get("queue_id")
            if uid:
                self._shuffle_history.append(uid)
        self._finish_transition_pending = False
        self._finish_guard_url = ""
        self._auto_failed_tracks.clear()
        self.current_queue_index = self.requested_index
        self.requested_track = None
        self.requested_index = -1
        self.pending_slot = None
        self.pending_media_url = None
        self.standby_key = None
        self.standby_ready = False
        self.last_switch_seconds = elapsed
        self.shuffle_future = None

        title = self.current_track.get("title") or "Без названия"
        artist = self.current_track.get("artist") or ""
        self.bottom_title.setText(title)
        self.bottom_title.setToolTip(title)
        self.bottom_artist.setText(self.bottom_artist.fontMetrics().elidedText(
            artist, Qt.TextElideMode.ElideRight, 145))
        self.bottom_artist.setToolTip(artist)
        self.show_cover(self.current_track.get("thumbnail", ""))
        self.update_bottom_track_actions()
        for list_widget in (self.source_list, self.youtube_likes_list,
                            self.soundcloud_likes_list, self.likes_list, self.queue_list):
            for row_index in range(list_widget.count()):
                row = list_widget.itemWidget(list_widget.item(row_index))
                if isinstance(row, TrackRow) and getattr(row, "_loading", False):
                    row.set_loading(False)
        if 0 <= self.current_queue_index < self.queue_list.count():
            self.queue_list.setCurrentRow(self.current_queue_index)
        self.on_slot_position(new, self.player.position())
        self.on_slot_duration(new, self.player.duration())
        self.on_slot_playback_state(new, self.player.playbackState())
        self.update_playing_row_highlight()
        QTimer.singleShot(0, self.ensure_following_track_prepared)
        QTimer.singleShot(0, self.prepare_next_track)
        self.set_status(f"Играет: {title}")

        # Делаем перекрытие заданной длительности только для играющего старого трека.
        # Для остановленного или пустого слота пропускаем этот переход.
        self.fade_old_slot = (
            old if (not self.players[old].source().isEmpty()
                    and self.players[old].playbackState() == QMediaPlayer.PlaybackState.PlayingState)
            else None
        )
        self.fade_started_at = None
        if self.fade_old_slot is None:
            self.fade_timer.stop()
            self.players[old].stop()
            self.audio_outputs[old].setVolume(0.0)
            self.players[old].setSource(QUrl())
            self.audio_outputs[new].setVolume(self.volume)
        else:
            self.fade_active_duration_ms = self.fade_duration_ms
            self.fade_started_at = time.monotonic()
            self.fade_timer.start()

    def _fade_progress(self):
        if self.fade_started_at is None:
            return 1.0
        elapsed_ms = (time.monotonic() - self.fade_started_at) * 1000
        return max(0.0, min(1.0, elapsed_ms / self.fade_active_duration_ms))

    def fade_step(self):
        if self.fade_old_slot is None:
            self.fade_timer.stop()
            return
        progress = self._fade_progress()
        self.audio_outputs[self.active_slot].setVolume(self.volume * progress)
        self.audio_outputs[self.fade_old_slot].setVolume(self.volume * (1 - progress))
        if progress >= 1:
            old = self.fade_old_slot
            self.fade_old_slot = None
            self.fade_started_at = None
            self.fade_timer.stop()
            self.players[old].stop()
            self.players[old].setSource(QUrl())
            self.audio_outputs[old].setVolume(0.0)
            # Когда бывший основной плеер освободился — предзагрузим следующую.
            QTimer.singleShot(0, self.prepare_next_track)

    def on_slot_error(self, slot, error, message):
        if error == QMediaPlayer.Error.NoError:
            return
        logging.getLogger("aurora").info(f"[Music Player] Ошибка Qt слота {slot}: {message}")
        if slot == self.pending_slot:
            self.pending_media_timer.stop()
            self.pending_slot = None
            self.pending_media_url = None
            self.players[slot].stop()
            self.players[slot].setSource(QUrl())
            self.audio_outputs[slot].setVolume(0.0)
            self.standby_key = None
            self.standby_ready = False
            track = self.requested_track
            if isinstance(track, dict):
                failed_url = str(track.get("url") or "")
                failed_source = str(track.get("source") or "")
                for list_widget in (self.source_list, self.youtube_likes_list,
                                    self.soundcloud_likes_list, self.likes_list, self.queue_list):
                    for row_index in range(list_widget.count()):
                        row = list_widget.itemWidget(list_widget.item(row_index))
                        if (isinstance(row, TrackRow) and getattr(row, "_loading", False)
                                and str(row.track.get("url") or "") == failed_url
                                and str(row.track.get("source") or "") == failed_source):
                            row.set_loading(False)
            if track and track.get("source") != "local" and not self.pending_refreshed:
                self.pending_refreshed = True
                self.stream_cache.pop(self._key(track), None)
                self.set_status("Поток отклонён Qt. Запрашиваю свежую ссылку…")
                self.start_stream_extraction(track)
                return
            failed_track = dict(track or {})
            failed_index = self.requested_index
            auto_transition = self._finish_transition_pending
            self.requested_track = None
            self.requested_index = -1
            if auto_transition:
                self.set_status("Не удалось открыть следующий трек; автоматически пробую следующий вариант.")
                self.recover_auto_transition_failure(failed_track, failed_index)
            else:
                self.set_status("Новый трек не удалось открыть, старая музыка продолжает играть.")
                self.show_toast(message or "Неподдерживаемый аудиопоток", 4500)
            return
        if slot != self.active_slot:
            # Ошибка предзагрузки — ничего не ломаем в основном плеере.
            if self.standby_key is not None:
                self.stream_cache.pop(self.standby_key, None)
                self.prefetch_failed_until[self.standby_key] = time.monotonic() + 120
            self.standby_key = None
            self.standby_ready = False
            self.players[slot].setSource(QUrl())
            return
        if self._finish_transition_pending:
            failed_track = dict(self.requested_track or self.current_track or {})
            failed_index = (self.requested_index if self.requested_track is not None
                            else self.current_queue_index)
            self.set_status("Ошибка аудио при автопереходе; пробую следующий трек.")
            self.recover_auto_transition_failure(failed_track, failed_index)
            return
        self.set_status("Ошибка воспроизведения текущего трека.")
        self.show_toast(message or "Ошибка воспроизведения", 4500)

    def set_volume(self, value):
        self.volume = max(0.0, min(1.0, value / 100.0))
        if hasattr(self, "volume_value_label"):
            self.volume_value_label.setText(f"{value}%")
        if self.fade_timer.isActive() and self.fade_old_slot is not None:
            progress = self._fade_progress()
            self.audio_outputs[self.active_slot].setVolume(self.volume * progress)
            self.audio_outputs[self.fade_old_slot].setVolume(self.volume * (1.0 - progress))
        else:
            self.audio_outputs[self.active_slot].setVolume(self.volume)
            self.audio_outputs[self.idle_slot()].setVolume(0.0)

    def toggle_playback(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        elif not self.player.source().isEmpty():
            duration = self.player.duration()
            if duration > 0 and self.player.position() >= duration - 300:
                self.player.setPosition(0)
                self._finish_guard_url = ""
                self._finish_transition_pending = False
            self.player.play()
        elif self.requested_track is not None:
            self.set_status("Новый трек ещё подготавливается…")
        elif 0 <= self.current_queue_index < len(self.queue_tracks):
            self.play_queue_index(self.current_queue_index)
        else:
            QMessageBox.information(self, "Music Player", "Сначала выбери трек одним щелчком по строке или нажми ▶.")

    def stop_all(self):
        self.cancel_pending_request()
        for player, output in zip(self.players, self.audio_outputs):
            player.stop()
            output.setVolume(0.0)
        self.audio_outputs[self.active_slot].setVolume(self.volume)
        self.play_button.setIcon(control_icon("play", "#FFFFFF"))
        self.set_status("Воспроизведение остановлено.")

    def seek_pressed(self):
        self.is_seeking = True

    def seek_released(self):
        if self.player.isSeekable():
            self.player.setPosition(self.seek_slider.value())
        self.is_seeking = False

    @staticmethod
    def format_position(milliseconds):
        total = max(0, int(milliseconds) // 1000)
        minutes, seconds = divmod(total, 60)
        hours, minutes = divmod(minutes, 60)
        return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"

    def closeEvent(self, event):
        # В обычном режиме закрытие окна скрывает плеер в трей и не прерывает звук.
        if not self._force_exit and self.minimize_to_tray and self.tray_icon is not None:
            self.save_preferences()
            self.hide()
            self.tray_icon.show()
            if not self._tray_notice_shown:
                self.tray_icon.showMessage(
                    "Music Player работает в фоне",
                    "Музыка продолжает играть. Открой плеер через значок в системном трее.",
                    QSystemTrayIcon.MessageIcon.Information, 2500
                )
                self._tray_notice_shown = True
            event.ignore()
            return

        # При полном выходе не уничтожаем работающий QThread: yt-dlp завершит запрос,
        # а _poll_app_exit закроет окно после окончания фоновых операций.
        working = [worker for worker in self.findChildren(QThread) if worker.isRunning()]
        if working and self._force_exit:
            for worker in working:
                if hasattr(worker, "cancel"):
                    try:
                        worker.cancel()
                    except RuntimeError:
                        pass
            event.ignore()
            QTimer.singleShot(250, self._poll_app_exit)
            return
        if working:
            answer = QMessageBox.question(
                self, "Завершение запроса", "Сейчас идёт поиск. Выйти всё равно?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer == QMessageBox.StandardButton.Yes:
                self._force_exit = True
                QTimer.singleShot(0, self.request_app_exit)
            event.ignore()
            return
        self.fade_timer.stop()
        self.pending_media_timer.stop()
        self.save_preferences()
        for player in self.players:
            player.stop()
        if self.tray_icon is not None:
            self.tray_icon.hide()
        event.accept()


def main():
    setup_logging()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    family = setup_font(app)
    window = MusicPlayer()
    window.setProperty("fontFamily", family)
    media_filter = WindowsMediaKeyFilter(window) if sys.platform == "win32" else None
    if media_filter is not None:
        app.installNativeEventFilter(media_filter)
    window.show()
    try:
        code = app.exec()
    finally:
        if media_filter is not None:
            app.removeNativeEventFilter(media_filter)
    sys.exit(code)


if __name__ == "__main__":
    main()
