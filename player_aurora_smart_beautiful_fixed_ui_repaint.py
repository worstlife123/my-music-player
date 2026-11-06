# Music Player Green Edition — Spotify-inspired redesign, artist profiles and track radio.
# Пока новый трек запускается в тихом плеере, старый продолжает играть.
# Когда позиция нового потока начинает двигаться, звук плавно переключается.
# Inter с кириллицей включён в fonts/ под лицензией SIL OFL 1.1.

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
import ssl
import base64
import struct
import unicodedata
import configparser
from uuid import uuid4
from collections import deque, OrderedDict
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn
from urllib.error import HTTPError, URLError
from urllib.parse import quote, quote_plus, urljoin, urlsplit, urlunsplit
from urllib.request import HTTPSHandler, Request, build_opener

try:
    import requests
except ImportError:
    requests = None


def _ensure_python_runtime():
    """Если скрипт запущен через системный Python без установленного PyQt6,
    автоматически переключается на локальный .build-venv или доустанавливает зависимости."""
    if getattr(sys, "frozen", False) or "unittest" in sys.modules:
        return
    root_dir = Path(__file__).resolve().parent
    for venv_name in (".build-venv", ".venv", "venv"):
        candidate = (
            root_dir / venv_name / "Scripts" / "python.exe"
            if sys.platform == "win32"
            else root_dir / venv_name / "bin" / "python"
        )
        if candidate.is_file() and candidate.resolve() != Path(sys.executable).resolve():
            try:
                probe = subprocess.run(
                    [str(candidate), "-c", "import PyQt6, yt_dlp, requests"],
                    capture_output=True,
                    timeout=10,
                )
                if probe.returncode == 0:
                    raise SystemExit(subprocess.call([str(candidate), str( Path(__file__).resolve() ), *sys.argv[1:]]))
            except SystemExit:
                raise
            except Exception:
                pass
    try:
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", "--upgrade",
            "PyQt6>=6.8,<7", "yt-dlp[default]", "ytmusicapi>=1.12,<2", "certifi", "requests",
        ])
    except Exception:
        pass


try:
    from PyQt6.QtCore import Qt, QThread, QUrl, QSize, QRect, QRectF, QTimer, QSettings, QPointF, QPoint, QEvent, QEasingCurve, QPropertyAnimation, QVariantAnimation, pyqtSignal, pyqtProperty, QStandardPaths, QAbstractNativeEventFilter, QBuffer, QIODevice, QSaveFile, QSignalBlocker, QT_VERSION_STR, QObject, QMimeData
except ImportError:
    _ensure_python_runtime()
    from PyQt6.QtCore import Qt, QThread, QUrl, QSize, QRect, QRectF, QTimer, QSettings, QPointF, QPoint, QEvent, QEasingCurve, QPropertyAnimation, QVariantAnimation, pyqtSignal, pyqtProperty, QStandardPaths, QAbstractNativeEventFilter, QBuffer, QIODevice, QSaveFile, QSignalBlocker, QT_VERSION_STR, QObject, QMimeData

if requests is None:
    try:
        import requests
    except ImportError:
        requests = None

from PyQt6.QtGui import (
    QShortcut, QKeySequence, QBrush, QColor, QFont, QFontDatabase, QLinearGradient,
    QPainter, QPen, QPixmap, QPalette, QIcon, QPolygonF, QPainterPath, QDesktopServices, QFontMetrics, QRadialGradient, QImageReader, QImage, QDrag,
)
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkDiskCache
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox,
    QPushButton, QSizePolicy, QSlider, QVBoxLayout, QWidget,
    QDialog, QTabWidget, QWidgetAction, QCheckBox, QFormLayout, QStyle, QStyleOptionSlider, QStackedWidget, QStackedLayout, QGraphicsOpacityEffect, QGraphicsDropShadowEffect, QGridLayout, QComboBox, QScrollArea, QSystemTrayIcon, QTextEdit, QPlainTextEdit, QAbstractSpinBox,
)


def YoutubeDL(*args, **kwargs):
    """Load the extraction engine in its worker, without delaying the first window."""
    from yt_dlp import YoutubeDL as Downloader
    return Downloader(*args, **kwargs)

_SMOKE_DIRECTORY = None
APP_VERSION = "0.2.0"
GITHUB_REPO = "worstlife123/my-music-player"


APP_USER_MODEL_ID = "AuroraLocal.MusicPlayer"
_APP_ICON = None
_CUSTOM_BRAND_PIXMAP = None
_WIN32_HICONS = None

_CUSTOM_BRAND_ICON_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAPoAAAD6CAMAAAC/MqoPAAAAhFBMVEUAAAAGAAAMAAASAAAYAAAeAAAkAAAqAAAwAAAwBgY2AAA8AAA8GBhCAABIAABOAABU"
    "AABaAABgAABmAABsAAByAAB4AAB+AACEAACKAACQAACWAACcAACiAACoAACuAAC0AAC6AADAAADABgbGAADMAADSAADYAADeAADkAADwAAD8/Pw/QnToAAA0"
    "dElEQVR42u29h4LcuA4tSFLxSaucM8UlVbPv/z9wASqUVF0d3G57PNfNudepiyWBAIGDQJCQ7/E9vsf3+B7f43t8j+/xPb7H9/gebw1KGd3G30b5LPgshJi5"
    "av420oN6KYPY71Tm/X0iX80W8WX8V273dopESujfSHosW2n9lUyPVEi60fgLKQ8VCDsbO/bXmXW+SA62bVaq/ttID8MwwhFG3t+p6f4qbjPXj9M0q9pjVGma"
    "xp7zPwxoqePFZT9zIRUOeYz1r4Lzrow9+3+NbOYX7SQEUgiaDYc4jf0fYBGEGJvc+19R+maUD7MEojV9cmU4uC185sPA8Xdk/QL/iouAn5Bznwf/efKdtJ2V"
    "JhtIWqSYmjqNHNs20Wvdd4Jl226cNS3shWX/rOJN/B8WfjvtxUqK0pyMXWSl4YSg18pu1XFd15Xw18DGHzE3LnYJgTmiS/6TONeMV7pRgKcmBQ5SOyh6kOh5"
    "aru+r/th6IeuLKq2a/CfBW9z36YoKQ2X21TRh/81pOvWs355YF0fA+uMqBmBur4IbNcKy7YdhhEH/Nb3TeoZzLajcoQVGOuQocAMOBep55Xz36HbiAepVrpr"
    "UFdGXM9irlMfZdrJe15nIdBqwDCZ6YZJOUnJiwD3vuFnNcgFks/CdhUbJfvov6H0rHyCnQ1vLFogwMlHyevQ0TrNLsex8ECpJVXdcRxDXeeha9l+Pi4SP68B"
    "QNxwMaQWUN+JlfVj+ufLvZnP28tmJq6CHDJ3+5HfzqVv+DmI8qItPA6wdaD4u8xnbjrdRG5uH/ZgyfRXZBOyXqopM/5wwjWXQDd7hMVcv7xmJNAy8txyy93U"
    "iRXCqM3aL2quPcOrlSpNsrkzuHAjCELQr9uH/8Gcp9m8Eg6vb7dyzu+G2e5FasWjJhUVNxIuGrBxXOk10JqBF7ZZKJGczGMxixpYX6+fmJI/NfYwrYTnjISj"
    "av0Tji1lYSfTbrC6AslttUCwVAo5lHylTTauWd568/ytvewDYharOI3Bn2jOWlBuQs05owkX5RmLeHx0w3ERq+4DkBapWTZ0A3SRFCNlsLdROSrV2PYg3Qsy"
    "qiUPiVni6kj4+Z/mn8AmnwGMlwaJ5/mskaJuFLnbLkCXRJHGf2sB0d4/UkuJvGRBi8QpWbJkrnPNXrbG6IHnPCImiD0sjkj/KO/W55ojrUUiIRJ8NTfdftQP"
    "LktgXUCZT+lqnukkVAa6jKUlroQrVL5qNqcGsQB95rth1FEdv3OOpeUBKJBV6t0/h+XVqoQ8WAKpyaMk+/822vuMtFqt8XjHJSbseNQE1aKQ+XS6555AuFEf"
    "zCWpUCyyf7K7XKnRIaFeY5n/IYz3Ub1JkRKrV/kux6mS4UZ69Y/QEP3Qexb81cXIpOASJbq/k85KrfxvPanxm3o+3ok0KwWqMZOoUoY/gfFsfRd4qRwF/tji"
    "PJf2Sjrz+kWjl3bLrjHgK65LuSwT01wvtx8kaOukrKuY1DDbFAEPzy5wr1JiD3ql/307B5xeX8Tjs3/W6jOpZmRcNxWFGwttvmWjgToBPFcgpXG27XVNh5mO"
    "euPMrp3nBcpDzEk5Xh4XickmqV7sxvjX9Ru8RW/Bvi0u+8+bGRk73L1+EFeRWa52GdwUlxLQDdw8aXgQf1M7K2gFGiNUfV4gdOtqWJer38bqpSA2bjHF/1Wh"
    "T7VnlRNnnuE9jO6A4MSBVzZFscG8oneMSmoop+RYNHKW3W7XYxCIsplXoKd4wNply75SsGhkvGcomF5cX3CLlLiQIvr3tnmNwj57JFtKpjU3euerHjcECKyr"
    "4g2PB1NtmjnXeE5o10X1mp1Gqf+i43Jg9xMjlsMOWlzcCKHcBZsN2c74lIQChb78t3yVXgu7wYZNmQMwi0sA3eiY0xmTKrHyDtU91w5K9bJ7L+CvFXmjMbz+"
    "F6WG2AomER8bJxXzFJs7cGfdYeli2VJrxKe3/4ojb+tnl8SVGnOH+MvQEBa14GszukpjKcy7bZJ9ZDpJv8akNZzfvTgMQ5aBlUzoABxjzFkx83m1b6yfxKHt"
    "rXG2KeIbdcH7vwuzc5S4hCRLrvclcJ4SRyHB9gwgbFpZ1I93Woycyz50rRhDdBh81ckHFAOMygUA1dMzE/Weockw21raR3e+azxaLSFYU9hv/Ldjeh/ZJnxQ"
    "1psvNegVyAUjzjTC6/T5Kqb8nEilHmwI3mSB78dpWVdlWZVJ5Lt+0cFG8a4YLZzXoA3ylfaceeK8MPFSghuEuuY3h+5CjJwAO1aWaNHuNKVTFS8VWwHsui9k"
    "9hiiribBx7GuizRJ0rLsRj53uf8Cm5b9XaH2t5gk/Cp2ooP/I6jwfjflajRNPpp7hjhdsYevxGqaNq7DZ5eXNsiK8wbFfcFIVZM/DzjzO37vOfdI1d5RA06A"
    "pzMbGCAvWOp3UD4Yljgp2F0cmw1+ddX+k7w7b2AvyTAkCeprH5h86qo0dq7a2hH2Qflog8EYj6Xwlb9au9mwUOVI7/dSTl2F1BkrNiVMrGtvitVlq7qXNiHA"
    "SPuaZMXMxJZohT8LzLeKeciDu9KKOd0pF9QVBtmYG8Wm3CSKdtIyJ7l6Q79jeCvl3goo/F0v70xJVnuW91f445fDGpTTiRUwWc2eXx/hb3pB9I/63F1J7jex"
    "of2tAewOCn+lr5jGu+RX0mIj0P579Lwj0JwC5RtKNTIuKnhyu0OrQb9ZPpwUe1ByTKQi6WOZxe7j3ja9OKtHTTogu6nQ3ny4YbhhrEg+wo5aZyW3/qQRS+A7"
    "yPxvsXE2PmhgLlJO15eh4SB7N58O/OmD7rvrY6cYV5J4m3kbAmGO67pBGIY+/L5vchttHObYAdhl1o5eJ9blpG1IOu2MvlCJtKOu+/VVaChekps2UE5JePhf"
    "XgOYev9LibvUVxt6b3XQSYzFmjI3w7TsuADlvtxu+D/Q8oK3RRrodzciTEPhhNrXj5sMNBbwv2LdQbGa9pVqzE3mrRkEsfvVkZsW0OtsW7LEKFR6u6+1UYi5"
    "sLZQRImZVngVFiLDpRxLZ88oyRuQ2jdNgRU0YYz55qbBhMwieR3pBJVfT3rj9z5hFZAHihM8l3Xvu6rh6zONadhsimBo3391EVoBlEuXifUx2djfI6t0rnrZ"
    "aTMTbto9HjXDG+Q3C2uuyYs96yV/qO3GNVe3Zap8vWSdlpVBK/XQpCokAr1A8IPtVd2x4Z9k14OcBqh6819JOfrW8BYjKBr8D7T4MB3WGITSa+R0RB9DTTjX"
    "ohA2YlFjAUQcxAId4KucjwJQMypgeUSFBNulJr7Xa0lTw9ThvLGHJS61xRum7NiEA0mQJ8EvVu456XaXJOu1GtqhS69D5vOcbCkJHX82MH003VQfOxuNYLu3"
    "PyV3GLankZmbD8ttRC1nFeDRSllbR9iHNJwhPIzBg5WsPbhsghSWeif+KsoNUHGqAUfUIlGaZXk69Nql2t46XXU6TTMMHUv4LM8YJljVbcoPH4MmicVQ2+VN"
    "D3q5rzNMLbvNCZC5Ob/JEphslqA81ZyiXolmkLJVuYc+6RZ+h8rAE5WSXlueX0R6o+BdabR4JLzJkQ+9dlEO2l1xBGS9CT6KWUfq9zfVnQUxKb08DUcphjaP"
    "46RoRymHKGyOIwEGRq7CfllaIN6qUdsPsHBJS0K1S0nDY07ak16DHzGwur8qbKO3k20rfMlc3bm00852FwpYvgWgvH6R13oQSpnfLrJ0DGI5ru/C74YH9G0F"
    "0jSMm/X13UapFpjsDUoH+VG57xmd8p/YFnSzdpH+LZeGhzvsl2x3G2NoMd3873wJTrZ+pZ2vnLN7eNkZbJvdLArzjuZFDLt/5oiacY+wXVfLNRGjybyFYIqC"
    "BFswxgHiwbbRFKW+M8m4O0TlPGW2NFJNs7/sMRGSAW/4L6i5or3e6O2u1TIVPtLetWuoHD7YWoRlYmlcHZnKzwE9kVCnVaovAhdHWAyLqmya3xqdssrTqNnl"
    "JGhvc8KIi2vJfbY9uVR20RnC1vDOluUe0ylxu6v2F8Sd8fEsBkXDPBg2yy+0o4LxI235QTpAMt3hNmnBoBG7Z15tMZpGc+PZOaRm52IpqSNGC9SZF5sG29lu"
    "h/zWgUHAHbQfEEoXH/1g4fjgJtvi2N3e4ptogeJfYNfALTYwPAyeGxbxA5ZbabdtSgzer/sd0B6mBWmuVLaasDTcAuh6u7YkUC+TRixTYLYHcTVOtePZtFIy"
    "wVSHnGF5dGAKFjThbHYdAVbtdEguEyxEC/fVgcpOq8+h00EJlRkuqLRkCTfFP3N+q4FlFugkBYJr97dhl9oijveCV/Twi1trPI1s3xIQ2PNOdQtwddFa3ACs"
    "Y+RbgS405wie489MBI5wphW4O+u0scN3+eojg7G2a6nEFfV4IostNIi0d43jeS4GGcCrEzIFt0YoBGqHmtgFWzakvqWvPKK85WQ4xW9Zt+fWq4UjmgeqBouY"
    "K74xppTNYnNfNwtvy5CBPH4tqDM5bCLfXFMN3kx8uYamIqR9D0ASF58LTMmXOSBPKvuHEXj++lYsbsnuHGiKw2MZYokbDatuphUJWsKBp24IxorGqYoNdKck"
    "Qx5NXwlsKi1HfX9ASpsPxk47uFSIQrQ6mIE9za1Hi5a4D2+QKTN6lecr3133Fj41rNOtoFh1g7RrV8lt82rGmCiWaomx5Tp9P9YE/qqyL0w3YErMiLYYgS+o"
    "DpitoHIJN1TlYOWvS4z+Vmuak+mqtCwV28vb+7AXrJifsIwy2t1AzkKQKm24gfRKcTQIiex8LfB4ag6UiWtjZufrsDyq7YRs8UaA35skhGuebc2n2qj1HWKP"
    "ty33EJXX3EAN0HN+O5RiqZKJZ65n6tHy1hmw0YQcsaZQBLVE2c+1B9tjLU66AMEVR79aVV9FeYDxH1JOFJGadRJg7VeEN2SltVLucLVZLie0Hsjyvdt7WeFs"
    "sVPxbKdGOaiC3tS0oxntOdBMSTBbZCedtA4CmwQ13ZdlJRAkBSbAY6BzOX1puFTotUcpyr9EaQfKd+qiB0SZzbQf3w1/zRWTT3Y7Q0cgv/UGBsIxFNWvIjfu"
    "9Tp3+ZAs+ToDBzhBDqQdVijlXnDOfiwTnboAhF6Fr53X44W1vF8KkCujHl6GcNYSY6CdwQabVaGLDmB5h3O+bx1TScAtlF8TmB/gYZ6t3JekE2NCrQNbDiiP"
    "iTm9jiJdaeXy/aCpvcSefCHx6aZl8hssNTgpe8VCvQlIcVrTQBnIq/6rmN6Svt1AzDW/RVuMjsNHVI45Qdz87tPMZyzo+JG44dAYTySeHqYfJLmGF/IwsmXU"
    "7IoeAlyCvgFmfU0+Bne666rVXrjLg82kADxsrGeCV7qBqk/b4mm4oG1MlX4k7ilPubUnAAOegXqFI3aZsaL8TiJLVa8TcubKrZ8ePpb8bP4ofL1snrmzYjRA"
    "GoGrbhCnT4W+z2z1kYRoKI32DelgPSgMXOrait2qAAS97w4a8WUNU/f1F+12dAh8Z69VBdPMHmURNjqIV7iADrJqn7RPmTYnvvxIfsSVTtm/CalB6YRS+6bp"
    "iTpvlGm/rpmvjEh9QazKBgAF6r3d6Qxe2GYP3iOFz2E4lFWm+5S3VEWx+kh6xF28hxKC+16wGbj5rgIJw6CATY6qVOJ0qmJ0r7UZC8K/ANIheo+MQ1atqJtO"
    "Cr72CBsF7Cvab5aLPtfxVPgfJd1/jfRkSMcU043N+lAaHq+hOpvcs3yhYGgG0p+j3IDl46QaDreztQ5JYikWsucK42H5rXg7vKXCn+Y6QHzt+DewyiBqMvP3"
    "IOiocdZ4iDhPGQrrzyXhIm229rJEX4JnEi6txyhzixmP6IC7Bsvrqvci4OKje105+fAaxOcam1szwFdYcV3LQBOxVRBb0t2NYMbRAqrwJy2bEFYIrhpGVaO1"
    "TsyfF0wG6qQ6aSSgB9qr9/Rpn9rK+5CGt9pXUai5npcJwAE0JiwxpsEk9oKzQu9EH4vJTRk48ifzj8jTlkwFCluc7SiVhmWV+dpHB88GtHt6ezfT1zbW8pE6"
    "7lxeYOkrVge8erTdVrhWqG5STjB2qz3mpkVYM/9Myh21RWhLdIkydXtSuTBIcBCt+f24SCro9BFXsuvY+1W/lgAL3klZ07uP5M0M9Hxjbb4m4JufCs5SRISs"
    "GDVi5XGrxuihqk8J2Hf1LSBm4LRvCbQnzVK8HzgyVeLI90OqKGauwGMkdLe6JW90tmZzYlIDfvwTQN6V6PXzRH+zqRO/PDs5o3TEinAXUayZ+vlb1oSJ1Fne"
    "jxemyiqnD/BkBKsNaqY94Q/VnfRNPoJU/IxpzxHJuVozG1spQzLJ2jsxHVakRR3HOjt805gAReP7XJha9qFeZOGt0pmwjVqz3IoajpWQZvxTEo/xh60C9ATq"
    "ezlt2fABme4vqEmNyN5tSe7jATVccPu0GOD1hrf3UHxyc8N3bCBzdQKqkzYYsJXtRqHGx2/mPyfxqN9rrTmv7iPI/VyYaOYx1dFt+H5LsbBGAaAMby1hhahP"
    "u7sdyPCOLJuiXWsm8CG+cUQqwrsfbAVtmo8OGLiKeMB2ByHN9HIngWlvf0LHo5IM3Gdah8UjWLpGArLzlov5tEcFNj8Bq+OOSi6Tf4pCBPY7mK9VVrZWx9l9"
    "VUydrgbP577s50IvYjANWds1eCgUMzXwAgDX+TPo4kgDJf6zR0Ra1O/5NaB2BNd9wxLoGdYXNGNzJaJUiVGMs5RJqlR2ML4QRnZ7C2HBT60VeZtYSWFxUFPW"
    "eENPMFkwtB2jX0w67uhoaI7pO248drExXF2RyGMLQ1mfoxyPo3XXwIGZnjZVpuDH9nU/mXNvb9lWfSonEPdjEJSD37+8vt0jkIlNE6YKkyn+MoB/vsLadhmp"
    "LSf850DpUPwE7jMomxd8ddO0AqmoWzIKMX4Ox/uwajk9x3X9xk7Du9HHg3rIR+OszXSurQJ5wbNYlDincJUD+6N/le8psLTdFspwNzU77HFlF1yFcgWNdC2d"
    "T8B9TtXdvtEIy+v1RASzgL4LHUj4pGmTbnjHIWYBwpsF95VBTDVyRiKXGGdFaDAKe8UhL4Kz4S0l7XPQyzC8ValrXK9UdyXdSj5L/6ITO4B14jgHZ4aO67hZ"
    "7aykM+GEnzZvqCFpffgScTUOU3DneqlkBcQUeKYlOhtVl/ckXTgl6Wg/UI8fT2/TS6EPZ/BE68cQVngqDEJX7Zo6b2ChOrm75WyDWmG2kg47lWkL9ZmtznHJ"
    "p+2brTrO2iAZu/3t6IQ4slzQU7yDHJbQCF2eUnEXXmsOiMWuyLdj9njrLy2mWDTeWtMYX0inK+Y9mYO5B8Gv8dclI5GU68ETEBtnDSPtpBcd4Z+07PhcWDj9"
    "OjTvTDJEospv7vFjeBM6oxIyskOGy6VVuipWH2EdpMx5e3lfm4ObHYyLqGMPQ8mGn9Ry6T0SY/L8MVCynfbeniev4Aofbs4CS9bcEYsPcL7RrAJPSTzjAVLx"
    "mRoL3CmhK7Yz9UnO6jyN23lncKEA3mP5EvOK+xmtUC1THuKhDIFn4ECOH8ODtFgGlzjltB72kmoZc4v6/FlmGNNn+1IDfnmMBqNqaHXqHY+bxJgNMXThkua6"
    "JW1sDPGZeEUJ88xkxV9uQvwqH+qxTHc1B+IcaXm3fOuuS4wOMa6F1bH6pJM9vfRp7FZNiUksO4jj2LdN3cumNp/vucPAXEi3TNuiBLP1GWocDFKn+jxovWr4"
    "Ft34Kbbl5yJ0AOCn/WgDtl9gcVW4h4a3dL3OOK1CcZFpMyKsRatOY/t5Bs7GAtA6jUM/jNNGSJ5br4WDDxWNpB9W2iqLstA63t40gBUjp4O184NJkUNd+Uk9"
    "h4CmIXO8kw5faWUp2bkeYGDKfhbsdoelBKQDSqBY+Gu2hXlp2wsF//Vt7LyFLHY8hrWapxyAXwGW6QSj/OyaBjuPQ1ARxYChmk+AGlMfWN229t50Iyx3DZ8r"
    "eKnoZWXMWiSaGGLQtfPPBfnY9++00sxOCaRKnQ82hTrTmC0eqeVJpoNdYfgBIknaSDH/eGENrnhsbRW/R78Rupc49xiIrtWjoDoDoJBOSPQ5sKJ7lvNPxEWx"
    "TGaz5WwSJ+knlsZQ/pIjoLvLdFCe2O8invtMuAIETDrRTA7SKT3BM1RADpk4fRG8FiLWJwYwEO6CdfmUnllPDGDmR2jNj8fBRT+o/vRT/APIhH+23QfpWFJu"
    "aDz3iVIyLAy10/5OulkbFwU0AVZ8mc5s8SgvSCoeCDOwe8mnMp4rCWBj4i2BZE5Cga0SunfPPQowcNRJd5DnbwKQaCDEP6niEQ6wsiV3NeeVQbhvNkBRjbbq"
    "JrsqcdPYLKNaK0eNl3udPdvgD5U3ZWWB3C0piJEaXWr3CknobtyjThue3AwLLdGhAvx2g57rpiyY+ExnA0Dw94MG616v8yw8ZELBNrv5xImNp+H1pmevZyOe"
    "aJZHhy7uJ6H7FXidmCcuen30q5zn6Rz4TUHPNXKXabqTbq7artRQ9ofFDiF6eyD4lfRTR4ES9WqO1SVB/VRLs9cVa7280HzW/KKolx4VE+tdIcef758wSHBL"
    "0Nakd6963Y4rN/KOzEL+cEURw0oJuh3R3bneHsc0WgngusWqF5r/aKEWQAJYMjsmKTNDojtO9ssnVIIf6whAsqt4N0/qMU0z+OeV9ExHpH/YsCOQyo4jHZp0"
    "Wlt7pTrIBGgfjeVY6v+4QM0A82qSRKTRGKni4odrO8PAhy8BRevtbo0d+uUQBEFU1KsYoGFXHzTsLGYGgKTYRNw4L4dZX9VcnJzAtQS3DYvR3eLHC1KLvuYG"
    "yR0rJ7nloOcZ8R/uuuDkuQOvgMd8785spIWHbirJ077bHpVl6VvoypKFuR1v0aTbgp5IT51zmJpTA5acRST8YczgCLefm3nqRcvHYe5ucTj/MNz06zqlZBL6"
    "XbYzQyTurm43Zt52TGO9nel1Fz9cbHtJXpJ+MUoenoJwN9fgx0HyWJCuSYe0bbIh7eoYOy79sDLS5DYCtJI8uJ5eY6TCjpcZNq1uHGO9Uz2aSrMSLFpcR74g"
    "/Zw8FCBp7vLZQ6TJjCVuueHFYDWCEN7+0/FyQbF3G7snHs5KZSd9xEzwe6RTEVPQ3XiYSqjAmV8lHSyfu7wDlF69usqQvlWA7kBVF7OahM9zsB+4+qqSJp3v"
    "OP0V0lnPTZCB90gP0VvrEw8zjWvlO2xxJ3lBevMm6WZY9hMeuZv7OnrpjLcNsTDiDC/kEp+8LBczg22+gPn2W/EUG8PtO1HZ9JR0wgY18g+QDh8ZEh9Id8E6"
    "EFqUKQ1yamyDfYDrAZrTPIl8P0wycMuHmD2GWi/a9jGUE7SX+XKMX8udZYCqhntnmlQ8JZ1iqKH4KOkeuJw2ku6VZKzboar1qBr/XdJDrlqfMtuNYXi2QbxK"
    "ipQ9JEIv6sh9mN8F+3wf5ruVlOlz65w+kC7pU66vT/kBgddcJ1kXvrnX7etL2cNSGlQ3zlPr6FNGE8kvyOeSybuIKc43Yf42G37rE8YSKR6dT31cNPtK0iMC"
    "6HVMkfRA73VEzU9IX/d6GJDmogfipTdZIZcxA18M1JTpp51StUnrW3nOT52bB/bFOUwA83OB8216n2/R6jIf1E+b5HVcwF6f7tGbZ6RL1/A9z3Ojd42bXQgz"
    "XDznuYb3zZ30TpMelH58ckZoeUtJItX12IuVCbCDvjo7c319irbfv6EEfySG+fZ1/ozzZW9cwxnUikppgIafrbdIt2OFrY/e6VkULEG4OM8hDfOtjGTtpubE"
    "BKQXxHeDxD3nglzW32rrZcRu4bY5nxqoxIctJv7dtNXKw/kvECcWftomf2zA4ts12nXJj54l0rfv56bZKvAugDEQXeft1GMMqDohYUWeobk8jTtaNAeacxSY"
    "qJREd4GvlW0K8dSdsafFp3w4vdaxd++mrdLzg+fzbwA3xoteoR5AGkzR7Giuk3MLunj/kHXZ65b6oJ/1hHRSA/V+v0XhOWXovkSnKE12s205veIksPYWGKeI"
    "Vt2S9b5ONsdHmtm2JH99fsjEQ10PIDndeO1AcyjwwU7i/xEsWQ4M/7b78pJ08+K00jhJ+s2bh8c9hOb8JTTF+KqLSJubZx/ZQ+Kp/bKfvbuQp+e/Xv1S31zr"
    "IT1FRY+kHy653uvhTvr/8/+ePbef8NdpkpM6SrRVoiPmz/uLv8V4A8DqjaYBrJdmvOwKjK53muG1ZvRj8ynMT64ZeBQ8/xSDShWolWKn9Uf89YcoTU0uURpK"
    "wszu1mVvpAxJfcFkmQBl9qYStYBH46vhmEya+dvVZSbOv4i8A5o2VbI8+UXW/RU+GaV5FpsjZjV6R/Il03ji5JLE9vJO2CK8hc5rysaQif2eKxjcousJmugW"
    "YfD32EXRpebpk7G5LSJbXEg3CnaPyBYkuZ2UcTbT9l3ZamfavcJ2EJoPzOf7qbM7jm3k3aZEl1L64nMRWR2Hp6c4/Ma30dlDix1YtxOXeG4v7xauuIvvq+fb"
    "Gecn78+PtmNnDsX+bbjlxpdx+AMlUtBYP36090X2BQW+jPNwT0ZyhvoV/E7dTctTZv6ByudhpPzprvCU9ZH53Uhm/S6x0YBEThMoAHFCRxfSP5t90aRH/BSb"
    "I27h70lmqusdBnjZ0NbpzWpk4gPrGymzfHq+o+CUfyBKFW/zMYodEBtAVbhW01jBC9LZZ3NumGmNdsOujVtaBNZRWtBKGZECTI2T6VMZY2Z/pBOQhWdWn6nc"
    "KXc+cNqXmCoMMfofD0Hk62K0XJdVOEP6gnRXUCy7+vEOuxbm1/eCQSDdreJ2mNO9tCDFJ2Lyg/hFZhMmg0h9xICOpfXsZeBBwNAPzOe1dj5ZGvU2KHddTIOn"
    "/YJTmvJk1j+VX3+oqvBrVtZh2O/WzcOTf6asYf9jONqVdjl/yHAM9NkBD3Bi8+kj8xvOBB5NiNGPGmYMSmLOKhYDKqEgv8YEPldVcamlMbqekjFQdfbPpk0N"
    "XcjRw2O1p+TNrO0+lH4QT/WcJ8z2Q1Yok2sOlGEfOwBd3gZjmQ5Op2cb0X62lgarNIWxt/EkQe0UdXDnOgpaSordsnsz+RjpgLL7J+XKIJx9+7H5pNtZm9xi"
    "BDR3IY8vp+10BdXymcqGaK2b27/MyKt54MdeXytznf25HyddPT2pHAk6fpT0o8VeB0q4P9VGp8I65UNMYYefrIh3wXdL2cm/t6vGvpcHW9pX3EtKfoDr5+6A"
    "d3sCMK/7Qa4buPZC8N1byeVFf27Vkp9pwmZcamRXsazcg+tg1MG85VtJgAcw9EPlqKWg87O9Lu0P7/VxIz0GeQfZ2zF68M+QZGma77zK+0/XyKLXM5P6gv7N"
    "dDgco0zpqOzWj0c6pfiILm07JqNnTpmT8w9p+Intjct6kPdRHN/GIj8MguDIfv5EZbSuh3cec0L3HrDYXtTSzwdob/AoUB+JCQBUf1bORYUfLR9I2VJR2tgW"
    "xcaDBZWO0LwW1RHu5+vhEc/doxXPpAK8Rd1VyuzTOf9I7xViL2HwFM0N1YfOvFoqCJfaYzHWYvoAJ+Vr6DlALDeLz92WgKCmfaNpRqzECB8Cs+qX5TTSj9SJ"
    "JYo1T9VZ+jEVnwCGV04MEN4E1IHq6DX0XHeYjOOfPMO+nngaXsXTHDsJo6ILGwK+ZPoBJDr17PnFVKAssg/MH3sqRsfLLZLe4nXxifuUPJ5YP9FcNdHnOl8v"
    "pi9Q0VmoRCMwc6X5frMz/+aFr5zWnQrz/aNZwc0PALe7OWEcXNUeYZUltrsBH5byp052OkKf5o3fCF2C2a8A0Tk2SaRRv3sGeRjJa415YmmU0np//oTzGVi2"
    "bDtSS6x0lP1jpDlZTzd+us8kHn8/X+pgP3xTI0HLbCfd6FwY8h1TEt/cQL2meGD+e6YoufneouezSTN9a/SI7aXl9eLqSber+PwpbjzJ7J1umnkEI55ueFSu"
    "sAaczvjtrmqOqo8jq8+0ph29efgR0z10XnFG+k+2HandrZ5XCV4fQTpbWtFPnWT2taI4JJ5eEgTM1AELcFu3vEM/rue5X4eHEy3F68a/H96bz1mxah79yOGh"
    "/tWTnZjL9QuySSvpz59fZ2AeZnpElAy+3BWRx1vdeVFiq4o10a4KOr5uSFkvLf8tttogvuPrb2sM0tznV6De8QqWy4fBCTCTYe7xrvdV3jvy+bH1qtgzQzzZ"
    "PQSrVaVBtgYlbDz6TBrTa/lMa1S29bYOD26hyeUrcXprUI61JRtc1eFDr98WrKHaUP1TgLjqhns/05THwQuEAXwenmmjJYBl20V0+oh7RIK1xJV1S0jHJXlm"
    "ZwMpLOu9mHh+C+jwvOloiPPFFHqeTnu5WHJ/yUwyjleSBL3oQoZ4ppc/2UcY+9KY+1kIwIZMptjF+H6zGjYjMki9YE/fwI0B2pa38QX2tdtbzzzV7PdB9dtF"
    "694qT0Yf7rTHpLi9vIIW5nfMFXXk4l5OwbDhmifr2b4jBcLSSerTXoYIsfjt57os6m5EbKM0G7EkIGzVqTocW+OUGJYHIrIw7sGTc8dbH52cHhq0C3xDeisP"
    "E76AB2Lkk5BiTClQvuwn8WKY74y34Tyf+I2er0SYFJlJPAU6rpXactFha7dkirKQXFt3ivcTlD/djQhDcBOpV/tYdIheb+1FuWCo24dt3lHi+i7Vd5b6wyLa"
    "DG+zcb2k4TeeMHs82m/Acg631hkWNXOxLK3dL/1RUODNAr5tvMnrfGoPsg6LpI+wBs7VjZw9YkeU8pW39U0MR5+QtQfV+JMXwejVM9e+dV1JYvGiIUarG+2V"
    "t83msxpPqNrpsLe+n3L4a7101uGaq5D1SqgxNqmdTgoL76NlDwLCfDz4eZ/P1/m9TRnD3E8FT8JIeYGd5XjsrvXkeX3fJb7CHoQ/3UPY0f3mOr20bdPtnc9X"
    "ScYdgH0VAIXRYdmbidqdmlObEct2Pdum1Aondd7+2AHSmNTWjBQ0P8pUfH9zp1Uc59t6PqFWNB0dSADBYgdiXG6cbmQz5y+ct7HCRNzPtxDGzsGuq+1bd2su"
    "He2nNaK+wib7XsdEzJxL0Td5Emd1N0tRuS8Df9tdORQnPmpie5+fpHXHT/NhUynQ65kWdx0Gp9GgrjE5bHwUfkkHYdzLHRkQXfvBFeXu9Tq1Tu+Eate22KTB"
    "TvK253zoitR5sueqU346uT0RTTve5pfJ2Sm1Oey9QHfEpqQS+kpcv+cXiLi2FP2KTrKXjqJ6VfVFyuMckK0Wng36Kvn0tsqwVb/7VHa+YRv+8q623W+1w21l"
    "c6Hv9iVmxkXjU7Dz5656nrKCr+koquW5wRtYD38uR0yjL60gZXYgHwoWWfclKkzzvVCVd6mfaNQ729LdTnSwDgQEFxqPqjNUH0EnAbMaZ6eow4Zrs/yS+xyx"
    "e7B77ylK+sziWyGDvdnOYO3gWaPpNlPit/Q97/O8ONnytphEvh+jqLEWO2O02D1Et6OfsSjTyLkq49N5L2UGeo+Sr2E7iM89QzBMstp2OWh+Gqcb2M/w3Urk"
    "Ufleuvnafzl+pyWZVwPx9vbt5ZFRMeNB8hKPKPVCHVWgg1bvX3WRJbLdN/f6HV8cRc6+zEuxNnSvYH0SlMgSDw+8HZamD6RHS/D2AZoUXdX1uwt1vrwMAzQj"
    "ADzc9daGFFn0RTt9c9uxP7zWTEap7tuoX0QXbUaq0x2zgTPNBxLa1eWAY3p7x8UyI3OjPDt64+7nqp18kkMMboQ29ExkWPDxdbeX4s0nCRWpvmAr4N5h93Tf"
    "PezLgO64lkRWYff+d4LxvbpArVrtjRHfmDPiPsew0eoDOSe3zS25bGN9g0bJ9We+7kI/fRcEi9eoId0ln3FcfyufV51n9GtEqFi2SyBYHJRPKKK5BMx+iprR"
    "kQ+35yHqQ4Bc7XwXKMpIOSA84ZunQwhePYvFI47ysEHRF94FoXsI16TXmo7uwU+8usBpJI8ZuJ877TnmkVdfxOrTMnypwMJlji+RqAD4mYknB/C8xLP2sDhe"
    "9I0abi1Kx84B87xkJxXBgljfk9qqL70BBLMN8G7mxQ005sQfZB9gC6JJh9y0zIPy9+elwJsSMoB7zotwQYH7PFTHZasGBh5IdnvJ9i5bi5xZfZvc9Q6l5tj9"
    "s2Pmj25pIvVVR9OX3luK7RtGkp2bH2aKi1q3WZ3FflVnh3wxgd/6niO3dPOXFnuAZWKV3KNLQBHeN+++vJIrKRvdSAz8f/Ad8KZ7dT8Dou8OSM/aErwBGTG8"
    "myf8SsrXK81yMt4xnSkmRNBWtV9MzPBEF8okcijXl1JRr4tfBh8HYnS3kStsmUTdfpk4WoXpRZYnTItYN7zXkSHwgjar5uJ3GngXKnDkTGbf637JX32tmYuF"
    "6655j2zXo/Yv5RjesTPRtxHp68f86dad267dfRjwRaelY968iLGdJJ4MGZfBdu4a8XwlN7B8wP6RWD0f7hDrLnvpCQOn0giUODmQXzXQUZzo8SgHTGcwylPv"
    "VmuNxQbYVaQBmS6UOqqJiXe6rpzU/2CfJKsTy20R6Aez5p8DpgRjf79bxqyVzMDzR9DAD8+VJyeOHKS7KtTinn415fpGYvCB283l6tpwlPXZUWZb+x59fyEP"
    "sIEzRpa2YM8pnEeMDcA7aZrYW/juuHCcj8cqsFQsGA1LZ6lVyOEuTyfSzUPr1lq7/4Jb/PTtVQr0SLX6K8c1xIc62JuSMWyEo4CbNOa37cba5tiT4TNXhdnW"
    "nj8yqu1Ml5FOtzHQHf+xl9cJ6Vp3X7wUZb4uZDthWe8vuqo11Td2OjruHE6nk5aubRmUGnir13r02Oew/DxheH8jEG+QY9NTs9l9Nut+aVmYu9WxjrH+ZjPX"
    "0Uj8BmD5Q3h6v5odtK8YhmJ9OROB1xdr95Nfjdf+xItDLuf1ET/N83oVCSwOlnEa2FdTIc+MfL6J/M4KZ9gklBp27G/E+0V2da+dSt54Cs+IJmznlOunWVN4"
    "5COMQ+CtzVUNfuU9rcTgut/8Y8qQzYmDN1nyyvH8cDvx5+MRbIk9ZIxkXFSfbBTbxX49cULCztxzG2F4V11m1i/LiDIRDPrCV/2Njk1ztU1g8/5pbyXdlrn2"
    "48dfdTsvYnlEif3D7Qebxu0v+JGlMzKsRSTrAxPBwbhsQ789DmURE2R8s2hO2subwBwLi3p9nfVmTrGnA2jQVK9cuYe0XH29G5sbfSfzJ4uGPgrqhAwpv6rR"
    "vtDyv14tdkK/pcCLE9CjJGbcipsayuCw7/Txkj9w88NqXG5zg36wmeDN7Wo+LjiJdUVQLPS2t+U9RospmFF3/JIh+YVDr61tXg88bCdkrgWgqLPtWmAHaV7o"
    "m2rjalY3xes09kx6TkxRanlJ1uqfljrl5JUzkjKXd4u2ldsZtUJQMJxfoJ2Zr371/esgd2hArONO3CT2PafqtWJvy4c8ADYm1DQoOab6xe20HuRyu8HGGdu2"
    "bZoGfh1BkpZlEX2lWztQN5+kFvXcOBgLY79u3cVkZ3yq8K+lYePdtM2vpVxfRC4n5m49jAdU6/BcwftOnmPK4V4SBOYZCZFiKFaFbrhBVneTPtKpm64Cni1T"
    "f5V/FlSjpltHXlYAs2mWYnfxAdW29r24qVSWOf/KC8hPSQBY4IH5WzgZj0fHwvfTPMvSK9M3Q06oD6xHVS3nPj/pOspM07z3IKFOlPezXibJSw2PGF49YU4r"
    "UeHdsNjDPO9R0lLaxoTsMMkvH1iXCt62fw+ley/PlwR7Jcaqncyo5gqJgl+mts5C13NW+ANQyPXcKKvbSejmu0pOVbiRYeqTRBvt7Hy6O+bbIaNSOVoQfw2K"
    "exFmkZr24CisscRxz06cnXc6otvd4rGwGIGn6NjpX8XM14HddiVeRo6/glyceyo364UH+rJrMpx1idGla/jIoT2qH5eQ30c7IKjtXej9ZGW9lkT4+05PLoXV"
    "ZlgCc5G7urHyeoRbk4yLMbVF8NiWYBUeps/sP7n7qVY2G9WpvfIvH5FuHUntvULkfl4g4dr44O02WMHH5hcuJHW9OG/6ld+z5v1YV3nk2c9C8duVVfqCd/cx"
    "2sh6Ya2UB+S3jQj5PpiWWIti7hbdn6nLeQEvyYbRINmLyuS9np4xRg3LssHFsZP81ehCtB2RZ8NkEH4N35njZNjYnvp3Ur7JPIc110DyHmFB4MEKXTUDrrd7"
    "YTrFayEKw7ishte1Xdv3r6nno5sDGzi9nshwRU8ctGrit1K+0i5BubTX8+gUG60Eq0/B2nvYVf9dkNDJaHy5NmM132H/WuKp2MMSgFbTsyUJl+p4id88/BlF"
    "LSb59SRZX95tuiHmc3CdDiQLMpouw9jXdYkuHht3G1gT+6nUW4cGw4s678tcLrHuViu5Q377sLnSbaX3u9jJjrkOIFeMxSW31pDYD5gTe75nMsurKjz7sOtq"
    "N39eSdkfUs7ao/zCGMBJq1HZThb5F4YFBhUUPTPGEzfSieyXl5kiIvG5+0RpPAozP46eG+NTwbVreTqptnc8CGRPzUGbGUb+lYF3GoGyc0lxO6KOPo93G6S3"
    "aXB/cVo/vme8IBw1Gn0f1BPKrUoO/nR3yNZWxKxcsnW/qZKSf2tkoGcwJOWJfdMafAc61mOcLH5ZZqL/KY2rp7wz8xlrxpIHA+lxkI8Ct7lMyb84Qr34nUnb"
    "ZWU8nfed/ngvm/mymmulySDhU087+7+tDmheDn2zYimxShoVnEf+1QEbHt4C3i4Q66uU2a6aH8xtuQkBBSDjuFdDnj2Lr5jFJND2ZePZrgDLU7muN/mXBytR"
    "6DHsXi6nNMGamLpnDYpiLRynsDn4AL4bMxw/zhO2ueD7bs5S3fp4WyW/5KItD/tmdyrbFvvfFfaDExw1/ZwQp5eHurOvHsUQA/jdKsBsdGLTtG7aru+H0jcN"
    "09ritLSv/DAMT1OpX03bsUejRE5jXF6o0SV/xDBrLYGDQ0Ixx/QJ0wnW9bqt7/m+77le2vK9PsGIyrlM8zXg/DhrX1udvE+xfMmbkOWqYuRPGSHXb9QYsA+5"
    "vtXTuYKsYOQ2yXMnEAMAmpDaNR+TLSbr1B4xmzCKwnqpgjiK4pdhB5rAohKzVZrlPvmDBiv1S4mcIvHP6mLAJ02Dk7o2877v68x3DNjpuV2iQKRq8IPADx4R"
    "GktnkaJWgZ0lZc7InzU81D5CzSml6Xq144uR+sS8VPJSw42TApbLHba25s9iDlYpeIw3QWrJah3yxw0aT5p4njL44+lK0zvphVs+KdU2yP3KiGAALXe5F8LX"
    "1QtYDopfPobkjxwsFyvxuUH8To0P50xZX6fpexU+bn7quUCsbJKtCxZe7KtK/tRhVus7Yn0RMEr20Yn6tP4xxG3GI5Y9E7eR614qDPInj5142QNasUsh+vTH"
    "UNcWmLezQWLxgpFi7k0TbpI/fZgFB22PuYQ6AAUGvJ/K6Ide24prmJQ7hAWNWL+LZ38+4Zr4dFCa9YpXPgNKulmMdex9QF5NL24mydvIArp12kJLUGyQ/8qg"
    "IbJLUy9qvFXDSWs8MVflsADP+t1TanhJXk9C8BpLi+y4EZpuMOW1T/5bw8TG8GIG6hcgJzAxqZY0Pce8y9g3eZZlCNzgt7ztRyBS8L6OAfhQK2y4XHQkQIk+"
    "Mch/cDj5tPIe8y28KXUqjdq2n2ZN3418mueJjx1guhQPxKE/G5btjIm5WdM9Zg75rw7qZp3OImpSgKKpyeLYtR+vUba9JM7bCanePitFm/536d7Be1j2mnyx"
    "JhbxsKbgHIRej35CUuWy6E/Maza2L0OL/G8MO85hl69pRl1ittYV6CH22jNMwSrB2zwyyf/WoHZUNB2qOWD8mmvdVgCP7cKfeNvkoU3J/+qgtufGaV437TCA"
    "qI8DyD3efet6/8NEPzPm9G8i9+rLsb+Vcmv8PRUwfxrc8d1ItrUIPM/7u3hPx5njfdUlWHjh/11cNwxmop4zGDPpX8b1Fdzp4f5dXA+i+zDI9/ge3+N7fI/v"
    "8T2+x/f4Ht/je3yP7/E9zuP/BzrfNImUEe62AAAAAElFTkSuQmCC"
)


def _custom_brand_pixmap():
    global _CUSTOM_BRAND_PIXMAP
    if _CUSTOM_BRAND_PIXMAP is None or _CUSTOM_BRAND_PIXMAP.isNull():
        pm = QPixmap()
        try:
            pm.loadFromData(base64.b64decode(_CUSTOM_BRAND_ICON_B64), "PNG")
        except Exception:
            pass
        if pm.isNull():
            fallback = Path(__file__).resolve().parent / "public" / "assets" / "aistudio" / "____________ffbb9db3.png"
            if fallback.is_file():
                pm = QPixmap(str(fallback))
        _CUSTOM_BRAND_PIXMAP = pm
    return _CUSTOM_BRAND_PIXMAP


def _sync_aurora_ico(frames):
    if not frames:
        return None
    written = None
    try:
        header = struct.pack("<HHH", 0, 1, len(frames))
        offset = 6 + 16 * len(frames)
        entries = []
        for side, data in frames:
            entries.append(struct.pack("<BBBBHHII", side % 256, side % 256, 0, 0, 1, 32, len(data), offset))
            offset += len(data)
        payload = header + b"".join(entries) + b"".join(data for _, data in frames)
        for base in (Path(__file__).resolve().parent, Path(sys.executable).resolve().parent):
            assets_dir = base / "assets"
            if assets_dir.is_dir():
                ico_path = assets_dir / "aurora.ico"
                try:
                    if not ico_path.is_file() or ico_path.read_bytes() != payload:
                        ico_path.write_bytes(payload)
                    written = ico_path
                except OSError:
                    pass
        if sys.platform == "win32":
            import tempfile
            tmp_ico = Path(tempfile.gettempdir()) / "aurora_halo_v2.ico"
            try:
                if not tmp_ico.is_file() or tmp_ico.read_bytes() != payload:
                    tmp_ico.write_bytes(payload)
                written = tmp_ico
            except OSError:
                pass
    except OSError:
        pass
    return written


def application_icon():
    global _APP_ICON
    if _APP_ICON is None:
        icon = QIcon()
        frames = []
        for side in (16, 24, 32, 48, 64, 128, 256):
            pixmap = make_service_artwork("brand", pixel_size=side)
            pixmap.setDevicePixelRatio(1)
            icon.addPixmap(pixmap)
            buf = QBuffer()
            buf.open(QIODevice.OpenModeFlag.WriteOnly)
            if pixmap.save(buf, "PNG"):
                frames.append((side, bytes(buf.data())))
        _sync_aurora_ico(frames)
        if icon.isNull() or icon.pixmap(32, 32).isNull():
            path = Path(__file__).resolve().parent / "assets" / "aurora.ico"
            if path.is_file():
                icon = QIcon(str(path))
        _APP_ICON = icon
    return QIcon(_APP_ICON)


def _apply_native_win32_icon(hwnd, clear_caption=False):
    """Qt6 already sets window icons natively via QWindow::setIcon; avoid raw Win32 class mutations."""
    return


def set_windows_app_id(app_id=None):
    if sys.platform != "win32":
        return False
    try:
        function = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
        function.argtypes = [ctypes.c_wchar_p]
        function.restype = ctypes.c_int32
        return function(app_id or APP_USER_MODEL_ID) >= 0
    except (AttributeError, OSError):
        logging.getLogger("aurora").debug("Windows AppUserModelID недоступен")
        return False


def native_window_theme(widget):
    owner = widget
    while owner is not None:
        theme = getattr(owner, "theme", None)
        if theme in ("dark", "light"):
            return theme
        owner = owner.parentWidget()
    app = QApplication.instance()
    return "light" if app is not None and app.property("auroraTheme") == "light" else "dark"


def apply_native_title_bar(widget, theme, dwm_api=None):
    """Color the native frame without replacing Windows sizing/Snap/system buttons."""
    if (sys.platform != "win32" or not isinstance(widget, (QMainWindow, QDialog))
            or not widget.isWindow() or widget.windowFlags() & Qt.WindowType.FramelessWindowHint):
        return False
    try:
        handle = widget.effectiveWinId()
        if not handle:
            return False
        api = dwm_api if dwm_api is not None else ctypes.WinDLL("dwmapi")
        function = api.DwmSetWindowAttribute
        function.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32]
        function.restype = ctypes.c_int32
        hwnd = ctypes.c_void_p(int(handle))
        def attribute(number, value):
            data = ctypes.c_uint32(value)
            return function(hwnd, number, ctypes.byref(data), ctypes.sizeof(data)) >= 0
        dark = theme != "light"
        # Windows 10 builds use 19 or 20. Caption/text/border colors are Windows 11.
        applied = attribute(20, int(dark))
        if not applied:
            applied = attribute(19, int(dark))
        def colorref(hex_color):
            color = QColor(hex_color)
            return color.red() | color.green() << 8 | color.blue() << 16
        background = colorref("#0B0D10" if dark else "#E9EDF2")
        text = colorref("#E9EEF5" if dark else "#18202A")
        for number, value in ((35, background), (36, text), (34, background)):
            applied = attribute(number, value) or applied
        if applied and dwm_api is None:
            try:
                redraw = ctypes.windll.user32.RedrawWindow
                redraw.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32]
                redraw.restype = ctypes.c_int32
                redraw(hwnd, None, None, 0x0501)  # INVALIDATE | UPDATENOW | FRAME
            except (AttributeError, OSError):
                pass
        return applied
    except (AttributeError, OSError, TypeError, ValueError):
        # Unsupported DWM attributes must never prevent opening the player.
        logging.getLogger("aurora").debug("Оформление заголовка DWM недоступно")
        return False


class NativeTitleBarFilter(QObject):
    def eventFilter(self, watched, event):
        if (event.type() in (QEvent.Type.Show, QEvent.Type.WinIdChange)
                and isinstance(watched, (QMainWindow, QDialog))
                and watched.isWindow()
                and not watched.windowFlags() & Qt.WindowType.FramelessWindowHint):
            apply_native_title_bar(watched, native_window_theme(watched))
        return False


def configure_application(app):
    app.setApplicationDisplayName("")
    app.setWindowIcon(application_icon())
    if sys.platform == "win32" and not hasattr(app, "_aurora_title_bar_filter"):
        app._aurora_title_bar_filter = NativeTitleBarFilter(app)
        app.installEventFilter(app._aurora_title_bar_filter)


def refresh_native_title_bars(theme):
    app = QApplication.instance()
    if app is None:
        return
    app.setProperty("auroraTheme", theme)
    if sys.platform == "win32":
        for widget in QApplication.topLevelWidgets():
            if isinstance(widget, (QMainWindow, QDialog)) and widget.isVisible():
                apply_native_title_bar(widget, native_window_theme(widget))

def yt_dlp_tls_options():
    """Проверяет HTTPS и учитывает явно настроенное системное хранилище CA."""
    options = {"nocheckcertificate": False}
    # yt-dlp по умолчанию выбирает certifi и игнорирует SSL_CERT_FILE/SSL_CERT_DIR.
    # Поддерживаем доверенные CA пользователя/прокси без отключения проверки TLS.
    if os.environ.get("SSL_CERT_FILE") or os.environ.get("SSL_CERT_DIR"):
        options["compat_opts"] = {"no-certifi"}
    return options


# -------------------------------------------------------------
# Локальный шрифт включается и в сборку PyInstaller, установки в Windows не требует.
# -------------------------------------------------------------

def setup_font(app):
    fonts_dir = Path(__file__).resolve().parent / "fonts"
    if fonts_dir.is_dir():
        for font_path in sorted(list(fonts_dir.glob("*.ttf")) + list(fonts_dir.glob("*.otf"))):
            QFontDatabase.addApplicationFont(str(font_path))

    families = {family.casefold(): family for family in QFontDatabase.families()}
    family = next((families[name] for name in ("inter variable", "inter", "segoe ui")
                   if name in families), app.font().family())
    font = QFont(family, 10)
    font.setHintingPreference(QFont.HintingPreference.PreferVerticalHinting)
    app.setFont(font)
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
    if _SMOKE_DIRECTORY is not None:
        return _SMOKE_DIRECTORY / "cache"
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
    if _SMOKE_DIRECTORY is not None:
        return _SMOKE_DIRECTORY / "data"
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    path = Path(base) if base else Path.home() / ".local" / "share"
    if path.name.casefold() != "auroramusicplayer":
        path /= "AuroraMusicPlayer"
    path.mkdir(parents=True, exist_ok=True)
    return path


def migrate_legacy_data(filename):
    destination = app_data_directory() / filename
    if _SMOKE_DIRECTORY is not None:
        return destination
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
    logger.info("Запуск Aurora %s; Qt %s; Python %s; platform=%s",
                APP_VERSION, QT_VERSION_STR, sys.version.split()[0], sys.platform)
    return logger


def style_dialog_for_theme(dialog, object_name, theme):
    """Задаёт диалогу читаемую палитру в обеих темах приложения."""
    dialog.setObjectName(object_name)
    dialog.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    dialog.setAutoFillBackground(True)
    palette = dialog.palette()
    if theme == "light":
        palette.setColor(QPalette.ColorRole.Window, QColor("#F3F6FA"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#18202A"))
        palette.setColor(QPalette.ColorRole.Base, QColor("#FFFFFF"))
        palette.setColor(QPalette.ColorRole.Text, QColor("#18202A"))
        palette.setColor(QPalette.ColorRole.Button, QColor("#EBF0F5"))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor("#18202A"))
        dialog.setPalette(palette)
        dialog.setStyleSheet("""
            QDialog { background: #F3F6FA; color: #18202A; }
            QDialog QWidget { color: #18202A; }
            QDialog QLabel { color: #18202A; background: transparent; }
            QDialog QLabel#settingsTitle { color: #141C26; font-size: 22pt; font-weight: 800; }
            QDialog QLabel#settingsHint, QDialog QLabel#mutedText { color: #5C697C; }
            QDialog QLineEdit, QDialog QComboBox {
                background: #FFFFFF; color: #18202A; border: 1px solid #D5DEE8;
                border-radius: 10px; padding: 8px 12px; min-height: 20px;
                selection-background-color: #1DB954; selection-color: #FFFFFF;
            }
            QDialog QLineEdit:focus, QDialog QComboBox:focus {
                border: 1px solid #23834D; background: #FFFFFF;
            }
            QDialog QComboBox QAbstractItemView {
                background: #FFFFFF; color: #18202A; selection-background-color: #E3F3E9;
                selection-color: #167942; border: 1px solid #D5DEE8;
            }
            QDialog QPushButton {
                background: #EBF0F5; color: #1C2633; border: 1px solid #D5DEE8;
                border-radius: 10px; padding: 9px 15px; font-weight: 600;
            }
            QDialog QPushButton:hover { background: #FFFFFF; border-color: #23834D; }
            QDialog QPushButton#accentButton {
                background: #1DB954; color: #FFFFFF; border: none; font-weight: 800;
            }
            QDialog QPushButton#accentButton:hover { background: #16883D; color: #FFFFFF; }
            QMessageBox { background: #F3F6FA; color: #18202A; }
            QMessageBox QLabel { color: #18202A; min-width: 280px; }
            QMessageBox QPushButton { background: #EBF0F5; color: #18202A; }
        """)
    else:
        palette.setColor(QPalette.ColorRole.Window, QColor("#10141B"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#F2F5F9"))
        palette.setColor(QPalette.ColorRole.Base, QColor("#181E27"))
        palette.setColor(QPalette.ColorRole.Text, QColor("#F2F5F9"))
        palette.setColor(QPalette.ColorRole.Button, QColor("#1E2530"))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor("#FFFFFF"))
        dialog.setPalette(palette)
        dialog.setStyleSheet("""
            QDialog { background: #10141B; color: #F2F5F9; }
            QDialog QWidget { color: #F2F5F9; }
            QDialog QLabel { color: #F2F5F9; background: transparent; }
            QDialog QLabel#settingsTitle { color: #FFFFFF; font-size: 22pt; font-weight: 800; }
            QDialog QLabel#settingsHint, QDialog QLabel#mutedText { color: #9DA9BA; }
            QDialog QLineEdit, QDialog QComboBox {
                background: #181E27; color: #FFFFFF; border: 1px solid #2C3544;
                border-radius: 10px; padding: 8px 12px; min-height: 20px;
                selection-background-color: #1DB954; selection-color: #0D1A12;
            }
            QDialog QLineEdit:focus, QDialog QComboBox:focus {
                border: 1px solid #5AD48D; background: #1D2430;
            }
            QDialog QComboBox QAbstractItemView {
                background: #181E27; color: #FFFFFF; selection-background-color: #21382B;
                selection-color: #66E099; border: 1px solid #2C3544;
            }
            QDialog QPushButton {
                background: #1E2530; color: #F2F5F9; border: 1px solid #2E3846;
                border-radius: 10px; padding: 9px 15px; font-weight: 600;
            }
            QDialog QPushButton:hover { background: #262F3D; border-color: #5AD48D; }
            QDialog QPushButton#accentButton {
                background: #1DB954; color: #0D1912; border: none; font-weight: 800;
            }
            QDialog QPushButton#accentButton:hover { background: #38DC73; }
            QMessageBox { background: #10141B; color: #FFFFFF; }
            QMessageBox QLabel { color: #FFFFFF; min-width: 280px; }
            QMessageBox QPushButton { background: #1E2530; color: #FFFFFF; }
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
    elif kind == "pause":
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(QRectF(-9, -10, 6, 20), 1.5, 1.5)
        painter.drawRoundedRect(QRectF(3, -10, 6, 20), 1.5, 1.5)
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
    elif kind in ("folder", "📁"):
        folder = QPainterPath()
        folder.moveTo(-12.5, -8.5)
        folder.lineTo(-3.2, -8.5)
        folder.lineTo(-0.2, -5.0)
        folder.lineTo(12.5, -5.0)
        folder.lineTo(12.5, 9.5)
        folder.lineTo(-12.5, 9.5)
        folder.closeSubpath()
        painter.setPen(QPen(color, 2.1, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(QColor(255, 255, 255, 38))
        painter.drawPath(folder)
    else:  # универсальная парная восьмая нота (♫) — симметричный и цельный символ
        stem_pen = QPen(color, 2.35, Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(stem_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        # Два вертикальных штиля
        painter.drawLine(QPointF(-3.8, -8.5), QPointF(-3.8, 5.2))
        painter.drawLine(QPointF(6.8, -10.8), QPointF(6.8, 3.0))
        # Соединяющее двойное ребро сверху
        beam = QPainterPath()
        beam.moveTo(-5.0, -9.6)
        beam.lineTo(8.0, -12.0)
        beam.lineTo(8.0, -7.8)
        beam.lineTo(-5.0, -5.4)
        beam.closeSubpath()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawPath(beam)
        # Две аккуратные наклонные головки нот
        for cx, cy in ((-6.8, 5.6), (3.8, 3.4)):
            painter.save()
            painter.translate(cx, cy)
            painter.rotate(-18.0)
            painter.drawEllipse(QRectF(-4.4, -3.1, 8.8, 6.2))
            painter.restore()
    painter.restore()


class SpotifyPlaylistCard(QPushButton):
    """Карточка быстрого старта с рисуемым градиентом и мягкой подсветкой."""
    def __init__(self, title, subtitle, symbol, color_a, color_b, parent=None, cover_url="", action_icon="play", artwork_style="", tile_mode=False):
        super().__init__(parent)
        self.tile_mode = tile_mode
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
        self.playback_state = "idle"
        self._equalizer_phase = 0
        self._equalizer_timer = QTimer(self)
        self._equalizer_timer.setInterval(120)
        self._equalizer_timer.timeout.connect(self._advance_equalizer)
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

    def set_playback_state(self, state):
        if state == self.playback_state:
            return
        self.playback_state = state
        descriptions = {"playing": "Сейчас играет", "paused": "На паузе",
                        "waiting": "Жду продолжение", "loading": "Загружается"}
        self.setAccessibleName(f"{self.title}: {descriptions.get(state, self.subtitle)}")
        if state in ("playing", "paused"):
            self.setToolTip("Поставить супермикс на паузу" if state == "playing" else "Продолжить супермикс")
        else:
            self.setToolTip(f"{self.title} — {descriptions.get(state, self.subtitle)}")
        self._update_equalizer_timer()
        self.update()

    def _update_equalizer_timer(self):
        if self.playback_state == "playing" and self.isVisible():
            if not self._equalizer_timer.isActive():
                self._equalizer_timer.start()
        else:
            self._equalizer_timer.stop()

    def _advance_equalizer(self):
        self._equalizer_phase = (self._equalizer_phase + 1) % 12
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        self._update_equalizer_timer()

    def hideEvent(self, event):
        self._equalizer_timer.stop()
        super().hideEvent(event)

    def _paint_playback_badge(self, painter, cover):
        if self.playback_state == "idle":
            return
        labels = {"playing": "Сейчас играет", "paused": "На паузе",
                  "waiting": "Продолжение…", "loading": "Загрузка…"}
        label = labels[self.playback_state]
        font = QFont(self.font().family(), 8, QFont.Weight.DemiBold)
        painter.setFont(font)
        width = min(cover.width() - 12, QFontMetrics(font).horizontalAdvance(label) + 40)
        badge = QRectF(cover.left() + 6, cover.top() + 7, width, 27)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(12, 34, 24, 235))
        painter.drawRoundedRect(badge, 13, 13)
        painter.setBrush(QColor("#68E59C"))
        for index in range(4):
            height = (5 + 9 * (0.5 + 0.5 * math.sin(self._equalizer_phase * 0.9 + index * 1.8))
                      if self.playback_state == "playing" else (5, 9, 9, 5)[index])
            painter.drawRoundedRect(QRectF(badge.left() + 10 + index * 4, badge.center().y() - height / 2, 2.5, height), 1, 1)
        painter.setPen(QColor("#D8FFE5"))
        painter.drawText(badge.adjusted(31, 0, -5, 0), Qt.AlignmentFlag.AlignVCenter,
                         QFontMetrics(font).elidedText(label, Qt.TextElideMode.ElideRight, int(width - 36)))

    def set_cover(self, pixmap):
        self._cover_pixmap = pixmap if pixmap is not None and not pixmap.isNull() else None
        self._scaled_cover = None
        self.update()

    def _cover_for_size(self, artwork, side):
        # Keep only the current display size. Hover/equalizer repaints must not
        # repeatedly resample a large network image on the GUI thread.
        key = (artwork.cacheKey(), int(side), self.devicePixelRatioF())
        cached = getattr(self, "_scaled_cover", None)
        if cached is None or cached[0] != key:
            pixels = max(1, round(side * key[2]))
            scaled = artwork.scaled(pixels, pixels, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                    Qt.TransformationMode.SmoothTransformation)
            scaled.setDevicePixelRatio(key[2])
            self._scaled_cover = (key, scaled)
        return self._scaled_cover[1]

    def _set_hover(self, value):
        self._hover = float(value)
        self.update()

    def enterEvent(self, event):
        self._hover_animation.stop()
        self._set_hover(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover_animation.stop()
        self._set_hover(0.0)
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
        """Дизайнерская студийная обложка 384×384 с виниловым диском, неоновым свечением и типографикой."""
        size = 384
        image = QPixmap(size, size)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        rect = QRectF(0, 0, size, size)
        clip = QPainterPath()
        clip.addRoundedRect(rect, 24, 24)
        painter.setClipPath(clip)

        themes = {
            "likes": ("#0F0826", "#4C1D95", "#EC4899", "#F472B6", "heart", "COLLECTION", "FAVORITES", "♥"),
            "soundcloud-likes": ("#1C090D", "#9A1B3B", "#FF5500", "#FF9E44", "heart", "SOUNDCLOUD", "LIKED TRACKS", "SC"),
            "supermix": ("#1A070D", "#BE123C", "#F97316", "#FBBF24", "supermix", "YOUTUBE MUSIC", "MY SUPERMIX", "∞"),
            "shuffle": ("#051923", "#0E7490", "#10B981", "#34D399", "headphones", "SMART WAVE", "SHUFFLE MIX", "⇄"),
            "my_mix_1": ("#07132B", "#1D4ED8", "#06B6D4", "#38BDF8", "music", "YOUTUBE MUSIC", "MY MIX 01", "01"),
            "my_mix_2": ("#061F18", "#047857", "#84CC16", "#A3E635", "supermix", "YOUTUBE MUSIC", "MY MIX 02", "02"),
            "my_mix_3": ("#21081F", "#9D174D", "#FB7185", "#FDA4AF", "headphones", "YOUTUBE MUSIC", "MY MIX 03", "03"),
            "discover_mix": ("#120829", "#5B21B6", "#A855F7", "#E879F9", "supermix", "YOUTUBE MUSIC", "DISCOVER MIX", "NEW"),
            "new_release_mix": ("#210E05", "#C2410C", "#F59E0B", "#FDE047", "play", "YOUTUBE MUSIC", "NEW RELEASES", "HOT"),
            "replay_mix": ("#170924", "#7E22CE", "#06B6D4", "#67E8F9", "repeat", "YOUTUBE MUSIC", "ON REPEAT", "TOP"),
        }
        c_dark, c_mid, c_bright, c_glow, icon_name, badge_txt, title_txt, wm_txt = themes.get(style, themes["likes"])

        # 1. Глубокий многослойный студийный градиент
        bg = QLinearGradient(0, 0, size, size)
        bg.setColorAt(0.0, QColor(c_dark))
        bg.setColorAt(0.52, QColor(c_mid))
        bg.setColorAt(1.0, QColor(c_bright).darker(135))
        painter.fillRect(rect, bg)

        # 2. Аврора-облака свечения в углах
        painter.setPen(Qt.PenStyle.NoPen)
        top_orb = QRadialGradient(QPointF(316, 68), 255)
        g1 = QColor(c_bright)
        g1.setAlpha(165)
        top_orb.setColorAt(0.0, g1)
        g2 = QColor(c_glow)
        g2.setAlpha(45)
        top_orb.setColorAt(0.55, g2)
        top_orb.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(rect, top_orb)

        bot_orb = QRadialGradient(QPointF(64, 330), 230)
        b1 = QColor(c_glow)
        b1.setAlpha(95)
        bot_orb.setColorAt(0.0, b1)
        bot_orb.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(rect, bot_orb)

        # 3. Диагональные световые лучи и геометрия
        painter.save()
        painter.translate(192, 192)
        painter.rotate(-24)
        for idx in range(5):
            stripe = QColor(255, 255, 255, 11 if idx % 2 == 0 else 6)
            painter.setBrush(stripe)
            painter.drawRoundedRect(QRectF(-260, -195 + idx * 78, 520, 28), 14, 14)
        painter.restore()

        # 4. Крупный полупрозрачный водяной знак номера/символа в правом верхнем углу
        wm_font = QFont("Segoe UI", 54, QFont.Weight.Black)
        painter.setFont(wm_font)
        painter.setPen(QColor(255, 255, 255, 24))
        painter.drawText(QRectF(180, 18, 178, 92), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop, wm_txt)

        # 5. Центральная виниловая/стеклянная пластинка-медальон
        cx, cy = 192.0, 174.0
        disc_shadow = QRadialGradient(QPointF(cx, cy + 8), 112)
        disc_shadow.setColorAt(0.0, QColor(0, 0, 0, 135))
        disc_shadow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(disc_shadow)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(cx, cy + 8), 112, 112)

        # Внешний виниловый диск
        disc_grad = QLinearGradient(cx - 92, cy - 92, cx + 92, cy + 92)
        disc_grad.setColorAt(0.0, QColor(18, 22, 32, 228))
        disc_grad.setColorAt(0.5, QColor(10, 13, 20, 242))
        disc_grad.setColorAt(1.0, QColor(24, 29, 42, 228))
        painter.setBrush(disc_grad)
        rim_col = QColor(c_glow)
        rim_col.setAlpha(135)
        painter.setPen(QPen(rim_col, 1.8))
        painter.drawEllipse(QPointF(cx, cy), 92, 92)

        # Концентрические звуковые дорожки на диске
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for r_idx, rad in enumerate((79, 67, 56)):
            groove = QColor(255, 255, 255, 26 - r_idx * 5)
            painter.setPen(QPen(groove, 1.1))
            painter.drawEllipse(QPointF(cx, cy), rad, rad)

        # Внутреннее неоновое ядро медальона
        core_grad = QLinearGradient(cx - 44, cy - 44, cx + 44, cy + 44)
        core_grad.setColorAt(0.0, QColor(c_bright))
        core_grad.setColorAt(1.0, QColor(c_mid))
        painter.setBrush(core_grad)
        painter.setPen(QPen(QColor(255, 255, 255, 95), 1.5))
        painter.drawEllipse(QPointF(cx, cy), 44, 44)

        draw_vector_icon(painter, icon_name, QRectF(cx - 23, cy - 23, 46, 46), "#FFFFFF")

        # 6. Верхний стеклянный бейдж («YOUTUBE MUSIC» / «COLLECTION»)
        pill_rect = QRectF(24, 24, 148, 28)
        painter.setBrush(QColor(10, 14, 22, 165))
        painter.setPen(QPen(QColor(255, 255, 255, 38), 1.0))
        painter.drawRoundedRect(pill_rect, 14, 14)
        dot_c = QColor(c_glow)
        painter.setBrush(dot_c)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(38, 38), 4.2, 4.2)
        tag_font = QFont("Segoe UI", 8, QFont.Weight.Bold)
        tag_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.1)
        painter.setFont(tag_font)
        painter.setPen(QColor(240, 246, 252, 230))
        painter.drawText(pill_rect.adjusted(24, 0, -8, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, badge_txt)

        # 7. Нижняя плашка с типографикой обложки и мини-эквалайзером
        footer_grad = QLinearGradient(0, 268, 0, size)
        footer_grad.setColorAt(0.0, QColor(8, 10, 16, 0))
        footer_grad.setColorAt(0.45, QColor(8, 10, 16, 155))
        footer_grad.setColorAt(1.0, QColor(6, 8, 14, 225))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.fillRect(QRectF(0, 268, size, size - 268), footer_grad)

        # Неоновая полоска-акцент над названием
        acc_bar = QLinearGradient(26, 314, 96, 314)
        acc_bar.setColorAt(0.0, QColor(c_glow))
        acc_bar.setColorAt(1.0, QColor(c_bright))
        painter.setBrush(acc_bar)
        painter.drawRoundedRect(QRectF(26, 312, 56, 4.5), 2.2, 2.2)

        cov_font = QFont("Segoe UI", 19, QFont.Weight.Black)
        cov_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.8)
        painter.setFont(cov_font)
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(QRectF(26, 320, 290, 38), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, title_txt)

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(255, 255, 255, 42), 2))
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 23, 23)
        painter.end()
        return image

    def _paint_artwork_card(self):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if not self.isEnabled():
            painter.setOpacity(0.6)
        bounds = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(bounds, 16, 16)
        light = getattr(self.window(), "theme", "dark") == "light"
        if light:
            bg_start = QColor("#EBF1F6" if self._hover > 0 else "#F4F7FA")
            bg_end = QColor("#E2EAF2" if self._hover > 0 else "#EDF2F7")
            border_color = QColor("#278454" if self._hover > 0 else "#D9E1EB")
        else:
            bg_start = QColor("#232A35" if self._hover > 0 else "#191E26")
            bg_end = QColor("#1B212A" if self._hover > 0 else "#141820")
            border_color = QColor(90, 212, 141, 125) if self._hover > 0 else QColor(255, 255, 255, 22)
        card_grad = QLinearGradient(bounds.topLeft(), bounds.bottomRight())
        card_grad.setColorAt(0.0, bg_start)
        card_grad.setColorAt(1.0, bg_end)
        painter.fillPath(path, card_grad)
        painter.setPen(QPen(border_color, 1.2 if self._hover > 0 else 1.0))
        painter.drawPath(path)
        side = min(114.0, bounds.height() - 26)
        cover = QRectF(bounds.left() + 14, bounds.center().y() - side / 2, side, side)
        artwork = self._cover_pixmap if self._cover_pixmap is not None and not self._cover_pixmap.isNull() else self._artwork
        cover_path = QPainterPath()
        cover_path.addRoundedRect(cover, 11, 11)
        painter.save()
        painter.setClipPath(cover_path)
        scaled = self._cover_for_size(artwork, side)
        pixels = side * scaled.devicePixelRatioF()
        crop = QRectF((scaled.width() - pixels) / 2, (scaled.height() - pixels) / 2, pixels, pixels)
        painter.drawPixmap(cover, scaled, crop)
        painter.restore()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(255, 255, 255, 28), 1))
        painter.drawRoundedRect(cover, 11, 11)

        left = cover.right() + 22
        width = max(24.0, bounds.right() - left - 76)
        title_font = QFont(self.font().family(), 15, QFont.Weight.Bold)
        painter.setFont(title_font)
        painter.setPen(QColor("#141C26" if light else "#F7F9FC"))
        has_subtitle = bool(str(self.subtitle or "").strip())
        title_y = bounds.center().y() - (24 if has_subtitle else 16)
        painter.drawText(QRectF(left, title_y, width, 28),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         QFontMetrics(title_font).elidedText(self.title, Qt.TextElideMode.ElideRight, int(width)))
        if has_subtitle:
            sub_font = QFont(self.font().family(), 10, QFont.Weight.Medium)
            painter.setFont(sub_font)
            painter.setPen(QColor("#5C697C" if light else "#9BA7B8"))
            painter.drawText(QRectF(left, title_y + 26, width, 22),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                             QFontMetrics(sub_font).elidedText(self.subtitle, Qt.TextElideMode.ElideRight, int(width)))
        button = QRectF(bounds.right() - 56, bounds.center().y() - 21, 42, 42)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#1ED760" if self._hover > 0 else ("#1DB954" if light else "#FFFFFF")))
        painter.drawEllipse(button)
        icon_fg = "#FFFFFF" if (light and self._hover <= 0) else "#0E1712"
        draw_vector_icon(painter, self.action_icon, button.adjusted(11, 11, -11, -11), icon_fg)
        painter.end()

    def _paint_tile(self):
        light = getattr(self.window(), "theme", "dark") == "light"
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            painter.setOpacity(0.55)
        bounds = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        active = self.playback_state in ("playing", "paused", "waiting")
        if active:
            border = QColor("#23834D" if light else "#389E63")
            background = QColor("#E4F4EA" if light else "#162B22")
        else:
            bg_idle = QColor("#F5F8FB" if light else "#161B23")
            bg_hover = QColor("#EBF0F6" if light else "#222936")
            background = self._blend(bg_idle, bg_hover, self._hover)
            border_idle = QColor(220, 227, 236, 255) if light else QColor(255, 255, 255, 15)
            border_hover = QColor(197, 210, 224, 255) if light else QColor(255, 255, 255, 34)
            border = self._blend(border_idle, border_hover, self._hover)
        painter.setPen(QPen(border, 1.4 if active else 1.0))
        painter.setBrush(background)
        painter.drawRoundedRect(bounds, 14, 14)
        side = self.width() - 28
        cover_h = max(80.0, self.height() - 64.0)
        cover = QRectF(14, 14, side, cover_h)
        artwork = self._cover_pixmap if self._cover_pixmap is not None else self._artwork
        if artwork is not None and not artwork.isNull():
            # Soft shadow under the square album artwork inside the card
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(0, 0, 0, 28 if light else 75))
            painter.drawRoundedRect(cover.translated(0, 4), 11, 11)
            path = QPainterPath()
            path.addRoundedRect(cover, 10, 10)
            painter.save()
            painter.setClipPath(path)
            scaled = self._cover_for_size(artwork, max(side, cover_h))
            dpr = scaled.devicePixelRatioF()
            pw = side * dpr
            ph = cover_h * dpr
            crop = QRectF((scaled.width() - pw) / 2, (scaled.height() - ph) / 2, pw, ph)
            painter.drawPixmap(cover, scaled, crop)
            if active or self._hover > 0:
                vignette = QLinearGradient(cover.topLeft(), cover.bottomLeft())
                vignette.setColorAt(0.0, QColor(0, 0, 0, 0))
                vignette.setColorAt(0.6, QColor(0, 0, 0, int(14 * self._hover)))
                vignette.setColorAt(1.0, QColor(0, 0, 0, int(75 * max(0.4, self._hover))))
                painter.fillRect(cover, vignette)
            painter.restore()
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(255, 255, 255, 22), 1))
            painter.drawRoundedRect(cover, 10, 10)
        self._paint_playback_badge(painter, cover)
        # Spotify-style green floating action button that lifts smoothly on hover
        lift = (1.0 - self._hover) * 3.5 if not active else 0.0
        btn_size = 40.0
        button = QRectF(cover.right() - btn_size - 8.0, cover.bottom() - btn_size - 8.0 + lift, btn_size, btn_size)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, int(85 + 45 * self._hover)))
        painter.drawEllipse(button.translated(0, 3))
        btn_color = QColor("#1ED760") if (active or self._hover > 0.1) else QColor("#1DB954")
        painter.setBrush(btn_color)
        painter.drawEllipse(button)
        action = "pause" if self.playback_state == "playing" else self.action_icon
        draw_vector_icon(painter, action, button.adjusted(11, 11, -11, -11), "#0A140E")
        title_font = QFont(self.font().family(), 11, QFont.Weight.Bold)
        painter.setFont(title_font)
        painter.setPen(QColor(("#1F7A46" if light else "#68E59C") if active else
                              ("#141C26" if light else "#F7F9FC")))
        title_y = cover.bottom() + 10
        painter.drawText(QRectF(14, title_y, side, 20), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                         QFontMetrics(title_font).elidedText(self.title, Qt.TextElideMode.ElideRight, int(side)))
        subtitle_text = str(self.subtitle or "").strip()
        if subtitle_text:
            sub_font = QFont(self.font().family(), 9, QFont.Weight.Medium)
            painter.setFont(sub_font)
            painter.setPen(QColor("#5C697C" if light else "#98A4B5"))
            painter.drawText(QRectF(14, title_y + 20, side, 18), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                             QFontMetrics(sub_font).elidedText(subtitle_text, Qt.TextElideMode.ElideRight, int(side)))
        painter.end()

    def paintEvent(self, event):
        if self.tile_mode:
            self._paint_tile()
            return
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
                 artist_filter=None, artist_catalog=False,
                 radio_seed_track=None, radio_excluded_keys=None,
                 radio_excluded_signatures=None, radio_recent_keys=None,
                 radio_round=0, radio_artist_context=None):
        super().__init__(parent)
        self.query = str(query or "").strip()
        self.source = source
        self.sort_mode = sort_mode
        self.limit = max(1, int(limit))
        self.direct_url = str(direct_url or "").strip()
        self.cookie_file = str(cookie_file or "").strip()
        self.cookies_from_browser = str(cookies_from_browser or "").strip()
        self.radio_seed_track = dict(radio_seed_track) if isinstance(radio_seed_track, dict) else None
        self.radio_excluded_keys = set(radio_excluded_keys or ())
        self.radio_excluded_signatures = set(radio_excluded_signatures or ())
        self.radio_recent_keys = set(radio_recent_keys or ())
        self.radio_round = max(0, int(radio_round or 0))
        self.radio_artist_context = str(radio_artist_context or "").strip()
        self.cache_enabled = bool(cache_enabled) and not bool(self.direct_url) and self.radio_seed_track is None
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

    _SOUNDCLOUD_CACHED_CLIENT_ID = None

    @staticmethod
    def _soundcloud_item_to_entry(item):
        """Преобразует JSON-объект трека из SoundCloud API v2 напрямую в плоский словарь трека без сетевых запросов."""
        if not isinstance(item, dict):
            return None
        if str(item.get("kind") or "track") != "track":
            return None
        permalink_url = str(item.get("permalink_url") or item.get("webpage_url") or item.get("url") or "").strip()
        track_id = str(item.get("id") or "").strip()
        if not permalink_url.startswith(("https://", "http://")):
            return None
        user = item.get("user") if isinstance(item.get("user"), dict) else {}
        pub = item.get("publisher_metadata") if isinstance(item.get("publisher_metadata"), dict) else {}
        uploader = str(user.get("username") or user.get("full_name") or item.get("uploader") or "").strip()
        uploader_url = str(user.get("permalink_url") or item.get("uploader_url") or "").strip()
        uploader_id = str(user.get("permalink") or user.get("id") or item.get("uploader_id") or "").strip()
        avatar_url = normalize_artwork_url(str(user.get("avatar_url") or item.get("avatar_url") or "").strip())
        explicit_artist = str(pub.get("artist") or item.get("artist") or "").strip()
        artwork_url = normalize_artwork_url(
            str(item.get("artwork_url") or item.get("thumbnail") or "").strip()
        ) or avatar_url
        try:
            raw_duration = float(item.get("duration") or item.get("full_duration") or 0)
            # В SoundCloud API v2 длительность приходит в миллисекундах (> 1000 для нормальных треков).
            duration = raw_duration / 1000.0 if raw_duration > 1000 else raw_duration
        except (TypeError, ValueError):
            duration = 0.0
        media = item.get("media") if isinstance(item.get("media"), dict) else None
        transcodings = media.get("transcodings") if media and isinstance(media.get("transcodings"), list) else None
        return {
            "_type": "url",
            "ie_key": "Soundcloud",
            "id": track_id,
            "title": str(item.get("title") or "Без названия").strip(),
            "url": permalink_url,
            "webpage_url": permalink_url,
            "permalink_url": permalink_url,
            "original_url": permalink_url,
            "thumbnail": artwork_url,
            "artwork_url": artwork_url,
            "avatar_url": avatar_url,
            "uploader_thumbnail": avatar_url,
            "artist": explicit_artist or uploader,
            "uploader": uploader,
            "uploader_id": uploader_id,
            "uploader_url": uploader_url,
            "channel": uploader,
            "channel_url": uploader_url,
            "duration": duration,
            "view_count": item.get("playback_count") if item.get("playback_count") is not None else item.get("view_count"),
            "playback_count": item.get("playback_count"),
            "created_at": item.get("created_at"),
            "timestamp": item.get("timestamp"),
            "media": media,
            "transcodings": transcodings,
        }

    def _configure_fast_soundcloud_ydl(self, ydl):
        """Ускоряет поиск и списки SoundCloud в ~50–100 раз: берёт метаданные и обложки прямо из ответа API v2 без 120 запросов к потокам."""
        if self.source != "soundcloud" or not type(ydl).__module__.startswith("yt_dlp"):
            return
        try:
            from yt_dlp.extractor import soundcloud as sc_mod
        except Exception:
            return
        sc_ie_cls = getattr(sc_mod, "SoundcloudIE", None)
        if sc_ie_cls is not None and SearchWorker._SOUNDCLOUD_CACHED_CLIENT_ID and not getattr(sc_ie_cls, "_CLIENT_ID", None):
            sc_ie_cls._CLIENT_ID = SearchWorker._SOUNDCLOUD_CACHED_CLIENT_ID

        item_by_id = {}
        item_by_url = {}

        def remember_item(raw):
            if not isinstance(raw, dict):
                return
            candidate = raw.get("track") if isinstance(raw.get("track"), dict) else raw
            converted = self._soundcloud_item_to_entry(candidate)
            if not converted:
                return
            if converted.get("id"):
                item_by_id[str(converted["id"])] = converted
            if converted.get("permalink_url"):
                item_by_url[converted["permalink_url"]] = converted
                item_by_url[converted["permalink_url"].rstrip("/")] = converted

        def wrap_extractor(ie):
            if getattr(ie, "_aurora_sc_fast_wrapped", False):
                return ie
            ie._aurora_sc_fast_wrapped = True
            orig_download_json = ie._download_json

            def fast_download_json(*args, **kwargs):
                res = orig_download_json(*args, **kwargs)
                if sc_ie_cls is not None and getattr(sc_ie_cls, "_CLIENT_ID", None):
                    SearchWorker._SOUNDCLOUD_CACHED_CLIENT_ID = sc_ie_cls._CLIENT_ID
                if isinstance(res, dict):
                    collection = res.get("collection")
                    if isinstance(collection, list):
                        for element in collection:
                            remember_item(element)
                    tracks_list = res.get("tracks")
                    if isinstance(tracks_list, list):
                        for element in tracks_list:
                            remember_item(element)
                    remember_item(res)
                elif isinstance(res, list):
                    for element in res:
                        remember_item(element)
                return res

            ie._download_json = fast_download_json

            if hasattr(ie, "_extract_info_dict"):
                orig_extract_info_dict = ie._extract_info_dict

                def fast_extract_info_dict(info, full_title=None, quiet=False, secret_token=None, *args, **kwargs):
                    remember_item(info)
                    converted = self._soundcloud_item_to_entry(info)
                    if converted:
                        return converted
                    try:
                        return orig_extract_info_dict(
                            info, full_title=full_title, quiet=quiet,
                            secret_token=secret_token, *args, **kwargs
                        )
                    except TypeError:
                        return orig_extract_info_dict(info, full_title=full_title, secret_token=secret_token)

                ie._extract_info_dict = fast_extract_info_dict

            orig_url_result = ie.url_result

            def fast_url_result(url, *args, **kwargs):
                if isinstance(url, dict):
                    remember_item(url)
                    converted = self._soundcloud_item_to_entry(url)
                    if converted:
                        return converted
                result = orig_url_result(url, *args, **kwargs)
                if not isinstance(result, dict):
                    return result
                url_str = str(url or result.get("url") or "")
                matched = item_by_url.get(url_str) or item_by_url.get(url_str.rstrip("/"))
                if not matched:
                    tail_match = re.search(r"(?:/tracks/(?:soundcloud:tracks:)?|soundcloud:tracks:)(\d+)", url_str)
                    if tail_match:
                        matched = item_by_id.get(tail_match.group(1))
                if not matched:
                    cand_id = str(kwargs.get("id") or kwargs.get("video_id") or result.get("id") or "")
                    if cand_id:
                        matched = item_by_id.get(cand_id)
                if matched:
                    enriched = dict(result)
                    enriched.update(matched)
                    enriched["_type"] = "url"
                    return enriched
                return result

            ie.url_result = fast_url_result
            return ie

        orig_get_info_extractor = ydl.get_info_extractor

        def fast_get_info_extractor(ie_key):
            ie = orig_get_info_extractor(ie_key)
            if isinstance(ie_key, str) and "soundcloud" in ie_key.casefold():
                return wrap_extractor(ie)
            return ie

        ydl.get_info_extractor = fast_get_info_extractor

    def _fetch_soundcloud_direct_api(self, limit):
        """Прямой быстрый запрос к SoundCloud API v2 на случай, если экстрактор yt-dlp вернул пустой список."""
        if not self.query or self.direct_url or requests is None:
            return []
        try:
            from yt_dlp.extractor import soundcloud as sc_mod
            sc_ie_cls = getattr(sc_mod, "SoundcloudIE", None)
        except Exception:
            sc_ie_cls = None

        client_id = SearchWorker._SOUNDCLOUD_CACHED_CLIENT_ID or (
            getattr(sc_ie_cls, "_CLIENT_ID", None) if sc_ie_cls is not None else None
        )
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Referer": "https://soundcloud.com/",
            "Origin": "https://soundcloud.com",
        }
        session = _create_keepalive_stream_session(prefer_ipv4=False)
        if session is None:
            return []
        try:
            if not client_id:
                home_resp = session.get("https://soundcloud.com/", headers=headers, timeout=(3.5, 5.0))
                if home_resp.status_code == 200:
                    scripts = re.findall(r'src="(https://a-v2\.sndcdn\.com/assets/[^"]+\.js)"', home_resp.text)
                    for script_url in reversed(scripts[-4:]):
                        if self._cancel_requested:
                            return []
                        js_resp = session.get(script_url, headers=headers, timeout=(3.0, 4.5))
                        if js_resp.status_code == 200:
                            m = re.search(r'client_id\s*:\s*"([0-9a-zA-Z]{32})"', js_resp.text)
                            if m:
                                client_id = m.group(1)
                                SearchWorker._SOUNDCLOUD_CACHED_CLIENT_ID = client_id
                                if sc_ie_cls is not None:
                                    sc_ie_cls._CLIENT_ID = client_id
                                break
            if not client_id:
                return []

            for attempt in range(2):
                api_url = (
                    f"https://api-v2.soundcloud.com/search/tracks"
                    f"?q={quote_plus(self.query)}&client_id={client_id}"
                    f"&limit={max(1, min(int(limit), 50))}&offset=0"
                )
                resp = session.get(api_url, headers=headers, timeout=(4.0, 5.5))
                if resp.status_code in (401, 403) and attempt == 0:
                    SearchWorker._SOUNDCLOUD_CACHED_CLIENT_ID = None
                    client_id = None
                    home_resp = session.get("https://soundcloud.com/", headers=headers, timeout=(3.5, 5.0))
                    if home_resp.status_code == 200:
                        scripts = re.findall(r'src="(https://a-v2\.sndcdn\.com/assets/[^"]+\.js)"', home_resp.text)
                        for script_url in reversed(scripts[-4:]):
                            js_resp = session.get(script_url, headers=headers, timeout=(3.0, 4.5))
                            if js_resp.status_code == 200:
                                m = re.search(r'client_id\s*:\s*"([0-9a-zA-Z]{32})"', js_resp.text)
                                if m:
                                    client_id = m.group(1)
                                    SearchWorker._SOUNDCLOUD_CACHED_CLIENT_ID = client_id
                                    break
                    if not client_id:
                        break
                    continue
                if resp.status_code == 200:
                    payload = resp.json()
                    collection = payload.get("collection") if isinstance(payload, dict) else None
                    if isinstance(collection, list):
                        entries = []
                        for item in collection:
                            converted = self._soundcloud_item_to_entry(item)
                            if converted:
                                entries.append(converted)
                        return entries
                break
        except Exception:
            pass
        finally:
            try:
                session.close()
            except Exception:
                pass
        return []

    def _configure_fast_youtube_ydl(self, ydl, emit_progress, limit, progress_state):
        """Отправляет первые результаты поиска YouTube сразу после первой страницы (~0.4 с), не дожидаясь загрузки всех страниц continuation."""
        if self.source != "youtube" or not type(ydl).__module__.startswith("yt_dlp"):
            return
        preview_tracks = []
        preview_visited = set()
        threshold = min(8, max(1, int(limit) - 1))

        def wrap_yt_extractor(ie):
            if getattr(ie, "_aurora_yt_fast_wrapped", False):
                return ie
            ie._aurora_yt_fast_wrapped = True
            orig_url_result = ie.url_result

            def fast_yt_url_result(url, *args, **kwargs):
                if self._cancel_requested:
                    raise RuntimeError("Поиск заменён новым запросом.")
                res = orig_url_result(url, *args, **kwargs)
                if emit_progress and not progress_state.get("sent") and isinstance(res, dict) and threshold > 0:
                    track = self._make_track(res, preview_visited)
                    if track and (not self.artist_filter or self._matches_artist_filter(track)):
                        preview_tracks.append(track)
                        if len(preview_tracks) >= threshold and int(limit) > threshold:
                            progress_state["sent"] = True
                            logging.getLogger("aurora").info(
                                "Первые результаты (ранний поток): source=%s; count=%d; seconds=%.1f",
                                self.source, len(preview_tracks),
                                time.perf_counter() - getattr(self, "_search_started_at", time.perf_counter()),
                            )
                            self.results_ready.emit(
                                [dict(item) for item in preview_tracks],
                                f"Первые {len(preview_tracks)} результатов готовы; загружаю остальные…",
                            )
                return res

            ie.url_result = fast_yt_url_result
            return ie

        orig_get_info_extractor = ydl.get_info_extractor

        def fast_get_info_extractor(ie_key):
            ie = orig_get_info_extractor(ie_key)
            if isinstance(ie_key, str) and "youtube" in ie_key.casefold():
                return wrap_yt_extractor(ie)
            return ie

        ydl.get_info_extractor = fast_get_info_extractor

    def _fetch(self, limit, mode="in_playlist", emit_progress=False, force_search=False, playlist_start=1):
        # Один сетевой запрос вместо отдельного запроса на 12 результатов и
        # повторного запроса на 25/50/100. Плоская выдача не открывает каждое видео.
        extract_flat_mode = mode
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
            "socket_timeout": 8 if self.paginate_all else (6 if self.source == "soundcloud" else 5),
            "retries": 1,
            "extractor_retries": 1,
            "cachedir": None if self.source == "soundcloud" else False,
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

        progress_state = {"sent": False}
        is_real_ydl = False
        try:
            with YoutubeDL(options) as ydl:
                is_real_ydl = type(ydl).__module__.startswith("yt_dlp")
                self._configure_fast_soundcloud_ydl(ydl)
                self._configure_fast_youtube_ydl(ydl, emit_progress, limit, progress_state)
                data = ydl.extract_info(target, download=False)
        except Exception as error:
            if self._cancel_requested:
                return [], "Поиск заменён новым запросом."
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
                if self.source == "soundcloud" and not self.direct_url and is_real_ydl:
                    direct_entries = self._fetch_soundcloud_direct_api(limit)
                    if direct_entries:
                        data = {"entries": direct_entries}
                    else:
                        raise
                else:
                    raise
            else:
                fallback_options = dict(options)
                fallback_options.pop("cookiefile", None)
                fallback_options.pop("cookiesfrombrowser", None)
                with YoutubeDL(fallback_options) as ydl:
                    self._configure_fast_soundcloud_ydl(ydl)
                    self._configure_fast_youtube_ydl(ydl, emit_progress, limit, progress_state)
                    data = ydl.extract_info(target, download=False)

        if (self.source == "soundcloud" and not self.direct_url and is_real_ydl
                and (not isinstance(data, dict) or not data.get("entries"))):
            direct_entries = self._fetch_soundcloud_direct_api(limit)
            if direct_entries:
                data = {"entries": direct_entries}

        if not isinstance(data, dict) or data.get("entries") is None:
            return [], "Источник не вернул список результатов."

        tracks, visited = [], set()
        filtered_out = 0
        progress_sent = bool(progress_state.get("sent"))
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
                    logging.getLogger("aurora").info("Первые результаты: source=%s; count=%d; seconds=%.1f",
                                                   self.source, len(tracks),
                                                   time.perf_counter() - getattr(self, "_search_started_at", time.perf_counter()))
                    self.results_ready.emit(
                        [dict(item) for item in tracks],
                        f"Первые {len(tracks)} результатов готовы; загружаю остальные…"
                    )
        if not tracks and self.source == "soundcloud" and not self.direct_url and is_real_ydl and not self._cancel_requested:
            for entry in self._fetch_soundcloud_direct_api(limit):
                track = self._make_track(entry, visited)
                if track:
                    if self.artist_filter and not self._matches_artist_filter(track):
                        continue
                    tracks.append(track)
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

    @staticmethod
    def _clean_radio_text(value):
        text = " ".join(str(value or "").split()).strip()
        if not text:
            return ""
        lowered = text.casefold()
        placeholders = {
            "исполнитель неизвестен",
            "без названия",
            "неизвестный исполнитель",
            "выбранный трек",
            "unknown artist",
            "unknown",
            "untitled",
            "track",
        }
        if lowered in placeholders or lowered.isdigit():
            return ""
        return text

    @classmethod
    def _radio_song_signature(cls, track):
        """Строит каноническую сигнатуру (artist_norm, title_norm) для отсечения перезаливов одной и той же песни."""
        if not isinstance(track, dict):
            return ("", "")
        raw_title = cls._clean_radio_text(track.get("title"))
        raw_artist = cls._clean_radio_text(
            track.get("artist_display") or track.get("artist")
            or track.get("uploader") or track.get("channel") or track.get("creator")
        )
        cleaned_title = unicodedata.normalize("NFKC", raw_title)
        noise_pattern = (
            r"[\(\[\{][^\)\]\}]*\b(?:"
            r"official\s*(?:music\s*)?(?:video|audio|lyric\s*video|visualizer)?|"
            r"music\s*video|lyric\s*video|lyrics?|audio|visualizer|live|hd|hq|4k|"
            r"remaster(?:ed)?|slowed(?:\s*\+\s*reverb)?|reverb|sped\s*up|speed\s*up|"
            r"nightcore|bass\s*boosted|instrumental|karaoke|cover|ost|"
            r"клип|официальн\w*\s*(?:видео|аудио|клип)|текст(?:\s*песни)?|премьера|"
            r"prod\.?\s*by[^\)\]\}]*"
            r")\b[^\)\]\}]*[\)\]\}]"
        )
        cleaned_title = re.sub(noise_pattern, " ", cleaned_title, flags=re.IGNORECASE)
        cleaned_title = re.sub(
            r"\b(?:official\s*(?:music\s*)?(?:video|audio)|lyric\s*video|lyrics|visualizer|"
            r"slowed(?:\s*\+\s*reverb)?|sped\s*up|speed\s*up|nightcore|bass\s*boosted|"
            r"prod\.?\s*by\s+\S+)\b",
            " ",
            cleaned_title,
            flags=re.IGNORECASE,
        )
        cleaned_title = " ".join(cleaned_title.split()).strip(" -–—|:")
        artist_part = raw_artist
        title_part = cleaned_title
        if re.search(r"\s+[-–—]\s+", cleaned_title):
            left, right = re.split(r"\s+[-–—]\s+", cleaned_title, maxsplit=1)
            left = left.strip()
            right = right.strip()
            if left and right:
                left_norm = cls._normalize_artist_name(left)
                artist_norm = cls._normalize_artist_name(raw_artist)
                if not artist_norm or left_norm == artist_norm or left_norm in artist_norm or artist_norm in left_norm:
                    artist_part = left
                    title_part = right
                else:
                    # В YouTube и SoundCloud название вида «Artist - Song» у стороннего канала-загрузчика
                    artist_part = left
                    title_part = right
        title_part = re.sub(r"\b(?:feat(?:uring)?\.?|ft\.?)\s+.*$", " ", title_part, flags=re.IGNORECASE)
        artist_parts = cls._artist_credit_parts(artist_part)
        primary_artist = artist_parts[0] if artist_parts else artist_part
        artist_sig = cls._normalize_artist_name(primary_artist)
        title_sig = cls._normalize_artist_name(title_part)
        return (artist_sig, title_sig)

    @staticmethod
    def _extract_soundcloud_slug_parts(url):
        try:
            parsed = urlsplit(str(url or "").strip())
        except Exception:
            return ("", "", "")
        host = (parsed.netloc or "").casefold()
        if "soundcloud.com" not in host or "api" in host:
            return ("", "", "")
        parts = [p for p in (parsed.path or "").split("/") if p]
        if len(parts) < 2:
            return ("", "", "")
        if parts[0].casefold() in ("discover", "charts", "search", "you", "stations", "stream"):
            return ("", "", "")
        if parts[1].casefold() in ("sets", "likes", "tracks", "albums", "reposts", "recommended"):
            return ("", "", "")
        permalink = f"https://soundcloud.com/{parts[0]}/{parts[1]}"
        user_guess = parts[0].replace("-", " ").replace("_", " ").strip()
        title_guess = parts[1].replace("-", " ").replace("_", " ").strip()
        return (permalink, user_guess, title_guess)

    def _filter_and_diversify_radio_tracks(self, candidate_groups, seed_track):
        """Отсекает дубликаты, перезаливы исходного трека, длинные компиляции и перемешивает выдачу."""
        seed_url = str((seed_track or {}).get("url") or "").strip()
        seed_key = f"{self.source}|{seed_url}" if seed_url else ""
        seed_vid = YouTubeRatingWorker._video_id(seed_track or {}) if self.source == "youtube" else ""
        seed_sig = self._radio_song_signature(seed_track or {})
        seed_artist_sig, seed_title_sig = seed_sig
        try:
            seed_duration = float((seed_track or {}).get("duration") or 0)
        except (TypeError, ValueError):
            seed_duration = 0.0
        max_allowed_duration = max(1200.0, seed_duration * 2.5) if seed_duration > 0 else 1200.0

        seen_keys = set(self.radio_excluded_keys)
        if seed_key:
            seen_keys.add(seed_key)
        if seed_vid:
            seen_keys.add(seed_vid)
            seen_keys.add(f"youtube|https://www.youtube.com/watch?v={seed_vid}")
            seen_keys.add(f"youtube|https://music.youtube.com/watch?v={seed_vid}")

        seen_sigs = set(self.radio_excluded_signatures)
        if seed_title_sig:
            seen_sigs.add(seed_sig)
        seen_titles = {seed_title_sig} if len(seed_title_sig) >= 3 else set()
        for existing_sig in self.radio_excluded_signatures:
            if isinstance(existing_sig, tuple) and len(existing_sig) == 2 and len(existing_sig[1]) >= 4:
                seen_titles.add(existing_sig[1])

        fresh_pool = []
        recent_pool = []
        rng = random.Random(f"{time.time_ns()}:{self.radio_round}:{seed_url}:{self.query}")

        for group in candidate_groups:
            if not group:
                continue
            items = list(group)
            # Мягкое перемешивание внутри каждой группы кандидатов, чтобы повторный
            # запуск радио никогда не выдавал статичный одинаковый порядок.
            if len(items) > 2:
                band_size = 6
                shuffled_items = []
                for idx in range(0, len(items), band_size):
                    band = items[idx:idx + band_size]
                    rng.shuffle(band)
                    shuffled_items.extend(band)
                items = shuffled_items

            for track in items:
                if not isinstance(track, dict):
                    continue
                url = str(track.get("url") or "").strip()
                if not url:
                    continue
                key = f"{track.get('source', self.source)}|{url}"
                vid = YouTubeRatingWorker._video_id(track) if self.source == "youtube" else ""
                if key in seen_keys or (vid and vid in seen_keys):
                    continue
                try:
                    dur = float(track.get("duration") or 0)
                except (TypeError, ValueError):
                    dur = 0.0
                if dur > max_allowed_duration:
                    continue
                if 0 < dur < 35:
                    continue

                sig = self._radio_song_signature(track)
                artist_sig, title_sig = sig
                if not title_sig:
                    continue
                # Исключаем перезаливы, ремиксы, slowed/lyrics-версии самого трека, по которому запущено радио.
                if seed_title_sig and len(seed_title_sig) >= 3:
                    if title_sig == seed_title_sig:
                        continue
                    if len(seed_title_sig) >= 5 and (seed_title_sig in title_sig or title_sig in seed_title_sig):
                        if not seed_artist_sig or not artist_sig or artist_sig == seed_artist_sig:
                            continue
                if sig in seen_sigs:
                    continue
                if len(title_sig) >= 4 and title_sig in seen_titles:
                    continue

                seen_keys.add(key)
                if vid:
                    seen_keys.add(vid)
                seen_sigs.add(sig)
                if len(title_sig) >= 4:
                    seen_titles.add(title_sig)

                was_recent = (
                    key in self.radio_recent_keys
                    or (vid and vid in self.radio_recent_keys)
                    or f"sig:{artist_sig}|{title_sig}" in self.radio_recent_keys
                )
                if was_recent:
                    recent_pool.append((artist_sig, dict(track)))
                else:
                    fresh_pool.append((artist_sig, dict(track)))

        def interleave_by_artist(pairs):
            if len(pairs) <= 2:
                return [t for _, t in pairs]
            # Разводим треки одного и того же исполнителя, чтобы в очереди не шло
            # 15 песен подряд от одного канала/автора.
            max_same_in_row = 2 if self.radio_artist_context else 1
            remaining = deque(pairs)
            ordered = []
            recent_artists = deque(maxlen=max_same_in_row)
            defer_limit = len(remaining) * 2
            deferred = 0
            while remaining:
                artist_sig, track = remaining.popleft()
                if (artist_sig and len(recent_artists) == max_same_in_row
                        and all(a == artist_sig for a in recent_artists)
                        and deferred < defer_limit
                        and any(a != artist_sig for a, _ in remaining)):
                    remaining.append((artist_sig, track))
                    deferred += 1
                    continue
                deferred = 0
                ordered.append(track)
                recent_artists.append(artist_sig)
            return ordered

        rng.shuffle(recent_pool)
        result = interleave_by_artist(fresh_pool)
        if len(result) < self.limit and recent_pool:
            result.extend(interleave_by_artist(recent_pool))
        return result[:self.limit]

    def _fetch_radio_tracks(self):
        """Собирает разнообразное радио по конкретному треку для YouTube и SoundCloud."""
        seed = dict(self.radio_seed_track or {})
        seed_url = str(seed.get("url") or "").strip()
        seed_artist = self._clean_radio_text(
            seed.get("artist_display") or seed.get("artist")
            or seed.get("uploader") or seed.get("channel")
        )
        seed_title = self._clean_radio_text(seed.get("title"))
        artist_context = self._clean_radio_text(self.radio_artist_context)
        if re.search(r"\s+[-–—]\s+", seed_title):
            left, right = re.split(r"\s+[-–—]\s+", seed_title, maxsplit=1)
            if left.strip() and right.strip():
                if not seed_artist:
                    seed_artist = left.strip()
                seed_title = right.strip()

        candidate_groups = []
        notes = []
        rng = random.Random(f"{time.time_ns()}:{self.radio_round}:{seed_url}")

        if self.source == "youtube":
            video_id = YouTubeRatingWorker._video_id(seed)
            # 1) Настоящий алгоритмический радио-микс YouTube Music по videoId.
            try:
                from ytmusicapi import YTMusic
                ytm = YTMusic()
                if not video_id and (seed_artist or seed_title):
                    search_q = f"{seed_artist} {seed_title}".strip()
                    found = ytm.search(search_q, filter="songs", limit=5) or []
                    for item in found:
                        cand_id = str((item or {}).get("videoId") or "").strip()
                        if cand_id:
                            video_id = cand_id
                            break

                if video_id and not self._cancel_requested:
                    watch = ytm.get_watch_playlist(videoId=video_id, radio=True, limit=max(50, self.limit)) or {}
                    raw_watch = watch.get("tracks") or []
                    primary_group = []
                    pivot_ids = []
                    seed_artist_norm = self._normalize_artist_name(seed_artist)
                    for entry in raw_watch:
                        if self._cancel_requested:
                            break
                        norm = SupermixWorker._normalize_track(entry)
                        if not norm:
                            continue
                        primary_group.append(norm)
                        vid = str(norm.get("video_id") or "").strip()
                        if vid and vid != video_id:
                            cand_artist_norm = self._normalize_artist_name(norm.get("artist"))
                            if cand_artist_norm != seed_artist_norm or len(pivot_ids) < 3:
                                pivot_ids.append(vid)
                    if primary_group:
                        candidate_groups.append(primary_group)
                        notes.append("Радио-микс YouTube Music по выбранному треку.")
                        preview = self._filter_and_diversify_radio_tracks(candidate_groups, seed)
                        if len(preview) >= 8 and not self._cancel_requested:
                            self.results_ready.emit(
                                [dict(item) for item in preview],
                                f"Найдено {len(preview)} похожих треков; расширяю подборку…"
                            )

                    # 2) Вторая волна по связанному треку из радио-плейлиста для свежести и разнообразия.
                    if pivot_ids and not self._cancel_requested:
                        rng.shuffle(pivot_ids)
                        chosen_pivots = pivot_ids[:2] if self.radio_round > 0 else pivot_ids[:1]
                        for pivot_id in chosen_pivots:
                            if self._cancel_requested:
                                break
                            try:
                                watch2 = ytm.get_watch_playlist(videoId=pivot_id, radio=True, limit=40) or {}
                                second_group = []
                                for entry in watch2.get("tracks") or []:
                                    norm = SupermixWorker._normalize_track(entry)
                                    if norm:
                                        second_group.append(norm)
                                if second_group:
                                    candidate_groups.append(second_group)
                            except Exception:
                                pass
            except Exception as ytm_err:
                logging.getLogger("aurora").info("YTMusic radio watch_playlist fallback: %s", ytm_err)

            # 3) Запасной вариант через нативный плейлист YouTube Mix RD<video_id> в yt-dlp.
            current_filtered = self._filter_and_diversify_radio_tracks(candidate_groups, seed)
            if len(current_filtered) < 25 and video_id and not self._cancel_requested:
                saved_direct = self.direct_url
                try:
                    self.direct_url = f"https://www.youtube.com/watch?v={video_id}&list=RD{video_id}"
                    mix_tracks, _ = self._fetch(min(50, self.limit), "in_playlist", emit_progress=False)
                    if mix_tracks:
                        candidate_groups.append(mix_tracks)
                        notes.append("Микс YouTube по выбранному треку.")
                except Exception:
                    pass
                finally:
                    self.direct_url = saved_direct

            # 4) Дополнительные разнообразные поисковые запросы, если радио-плейлист вернул мало новых песен.
            current_filtered = self._filter_and_diversify_radio_tracks(candidate_groups, seed)
            if len(current_filtered) < 20 and not self._cancel_requested:
                queries = []
                target_artist = artist_context or seed_artist
                if target_artist and seed_title:
                    queries.extend([
                        f"songs similar to {seed_title} {target_artist}",
                        f"{target_artist} popular songs",
                        f"{target_artist} radio mix",
                        f"{target_artist} best tracks",
                    ])
                elif target_artist:
                    queries.extend([
                        f"{target_artist} popular songs",
                        f"{target_artist} best tracks",
                        f"{target_artist} radio mix",
                    ])
                elif seed_title:
                    queries.extend([
                        f"songs similar to {seed_title}",
                        f"{seed_title} radio",
                    ])
                if not queries:
                    queries = [self.query or "popular music hits"]
                rng.shuffle(queries)
                saved_query, saved_direct = self.query, self.direct_url
                try:
                    self.direct_url = ""
                    for q in queries[:2]:
                        if self._cancel_requested:
                            break
                        self.query = q
                        found_tracks, _ = self._fetch(45, "in_playlist", emit_progress=False, force_search=True)
                        if found_tracks:
                            candidate_groups.append(found_tracks)
                except Exception:
                    pass
                finally:
                    self.query, self.direct_url = saved_query, saved_direct

        elif self.source == "soundcloud":
            permalink, slug_user, slug_title = self._extract_soundcloud_slug_parts(seed_url)
            seed_genre = self._clean_radio_text(seed.get("genre"))
            if not seed_artist and slug_user:
                seed_artist = slug_user
            if not seed_title and slug_title:
                seed_title = slug_title

            # Если у трека из кэша SoundCloud не было названия/автора или permalink, быстро догружаем метаданные.
            if seed_url and (not permalink or not seed_title or not seed_artist) and not self._cancel_requested:
                try:
                    meta_opts = {
                        **yt_dlp_tls_options(),
                        "quiet": True,
                        "no_warnings": True,
                        "skip_download": True,
                        "noplaylist": True,
                        "extract_flat": False,
                        "socket_timeout": 5,
                        "retries": 1,
                        "extractor_retries": 1,
                        "cachedir": None,
                        "ignoreconfig": True,
                    }
                    with YoutubeDL(meta_opts) as ydl:
                        self._configure_fast_soundcloud_ydl(ydl)
                        info = ydl.extract_info(seed_url, download=False)
                    if isinstance(info, dict):
                        resolved_url = str(info.get("webpage_url") or info.get("permalink_url") or "").strip()
                        if resolved_url:
                            p_url, p_user, p_title = self._extract_soundcloud_slug_parts(resolved_url)
                            if p_url:
                                permalink = p_url
                            if not seed_artist and p_user:
                                seed_artist = p_user
                            if not seed_title and p_title:
                                seed_title = p_title
                        info_title = self._clean_radio_text(info.get("title"))
                        info_artist = self._clean_radio_text(
                            info.get("artist") or info.get("uploader") or info.get("channel")
                        )
                        info_genre = self._clean_radio_text(info.get("genre"))
                        if info_title:
                            seed_title = info_title
                            seed["title"] = info_title
                        if info_artist:
                            seed_artist = info_artist
                            seed["artist"] = info_artist
                        if info_genre:
                            seed_genre = info_genre
                except Exception:
                    pass

            # 1) Нативная станция похожих треков SoundCloud (/recommended -> /tracks/{id}/related).
            if permalink and not self._cancel_requested:
                saved_direct = self.direct_url
                try:
                    self.direct_url = permalink.rstrip("/") + "/recommended"
                    related_tracks, _ = self._fetch(max(50, self.limit), "in_playlist", emit_progress=False)
                    if related_tracks:
                        candidate_groups.append(related_tracks)
                        notes.append("Рекомендации SoundCloud по выбранному треку.")
                        preview = self._filter_and_diversify_radio_tracks(candidate_groups, seed)
                        if len(preview) >= 6 and not self._cancel_requested:
                            self.results_ready.emit(
                                [dict(item) for item in preview],
                                f"Найдено {len(preview)} похожих треков SoundCloud; расширяю подборку…"
                            )
                        # При повторном запуске или пополнении берём также рекомендации от одного из связанных треков.
                        if (self.radio_round > 0 or len(preview) < 25) and not self._cancel_requested:
                            pivot_permalinks = []
                            for rel in related_tracks[:12]:
                                rel_perm, _, _ = self._extract_soundcloud_slug_parts(rel.get("url"))
                                if rel_perm and rel_perm.casefold() != permalink.casefold():
                                    pivot_permalinks.append(rel_perm)
                            if pivot_permalinks:
                                rng.shuffle(pivot_permalinks)
                                self.direct_url = pivot_permalinks[0].rstrip("/") + "/recommended"
                                rel2, _ = self._fetch(40, "in_playlist", emit_progress=False)
                                if rel2:
                                    candidate_groups.append(rel2)
                except Exception as sc_rel_err:
                    logging.getLogger("aurora").info("SoundCloud /recommended fallback: %s", sc_rel_err)
                finally:
                    self.direct_url = saved_direct

            # 2) Разнообразный поиск по артисту/жанру/связанным трекам (с отсечением дублей самой песни).
            current_filtered = self._filter_and_diversify_radio_tracks(candidate_groups, seed)
            if len(current_filtered) < 25 and not self._cancel_requested:
                target_artist = artist_context or seed_artist
                queries = []
                if target_artist and seed_genre:
                    queries.append(f"{target_artist} {seed_genre}")
                if target_artist:
                    queries.extend([
                        f"{target_artist} tracks",
                        f"{target_artist} popular",
                        f"{target_artist} mix",
                    ])
                if seed_title and target_artist:
                    queries.append(f"{target_artist} {seed_title}")
                elif seed_title:
                    queries.append(f"{seed_title} mix")
                if seed_genre:
                    queries.append(f"{seed_genre} music")
                if not queries:
                    queries = [self._clean_radio_text(self.query) or "electronic music"]
                rng.shuffle(queries)
                saved_query, saved_direct = self.query, self.direct_url
                try:
                    self.direct_url = ""
                    for q in queries[:2]:
                        if self._cancel_requested:
                            break
                        self.query = q
                        found_tracks, _ = self._fetch(50, "in_playlist", emit_progress=False, force_search=True)
                        if found_tracks:
                            candidate_groups.append(found_tracks)
                except Exception:
                    pass
                finally:
                    self.query, self.direct_url = saved_query, saved_direct

        final_tracks = self._filter_and_diversify_radio_tracks(candidate_groups, seed)
        summary_note = " ".join(dict.fromkeys(n for n in notes if n)).strip() or "Подборка похожих треков готова."
        return final_tracks, summary_note

    def run(self):
        self._search_started_at = time.perf_counter()
        logging.getLogger("aurora").info("Поиск начат: source=%s; limit=%d", self.source, self.limit)
        try:
            if self.paginate_all:
                self._run_paginated()
                return
            if self.radio_seed_track is not None:
                tracks, note = self._fetch_radio_tracks()
                if self._cancel_requested:
                    return
                if tracks:
                    self.results_ready.emit(tracks, note or "Радио готово.")
                else:
                    self.results_ready.emit([], note or "Источник не вернул подходящих треков для радио.")
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

        finally:
            logging.getLogger("aurora").info("Поиск завершён: source=%s; seconds=%.1f; cancelled=%s",
                                           self.source, time.perf_counter() - self._search_started_at,
                                           self._cancel_requested)


class YouTubeMusicAuth:
    """Общая авторизация каталога и лайков через существующее подключение."""

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

    _BROWSER_COOKIE_CACHE = {}
    _BROWSER_COOKIE_TTL = 900.0

    @classmethod
    def invalidate_browser_cookie_cache(cls, browser_spec=None):
        if browser_spec is None:
            cls._BROWSER_COOKIE_CACHE.clear()
        else:
            cls._BROWSER_COOKIE_CACHE.pop(str(browser_spec or "").strip(), None)

    def _cookies_from_browser(self):
        if not self.browser_spec:
            raise RuntimeError("Не выбран браузерный профиль YouTube Music.")
        spec_key = str(self.browser_spec).strip()
        now = time.monotonic()
        cached = self._BROWSER_COOKIE_CACHE.get(spec_key)
        if cached and (now - cached[0]) < self._BROWSER_COOKIE_TTL and cached[1]:
            return cached[1]
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
            header = self._cookie_header_from_pairs(pairs)
            if header and "__Secure-3PAPISID=" in header:
                self._BROWSER_COOKIE_CACHE[spec_key] = (now, header)
            return header
        except Exception as error:
            raise RuntimeError(
                "Не удалось прочитать cookies выбранного браузера. Полностью закрой Waterfox и его фоновые "
                "процессы, проверь путь профиля и повтори. Если ошибка останется, подключи свежий cookies.txt. "
                f"Подробности: {str(error)[:240]}"
            ) from error

    def _auth_headers(self):
        cookie_header = (self._cookies_from_browser() if self.auth_mode == "browser"
                         else self._cookies_from_file())
        if "__Secure-3PAPISID=" not in cookie_header:
            raise RuntimeError(
                "В cookies для music.youtube.com нет __Secure-3PAPISID. "
                "Обнови cookies из браузера, где выполнен вход в YouTube Music."
            )
        from ytmusicapi.helpers import get_authorization, sapisid_from_cookie, initialize_headers
        origin = "https://music.youtube.com"
        sapisid = sapisid_from_cookie(cookie_header)
        # Минимальный BROWSER auth; ytmusicapi обновляет SAPISIDHASH сама.
        return {
            "user-agent": initialize_headers().get("user-agent", "Mozilla/5.0"),
            "accept": "*/*", "content-type": "application/json",
            "origin": origin, "x-origin": origin, "referer": origin + "/",
            "x-goog-authuser": "0", "cookie": cookie_header,
            "authorization": get_authorization(f"{sapisid} {origin}"),
        }


class YouTubeRatingWorker(QThread, YouTubeMusicAuth):
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

            headers = self._auth_headers()
            import requests
            from ytmusicapi import YTMusic, LikeStatus

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


class SupermixWorker(QThread, YouTubeMusicAuth):
    """Загружает My Supermix подключённого аккаунта или продолжение того же микса.

    API-последовательность соответствует cloudmus: get_home → playlistId,
    затем get_watch_playlist с сохранённым playlistId и последним дослушанным videoId.
    Историю аккаунта этот worker не изменяет.
    """
    result_ready = pyqtSignal(list, dict)
    failed = pyqtSignal(str)
    REQUEST_BUDGET_SECONDS = 30
    MIX_ID_PREFIX = "RDTMAK5uy_"
    ALT_MIX_PREFIX = "RDCLAK5uy_"
    MIX_KEY_ALIASES = {
        "supermix": ("my supermix", "мой супермикс", "супермикс"),
        "my_mix_1": ("my mix 1", "мой микс 1", "микс 1"),
        "my_mix_2": ("my mix 2", "мой микс 2", "микс 2"),
        "my_mix_3": ("my mix 3", "мой микс 3", "микс 3"),
        "discover_mix": ("discover mix", "микс открытий", "открытия"),
        "new_release_mix": ("new release mix", "новинки", "новые релизы"),
        "replay_mix": ("replay mix", "archive mix", "on repeat", "на повторе", "архивный микс"),
    }

    def __init__(self, auth_mode, cookie_file="", browser_spec="", parent=None,
                 mix_id="", anchor="", excluded_ids=None, limit=25, mix_key="supermix",
                 known_mix_id="", known_cover_url=""):
        super().__init__(parent)
        self.auth_mode = str(auth_mode or "file")
        self.cookie_file = str(cookie_file or "").strip()
        self.browser_spec = str(browser_spec or "").strip()
        self.mix_id = str(mix_id or "")
        self.known_mix_id = str(known_mix_id or "").strip()
        self.known_cover_url = str(known_cover_url or "").strip()
        self.mix_key = str(mix_key or "supermix").strip() or "supermix"
        self.anchor = str(anchor or "")
        self.excluded_ids = set(excluded_ids or ())
        self.limit = max(1, min(50, int(limit)))
        self._cancelled = threading.Event()

    def cancel(self):
        self._cancelled.set()

    @classmethod
    def _find_supermix(cls, shelves):
        supermix_candidates = []
        for shelf in shelves or []:
            if not isinstance(shelf, dict):
                continue
            for item in shelf.get("contents") or []:
                if not isinstance(item, dict):
                    continue
                pid = str(item.get("playlistId") or "").strip()
                if not (pid.startswith(cls.MIX_ID_PREFIX) or pid.startswith(cls.ALT_MIX_PREFIX)):
                    continue
                title = str(item.get("title") or "").strip().casefold()
                if any(title == alias or alias in title for alias in ("my supermix", "мой супермикс", "супермикс", "supermix")):
                    return item
                supermix_candidates.append(item)
        for item in supermix_candidates:
            pid = str(item.get("playlistId") or "").strip()
            if pid.startswith(cls.MIX_ID_PREFIX):
                return item
        return supermix_candidates[0] if supermix_candidates else None

    @classmethod
    def _discover_mix_catalog(cls, shelves):
        """Собирает все персональные миксы YouTube Music с главной страницы аккаунта."""
        catalog = {}
        personal_pool = []
        seen_ids = set()
        for shelf in shelves or []:
            if not isinstance(shelf, dict):
                continue
            for item in shelf.get("contents") or []:
                if not isinstance(item, dict):
                    continue
                pid = str(item.get("playlistId") or "").strip()
                if not (pid.startswith(cls.MIX_ID_PREFIX) or pid.startswith(cls.ALT_MIX_PREFIX)):
                    continue
                if pid in seen_ids:
                    continue
                seen_ids.add(pid)
                title = str(item.get("title") or "").strip()
                title_cf = title.casefold()
                thumbnails = item.get("thumbnails") or []
                cover_url = normalize_artwork_url(thumbnails[-1].get("url", "")) if thumbnails and isinstance(thumbnails[-1], dict) else ""
                desc = str(item.get("description") or "").strip()
                entry = {"playlistId": pid, "title": title, "cover_url": cover_url, "description": desc, "raw": item}
                matched_key = None
                for key, aliases in cls.MIX_KEY_ALIASES.items():
                    if any(title_cf == alias or alias in title_cf for alias in aliases):
                        if key == "supermix" and not pid.startswith(cls.MIX_ID_PREFIX):
                            continue
                        matched_key = key
                        break
                if matched_key and matched_key not in catalog:
                    catalog[matched_key] = entry
                elif title_cf not in ("my supermix", "мой супермикс", "супермикс", "supermix"):
                    personal_pool.append(entry)

        fallback_keys = ("my_mix_1", "my_mix_2", "my_mix_3", "discover_mix", "new_release_mix", "replay_mix")
        pool_idx = 0
        for key in fallback_keys:
            if key not in catalog and pool_idx < len(personal_pool):
                catalog[key] = personal_pool[pool_idx]
                pool_idx += 1
        return catalog

    @classmethod
    def _find_mix_for_key(cls, shelves, mix_key):
        if not mix_key or mix_key == "supermix":
            return cls._find_supermix(shelves)
        catalog = cls._discover_mix_catalog(shelves)
        if mix_key in catalog:
            return catalog[mix_key]["raw"]
        return cls._find_supermix(shelves)

    @staticmethod
    def _normalize_track(entry):
        if (not isinstance(entry, dict) or entry.get("isAvailable") is False
                or entry.get("isPlayable") is False or entry.get("likeStatus") == "DISLIKE"):
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
            for part in str(entry.get("length") or "").split(":"):
                duration = duration * 60 + int(part)
        except (ValueError, TypeError):
            duration = 0
        track = {"source": "youtube", "video_id": video_id,
                 "url": f"https://music.youtube.com/watch?v={video_id}",
                 "title": title, "artist": ", ".join(filter(None, names)) or "Исполнитель неизвестен",
                 "artist_metadata": list(filter(None, names)),
                 "thumbnail": thumbnail, "duration": duration}
        if entry.get("likeStatus") == "LIKE":
            track["youtube_music_like"] = True
        return track

    def run(self):
        if self._cancelled.is_set():
            return
        try:
            import requests
            from ytmusicapi import YTMusic
            headers = self._auth_headers()
            if self._cancelled.is_set():
                return
            metadata = {"mix_id": self.mix_id}
            deadline = time.monotonic() + self.REQUEST_BUDGET_SECONDS
            with requests.Session() as session:
                original_request = session.request

                def bounded_request(method, url, *args, **kwargs):
                    remaining = deadline - time.monotonic()
                    if self._cancelled.is_set() or remaining <= 0:
                        raise TimeoutError("Супермикс: время ожидания истекло.")
                    kwargs["timeout"] = (min(3.5, remaining), min(6.0, remaining))
                    return original_request(method, url, *args, **kwargs)

                session.request = bounded_request
                client = YTMusic(headers, requests_session=session, language="en")
                playlist = None
                if not self.mix_id:
                    if self.known_mix_id:
                        try:
                            playlist = client.get_watch_playlist(playlistId=self.known_mix_id, limit=self.limit)
                            if playlist and playlist.get("tracks"):
                                metadata["mix_id"] = self.known_mix_id
                                metadata["mix_key"] = self.mix_key
                                if self.known_cover_url:
                                    metadata["cover_url"] = self.known_cover_url
                        except Exception:
                            playlist = None
                    if not playlist or not playlist.get("tracks"):
                        shelves = client.get_home(limit=8)
                        item = self._find_mix_for_key(shelves, self.mix_key)
                        if self._cancelled.is_set():
                            return
                        if item is None:
                            self.failed.emit(
                                "В аккаунте не найден My Supermix. Открой YouTube Music, проверь выбранный "
                                "аккаунт и наличие супермикса, затем обнови cookies при необходимости."
                            )
                            return
                        metadata["mix_id"] = item["playlistId"]
                        metadata["mix_key"] = self.mix_key
                        metadata["mix_title"] = str(item.get("title") or "")
                        thumbnails = item.get("thumbnails") or []
                        metadata["cover_url"] = normalize_artwork_url(thumbnails[-1].get("url", "")) if thumbnails else ""
                        catalog = self._discover_mix_catalog(shelves)
                        if catalog:
                            metadata["catalog"] = {
                                k: {"mix_id": v["playlistId"], "cover_url": v["cover_url"],
                                    "title": v["title"], "description": v["description"]}
                                for k, v in catalog.items()
                            }
                        playlist = client.get_watch_playlist(playlistId=metadata["mix_id"], limit=self.limit)
                else:
                    options = {"playlistId": self.mix_id, "radio": True, "limit": self.limit}
                    if self.anchor:
                        options["videoId"] = self.anchor
                    playlist = client.get_watch_playlist(**options)
            if self._cancelled.is_set():
                return
            result, seen = [], set(self.excluded_ids)
            for entry in (playlist or {}).get("tracks") or []:
                track = self._normalize_track(entry)
                if track and track["video_id"] not in seen:
                    result.append(track)
                    seen.add(track["video_id"])
                    if len(result) >= self.limit:
                        break
            # Пустое продолжение — повод повторить позднее, а не вернуть старые песни.
            if not result and not self.mix_id:
                self.failed.emit("My Supermix не вернул доступных треков. Попробуй открыть его позже.")
                return
            self.result_ready.emit(result, metadata)
        except ImportError:
            if not self._cancelled.is_set():
                self.failed.emit("Для My Supermix нужна ytmusicapi: python -m pip install -U ytmusicapi")
        except Exception as error:
            if self._cancelled.is_set():
                return
            # Не выводим ответ сервера/заголовки: в исключении могут оказаться cookies.
            detail = str(error).lower()
            if "403" in detail or "401" in detail:
                self.invalidate_browser_cookie_cache(self.browser_spec)
                message = "YouTube Music отклонил доступ к My Supermix (HTTP 401/403). Проверь аккаунт и обнови cookies."
            elif "cookie" in detail or "sapisid" in detail:
                message = "Не удалось прочитать авторизацию My Supermix. Проверь профиль браузера или обнови cookies.txt."
            elif "certificate" in detail or "ssl" in detail:
                message = "Не удалось проверить HTTPS-сертификат YouTube Music. Проверь настройки доверенных сертификатов."
            else:
                message = "My Supermix временно недоступен. Проверь сеть и попробуй ещё раз."
            self.failed.emit(message)


def _create_stream_ssl_context():
    """Создаёт проверенный SSLContext с учётом системных CA или certifi."""
    ctx = ssl.create_default_context()
    if not os.environ.get("SSL_CERT_FILE") and not os.environ.get("SSL_CERT_DIR"):
        try:
            import certifi
            cafile = certifi.where()
            if cafile and os.path.isfile(cafile):
                ctx.load_verify_locations(cafile=cafile)
        except Exception:
            pass
    return ctx


class _ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def _create_keepalive_stream_session(prefer_ipv4=False):
    """Создаёт постоянную HTTP Keep-Alive сессию с поддержкой системного прокси/VPN и zapret."""
    try:
        import requests
        import requests.adapters
    except Exception:
        return None

    class _IPv4HTTPAdapter(requests.adapters.HTTPAdapter):
        """Привязывает исходящие соединения к IPv4 (0.0.0.0) при резервном обходе зависших IPv6-маршрутов."""
        def __init__(self, source_address="0.0.0.0", *args, **kwargs):
            self._source_address = (source_address, 0) if source_address else None
            super().__init__(*args, **kwargs)

        def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
            if self._source_address:
                pool_kwargs["source_address"] = self._source_address
            return super().init_poolmanager(connections, maxsize, block=block, **pool_kwargs)

    session = requests.Session()
    ca_file = os.environ.get("SSL_CERT_FILE") or ""
    if ca_file and os.path.isfile(ca_file):
        session.verify = ca_file
    elif not os.environ.get("SSL_CERT_DIR"):
        try:
            import certifi
            cpath = certifi.where()
            if cpath and os.path.isfile(cpath):
                session.verify = cpath
        except Exception:
            pass
    adapter = (
        _IPv4HTTPAdapter("0.0.0.0", pool_connections=6, pool_maxsize=12, max_retries=0)
        if prefer_ipv4
        else requests.adapters.HTTPAdapter(pool_connections=6, pool_maxsize=12, max_retries=0)
    )
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


class BufferedStreamEntry:
    """Потоковый буфер аудио (64 КБ на блок) с непрерывной загрузкой в ОЗУ без параллельных Range-запросов, вызывающих 403."""
    BLOCK_SIZE = 64 * 1024
    STREAM_CHUNK_BYTES = 512 * 1024
    READAHEAD_BLOCKS = 64
    MAX_CACHED_BLOCKS = 1024
    MAX_HLS_BYTES = 50 * 1024 * 1024

    def __init__(self, remote_url, headers=None, content_type="audio/mp4", protocol="https",
                 backup_urls=None, fragments=None, fragment_base_url=None, total_size=None):
        self.remote_url = str(remote_url or "")
        self.backup_urls = [str(u) for u in (backup_urls or []) if u and str(u) != self.remote_url]
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
            "Connection": "keep-alive",
        }
        if isinstance(headers, dict):
            for k, v in headers.items():
                if k and v and str(k).lower() not in ("range", "host"):
                    self.headers[str(k)] = str(v)
        self.headers["Accept-Encoding"] = "identity"
        self.content_type = str(content_type or "audio/mp4")
        self.protocol = str(protocol or "https")
        self.fragments = list(fragments) if isinstance(fragments, (list, tuple)) else []
        self.fragment_base_url = str(fragment_base_url or "")
        self.blocks = OrderedDict()
        self._inflight = set()
        self._cursor_block = 0
        self._priority_block = None
        self.hls_buffer = bytearray()
        self.Sequential_mode = False
        self.total_size = int(total_size) if isinstance(total_size, (int, float)) and total_size > 0 else None
        self.eof = False
        self.fully_buffered = False
        self.failed = False
        self.last_error = ""
        self.closed = False
        self.active_readers = 0
        self.created_at = time.monotonic()
        self.last_access = self.created_at
        self._cond = threading.Condition()
        self._thread = None
        self._ssl_ctx = None
        self._session_lock = threading.Lock()
        self._session = None
        self._req_number = 0
        self._has_initial_data = False

    def _get_session(self, reset=False, prefer_ipv4=False):
        with self._session_lock:
            if reset and self._session is not None:
                try:
                    self._session.close()
                except Exception:
                    pass
                self._session = None
            if self._session is None:
                is_local = self.remote_url.startswith(("http://127.0.0.1", "https://127.0.0.1", "http://localhost", "https://localhost"))
                self._session = _create_keepalive_stream_session(prefer_ipv4=(prefer_ipv4 and not is_local))
            return self._session

    def _build_opener(self):
        if self._ssl_ctx is None:
            self._ssl_ctx = _create_stream_ssl_context()
        return build_opener(HTTPSHandler(context=self._ssl_ctx))

    def _is_hls(self):
        lower_url = self.remote_url.lower()
        proto = self.protocol.lower()
        return (
            "hls" in proto
            or "m3u8" in proto
            or "dash" in proto
            or "hls" in lower_url
            or ".m3u8" in lower_url
            or "hls_playlist" in lower_url
            or "hls_variant" in lower_url
            or bool(self.fragments)
        )

    def detect_container_ext(self, default_ext="m4a"):
        """Определяет точный контейнер по первым байтам потока, чтобы FFmpeg выбирал верный демуксер."""
        with self._cond:
            if self._is_hls() or self.Sequential_mode or len(self.hls_buffer) > 0:
                head = bytes(self.hls_buffer[:16])
            else:
                first_blk = self.blocks.get(0, b"")
                head = bytes(first_blk[:16])
        if len(head) >= 8 and head[4:8] in (b"ftyp", b"styp", b"moov", b"sidx"):
            self.content_type = "audio/mp4"
            return "m4a"
        if head.startswith(b"\x1a\x45\xdf\xa3"):
            self.content_type = "audio/webm"
            return "webm"
        if head.startswith(b"OggS"):
            self.content_type = "audio/ogg"
            return "ogg"
        if head.startswith(b"\x47"):
            self.content_type = "video/mp2t"
            return "ts"
        if head.startswith(b"ID3") or (len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0):
            if len(head) >= 2 and head[0] == 0xFF and (head[1] & 0x06) == 0:
                self.content_type = "audio/aac"
                return "aac"
            self.content_type = "audio/mpeg"
            return "mp3"
        return default_ext

    def canonical_url(self, proxy_url):
        base, dot, current_ext = str(proxy_url or "").rpartition(".")
        if not base or not dot:
            return proxy_url
        true_ext = self.detect_container_ext(default_ext=current_ext)
        return f"{base}.{true_ext}"

    def is_complete(self):
        with self._cond:
            if self._is_hls() or self.Sequential_mode:
                return bool(self.eof and len(self.hls_buffer) > 0 and not self.failed)
            if self.fully_buffered:
                return True
            if self.total_size is not None and self.total_size > 0:
                num_blocks = (self.total_size + self.BLOCK_SIZE - 1) // self.BLOCK_SIZE
                return num_blocks > 0 and all(idx in self.blocks for idx in range(num_blocks))
            return False

    def start(self):
        with self._cond:
            if self._thread is not None:
                return
            self._thread = threading.Thread(target=self._download_worker, daemon=True)
            self._thread.start()

    def close(self):
        with self._cond:
            self.closed = True
            self._cond.notify_all()
        with self._session_lock:
            if self._session is not None:
                try:
                    self._session.close()
                except Exception:
                    pass
                self._session = None

    def wait_for_initial_bytes(self, min_bytes=1024, timeout=1.8):
        self.start()
        deadline = time.monotonic() + max(0.2, float(timeout))
        with self._cond:
            while not self.closed and not self.failed:
                if self._is_hls() or self.Sequential_mode:
                    if len(self.hls_buffer) >= min_bytes or (self.eof and len(self.hls_buffer) > 0):
                        return True
                else:
                    first_block = self.blocks.get(0)
                    if (first_block and len(first_block) > 0) or getattr(self, "_has_initial_data", False):
                        return True
                if self.eof:
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._cond.wait(timeout=min(0.04, remaining))
            if self.closed or self.failed:
                return False
            if self._is_hls() or self.Sequential_mode:
                return len(self.hls_buffer) > 0
            return bool(self.blocks.get(0)) or getattr(self, "_has_initial_data", False)

    def _store_block(self, block_idx, data):
        with self._cond:
            expected = min(self.BLOCK_SIZE, self.total_size - block_idx * self.BLOCK_SIZE) if self.total_size is not None else self.BLOCK_SIZE
            if not data or len(data) != expected:
                raise ValueError("Неполный блок аудиопотока нельзя поместить в кэш.")
            self.blocks[block_idx] = bytes(data)
            self.blocks.move_to_end(block_idx)
            if block_idx == 0:
                self._has_initial_data = True
            if self._priority_block == block_idx:
                self._priority_block = None
            while len(self.blocks) > self.MAX_CACHED_BLOCKS:
                oldest_key = next(iter(self.blocks))
                if oldest_key in (0, self._cursor_block) and len(self.blocks) > 2:
                    self.blocks.move_to_end(oldest_key)
                    oldest_key = next(iter(self.blocks))
                self.blocks.pop(oldest_key, None)
            if self.total_size is not None and self.total_size > 0:
                num_blocks = (self.total_size + self.BLOCK_SIZE - 1) // self.BLOCK_SIZE
                if num_blocks > 0 and len(self.blocks) >= num_blocks and all(i in self.blocks for i in range(num_blocks)):
                    self.fully_buffered = True
                    self.eof = True
            self._cond.notify_all()

    @staticmethod
    def _with_googlevideo_params(url, start_byte, end_byte, req_num, use_query_range=False):
        if "googlevideo.com" not in url.lower():
            return url
        cleaned = re.sub(r"([?&])rn=\d+&?", r"\1", url).rstrip("?&")
        sep = "&" if "?" in cleaned else "?"
        out = f"{cleaned}{sep}rn={req_num}"
        if use_query_range:
            if re.search(r"[?&]range=", out):
                out = re.sub(r"([?&])range=[^&]*", lambda match: f"{match[1]}range={start_byte}-{end_byte}", out)
            else:
                out = f"{out}&range={start_byte}-{end_byte}"
        return out

    def _stream_span_into_blocks(self, start_block_idx, num_blocks_to_read=8, opener=None, dedicated_session=False):
        """Cache complete blocks from one representation; resume interrupted reads."""
        num_blocks_to_read = max(1, int(num_blocks_to_read))
        span_indices = range(start_block_idx, start_block_idx + num_blocks_to_read)
        with self._cond:
            if self.closed:
                return None
            if start_block_idx in self.blocks:
                self.blocks.move_to_end(start_block_idx)
                return self.blocks[start_block_idx]
            if self.failed:
                return None
            if self.total_size is not None and start_block_idx * self.BLOCK_SIZE >= self.total_size:
                return b""
            while start_block_idx in self._inflight and not self.closed and not self.failed:
                self._cond.wait(timeout=0.12)
                if start_block_idx in self.blocks:
                    return self.blocks[start_block_idx]
            if self.closed or self.failed:
                return None
            self._inflight.update(span_indices)

        start_byte = start_block_idx * self.BLOCK_SIZE
        end_byte = start_byte + num_blocks_to_read * self.BLOCK_SIZE - 1
        next_byte, next_block = start_byte, start_block_idx
        pending = bytearray()
        local_session = None

        def remember_size(size):
            with self._cond:
                if self.total_size is not None and self.total_size != size:
                    raise RuntimeError("Размер аудиопотока изменился; нужна новая ссылка.")
                self.total_size = size
                count = (size + self.BLOCK_SIZE - 1) // self.BLOCK_SIZE
                if count and all(index in self.blocks for index in range(count)):
                    self.fully_buffered = True
                    self.eof = True
                self._cond.notify_all()

        def finish_range(headers, request_start):
            match = re.fullmatch(r"bytes \*/(\d+)", headers.get("Content-Range", ""), re.I)
            if match:
                remember_size(int(match[1]))
            if self.total_size is not None and request_start >= self.total_size:
                return True
            raise RuntimeError("Сервер отклонил диапазон аудиопотока.")

        def receive(status, headers, chunks, request_start, request_end, target_url):
            nonlocal next_byte, next_block
            if status == 416:
                return finish_range(headers, request_start)
            if status not in (200, 206):
                raise RuntimeError(f"HTTP {status}")
            if str(headers.get("Content-Encoding", "identity")).lower() not in ("", "identity"):
                raise RuntimeError("Сервер изменил кодирование байтов аудиопотока.")
            content_range = headers.get("Content-Range", "")
            interval = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+|\*)", content_range, re.I)
            if status == 206 and interval is None:
                raise RuntimeError("В ответе сервера нет корректного диапазона байтов.")
            response_start, response_end = 0, None
            length = str(headers.get("Content-Length", ""))
            google_range = (urlsplit(target_url).hostname or "").lower().endswith(".googlevideo.com")
            query_range = re.search(r"[?&]range=(\d+)-(\d+)(?:&|$)", target_url) if google_range else None
            if interval is not None:
                response_start, response_end = int(interval[1]), int(interval[2])
                if response_start != request_start or response_end < response_start:
                    raise RuntimeError("Сервер вернул другой диапазон байтов аудиопотока.")
                if interval[3] != "*":
                    size = int(interval[3])
                    if response_end >= size:
                        raise RuntimeError("Некорректный размер диапазона аудиопотока.")
                    remember_size(size)
            elif query_range is not None:
                if int(query_range[1]) != request_start:
                    raise RuntimeError("Ссылка содержит другой диапазон байтов.")
                response_start, response_end = request_start, int(query_range[2])
                hint = re.search(r"[?&]clen=(\d+)(?:&|$)", target_url)
                if hint:
                    remember_size(int(hint[1]))
                # Some servers ignore even query ranges and return the full file.
                if length.isdigit() and (int(length) > response_end - response_start + 1
                                          or (self.total_size == int(length) and request_start > 0)):
                    response_start, response_end, query_range = 0, None, None
            elif length.isdigit():
                remember_size(int(length))
            if self.total_size is not None:
                request_end = min(request_end, self.total_size - 1)
                if request_start >= self.total_size:
                    return True
            content_type = headers.get("Content-Type")
            if content_type:
                self.content_type = content_type.split(";")[0].strip()
            skip = max(0, request_start - response_start)
            read_end = min(request_end, response_end) if response_end is not None else request_end
            stopped_at_range = False
            for chunk in chunks:
                if self.closed:
                    return False
                if not chunk:
                    continue
                if skip:
                    discard = min(skip, len(chunk))
                    skip -= discard
                    chunk = chunk[discard:]
                if not chunk:
                    continue
                chunk = chunk[:max(0, read_end - next_byte + 1)]
                pending.extend(chunk)
                next_byte += len(chunk)
                while len(pending) >= self.BLOCK_SIZE:
                    self._store_block(next_block, bytes(pending[:self.BLOCK_SIZE]))
                    del pending[:self.BLOCK_SIZE]
                    next_block += 1
                if next_byte > read_end:
                    stopped_at_range = True
                    break
            if (self.total_size is None and status == 200 and query_range is None
                    and not stopped_at_range and skip == 0):
                remember_size(next_byte)
            if self.total_size is not None and next_byte == self.total_size and pending:
                self._store_block(next_block, bytes(pending))
                pending.clear()
            if not stopped_at_range and response_end is not None and next_byte <= read_end:
                raise RuntimeError("Соединение оборвалось до конца диапазона аудио.")
            return self.total_size is not None and request_start >= self.total_size

        try:
            last_error = ""
            for attempt in range(4):
                if self.closed or self.failed:
                    return None
                if self.total_size is not None:
                    end_byte = min(end_byte, self.total_size - 1)
                request_start = next_byte
                self._req_number += 1
                active_url = (self.backup_urls[(attempt - 1) % len(self.backup_urls)]
                              if attempt and self.backup_urls else self.remote_url)
                target_url = active_url
                if attempt or re.search(r"[?&]range=", active_url):
                    target_url = self._with_googlevideo_params(active_url, request_start, end_byte,
                                                              self._req_number, use_query_range=True)
                headers = dict(self.headers)
                headers["Range"] = f"bytes={request_start}-{end_byte}"
                try:
                    if dedicated_session:
                        if local_session is not None:
                            local_session.close()
                        local_session = _create_keepalive_stream_session()
                        session = local_session
                    else:
                        # Keep the OS/VPN route used to obtain this signed URL.
                        session = self._get_session(reset=attempt > 0)
                    if session is not None:
                        with session.get(target_url, headers=headers, stream=True, timeout=(3.0, 5.0)) as response:
                            at_end = receive(response.status_code, response.headers,
                                             response.iter_content(chunk_size=32768), request_start, end_byte, target_url)
                    else:
                        if opener is None:
                            opener = self._build_opener()
                        with opener.open(Request(target_url, headers=headers), timeout=4.5) as response:
                            at_end = receive(response.getcode(), response.headers,
                                             iter(lambda: response.read(32768), b""), request_start, end_byte, target_url)
                    if at_end:
                        return b""
                except HTTPError as error:
                    if error.code == 416:
                        try:
                            if finish_range(error.headers, request_start):
                                return b""
                        except RuntimeError as invalid_range:
                            last_error = str(invalid_range)
                    else:
                        last_error = f"HTTP {error.code}"
                    error.close()
                except Exception as error:
                    last_error = str(error)
                with self._cond:
                    if start_block_idx in self.blocks:
                        return self.blocks[start_block_idx]
                if next_byte == request_start:
                    time.sleep(0.08)
            with self._cond:
                self.last_error = last_error or "Не удалось загрузить полный блок аудиопотока."
                self.failed = True
                self._cond.notify_all()
            return None
        finally:
            if local_session is not None:
                local_session.close()
            with self._cond:
                self._inflight.difference_update(span_indices)
                self._cond.notify_all()


    def _fetch_block(self, block_idx, opener=None):
        return self._stream_span_into_blocks(block_idx, num_blocks_to_read=1, opener=opener)

    def read_at(self, position, length):
        """Читает до length байт с позиции position, ожидая последовательную подгрузку без лишних параллельных сокетов."""
        self.start()
        with self._cond:
            self.last_access = time.monotonic()

        if self._is_hls() or self.Sequential_mode:
            deadline = time.monotonic() + 10.0
            with self._cond:
                while len(self.hls_buffer) <= position and not self.eof and not self.failed and not self.closed:
                    rem = deadline - time.monotonic()
                    if rem <= 0:
                        break
                    self._cond.wait(timeout=min(0.15, rem))
                if position >= len(self.hls_buffer):
                    return b""
                upper = min(len(self.hls_buffer), position + length)
                return bytes(self.hls_buffer[position:upper])

        if self.total_size is not None and position >= self.total_size > 0:
            return b""

        block_idx = position // self.BLOCK_SIZE
        offset_in_block = position % self.BLOCK_SIZE
        wait_deadline = time.monotonic() + 3.0
        with self._cond:
            is_tail_probe = (
                self.total_size is not None
                and self.total_size > self.BLOCK_SIZE * 4
                and position >= self.total_size - self.BLOCK_SIZE * 2
                and 1 not in self.blocks
            )
            if not is_tail_probe:
                self._cursor_block = block_idx
            if block_idx not in self.blocks and block_idx not in self._inflight:
                self._priority_block = block_idx
                self._cond.notify_all()
            while block_idx not in self.blocks and not self.eof and not self.failed and not self.closed:
                rem = wait_deadline - time.monotonic()
                if rem <= 0:
                    break
                self._cond.wait(timeout=min(0.08, rem))
            if block_idx in self.blocks:
                self.blocks.move_to_end(block_idx)
                block_data = self.blocks[block_idx]
                if offset_in_block >= len(block_data):
                    return b""
                return block_data[offset_in_block:min(len(block_data), offset_in_block + length)]
            self._priority_block = block_idx
            self._cond.notify_all()

        block_data = self._stream_span_into_blocks(block_idx, num_blocks_to_read=4, dedicated_session=True)
        if not block_data or offset_in_block >= len(block_data):
            return b""
        upper = min(len(block_data), offset_in_block + length)
        return block_data[offset_in_block:upper]

    def _download_worker(self):
        try:
            opener = self._build_opener()
            if self._is_hls():
                self._download_hls(opener)
                return

            # Сначала быстро скачиваем первые 4 блока (256 КБ) за ~100 мс, чтобы мгновенно отдать старт и обслужить probe конца файла от FFmpeg
            first = self._stream_span_into_blocks(0, num_blocks_to_read=4, opener=opener)
            if not first:
                with self._cond:
                    self.failed = True
                    self.eof = True
                    self._cond.notify_all()
                return

            while not self.closed:
                with self._cond:
                    if self.fully_buffered or self.eof or self.failed:
                        break
                    cursor = self._cursor_block
                    priority = self._priority_block
                    total = self.total_size

                next_to_fetch = None
                span_blocks = 8
                if priority is not None:
                    with self._cond:
                        if priority not in self.blocks and priority not in self._inflight:
                            if total is None or priority * self.BLOCK_SIZE < total:
                                next_to_fetch = priority
                                span_blocks = 4
                    with self._cond:
                        if priority not in self.blocks and priority not in self._inflight:
                            if total is None or priority * self.BLOCK_SIZE < total:
                                next_to_fetch = priority

                if next_to_fetch is None:
                    for candidate in range(cursor, cursor + self.READAHEAD_BLOCKS):
                        if total is not None and candidate * self.BLOCK_SIZE >= total > 0:
                            break
                        with self._cond:
                            already = candidate in self.blocks or candidate in self._inflight
                        if not already:
                            next_to_fetch = candidate
                            break

                if (next_to_fetch is None and total is not None
                        and 0 < total <= self.MAX_CACHED_BLOCKS * self.BLOCK_SIZE):
                    num_blocks = min(self.MAX_CACHED_BLOCKS, (total + self.BLOCK_SIZE - 1) // self.BLOCK_SIZE)
                    for candidate in range(num_blocks):
                        with self._cond:
                            already = candidate in self.blocks or candidate in self._inflight
                        if not already:
                            next_to_fetch = candidate
                            break

                if next_to_fetch is not None:
                    data = self._stream_span_into_blocks(next_to_fetch, num_blocks_to_read=span_blocks, opener=opener)
                    if data is None and self.closed:
                        break
                    if data is None and self.failed:
                        break
                else:
                    with self._cond:
                        if self.closed or self.fully_buffered:
                            break
                        self._cond.wait(timeout=0.25)
        except Exception as err:
            with self._cond:
                self.last_error = str(err)
                if 0 not in self.blocks and len(self.hls_buffer) == 0:
                    self.failed = True
                self.eof = True
                self._cond.notify_all()

    @staticmethod
    def _parse_m3u8_segments(manifest_text, base_url):
        segments = []
        seen_init = set()
        for raw_line in (manifest_text or "").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("#EXT-X-MAP:"):
                m = re.search(r'URI=["\']([^"\']+)["\']', line)
                if m:
                    init_url = urljoin(base_url, m.group(1).strip())
                    if init_url not in seen_init:
                        seen_init.add(init_url)
                        segments.append(init_url)
                continue
            if line.startswith("#"):
                continue
            segments.append(urljoin(base_url, line))
        return segments

    def _fetch_text(self, url, opener):
        session = self._get_session(prefer_ipv4=False)
        if session is not None:
            resp = session.get(url, headers=dict(self.headers), timeout=(3.0, 5.0))
            if resp.status_code < 400:
                return resp.text
            raise RuntimeError(f"HTTP {resp.status_code}")
        req = Request(url, headers=dict(self.headers))
        with opener.open(req, timeout=4.5) as uresp:
            return uresp.read(2 * 1024 * 1024).decode("utf-8", errors="replace")

    def _download_hls(self, opener):
        try:
            segments = []
            if self.fragments:
                base = self.fragment_base_url or self.remote_url
                for frag in self.fragments:
                    if isinstance(frag, dict):
                        u = frag.get("url") or (urljoin(base, str(frag.get("path") or "")) if frag.get("path") else "")
                        if u:
                            segments.append(str(u))
            else:
                manifest_url = self.remote_url
                manifest_text = self._fetch_text(manifest_url, opener)
                segments = self._parse_m3u8_segments(manifest_text, manifest_url)
                if segments and len(segments) <= 12 and (
                    segments[0].lower().split("?", 1)[0].endswith(".m3u8")
                    or "hls_playlist" in segments[0].lower()
                ):
                    sub_url = segments[-1]
                    sub_text = self._fetch_text(sub_url, opener)
                    sub_segments = self._parse_m3u8_segments(sub_text, sub_url)
                    if sub_segments:
                        segments = sub_segments

            if not segments:
                with self._cond:
                    self.failed = True
                    self.last_error = "Пустой HLS/DASH-манифест"
                    self.eof = True
                    self._cond.notify_all()
                return

            for seg_idx, seg_url in enumerate(segments):
                if self.closed:
                    return
                if len(self.hls_buffer) >= self.MAX_HLS_BYTES:
                    raise RuntimeError("Превышен предел буфера сегментированного аудио.")
                seg_bytes = None
                max_tries = 2 if seg_idx == 0 else 4
                for attempt in range(max_tries):
                    if self.closed:
                        break
                    try:
                        s = self._get_session(reset=(attempt >= 1), prefer_ipv4=(attempt == 1))
                        if s is not None:
                            seg_resp = s.get(seg_url, headers=dict(self.headers), timeout=(3.0, 5.0))
                            if seg_resp.status_code < 400 and seg_resp.content:
                                seg_bytes = seg_resp.content
                                break
                            if seg_resp.status_code in (401, 403) and seg_idx == 0:
                                break
                        else:
                            seg_req = Request(seg_url, headers=dict(self.headers))
                            with opener.open(seg_req, timeout=4.5) as seg_uresp:
                                seg_bytes = seg_uresp.read(4 * 1024 * 1024)
                            if seg_bytes:
                                break
                    except HTTPError as http_err:
                        self.last_error = f"HTTP {http_err.code}"
                        if http_err.code in (401, 403) and seg_idx == 0:
                            break
                        time.sleep(0.08)
                    except Exception as err:
                        self.last_error = str(err)
                        time.sleep(0.1 * (attempt + 1))
                if not seg_bytes:
                    with self._cond:
                        self.failed = True
                        self.eof = True
                        self._cond.notify_all()
                    return
                with self._cond:
                    self.hls_buffer.extend(seg_bytes)
                    if seg_idx == 0:
                        self.detect_container_ext()
                    self._cond.notify_all()
            with self._cond:
                self.total_size = len(self.hls_buffer)
                self.fully_buffered = True
                self.eof = True
                self._cond.notify_all()
        except Exception as err:
            with self._cond:
                self.last_error = str(err)
                self.failed = True
                self.eof = True
                self._cond.notify_all()


class LocalStreamProxy:
    """Локальный HTTP-прокси (127.0.0.1) для QMediaPlayer: защищает от обрывов связи и DPI-сбросов посередине трека."""
    _instance = None
    _instance_lock = threading.Lock()
    MAX_ACTIVE_STREAMS = 16

    def __init__(self):
        self._lock = threading.Lock()
        self._streams = OrderedDict()
        self._server = None
        self._port = 0

    @classmethod
    def instance(cls):
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def _ensure_server(self):
        with self._lock:
            if self._server is not None:
                return self._port
            proxy_ref = self

            class Handler(BaseHTTPRequestHandler):
                protocol_version = "HTTP/1.1"

                def log_message(self, format_str, *args):
                    return

                def do_HEAD(self):
                    self._handle_request(send_body=False)

                def do_GET(self):
                    self._handle_request(send_body=True)

                def _handle_request(self, send_body=True):
                    path = self.path.split("?", 1)[0].strip("/")
                    parts = path.split("/")
                    token = parts[1].split(".", 1)[0] if len(parts) >= 2 and parts[0] == "stream" else ""
                    entry = proxy_ref.get_entry(token)
                    if entry is None:
                        self.send_response(404)
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return

                    if not entry.wait_for_initial_bytes(min_bytes=1024, timeout=2.2):
                        self.send_response(502)
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return

                    entry.detect_container_ext()
                    range_header = self.headers.get("Range") or ""
                    start_byte = 0
                    end_byte = None
                    is_range = False
                    if range_header.startswith("bytes="):
                        is_range = True
                        spec = range_header[6:].split(",", 1)[0].strip()
                        if "-" in spec:
                            s_part, e_part = spec.split("-", 1)
                            if s_part.strip().isdigit():
                                start_byte = int(s_part.strip())
                            if e_part.strip().isdigit():
                                end_byte = int(e_part.strip())

                    total = entry.total_size
                    if total is not None and start_byte >= total > 0:
                        self.send_response(416)
                        self.send_header("Content-Range", f"bytes */{total}")
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return

                    if total is not None and total > 0:
                        actual_end = min(end_byte, total - 1) if end_byte is not None else (total - 1)
                        content_len = max(0, actual_end - start_byte + 1)
                        self.send_response(206 if is_range else 200)
                        self.send_header("Content-Type", entry.content_type)
                        self.send_header("Accept-Ranges", "bytes")
                        if is_range:
                            self.send_header("Content-Range", f"bytes {start_byte}-{actual_end}/{total}")
                        self.send_header("Content-Length", str(content_len))
                        self.send_header("Connection", "close")
                        self.end_headers()
                        cursor = start_byte
                    else:
                        self.send_response(200)
                        self.send_header("Content-Type", entry.content_type)
                        self.send_header("Connection", "close")
                        self.end_headers()
                        cursor = 0

                    if not send_body:
                        return

                    limit_byte = (min(end_byte, total - 1) if (end_byte is not None and total is not None)
                                  else (end_byte if (end_byte is not None and total is not None)
                                        else (total - 1 if total is not None else None)))
                    with entry._cond:
                        entry.active_readers += 1
                    try:
                        while not entry.closed:
                            if limit_byte is not None and cursor > limit_byte:
                                break
                            want = 65536
                            if limit_byte is not None:
                                want = min(want, limit_byte - cursor + 1)
                            data_slice = entry.read_at(cursor, want)
                            if not data_slice:
                                if entry.eof or (total is not None and cursor >= total):
                                    break
                                time.sleep(0.08)
                                data_slice = entry.read_at(cursor, want)
                                if not data_slice:
                                    break
                            self.wfile.write(data_slice)
                            cursor += len(data_slice)
                    except (BrokenPipeError, ConnectionResetError, OSError):
                        return
                    finally:
                        with entry._cond:
                            entry.active_readers = max(0, entry.active_readers - 1)
                            entry.last_access = time.monotonic()

            self._server = _ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            self._port = self._server.server_port
            server_thread = threading.Thread(target=self._server.serve_forever, daemon=True)
            server_thread.start()
            return self._port

    @staticmethod
    def _extract_token_from_url(url):
        text = str(url or "").split("?", 1)[0].strip("/")
        if "/stream/" not in text:
            return ""
        tail = text.rsplit("/stream/", 1)[-1]
        return tail.split(".", 1)[0].strip()

    def get_entry(self, token):
        with self._lock:
            entry = self._streams.get(token)
            if entry is not None:
                entry.last_access = time.monotonic()
            return entry

    def get_entry_by_url(self, url):
        token = self._extract_token_from_url(url)
        return self.get_entry(token) if token else None

    def is_stream_url_alive(self, url):
        entry = self.get_entry_by_url(url)
        return bool(entry is not None and not entry.closed and not entry.failed)

    def register_stream(self, remote_url, headers=None, ext="m4a", protocol="https",
                        backup_urls=None, fragments=None, fragment_base_url=None, total_size=None):
        port = self._ensure_server()
        ext_clean = re.sub(r"[^a-z0-9]", "", str(ext or "m4a").lower()) or "m4a"
        if "m3u8" in str(protocol or "").lower() and ext_clean == "mp4":
            ext_clean = "ts"
        mime_map = {
            "m4a": "audio/mp4",
            "mp4": "audio/mp4",
            "mp3": "audio/mpeg",
            "aac": "audio/aac",
            "ts": "video/mp2t",
            "webm": "audio/webm",
            "opus": "audio/ogg",
            "ogg": "audio/ogg",
        }
        content_type = mime_map.get(ext_clean, "audio/mp4")
        entry = BufferedStreamEntry(
            remote_url, headers=headers, content_type=content_type,
            protocol=protocol, backup_urls=backup_urls,
            fragments=fragments, fragment_base_url=fragment_base_url,
            total_size=total_size,
        )
        token = uuid4().hex
        now = time.monotonic()
        with self._lock:
            self._streams[token] = entry
            if len(self._streams) > self.MAX_ACTIVE_STREAMS:
                removable = [
                    k for k, v in self._streams.items()
                    if k != token and v.active_readers <= 0 and (now - v.last_access) > 45.0
                ]
                for k in removable:
                    if len(self._streams) <= self.MAX_ACTIVE_STREAMS:
                        break
                    old = self._streams.pop(k, None)
                    if old is not None:
                        old.close()
                while len(self._streams) > self.MAX_ACTIVE_STREAMS + 6:
                    oldest_key = next(
                        (k for k, v in self._streams.items() if k != token and v.active_readers <= 0),
                        None,
                    )
                    if oldest_key is None:
                        break
                    old = self._streams.pop(oldest_key, None)
                    if old is not None:
                        old.close()
        entry.start()
        return f"http://127.0.0.1:{port}/stream/{token}.{ext_clean}", entry


class StreamWorker(QThread):
    # Ссылка, название и время её получения (секунды).
    stream_ready = pyqtSignal(str, str, float)
    metadata_ready = pyqtSignal(dict)
    failed = pyqtSignal(str)

    _SHARED_YDL = None
    _SHARED_YDL_LOCK = threading.Lock()
    _SOUNDCLOUD_API_SESSION = None
    _SOUNDCLOUD_API_SESSION_LOCK = threading.Lock()
    _SOUNDCLOUD_RESOLVED_TRACKS = {}

    @classmethod
    def _get_soundcloud_session(cls):
        with cls._SOUNDCLOUD_API_SESSION_LOCK:
            if cls._SOUNDCLOUD_API_SESSION is None and requests is not None:
                cls._SOUNDCLOUD_API_SESSION = _create_keepalive_stream_session(prefer_ipv4=False)
            return cls._SOUNDCLOUD_API_SESSION

    @classmethod
    def get_soundcloud_client_id(cls):
        """Возвращает кэшированный client_id для SoundCloud или извлекает его один раз в фоне."""
        client_id = SearchWorker._SOUNDCLOUD_CACHED_CLIENT_ID
        if client_id:
            return client_id
        try:
            from yt_dlp.extractor import soundcloud as sc_mod
            sc_ie_cls = getattr(sc_mod, "SoundcloudIE", None)
            client_id = getattr(sc_ie_cls, "_CLIENT_ID", None) if sc_ie_cls else None
            if client_id:
                SearchWorker._SOUNDCLOUD_CACHED_CLIENT_ID = client_id
                return client_id
        except Exception:
            pass
        session = cls._get_soundcloud_session()
        if session is not None:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Referer": "https://soundcloud.com/",
            }
            try:
                home_resp = session.get("https://soundcloud.com/", headers=headers, timeout=(2.5, 3.5))
                if home_resp.status_code == 200:
                    scripts = re.findall(r'src="(https://a-v2\.sndcdn\.com/assets/[^"]+\.js)"', home_resp.text)
                    for script_url in reversed(scripts[-4:]):
                        js_resp = session.get(script_url, headers=headers, timeout=(2.0, 3.0))
                        if js_resp.status_code == 200:
                            m_id = re.search(r'client_id\s*:\s*"([0-9a-zA-Z]{32})"', js_resp.text)
                            if m_id:
                                client_id = m_id.group(1)
                                SearchWorker._SOUNDCLOUD_CACHED_CLIENT_ID = client_id
                                return client_id
            except Exception:
                pass
        return client_id

    @classmethod
    def _warmup_shared_ydl(cls):
        """Предварительно инициализирует YoutubeDL в пуле, чтобы первый клик по треку не тратил 200+ мс на импорты."""
        if cls._SHARED_YDL is not None:
            return
        opts = {
            **yt_dlp_tls_options(),
            "format": "bestaudio/best",
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
            "socket_timeout": 5,
            "cachedir": None,
            "ignoreconfig": True,
            "no_color": True,
            "check_formats": None,
        }
        with cls._SHARED_YDL_LOCK:
            if cls._SHARED_YDL is None:
                try:
                    cls._SHARED_YDL = YoutubeDL(opts)
                except Exception:
                    pass

    def __init__(self, track, parent=None, cookie_file=None, cookies_from_browser=None, audio_quality="auto", avoid_format_id="", resume_position_ms=0):
        super().__init__(parent)
        self.track = dict(track)
        self.cookie_file = str(cookie_file or "").strip()
        self.cookies_from_browser = str(cookies_from_browser or "").strip()
        self.audio_quality = str(audio_quality or "auto")
        self.avoid_format_id = str(avoid_format_id or "")
        self.resume_position_ms = max(0, int(resume_position_ms))
        self._cancel_requested = False

    def cancel(self):
        """Подавляет результат устаревшего запроса после завершения сетевого вызова."""
        self._cancel_requested = True

    @staticmethod
    def _auth_may_help(error):
        """True для ошибок, где авторизация или резервный клиент реально может помочь."""
        message = str(error or "").casefold()
        markers = (
            "sign in", "login required", "age-restricted", "age restricted",
            "members-only", "members only", "private video",
            "confirm you're not a bot", "confirm you’re not a bot",
            "cookies are required", "http error 403", "403 forbidden",
            "requested format is not available", "no video formats",
            "not available on this device", "this video is not available",
        )
        return any(marker in message for marker in markers)

    def _is_real_extract(self):
        return (
            "_extract" not in self.__dict__
            and getattr(self.__class__._extract, "__name__", "") == "_extract"
        )

    @staticmethod
    def _attach_ydl_cookies(ydl, info):
        """Переносит сессионные cookies (VISITOR_INFO1_LIVE, YSC и др.) из ydl.cookiejar в http_headers каждого формата."""
        if not isinstance(info, dict):
            return
        jar = getattr(ydl, "cookiejar", None)
        if jar is None:
            return

        def inject_into_dict(target_dict):
            if not isinstance(target_dict, dict):
                return
            u = str(target_dict.get("url") or "")
            if not u.startswith(("https://", "http://")):
                return
            try:
                dummy_req = Request(u)
                jar.add_cookie_header(dummy_req)
                cookie_val = (
                    dummy_req.get_header("Cookie")
                    or dummy_req.unredirected_hdrs.get("Cookie")
                    or ""
                )
                fmt_cookies = str(target_dict.get("cookies") or "").strip()
                if fmt_cookies and not cookie_val:
                    cookie_val = fmt_cookies
                if cookie_val:
                    hdrs = dict(target_dict.get("http_headers") or {})
                    hdrs.setdefault("Cookie", cookie_val)
                    target_dict["http_headers"] = hdrs
            except Exception:
                pass

        inject_into_dict(info)
        for key in ("formats", "requested_formats"):
            for fmt in (info.get(key) or []):
                inject_into_dict(fmt)

    def _extract(self, options):
        # YoutubeDL initializes required defaults and caches cookies/extractors.
        # Keep that state local to this request; clearing params breaks defaults
        # such as http_headers and reusing a client can retain another login.
        with YoutubeDL(dict(options)) as ydl:
            if type(ydl).__module__.startswith("yt_dlp"):
                try:
                    from yt_dlp.extractor import soundcloud as sc_mod
                    sc_ie_cls = getattr(sc_mod, "SoundcloudIE", None)
                    cached_cid = SearchWorker._SOUNDCLOUD_CACHED_CLIENT_ID or self.get_soundcloud_client_id()
                    if sc_ie_cls is not None and cached_cid and not getattr(sc_ie_cls, "_CLIENT_ID", None):
                        sc_ie_cls._CLIENT_ID = cached_cid
                except Exception:
                    pass
            info = ydl.extract_info(self.track["url"], download=False)
            if type(ydl).__module__.startswith("yt_dlp"):
                try:
                    self._attach_ydl_cookies(ydl, info)
                except Exception:
                    pass
                try:
                    from yt_dlp.extractor import soundcloud as sc_mod
                    sc_ie_cls = getattr(sc_mod, "SoundcloudIE", None)
                    if sc_ie_cls is not None and getattr(sc_ie_cls, "_CLIENT_ID", None):
                        SearchWorker._SOUNDCLOUD_CACHED_CLIENT_ID = sc_ie_cls._CLIENT_ID
                except Exception:
                    pass
            return info

    def _download_stream_via_ytdlp(self, base_options, auth_options=None):
        """Прямая загрузка аудио силами самого yt-dlp в локальный кэш (точно как в DownloadWorker)."""
        cache_dir = app_cache_directory() / "stream_temp"
        cache_dir.mkdir(parents=True, exist_ok=True)
        now = time.time()
        try:
            for old_file in cache_dir.iterdir():
                if old_file.is_file() and (now - old_file.stat().st_mtime) > 1800:
                    try:
                        old_file.unlink()
                    except OSError:
                        pass
        except OSError:
            pass
        url = str(self.track.get("url") or "")
        stem = "stream_" + hashlib.sha256(f"{url}_{time.monotonic()}".encode()).hexdigest()[:16]
        dl_opts = {
            **yt_dlp_tls_options(),
            "format": "bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best",
            "outtmpl": str(cache_dir / (stem + ".%(ext)s")),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "retries": 2,
            "fragment_retries": 2,
            "cachedir": None,
            "ignoreconfig": True,
        }
        if auth_options:
            dl_opts.update(auth_options)
        for client_override in (None, {"youtube": {"player_client": ["android_vr", "tv_embedded", "mweb"]}}):
            if self._cancel_requested:
                return None, None
            run_opts = dict(dl_opts)
            if client_override is not None:
                run_opts["extractor_args"] = client_override
            try:
                with YoutubeDL(run_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    if not info:
                        continue
                    if info.get("_type") in ("playlist", "multi_video"):
                        info = next((e for e in info.get("entries", []) if e), None)
                    if not info:
                        continue
                    prepared = Path(ydl.prepare_filename(info))
                    if not prepared.is_file():
                        matches = [
                            p for p in cache_dir.iterdir()
                            if p.is_file() and p.name.startswith(stem) and p.suffix not in (".part", ".ytdl", ".temp")
                        ]
                        if matches:
                            prepared = max(matches, key=lambda p: p.stat().st_mtime)
                    if prepared.is_file() and prepared.stat().st_size > 0:
                        return QUrl.fromLocalFile(str(prepared.resolve())).toString(), info
            except Exception:
                continue
        return None, None

    @staticmethod
    def _select_audio_candidate(info):
        stream_url = info.get("url")
        selected_info = info
        formats = [
            f for f in (info.get("requested_formats") or info.get("formats") or [])
            if isinstance(f, dict) and f.get("url") and f.get("acodec") not in (None, "none")
        ]
        pure_audio = [
            f for f in formats
            if f.get("vcodec") in (None, "none")
        ]
        if not stream_url:
            selected = (pure_audio[-1] if pure_audio else (formats[-1] if formats else None))
            stream_url = selected.get("url") if selected else None
            selected_info = selected or info
        return stream_url, selected_info

    def _auth_options(self):
        auth_options = {}
        if self.cookie_file and Path(self.cookie_file).is_file():
            auth_options["cookiefile"] = self.cookie_file
        elif self.cookies_from_browser:
            auth_options["cookiesfrombrowser"] = parse_cookies_from_browser(self.cookies_from_browser)
        return auth_options

    def _wait_for_proxy(self, entry, timeout):
        if not entry.wait_for_initial_bytes(min_bytes=4096, timeout=timeout):
            return False
        if self.resume_position_ms > 0 and entry._is_hls():
            # Joined HLS fragments need a final byte length before FFmpeg can
            # seek reliably. Only recovery/resume waits for the complete buffer.
            deadline = time.monotonic() + 15.0
            with entry._cond:
                while not entry.is_complete():
                    if self._cancel_requested or entry.closed or entry.failed:
                        return False
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        return False
                    entry._cond.wait(timeout=min(0.1, remaining))
        return not self._cancel_requested

    def _try_open_proxy_stream(self, info):
        """Пробует открыть основной и альтернативные форматы из info через LocalStreamProxy. Возвращает (playback_url, selected_info, remote_host) или None."""
        stream_url, selected_info = self._select_audio_candidate(info)
        if not stream_url:
            return None
        headers = selected_info.get("http_headers") or info.get("http_headers") or {}
        ext = selected_info.get("ext") or info.get("ext") or "m4a"
        protocol = selected_info.get("protocol") or info.get("protocol") or "https"
        remote_host = QUrl(str(stream_url)).host()
        raw_formats = [
            f for f in (info.get("formats") or [])
            if isinstance(f, dict) and f.get("url") and f.get("url") != stream_url
            and f.get("acodec") not in (None, "none")
        ]
        pure_audio = [
            f for f in raw_formats
            if f.get("vcodec") in (None, "none")
        ]
        candidates = pure_audio or raw_formats
        # Different bitrates/codecs are different byte streams even if the
        # extension matches. Try them only with a new buffer and decoder.
        proxy_url, proxy_entry = LocalStreamProxy.instance().register_stream(
            stream_url, headers=headers, ext=ext, protocol=protocol,
            fragments=selected_info.get("fragments"),
            fragment_base_url=selected_info.get("fragment_base_url"),
            total_size=selected_info.get("filesize") if protocol in ("https", "http") and not selected_info.get("fragments") else None,
        )
        if self._wait_for_proxy(proxy_entry, timeout=1.8):
            return proxy_entry.canonical_url(proxy_url), selected_info, remote_host
        proxy_entry.close()

        candidates = (pure_audio or raw_formats)[-2:]
        for alt in reversed(candidates):
            if self._cancel_requested:
                return None
            alt_headers = alt.get("http_headers") or headers
            alt_ext = alt.get("ext") or ext
            alt_proto = alt.get("protocol") or protocol
            alt_proxy_url, alt_entry = LocalStreamProxy.instance().register_stream(
                alt["url"], headers=alt_headers, ext=alt_ext, protocol=alt_proto,
                fragments=alt.get("fragments"),
                fragment_base_url=alt.get("fragment_base_url"),
                total_size=alt.get("filesize") if alt_proto in ("https", "http") and not alt.get("fragments") else None,
            )
            if self._wait_for_proxy(alt_entry, timeout=1.8):
                alt_host = QUrl(str(alt["url"])).host() or remote_host
                return alt_entry.canonical_url(alt_proxy_url), alt, alt_host
            alt_entry.close()
        return None

    def _resolve_fast_soundcloud_stream(self):
        """Прямой запрос к SoundCloud API v2 медиа-потоку (разрешение за ~40–90 мс через keep-alive сессию)."""
        if requests is None or not self._is_real_extract():
            return None
        url = str(self.track.get("url") or "")
        is_sc = (
            self.track.get("source") == "soundcloud"
            or "soundcloud.com" in url.lower()
        )
        if not is_sc:
            return None

        client_id = self.get_soundcloud_client_id()
        session = self._get_soundcloud_session()
        if session is None:
            session = _create_keepalive_stream_session(prefer_ipv4=False)
        if session is None:
            return None
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Referer": "https://soundcloud.com/",
            "Origin": "https://soundcloud.com",
        }
        try:
            if not client_id:
                client_id = self.get_soundcloud_client_id()
            if not client_id:
                return None

            transcodings = self.track.get("transcodings")
            track_title = self.track.get("title") or "Трек"
            track_duration = float(self.track.get("duration") or 0.0)

            if not transcodings and url.startswith(("https://", "http://")):
                cached_res = self._SOUNDCLOUD_RESOLVED_TRACKS.get(url)
                if cached_res and (time.monotonic() - cached_res[0]) < 1200:
                    payload = cached_res[1]
                    if isinstance(payload, dict):
                        if payload.get("title"):
                            track_title = payload.get("title")
                        raw_dur = payload.get("duration") or payload.get("full_duration")
                        if raw_dur:
                            track_duration = float(raw_dur) / 1000.0 if float(raw_dur) > 1000 else float(raw_dur)
                        med = payload.get("media") if isinstance(payload.get("media"), dict) else {}
                        transcodings = med.get("transcodings") if isinstance(med.get("transcodings"), list) else None

            if not transcodings and url.startswith(("https://", "http://")):
                resolve_url = f"https://api-v2.soundcloud.com/resolve?url={quote(url)}&client_id={client_id}"
                resp = session.get(resolve_url, headers=headers, timeout=(2.5, 3.5))
                if resp.status_code == 200:
                    payload = resp.json()
                    if isinstance(payload, dict):
                        self._SOUNDCLOUD_RESOLVED_TRACKS[url] = (time.monotonic(), payload)
                        if len(self._SOUNDCLOUD_RESOLVED_TRACKS) > 300:
                            oldest_k = next(iter(self._SOUNDCLOUD_RESOLVED_TRACKS))
                            self._SOUNDCLOUD_RESOLVED_TRACKS.pop(oldest_k, None)
                        if payload.get("title"):
                            track_title = payload.get("title")
                        raw_dur = payload.get("duration") or payload.get("full_duration")
                        if raw_dur:
                            track_duration = float(raw_dur) / 1000.0 if float(raw_dur) > 1000 else float(raw_dur)
                        med = payload.get("media") if isinstance(payload.get("media"), dict) else {}
                        transcodings = med.get("transcodings") if isinstance(med.get("transcodings"), list) else None

            if not transcodings or not isinstance(transcodings, list):
                return None

            chosen_tc = None
            for tc in transcodings:
                if not isinstance(tc, dict):
                    continue
                fmt = tc.get("format") or {}
                proto = str(fmt.get("protocol") or "").lower()
                if "progressive" in proto or "http" in proto:
                    chosen_tc = tc
                    break
            if not chosen_tc:
                for tc in transcodings:
                    if isinstance(tc, dict) and tc.get("url"):
                        fmt = tc.get("format") or {}
                        proto = str(fmt.get("protocol") or "").lower()
                        if "encrypted" not in proto and "drm" not in proto:
                            chosen_tc = tc
                            break
            if not chosen_tc or not chosen_tc.get("url"):
                return None

            media_auth_url = chosen_tc["url"]
            delim = "&" if "?" in media_auth_url else "?"
            media_auth_url = f"{media_auth_url}{delim}client_id={client_id}"

            m_resp = session.get(media_auth_url, headers=headers, timeout=(2.5, 3.5))
            if m_resp.status_code != 200:
                return None
            m_data = m_resp.json()
            stream_url = m_data.get("url") if isinstance(m_data, dict) else None
            if not stream_url or not str(stream_url).startswith(("https://", "http://")):
                return None

            ext = "mp3" if "mp3" in str(chosen_tc.get("preset") or "").lower() else "m4a"
            proto = (chosen_tc.get("format") or {}).get("protocol") or "https"
            stream_headers = {
                "User-Agent": headers["User-Agent"],
                "Accept": "*/*",
                "Referer": "https://soundcloud.com/",
            }

            proxy_url, proxy_entry = LocalStreamProxy.instance().register_stream(
                stream_url,
                headers=stream_headers,
                ext=ext,
                protocol=proto,
            )
            if self._wait_for_proxy(proxy_entry, timeout=1.8):
                canonical_url = proxy_entry.canonical_url(proxy_url)
                remote_host = QUrl(str(stream_url)).host() or "sndcdn.com"
                return {
                    "playback_url": canonical_url,
                    "title": track_title,
                    "duration": track_duration,
                    "format_id": str(chosen_tc.get("preset") or "sc_api"),
                    "protocol": proto,
                    "remote_host": remote_host,
                }
            proxy_entry.close()
        except Exception:
            pass
        return None

    def run(self):
        started = time.perf_counter()
        if self._is_real_extract():
            fast_sc = self._resolve_fast_soundcloud_stream()
            if fast_sc and not self._cancel_requested:
                self.metadata_ready.emit({
                    "duration": fast_sc["duration"],
                    "is_live": False,
                    "format_id": fast_sc["format_id"],
                    "protocol": fast_sc["protocol"],
                    "hostname": fast_sc["remote_host"],
                })
                self.stream_ready.emit(fast_sc["playback_url"], fast_sc["title"], time.perf_counter() - started)
                return

        format_options = {
            "auto": (
                "bestaudio[protocol=https][format_id=251]/bestaudio[protocol=https][format_id=140]/"
                "18/bestaudio[protocol=https][ext=m4a]/bestaudio[protocol=https][ext=webm]/"
                "bestaudio[protocol=https][ext=mp3]/bestaudio[protocol=https]/bestaudio[protocol=http]/"
                "bestaudio[ext=m4a]/bestaudio[ext=mp3]/bestaudio/best"
            ),
            "high": (
                "bestaudio[protocol=https][format_id=251]/bestaudio[protocol=https][abr>=192]/"
                "bestaudio[protocol=https][format_id=140]/18/bestaudio[protocol=https]/"
                "bestaudio[abr>=192]/bestaudio[ext=m4a]/bestaudio[ext=mp3]/bestaudio/best"
            ),
            "economy": (
                "bestaudio[protocol=https][format_id=250]/bestaudio[protocol=https][format_id=249]/"
                "18/bestaudio[protocol=https][abr<=128]/bestaudio[protocol=https]/"
                "bestaudio[abr<=128]/bestaudio[ext=m4a]/bestaudio[ext=mp3]/bestaudio/best"
            ),
            "compatibility": (
                "18/bestaudio[protocol=https][format_id=140]/bestaudio[protocol=https][ext=m4a]/"
                "bestaudio[protocol=https][ext=mp3]/bestaudio[protocol=https]/bestaudio[protocol=http]/"
                "bestaudio[ext=m4a]/bestaudio[ext=mp3]/bestaudio/best"
            ),
        }
        is_yt = (
            self.track.get("source") == "youtube"
            or (
                not self.track.get("source")
                and (
                    "youtube.com" in str(self.track.get("url") or "").lower()
                    or "youtu.be" in str(self.track.get("url") or "").lower()
                )
            )
        )
        selector = format_options.get(self.audio_quality, format_options["auto"])
        if re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", self.avoid_format_id):
            alternate = "/".join(part + f'[format_id!="{self.avoid_format_id}"]' for part in selector.split("/"))
            selector = alternate + "/" + selector

        options = {
            **yt_dlp_tls_options(),
            "format": selector,
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
            "socket_timeout": 5,
            "retries": 1,
            "extractor_retries": 1,
            "cachedir": None,
            "ignoreconfig": True,
            "no_color": True,
            "check_formats": None,
        }
        used_auth = False
        try:
            try:
                info = self._extract(options)
                if self._cancel_requested:
                    return
            except Exception as public_error:
                if self._cancel_requested:
                    return
                auth_options = self._auth_options()
                can_retry_default = self._is_real_extract() and is_yt and self._auth_may_help(public_error)
                if not can_retry_default and (not auth_options or not self._auth_may_help(public_error)):
                    raise
                retry_options = dict(options)
                if can_retry_default and not auth_options:
                    retry_options["extractor_args"] = {
                        "youtube": {
                            "player_client": ["android_vr", "web_safari"],
                        }
                    }
                else:
                    retry_options.pop("extractor_args", None)
                if auth_options and (self._auth_may_help(public_error) or not can_retry_default):
                    retry_options.update(auth_options)
                    used_auth = True
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

            stream_url, selected_info = self._select_audio_candidate(info)
            if not stream_url:
                raise RuntimeError("Не удалось получить аудиопоток: YouTube не вернул прямую ссылку.")
            title = info.get("title") or self.track.get("title") or "Трек"
            if self._cancel_requested:
                return
            try:
                duration = float(info.get("duration") or 0)
                if not math.isfinite(duration) or not 0 < duration <= 604800:
                    duration = 0
            except (TypeError, ValueError, OverflowError):
                duration = 0

            remote_host = QUrl(stream_url).host()
            playback_url = stream_url
            if (self._is_real_extract()
                    and str(stream_url).startswith(("https://", "http://"))
                    and not str(stream_url).startswith(("https://example.invalid", "http://example.invalid", "http://127.0.0.1"))
                    and "sig=PRIVATE" not in str(stream_url)):
                opened = self._try_open_proxy_stream(info)
                if opened is None and is_yt and not self._cancel_requested:
                    fallback_profiles = [
                        {},
                        {"extractor_args": {"youtube": {"player_client": ["mweb", "web_safari"]}}},
                    ]
                    if not used_auth:
                        auth_opts = self._auth_options()
                        if auth_opts:
                            fallback_profiles.append(auth_opts)
                    for prof in fallback_profiles:
                        if self._cancel_requested or opened is not None:
                            break
                        prof_opts = dict(options)
                        prof_opts.pop("extractor_args", None)
                        prof_opts.update(prof)
                        try:
                            alt_info = self._extract(prof_opts)
                            if alt_info and not self._cancel_requested:
                                if alt_info.get("_type") in ("playlist", "multi_video"):
                                    alt_info = next((e for e in alt_info.get("entries", []) if e), None)
                                if isinstance(alt_info, dict):
                                    opened = self._try_open_proxy_stream(alt_info)
                        except Exception:
                            continue

                if opened is not None:
                    playback_url, selected_info, remote_host = opened
                elif not self._cancel_requested:
                    local_file_url, dl_info = self._download_stream_via_ytdlp(options, self._auth_options())
                    if local_file_url:
                        playback_url = local_file_url
                        if isinstance(dl_info, dict):
                            selected_info = dl_info
                    else:
                        service = "YouTube" if is_yt else "SoundCloud"
                        raise RuntimeError(f"Не удалось открыть аудиопоток {service}. Проверь соединение и доступ к сервису.")

            self.metadata_ready.emit({"duration": duration, "is_live": bool(info.get("is_live")),
                                      "format_id": str(selected_info.get("format_id") or ""),
                                      "protocol": str(selected_info.get("protocol") or ""),
                                      "hostname": remote_host})
            self.stream_ready.emit(playback_url, title, time.perf_counter() - started)
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
                "cachedir": None,
                "ignoreconfig": True,
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
            stream_url = ""
            formats = [
                f for f in (info.get("formats") or [])
                if isinstance(f, dict) and f.get("url") and f.get("acodec") not in (None, "none")
            ]
            if formats:
                preferred = (
                    [f for f in formats if f.get("protocol") in ("https", "http") and f.get("ext") in ("m4a", "mp3")]
                    or [f for f in formats if f.get("protocol") in ("https", "http")]
                    or [f for f in formats if f.get("ext") in ("m4a", "mp3")]
                    or formats
                )
                stream_url = str(preferred[-1].get("url") or "")
            if not stream_url and isinstance(info.get("url"), str):
                stream_url = info["url"]
            data = {
                "thumbnail": normalize_artwork_url(thumbnail),
                "artist": str(artist or ""),
                "duration": info.get("duration") or 0,
                "title": info.get("title") or self.track.get("title") or "",
            }
            if stream_url:
                data["stream_url"] = stream_url
            if not data["thumbnail"] and not stream_url:
                raise RuntimeError("В метаданных SoundCloud нет обложки")
            self.metadata_ready.emit(url, data)
        except Exception as error:
            self.failed.emit(url, str(error))


def _parse_version_tuple(version_str):
    """Преобразует строку версии ('v0.2.1', '0.2.1-beta') в кортеж чисел (0, 2, 1) для точного сравнения."""
    cleaned = str(version_str or "").strip().lstrip("vV")
    parts = re.findall(r"\d+", cleaned)
    if not parts:
        return (0, 0, 0)
    return tuple(int(p) for p in parts[:4])


def _detect_github_repo(default_repo=GITHUB_REPO):
    """Определяет owner/repo из локального .git/config, если приложение запущено из клона репозитория."""
    try:
        git_cfg = Path(__file__).resolve().parent / ".git" / "config"
        if git_cfg.is_file():
            text = git_cfg.read_text(encoding="utf-8", errors="ignore")
            m = re.search(r"github\.com[:/]([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?\s*$", text, re.M)
            if m:
                return m.group(1).strip()
    except Exception:
        pass
    return str(default_repo or GITHUB_REPO).strip()


class AppUpdateCheckerWorker(QThread):
    """Проверяет наличие новой версии и готового .exe в GitHub Releases, ветке main и локальном git."""
    update_checked = pyqtSignal(dict)

    def __init__(self, repo=GITHUB_REPO, current_version=APP_VERSION, parent=None):
        super().__init__(parent)
        self.repo = _detect_github_repo(repo)
        self.current_version = str(current_version or APP_VERSION).strip()
        self._cancel_requested = False

    def cancel(self):
        self._cancel_requested = True

    def _http_get_json(self, url, timeout=5.0):
        headers = {
            "User-Agent": f"AuroraMusicPlayer/{self.current_version}",
            "Accept": "application/vnd.github+json, application/json;q=0.9, */*;q=0.8",
        }
        req = Request(url, headers=headers)
        ctx = _create_stream_ssl_context()
        opener = build_opener(HTTPSHandler(context=ctx))
        with opener.open(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw)

    def _http_get_text(self, url, max_bytes=8192, timeout=4.5):
        headers = {
            "User-Agent": f"AuroraMusicPlayer/{self.current_version}",
            "Range": f"bytes=0-{max_bytes}",
        }
        req = Request(url, headers=headers)
        ctx = _create_stream_ssl_context()
        opener = build_opener(HTTPSHandler(context=ctx))
        with opener.open(req, timeout=timeout) as resp:
            return resp.read(max_bytes).decode("utf-8", errors="replace")

    def run(self):
        result = {
            "ok": False,
            "repo": self.repo,
            "current_version": self.current_version,
            "latest_version": self.current_version,
            "tag_name": f"v{self.current_version}",
            "is_newer": False,
            "no_releases_yet": False,
            "can_git_pull": False,
            "has_git_commits": False,
            "exe_url": "",
            "exe_sha256_url": "",
            "zip_url": "",
            "zip_sha256_url": "",
            "source_url": f"https://raw.githubusercontent.com/{self.repo}/main/player_aurora_smart_beautiful_fixed_ui_repaint.py",
            "release_url": f"https://github.com/{self.repo}/releases",
            "actions_url": f"https://github.com/{self.repo}/actions/workflows/windows-build.yml",
            "published_at": "",
            "notes": "",
            "error": "",
        }
        last_err = ""
        try:
            release_data = None
            try:
                release_data = self._http_get_json(f"https://api.github.com/repos/{self.repo}/releases/latest")
            except Exception as e1:
                last_err = str(e1)
                try:
                    all_releases = self._http_get_json(f"https://api.github.com/repos/{self.repo}/releases")
                    if isinstance(all_releases, list):
                        result["ok"] = True
                        if all_releases:
                            release_data = all_releases[0]
                        else:
                            result["no_releases_yet"] = True
                except Exception as e2:
                    last_err = str(e2)
                    release_data = None

            if self._cancel_requested:
                return

            best_version = self.current_version
            if isinstance(release_data, dict):
                tag_name = str(release_data.get("tag_name") or release_data.get("name") or "").strip()
                if tag_name:
                    result["tag_name"] = tag_name
                    best_version = tag_name.lstrip("vV").strip() or best_version
                if release_data.get("html_url"):
                    result["release_url"] = str(release_data["html_url"])
                if release_data.get("published_at"):
                    result["published_at"] = str(release_data["published_at"])[:10]
                if release_data.get("body"):
                    result["notes"] = str(release_data["body"]).strip()
                assets = release_data.get("assets") if isinstance(release_data.get("assets"), list) else []
                for asset in assets:
                    if not isinstance(asset, dict):
                        continue
                    name = str(asset.get("name") or "").lower()
                    dl_url = str(asset.get("browser_download_url") or "")
                    if not dl_url:
                        continue
                    if name == "auroramusicplayer.exe":
                        result["exe_url"] = dl_url
                    elif name == "auroramusicplayer.exe.sha256.txt":
                        result["exe_sha256_url"] = dl_url
                    elif name.endswith(".exe") and not result["exe_url"]:
                        result["exe_url"] = dl_url
                    elif name == "auroramusicplayer-windows-x64.zip":
                        result["zip_url"] = dl_url
                    elif name == "auroramusicplayer-windows-x64.zip.sha256.txt":
                        result["zip_sha256_url"] = dl_url
                    elif name.endswith(".zip") and not result["zip_url"]:
                        result["zip_url"] = dl_url
                result["ok"] = True

            # Дополнительно проверяем APP_VERSION в ветке main
            try:
                head_src = self._http_get_text(result["source_url"], max_bytes=4096, timeout=4.0)
                m_ver = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']', head_src)
                if m_ver:
                    src_ver = m_ver.group(1).strip()
                    if _parse_version_tuple(src_ver) > _parse_version_tuple(best_version):
                        best_version = src_ver
                        result["tag_name"] = f"v{src_ver.lstrip('vV')}"
                    result["ok"] = True
            except Exception as e3:
                if not last_err:
                    last_err = str(e3)

            # Если приложение запущено из git-репозитория (включая приватный репозиторий)
            app_root = Path(__file__).resolve().parent
            if not getattr(sys, "frozen", False) and (app_root / ".git").exists():
                try:
                    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if sys.platform == "win32" else 0
                    local_proc = subprocess.run(
                        ["git", "rev-parse", "HEAD"],
                        cwd=str(app_root), capture_output=True, text=True, timeout=3, creationflags=flags
                    )
                    remote_proc = subprocess.run(
                        ["git", "ls-remote", "origin", "HEAD"],
                        cwd=str(app_root), capture_output=True, text=True, timeout=4, creationflags=flags
                    )
                    if local_proc.returncode == 0 and remote_proc.returncode == 0:
                        local_sha = local_proc.stdout.strip()
                        remote_sha = (remote_proc.stdout.strip().split() or [""])[0]
                        result["can_git_pull"] = True
                        result["ok"] = True
                        if local_sha and remote_sha and local_sha != remote_sha:
                            result["has_git_commits"] = True
                except Exception:
                    pass

            result["latest_version"] = best_version
            result["is_newer"] = (
                _parse_version_tuple(best_version) > _parse_version_tuple(self.current_version)
                or bool(result.get("has_git_commits"))
            )
            if not result["ok"] and last_err:
                result["error"] = last_err
        except Exception as exc:
            result["error"] = str(exc)

        if not self._cancel_requested:
            self.update_checked.emit(result)


class AppUpdateInstallerWorker(QThread):
    """Скачивает обновление (готовый .exe, портативный .zip, git pull или исходник .py) и подготавливает автоперезапуск."""
    progress_changed = pyqtSignal(int, str)
    update_ready_to_restart = pyqtSignal(str, str)
    update_failed = pyqtSignal(str)

    def __init__(self, update_info, parent=None):
        super().__init__(parent)
        self.update_info = dict(update_info or {})
        self._cancel_requested = False

    def cancel(self):
        self._cancel_requested = True

    def _download_file(self, url, dest_path, label="Скачивание обновления"):
        headers = {
            "User-Agent": f"AuroraMusicPlayer/{APP_VERSION}",
            "Accept": "*/*",
        }
        req = Request(url, headers=headers)
        ctx = _create_stream_ssl_context()
        opener = build_opener(HTTPSHandler(context=ctx))
        with opener.open(req, timeout=20) as resp:
            total = int(resp.headers.get("Content-Length") or 0)
            downloaded = 0
            with open(dest_path, "wb") as out:
                while True:
                    if self._cancel_requested:
                        raise RuntimeError("Обновление отменено пользователем.")
                    chunk = resp.read(64 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        pct = min(98, int(downloaded * 100 / total))
                        mb_done = downloaded / (1024 * 1024)
                        mb_total = total / (1024 * 1024)
                        self.progress_changed.emit(pct, f"{label}: {mb_done:.1f} / {mb_total:.1f} МБ ({pct}%)")
                    else:
                        mb_done = downloaded / (1024 * 1024)
                        self.progress_changed.emit(50, f"{label}: {mb_done:.1f} МБ…")

    def _verify_optional_sha256(self, file_path, sha_url):
        if not sha_url:
            return
        try:
            headers = {"User-Agent": f"AuroraMusicPlayer/{APP_VERSION}"}
            req = Request(sha_url, headers=headers)
            ctx = _create_stream_ssl_context()
            opener = build_opener(HTTPSHandler(context=ctx))
            with opener.open(req, timeout=6) as resp:
                text = resp.read(512).decode("utf-8", errors="replace").strip()
            expected = text.split()[0].lower() if text else ""
            if len(expected) == 64 and all(c in "0123456789abcdef" for c in expected):
                actual = hashlib.sha256(Path(file_path).read_bytes()).hexdigest().lower()
                if actual != expected:
                    raise RuntimeError("Контрольная сумма SHA256 скачанного файла не совпала.")
        except RuntimeError:
            raise
        except Exception:
            pass

    def run(self):
        try:
            is_frozen = bool(getattr(sys, "frozen", False))
            exe_url = str(self.update_info.get("exe_url") or "")
            exe_sha_url = str(self.update_info.get("exe_sha256_url") or "")
            zip_url = str(self.update_info.get("zip_url") or "")
            zip_sha_url = str(self.update_info.get("zip_sha256_url") or "")
            source_url = str(self.update_info.get("source_url") or "")
            ver = str(self.update_info.get("latest_version") or APP_VERSION)

            if is_frozen and sys.platform == "win32":
                current_exe = Path(sys.executable).resolve()
                install_dir = current_exe.parent
                is_onedir = (install_dir / "_internal").is_dir()

                # Вариант 1: Сборка в папке (--onedir) и есть ZIP-архив релиза
                if is_onedir and zip_url:
                    import zipfile
                    temp_dir = app_cache_directory() / "updater"
                    if temp_dir.exists():
                        shutil.rmtree(temp_dir, ignore_errors=True)
                    temp_dir.mkdir(parents=True, exist_ok=True)
                    zip_path = temp_dir / "AuroraMusicPlayer-update.zip"
                    self._download_file(zip_url, zip_path, "Скачивание ZIP-сборки")
                    self._verify_optional_sha256(zip_path, zip_sha_url)
                    self.progress_changed.emit(99, "Распаковка обновления…")
                    extract_dir = temp_dir / "extracted"
                    with zipfile.ZipFile(zip_path, "r") as zf:
                        zf.extractall(extract_dir)
                    source_root = extract_dir / "AuroraMusicPlayer"
                    if not source_root.is_dir():
                        source_root = extract_dir
                    bat_path = temp_dir / "apply_aurora_update.bat"
                    pid = os.getpid()
                    bat_content = (
                        "@echo off\r\n"
                        "chcp 65001 >nul\r\n"
                        "title Обновление Aurora Music Player...\r\n"
                        f":wait_loop\r\n"
                        f'tasklist /FI "PID eq {pid}" 2>NUL | find /I "{pid}" >NUL\r\n'
                        "if not errorlevel 1 (\r\n"
                        "    timeout /t 1 /nobreak >nul\r\n"
                        "    goto wait_loop\r\n"
                        ")\r\n"
                        f'xcopy /E /Y /I "{source_root}\\*" "{install_dir}\\" >nul\r\n'
                        f'start "" "{current_exe}"\r\n'
                        'del "%~f0"\r\n'
                    )
                    bat_path.write_text(bat_content, encoding="utf-8")
                    self.progress_changed.emit(100, "Готово к перезапуску!")
                    self.update_ready_to_restart.emit(str(bat_path), f"Версия v{ver} скачана и готова к установке.")
                    return

                # Вариант 2: Одиночный EXE (--onefile) или обновление самого EXE
                if exe_url:
                    new_exe = current_exe.with_suffix(".new.exe")
                    self._download_file(exe_url, new_exe, "Скачивание AuroraMusicPlayer.exe")
                    self._verify_optional_sha256(new_exe, exe_sha_url)
                    with open(new_exe, "rb") as f:
                        if f.read(2) != b"MZ":
                            new_exe.unlink(missing_ok=True)
                            raise RuntimeError("Скачанный файл не является корректным приложением Windows (.exe).")
                    temp_dir = app_cache_directory() / "updater"
                    temp_dir.mkdir(parents=True, exist_ok=True)
                    bat_path = temp_dir / "apply_aurora_exe_update.bat"
                    pid = os.getpid()
                    bat_content = (
                        "@echo off\r\n"
                        "chcp 65001 >nul\r\n"
                        "title Обновление Aurora Music Player...\r\n"
                        f":wait_loop\r\n"
                        f'tasklist /FI "PID eq {pid}" 2>NUL | find /I "{pid}" >NUL\r\n'
                        "if not errorlevel 1 (\r\n"
                        "    timeout /t 1 /nobreak >nul\r\n"
                        "    goto wait_loop\r\n"
                        ")\r\n"
                        f'move /Y "{new_exe}" "{current_exe}" >nul\r\n'
                        f'start "" "{current_exe}"\r\n'
                        'del "%~f0"\r\n'
                    )
                    bat_path.write_text(bat_content, encoding="utf-8")
                    self.progress_changed.emit(100, "Готово к перезапуску!")
                    self.update_ready_to_restart.emit(str(bat_path), f"Новый AuroraMusicPlayer.exe (v{ver}) готов к запуску.")
                    return

            # Вариант 3: Запуск из исходного .py файла в git-репозитории (git pull)
            app_root = Path(__file__).resolve().parent
            if not is_frozen and (app_root / ".git").exists():
                try:
                    self.progress_changed.emit(35, "Обновление через git pull…")
                    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if sys.platform == "win32" else 0
                    pull_proc = subprocess.run(
                        ["git", "pull", "--ff-only"],
                        cwd=str(app_root), capture_output=True, text=True, timeout=15, creationflags=flags
                    )
                    if pull_proc.returncode == 0:
                        self.progress_changed.emit(100, "Обновление через Git завершено!")
                        self.update_ready_to_restart.emit("__python_restart__", f"Приложение обновлено через Git до актуальной версии v{ver}.")
                        return
                except Exception:
                    pass

            # Вариант 4: Запуск из исходного .py файла — обновляем скрипт напрямую из ветки main
            if source_url:
                import ast
                script_path = Path(__file__).resolve()
                temp_py = script_path.with_suffix(".update_tmp.py")
                self._download_file(source_url, temp_py, "Скачивание новой версии скрипта")
                code_text = temp_py.read_text(encoding="utf-8")
                ast.parse(code_text)
                backup_py = script_path.with_suffix(".bak.py")
                try:
                    shutil.copy2(script_path, backup_py)
                except OSError:
                    pass
                temp_py.replace(script_path)
                self.progress_changed.emit(100, "Обновление установлено!")
                self.update_ready_to_restart.emit("__python_restart__", f"Исходный код обновлён до версии v{ver}.")
                return

            raise RuntimeError("В релизе пока нет готового .exe файла. Дождитесь завершения сборки в GitHub Actions.")
        except Exception as exc:
            if not self._cancel_requested:
                self.update_failed.emit(str(exc))

AURORA_TRACK_MIME = "application/x-aurora-track"
AURORA_PLAYLIST_MIME = "application/x-aurora-playlist-id"


class ClickableLabel(QLabel):
    """QLabel с сигналом клика — используется для обложки и названия трека."""
    clicked = pyqtSignal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._press_pos = None
        self._dragged = False
        self._hover_overlay = False

    def set_hover_overlay(self, hovered):
        hovered = bool(hovered)
        if self._hover_overlay != hovered:
            self._hover_overlay = hovered
            self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            parent = self.parentWidget()
            if parent is not None and parent.__class__.__name__ == "TrackRow":
                self._press_pos = event.position().toPoint()
                self._dragged = False
                parent._drag_start_pos = self.mapTo(parent, self._press_pos)
                parent._drag_in_progress = False
                event.accept()
                return
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (event.buttons() & Qt.MouseButton.LeftButton) and self._press_pos is not None:
            parent = self.parentWidget()
            if parent is not None and hasattr(parent, "_maybe_begin_drag"):
                mapped = self.mapTo(parent, event.position().toPoint())
                if parent._maybe_begin_drag(mapped):
                    self._dragged = True
                    self._press_pos = None
                    event.accept()
                    return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._press_pos is not None:
            was_dragged = self._dragged
            self._press_pos = None
            self._dragged = False
            if not was_dragged and self.rect().contains(event.position().toPoint()):
                self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.objectName() != "rowCover":
            return
        parent = self.parentWidget()
        is_row = parent is not None and parent.__class__.__name__ == "TrackRow"
        is_current = bool(is_row and getattr(parent, "_is_current", False))
        is_loading = bool(is_row and getattr(parent, "_loading", False))
        is_compact = bool(is_row and getattr(parent, "compact", False))
        # В компактном режиме (очередь / недавно слушал) поверх обложки уже рисуется CompactNowPlayingBadge
        if is_compact and (is_current or is_loading):
            return
        # В обычных строках (поиск, лайки, плейлисты) слева уже есть индикатор/номер трека,
        # а справа кнопка Play. На обложке не дублируем второй значок, оставляя только один чёткий индикатор.
        show_hover_play = bool(self._hover_overlay and is_compact)
        if not show_hover_play:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect())
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(8, 12, 18, 142 if is_current else 150))
        painter.drawRoundedRect(rect, 8.0, 8.0)

        win = self.window()
        accent = getattr(win, "chameleon_bright", QColor("#1ED760")) if getattr(win, "chameleon_enabled", True) else QColor("#1ED760")
        cx, cy = rect.center().x(), rect.center().y()

        # Внешнее мягкое свечение вокруг медальона
        halo = QRadialGradient(cx, cy, 16.5)
        halo_c = QColor(accent)
        halo_c.setAlpha(72 if is_current else 52)
        halo.setColorAt(0.0, halo_c)
        halo_c2 = QColor(accent)
        halo_c2.setAlpha(0)
        halo.setColorAt(1.0, halo_c2)
        painter.setBrush(QBrush(halo))
        painter.drawEllipse(QPointF(cx, cy), 16.5, 16.5)

        # Тёмный стеклянный медальон с неоновым ободком
        ring_col = QColor(accent)
        ring_col.setAlpha(185 if is_current else 145)
        painter.setBrush(QColor(11, 16, 23, 222))
        painter.setPen(QPen(ring_col, 1.35))
        painter.drawEllipse(QPointF(cx, cy), 13.0, 13.0)

        if is_current:
            playing = bool(getattr(parent, "_is_playing", False))
            phase = int(getattr(parent, "_eq_phase", 0))
            t = phase * 0.32
            if playing:
                levels = (
                    0.42 + 0.48 * (0.5 + 0.5 * math.sin(t + 0.2)),
                    0.50 + 0.50 * (0.5 + 0.5 * math.sin(t * 1.28 + 1.7)),
                    0.46 + 0.52 * (0.5 + 0.5 * math.sin(t * 1.12 + 3.1)),
                    0.38 + 0.46 * (0.5 + 0.5 * math.sin(t * 0.94 + 4.4)),
                )
            else:
                levels = (0.36, 0.72, 0.54, 0.36)
            bar_w = 2.1
            gap = 1.65
            total_w = 4 * bar_w + 3 * gap
            start_x = cx - total_w / 2.0
            max_h = 11.6
            min_h = 3.2
            painter.setPen(Qt.PenStyle.NoPen)
            for idx, lvl in enumerate(levels):
                bh = min_h + (max_h - min_h) * max(0.0, min(1.0, lvl))
                bx = start_x + idx * (bar_w + gap)
                by = cy - bh / 2.0
                bgrad = QLinearGradient(bx, by, bx, by + bh)
                top_c = QColor("#FFFFFF") if idx in (1, 2) and playing else QColor(accent).lighter(120)
                bgrad.setColorAt(0.0, top_c)
                bgrad.setColorAt(0.5, accent)
                bgrad.setColorAt(1.0, QColor(accent).darker(115))
                painter.setBrush(QBrush(bgrad))
                painter.drawRoundedRect(QRectF(bx, by, bar_w, bh), bar_w / 2.0, bar_w / 2.0)
        else:
            icon_rect = QRectF(cx - 6.5, cy - 7.0, 14.0, 14.0)
            draw_vector_icon(painter, "play", icon_rect, "#FFFFFF")
        painter.end()


class LikesCollageCover(QWidget):
    """Коллаж 2×2 из обложек любимых треков или неоновая градиентная эмблема для шапки раздела «Лайки»."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(112, 112)
        self._covers = []
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def set_covers(self, pixmaps):
        valid = [pm for pm in (pixmaps or []) if isinstance(pm, QPixmap) and not pm.isNull()][:4]
        keys = tuple(pm.cacheKey() for pm in valid)
        old_keys = tuple(pm.cacheKey() for pm in self._covers)
        if keys != old_keys:
            self._covers = valid
            self.update()

    def set_pixmaps(self, pixmaps):
        self.set_covers(pixmaps)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        box = QRectF(4.0, 4.0, self.width() - 8.0, self.height() - 8.0)
        radius = 16.0

        # Мягкая глубокая тень
        painter.setPen(Qt.PenStyle.NoPen)
        for dy, expand, alpha in ((4.0, 2.5, 36), (2.0, 1.0, 58)):
            painter.setBrush(QColor(0, 0, 0, alpha))
            painter.drawRoundedRect(box.adjusted(-expand, dy - expand, expand, dy + expand), radius + 1.5, radius + 1.5)

        clip = QPainterPath()
        clip.addRoundedRect(box, radius, radius)
        painter.save()
        painter.setClipPath(clip)

        grad = QLinearGradient(box.topLeft(), box.bottomRight())
        grad.setColorAt(0.0, QColor("#5B3DF5"))
        grad.setColorAt(0.52, QColor("#246B6B"))
        grad.setColorAt(1.0, QColor("#1DB954"))
        painter.fillPath(clip, grad)

        if len(self._covers) >= 4:
            half_w = box.width() / 2.0
            half_h = box.height() / 2.0
            cells = (
                QRectF(box.left(), box.top(), half_w, half_h),
                QRectF(box.left() + half_w, box.top(), half_w, half_h),
                QRectF(box.left(), box.top() + half_h, half_w, half_h),
                QRectF(box.left() + half_w, box.top() + half_h, half_w, half_h),
            )
            for cell, pm in zip(cells, self._covers[:4]):
                sw, sh = float(pm.width()), float(pm.height())
                s = min(sw, sh)
                src = QRectF((sw - s) / 2.0, (sh - s) / 2.0, s, s)
                painter.drawPixmap(cell, pm, src)
            painter.setPen(QPen(QColor(15, 20, 28, 150), 1.4))
            painter.drawLine(QPointF(box.center().x(), box.top()), QPointF(box.center().x(), box.bottom()))
            painter.drawLine(QPointF(box.left(), box.center().y()), QPointF(box.right(), box.center().y()))
        elif self._covers:
            pm = self._covers[0]
            sw, sh = float(pm.width()), float(pm.height())
            s = min(sw, sh)
            src = QRectF((sw - s) / 2.0, (sh - s) / 2.0, s, s)
            painter.drawPixmap(box, pm, src)
            painter.fillRect(box, QColor(12, 18, 26, 55))

        # Центральный стеклянный медальон с сердечком
        cx, cy = box.center().x(), box.center().y()
        badge_r = 18.0 if self._covers else 26.0
        painter.setPen(QPen(QColor(255, 255, 255, 65), 1.2))
        painter.setBrush(QColor(14, 20, 28, 195 if self._covers else 110))
        painter.drawEllipse(QPointF(cx, cy), badge_r, badge_r)
        heart_side = badge_r * 1.15
        draw_vector_icon(
            painter, "heart",
            QRectF(cx - heart_side / 2.0, cy - heart_side / 2.0, heart_side, heart_side),
            "#1ED760" if self._covers else "#FFFFFF",
        )
        painter.restore()

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(255, 255, 255, 42), 1.1))
        painter.drawRoundedRect(box.adjusted(0.5, 0.5, -0.5, -0.5), radius - 0.5, radius - 0.5)
        painter.end()


class ExpandedArtwork(QLabel):
    """Крупная обложка со скруглёнными краями и вращающейся виниловой пластинкой над миниатюрой внизу."""
    clicked = pyqtSignal()
    SQUARE_SIDE = 186
    CORNER_RADIUS = 16.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self._source = None
        self._scale_key = None
        self._vinyl_angle = 0.0
        self._vinyl_timer = QTimer(self)
        self._vinyl_timer.setInterval(36)
        self._vinyl_timer.timeout.connect(self._step_vinyl)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Свернуть обложку (Esc)")

    def _step_vinyl(self):
        if not self.isVisible():
            self._vinyl_timer.stop()
            return
        win = self.window()
        playing = bool(
            win is not None
            and hasattr(win, "player")
            and win.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        )
        if playing and getattr(win, "vinyl_enabled", True):
            self._vinyl_angle = (self._vinyl_angle + 1.65) % 360.0
            self.update()

    def sync_vinyl_state(self):
        if not self.isVisible():
            self._vinyl_timer.stop()
            return
        win = self.window()
        playing = bool(
            win is not None
            and hasattr(win, "player")
            and win.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        )
        if playing and getattr(win, "vinyl_enabled", True):
            if not self._vinyl_timer.isActive():
                self._vinyl_timer.start()
        else:
            self._vinyl_timer.stop()
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        self.sync_vinyl_state()

    def hideEvent(self, event):
        self._vinyl_timer.stop()
        super().hideEvent(event)

    def set_artwork(self, pixmap):
        self._source = pixmap
        self._scale_key = None
        self._render_cover()
        self.update()

    def clear_artwork(self):
        self._source = None
        self._scale_key = None
        self.clear()
        self.setProperty("requested_image", "")

    def target_size(self):
        win = self.window()
        vinyl_on = getattr(win, "vinyl_enabled", True)
        extra_w = 78 if vinyl_on else 12
        return QSize(self.SQUARE_SIDE + extra_w, self.SQUARE_SIDE + 16)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._render_cover()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def _render_cover(self):
        if self._source is None or self._source.isNull():
            return
        dpr = min(2.0, self.devicePixelRatioF())
        key = (self._source.cacheKey(), self.SQUARE_SIDE, dpr)
        if key == self._scale_key:
            return
        self._scale_key = key
        pixels = max(1, round(self.SQUARE_SIDE * dpr))
        scaled = self._source.scaled(pixels, pixels, Qt.AspectRatioMode.KeepAspectRatio,
                                     Qt.TransformationMode.SmoothTransformation)
        scaled.setDevicePixelRatio(dpr)
        self.setPixmap(scaled)

    def paintEvent(self, event):
        src = self._source if (self._source is not None and not self._source.isNull()) else self.pixmap()
        if src is None or src.isNull():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        avail = QRectF(self.rect()).adjusted(6.0, 6.0, -6.0, -10.0)
        side = min(avail.width(), avail.height())
        if side <= 4:
            painter.end()
            return
        win = self.window()
        vinyl_on = bool(getattr(win, "vinyl_enabled", True) and avail.width() >= side + 32)
        left_x = avail.left() + 2.0 if vinyl_on else (avail.center().x() - side / 2.0)
        target = QRectF(
            left_x,
            avail.center().y() - side / 2.0,
            side,
            side,
        )
        radius = min(self.CORNER_RADIUS, side * 0.22)
        sw = float(src.width())
        sh = float(src.height())
        crop_side = min(sw, sh)
        src_rect = QRectF((sw - crop_side) / 2.0, (sh - crop_side) / 2.0, crop_side, crop_side)

        # 1. Атмосферное свечение цвета обложки позади конверта
        accent = getattr(win, "chameleon_bright", QColor("#1ED760")) if getattr(win, "chameleon_enabled", True) else QColor("#1ED760")
        glow_color = QColor(accent)
        glow_color.setAlpha(46)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow_color)
        painter.drawRoundedRect(target.adjusted(-4.0, -2.0, 4.0, 5.0), radius + 4.0, radius + 4.0)

        # 2. Вращающаяся виниловая пластинка, выступающая справа из-за обложки
        if vinyl_on:
            disc_d = side * 0.92
            disc_cx = min(avail.right() - disc_d / 2.0 - 2.0, target.right() + disc_d * 0.34)
            disc_cy = target.center().y()
            disc_rect = QRectF(disc_cx - disc_d / 2.0, disc_cy - disc_d / 2.0, disc_d, disc_d)

            painter.save()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(0, 0, 0, 110))
            painter.drawEllipse(disc_rect.adjusted(-1.0, 3.0, 2.0, 4.0))

            disc_grad = QRadialGradient(disc_cx, disc_cy, disc_d / 2.0)
            disc_grad.setColorAt(0.0, QColor("#232834"))
            disc_grad.setColorAt(0.38, QColor("#12151C"))
            disc_grad.setColorAt(0.88, QColor("#090B0F"))
            disc_grad.setColorAt(1.0, QColor("#1D232E"))
            painter.setBrush(QBrush(disc_grad))
            painter.setPen(QPen(QColor(255, 255, 255, 36), 1.0))
            painter.drawEllipse(disc_rect)

            painter.translate(disc_cx, disc_cy)
            painter.rotate(self._vinyl_angle)

            # Блик и дорожки винила
            sheen = QPolygonF([
                QPointF(0, 0),
                QPointF(-disc_d * 0.45, -disc_d * 0.16),
                QPointF(-disc_d * 0.16, -disc_d * 0.45),
            ])
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 255, 255, 18))
            painter.drawPolygon(sheen)
            sheen2 = QPolygonF([
                QPointF(0, 0),
                QPointF(disc_d * 0.45, disc_d * 0.16),
                QPointF(disc_d * 0.16, disc_d * 0.45),
            ])
            painter.drawPolygon(sheen2)

            painter.setBrush(Qt.BrushStyle.NoBrush)
            for gr_idx, ratio in enumerate((0.86, 0.76, 0.66, 0.56, 0.47)):
                gr_r = (disc_d / 2.0) * ratio
                pen = QPen(QColor(255, 255, 255, 24 if gr_idx % 2 == 0 else 13), 0.9)
                pen.setDashPattern([18.0, 8.0])
                painter.setPen(pen)
                painter.drawEllipse(QPointF(0, 0), gr_r, gr_r)

            # Круглое яблоко пластинки из обложки трека
            label_r = disc_d * 0.19
            label_rect = QRectF(-label_r, -label_r, label_r * 2.0, label_r * 2.0)
            label_clip = QPainterPath()
            label_clip.addEllipse(label_rect)
            painter.save()
            painter.setClipPath(label_clip)
            painter.drawPixmap(label_rect, src, src_rect)
            painter.restore()

            painter.setPen(QPen(accent, 1.4))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(label_rect)

            # Центральное отверстие шпинделя
            painter.setPen(QPen(QColor(255, 255, 255, 90), 1.0))
            painter.setBrush(QColor("#0B0D12"))
            painter.drawEllipse(QPointF(0, 0), 4.2, 4.2)
            painter.restore()

        # 3. Мягкая тёмная тень под квадратной обложкой
        painter.setPen(Qt.PenStyle.NoPen)
        for dy, expand, alpha in ((4.0, 2.0, 34), (2.5, 1.0, 52), (1.0, 0.0, 72)):
            painter.setBrush(QColor(0, 0, 0, alpha))
            painter.drawRoundedRect(target.adjusted(-expand, dy - expand, expand, dy + expand), radius + 1.0, radius + 1.0)
        clip = QPainterPath()
        clip.addRoundedRect(target, radius, radius)
        painter.save()
        painter.setClipPath(clip)
        painter.drawPixmap(target, src, src_rect)
        painter.restore()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(255, 255, 255, 38), 1.1))
        painter.drawRoundedRect(target.adjusted(0.5, 0.5, -0.5, -0.5), max(1.0, radius - 0.5), max(1.0, radius - 0.5))
        painter.end()


def read_wallpaper_image(path):
    """Decode one local frame and keep a bounded image, including EXIF rotation."""
    if not path:
        return QImage()
    try:
        image_path = Path(path)
        if not image_path.is_file() or image_path.stat().st_size > 40_000_000:
            return QImage()
        reader = QImageReader(str(image_path))
        reader.setAutoTransform(True)
        size = reader.size()
        if not size.isValid() or size.width() * size.height() > 36_000_000:
            return QImage()
        if max(size.width(), size.height()) > 2048:
            reader.setScaledSize(size.scaled(2048, 2048, Qt.AspectRatioMode.KeepAspectRatio))
        return reader.read()
    except (OSError, ValueError, TypeError):
        return QImage()


class PlayerBackdrop(QWidget):
    """Static wallpaper; hover paints reuse the composed bitmap without scaling."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.image = QPixmap()
        self.theme = "dark"
        self.dim = 55
        self._cache = None
        self._cache_key = None

    @property
    def has_wallpaper(self):
        return not self.image.isNull()

    def set_image(self, image):
        self.image = QPixmap.fromImage(image) if not image.isNull() else QPixmap()
        self._cache = None
        self.update()

    def set_appearance(self, theme, dim):
        if self.theme != theme or self.dim != dim:
            self.theme, self.dim = theme, dim
            self._cache = None
            self.update()

    def paintEvent(self, event):
        if not self.has_wallpaper:
            painter = QPainter(self)
            painter.fillRect(self.rect(), QColor("#0B0D10" if self.theme == "dark" else "#E9EDF2"))
            painter.end()
            return
        key = (self.size(), self.devicePixelRatioF(), self.theme, self.dim)
        if self._cache is None or key != self._cache_key:
            dpr = self.devicePixelRatioF()
            # A wallpaper is deliberately capped at 2048 px even on 4K/HiDPI screens.
            pixels = QSize(max(1, round(self.width() * dpr)), max(1, round(self.height() * dpr)))
            if max(pixels.width(), pixels.height()) > 2048:
                pixels = pixels.scaled(2048, 2048, Qt.AspectRatioMode.KeepAspectRatio)
            bitmap = QPixmap(pixels)
            bitmap.fill(QColor("#0B0D10" if self.theme == "dark" else "#E9EDF2"))
            if self.has_wallpaper:
                painter = QPainter(bitmap)
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                target = QRectF(0, 0, pixels.width(), pixels.height())
                ratio = max(pixels.width() / self.image.width(), pixels.height() / self.image.height())
                crop_w, crop_h = pixels.width() / ratio, pixels.height() / ratio
                crop = QRectF((self.image.width() - crop_w) / 2, (self.image.height() - crop_h) / 2, crop_w, crop_h)
                painter.drawPixmap(target, self.image, crop)
                painter.fillRect(target, QColor(0, 0, 0, round(255 * self.dim / 100)))
                painter.end()
            self._cache, self._cache_key = bitmap, key
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self._cache)
        painter.end()


def make_service_artwork(source, pixel_size=80):
    """Small local artwork for navigation; no downloads or emoji fonts."""
    pixmap = QPixmap(pixel_size, pixel_size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    if source == "brand":
        brand_pm = _custom_brand_pixmap()
        painter.scale(pixel_size / 80, pixel_size / 80)
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(1, 1, 78, 78), 18, 18)
        painter.save()
        painter.setClipPath(clip)
        if not brand_pm.isNull():
            scaled = brand_pm.scaled(
                max(1, int(pixel_size)),
                max(1, int(pixel_size)),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            scaled.setDevicePixelRatio(1)
            painter.drawPixmap(QRectF(0, 0, 80, 80), scaled, QRectF(0, 0, scaled.width(), scaled.height()))
        else:
            painter.fillPath(clip, QColor("#040406"))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for radius, width in ((35.5, 2.2), (31.0, 1.8), (19.5, 2.0), (16.0, 1.5)):
                painter.setPen(QPen(QColor("#E11919"), width))
                painter.drawEllipse(QPointF(40, 40), radius, radius)
            for angle_deg in (90, 210, 330):
                rad = math.radians(angle_deg)
                cx = 40 + 8.5 * math.cos(rad)
                cy = 40 - 8.5 * math.sin(rad)
                painter.setPen(QPen(QColor("#E11919"), 1.8))
                painter.drawEllipse(QPointF(cx, cy), 5.2, 5.2)
        painter.restore()
        painter.end()
        pixmap.setDevicePixelRatio(2)
        return pixmap
    painter.scale(pixel_size / 80, pixel_size / 80)
    colors = {
        "youtube": ("#2B0710", "#E11D48", "#FB7185"),
        "soundcloud": ("#260E04", "#EA580C", "#FBBF24"),
        "likes": ("#12092B", "#6D28D9", "#EC4899"),
        "supermix": ("#1F080E", "#E11D48", "#F59E0B"),
        "shuffle": ("#061D24", "#0891B2", "#10B981"),
        "my_mix_1": ("#07142B", "#2563EB", "#38BDF8"),
        "my_mix_2": ("#062019", "#059669", "#A3E635"),
        "my_mix_3": ("#230820", "#BE185D", "#FB7185"),
        "discover_mix": ("#130829", "#7C3AED", "#E879F9"),
        "new_release_mix": ("#230F05", "#EA580C", "#FDE047"),
        "replay_mix": ("#170924", "#9333EA", "#22D3EE"),
        "playlist": ("#0C192E", "#2563EB", "#60A5FA"),
        "user_playlist": ("#071F15", "#10B981", "#34D399"),
        "folder": ("#141D2B", "#334155", "#94A3B8"),
        "brand": ("#160406", "#050507", "#E11919"),
    }
    c_dark, c_mid, c_glow = colors.get(source, colors["brand"])
    gradient = QLinearGradient(0, 0, 80, 80)
    gradient.setColorAt(0.0, QColor(c_dark))
    gradient.setColorAt(0.58, QColor(c_mid))
    gradient.setColorAt(1.0, QColor(c_glow).darker(125))
    clip = QPainterPath()
    clip.addRoundedRect(QRectF(1, 1, 78, 78), 18, 18)
    painter.save()
    painter.setClipPath(clip)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.fillPath(clip, gradient)
    orb = QRadialGradient(QPointF(64, 16), 48)
    oc = QColor(c_glow)
    oc.setAlpha(135)
    orb.setColorAt(0.0, oc)
    orb.setColorAt(1.0, QColor(0, 0, 0, 0))
    painter.fillRect(QRectF(0, 0, 80, 80), orb)
    # Мини-виниловый стеклянный медальон в центре иконки
    painter.setBrush(QColor(10, 14, 22, 175))
    ring_c = QColor(c_glow)
    ring_c.setAlpha(150)
    painter.setPen(QPen(ring_c, 1.2))
    painter.drawEllipse(QPointF(40, 40), 25, 25)
    painter.restore()
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(QColor(255, 255, 255, 42), 1.4))
    painter.drawPath(clip)
    kind = {
        "youtube": "play",
        "soundcloud": "cloud",
        "likes": "heart",
        "supermix": "supermix",
        "shuffle": "headphones",
        "my_mix_1": "music",
        "my_mix_2": "supermix",
        "my_mix_3": "headphones",
        "discover_mix": "supermix",
        "new_release_mix": "play",
        "replay_mix": "repeat",
        "playlist": "music",
        "user_playlist": "music",
        "folder": "folder",
        "brand": "music",
    }.get(source, "music")
    draw_vector_icon(painter, kind, QRectF(24, 24, 32, 32), "#FFFFFF")
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return pixmap


class AnimatedNavButton(QPushButton):
    """Элемент источника/раздела внутри «Моей медиатеки» в стиле Spotify."""
    def __init__(self, icon_text, title, parent=None, subtitle=""):
        super().__init__(parent)
        self.setObjectName("navButton")
        self.setCheckable(True)
        self.setFixedHeight(50)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._nav_icon = icon_text
        self._nav_title = title
        source = "youtube" if "youtube" in title.casefold() else "soundcloud" if "soundcloud" in title.casefold() else "likes"
        default_subtitles = {
            "youtube": "Каталог • Рекомендации",
            "soundcloud": "Поток • Треки и волны",
            "likes": "Плейлист • Любимая музыка",
        }
        self._nav_subtitle = str(subtitle or default_subtitles.get(source, ""))
        self._service_artwork = make_service_artwork(source, 76)
        self._collapsed = False
        self._theme = "dark"
        self._base_color = QColor("#F4F7FB")
        self._hover_color = QColor("#FFFFFF")
        self._active_color = QColor("#1ED760")
        self._text_color = QColor(self._base_color)
        self._color_animation = QVariantAnimation(self)
        self._color_animation.setDuration(180)
        self._color_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._color_animation.valueChanged.connect(self._set_animated_color)
        self.toggled.connect(self._checked_changed)
        self.setAccessibleName(f"{self._nav_title}: {self._nav_subtitle}" if self._nav_subtitle else self._nav_title)
        self.setToolTip(f"{self._nav_title}\n{self._nav_subtitle}" if self._nav_subtitle else self._nav_title)
        self.setStyleSheet("QPushButton#navButton { border: none; padding: 0; background: transparent; }")

    def set_subtitle(self, subtitle):
        subtitle = str(subtitle or "")
        if self._nav_subtitle != subtitle:
            self._nav_subtitle = subtitle
            self.setAccessibleName(f"{self._nav_title}: {self._nav_subtitle}" if self._nav_subtitle else self._nav_title)
            self.setToolTip(f"{self._nav_title}\n{self._nav_subtitle}" if self._nav_subtitle else self._nav_title)
            self.update()

    def set_collapsed(self, collapsed):
        self._collapsed = bool(collapsed)
        self.setText(self._nav_icon if self._collapsed else f"{self._nav_icon}    {self._nav_title}")
        self.update()

    def set_theme(self, theme):
        self._theme = "light" if theme == "light" else "dark"
        if self._theme == "light":
            self._base_color = QColor("#141C26")
            self._hover_color = QColor("#141C26")
            self._active_color = QColor("#167A40")
        else:
            self._base_color = QColor("#F4F7FB")
            self._hover_color = QColor("#FFFFFF")
            self._active_color = QColor("#1ED760")
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
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
        if self.isChecked() or self.underMouse() or self.isDown():
            if self._theme == "light":
                background = QColor("#E2F3E8" if self.isChecked() else ("#DCE5EE" if self.isDown() else "#EDF2F7"))
                border = QColor("#A9DBC0" if self.isChecked() else "#D7E0EA")
            else:
                background = QColor("#162920" if self.isChecked() else ("#222B37" if self.isDown() else "#1A212C"))
                border = QColor("#29543D" if self.isChecked() else "#26303F")
            painter.setPen(QPen(border, 1.0))
            painter.setBrush(background)
            painter.drawRoundedRect(rect, 9.0, 9.0)
        if self.isChecked():
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#1DB954"))
            indicator = QRectF(rect.left() + 1.0, rect.top() + 10.0,
                               3.0, max(12.0, rect.height() - 20.0))
            painter.drawRoundedRect(indicator, 1.5, 1.5)
        icon_rect = QRectF(rect.center().x() - 19.0 if self._collapsed else 6.0,
                           6.0, 38.0, 38.0)
        painter.drawPixmap(icon_rect, self._service_artwork, QRectF(0, 0, 76, 76))
        if not self._collapsed:
            text_left = 51
            text_w = max(20, int(self.width() - text_left - 8))
            title_font = QFont(self.font())
            title_font.setPixelSize(12)
            title_font.setWeight(QFont.Weight.Bold if self.isChecked() else QFont.Weight.DemiBold)
            painter.setFont(title_font)
            painter.setPen(self._text_color)
            title_rect = QRect(text_left, 7, text_w, 18)
            painter.drawText(
                title_rect,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                QFontMetrics(title_font).elidedText(self._nav_title, Qt.TextElideMode.ElideRight, text_w),
            )
            sub_font = QFont(self.font())
            sub_font.setPixelSize(11)
            sub_font.setWeight(QFont.Weight.Medium)
            painter.setFont(sub_font)
            painter.setPen(QColor("#5C697C" if self._theme == "light" else "#8F9BAE"))
            sub_rect = QRect(text_left, 25, text_w, 17)
            painter.drawText(
                sub_rect,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                QFontMetrics(sub_font).elidedText(self._nav_subtitle, Qt.TextElideMode.ElideRight, text_w),
            )
        painter.end()


class SidebarMediaItem(QPushButton):
    """Компактная строка «Моей медиатеки» в стиле Spotify с фото-обложкой 38×38 и поддержкой Drag & Drop."""
    track_dropped = pyqtSignal(str, object)
    playlist_dropped = pyqtSignal(str, str)

    def __init__(self, title, subtitle, artwork_kind="likes", parent=None, *,
                 playlist_id="", folder_name="", is_folder=False, folder_collapsed=False, indent_level=0):
        super().__init__(parent)
        self.setObjectName("sidebarMediaItem")
        self.setFixedHeight(46 if is_folder else 50)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.item_title = str(title or "")
        self.item_subtitle = str(subtitle or "")
        self.playlist_id = str(playlist_id or "")
        self.folder_name = str(folder_name or "")
        self.is_folder = bool(is_folder)
        self.folder_collapsed = bool(folder_collapsed)
        self.indent_level = max(0, int(indent_level or 0))
        self._playing = False
        self._active_selected = False
        self._pinned = False
        self._drop_hover = False
        self._drag_start_pos = None
        self.track_key = ""
        self.cover_label = QLabel(self)
        self.cover_label.setObjectName("sidebarMediaCover")
        side = 34 if is_folder else 38
        self.cover_label.setFixedSize(side, side)
        left_offset = 6 + self.indent_level * 12
        self.cover_label.move(left_offset, (self.height() - side) // 2)
        self.cover_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        default_art = make_service_artwork(artwork_kind, side * 2)
        self.cover_label.setPixmap(default_art)
        if self.playlist_id or self.is_folder:
            self.setAcceptDrops(True)
        self.setAccessibleName(f"{self.item_title}: {self.item_subtitle}")
        self.setToolTip(f"{self.item_title}\n{self.item_subtitle}" if self.item_subtitle else self.item_title)
        self.setStyleSheet("QPushButton#sidebarMediaItem { border: none; padding: 0; background: transparent; }")

    def set_metadata(self, title=None, subtitle=None):
        if title is not None:
            self.item_title = str(title)
        if subtitle is not None:
            self.item_subtitle = str(subtitle)
        self.setAccessibleName(f"{self.item_title}: {self.item_subtitle}")
        self.setToolTip(f"{self.item_title}\n{self.item_subtitle}" if self.item_subtitle else self.item_title)
        self.update()

    def set_playing(self, playing):
        playing = bool(playing)
        if self._playing != playing:
            self._playing = playing
            self.update()

    def set_active_selected(self, selected):
        selected = bool(selected)
        if self._active_selected != selected:
            self._active_selected = selected
            self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.playlist_id and not self.is_folder:
            self._drag_start_pos = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (
            (event.buttons() & Qt.MouseButton.LeftButton)
            and self.playlist_id
            and not self.is_folder
            and self._drag_start_pos is not None
            and (event.position().toPoint() - self._drag_start_pos).manhattanLength() >= QApplication.startDragDistance()
        ):
            self._drag_start_pos = None
            self.setDown(False)
            drag = QDrag(self)
            mime = QMimeData()
            mime.setData(AURORA_PLAYLIST_MIME, self.playlist_id.encode("utf-8"))
            mime.setText(self.item_title)
            drag.setMimeData(mime)
            pm = QPixmap(176, 38)
            pm.fill(Qt.GlobalColor.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            p.setBrush(QColor(22, 32, 42, 235))
            p.setPen(QPen(QColor("#1DB954"), 1.3))
            p.drawRoundedRect(QRectF(1, 1, 174, 36), 9, 9)
            p.setPen(QColor("#F2F6FA"))
            font = QFont(self.font())
            font.setPixelSize(12)
            font.setWeight(QFont.Weight.Bold)
            p.setFont(font)
            p.drawText(QRect(12, 0, 152, 38), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       QFontMetrics(font).elidedText(f"♫  {self.item_title}", Qt.TextElideMode.ElideRight, 152))
            p.end()
            drag.setPixmap(pm)
            drag.exec(Qt.DropAction.MoveAction)
            return
        super().mouseMoveEvent(event)

    def dragEnterEvent(self, event):
        md = event.mimeData()
        if md is not None:
            if self.playlist_id and md.hasFormat(AURORA_TRACK_MIME):
                self._drop_hover = True
                self.update()
                event.acceptProposedAction()
                return
            if self.is_folder and (md.hasFormat(AURORA_PLAYLIST_MIME) or md.hasFormat(AURORA_TRACK_MIME)):
                self._drop_hover = True
                self.update()
                event.acceptProposedAction()
                return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        md = event.mimeData()
        if md is not None and (
            (self.playlist_id and md.hasFormat(AURORA_TRACK_MIME))
            or (self.is_folder and (md.hasFormat(AURORA_PLAYLIST_MIME) or md.hasFormat(AURORA_TRACK_MIME)))
        ):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dragLeaveEvent(self, event):
        if self._drop_hover:
            self._drop_hover = False
            self.update()
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self._drop_hover = False
        self.update()
        md = event.mimeData()
        if md is None:
            return
        if self.is_folder and md.hasFormat(AURORA_PLAYLIST_MIME):
            raw_pid = bytes(md.data(AURORA_PLAYLIST_MIME)).decode("utf-8", errors="ignore").strip()
            if raw_pid:
                self.playlist_dropped.emit(raw_pid, self.folder_name)
                event.acceptProposedAction()
                return
        if md.hasFormat(AURORA_TRACK_MIME) and (self.playlist_id or self.is_folder):
            try:
                payload = json.loads(bytes(md.data(AURORA_TRACK_MIME)).decode("utf-8"))
                track = payload.get("track") if isinstance(payload, dict) and "track" in payload else payload
                if isinstance(track, dict) and track.get("url"):
                    target_id = self.playlist_id if self.playlist_id else f"folder:{self.folder_name}"
                    self.track_dropped.emit(target_id, track)
                    event.acceptProposedAction()
                    return
            except (ValueError, TypeError):
                pass
        super().dropEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        light = getattr(self.window(), "theme", "dark") == "light"
        indent_px = self.indent_level * 12
        rect = QRectF(self.rect()).adjusted(1.0 + indent_px, 1.0, -1.0, -1.0)
        hovered = self.underMouse() or self.isDown()
        active = self._playing or self._active_selected
        if self._drop_hover:
            bg = QColor("#D5F2E0" if light else "#1C3B2B")
            border = QColor("#1DB954")
            painter.setPen(QPen(border, 1.6))
            painter.setBrush(bg)
            painter.drawRoundedRect(rect, 9.0, 9.0)
        elif active or hovered:
            if light:
                bg = QColor("#E2F3E8" if active else ("#DCE5EE" if self.isDown() else "#EDF2F7"))
                border = QColor("#A9DBC0" if active else "#D7E0EA")
            else:
                bg = QColor("#162920" if active else ("#222B37" if self.isDown() else "#1A212C"))
                border = QColor("#29543D" if active else "#26303F")
            painter.setPen(QPen(border, 1.0))
            painter.setBrush(bg)
            painter.drawRoundedRect(rect, 9.0, 9.0)

        if self._active_selected and not self._playing:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#1DB954"))
            indicator = QRectF(rect.left() + 1.0, rect.top() + 10.0,
                               3.0, max(12.0, rect.height() - 20.0))
            painter.drawRoundedRect(indicator, 1.5, 1.5)

        right_pad = 22 if (self._playing or self.is_folder) else 5
        text_left = (46 if self.is_folder else 48) + indent_px
        text_w = max(20, int(self.width() - text_left - right_pad))

        title_font = QFont(self.font())
        title_font.setPixelSize(12)
        title_font.setWeight(QFont.Weight.Bold if active else QFont.Weight.DemiBold)
        painter.setFont(title_font)
        if self._playing or self._active_selected:
            title_color = QColor("#167A40" if light else "#1ED760")
        else:
            title_color = QColor("#141C26" if light else "#F4F7FB")
        painter.setPen(title_color)
        title_rect = QRect(text_left, 5 if self.is_folder else 7, text_w, 18)
        painter.drawText(
            title_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            QFontMetrics(title_font).elidedText(self.item_title, Qt.TextElideMode.ElideRight, text_w),
        )

        sub_font = QFont(self.font())
        sub_font.setPixelSize(10 if self.is_folder else 11)
        sub_font.setWeight(QFont.Weight.Medium)
        painter.setFont(sub_font)
        painter.setPen(QColor("#5C697C" if light else "#8F9BAE"))
        sub_rect = QRect(text_left, 23 if self.is_folder else 25, text_w, 16)
        painter.drawText(
            sub_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            QFontMetrics(sub_font).elidedText(self.item_subtitle, Qt.TextElideMode.ElideRight, text_w),
        )

        if self.is_folder:
            chevron = "▸" if self.folder_collapsed else "▾"
            painter.setPen(QColor("#647285" if light else "#9DA8B8"))
            chev_font = QFont(self.font())
            chev_font.setPixelSize(12)
            chev_font.setWeight(QFont.Weight.Bold)
            painter.setFont(chev_font)
            painter.drawText(QRect(self.width() - 20, 0, 16, self.height()),
                             Qt.AlignmentFlag.AlignCenter, chevron)
        elif self._playing:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#1ED760"))
            dot = QRectF(self.width() - 14, self.height() / 2 - 4, 8, 8)
            painter.drawEllipse(dot)
        painter.end()


class MarqueeLabel(QLabel):
    """Заголовок трека с аккуратным троеточием в покое и плавной прокруткой при наведении."""
    MAX_NATURAL_WIDTH = 310

    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._full_text = ""
        self._offset = 0.0
        self._hovered = False
        self._marquee_timer = QTimer(self)
        self._marquee_timer.setInterval(30)
        self._marquee_timer.timeout.connect(self._step_marquee)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        self.setMaximumWidth(self.MAX_NATURAL_WIDTH)
        self.setText(text)

    def setText(self, text):
        self._full_text = str(text or "")
        self._offset = 0.0
        super().setText(self._full_text)
        self.updateGeometry()
        self.update()

    def _step_marquee(self):
        fm = QFontMetrics(self.font())
        overflow = fm.horizontalAdvance(self._full_text) - self.contentsRect().width()
        if not self._hovered or overflow <= 4:
            self._offset = 0.0
            self._marquee_timer.stop()
            self.update()
            return
        cycle = overflow + 48.0
        self._offset = (self._offset + 1.1) % cycle
        self.update()

    def enterEvent(self, event):
        self._hovered = True
        fm = QFontMetrics(self.font())
        if fm.horizontalAdvance(self._full_text) > self.contentsRect().width() + 4:
            self._offset = 0.0
            self._marquee_timer.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self._marquee_timer.stop()
        if self._offset != 0.0:
            self._offset = 0.0
            self.update()
        super().leaveEvent(event)

    def sizeHint(self):
        base = super().sizeHint()
        fm = QFontMetrics(self.font())
        text_w = fm.horizontalAdvance(self._full_text) + 4 if self._full_text else 40
        max_w = max(self.MAX_NATURAL_WIDTH, self.maximumWidth())
        return QSize(min(max_w, max(36, text_w)), base.height())

    def minimumSizeHint(self):
        return QSize(36, super().minimumSizeHint().height())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        rect = self.contentsRect()
        painter.setClipRect(rect)
        painter.setFont(self.font())
        painter.setPen(self.palette().color(QPalette.ColorRole.WindowText))
        fm = QFontMetrics(self.font())
        baseline = rect.top() + (rect.height() - fm.height()) // 2 + fm.ascent()
        full_w = fm.horizontalAdvance(self._full_text)
        if self._hovered and full_w > rect.width() + 4 and self._offset > 0:
            shift = min(float(full_w - rect.width() + 12), self._offset)
            painter.drawText(int(rect.left() - shift), baseline, self._full_text)
        else:
            elided = fm.elidedText(self._full_text, Qt.TextElideMode.ElideRight, max(16, rect.width()))
            painter.drawText(rect.left(), baseline, elided)
        painter.end()


class TrackIndexIndicator(QLabel):
    """Отрисовывает плавный круговой спиннер при загрузке и 3-полосный эквалайзер при игре без перестроения layout."""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._loading = False
        self._current = False
        self._playing = False
        self._phase = 0

    def set_state(self, *, loading=False, current=False, playing=False, phase=0):
        self._loading = bool(loading)
        self._current = bool(current)
        self._playing = bool(playing)
        self._phase = int(phase)
        self.update()

    def paintEvent(self, event):
        if not self._loading:
            super().paintEvent(event)
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        win = self.window()
        accent = getattr(win, "chameleon_bright", QColor("#1DB954")) if getattr(win, "chameleon_enabled", True) else QColor("#1DB954")

        size = min(self.width(), self.height()) - 6.0
        size = max(12.0, min(15.0, size))
        cx = self.width() / 2.0
        cy = self.height() / 2.0
        rect = QRectF(cx - size / 2.0, cy - size / 2.0, size, size)

        ring_color = QColor(accent)
        ring_color.setAlpha(48)
        ring_pen = QPen(ring_color, 1.8)
        ring_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(ring_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(rect)

        arc_pen = QPen(accent, 2.0)
        arc_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(arc_pen)
        start_angle = int((-(self._phase * 16) % 360) * 16)
        span_angle = 110 * 16
        painter.drawArc(rect, start_angle, span_angle)
        painter.end()


class CompactNowPlayingBadge(QLabel):
    """Центральный стеклянный медальон со спиннером или 4-полосной звуковой волной поверх мини-обложки."""

    def __init__(self, text="♫", parent=None):
        super().__init__(text, parent)
        self._loading = False
        self._current = False
        self._playing = False
        self._phase = 0
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def set_state(self, *, loading=False, current=False, playing=False, phase=0):
        self._loading = bool(loading)
        self._current = bool(current)
        self._playing = bool(playing)
        self._phase = int(phase)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect())
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(8, 12, 18, 142))
        painter.drawRoundedRect(rect, 8.0, 8.0)

        win = self.window()
        accent = getattr(win, "chameleon_bright", QColor("#1ED760")) if getattr(win, "chameleon_enabled", True) else QColor("#1ED760")
        cx = rect.center().x()
        cy = rect.center().y()
        med_r = min(13.0, min(rect.width(), rect.height()) * 0.34)

        # Мягкий неоновый ореол вокруг медальона
        halo = QRadialGradient(cx, cy, med_r * 1.32)
        hc = QColor(accent)
        hc.setAlpha(75)
        halo.setColorAt(0.0, hc)
        hc2 = QColor(accent)
        hc2.setAlpha(0)
        halo.setColorAt(1.0, hc2)
        painter.setBrush(QBrush(halo))
        painter.drawEllipse(QPointF(cx, cy), med_r * 1.32, med_r * 1.32)

        # Тёмный стеклянный кружок с тонким светящимся ободком
        ring_col = QColor(accent)
        ring_col.setAlpha(190)
        painter.setBrush(QColor(11, 16, 23, 224))
        painter.setPen(QPen(ring_col, 1.35))
        painter.drawEllipse(QPointF(cx, cy), med_r, med_r)

        if self._loading:
            size = med_r * 1.12
            arc_rect = QRectF(cx - size / 2.0, cy - size / 2.0, size, size)
            ring_color = QColor(accent)
            ring_color.setAlpha(55)
            painter.setPen(QPen(ring_color, 1.6))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(arc_rect)
            arc_pen = QPen(accent, 1.9)
            arc_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(arc_pen)
            start_angle = int((-(self._phase * 16) % 360) * 16)
            painter.drawArc(arc_rect, start_angle, 115 * 16)
            painter.end()
            return

        painter.setPen(Qt.PenStyle.NoPen)
        bar_w = 2.0
        gap = 1.55
        total_w = 4 * bar_w + 3 * gap
        start_x = cx - total_w / 2.0
        max_h = med_r * 0.92
        min_h = 3.0
        if self._playing:
            t = self._phase * 0.32
            levels = (
                0.40 + 0.50 * (0.5 + 0.5 * math.sin(t + 0.2)),
                0.50 + 0.50 * (0.5 + 0.5 * math.sin(t * 1.28 + 1.7)),
                0.46 + 0.52 * (0.5 + 0.5 * math.sin(t * 1.12 + 3.1)),
                0.38 + 0.48 * (0.5 + 0.5 * math.sin(t * 0.94 + 4.4)),
            )
        else:
            levels = (0.36, 0.72, 0.54, 0.36)
        for idx, level in enumerate(levels):
            clamped = max(0.0, min(1.0, level))
            h = min_h + (max_h - min_h) * clamped
            x = start_x + idx * (bar_w + gap)
            y = cy - h / 2.0
            bgrad = QLinearGradient(x, y, x, y + h)
            top_c = QColor("#FFFFFF") if idx in (1, 2) and self._playing else QColor(accent).lighter(120)
            bgrad.setColorAt(0.0, top_c)
            bgrad.setColorAt(0.5, accent)
            bgrad.setColorAt(1.0, QColor(accent).darker(115))
            painter.setBrush(QBrush(bgrad))
            painter.drawRoundedRect(QRectF(x, y, bar_w, h), bar_w / 2.0, bar_w / 2.0)
        painter.end()


class TrackRow(QWidget):
    """Строка трека в стиле Spotify: номер, обложка, название, источник и действия."""
    play_requested = pyqtSignal(object)
    artist_requested = pyqtSignal(object)

    def __init__(self, track, compact=False, is_favorite=False, index=0, parent=None, show_source=True, removable=True):
        super().__init__(parent)
        self.setObjectName("trackRow")
        self.track = dict(track)
        self._full_title = str(track.get("title") or "Без названия")
        self._full_artist = str(track.get("artist_display") or track.get("artist") or "Исполнитель неизвестен")
        self.compact = compact
        self.removable = removable
        self._is_playing = False
        self._is_current = False
        self._loading = False
        self._original_index = str(index) if index else "•"
        self._eq_phase = 0
        self._eq_timer = QTimer(self)
        self._eq_timer.setInterval(45)
        self._eq_timer.timeout.connect(self._animate_equalizer)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10 if compact else 12)

        if not compact:
            self.index_label = TrackIndexIndicator(self._original_index)
            self.index_label.setObjectName("trackIndex")
            self.index_label.setProperty("playing", False)
            self.index_label.setFixedSize(22, 22)
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
        artist_row = QHBoxLayout()
        artist_row.setContentsMargins(0, 0, 0, 0)
        artist_row.setSpacing(6)
        src_kind = str(self.track.get("source") or "")
        badge_text = "YT" if src_kind == "youtube" else "SC" if src_kind == "soundcloud" else "HQ" if src_kind == "local" else ""
        if self.track.get("local_path"):
            badge_text = f"{badge_text} • ✓" if badge_text else "✓"
        if badge_text:
            self.source_badge = QLabel(badge_text, self)
            self.source_badge.setObjectName("trackSourceBadge")
            self.source_badge.setProperty("sourceKind", src_kind or "local")
            self.source_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.source_badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            artist_row.addWidget(self.source_badge, 0, Qt.AlignmentFlag.AlignVCenter)
        artist_row.addWidget(self.artist_label, 1)
        text_column.addWidget(self.title_label)
        text_column.addLayout(artist_row)
        layout.addLayout(text_column, 1)

        if compact:
            if not removable:
                src = self.track.get("source")
                self.source_label = QLabel(
                    "YouTube" if src == "youtube" else "SoundCloud" if src == "soundcloud" else "Файл",
                    self,
                )
                self.source_label.setObjectName("sourceText")
                self.source_label.setFixedWidth(78)
                self.source_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.source_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                layout.addWidget(self.source_label)

                dur_str = human_time(self.track.get("duration"))
                self.duration_label = QLabel(dur_str, self)
                self.duration_label.setObjectName("durationText")
                self.duration_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.duration_label.setFixedWidth(42 if dur_str else 4)
                self.duration_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                layout.addWidget(self.duration_label)

                self.favorite_button = QPushButton("", self)
                self.favorite_button.setObjectName("rowFavorite")
                self.favorite_button.setIcon(control_icon(
                    "heart" if is_favorite else "heart-outline",
                    "#1DB954" if is_favorite else "#B3B3B3", 22
                ))
                self.favorite_button.setIconSize(QSize(19, 19))
                self.favorite_button.setFixedSize(32, 32)
                self.favorite_button.setCheckable(True)
                self.favorite_button.setChecked(bool(is_favorite))
                self.favorite_button.setCursor(Qt.CursorShape.PointingHandCursor)
                self.favorite_button.setToolTip("Убрать из лайков" if is_favorite else "Добавить в лайки")
                layout.addWidget(self.favorite_button)

                self.menu_button = QPushButton("⋯", self)
                self.menu_button.setObjectName("rowRemove")
                self.menu_button.setFixedSize(28, 28)
                self.menu_button.setCursor(Qt.CursorShape.PointingHandCursor)
                self.menu_button.setToolTip("Действия с треком")
                self.menu_button.setProperty("revealed", False)
                layout.addWidget(self.menu_button)

            # An unparented button becomes a native top-level window on show().
            # Set its owner before visibility changes to avoid a 28x28 flash.
            self.remove_button = QPushButton("×", self)
            self.remove_button.setObjectName("rowRemove")
            self.remove_button.setFixedSize(28, 28)
            self.remove_button.setToolTip("Удалить из очереди")
            self.remove_button.setAccessibleName(f"Удалить {self._full_title} из очереди")
            self.remove_button.setProperty("revealed", False)
            layout.addWidget(self.remove_button)
            self.remove_button.setVisible(removable)
            self.now_playing = CompactNowPlayingBadge("♫", self.thumbnail_label)
            self.now_playing.setObjectName("queuePlayingBadge")
            self.now_playing.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.now_playing.setGeometry(0, 0, side, side)
            self.now_playing.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            self.now_playing.hide()
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
            self.play_button = QPushButton()
            self.play_button.setObjectName("rowPlay")
            self.play_button.setProperty("revealed", False)
            self.play_button.setIcon(control_icon("play", "#A7A7A7", 14))
            self.play_button.setIconSize(QSize(14, 14))
            self.play_button.setFixedSize(32, 32)
            self.play_button.setCursor(Qt.CursorShape.PointingHandCursor)
            self.play_button.setToolTip("Воспроизвести")
            self.favorite_button = QPushButton("")
            self.favorite_button.setObjectName("rowFavorite")
            self.favorite_button.setIcon(control_icon("heart" if is_favorite else "heart-outline",
                                                      "#1DB954" if is_favorite else "#B3B3B3", 24))
            self.favorite_button.setIconSize(QSize(22, 22))
            self.favorite_button.setFixedSize(36, 36)
            self.favorite_button.setCheckable(True)
            self.favorite_button.setChecked(bool(is_favorite))
            self.favorite_button.setCursor(Qt.CursorShape.PointingHandCursor)
            self.favorite_button.setToolTip("Убрать из лайков" if is_favorite else "Добавить в лайки")
            layout.addWidget(self.play_button)
            layout.addWidget(self.favorite_button)

    def _sync_indicator_state(self):
        needs_timer = bool(self._loading or (self._is_current and self._is_playing))
        if self.compact:
            if hasattr(self, "now_playing"):
                self.now_playing.setVisible(bool(self._is_current or self._loading))
                self.now_playing.set_state(
                    loading=self._loading,
                    current=self._is_current,
                    playing=self._is_playing,
                    phase=self._eq_phase,
                )
        elif hasattr(self, "index_label"):
            target_text = "⏳" if self._loading else self._original_index
            if self.index_label.text() != target_text:
                self.index_label.setText(target_text)
            self.index_label.set_state(
                loading=self._loading,
                current=self._is_current,
                playing=self._is_playing,
                phase=self._eq_phase,
            )
            if hasattr(self, "thumbnail_label"):
                self.thumbnail_label.update()
        if needs_timer and self.isVisible():
            if not self._eq_timer.isActive():
                self._eq_timer.start()
        else:
            self._eq_timer.stop()

    def set_playing(self, current, animate=None):
        """Текущая строка остаётся выделенной и на паузе; эквалайзер движется только при Play."""
        current = bool(current)
        if animate is None:
            animate = current
        animate = bool(animate and current)
        current_changed = self._is_current != current
        animation_changed = self._is_playing != animate
        if not current_changed and not animation_changed:
            return
        self._is_current = current
        self._is_playing = animate
        if current_changed:
            self.setProperty("playing", current)
            self.title_label.setProperty("playing", current)
            widgets = [self, self.title_label]
            if not self.compact and hasattr(self, "index_label"):
                self.index_label.setProperty("playing", current)
                widgets.append(self.index_label)
            for widget in widgets:
                widget.style().unpolish(widget)
                widget.style().polish(widget)
                widget.update()
        if (current_changed or animation_changed) and animate and not self._loading:
            self._eq_phase = 0
        self._sync_indicator_state()
        if hasattr(self, "thumbnail_label"):
            self.thumbnail_label.update()
        self.update()

    def set_loading(self, loading: bool):
        """Показывает плавный спиннер, пока выбранный трек подготавливается к запуску."""
        new_loading = bool(loading)
        if self._loading == new_loading:
            return
        self._loading = new_loading
        self._eq_phase = 0
        self._sync_indicator_state()

    def _animate_equalizer(self):
        if not (self._loading or (self._is_current and self._is_playing)):
            self._eq_timer.stop()
            return
        self._eq_phase = (self._eq_phase + 1) % 3600
        if self.compact:
            if hasattr(self, "now_playing"):
                self.now_playing.set_state(
                    loading=self._loading,
                    current=self._is_current,
                    playing=self._is_playing,
                    phase=self._eq_phase,
                )
        elif hasattr(self, "index_label"):
            self.index_label.set_state(
                loading=self._loading,
                current=self._is_current,
                playing=self._is_playing,
                phase=self._eq_phase,
            )
            if hasattr(self, "thumbnail_label"):
                self.thumbnail_label.update()

    def showEvent(self, event):
        super().showEvent(event)
        if (self._loading or (self._is_current and self._is_playing)) and not self._eq_timer.isActive():
            self._eq_timer.start()

    def hideEvent(self, event):
        self._eq_timer.stop()
        super().hideEvent(event)

    def _reveal_queue_action(self, revealed):
        if self.compact and hasattr(self, "thumbnail_label"):
            self.thumbnail_label.set_hover_overlay(revealed)
        if hasattr(self, "play_button"):
            self.play_button.setProperty("revealed", revealed)
            self.play_button.style().unpolish(self.play_button)
            self.play_button.style().polish(self.play_button)
        if self.compact and self.removable:
            self.remove_button.setProperty("revealed", revealed)
            self.remove_button.style().unpolish(self.remove_button)
            self.remove_button.style().polish(self.remove_button)
        if self.compact and hasattr(self, "menu_button"):
            self.menu_button.setProperty("revealed", revealed)
            self.menu_button.style().unpolish(self.menu_button)
            self.menu_button.style().polish(self.menu_button)

    def enterEvent(self, event):
        self._reveal_queue_action(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._reveal_queue_action(False)
        super().leaveEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._is_current:
            win = self.window()
            if getattr(win, "chameleon_enabled", True) and hasattr(win, "chameleon_accent"):
                painter = QPainter(self)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                rect = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
                fill = QColor(win.chameleon_accent)
                fill.setAlpha(42 if self.underMouse() else 28)
                border = QColor(win.chameleon_bright)
                border.setAlpha(115 if self.underMouse() else 76)
                painter.setBrush(fill)
                painter.setPen(QPen(border, 1.1))
                painter.drawRoundedRect(rect, 9.0, 9.0)
                painter.end()

    def _is_action_widget(self, child):
        if child is None:
            return False
        action_buttons = tuple(
            button for button in (
                getattr(self, "play_button", None),
                getattr(self, "favorite_button", None),
                getattr(self, "menu_button", None),
                getattr(self, "remove_button", None),
                getattr(self, "artist_label", None),
            ) if button is not None
        )
        return child in action_buttons

    def _maybe_begin_drag(self, pos):
        start_pos = getattr(self, "_drag_start_pos", None)
        if start_pos is None or getattr(self, "_drag_in_progress", False):
            return False
        if (pos - start_pos).manhattanLength() < QApplication.startDragDistance():
            return False
        self._drag_in_progress = True
        self._drag_start_pos = None
        drag = QDrag(self)
        mime = QMimeData()
        payload = {
            "track": dict(self.track),
            "source_kind": str(getattr(self, "drag_source_kind", "") or ""),
            "source_index": int(getattr(self, "drag_source_index", -1)),
            "queue_id": str(self.track.get("queue_id") or ""),
        }
        mime.setData(AURORA_TRACK_MIME, json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        mime.setText(f"{self._full_artist} — {self._full_title}")
        drag.setMimeData(mime)

        badge_w, badge_h = 248, 48
        pm = QPixmap(badge_w, badge_h)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setBrush(QColor(20, 27, 36, 240))
        p.setPen(QPen(QColor("#1DB954"), 1.5))
        p.drawRoundedRect(QRectF(1, 1, badge_w - 2, badge_h - 2), 11, 11)
        cover_pm = self.thumbnail_label.pixmap() if hasattr(self, "thumbnail_label") else None
        if cover_pm is not None and not cover_pm.isNull():
            p.drawPixmap(QRect(8, 6, 36, 36), cover_pm)
        title_font = QFont(self.font())
        title_font.setPixelSize(12)
        title_font.setWeight(QFont.Weight.Bold)
        p.setFont(title_font)
        p.setPen(QColor("#F2F6FA"))
        p.drawText(
            QRect(52, 6, badge_w - 60, 18),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            QFontMetrics(title_font).elidedText(self._full_title, Qt.TextElideMode.ElideRight, badge_w - 60),
        )
        sub_font = QFont(self.font())
        sub_font.setPixelSize(11)
        p.setFont(sub_font)
        p.setPen(QColor("#8F9BAE"))
        p.drawText(
            QRect(52, 24, badge_w - 60, 16),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            QFontMetrics(sub_font).elidedText(self._full_artist, Qt.TextElideMode.ElideRight, badge_w - 60),
        )
        p.end()
        drag.setPixmap(pm)
        drag.setHotSpot(QPoint(24, 24))
        drag.exec(Qt.DropAction.CopyAction | Qt.DropAction.MoveAction)
        return True

    def mousePressEvent(self, event):
        # Кнопки действий должны обрабатывать нажатие самостоятельно:
        # иначе клик по Play/лайку/удалению/автору может запустить строку повторно.
        if event.button() == Qt.MouseButton.LeftButton:
            child = self.childAt(event.position().toPoint())
            if self._is_action_widget(child):
                self._drag_start_pos = None
                super().mousePressEvent(event)
                return
            self._drag_start_pos = event.position().toPoint()
            self._drag_in_progress = False
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (event.buttons() & Qt.MouseButton.LeftButton) and getattr(self, "_drag_start_pos", None) is not None:
            if self._maybe_begin_drag(event.position().toPoint()):
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            was_dragging = getattr(self, "_drag_in_progress", False)
            had_press = getattr(self, "_drag_start_pos", None) is not None
            self._drag_start_pos = None
            self._drag_in_progress = False
            if not was_dragging and had_press and self.rect().contains(event.position().toPoint()):
                self.play_requested.emit(dict(self.track))
                event.accept()
                return
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        for label, full in ((self.title_label, self._full_title),
                            (self.artist_label, self._full_artist)):
            width = max(0, label.contentsRect().width() - 3)
            shortened = label.fontMetrics().elidedText(full, Qt.TextElideMode.ElideRight, width)
            if label.text() != shortened:
                label.setText(shortened)


class DroppableTrackListWidget(QListWidget):
    """Список треков с поддержкой перетаскивания (Drag & Drop) для сортировки и добавления."""
    track_dropped_at = pyqtSignal(int, object, str, int)
    files_dropped = pyqtSignal(object)

    def __init__(self, list_kind="playlist", parent=None):
        super().__init__(parent)
        self.list_kind = str(list_kind or "playlist")
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self._drop_row = -1
        self._drop_indicator_y = -1

    def _compute_drop_target(self, pos):
        count = self.count()
        if count <= 0:
            return 0, 6
        item = self.itemAt(pos)
        if item is None:
            last_rect = self.visualItemRect(self.item(count - 1))
            if pos.y() < 12:
                return 0, 4
            return count, min(self.viewport().height() - 4, last_rect.bottom() + 1)
        row = self.row(item)
        rect = self.visualItemRect(item)
        if pos.y() > rect.center().y():
            return row + 1, rect.bottom() + 1
        return row, max(2, rect.top() - 1)

    def _can_accept_mime(self, md):
        if md is None:
            return False
        if md.hasFormat(AURORA_TRACK_MIME):
            return True
        if md.hasUrls():
            for url in md.urls():
                if url.isLocalFile():
                    suffix = Path(url.toLocalFile()).suffix.lower()
                    if suffix in (".json", ".m3u", ".m3u8", ".mp3", ".flac", ".m4a", ".wav", ".ogg", ".opus"):
                        return True
        return False

    def dragEnterEvent(self, event):
        if self._can_accept_mime(event.mimeData()):
            self._drop_row, self._drop_indicator_y = self._compute_drop_target(event.position().toPoint())
            self.viewport().update()
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if self._can_accept_mime(event.mimeData()):
            self._drop_row, self._drop_indicator_y = self._compute_drop_target(event.position().toPoint())
            self.viewport().update()
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dragLeaveEvent(self, event):
        self._drop_row = -1
        self._drop_indicator_y = -1
        self.viewport().update()
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        target_row, _ = self._compute_drop_target(event.position().toPoint())
        self._drop_row = -1
        self._drop_indicator_y = -1
        self.viewport().update()
        md = event.mimeData()
        if md is None:
            return
        if md.hasFormat(AURORA_TRACK_MIME):
            try:
                payload = json.loads(bytes(md.data(AURORA_TRACK_MIME)).decode("utf-8"))
                if isinstance(payload, dict):
                    track = payload.get("track") if "track" in payload else payload
                    source_kind = str(payload.get("source_kind") or "")
                    source_index = int(payload.get("source_index", -1))
                    if isinstance(track, dict) and track.get("url"):
                        self.track_dropped_at.emit(target_row, track, source_kind, source_index)
                        event.acceptProposedAction()
                        return
            except (ValueError, TypeError):
                pass
        if md.hasUrls():
            paths = [url.toLocalFile() for url in md.urls() if url.isLocalFile()]
            if paths:
                self.files_dropped.emit(paths)
                event.acceptProposedAction()
                return
        super().dropEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._drop_indicator_y >= 0:
            painter = QPainter(self.viewport())
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            y = int(self._drop_indicator_y)
            w = self.viewport().width()
            painter.setPen(QPen(QColor("#1ED760"), 2.4))
            painter.drawLine(14, y, max(20, w - 14), y)
            painter.setBrush(QColor("#1ED760"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(14, y), 4.0, 4.0)
            painter.drawEllipse(QPointF(max(20, w - 14), y), 4.0, 4.0)
            painter.end()


def make_placeholder(side=240):
    pixmap = QPixmap(side, side)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    radius = max(8.0, side * 0.08)

    # Благородный тёмно-графитовый фон в стиле Spotify вместо кислотно-зелёного квадрата
    bg = QLinearGradient(0, 0, side, side)
    bg.setColorAt(0.0, QColor("#222834"))
    bg.setColorAt(0.55, QColor("#161B24"))
    bg.setColorAt(1.0, QColor("#0E1218"))
    p.setBrush(QBrush(bg))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(QRectF(0, 0, side, side), radius, radius)

    # Мягкое радиальное свечение в центре
    glow = QRadialGradient(side * 0.5, side * 0.48, side * 0.46)
    glow.setColorAt(0.0, QColor(29, 185, 84, 34))
    glow.setColorAt(0.65, QColor(29, 185, 84, 10))
    glow.setColorAt(1.0, QColor(0, 0, 0, 0))
    p.setBrush(QBrush(glow))
    p.drawRoundedRect(QRectF(0, 0, side, side), radius, radius)

    # Силуэт виниловой пластинки с тонкими дорожками
    disc_r = side * 0.72
    disc_rect = QRectF((side - disc_r) * 0.5, (side - disc_r) * 0.5, disc_r, disc_r)
    disc_grad = QLinearGradient(disc_rect.topLeft(), disc_rect.bottomRight())
    disc_grad.setColorAt(0.0, QColor(255, 255, 255, 18))
    disc_grad.setColorAt(0.5, QColor(255, 255, 255, 7))
    disc_grad.setColorAt(1.0, QColor(255, 255, 255, 16))
    p.setBrush(QBrush(disc_grad))
    p.setPen(QPen(QColor(255, 255, 255, 26), max(1.0, side / 120.0)))
    p.drawEllipse(disc_rect)

    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor(255, 255, 255, 16), max(1.0, side / 160.0)))
    for ratio in (0.56, 0.42):
        r = side * ratio
        p.drawEllipse(QRectF((side - r) * 0.5, (side - r) * 0.5, r, r))

    # Тонкая внутренняя рамка обложки
    p.setPen(QPen(QColor(255, 255, 255, 22), 1.0))
    p.drawRoundedRect(QRectF(0.5, 0.5, side - 1.0, side - 1.0), radius, radius)

    # Аккуратная парная нота в центре
    inset = side * 0.31
    draw_vector_icon(p, "music", QRectF(inset, inset, side - 2 * inset, side - 2 * inset), "#B8C4D6")
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
    elif name == "search":
        p.drawEllipse(QPointF(14, 14), 8, 8)
        p.drawLine(20, 20, 27, 27)
    elif name == "settings":
        for angle in range(0, 360, 45):
            p.save()
            p.translate(16, 16)
            p.rotate(angle)
            p.drawLine(0, -10, 0, -13)
            p.restore()
        p.drawEllipse(QPointF(16, 16), 9, 9)
        p.drawEllipse(QPointF(16, 16), 3, 3)
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
    elif name == "mini":
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(5, 7, 22, 18, 3, 3)
        p.setBrush(QColor(color))
        p.drawRoundedRect(15, 14, 9, 8, 1.8, 1.8)
    elif name == "download":
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(16, 5.5), QPointF(16, 19.5))
        p.drawLine(QPointF(10.5, 14.2), QPointF(16, 19.8))
        p.drawLine(QPointF(21.5, 14.2), QPointF(16, 19.8))
        tray = QPainterPath()
        tray.moveTo(6.5, 20.5)
        tray.lineTo(6.5, 24.5)
        tray.quadTo(6.5, 26.0, 8.0, 26.0)
        tray.lineTo(24.0, 26.0)
        tray.quadTo(25.5, 26.0, 25.5, 24.5)
        tray.lineTo(25.5, 20.5)
        p.drawPath(tray)
    elif name == "downloaded":
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(16, 16), 10.5, 10.5)
        p.drawLine(QPointF(11.2, 16.3), QPointF(14.6, 19.7))
        p.drawLine(QPointF(14.6, 19.7), QPointF(21.2, 12.6))
    elif name == "queue-add":
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(6, 9.5), QPointF(21, 9.5))
        p.drawLine(QPointF(6, 15.5), QPointF(19, 15.5))
        p.drawLine(QPointF(6, 21.5), QPointF(14, 21.5))
        p.drawLine(QPointF(18.5, 21.5), QPointF(26.5, 21.5))
        p.drawLine(QPointF(22.5, 17.5), QPointF(22.5, 25.5))
    elif name == "radio":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(color))
        p.drawEllipse(QPointF(16, 16), 2.5, 2.5)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRectF(9.5, 9.5, 13.0, 13.0), -42 * 16, 84 * 16)
        p.drawArc(QRectF(9.5, 9.5, 13.0, 13.0), 138 * 16, 84 * 16)
        p.drawArc(QRectF(4.8, 4.8, 22.4, 22.4), -46 * 16, 92 * 16)
        p.drawArc(QRectF(4.8, 4.8, 22.4, 22.4), 134 * 16, 92 * 16)
    elif name == "artist":
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(16, 11), 4.6, 4.6)
        shoulders = QPainterPath()
        shoulders.moveTo(7.2, 25.2)
        shoulders.cubicTo(7.8, 19.2, 24.2, 19.2, 24.8, 25.2)
        p.drawPath(shoulders)
    elif name == "external":
        p.setBrush(Qt.BrushStyle.NoBrush)
        box = QPainterPath()
        box.moveTo(14.5, 8.0)
        box.lineTo(9.0, 8.0)
        box.quadTo(7.0, 8.0, 7.0, 10.0)
        box.lineTo(7.0, 23.0)
        box.quadTo(7.0, 25.0, 9.0, 25.0)
        box.lineTo(22.0, 25.0)
        box.quadTo(24.0, 25.0, 24.0, 23.0)
        box.lineTo(24.0, 17.5)
        p.drawPath(box)
        p.drawLine(QPointF(14.5, 17.5), QPointF(25.0, 7.0))
        p.drawLine(QPointF(18.5, 7.0), QPointF(25.0, 7.0))
        p.drawLine(QPointF(25.0, 7.0), QPointF(25.0, 13.5))
    elif name == "folder":
        p.setBrush(Qt.BrushStyle.NoBrush)
        folder_path = QPainterPath()
        folder_path.moveTo(5.5, 9.5)
        folder_path.lineTo(12.2, 9.5)
        folder_path.lineTo(14.8, 12.2)
        folder_path.lineTo(26.5, 12.2)
        folder_path.lineTo(26.5, 24.2)
        folder_path.lineTo(5.5, 24.2)
        folder_path.closeSubpath()
        p.drawPath(folder_path)
    elif name == "arrow-up":
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(16, 25), QPointF(16, 7))
        p.drawLine(QPointF(10, 13), QPointF(16, 7))
        p.drawLine(QPointF(22, 13), QPointF(16, 7))
    elif name == "arrow-down":
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(16, 7), QPointF(16, 25))
        p.drawLine(QPointF(10, 19), QPointF(16, 25))
        p.drawLine(QPointF(22, 19), QPointF(16, 25))
    elif name == "remove":
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(9.5, 9.5), QPointF(22.5, 22.5))
        p.drawLine(QPointF(22.5, 9.5), QPointF(9.5, 22.5))
    elif name in ("playlist-add", "plus"):
        p.setBrush(Qt.BrushStyle.NoBrush)
        if name == "playlist-add":
            p.drawLine(QPointF(6.0, 9.0), QPointF(19.0, 9.0))
            p.drawLine(QPointF(6.0, 15.0), QPointF(15.0, 15.0))
            p.drawLine(QPointF(6.0, 21.0), QPointF(13.0, 21.0))
            p.drawLine(QPointF(18.0, 18.0), QPointF(26.0, 18.0))
            p.drawLine(QPointF(22.0, 14.0), QPointF(22.0, 22.0))
        else:
            p.drawLine(QPointF(8.0, 16.0), QPointF(24.0, 16.0))
            p.drawLine(QPointF(16.0, 8.0), QPointF(16.0, 24.0))
    elif name == "export":
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(16, 19.5), QPointF(16, 5.5))
        p.drawLine(QPointF(10.5, 11.2), QPointF(16, 5.5))
        p.drawLine(QPointF(21.5, 11.2), QPointF(16, 5.5))
        tray = QPainterPath()
        tray.moveTo(6.5, 20.5)
        tray.lineTo(6.5, 24.5)
        tray.quadTo(6.5, 26.0, 8.0, 26.0)
        tray.lineTo(24.0, 26.0)
        tray.quadTo(25.5, 26.0, 25.5, 24.5)
        tray.lineTo(25.5, 20.5)
        p.drawPath(tray)
    elif name == "import":
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(16, 5.5), QPointF(16, 19.5))
        p.drawLine(QPointF(10.5, 14.2), QPointF(16, 19.8))
        p.drawLine(QPointF(21.5, 14.2), QPointF(16, 19.8))
        tray = QPainterPath()
        tray.moveTo(6.5, 20.5)
        tray.lineTo(6.5, 24.5)
        tray.quadTo(6.5, 26.0, 8.0, 26.0)
        tray.lineTo(24.0, 26.0)
        tray.quadTo(25.5, 26.0, 25.5, 24.5)
        tray.lineTo(25.5, 20.5)
        p.drawPath(tray)
    elif name == "edit":
        p.setBrush(Qt.BrushStyle.NoBrush)
        pen_path = QPainterPath()
        pen_path.moveTo(7.5, 24.5)
        pen_path.lineTo(12.2, 23.4)
        pen_path.lineTo(23.8, 11.8)
        pen_path.lineTo(20.2, 8.2)
        pen_path.lineTo(8.6, 19.8)
        pen_path.closeSubpath()
        p.drawPath(pen_path)
    p.end()
    return QIcon(pix)


def menu_action_icon(name, theme="dark", accent=False):
    """Создаёт чёткую векторную иконку для пунктов QMenu с подсветкой при наведении."""
    light = theme == "light"
    normal_color = ("#187941" if accent else "#334152") if light else ("#5CE092" if accent else "#D6E0EE")
    active_color = "#167A40" if light else "#66E099"
    disabled_color = "#9AA6B8" if light else "#556274"
    icon = QIcon()
    for mode, color in (
        (QIcon.Mode.Normal, normal_color),
        (QIcon.Mode.Active, active_color),
        (QIcon.Mode.Selected, active_color),
        (QIcon.Mode.Disabled, disabled_color),
    ):
        pm = control_icon(name, color, 36).pixmap(36, 36)
        pm.setDevicePixelRatio(2.0)
        icon.addPixmap(pm, mode)
    return icon




# -------------------------------------------------------------
# Кликабельная шкала.
# Обычный QSlider в Windows может двигать значение лишь на шаг
# при клике на дорожку. Эта версия сразу переходит в точку клика.
# При этом перетаскивание за круглую ручку остаётся обычным.
# -------------------------------------------------------------

class ClickSlider(QSlider):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setMouseTracking(True)
        self._hover_x = None

    def leaveEvent(self, event):
        self._hover_x = None
        self.update()
        super().leaveEvent(event)

    def mouseMoveEvent(self, event):
        self._hover_x = event.position().x()
        if self.objectName() == "seekSlider" and self.maximum() > self.minimum():
            rail_left = 6.0
            rail_w = max(1.0, self.width() - 12.0)
            ratio = max(0.0, min(1.0, (self._hover_x - rail_left) / rail_w))
            hover_ms = int(self.minimum() + ratio * (self.maximum() - self.minimum()))
            hover_str = human_time(hover_ms / 1000.0) or "0:00"
            total_str = human_time(self.maximum() / 1000.0) or "0:00"
            self.setToolTip(f"Перемотать на {hover_str} / {total_str}")
        self.update()
        super().mouseMoveEvent(event)

    def wheelEvent(self, event):
        if self.maximum() == 100 and self.minimum() == 0 and self.objectName() != "seekSlider":
            delta = event.angleDelta().y()
            if delta != 0:
                step = 1 if self.value() < 20 else 2
                self.setValue(max(0, min(100, self.value() + (step if delta > 0 else -step))))
                event.accept()
                return
        super().wheelEvent(event)

    def paintEvent(self, event):
        if self.orientation() != Qt.Orientation.Horizontal:
            return super().paintEvent(event)
        option = QStyleOptionSlider()
        self.initStyleOption(option)
        win = self.window()
        light = getattr(win, "theme", "dark") == "light"
        hovered = self.underMouse() or self.isSliderDown()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rail_h = 5.0 if hovered else 4.0
        rail = QRectF(6, self.height() / 2 - rail_h / 2.0, max(1, self.width() - 12), rail_h)
        has_range = self.maximum() > self.minimum()
        position = (
            QStyle.sliderPositionFromValue(
                self.minimum(), self.maximum(), self.value(), int(rail.width()), option.upsideDown
            )
            if has_range else 0
        )
        chameleon_on = getattr(win, "chameleon_enabled", True)
        base_accent = getattr(win, "chameleon_bright", QColor("#1ED760")) if chameleon_on else QColor("#1ED760" if hovered and not light else ("#21834C" if light else "#1DB954"))
        color = QColor(base_accent)
        if not self.isEnabled():
            color.setAlpha(185)

        is_seek = self.objectName() == "seekSlider"
        viz_on = getattr(win, "visualizer_enabled", True)
        if is_seek and viz_on and rail.width() >= 90:
            # Красивая звуковая волна (SoundCloud / Yandex Music style) с уникальным профилем трека
            seed = int(getattr(self, "_wave_seed", 42) or 42)
            bar_step = 5.2
            num_bars = max(16, int(rail.width() // bar_step))
            bar_w = 2.5
            cy = self.height() / 2.0
            max_amp = max(4.5, min(7.2, self.height() * 0.45)) if hovered else max(3.6, min(5.8, self.height() * 0.36))
            unplayed_col = QColor("#B9C5D4" if light else "#384354")
            if not light:
                unplayed_col.setAlpha(155)
            hover_x = self._hover_x if (hovered and self._hover_x is not None) else -1.0
            painter.setPen(Qt.PenStyle.NoPen)
            for idx in range(num_bars):
                bx = rail.left() + idx * (rail.width() / max(1, num_bars))
                norm = idx / max(1.0, float(num_bars - 1))
                envelope = math.sin(norm * math.pi) ** 0.35
                wave = (
                    0.46
                    + 0.28 * abs(math.sin(idx * 0.63 + seed * 0.17))
                    + 0.26 * abs(math.cos(idx * 1.19 + seed * 0.41))
                )
                amp = max(1.8, max_amp * min(1.0, wave * (0.45 + 0.55 * envelope)))
                played = (bx - rail.left()) <= position and (self.isEnabled() or (has_range and self.value() > self.minimum()))
                if played:
                    painter.setBrush(color)
                elif hover_x >= bx and self.isEnabled():
                    preview_col = QColor(color)
                    preview_col.setAlpha(95)
                    painter.setBrush(preview_col)
                else:
                    painter.setBrush(unplayed_col)
                painter.drawRoundedRect(QRectF(bx, cy - amp, bar_w, amp * 2.0), 1.2, 1.2)
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#CFD8E3" if light else "#323B48"))
            painter.drawRoundedRect(rail, rail_h / 2.0, rail_h / 2.0)
            if self.isEnabled() or (has_range and self.value() > self.minimum()):
                painter.setBrush(color)
                progress = QRectF(rail)
                if option.upsideDown:
                    progress.setLeft(rail.left() + position)
                else:
                    progress.setWidth(max(0.0, float(position)))
                painter.drawRoundedRect(progress, rail_h / 2.0, rail_h / 2.0)

        if self.isEnabled() or (has_range and self.value() > self.minimum()):
            thumb_center = QPointF(rail.left() + position, rail.center().y())
            if self.isEnabled():
                for glow_r, glow_a in ((10.0, 34), (7.2, 74)) if hovered else ((7.0, 38),):
                    halo = QColor(color)
                    halo.setAlpha(glow_a)
                    painter.setBrush(halo)
                    painter.drawEllipse(thumb_center, glow_r, glow_r)
            thumb_r = 5.6 if hovered else 4.6
            painter.setBrush(color if light else QColor("#F5F8FC"))
            painter.drawEllipse(thumb_center, thumb_r, thumb_r)
        painter.end()

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
                background: #1A2029; color: #F4F7FA;
                border: 1px solid #2F3947; border-radius: 10px; padding: 6px;
            }
            QMenu::item {
                padding: 10px 22px 10px 13px; border: none;
                margin: 2px 1px; border-radius: 8px;
                background: transparent;
            }
            QMenu::item:selected { background: #23382D; color: #66E099; }
            QMenu::separator { height: 0px; }
        """)
        palette = self.menu_popup.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor('#1A2029'))
        palette.setColor(QPalette.ColorRole.Base, QColor('#1A2029'))
        palette.setColor(QPalette.ColorRole.Text, QColor('#F4F7FA'))
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
    """Настройки плеера с сохранением выбранных параметров."""

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
        general_layout.setSpacing(12)
        self._add_group_label(general_layout, "ПОИСК")

        self.result_count = MenuChoice(
            [("25 треков", 25), ("50 треков", 50), ("100 треков", 100)],
            player.result_limit, width=214, suffix=" треков"
        )
        general_layout.addLayout(self._form_row("Количество результатов", self.result_count))
        general_layout.addSpacing(4)
        self._add_group_label(general_layout, "ВНЕШНИЙ ВИД")
        self.theme_choice = MenuChoice(
            [("Тёмная тема", "dark"), ("Светлая тема", "light")],
            player.theme, width=214
        )
        general_layout.addLayout(self._form_row("Тема оформления", self.theme_choice))
        general_layout.addSpacing(4)
        self._add_group_label(general_layout, "СКАЧИВАНИЕ ТРЕКОВ")
        self.download_dir_draft = str(getattr(player, "download_dir", "") or "").strip()
        self.download_dir_field = QLineEdit()
        self.download_dir_field.setObjectName("settingsPathField")
        self.download_dir_field.setReadOnly(True)
        self.download_dir_field.setMinimumWidth(280)
        self.download_dir_choose = QPushButton("Выбрать папку…")
        self.download_dir_choose.setObjectName("settingsPicker")
        self.download_dir_choose.clicked.connect(self.choose_download_dir)
        self.download_dir_open = QPushButton("Открыть папку")
        self.download_dir_open.setObjectName("settingsPicker")
        self.download_dir_open.clicked.connect(self.open_download_dir_from_settings)
        self.download_dir_reset = QPushButton("По умолчанию")
        self.download_dir_reset.setObjectName("settingsPicker")
        self.download_dir_reset.clicked.connect(self.reset_download_dir)
        general_layout.addLayout(self._form_row("Папка загрузки", self.download_dir_field))
        dl_btn_row = QHBoxLayout()
        dl_btn_row.setSpacing(8)
        dl_btn_row.addStretch(1)
        dl_btn_row.addWidget(self.download_dir_choose, 0)
        dl_btn_row.addWidget(self.download_dir_open, 0)
        dl_btn_row.addWidget(self.download_dir_reset, 0)
        general_layout.addLayout(dl_btn_row)
        self.update_download_dir_ui()
        general_layout.addSpacing(4)
        self._add_group_label(general_layout, "ПАНЕЛИ")
        self.minimize_to_tray = QCheckBox("При закрытии окна сворачивать плеер в системный трей")
        self.minimize_to_tray.setChecked(player.minimize_to_tray)
        self.hide_on_minimize = QCheckBox("Скрывать окно в трей при нажатии кнопки сворачивания")
        self.hide_on_minimize.setChecked(player.hide_on_minimize)
        general_layout.addWidget(self.minimize_to_tray)
        general_layout.addWidget(self.hide_on_minimize)
        # Очередь больше не занимает правую колонку постоянно.
        self._add_hint(general_layout, "Очередь открывается по кнопке ≡ внизу плеера. Для выхода используй меню значка в трее.")
        general_layout.addSpacing(4)
        self._add_group_label(general_layout, "ОБНОВЛЕНИЕ ПРИЛОЖЕНИЯ (GITHUB)")
        upd_info = getattr(player, "_available_update_info", None) or {}
        has_upd = bool(upd_info.get("is_newer"))
        latest_ver = str(upd_info.get("latest_version") or APP_VERSION)
        status_txt = (
            f"⚠ Доступна новая версия v{latest_ver} (текущая: v{APP_VERSION})!"
            if has_upd
            else f"Текущая версия: v{APP_VERSION} · проверка релизов GitHub"
        )
        self.update_status_label = QLabel(status_txt, general)
        self.update_status_label.setObjectName("settingsHint")
        self.update_status_label.setWordWrap(True)
        general_layout.addWidget(self.update_status_label)
        upd_btn_row = QHBoxLayout()
        upd_btn_row.setSpacing(8)
        self.check_update_btn = QPushButton("Проверить обновления", general)
        self.check_update_btn.setObjectName("settingsPicker")
        self.install_update_btn = QPushButton(
            f"⬇ Обновить до v{latest_ver}" if has_upd else "⬇ Обновить с GitHub",
            general,
        )
        self.install_update_btn.setObjectName("settingsPicker")
        self.github_releases_btn = QPushButton("Открыть GitHub Releases ↗", general)
        self.github_releases_btn.setObjectName("settingsPicker")
        self.check_update_btn.clicked.connect(
            lambda: self._defer_service_action(lambda: player.check_for_updates(manual=True))
        )
        self.install_update_btn.clicked.connect(
            lambda: self._defer_service_action(player.on_update_button_clicked)
        )
        self.github_releases_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(f"https://github.com/{GITHUB_REPO}/releases"))
        )
        upd_btn_row.addWidget(self.check_update_btn, 0)
        upd_btn_row.addWidget(self.install_update_btn, 0)
        upd_btn_row.addWidget(self.github_releases_btn, 0)
        upd_btn_row.addStretch(1)
        general_layout.addLayout(upd_btn_row)
        general_layout.addStretch(1)
        self._add_hint(
            general_layout,
            "Шрифт Inter включён в плеер. Устанавливать его в Windows не нужно."
        )
        tabs.addTab(general, "Общие")

        # Wallpaper changes are drafts until Save; Cancel leaves the player untouched.
        self.wallpaper_dirty = False
        self.wallpaper_draft = QImage()
        self.wallpaper_preview_source = player.backdrop.image
        background = QWidget()
        background.setObjectName("settingsBackground")
        background_layout = QVBoxLayout(background)
        background_layout.setContentsMargins(16, 18, 16, 18)
        background_layout.setSpacing(14)
        self.wallpaper_preview = QLabel()
        self.wallpaper_preview.setObjectName("wallpaperPreview")
        self.wallpaper_preview.setFixedSize(360, 170)
        self.wallpaper_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        background_layout.addWidget(self.wallpaper_preview, 0, Qt.AlignmentFlag.AlignHCenter)
        image_buttons = QHBoxLayout()
        self.wallpaper_choose = QPushButton("Выбрать картинку")
        self.wallpaper_choose.setObjectName("settingsPicker")
        self.wallpaper_choose.clicked.connect(self.choose_wallpaper)
        self.wallpaper_remove = QPushButton("Убрать фон")
        self.wallpaper_remove.setObjectName("settingsPicker")
        self.wallpaper_remove.clicked.connect(self.remove_wallpaper)
        image_buttons.addWidget(self.wallpaper_choose)
        image_buttons.addWidget(self.wallpaper_remove)
        background_layout.addLayout(image_buttons)
        self.wallpaper_dim_label = QLabel()
        self.wallpaper_dim_label.setObjectName("settingsField")
        background_layout.addWidget(self.wallpaper_dim_label)
        self.wallpaper_dim_slider = QSlider(Qt.Orientation.Horizontal)
        self.wallpaper_dim_slider.setRange(0, 90)
        self.wallpaper_dim_slider.setValue(player.wallpaper_dim)
        self.wallpaper_dim_slider.setTracking(False)
        self.wallpaper_dim_slider.valueChanged.connect(self.update_wallpaper_preview)
        background_layout.addWidget(self.wallpaper_dim_slider)
        self.wallpaper_message = QLabel("Картинка сохранится в плеере. Оригинал останется на месте.")
        self.wallpaper_message.setObjectName("settingsHint")
        self.wallpaper_message.setWordWrap(True)
        background_layout.addWidget(self.wallpaper_message)
        background_layout.addStretch(1)
        self.update_wallpaper_preview()
        tabs.addTab(background, "Фон")

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
            /* Делаем фон диалога сплошным в единой палитре Aurora. */
            QDialog#settingsDialog {
                background-color: #0E1217;
                color: #F2F5F9;
            }
            QWidget { color: #F2F5F9; }
            QLabel, QTabWidget#settingsTabs { background: transparent; }
            QWidget#settingsGeneral,
            QWidget#settingsPlayback,
            QWidget#settingsServices,
            QWidget#settingsBackground {
                background-color: #151A22;
            }
            QLabel#wallpaperPreview {
                background: #1C222D; border: 1px solid #2A3342;
                border-radius: 12px; color: #9DA9BA;
            }
            QLabel#settingsTitle { font-size: 24px; font-weight: 800; color: #FFFFFF; }
            QLabel#settingsHint { color: #9AA6B8; font-size: 10pt; }
            QLabel#settingsGroup { color: #5CE092; font-size: 9.5pt; font-weight: 800; letter-spacing: 0.8px; }
            QLabel#settingsField { font-size: 10pt; color: #DDE4EE; font-weight: 500; }
            QLineEdit#settingsPathField {
                background: #1C232E; border: 1px solid #2E3846; border-radius: 10px;
                color: #DCE5F2; padding: 8px 12px; font-size: 9.5pt;
            }
            QTabWidget::pane {
                border: 1px solid #252E3B;
                background: #151A22; border-radius: 14px;
            }
            QTabBar { background: transparent; }
            QTabBar::tab {
                background: transparent; color: #9AA6B8;
                border: none; padding: 10px 18px; margin-right: 6px;
                border-radius: 9px; font-weight: 600;
            }
            QTabBar::tab:hover { color: #FFFFFF; background: #1B222C; }
            QTabBar::tab:selected {
                background: #1E352A; color: #66E099;
                border-radius: 9px; font-weight: 700;
            }
            QPushButton#settingsPicker {
                text-align: left; background: #1C232E;
                border: 1px solid #2E3846; border-radius: 10px;
                color: #F4F7FA; padding: 9px 13px; font-weight: 650;
            }
            QPushButton#settingsPicker:hover {
                background: #232C3A; border-color: #5CE092;
            }
            QPushButton#settingsPicker::menu-indicator { image: none; width: 0; }
            QCheckBox { spacing: 10px; color: #E3E9F2; }
            QCheckBox::indicator {
                width: 18px; height: 18px;
                background: #1C232E; border: 1px solid #455163;
                border-radius: 5px;
            }
            QCheckBox::indicator:checked {
                background: #1DB954; border: 1px solid #1DB954;
            }
            QSlider::groove:horizontal {
                height: 5px; background: #323B48; border-radius: 2.5px;
            }
            QSlider::sub-page:horizontal { background: #5CE092; border-radius: 2.5px; }
            QSlider::handle:horizontal {
                background: #F5F8FC; width: 14px;
                margin: -5px 0; border-radius: 7px;
            }
            QPushButton#settingsCancel, QPushButton#settingsSave {
                border: 1px solid #2E3846; border-radius: 10px;
                padding: 11px 22px; font-weight: 700;
                background: #1C232E; color: #F2F5F9;
            }
            QPushButton#settingsSave { background: #1DB954; color: #0C1911; border: none; }
            QPushButton#settingsCancel:hover { background: #252E3C; border-color: #465366; }
            QPushButton#settingsSave:hover { background: #36DC72; }
        """)
        if player.theme == "light":
            self.setStyleSheet(self.styleSheet() + """
                QDialog#settingsDialog { background: #F2F5F9; color: #18202A; }
                QWidget { color: #18202A; }
                QWidget#settingsGeneral, QWidget#settingsPlayback, QWidget#settingsServices,
                QWidget#settingsBackground, QTabWidget#settingsTabs::pane {
                    background: #FFFFFF; border-color: #D8E0EA;
                }
                QLabel#wallpaperPreview { background: #EAF0F6; border-color: #D5DEE8; color: #58667A; }
                QLabel#settingsTitle { color: #141C26; }
                QLabel#settingsHint { color: #5E6B7E; }
                QLabel#settingsGroup { color: #187941; }
                QLabel#settingsField { color: #263242; }
                QLineEdit#settingsPathField {
                    background: #F4F7FA; border-color: #D4DCE7; color: #18202A;
                }
                QTabWidget::pane { border-color: #D8E0EA; background: #FFFFFF; }
                QTabBar::tab { color: #5E6B7E; }
                QTabBar::tab:hover { background: #E9EFF6; color: #141C26; }
                QTabBar::tab:selected { background: #E1F3E8; color: #167A40; }
                QPushButton#settingsPicker { background: #F4F7FA; border-color: #D4DCE7; color: #18202A; }
                QPushButton#settingsPicker:hover { background: #FFFFFF; border-color: #21834C; }
                QCheckBox { color: #222E3D; }
                QCheckBox::indicator { background: #FFFFFF; border-color: #B8C4D4; }
                QSlider::groove:horizontal { background: #CFD8E3; }
                QSlider::sub-page:horizontal { background: #21834C; }
                QSlider::handle:horizontal { background: #21834C; }
                QPushButton#settingsCancel { background: #E7EDF4; color: #222E3D; border-color: #D0DAE6; }
                QPushButton#settingsCancel:hover { background: #DCE5F0; }
                QPushButton#settingsSave { background: #1DB954; color: #FFFFFF; }
                QPushButton#settingsSave:hover { background: #189E47; }
            """)
            light_menu = """QMenu { background: #FFFFFF; color: #18202A; border: 1px solid #D5DEE8; border-radius: 10px; padding: 6px; }
                QMenu::item { padding: 10px 20px; border: none; border-radius: 7px; }
                QMenu::item:selected { background: #E2F3E8; color: #167A40; }"""
            for popup in self.findChildren(QMenu):
                popup.setStyleSheet(light_menu)

    def choose_download_dir(self):
        default_dir = str(app_cache_directory() / "downloads")
        initial = self.download_dir_draft or default_dir
        selected = QFileDialog.getExistingDirectory(
            self,
            "Выбрать папку для скачивания треков",
            initial,
        )
        if not selected:
            return
        self.download_dir_draft = str(Path(selected))
        self.update_download_dir_ui()

    def reset_download_dir(self):
        self.download_dir_draft = ""
        self.update_download_dir_ui()

    def open_download_dir_from_settings(self):
        target = Path(self.download_dir_draft) if self.download_dir_draft else (app_cache_directory() / "downloads")
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    def update_download_dir_ui(self):
        default_dir = str(app_cache_directory() / "downloads")
        if self.download_dir_draft:
            self.download_dir_field.setText(self.download_dir_draft)
            self.download_dir_field.setToolTip(f"Выбранная папка загрузки:\n{self.download_dir_draft}")
        else:
            self.download_dir_field.setText(f"Стандартная папка: {default_dir}")
            self.download_dir_field.setToolTip(f"Папка по умолчанию:\n{default_dir}")
        self.download_dir_field.setCursorPosition(0)
        self.download_dir_reset.setEnabled(bool(self.download_dir_draft))

    def choose_wallpaper(self):
        path, _ = QFileDialog.getOpenFileName(self, "Выбрать фон", "", "Картинки (*.png *.jpg *.jpeg *.webp *.bmp)")
        if not path:
            return
        image = read_wallpaper_image(path)
        if image.isNull():
            self.wallpaper_message.setText("Не удалось открыть картинку. Выбери PNG, JPEG или WebP до 36 мегапикселей и 40 МБ.")
            return
        self.wallpaper_draft = image
        self.wallpaper_dirty = True
        self.wallpaper_preview_source = QPixmap.fromImage(image)
        self.wallpaper_message.setText("Нажми «Сохранить», чтобы применить фон.")
        self.update_wallpaper_preview()

    def remove_wallpaper(self):
        self.wallpaper_draft = QImage()
        self.wallpaper_dirty = True
        self.wallpaper_preview_source = QPixmap()
        self.wallpaper_message.setText("Нажми «Сохранить», чтобы убрать фон.")
        self.update_wallpaper_preview()

    def update_wallpaper_preview(self):
        dim = self.wallpaper_dim_slider.value()
        self.wallpaper_dim_label.setText(f"Затемнение · {dim}%")
        self.wallpaper_remove.setEnabled(not self.wallpaper_preview_source.isNull())
        self.wallpaper_preview.clear()
        if self.wallpaper_preview_source.isNull():
            self.wallpaper_preview.setText("Фон не выбран")
            return
        preview = self.wallpaper_preview_source.scaled(self.wallpaper_preview.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                                       Qt.TransformationMode.SmoothTransformation)
        # This is a small settings preview; the main window reuses its static cache.
        preview.setDevicePixelRatio(1)
        painter = QPainter(preview)
        painter.fillRect(preview.rect(), QColor(0, 0, 0, round(255 * dim / 100)))
        painter.end()
        self.wallpaper_preview.setPixmap(preview)

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
        if self.wallpaper_dirty and not player.set_wallpaper_image(self.wallpaper_draft):
            self.wallpaper_message.setText("Не удалось сохранить фон. Проверь свободное место и попробуй снова.")
            return
        player.wallpaper_dim = self.wallpaper_dim_slider.value()
        player.download_dir = str(self.download_dir_draft or "").strip()
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
        player.apply_styles()
        player.save_preferences()
        self.accept()


class Toast(QLabel):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWordWrap(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setStyleSheet(
            "background: rgba(18, 23, 31, 242); color: #F4F7FA; "
            "border: 1px solid rgba(92, 224, 146, 95); border-radius: 12px; padding: 12px 15px; font-weight: 600;"
        )
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

    def __init__(self, track, parent=None, download_dir=None):
        super().__init__(parent)
        self.track = dict(track)
        if download_dir is None and parent is not None and hasattr(parent, "get_download_directory"):
            try:
                download_dir = parent.get_download_directory()
            except Exception:
                download_dir = None
        self.download_dir = str(download_dir or "").strip()

    @staticmethod
    def _sanitize_filename(value):
        cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', " ", str(value or ""))
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
        return cleaned[:110]

    def run(self):
        try:
            url = str(self.track.get("url") or "")
            if not url.startswith(("https://", "http://")):
                raise ValueError("Нет адреса для скачивания")
            folder = Path(self.download_dir) if self.download_dir else (app_cache_directory() / "downloads")
            try:
                folder.mkdir(parents=True, exist_ok=True)
            except OSError:
                folder = app_cache_directory() / "downloads"
                folder.mkdir(parents=True, exist_ok=True)
            from urllib.parse import urlparse, parse_qs
            video_id = str(self.track.get("video_id") or "")
            if not video_id and self.track.get("source") == "youtube":
                video_id = parse_qs(urlparse(url).query).get("v", [""])[0]
            video_id = video_id or hashlib.sha256(url.encode()).hexdigest()[:24]
            source = re.sub(r"[^A-Za-z0-9_-]", "_", str(self.track.get("source") or "web"))
            video_id = re.sub(r"[^A-Za-z0-9_-]", "_", video_id)[:120]
            title = self._sanitize_filename(self.track.get("title") or "")
            artist = self._sanitize_filename(self.track.get("artist") or "")
            if artist.casefold() in ("исполнитель неизвестен", "unknown artist"):
                artist = ""
            if title and artist and artist.casefold() not in title.casefold():
                readable = f"{artist} - {title}"
            else:
                readable = title
            readable = self._sanitize_filename(readable)
            stem = f"{readable} [{video_id[:16]}]" if readable else f"{source}_{video_id}"
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
                candidates = [
                    p for p in folder.iterdir()
                    if p.is_file() and p.stem == stem and p.suffix not in (".part", ".ytdl", ".temp")
                ]
                if not candidates:
                    raise FileNotFoundError("Скачанный файл не найден")
                path = max(candidates, key=lambda p: p.stat().st_mtime)
            self.progress.emit(100)
            self.completed.emit(self.track, str(path.resolve()))
        except Exception as exc:
            self.failed.emit(str(exc))


class PlayerBar(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.accent = QColor("#243F35")
        self.accent_bright = QColor("#1ED760")
        self._viz_phase = 0.0
        self._viz_energy = 0.0
        self._viz_timer = QTimer(self)
        self._viz_timer.setInterval(40)
        self._viz_timer.timeout.connect(self._step_visualizer)

    def sync_visualizer_state(self, playing=False):
        win = self.window()
        viz_enabled = getattr(win, "visualizer_enabled", True)
        if playing and viz_enabled:
            if not self._viz_timer.isActive():
                self._viz_timer.start()
        elif self._viz_energy > 0.01:
            if not self._viz_timer.isActive():
                self._viz_timer.start()
        else:
            self._viz_energy = 0.0
            self._viz_timer.stop()
            self.update()

    def _step_visualizer(self):
        win = self.window()
        playing = bool(
            win is not None
            and hasattr(win, "player")
            and win.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
            and getattr(win, "visualizer_enabled", True)
        )
        if playing:
            self._viz_energy = min(1.0, self._viz_energy + 0.14)
            self._viz_phase = (self._viz_phase + 0.24) % (math.pi * 200.0)
        else:
            self._viz_energy = max(0.0, self._viz_energy - 0.12)
            if self._viz_energy <= 0.01:
                self._viz_energy = 0.0
                self._viz_timer.stop()
        self.update()

    def set_cover_accent(self, pixmap):
        if pixmap is None or pixmap.isNull():
            self.accent = QColor("#243F35")
            self.accent_bright = QColor("#1ED760")
        else:
            image = pixmap.toImage().scaled(12, 12)
            colors = [image.pixelColor(x, y) for x in range(12) for y in range(12)]
            avg = QColor(*(sum(getattr(c, channel)() for c in colors) // len(colors)
                           for channel in ("red", "green", "blue")))
            self.accent = avg
            h, s, l, _ = avg.getHsl()
            if h < 0:
                self.accent_bright = QColor("#1ED760")
            else:
                boosted = QColor.fromHsl(h, max(165, min(245, int(s * 1.45))), max(135, min(175, int(l * 1.25))))
                self.accent_bright = boosted
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 14, 14)
        painter.setClipPath(path)
        win = self.window()
        light = getattr(win, "theme", "dark") == "light"
        chameleon_on = getattr(win, "chameleon_enabled", True)
        base_col = QColor(self.accent if chameleon_on else QColor("#1C3B2B"))
        bright_col = QColor(self.accent_bright if chameleon_on else QColor("#1ED760"))

        color = QColor(base_col)
        color.setAlpha(32 if light else 68)
        gradient = QLinearGradient(0, 0, min(740, self.width()), self.height())
        gradient.setColorAt(0.0, color)
        mid = QColor(bright_col)
        mid.setAlpha(14 if light else 26)
        gradient.setColorAt(0.52, mid)
        color.setAlpha(0)
        gradient.setColorAt(1.0, color)
        painter.fillRect(self.rect(), gradient)

        # Живой спектр-эквалайзер на фоне нижней панели во время воспроизведения
        if self._viz_energy > 0.01 and getattr(win, "visualizer_enabled", True):
            num_bars = 44
            span_w = min(640.0, max(280.0, self.width() * 0.52))
            start_x = (self.width() - span_w) / 2.0
            step_x = span_w / num_bars
            bar_w = max(3.0, step_x * 0.56)
            bottom_y = float(self.height() - 2.0)
            max_bar_h = float(self.height() * 0.44) * self._viz_energy
            painter.setPen(Qt.PenStyle.NoPen)
            for idx in range(num_bars):
                norm = idx / max(1.0, float(num_bars - 1))
                bell = math.sin(norm * math.pi) ** 0.65
                w1 = math.sin(self._viz_phase * 1.15 + idx * 0.42)
                w2 = math.cos(self._viz_phase * 0.78 - idx * 0.67)
                w3 = math.sin(self._viz_phase * 1.65 + idx * 0.23)
                level = max(0.08, (0.45 + 0.25 * w1 + 0.18 * w2 + 0.12 * w3) * bell)
                bh = max(2.5, max_bar_h * level)
                bx = start_x + idx * step_x
                bar_grad = QLinearGradient(bx, bottom_y - bh, bx, bottom_y)
                top_c = QColor(bright_col)
                top_c.setAlpha(int((48 if light else 64) * self._viz_energy))
                bot_c = QColor(bright_col)
                bot_c.setAlpha(int((12 if light else 18) * self._viz_energy))
                bar_grad.setColorAt(0.0, top_c)
                bar_grad.setColorAt(1.0, bot_c)
                painter.setBrush(QBrush(bar_grad))
                painter.drawRoundedRect(QRectF(bx, bottom_y - bh, bar_w, bh), 2.0, 2.0)

        top_glow = QColor(bright_col)
        top_glow.setAlpha(68 if not light else 45)
        painter.setPen(QPen(top_glow, 1.1))
        painter.drawLine(16, 1, max(16, self.width() - 16), 1)
        painter.end()


class CoverPopupPage(QWidget):
    """Атмосферная прослойка для раскрытой обложки с мягким свечением, карточкой трека и винил-режимом."""
    close_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.accent = QColor("#243F35")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setStyleSheet("background: transparent; border: none;")

    def set_cover_accent(self, pixmap):
        if pixmap is not None and not pixmap.isNull():
            img = pixmap.toImage().scaled(8, 8)
            cols = [img.pixelColor(x, y) for x in range(8) for y in range(8)]
            self.accent = QColor(*(sum(getattr(c, ch)() for c in cols) // len(cols) for ch in ("red", "green", "blue")))
        self.update()


class MiniPlayer(PlayerBar):
    """A second view of the existing players; it owns no audio or network workers."""
    def __init__(self, player):
        super().__init__(player)
        self.owner = player
        self.theme = player.theme
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setObjectName("miniPlayer")
        self.setWindowTitle("Aurora · Мини-плеер")
        self.setWindowIcon(application_icon())
        self.setFixedSize(420, 200)
        self._drag_offset = None
        self._seeking = False
        self._cover_url = None
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 9, 14, 12)
        root.setSpacing(6)
        header = QHBoxLayout()
        self.status = QLabel("Мини-плеер")
        self.status.setObjectName("miniStatus")
        self.status.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        header.addWidget(self.status, 1)
        self.restore_button = QPushButton("↗")
        self.restore_button.setToolTip("Открыть полный плеер")
        self.close_button = QPushButton("×")
        self.close_button.setToolTip("Закрыть мини-плеер и вернуться к полному окну")
        for button in (self.restore_button, self.close_button):
            button.setFixedSize(26, 24)
            header.addWidget(button)
        self.restore_button.clicked.connect(player.restore_from_tray)
        self.close_button.clicked.connect(self.close)
        root.addLayout(header)
        info = QHBoxLayout()
        info.setSpacing(12)
        self.cover = QLabel()
        self.cover.setFixedSize(56, 56)
        info.addWidget(self.cover)
        text = QVBoxLayout()
        self.title_label = MarqueeLabel()
        self.title_label.setObjectName("miniTitle")
        self.artist_label = QLabel()
        self.artist_label.setObjectName("miniArtist")
        for label in (self.title_label, self.artist_label):
            label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            text.addWidget(label)
        info.addLayout(text, 1)
        self.favorite_button = QPushButton()
        self.favorite_button.setFixedSize(32, 32)
        self.favorite_button.clicked.connect(player.toggle_current_favorite)
        info.addWidget(self.favorite_button)
        root.addLayout(info)
        transport = QHBoxLayout()
        transport.setSpacing(8)
        transport.addStretch(1)
        self.previous_button, self.play_button, self.next_button = QPushButton(), QPushButton(), QPushButton()
        for button in (self.previous_button, self.play_button, self.next_button):
            button.setFixedSize(34, 34)
            button.setIconSize(QSize(20, 20))
            transport.addWidget(button)
        self.play_button.setObjectName("miniPlay")
        self.play_button.setFixedSize(40, 40)
        self.previous_button.setToolTip("Предыдущий трек")
        self.play_button.setToolTip("Воспроизведение / пауза")
        self.next_button.setToolTip("Следующий трек")
        self.previous_button.clicked.connect(player.play_previous)
        self.play_button.clicked.connect(self.toggle_playback)
        self.next_button.clicked.connect(player.play_next)
        transport.addStretch(1)
        self.volume_slider = ClickSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setFixedSize(76, 16)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setToolTip("Громкость")
        self.volume_slider.valueChanged.connect(player.volume_slider.setValue)
        transport.addWidget(self.volume_slider)
        root.addLayout(transport)
        timeline = QHBoxLayout()
        self.position_label = QLabel("0:00")
        self.duration_label = QLabel("0:00")
        self.seek_slider = ClickSlider(Qt.Orientation.Horizontal)
        self.seek_slider.setFixedHeight(16)
        self.seek_slider.sliderPressed.connect(lambda: setattr(self, "_seeking", True))
        self.seek_slider.sliderReleased.connect(self.seek_released)
        timeline.addWidget(self.position_label)
        timeline.addWidget(self.seek_slider, 1)
        timeline.addWidget(self.duration_label)
        root.addLayout(timeline)
        for keys, callback in (("Space", self.toggle_playback), ("Ctrl+Right", player.play_next),
                               ("Ctrl+Left", player.play_previous), ("Ctrl+L", player.like_current_shortcut),
                               ("Ctrl+Q", player.request_app_exit),
                               ("Ctrl+M", player.restore_from_tray),
                               ("Escape", player.restore_from_tray)):
            shortcut = QShortcut(QKeySequence(keys), self)
            shortcut.activated.connect(callback)
        self.apply_theme()

    def paintEvent(self, event):
        # A translucent top-level window needs an explicit opaque base inside
        # the rounded frame; relying on QFrame's stylesheet leaves stale pixels.
        painter = QPainter(self)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 0))
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bounds = QRectF(self.rect()).adjusted(.5, .5, -.5, -.5)
        path = QPainterPath()
        path.addRoundedRect(bounds, 14, 14)
        light = self.theme == "light"
        painter.fillPath(path, QColor("#FFFFFF" if light else "#151921"))
        gradient = QLinearGradient(0, 0, self.width(), self.height())
        accent = QColor(self.accent)
        accent.setAlpha(24 if light else 52)
        gradient.setColorAt(0.0, accent)
        accent_mid = QColor(self.accent)
        accent_mid.setAlpha(8 if light else 18)
        gradient.setColorAt(0.6, accent_mid)
        accent.setAlpha(0)
        gradient.setColorAt(1.0, accent)
        painter.fillPath(path, gradient)
        painter.setPen(QPen(QColor("#D5DEE8" if light else "#2D3644"), 1))
        painter.drawPath(path)
        painter.end()

    def apply_theme(self):
        self.theme = self.owner.theme
        light = self.theme == "light"
        background, foreground, muted = ("#FFFFFF", "#18202A", "#606D80") if light else ("#151921", "#F5F7FA", "#A6B1C2")
        self.setStyleSheet(f"""
            QFrame#miniPlayer {{ background: {background}; border: 1px solid {'#D5DEE8' if light else '#2D3644'}; border-radius: 14px; }}
            QLabel {{ color: {foreground}; background: transparent; border: none; }}
            QLabel#miniTitle {{ font-size: 14px; font-weight: 700; }}
            QLabel#miniStatus, QLabel#miniArtist {{ color: {muted}; font-size: 11px; }}
            QPushButton {{ background: transparent; color: {foreground}; border: none; border-radius: 8px; padding: 0; }}
            QPushButton:hover {{ background: {'#E8F1EC' if light else '#252F38'}; }}
            QPushButton#miniPlay {{ background: #1DB954; border-radius: 20px; }}
            QPushButton#miniPlay:hover {{ background: #1ED760; }}
        """)
        self.previous_button.setIcon(control_icon("previous", foreground))
        self.next_button.setIcon(control_icon("next", foreground))
        self.sync_from_player()

    def sync_from_player(self):
        w = self.owner
        track = w.current_track or w.requested_track or {}
        full_title = str(track.get("title") or "Ничего не играет")
        self.title_label.setText(full_title)
        self.title_label.setToolTip(full_title)
        full_artist = str(track.get("artist_display") or track.get("artist") or "Выбери трек в полном плеере")
        self.artist_label.setText(self.artist_label.fontMetrics().elidedText(full_artist, Qt.TextElideMode.ElideRight, max(60, self.artist_label.width())))
        self.artist_label.setToolTip(full_artist)
        playing = w.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        self.play_button.setIcon(control_icon("pause" if playing else "play", "#FFFFFF", 24))
        status = ("Загрузка…" if w.requested_track is not None else "Продолжить прослушивание" if w._restored_playback else
                  "Сейчас играет" if playing else "На паузе" if track else "Мини-плеер")
        self.status.setText(status)
        self.favorite_button.setEnabled(w.bottom_favorite_button.isEnabled())
        self.favorite_button.setIcon(w.bottom_favorite_button.icon())
        self.favorite_button.setIconSize(QSize(22, 22))
        self.favorite_button.setToolTip(w.bottom_favorite_button.toolTip())
        self.volume_slider.blockSignals(True)
        self.volume_slider.setValue(round(w.volume * 100))
        self.volume_slider.blockSignals(False)
        url = normalize_artwork_url(track.get("thumbnail", ""))
        if url != self._cover_url:
            self._cover_url = url
            w.request_image(url, self.cover)
            self.set_cover_accent(w.pixmap_cache.get(url))
        self.sync_position()

    def sync_position(self):
        w = self.owner
        position = w._restored_playback["position"] if w._restored_playback else w.player.position()
        duration = w.player.duration() or int((w.current_track or {}).get("duration") or 0) * 1000
        self.position_label.setText(w.format_position(position))
        self.duration_label.setText(w.format_position(duration))
        if not self._seeking:
            self.seek_slider.setRange(0, max(0, duration))
            self.seek_slider.setValue(position)
        self.seek_slider.setEnabled(w.player.isSeekable() and w._restored_playback is None)

    def seek_released(self):
        if self.owner.player.isSeekable():
            self.owner._last_progress_position = self.seek_slider.value()
            self.owner._last_progress_at = time.monotonic()
            self.owner.player.setPosition(self.seek_slider.value())
        self._seeking = False

    def toggle_playback(self):
        if not (self.owner.current_track or self.owner.requested_track or self.owner.queue_tracks):
            self.owner.restore_from_tray()
            return
        self.owner.toggle_playback()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None

    def closeEvent(self, event):
        self.owner.settings.setValue("mini_geometry", self.saveGeometry())
        if not self.owner._force_exit:
            self.owner.restore_from_tray()
        event.accept()


class MusicPlayer(QMainWindow):
    RECENT_TRACK_LIMIT = 40
    RECENT_PREVIEW_COUNT = 12
    PENDING_MEDIA_TIMEOUT_MS = 20_000
    PLAYBACK_STALL_SECONDS = 5
    MAX_STREAM_RECOVERIES = 5
    ARTWORK_MAX_SIDE = 768
    ARTWORK_MAX_PIXELS = 16_777_216
    ARTWORK_MAX_DOWNLOAD = 5_000_000
    ARTWORK_CACHE_BYTES = 32 * 1024 * 1024
    THUMBNAIL_CACHE_BYTES = 4 * 1024 * 1024

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
        bind("Ctrl+M", self.show_mini_player)
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
        if self.view_stack.currentWidget() is self.cover_page:
            self.close_cover_view()
        elif self.queue_open:
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

    def _sync_bottom_bar_side_widths(self):
        if not hasattr(self, "bottom_track_info") or not hasattr(self, "bottom_right_tools"):
            return
        side_w = max(360, min(460, (self.width() - 520) // 2))
        self.bottom_track_info.setFixedWidth(side_w)
        self.bottom_right_tools.setFixedWidth(side_w)
        label_max = max(220, side_w - 116)
        self.bottom_labels_box.setMaximumWidth(label_max)
        self.bottom_title.setMaximumWidth(label_max)
        self.bottom_artist.setMaximumWidth(max(215, label_max - 5))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_bottom_bar_side_widths()
        if hasattr(self, "cover_page") and not self._force_exit:
            QTimer.singleShot(0, self.refresh_current_track_views)
            self._position_expanded_cover()
        toast = getattr(self, "toast", None)
        if toast is not None and toast.isVisible():
            toast.move(max(0, self.width() - toast.width() - 20),
                       max(0, self.height() - toast.height() - 20))

    def get_download_directory(self):
        custom = str(getattr(self, "download_dir", "") or "").strip()
        if custom:
            try:
                path = Path(custom).expanduser()
                path.mkdir(parents=True, exist_ok=True)
                return path
            except OSError:
                pass
        default_dir = app_cache_directory() / "downloads"
        try:
            default_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        return default_dir

    def open_download_folder(self, track=None):
        target = None
        if isinstance(track, dict):
            offline = self.offline_path_for(track)
            if offline:
                try:
                    target = Path(offline).resolve().parent
                except OSError:
                    target = None
        if target is None or not target.is_dir():
            target = self.get_download_directory()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

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
                custom_candidate = self.get_download_directory() / path
                path = custom_candidate if custom_candidate.is_file() else (app_cache_directory() / "downloads" / path)
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
        worker = DownloadWorker(track, self, download_dir=self.get_download_directory())
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

    def __init__(self, settings=None):
        super().__init__()
        # QSettings сохраняет предпочтения между запусками на Windows.
        self.settings = settings if settings is not None else QSettings("AuroraLocal", "MusicPlayer")
        self.theme = str(self.settings.value("spotify_theme", "dark"))
        if self.theme not in ("dark", "light"):
            self.theme = "dark"
        self.download_dir = str(self.settings.value("download_dir", "") or "").strip()
        self.wallpaper_path = str(self.settings.value("wallpaper_path", "") or "")
        try:
            self.wallpaper_dim = max(0, min(90, int(self.settings.value("wallpaper_dim", 55))))
        except (TypeError, ValueError):
            self.wallpaper_dim = 55
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
        self.recent_tracks = self.load_recent_tracks()
        self._recent_expanded_sources = set()
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
        self._likes_live_rows = {"youtube": {}, "soundcloud": {}, "local": {}}
        self._row_windows_updating = set()
        self._queue_live_rows = {}
        self._queue_rebuilding = False
        self._likes_display_tracks = {}
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
        self.user_playlists_file = migrate_legacy_data("user_playlists.json")
        self.user_playlist_folders = []
        self.collapsed_playlist_folders = set()
        self.user_playlists = self.load_user_playlists()
        self.active_user_playlist_id = ""
        self._playlist_search_query = ""
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
        self.setWindowTitle("")
        self.setWindowIcon(application_icon())
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
        self.queue_open = False
        self.mini_player = None
        self._restored_playback = None
        self._requested_start_position = 0
        self._session_ready = False
        self._session_queue_dirty = False
        self._session_revision = ""
        self._last_checkpoint_blob = ""
        self.session_file = app_data_directory() / "playback_session.json"
        self.session_save_timer = QTimer(self)
        self.session_save_timer.setSingleShot(True)
        self.session_save_timer.timeout.connect(self.save_playback_session)
        self.checkpoint_timer = QTimer(self)
        self.checkpoint_timer.setInterval(5000)
        self.checkpoint_timer.timeout.connect(self.save_playback_checkpoint)
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
        self.supermix_refill_worker = None
        self.supermix_session = None
        self.supermix_cover_url = str(self.settings.value("supermix_cover_url", "") or "")
        self.youtube_mix_catalog = {}
        self.youtube_mix_covers = {}
        try:
            raw_cat = str(self.settings.value("youtube_mix_catalog_json", "") or "").strip()
            if raw_cat:
                parsed_cat = json.loads(raw_cat)
                if isinstance(parsed_cat, dict):
                    self.youtube_mix_catalog = parsed_cat
                    for ck, cinfo in parsed_cat.items():
                        if isinstance(cinfo, dict) and cinfo.get("cover_url"):
                            self.youtube_mix_covers[str(ck)] = str(cinfo["cover_url"])
                            if ck == "supermix" and not self.supermix_cover_url:
                                self.supermix_cover_url = str(cinfo["cover_url"])
        except Exception:
            pass
        self.supermix_retry_timer = QTimer(self)
        self.supermix_retry_timer.setSingleShot(True)
        self.supermix_retry_timer.timeout.connect(self.maybe_refill_supermix)
        self.radio_mode_active = False
        self.radio_seed_track = None
        self.radio_refill_worker = None
        self.radio_refill_attempt_key = ""
        self.radio_refill_added_urls = set()
        self.radio_refill_next_allowed_at = 0.0
        self.radio_refill_round = 0
        self.radio_launch_counter = 0
        self.radio_refill_added_count = 0
        self.radio_refill_last_error = ""
        self._radio_refill_failed_attempts = 0
        self.radio_artist_context = ""
        self.radio_seen_urls = set()
        self.radio_seen_signatures = set()
        self.radio_recent_history = deque(maxlen=300)
        self._radio_waiting_for_tracks = False
        self._finish_transition_pending = False
        self._finish_guard_url = ""
        self._auto_failed_tracks = set()
        self.auto_play_next_search = False
        self.auto_play_generation = -1
        self.start_cards = []

        # Прямые ссылки временные и могут истекать; сохраняем их на 45 минут.
        self.stream_cache = {}
        self._stream_details = OrderedDict()
        self.stream_cache_ttl = 45 * 60
        self._stream_workers = set()
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
        self._network_recovery = None
        self._network_recovery_attempts = 0
        self._recovery_committed_position = None
        self._playback_wanted = False
        self._last_progress_at = time.monotonic()
        self._last_progress_position = 0
        self._last_duration = 0
        self._recovery_seek_applied = False
        self.playback_watchdog = QTimer(self)
        self.playback_watchdog.setInterval(1000)
        self.playback_watchdog.timeout.connect(self.check_playback_health)
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
        self.thumbnail_cache = OrderedDict()
        self.image_waiters = {}  # URL -> weak references to current image targets
        self.image_backlog = deque()
        self.active_images = 0
        self.image_limit = 6
        self.fallback_cover = make_placeholder()

        self.visualizer_enabled = self.settings.value("visualizer_enabled", "true") == "true"
        self.chameleon_enabled = self.settings.value("chameleon_enabled", "true") == "true"
        self.vinyl_enabled = self.settings.value("vinyl_enabled", "true") == "true"
        self.frameless_enabled = False
        self.chameleon_accent = QColor("#1DB954")
        self.chameleon_bright = QColor("#1ED760")
        self._top_drag_offset = None

        self._likes_search_query = ""
        self._available_update_info = None
        self._update_checker_worker = None
        self._update_installer_worker = None
        self._update_banner_dismissed = False
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
        self.refresh_repeat_button()
        self.shuffle_button.setChecked(self.shuffle_enabled)
        self.set_volume(int(round(self.volume * 100)))
        self.restore_playback_session()
        self._session_ready = True
        self.checkpoint_timer.start()
        self._startup_update_timer = QTimer(self)
        self._startup_update_timer.setSingleShot(True)
        self._startup_update_timer.timeout.connect(lambda: self.check_for_updates(manual=False))
        if (os.environ.get("QT_QPA_PLATFORM") != "offscreen"
                and _SMOKE_DIRECTORY is None
                and "unittest" not in sys.modules):
            self._startup_update_timer.start(3200)
            QTimer.singleShot(150, self._prewarm_youtube_startup)
            if self.supermix_cover_url or self.youtube_mix_covers:
                QTimer.singleShot(250, self._update_supermix_cover)
                QTimer.singleShot(250, self._update_youtube_mix_covers)

    # ---------------------------------------------------------
    # Интерфейс. Две постоянные колонки + выдвижная очередь.
    # ---------------------------------------------------------

    def setup_system_tray(self):
        """Создаёт значок системного трея с управлением воспроизведением."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_icon = None
            return
        icon = application_icon()
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
        if self.mini_player is not None:
            self.settings.setValue("mini_geometry", self.mini_player.saveGeometry())
            self.mini_player.hide()
        self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()

    def show_mini_player(self):
        if self.mini_player is None:
            self.mini_player = MiniPlayer(self)
            geometry = self.settings.value("mini_geometry")
            if geometry:
                try:
                    self.mini_player.restoreGeometry(geometry)
                except TypeError:
                    pass
            else:
                self.mini_player.move(self.frameGeometry().topLeft() + QPoint(30, 30))
        mini = self.mini_player
        if not any(screen.availableGeometry().intersects(mini.frameGeometry()) for screen in QApplication.screens()):
            mini.move(self.screen().availableGeometry().topLeft() + QPoint(24, 24))
        mini.apply_theme()
        mini.show()
        mini.sync_from_player()
        mini.raise_()
        self.hide()

    def refresh_mini_player(self):
        if self.mini_player is not None and self.mini_player.isVisible():
            self.mini_player.sync_from_player()

    def request_app_exit(self):
        """Аккуратно завершает приложение после завершения/отмены фоновых потоков."""
        self.save_playback_session()
        self.checkpoint_timer.stop()
        self.session_save_timer.stop()
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
        root_widget = PlayerBackdrop()
        self.backdrop = root_widget
        root_widget.set_image(read_wallpaper_image(self.wallpaper_path))
        root_widget.set_appearance(self.theme, self.wallpaper_dim)
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
        self.queue_animation.valueChanged.connect(lambda width: self.queue_panel.setMinimumWidth(int(width)))
        self.page_animation = None
        self._animated_page = None
        self.last_library_page = self.browse_page
        self.toast = Toast(self)
        self.install_shortcuts()

    def create_sidebar(self):
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(216)
        side_layout = QVBoxLayout(self.sidebar)
        side_layout.setContentsMargins(12, 16, 12, 14)
        side_layout.setSpacing(6)

        lib_header = QWidget(self.sidebar)
        lib_header_layout = QHBoxLayout(lib_header)
        lib_header_layout.setContentsMargins(4, 0, 2, 2)
        lib_header_layout.setSpacing(6)
        self.sidebar_library_title = QLabel("МОЯ МЕДИАТЕКА", lib_header)
        self.sidebar_library_title.setObjectName("sidebarSectionTitle")
        self.sidebar_add_playlist_button = QPushButton("＋", lib_header)
        self.sidebar_add_playlist_button.setObjectName("sidebarAddButton")
        self.sidebar_add_playlist_button.setFixedSize(24, 24)
        self.sidebar_add_playlist_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sidebar_add_playlist_button.setToolTip("Создать плейлист, папку или импортировать из файла")
        self.sidebar_add_playlist_button.clicked.connect(self.open_sidebar_add_menu)
        lib_header_layout.addWidget(self.sidebar_library_title, 1)
        lib_header_layout.addWidget(self.sidebar_add_playlist_button)
        side_layout.addWidget(lib_header)

        self.sidebar_library_scroll = QScrollArea(self.sidebar)
        self.sidebar_library_scroll.setObjectName("sidebarLibraryScroll")
        self.sidebar_library_scroll.setWidgetResizable(True)
        self.sidebar_library_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.sidebar_library_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.sidebar_library_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.sidebar_library_widget = QWidget(self.sidebar_library_scroll)
        self.sidebar_library_widget.setObjectName("sidebarLibraryWidget")
        self.sidebar_library_layout = QVBoxLayout(self.sidebar_library_widget)
        self.sidebar_library_layout.setContentsMargins(0, 2, 0, 4)
        self.sidebar_library_layout.setSpacing(4)
        self.sidebar_library_scroll.setWidget(self.sidebar_library_widget)
        side_layout.addWidget(self.sidebar_library_scroll, 1)

        self.nav_buttons = []
        self.nav_data = [
            ("▶", "YouTube Music", "youtube"),
            ("☁", "SoundCloud", "soundcloud"),
            ("♥", "Лайки", "likes"),
        ]
        for icon, title, _ in self.nav_data:
            btn = AnimatedNavButton(icon, title, self.sidebar_library_widget)
            self.sidebar_library_layout.addWidget(btn)
            self.nav_buttons.append(btn)

        self.sidebar_library_items = []
        self._sidebar_library_signature = None

        self.sidebar_divider = QFrame(self.sidebar)
        self.sidebar_divider.setObjectName("sidebarDivider")
        self.sidebar_divider.setFixedHeight(1)
        side_layout.addWidget(self.sidebar_divider)
        update_button = QPushButton(f"↻ Обновить · v{APP_VERSION}", self.sidebar)
        self.sidebar_update_button = update_button
        update_button.setObjectName("sidebarUpdate")
        update_button.setProperty("has_update", False)
        update_button.setMinimumHeight(40)
        update_button.setCursor(Qt.CursorShape.PointingHandCursor)
        update_button.setToolTip("Проверить наличие новой версии на GitHub и обновить приложение")
        update_button.clicked.connect(self.on_update_button_clicked)
        side_layout.addWidget(update_button)
        settings_button = QPushButton("Настройки", self.sidebar)
        self.sidebar_settings_button = settings_button
        settings_button.setObjectName("sidebarSettings")
        settings_button.setMinimumHeight(44)
        settings_button.setIconSize(QSize(18, 18))
        settings_button.setToolTip("Настройки плеера")
        settings_button.clicked.connect(self.open_settings)
        side_layout.addWidget(settings_button)
        return self.sidebar

    def create_center(self):
        panel = QFrame()
        panel.setObjectName("centerPanel")
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(24, 20, 24, 18)
        outer.setSpacing(0)

        # Три внутренних экрана: каталог, полноразмерная обложка, лайки.
        self.view_stack = QStackedWidget()
        outer.addWidget(self.view_stack, 1)

        self.browse_page = QWidget()
        browse = QVBoxLayout(self.browse_page)
        browse.setContentsMargins(0, 0, 0, 0)
        browse.setSpacing(12)

        self.page_title = QLabel("YouTube Music", self.browse_page)
        self.page_title.setObjectName("pageTitle")
        self.page_description = QLabel("", self.browse_page)
        self.page_description.setObjectName("mutedText")
        self.page_title.hide()
        self.page_description.hide()
        self.theme_button = QPushButton("☀")
        self.theme_button.setObjectName("themeButton")
        self.theme_button.setFixedSize(42, 38)
        self.theme_button.setToolTip("Переключить светлую / тёмную тему")

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

        self.search_shell = QFrame()
        self.search_shell.setObjectName("searchBox")
        self.search_shell.setMinimumHeight(54)
        self.search_shell.setProperty("focused", False)
        shell_layout = QHBoxLayout(self.search_shell)
        shell_layout.setContentsMargins(16, 5, 6, 5)
        shell_layout.setSpacing(10)
        self.search_icon = QLabel()
        self.search_icon.setFixedSize(20, 20)
        shell_layout.addWidget(self.search_icon)
        self.search_input = QLineEdit()
        self.search_input.setObjectName("catalogSearch")
        self.search_input.setPlaceholderText("Найти трек или исполнителя")
        self.search_input.setAccessibleName("Поиск музыки")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setMinimumWidth(0)
        self.search_input.setMinimumHeight(40)
        self.search_input.installEventFilter(self)
        self.search_shell.installEventFilter(self)
        shell_layout.addWidget(self.search_input, 1)
        self.search_shortcut = QLabel("Ctrl F")
        self.search_shortcut.setObjectName("searchShortcut")
        self.search_shortcut.setAlignment(Qt.AlignmentFlag.AlignCenter)
        shell_layout.addWidget(self.search_shortcut)

        # Переключатель сортировки убран из интерфейса: профиль показывает
        # обычную выдачу исполнителя без меню «Популярные / Сначала новые».
        # Атрибут оставлен скрытым, чтобы старые внутренние вызовы не ломались.
        self.sort_button = QPushButton(self)
        self.sort_button.setObjectName("filterButton")
        self.sort_button.hide()
        self.sort_menu = None

        # Количество результатов теперь только в настройках.
        self.search_button = QPushButton("Найти")
        self.search_button.setObjectName("searchSubmit")
        self.search_button.setFixedSize(80, 40)
        shell_layout.addWidget(self.search_button)
        self.top_update_button = QPushButton("⬇ Обновить", self.search_row)
        self.top_update_button.setObjectName("topUpdateButton")
        self.top_update_button.setProperty("has_update", False)
        self.top_update_button.setMinimumHeight(38)
        self.top_update_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.top_update_button.setToolTip("Доступна новая версия на GitHub — нажмите для обновления")
        self.top_update_button.clicked.connect(self.on_update_button_clicked)
        self.top_update_button.hide()
        search_layout.addWidget(self.back_button)
        search_layout.addWidget(self.search_shell, 1)
        search_layout.addWidget(self.top_update_button)
        search_layout.addWidget(self.theme_button)
        browse.addWidget(self.search_row)

        # Плашка-предупреждение о выходе новой версии на GitHub
        self.update_warning_banner = QFrame(self.browse_page)
        self.update_warning_banner.setObjectName("updateWarningBanner")
        banner_layout = QHBoxLayout(self.update_warning_banner)
        banner_layout.setContentsMargins(16, 10, 12, 10)
        banner_layout.setSpacing(10)
        self.update_banner_label = QLabel(
            f"⚠ Доступна новая версия Aurora! Ваша версия: v{APP_VERSION}.",
            self.update_warning_banner,
        )
        self.update_banner_label.setObjectName("updateBannerTitle")
        self.update_banner_label.setWordWrap(True)
        self.update_banner_install_btn = QPushButton("⬇ Обновить сейчас", self.update_warning_banner)
        self.update_banner_install_btn.setObjectName("updateBannerAction")
        self.update_banner_install_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_banner_install_btn.clicked.connect(self.on_update_button_clicked)
        self.update_banner_github_btn = QPushButton("GitHub Release ↗", self.update_warning_banner)
        self.update_banner_github_btn.setObjectName("textButton")
        self.update_banner_github_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_banner_github_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(
                QUrl(
                    str((self._available_update_info or {}).get("release_url") or f"https://github.com/{GITHUB_REPO}/releases")
                )
            )
        )
        self.update_banner_close_btn = QPushButton("×", self.update_warning_banner)
        self.update_banner_close_btn.setObjectName("updateBannerClose")
        self.update_banner_close_btn.setFixedSize(28, 28)
        self.update_banner_close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_banner_close_btn.setToolTip("Скрыть уведомление до следующего запуска")
        self.update_banner_close_btn.clicked.connect(self.dismiss_update_banner)
        banner_layout.addWidget(self.update_banner_label, 1)
        banner_layout.addWidget(self.update_banner_install_btn, 0)
        banner_layout.addWidget(self.update_banner_github_btn, 0)
        banner_layout.addWidget(self.update_banner_close_btn, 0)
        self.update_warning_banner.hide()
        browse.addWidget(self.update_warning_banner)

        self.start_cards_widget = QWidget()
        self.start_cards_widget.setObjectName("startCardsWidget")
        self.start_cards_layout = QVBoxLayout(self.start_cards_widget)
        self.start_cards_layout.setContentsMargins(0, 8, 0, 4)
        self.start_cards_layout.setSpacing(24)
        self.home_tiles = QWidget()
        self.home_tiles_layout = QGridLayout(self.home_tiles)
        self.home_tiles_layout.setContentsMargins(0, 0, 0, 0)
        self.home_tiles_layout.setSpacing(16)
        self.start_cards_layout.addWidget(self.home_tiles)
        self.recent_section = QWidget()
        recent_layout = QVBoxLayout(self.recent_section)
        recent_layout.setContentsMargins(0, 0, 0, 0)
        recent_layout.setSpacing(8)
        self.recent_heading = QLabel("Недавно слушал")
        self.recent_heading.setObjectName("sectionTitle")
        recent_header = QHBoxLayout()
        recent_header.addWidget(self.recent_heading)
        recent_header.addStretch(1)
        self.recent_more_button = QPushButton("Показать все")
        self.recent_more_button.setObjectName("textButton")
        self.recent_more_button.clicked.connect(self.toggle_recent_tracks)
        self.recent_more_button.hide()
        recent_header.addWidget(self.recent_more_button)
        recent_layout.addLayout(recent_header)
        self.recent_rows_widget = QWidget()
        self.recent_rows_layout = QVBoxLayout(self.recent_rows_widget)
        self.recent_rows_layout.setContentsMargins(0, 0, 0, 0)
        self.recent_rows_layout.setSpacing(4)
        recent_layout.addWidget(self.recent_rows_widget)
        self.start_cards_layout.addWidget(self.recent_section)
        self.start_cards_layout.addStretch(1)
        self.start_cards_scroll = QScrollArea()
        self.start_cards_scroll.setObjectName("startCardsScroll")
        self.start_cards_scroll.setWidgetResizable(True)
        self.start_cards_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.start_cards_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.start_cards_scroll.setWidget(self.start_cards_widget)
        self.start_cards_scroll.viewport().installEventFilter(self)
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
        table_duration = QLabel("Время")
        table_duration.setFixedWidth(48)
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

        self.likes_hero_header = QFrame(self.likes_page)
        self.likes_hero_header.setObjectName("likesHeroHeader")
        self.likes_hero_header.setMinimumHeight(136)
        self.likes_hero_header.setMaximumHeight(156)
        hero_layout = QHBoxLayout(self.likes_hero_header)
        hero_layout.setContentsMargins(18, 14, 18, 14)
        hero_layout.setSpacing(18)

        self.likes_collage_cover = LikesCollageCover(self.likes_hero_header)
        hero_layout.addWidget(self.likes_collage_cover, 0, Qt.AlignmentFlag.AlignVCenter)

        heading_text = QVBoxLayout()
        heading_text.setContentsMargins(0, 0, 0, 0)
        heading_text.setSpacing(3)
        likes_eyebrow = QLabel("КОЛЛЕКЦИЯ · ИЗБРАННОЕ")
        likes_eyebrow.setObjectName("artistVerified")
        likes_title = QLabel("Лайки")
        likes_title.setObjectName("pageTitle")
        self.likes_title = QLabel("Твоя любимая музыка")
        self.likes_title.setObjectName("mutedText")
        heading_text.addWidget(likes_eyebrow)
        heading_text.addWidget(likes_title)
        heading_text.addWidget(self.likes_title)

        hero_actions = QHBoxLayout()
        hero_actions.setContentsMargins(0, 4, 0, 0)
        hero_actions.setSpacing(8)
        self.likes_play_all_button = QPushButton("Слушать")
        self.likes_play_all_button.setObjectName("artistShuffleButton")
        self.likes_play_all_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.likes_play_all_button.setIcon(control_icon("play", "#101010", 18))
        self.likes_play_all_button.setIconSize(QSize(16, 16))
        self.likes_play_all_button.setMinimumHeight(32)
        self.likes_play_all_button.setToolTip("Запустить воспроизведение текущей вкладки лайков")
        self.likes_play_all_button.clicked.connect(lambda checked=False: self.play_active_likes_tab(shuffle=False))

        self.likes_shuffle_all_button = QPushButton("Перемешать")
        self.likes_shuffle_all_button.setObjectName("artistMixButton")
        self.likes_shuffle_all_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.likes_shuffle_all_button.setIcon(control_icon("shuffle", "#66E099", 18))
        self.likes_shuffle_all_button.setIconSize(QSize(16, 16))
        self.likes_shuffle_all_button.setMinimumHeight(32)
        self.likes_shuffle_all_button.setToolTip("Перемешать любимые треки и начать воспроизведение")
        self.likes_shuffle_all_button.clicked.connect(lambda checked=False: self.play_active_likes_tab(shuffle=True))
        hero_actions.addWidget(self.likes_play_all_button)
        hero_actions.addWidget(self.likes_shuffle_all_button)
        hero_actions.addStretch(1)
        heading_text.addLayout(hero_actions)
        hero_layout.addLayout(heading_text, 1)

        right_controls = QVBoxLayout()
        right_controls.setContentsMargins(0, 0, 0, 0)
        right_controls.setSpacing(8)
        top_badges = QHBoxLayout()
        top_badges.setSpacing(8)
        self.connection_badge = QLabel("● Локально")
        self.connection_badge.setObjectName("connectionBadge")
        top_badges.addWidget(self.connection_badge)
        self.sync_account_button = QPushButton("⟳  YouTube")
        self.sync_account_button.setObjectName("filterButton")
        self.sync_account_button.setToolTip("Синхронизировать лайки YouTube Music")
        top_badges.addWidget(self.sync_account_button)
        self.likes_settings_button = QPushButton("⚙")
        self.likes_settings_button.setObjectName("themeButton")
        self.likes_settings_button.setFixedSize(38, 38)
        self.likes_settings_button.setToolTip("Подключения и синхронизация")
        self.likes_settings_button.setAccessibleName("Настройки подключений")
        self.likes_settings_menu = QMenu(self)
        self.likes_settings_menu.setObjectName("darkMenu")
        self.likes_settings_button.setMenu(self.likes_settings_menu)
        top_badges.addWidget(self.likes_settings_button)
        right_controls.addLayout(top_badges)
        right_controls.addStretch(1)
        hero_layout.addLayout(right_controls)
        likes.addWidget(self.likes_hero_header)

        account_card = QFrame()
        account_card.setObjectName("likesAccountCard")
        account_card.setFixedWidth(360)
        account_layout = QVBoxLayout(account_card)
        account_layout.setContentsMargins(16, 14, 16, 14)
        account_layout.setSpacing(12)
        account_heading = QLabel("Подключения")
        account_heading.setObjectName("sectionTitle")
        account_layout.addWidget(account_heading)
        self.likes_account_title = QLabel("YouTube Music")
        self.likes_account_title.setObjectName("trackTitle")
        self.likes_account_status = QLabel("Аккаунт не подключён")
        self.likes_account_status.setObjectName("mutedText")
        self.likes_account_status.setWordWrap(True)
        account_layout.addWidget(self.likes_account_title)
        account_layout.addWidget(self.likes_account_status)
        self.connect_account_button = QPushButton("Подключить YouTube Music")
        self.connect_account_button.setObjectName("filterButton")
        account_layout.addWidget(self.connect_account_button)
        self.soundcloud_account_status = QLabel("SoundCloud: аккаунт не подключён")
        self.soundcloud_account_status.setObjectName("mutedText")
        self.soundcloud_account_status.setWordWrap(True)
        account_layout.addWidget(self.soundcloud_account_status)
        self.connect_soundcloud_button = QPushButton("Подключить SoundCloud")
        self.connect_soundcloud_button.setObjectName("filterButton")
        account_layout.addWidget(self.connect_soundcloud_button)
        self.disconnect_account_button = QPushButton("Отключить YouTube Music")
        self.disconnect_account_button.setObjectName("textButton")
        account_layout.addWidget(self.disconnect_account_button)
        for button in (self.connect_account_button, self.connect_soundcloud_button, self.disconnect_account_button):
            button.clicked.connect(self.likes_settings_menu.close)
        account_action = QWidgetAction(self.likes_settings_menu)
        account_action.setDefaultWidget(account_card)
        self.likes_settings_menu.addAction(account_action)

        self.likes_search_input = QLineEdit()
        self.likes_search_input.setPlaceholderText("Поиск по любимым трекам")
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
            list_widget.setUniformItemSizes(True)
            list_widget.setSpacing(2)
            list_widget.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
            list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            list_widget.viewport().installEventFilter(self)
            list_widget.customContextMenuRequested.connect(
                lambda point, lw=list_widget: self.open_likes_menu(point, lw)
            )
        self.likes_tabs.addTab(self.youtube_likes_list, "YouTube Music · 0")
        self.likes_tabs.addTab(self.soundcloud_likes_list, "SoundCloud · 0")
        self.likes_tabs.addTab(self.likes_list, "Мои лайки · 0")
        self.likes_tabs.currentChanged.connect(self._update_likes_collage)
        likes.addWidget(self.likes_tabs, 1)
        self.view_stack.addWidget(self.likes_page)

        # Страница локального пользовательского плейлиста (с поддержкой папок, Drag & Drop и экспорта/импорта).
        self.playlist_page = QWidget()
        pl_layout = QVBoxLayout(self.playlist_page)
        pl_layout.setContentsMargins(6, 6, 6, 6)
        pl_layout.setSpacing(12)

        self.playlist_header = QFrame(self.playlist_page)
        self.playlist_header.setObjectName("artistHeader")
        self.playlist_header.setMinimumHeight(184)
        self.playlist_header.setMaximumHeight(214)
        pl_header_layout = QHBoxLayout(self.playlist_header)
        pl_header_layout.setContentsMargins(22, 14, 22, 14)
        pl_header_layout.setSpacing(22)

        self.playlist_cover_label = QLabel(self.playlist_header)
        self.playlist_cover_label.setObjectName("rowCover")
        self.playlist_cover_label.setFixedSize(124, 124)
        self.playlist_cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pl_header_layout.addWidget(self.playlist_cover_label, 0, Qt.AlignmentFlag.AlignVCenter)

        pl_text = QVBoxLayout()
        pl_text.setContentsMargins(0, 0, 0, 0)
        pl_text.setSpacing(3)
        self.playlist_folder_badge = QLabel("ЛОКАЛЬНЫЙ ПЛЕЙЛИСТ")
        self.playlist_folder_badge.setObjectName("artistVerified")
        pl_text.addWidget(self.playlist_folder_badge)

        self.playlist_title_button = QPushButton("Мой плейлист")
        self.playlist_title_button.setObjectName("artistNameLink")
        self.playlist_title_button.setFlat(True)
        self.playlist_title_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.playlist_title_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.playlist_title_button.setToolTip("Нажми, чтобы переименовать плейлист или сменить папку")
        self.playlist_title_button.setMinimumHeight(38)
        self.playlist_title_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.playlist_title_button.clicked.connect(lambda checked=False: self.edit_active_user_playlist())
        pl_text.addWidget(self.playlist_title_button)

        self.playlist_meta_label = QLabel("0 треков · Перетаскивай треки мышкой для сортировки")
        self.playlist_meta_label.setObjectName("artistMeta")
        pl_text.addWidget(self.playlist_meta_label)

        pl_actions = QHBoxLayout()
        pl_actions.setContentsMargins(0, 5, 0, 0)
        pl_actions.setSpacing(8)
        self.playlist_play_button = QPushButton("Слушать")
        self.playlist_play_button.setObjectName("artistShuffleButton")
        self.playlist_play_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.playlist_play_button.setIcon(control_icon("play", "#101010", 18))
        self.playlist_play_button.setIconSize(QSize(16, 16))
        self.playlist_play_button.setMinimumHeight(32)
        self.playlist_play_button.clicked.connect(lambda checked=False: self.play_active_user_playlist(shuffle=False))

        self.playlist_shuffle_button = QPushButton("Перемешать")
        self.playlist_shuffle_button.setObjectName("artistMixButton")
        self.playlist_shuffle_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.playlist_shuffle_button.setMinimumHeight(32)
        self.playlist_shuffle_button.clicked.connect(lambda checked=False: self.play_active_user_playlist(shuffle=True))

        self.playlist_add_queue_button = QPushButton("＋ Из очереди")
        self.playlist_add_queue_button.setObjectName("artistMixButton")
        self.playlist_add_queue_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.playlist_add_queue_button.setMinimumHeight(32)
        self.playlist_add_queue_button.setToolTip("Добавить треки из текущей очереди в этот плейлист")
        self.playlist_add_queue_button.clicked.connect(lambda checked=False: self.add_current_queue_to_active_playlist())

        self.playlist_export_button = QPushButton("Экспорт…")
        self.playlist_export_button.setObjectName("artistMixButton")
        self.playlist_export_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.playlist_export_button.setMinimumHeight(32)
        self.playlist_export_button.setToolTip("Экспортировать плейлист в файл (.json или .m3u8)")
        self.playlist_export_button.clicked.connect(lambda checked=False: self.export_user_playlist(self.active_user_playlist_id))

        self.playlist_import_button = QPushButton("Импорт…")
        self.playlist_import_button.setObjectName("artistMixButton")
        self.playlist_import_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.playlist_import_button.setMinimumHeight(32)
        self.playlist_import_button.setToolTip("Импортировать треки из файла (.json, .m3u, .m3u8)")
        self.playlist_import_button.clicked.connect(
            lambda checked=False: self.import_user_playlist_from_file(target_playlist_id=self.active_user_playlist_id)
        )

        self.playlist_edit_button = QPushButton("Папка / Имя")
        self.playlist_edit_button.setObjectName("artistMixButton")
        self.playlist_edit_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.playlist_edit_button.setMinimumHeight(32)
        self.playlist_edit_button.clicked.connect(lambda checked=False: self.edit_active_user_playlist())

        self.playlist_delete_button = QPushButton("Удалить")
        self.playlist_delete_button.setObjectName("textButton")
        self.playlist_delete_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.playlist_delete_button.clicked.connect(lambda checked=False: self.delete_user_playlist(self.active_user_playlist_id))

        for btn in (
            self.playlist_play_button,
            self.playlist_shuffle_button,
            self.playlist_add_queue_button,
            self.playlist_export_button,
            self.playlist_import_button,
            self.playlist_edit_button,
            self.playlist_delete_button,
        ):
            pl_actions.addWidget(btn, 0)
        pl_actions.addStretch(1)
        pl_text.addLayout(pl_actions)
        pl_header_layout.addLayout(pl_text, 1)
        pl_layout.addWidget(self.playlist_header)

        self.playlist_search_input = QLineEdit(self.playlist_page)
        self.playlist_search_input.setPlaceholderText("Поиск внутри плейлиста (или перетащи сюда треки и файлы .json/.m3u8)")
        self.playlist_search_input.setClearButtonEnabled(True)
        self.playlist_search_input.setMinimumHeight(38)
        self.playlist_search_input.textChanged.connect(self.on_playlist_search_changed)
        pl_layout.addWidget(self.playlist_search_input)

        self.user_playlist_empty = QLabel(
            "Плейлист пока пуст.\nПеретащите сюда треки мышкой из поиска, лайков или очереди, "
            "добавьте через правый клик по треку («Добавить в плейлист») или импортируйте из файла.",
            self.playlist_page,
        )
        self.user_playlist_empty.setObjectName("recentEmpty")
        self.user_playlist_empty.setWordWrap(True)
        self.user_playlist_empty.setMinimumHeight(86)
        self.user_playlist_empty.hide()
        pl_layout.addWidget(self.user_playlist_empty)

        self.user_playlist_list = DroppableTrackListWidget("playlist", self.playlist_page)
        self.user_playlist_list.setObjectName("trackList")
        self.user_playlist_list.setSpacing(2)
        self.user_playlist_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.user_playlist_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.user_playlist_list.viewport().installEventFilter(self)
        self.user_playlist_list.customContextMenuRequested.connect(self.open_user_playlist_track_menu)
        self.user_playlist_list.track_dropped_at.connect(self.on_user_playlist_track_dropped)
        self.user_playlist_list.files_dropped.connect(self.on_user_playlist_files_dropped)
        pl_layout.addWidget(self.user_playlist_list, 1)
        self.view_stack.addWidget(self.playlist_page)

        self.create_cover_page()
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
        header.addWidget(self.queue_heading)
        header.addStretch(1)
        header.addWidget(self.clear_queue_button)
        header.addWidget(self.queue_toggle)
        layout.addLayout(header)

        queue_meta_row = QHBoxLayout()
        queue_meta_row.setContentsMargins(0, 0, 0, 0)
        queue_meta_row.setSpacing(6)
        self.queue_count = QLabel("0 треков")
        self.queue_count.setObjectName("mutedText")
        self.queue_source_badge = QLabel("Очередь")
        self.queue_source_badge.setObjectName("queueSourceBadge")
        queue_meta_row.addWidget(self.queue_count)
        queue_meta_row.addStretch(1)
        queue_meta_row.addWidget(self.queue_source_badge)
        layout.addLayout(queue_meta_row)
        self.queue_list = DroppableTrackListWidget("queue")
        self.queue_list.setObjectName("queueList")
        self.queue_list.setSpacing(2)
        self.queue_list.setUniformItemSizes(True)
        self.queue_list.viewport().installEventFilter(self)
        self.queue_list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.queue_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.queue_list.track_dropped_at.connect(self.on_queue_track_dropped)
        self.queue_list.files_dropped.connect(self.on_queue_files_dropped)
        layout.addWidget(self.queue_list, 1)
        self.queue_hint = QLabel("Правый клик — порядок и удаление · × — закрыть")
        self.queue_hint.setObjectName("mutedText")
        self.queue_hint.hide()
        self.queue_list.setToolTip("Перетаскивай треки мышкой или нажми ПКМ, чтобы изменить порядок")
        return self.queue_panel

    def create_cover_page(self):
        self.cover_page = CoverPopupPage()
        self.cover_page.setObjectName("coverPage")
        self.cover_page.close_requested.connect(self.close_cover_view)
        self.cover_back_button = QPushButton("×", self.cover_page)
        self.cover_back_button.setObjectName("coverCloseButton")
        self.cover_back_button.hide()
        self.cover_back_button.clicked.connect(self.close_cover_view)
        self.expanded_title = QLabel("", self.cover_page)
        self.expanded_title.setObjectName("expandedTitle")
        self.expanded_title.setTextFormat(Qt.TextFormat.PlainText)
        self.expanded_title.hide()
        self.expanded_artist = QPushButton("", self.cover_page)
        self.expanded_artist.setObjectName("expandedArtist")
        self.expanded_artist.setFlat(True)
        self.expanded_artist.hide()
        self.expanded_artist.clicked.connect(self.open_current_artist)
        self.expanded_cover = ExpandedArtwork(self)
        self.expanded_cover.setObjectName("expandedCover")
        self.expanded_cover.hide()
        self.expanded_cover.clicked.connect(self.close_cover_view)
        self._cover_expand_progress = 1.0
        self._cover_expand_anim = QVariantAnimation(self)
        self._cover_expand_anim.setDuration(210)
        self._cover_expand_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._cover_expand_anim.valueChanged.connect(self._on_cover_expand_progress)
        self._cover_return_page = None
        self.view_stack.addWidget(self.cover_page)

    def _on_cover_expand_progress(self, value):
        self._cover_expand_progress = float(value)
        self._position_expanded_cover()

    def _position_expanded_cover(self):
        if not hasattr(self, "expanded_cover") or not self.expanded_cover.isVisible():
            return
        target_size = self.expanded_cover.target_size()
        target_w = float(target_size.width())
        target_h = float(target_size.height())
        if hasattr(self, "bottom_cover") and hasattr(self, "player_bar"):
            origin = self.bottom_cover.mapTo(self, QPoint(0, 0))
            start_x = float(origin.x())
            start_y = float(origin.y())
            start_w = float(max(48, self.bottom_cover.width()))
            start_h = float(max(48, self.bottom_cover.height()))
            bar_top = float(self.player_bar.mapTo(self, QPoint(0, 0)).y())
            end_x = max(10.0, start_x - 6.0)
            end_y = max(10.0, bar_top - target_h - 4.0)
        else:
            start_x, start_y, start_w, start_h = 18.0, float(max(60, self.height() - 80)), 56.0, 56.0
            end_x, end_y = 14.0, max(10.0, float(self.height()) - target_h - 96.0)
        t = getattr(self, "_cover_expand_progress", 1.0)
        x = round(start_x + (end_x - start_x) * t)
        y = round(start_y + (end_y - start_y) * t)
        w = round(start_w + (target_w - start_w) * t)
        h = round(start_h + (target_h - start_h) * t)
        self.expanded_cover.setGeometry(x, y, max(48, w), max(48, h))
        self.expanded_cover.raise_()

    @staticmethod
    def artist_card_name(track):
        if not isinstance(track, dict) or track.get("source") not in ("youtube", "soundcloud"):
            return ""
        if track.get("source") == "youtube":
            credits = track.get("artist_metadata") or []
            if isinstance(credits, str):
                credits = [credits]
            name = track.get("profile_artist_name") or (credits[0] if credits else track.get("artist"))
        else:
            name = track.get("artist")
        name = str(name or "").strip()
        return "" if name.casefold() in ("исполнитель неизвестен", "unknown artist") else name

    def refresh_current_track_views(self):
        if self._force_exit or not hasattr(self, "expanded_artist"):
            return
        track = self.current_track or {}
        available = bool(track.get("url"))
        name = self.artist_card_name(track)
        display = str(track.get("artist_display") or track.get("artist") or name or "")
        self.bottom_cover.setEnabled(available)
        self.bottom_cover.setCursor(Qt.CursorShape.PointingHandCursor if available else Qt.CursorShape.ArrowCursor)
        for button in (self.bottom_artist, self.expanded_artist):
            button.setEnabled(bool(name))
            button.setCursor(Qt.CursorShape.PointingHandCursor if name else Qt.CursorShape.ArrowCursor)
            max_w = max(215, self.bottom_artist.maximumWidth()) if button is self.bottom_artist else max(40, button.width() - 8)
            button.setText(button.fontMetrics().elidedText(display, Qt.TextElideMode.ElideRight, max_w))
            button.setToolTip(f"Открыть исполнителя: {name}" if name else display)
            button.setAccessibleName(f"Открыть исполнителя: {name}" if name else display)
        if self.view_stack.currentWidget() is self.cover_page:
            if not available:
                self.close_cover_view()
                return
            self.expanded_title.setText(str(track.get("title") or "Без названия"))
            self.expanded_title.setToolTip(self.expanded_title.text())
            url = normalize_artwork_url(track.get("thumbnail", ""))
            if self.expanded_cover.property("requested_image") != url:
                self.request_image(url, self.expanded_cover)
            self._position_expanded_cover()

    def toggle_cover_view(self):
        if self.view_stack.currentWidget() is self.cover_page:
            self.close_cover_view()
            return
        if not self.current_track or not self.current_track.get("url"):
            return
        self._cover_return_page = self.view_stack.currentWidget()
        # Никаких новых окон или перекрытия экрана: просто расширяется фото обложки внизу.
        self.fade_to_page(self.cover_page)
        self.refresh_current_track_views()
        self._cover_expand_anim.stop()
        self._cover_expand_progress = 0.0
        self.expanded_cover.show()
        self.expanded_cover.sync_vinyl_state()
        self._position_expanded_cover()
        self._cover_expand_anim.setStartValue(0.0)
        self._cover_expand_anim.setEndValue(1.0)
        self._cover_expand_anim.start()

    def close_cover_view(self):
        if self.view_stack.currentWidget() is self.cover_page:
            self._cover_expand_anim.stop()
            self.expanded_cover.hide()
            self.expanded_cover.clear_artwork()
            self.expanded_cover.sync_vinyl_state()
            page = self._cover_return_page
            if page not in (self.browse_page, self.likes_page, getattr(self, "playlist_page", None)):
                page = self.last_library_page
            self.fade_to_page(page)

    def open_current_artist(self):
        track = self.current_track
        if not self.artist_card_name(track):
            return
        self.search_artist_name(dict(track), track.get("source"))
        self.last_library_page = self.browse_page
        if self.view_stack.currentWidget() is not self.browse_page:
            self.fade_to_page(self.browse_page)

    def create_bottom_bar(self):
        """Нижняя панель в стиле Spotify: слева трек и сердечко рядом с текстом, по центру транспорт + таймлайн, справа громкость и очередь."""
        bar = PlayerBar()
        self.player_bar = bar
        bar.setObjectName("playerBar")
        base = QHBoxLayout(bar)
        base.setContentsMargins(16, 10, 16, 10)
        base.setSpacing(0)

        # 1. Левая колонка: Обложка + (Название / Исполнитель) + Сердечко сразу рядом с текстом.
        track_info = QWidget()
        self.bottom_track_info = track_info
        track_info.setFixedWidth(360)
        info = QHBoxLayout(track_info)
        info.setContentsMargins(0, 0, 0, 0)
        info.setSpacing(12)
        self.bottom_cover = ClickableLabel()
        self.bottom_cover.setEnabled(False)
        self.bottom_cover.setToolTip("Открыть крупную обложку")
        self.bottom_cover.setAccessibleName("Открыть крупную обложку текущего трека")
        self.bottom_cover.clicked.connect(self.toggle_cover_view)
        self.bottom_cover.setObjectName("bottomCover")
        self.bottom_cover.setFixedSize(56, 56)
        cover_shadow = QGraphicsDropShadowEffect(self.bottom_cover)
        cover_shadow.setBlurRadius(16)
        cover_shadow.setOffset(0, 2)
        cover_shadow.setColor(QColor(0, 0, 0, 100))
        self.bottom_cover.setGraphicsEffect(cover_shadow)
        info.addWidget(self.bottom_cover)

        labels_box = QWidget(track_info)
        self.bottom_labels_box = labels_box
        labels_box.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        labels_box.setMaximumWidth(244)
        labels = QVBoxLayout(labels_box)
        labels.setContentsMargins(0, 2, 0, 2)
        labels.setSpacing(2)
        self.bottom_title = MarqueeLabel("Ничего не играет", labels_box)
        self.bottom_title.setObjectName("bottomTitle")
        self.bottom_title.setToolTip("Текущий трек")
        self.bottom_artist = QPushButton("", labels_box)
        self.bottom_artist.setObjectName("bottomArtistLink")
        self.bottom_artist.setFlat(True)
        self.bottom_artist.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        self.bottom_artist.setMaximumWidth(238)
        self.bottom_artist.clicked.connect(self.open_current_artist)
        labels.addWidget(self.bottom_title)
        labels.addWidget(self.bottom_artist)
        info.addWidget(labels_box, 0, Qt.AlignmentFlag.AlignVCenter)

        self.bottom_favorite_button = QPushButton()
        self.bottom_favorite_button.setObjectName("bottomFavorite")
        self.bottom_favorite_button.setIcon(control_icon("heart-outline", "#B3B3B3", 22))
        self.bottom_favorite_button.setIconSize(QSize(20, 20))
        self.bottom_favorite_button.setFixedSize(32, 32)
        self.bottom_favorite_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bottom_favorite_button.setCheckable(True)
        self.bottom_favorite_button.setEnabled(False)
        self.bottom_favorite_button.setToolTip("Добавить в локальные лайки")
        info.addWidget(self.bottom_favorite_button, 0, Qt.AlignmentFlag.AlignVCenter)
        info.addStretch(1)

        self.bottom_dislike_button = QPushButton()
        self.bottom_dislike_button.setObjectName("bottomDislike")
        self.bottom_dislike_button.setIcon(control_icon("thumb-down-outline", "#B3B3B3", 22))
        self.bottom_dislike_button.setIconSize(QSize(20, 20))
        self.bottom_dislike_button.setFixedSize(30, 30)
        self.bottom_dislike_button.setCheckable(True)
        self.bottom_dislike_button.setEnabled(False)
        self.bottom_dislike_button.setToolTip("Не показывать этот трек в будущих миксах и радио")
        self.bottom_dislike_button.setParent(bar)
        self.bottom_dislike_button.hide()
        base.addWidget(track_info, 0, Qt.AlignmentFlag.AlignVCenter)
        base.addStretch(1)

        def tool_button(name, tooltip, object_name="transportButton", icon_color="#CEC3CC"):
            button = QPushButton()
            button.setObjectName(object_name)
            button.setIcon(control_icon(name, icon_color))
            button.setIconSize(QSize(22, 22))
            button.setFixedSize(36, 36)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setToolTip(tooltip)
            return button

        # 2. Центральная колонка Spotify: сверху 5 кнопок транспорта, прямо под ними компактный таймлайн.
        central_controls = QWidget()
        central_controls.setMinimumWidth(420)
        central_controls.setMaximumWidth(600)
        central_controls.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        center_stack = QVBoxLayout(central_controls)
        center_stack.setContentsMargins(0, 0, 0, 0)
        center_stack.setSpacing(4)

        center_row = QHBoxLayout()
        center_row.setContentsMargins(0, 0, 0, 0)
        center_row.setSpacing(10)
        center_row.addStretch(1)
        self.shuffle_button = tool_button("shuffle", "Перемешивание: выкл.")
        self.shuffle_button.setCheckable(True)
        self.previous_button = tool_button("previous", "Предыдущий трек")
        self.play_button = tool_button("play", "Воспроизведение / пауза", "playButton", "#FFFFFF")
        self.play_button.setFixedSize(42, 42)
        self.play_button.setIconSize(QSize(24, 24))
        self.next_button = tool_button("next", "Следующий трек")
        self.repeat_button = tool_button("repeat", "Повтор: выкл.")
        self.repeat_button.setCheckable(True)
        self.stop_button = tool_button("stop", "Остановить")
        for button in (
            self.shuffle_button, self.previous_button, self.play_button,
            self.next_button, self.repeat_button,
        ):
            center_row.addWidget(button)
        center_row.addStretch(1)
        self.stop_button.setParent(bar)
        self.stop_button.hide()
        center_stack.addLayout(center_row)

        timeline = QHBoxLayout()
        timeline.setContentsMargins(0, 0, 0, 0)
        timeline.setSpacing(8)
        self.position_label = QLabel("0:00")
        self.position_label.setObjectName("timeText")
        self.position_label.setMinimumWidth(32)
        self.position_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.seek_slider = ClickSlider(Qt.Orientation.Horizontal)
        self.seek_slider.setObjectName("seekSlider")
        self.seek_slider.setFixedHeight(16)
        self.seek_slider.setRange(0, 0)
        self.seek_slider.setEnabled(False)
        self.seek_slider.setToolTip("Нажми в любую точку для перемотки")
        self.duration_label = QLabel("0:00")
        self.duration_label.setObjectName("timeText")
        self.duration_label.setMinimumWidth(32)
        self.duration_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        timeline.addWidget(self.position_label)
        timeline.addWidget(self.seek_slider, 1)
        timeline.addWidget(self.duration_label)
        center_stack.addLayout(timeline)
        base.addWidget(central_controls, 1, Qt.AlignmentFlag.AlignVCenter)
        base.addStretch(1)

        # 3. Правая колонка Spotify: Мини-плеер + Очередь + Громкость + Меню.
        right_tools = QWidget()
        self.bottom_right_tools = right_tools
        right_tools.setFixedWidth(360)
        right_row = QHBoxLayout(right_tools)
        right_row.setContentsMargins(0, 0, 0, 0)
        right_row.setSpacing(6)
        right_row.addStretch(1)
        self.bottom_mini_button = tool_button("mini", "Мини-плеер поверх окон (Ctrl+M)")
        self.bottom_mini_button.clicked.connect(self.show_mini_player)
        self.bottom_queue_button = tool_button("queue", "Показать / скрыть очередь")
        volume_icon = QLabel()
        self.volume_icon = volume_icon
        volume_icon.setPixmap(control_icon("volume", "#C7BDC7").pixmap(18, 18))
        self.volume_slider = ClickSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(int(round(self.volume * 100)))
        self.volume_slider.setFixedWidth(96)
        self.volume_value_label = QLabel(f"{int(round(self.volume * 100))}%")
        self.volume_value_label.setObjectName("timeText")
        self.volume_value_label.setFixedWidth(32)
        self.volume_value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.menu_button = tool_button("menu", "Действия с треком и настройки")
        self.menu_button.setIcon(QIcon())
        self.menu_button.setText("⋯")
        right_row.addWidget(self.bottom_mini_button)
        right_row.addWidget(self.bottom_queue_button)
        right_row.addSpacing(2)
        right_row.addWidget(volume_icon)
        right_row.addWidget(self.volume_slider)
        right_row.addWidget(self.volume_value_label)
        right_row.addSpacing(2)
        right_row.addWidget(self.menu_button)
        base.addWidget(right_tools, 0, Qt.AlignmentFlag.AlignVCenter)

        self.options_menu = QMenu(self)
        self.options_menu.setObjectName("darkMenu")
        self.stop_action = self.options_menu.addAction("Остановить воспроизведение", self.stop_all)
        self.dislike_action = self.options_menu.addAction("Не рекомендовать этот трек")
        self.dislike_action.setEnabled(False)
        self.dislike_action.triggered.connect(self.dislike_current_track)
        self.options_menu.addSeparator()
        self.mini_player_action = self.options_menu.addAction("Мини-плеер поверх окон   Ctrl+M", self.show_mini_player)
        self.options_menu.addAction("Настройки…", self.open_settings)
        self.update_app_action = self.options_menu.addAction(
            f"Проверить обновления (v{APP_VERSION})…", self.on_update_button_clicked
        )
        self.options_menu.addAction("О программе", self.show_about)
        updates = self.options_menu.addMenu("Готовые версии на GitHub")
        updates.addAction("Проверить и установить обновление…", self.on_update_button_clicked)
        updates.addAction("Скачать готовый .exe (Releases)", lambda: QDesktopServices.openUrl(
            QUrl(f"https://github.com/{GITHUB_REPO}/releases/latest")))
        updates.addAction("Последние сборки (GitHub Actions)", lambda: QDesktopServices.openUrl(
            QUrl(f"https://github.com/{GITHUB_REPO}/actions/workflows/windows-build.yml")))
        updates.addAction("Все релизы", lambda: QDesktopServices.openUrl(
            QUrl(f"https://github.com/{GITHUB_REPO}/releases")))
        self.options_menu.addSeparator()
        self.options_menu.addAction("Выход", self.request_app_exit)
        self.menu_button.setMenu(self.options_menu)
        return bar

    # ---------------------------------------------------------
    # Единая палитра; семейство шрифта берётся из QApplication.font().
    # Все QLabel прозрачные: никаких тёмных полос за надписями.
    # ---------------------------------------------------------

    def apply_styles(self):
        """Aurora Slate & Emerald palette: cohesive dark/light surfaces and glassmorphic wallpaper support."""
        dark_styles = r"""
            QMainWindow, QWidget#root { background: #0B0D10; }
            QWidget { color: #F2F5F9; font-size: 14px; }
            QLabel { background: transparent; border: none; }

            QFrame#sidebar, QFrame#queuePanel {
                background: #11141A;
                border: 1px solid #1C222B;
                border-radius: 15px;
            }
            QFrame#centerPanel {
                background: #151921;
                border: 1px solid #1F2631;
                border-radius: 15px;
            }
            QFrame#playerBar {
                background: #161B23;
                border: 1px solid #252D3A;
                border-radius: 15px;
            }

            QLabel#bottomCover, QLabel#rowCover { background: #202631; border-radius: 8px; }
            QLabel#bottomArtist, QLabel#mutedText, QLabel#trackArtist, QLabel#statusText,
            QLabel#durationText, QLabel#sourceText, QLabel#artistMeta { color: #9DA8B8; font-size: 12px; }
            QLabel#bottomTitle, QLabel#pageTitle, QLabel#trackTitle, QLabel#queueTitle { color: #F7F9FC; font-weight: 700; }

            QLabel#pageTitle { font-size: 27px; font-weight: 800; letter-spacing: -0.5px; }
            QLabel#sectionTitle { font-size: 18px; font-weight: 700; color: #F4F7FA; }
            QLabel#queueTitle { font-size: 17px; font-weight: 700; }
            QLabel#bottomTitle { font-size: 15px; font-weight: 700; }
            QLabel#trackTitle { font-size: 14px; font-weight: 600; }
            QLabel#eyebrow { color: #8290A2; font-size: 10px; font-weight: 700; letter-spacing: 1.2px; }
            QLabel#timeText { color: #9DA8B8; font-size: 11px; }
            QLabel#trackIndex, QLabel#tableHeaderText { color: #8C98AA; font-size: 9.5pt; }
            QLabel#recentEmpty {
                color: #9DA8B8; font-size: 13px; padding: 18px;
                background: #1A2029; border: 1px solid #252E3B; border-radius: 13px;
            }
            QLabel#connectionBadge { color: #9DA8B8; font-size: 11px; padding: 6px; }
            QLabel#connectionBadge[connected="true"] { color: #66E099; }

            QFrame#likesHeroHeader {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 rgba(27, 68, 52, 168), stop:0.55 rgba(23, 33, 45, 178), stop:1 rgba(18, 23, 31, 186));
                border: 1px solid rgba(92, 224, 146, 48);
                border-radius: 16px;
            }
            QLabel#trackSourceBadge {
                background: rgba(255, 255, 255, 15); color: #9DA8B8;
                border: 1px solid rgba(255, 255, 255, 18);
                border-radius: 6px; padding: 1px 5px; font-size: 9px; font-weight: 800; letter-spacing: 0.4px;
            }
            QLabel#trackSourceBadge[sourceKind="YT"] {
                background: rgba(255, 62, 85, 28); color: #FF8A98; border-color: rgba(255, 92, 112, 54);
            }
            QLabel#trackSourceBadge[sourceKind="SC"] {
                background: rgba(255, 115, 36, 30); color: #FFA26B; border-color: rgba(255, 136, 68, 58);
            }
            QLabel#trackSourceBadge[sourceKind="OK"] {
                background: rgba(29, 185, 84, 34); color: #66E099; border-color: rgba(92, 224, 146, 68);
            }
            QLabel#queueSourceBadge {
                background: rgba(29, 185, 84, 28); color: #66E099;
                border: 1px solid rgba(92, 224, 146, 52);
                border-radius: 9px; padding: 2px 8px; font-size: 10px; font-weight: 700;
            }

            QFrame#artistHeader {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #1E2938, stop:1 #161B23);
                border: 1px solid #283241;
                border-radius: 16px;
            }
            QLabel#artistAvatar { background: #222936; border-radius: 62px; }
            QLabel#artistVerified { color: #5CE092; font-size: 9pt; font-weight: 800; letter-spacing: 1px; }
            QPushButton#artistNameLink {
                color: #FFFFFF; background: transparent; border: none;
                text-align: left; padding: 0; margin: 0; font-size: 27pt; font-weight: 800;
            }
            QPushButton#artistNameLink:hover { color: #66E099; background: transparent; }
            QLabel#artistPopular { color: #F4F7FA; font-size: 11pt; font-weight: 700; }

            QPushButton#artistShuffleButton {
                background: #1DB954; color: #0C1810; border: none;
                border-radius: 17px; padding: 6px 16px; font-weight: 800; min-height: 30px;
            }
            QPushButton#artistShuffleButton:hover { background: #34DC70; }
            QPushButton#artistMixButton {
                background: #1E2531; color: #F2F5F9; border: 1px solid #323D4E;
                border-radius: 17px; padding: 6px 16px; font-weight: 700; min-height: 30px;
            }
            QPushButton#artistMixButton:hover { background: #263040; border-color: #5CE092; color: #66E099; }

            QFrame#tableHeader { background: transparent; border-bottom: 1px solid #232B37; }
            QFrame#likesAccountCard { background: #1B212B; border: 1px solid #27303E; border-radius: 12px; }
            QLabel#likesAccountIcon {
                color: #5CE092; background: #182E23; border: 1px solid #2A523D;
                border-radius: 12px; font-size: 24px; font-weight: 800;
            }

            QScrollArea#startCardsScroll,
            QScrollArea#startCardsScroll QWidget#qt_scrollarea_viewport,
            QWidget#startCardsWidget { background: #151921; border: none; }
            QScrollBar:vertical { background: transparent; width: 5px; margin: 4px 1px; border: none; }
            QScrollBar::handle:vertical { background: rgba(157, 168, 184, 68); min-height: 28px; border-radius: 2.5px; }
            QScrollBar::handle:vertical:hover { background: #5CE092; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; height: 0px; }

            QLabel#startSectionTitle { color: #FFFFFF; font-size: 17pt; font-weight: 800; padding: 2px 0; }
            QPushButton#addPlaylistCard {
                background: #181E27; color: #9DA8B8; border: 1px dashed #3A4454;
                border-radius: 14px; font-size: 13pt; font-weight: 700; padding: 18px;
            }
            QPushButton#addPlaylistCard:hover {
                background: #1F2733; color: #FFFFFF; border: 1px dashed #5CE092;
            }

            QPushButton { background: transparent; color: #F2F5F9; border: none; border-radius: 9px; padding: 7px 10px; }
            QPushButton:hover { background: #202733; }
            QPushButton#navButton { color: #9DA8B8; text-align: left; padding: 0; border: none; background: transparent; }
            QPushButton#sidebarSettings { color: #A2AEBF; text-align: left; padding: 12px 10px; border-radius: 10px; font-weight: 600; }
            QPushButton#sidebarSettings:hover { background: #1B222C; color: #FFFFFF; }
            QPushButton#sidebarUpdate {
                color: #9DA8B8; background: rgba(255, 255, 255, 6); border: 1px solid #232C39;
                text-align: left; padding: 10px 12px; border-radius: 10px; font-weight: 600; font-size: 12.5px;
            }
            QPushButton#sidebarUpdate:hover { background: #1D2834; color: #FFFFFF; border-color: #5CE092; }
            QPushButton#sidebarUpdate[has_update="true"] {
                background: rgba(29, 185, 84, 34); color: #66E099; border: 1px solid #1DB954; font-weight: 800;
            }
            QPushButton#sidebarUpdate[has_update="true"]:hover {
                background: #1DB954; color: #09140D;
            }
            QPushButton#topUpdateButton {
                background: #1DB954; color: #09140D; border: none;
                border-radius: 19px; padding: 6px 14px; font-weight: 800; font-size: 12.5px;
            }
            QPushButton#topUpdateButton:hover { background: #1ED760; }
            QFrame#updateWarningBanner {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(29, 185, 84, 42), stop:1 rgba(25, 34, 46, 210));
                border: 1px solid #1DB954; border-radius: 14px;
            }
            QLabel#updateBannerTitle { color: #F4F9F5; font-size: 13px; font-weight: 700; }
            QPushButton#updateBannerAction {
                background: #1DB954; color: #09140D; border: none;
                border-radius: 15px; padding: 7px 16px; font-weight: 800; font-size: 12.5px;
            }
            QPushButton#updateBannerAction:hover { background: #2FE06D; }
            QPushButton#updateBannerClose {
                background: transparent; color: #9DA8B8; border-radius: 14px; font-size: 16px; font-weight: 700; padding: 0;
            }
            QPushButton#updateBannerClose:hover { background: rgba(255, 255, 255, 22); color: #FFFFFF; }
            QPushButton#iconButton, QPushButton#transportButton {
                background: transparent; color: #C6D0DE; border-radius: 9px; padding: 4px; font-size: 24px;
            }
            QPushButton#iconButton:hover, QPushButton#transportButton:hover { background: #212936; color: #5CE092; }
            QPushButton#transportButton:checked { color: #5CE092; background: #1B2E26; }
            QPushButton#transportButton::menu-indicator, QPushButton#themeButton::menu-indicator { image: none; width: 0; }

            QPushButton#bottomFavorite, QPushButton#bottomDislike { background: transparent; border: none; border-radius: 17px; padding: 0; }
            QPushButton#bottomFavorite:hover, QPushButton#bottomDislike:hover { background: rgba(255, 255, 255, 18); }
            QPushButton#bottomFavorite:checked { background: transparent; }
            QPushButton#bottomFavorite:checked:hover { background: rgba(29, 185, 84, 28); }
            QPushButton#bottomDislike:checked { background: #361F22; }

            QPushButton#playButton { background: #1DB954; color: #FFFFFF; border: none; border-radius: 21px; padding: 0; }
            QPushButton#playButton:hover { background: #1ED760; }
            QPushButton#playButton:pressed { background: #169C46; }

            QPushButton#rowPlay, QPushButton#rowFavorite, QPushButton#rowRemove {
                background: transparent; color: #A2AEBF; border: none; border-radius: 16px;
                font-size: 13px; padding: 2px; font-weight: 700;
            }
            QPushButton#rowPlay[revealed="true"] { background: rgba(255, 255, 255, 16); color: #F2F5F9; }
            QPushButton#rowPlay:hover { background: #1DB954; color: #0D1912; }
            QPushButton#rowFavorite { font-size: 21px; color: #A2AEBF; background: transparent; border-radius: 16px; }
            QPushButton#rowFavorite:checked { color: #5CE092; background: transparent; }
            QPushButton#rowFavorite:hover { background: rgba(255, 255, 255, 18); color: #66E099; }
            QPushButton#rowRemove { background: transparent; color: transparent; border-radius: 14px; }
            QPushButton#rowRemove[revealed="true"], QPushButton#rowRemove:focus { background: rgba(255, 255, 255, 14); color: #F2F5F9; border-radius: 14px; }
            QPushButton#rowRemove:hover { background: rgba(255, 255, 255, 26); color: #FFFFFF; border-radius: 14px; }

            QPushButton#trackArtistLink {
                color: #9DA8B8; background: transparent; border: none;
                text-align: left; padding: 0; margin: 0; font-size: 9pt; font-weight: 500;
            }
            QPushButton#trackArtistLink:hover { color: #FFFFFF; text-decoration: underline; }

            QPushButton#themeButton {
                background: #1C222C; color: #C6D0DE; border: 1px solid #2D3644;
                border-radius: 19px; font-size: 16px; padding: 3px;
            }
            QPushButton#themeButton:hover { background: #262E3B; border-color: #5CE092; color: #FFFFFF; }
            QPushButton#accentButton {
                background: #1DB954; color: #0C1810; border: none;
                border-radius: 10px; padding: 10px 18px; font-weight: 800;
            }
            QPushButton#accentButton:hover { background: #2FE06D; }
            QPushButton#textButton { color: #5CE092; background: transparent; font-size: 9.5pt; font-weight: 600; padding: 5px 8px; }
            QPushButton#textButton:hover { color: #7AE8A8; background: #1E2631; }
            QPushButton#filterButton {
                color: #F2F5F9; background: #1E242E; border: 1px solid #303948;
                border-radius: 10px; padding: 8px 12px; text-align: left;
            }
            QPushButton#filterButton:hover { border: 1px solid #5CE092; background: #252D3A; }
            QPushButton:disabled { background: #1B2029; color: #5D6777; }

            QLineEdit {
                background: #1C222C; color: #FFFFFF; border: 1px solid #303948;
                border-radius: 11px; padding: 10px 14px; selection-background-color: #1DB954;
            }
            QLineEdit:hover, QLineEdit:focus { border: 1px solid #5CE092; background: #212834; }

            QListWidget { background: #151921; color: #F2F5F9; border: none; border-radius: 10px; outline: 0; padding: 2px; }
            QListWidget#queueList { background: transparent; padding: 0; }
            QListWidget::item { background: transparent; border: 1px solid transparent; border-radius: 10px; padding: 0; }
            QListWidget::item:hover, QWidget#trackRow:hover { background: rgba(255, 255, 255, 14); }
            QListWidget::item:selected { background: rgba(29, 185, 84, 24); border: 1px solid rgba(92, 224, 146, 50); }

            QWidget#trackRow { background: transparent; border: 1px solid transparent; border-radius: 9px; }
            QWidget#trackRow[playing="true"] { background: rgba(29, 185, 84, 26); border: 1px solid rgba(92, 224, 146, 52); border-radius: 9px; }
            QWidget#trackRow[playing="true"]:hover { background: rgba(29, 185, 84, 38); border: 1px solid rgba(92, 224, 146, 78); }
            QLabel#trackTitle[playing="true"] { color: #66E099; font-weight: 800; }
            QLabel#trackIndex[playing="true"] { color: #66E099; font-weight: 900; }
            QLabel#queuePlayingBadge { background: transparent; color: transparent; border: none; }

            QSlider::groove:horizontal { background: #36404F; height: 4px; border-radius: 2px; }
            QSlider::sub-page:horizontal { background: #1DB954; border-radius: 2px; }
            QSlider::handle:horizontal { background: #F5F8FC; width: 12px; margin: -4px 0; border-radius: 6px; }
            QSlider::handle:horizontal:hover { background: #1ED760; }
            QSlider:disabled::handle:horizontal { background: #3E4858; }
            QSlider#seekSlider::groove:horizontal { background: #36404F; height: 4px; border-radius: 2px; }
            QSlider#seekSlider::sub-page:horizontal { background: #1DB954; height: 4px; border-radius: 2px; }
            QSlider#seekSlider::handle:horizontal { background: #FFFFFF; width: 10px; margin: -3px 0; border-radius: 5px; }

            QMenu#darkMenu, QMenu {
                background: #1A2029; color: #F4F7FA; border: 1px solid #2E3846;
                padding: 7px; border-radius: 10px;
            }
            QMenu#darkMenu::item, QMenu::item {
                background: transparent; color: #F4F7FA; padding: 10px 22px 10px 14px;
                border: none; margin: 1px; border-radius: 7px;
            }
            QMenu#darkMenu::item:selected, QMenu::item:selected { background: #23372C; color: #66E099; }
            QMenu#darkMenu::separator, QMenu::separator { height: 1px; background: #2B3442; margin: 5px 10px; }

            QTabWidget::pane { border: none; background: transparent; }
            QTabBar::tab {
                background: transparent; color: #9DA8B8; padding: 12px 14px;
                margin-right: 12px; border-radius: 0; border-bottom: 2px solid transparent; font-weight: 600;
            }
            QTabBar::tab:selected { background: transparent; color: #F7F9FC; border-bottom: 2px solid #1DB954; font-weight: 700; }
            QTabBar::tab:hover:!selected { background: #1D2430; color: #FFFFFF; border-radius: 8px; }

            QCheckBox { spacing: 9px; }
            QCheckBox::indicator { width: 17px; height: 17px; }
            QCheckBox::indicator:checked { background: #1DB954; border: 1px solid #1DB954; border-radius: 4px; }
            QCheckBox::indicator:unchecked { background: #1C232E; border: 1px solid #455163; border-radius: 4px; }

            QFrame#radioCard { background: #151A22; border: 1px solid #2E3846; border-radius: 24px; }
            QLabel#radioBrand { color: #5CE092; font-size: 10pt; font-weight: 800; letter-spacing: 2px; }
            QLabel#radioTrackTitle { color: #FFFFFF; font-size: 15pt; font-weight: 800; }
            QLabel#radioStatus { color: #9DA8B8; font-size: 10pt; }

            QPushButton#bottomArtistLink, QPushButton#expandedArtist {
                background: transparent; border: none; padding: 0;
                color: #A2AEBF; font-size: 12px; text-align: left;
            }
            QPushButton#bottomArtistLink:hover:enabled, QPushButton#expandedArtist:hover:enabled {
                color: #FFFFFF; text-decoration: underline;
            }
            QPushButton#expandedArtist { font-size: 14px; text-align: center; padding: 3px 8px; border-radius: 8px; }
            QPushButton#expandedArtist:hover:enabled { background: rgba(255, 255, 255, 14); }
            QLabel#expandedTitle { color: #F7F9FC; font-size: 18px; font-weight: 800; }
            QWidget#coverPage, QLabel#expandedCover { background: transparent; border: none; }
            QFrame#sidebarDivider { background: #222A35; }
            QLabel#sidebarSectionTitle {
                color: #8E9BAE; font-size: 10px; font-weight: 800; letter-spacing: 1px; background: transparent;
            }
            QPushButton#sidebarAddButton {
                background: transparent; color: #9DA8B8; border-radius: 12px; padding: 0; font-size: 15px; font-weight: 700;
            }
            QPushButton#sidebarAddButton:hover { background: #212936; color: #FFFFFF; }
            QScrollArea#sidebarLibraryScroll,
            QScrollArea#sidebarLibraryScroll QWidget#qt_scrollarea_viewport,
            QWidget#sidebarLibraryWidget { background: transparent; border: none; }
            QLabel#sidebarMediaCover { background: transparent; border: none; }
            QFrame#searchBox { background: #1B212B; border: 1px solid #2A3342; border-radius: 24px; }
            QFrame#searchBox[focused="true"] { border-color: #1DB954; background: #202834; }
            QLineEdit#catalogSearch, QLineEdit#catalogSearch:hover, QLineEdit#catalogSearch:focus {
                background: transparent; border: none; padding: 0; color: #F2F6FA; font-size: 14px;
            }
            QLabel#searchShortcut {
                background: #252E3B; color: #A2AEBF; border: 1px solid #354152;
                border-radius: 8px; padding: 4px 7px; font-size: 11px;
            }
            QPushButton#searchSubmit { background: #1DB954; color: #09140D; border-radius: 19px; font-weight: 800; }
            QPushButton#searchSubmit:hover { background: #1ED760; }
            QPushButton#searchSubmit:pressed { background: #43BE76; }
            QPushButton#searchSubmit:disabled { background: #26362E; color: #7E9489; }
            QDialog, QMessageBox { background-color: #151921; color: #F2F5F9; }
            QMessageBox QLabel, QDialog QLabel { background: transparent; color: #F2F5F9; }
            QMessageBox QLabel { min-width: 300px; }
            QMessageBox QPushButton {
                background: #212834; color: #F2F5F9; border: 1px solid #303948;
                border-radius: 9px; padding: 8px 18px; min-width: 82px; font-weight: 600;
            }
            QMessageBox QPushButton:hover {
                background: #2A3444; border-color: #5CE092; color: #FFFFFF;
            }
        """
        light_styles = r"""
            QMainWindow, QWidget#root { background: #E9EDF2; }
            QWidget { color: #18202A; }
            QDialog, QMessageBox { background-color: #F3F6FA; color: #18202A; }
            QMessageBox QLabel { background: transparent; color: #18202A; min-width: 280px; }
            QMessageBox QPushButton {
                background: #E8EEF5; color: #18202A; border: 1px solid #CFD8E3;
                border-radius: 9px; padding: 7px 18px; min-width: 72px;
            }
            QMessageBox QPushButton:hover { background: #E0F2E7; border-color: #21834C; }

            QFrame#sidebar, QFrame#queuePanel, QFrame#centerPanel {
                background: #FFFFFF; border: 1px solid #DCE3EC;
            }
            QFrame#playerBar { background: #FAFCFE; border: 1px solid #D6DEE8; }
            QLabel#bottomCover, QLabel#rowCover { background: #E9EEF4; border-radius: 8px; }

            QFrame#artistHeader {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #EBF3F9, stop:1 #FFFFFF);
                border: 1px solid #D8E1EC;
            }
            QLabel#artistAvatar { background: #E9EEF4; }
            QPushButton#artistShuffleButton {
                background: #1DB954; color: #FFFFFF; border: none;
                border-radius: 17px; padding: 6px 16px; font-weight: 800; min-height: 30px;
            }
            QPushButton#artistShuffleButton:hover { background: #16883D; }
            QPushButton#artistMixButton {
                background: #EEF2F7; color: #18202A; border: 1px solid #D4DCE7;
                border-radius: 17px; padding: 6px 16px; font-weight: 700; min-height: 30px;
            }
            QPushButton#artistMixButton:hover { background: #E1F3E8; border-color: #21834C; color: #167A40; }

            QFrame#tableHeader { border-bottom: 1px solid #E2E8F0; }
            QFrame#likesAccountCard { background: #F4F7FA; border: 1px solid #DCE3EC; }
            QLabel#likesAccountIcon { color: #167A40; background: #E1F3E8; border: 1px solid #B5DFC5; }
            QPushButton#startCard { color: #FFFFFF; }
            QScrollArea#startCardsScroll,
            QScrollArea#startCardsScroll QWidget#qt_scrollarea_viewport,
            QWidget#startCardsWidget, QListWidget { background: #FFFFFF; border: none; }
            QScrollBar:vertical { background: transparent; width: 5px; margin: 4px 1px; border: none; }
            QScrollBar::handle:vertical { background: rgba(100, 114, 133, 78); min-height: 28px; border-radius: 2.5px; }
            QScrollBar::handle:vertical:hover { background: #21834C; }

            QLabel#startSectionTitle, QLabel#sectionTitle, QLabel#pageTitle,
            QLabel#trackTitle, QLabel#bottomTitle, QLabel#queueTitle { color: #141C26; }
            QPushButton#artistNameLink { color: #141C26; }
            QPushButton#artistNameLink:hover { color: #167A40; background: transparent; }
            QLabel#mutedText, QLabel#bottomArtist, QLabel#trackArtist, QLabel#statusText,
            QLabel#durationText, QLabel#sourceText, QLabel#artistMeta, QLabel#timeText { color: #5C697C; }
            QLabel#artistVerified, QLabel#artistPopular { color: #167A40; }
            QLabel#trackIndex, QLabel#tableHeaderText { color: #647285; }
            QLabel#connectionBadge { color: #5C697C; }
            QLabel#connectionBadge[connected="true"] { color: #187941; }
            QLabel#recentEmpty { background: #F2F5F9; border-color: #DCE3EC; color: #5C697C; }

            QPushButton#addPlaylistCard {
                background: #F6F8FB; color: #546275; border: 1px dashed #BDC9D7;
            }
            QPushButton#addPlaylistCard:hover {
                background: #E4F4EA; color: #167A40; border: 1px dashed #21834C;
            }

            QWidget#trackRow[playing="true"] { background: #E3F3E9; border: 1px solid #9FD4B3; border-radius: 10px; }
            QWidget#trackRow[playing="true"]:hover { background: #D8EFE1; border: 1px solid #7BC497; }
            QLabel#trackTitle[playing="true"] { color: #167A40; font-weight: 800; }
            QLabel#trackIndex[playing="true"] { color: #167A40; font-weight: 900; }

            QPushButton#navButton { color: #546275; }
            QPushButton#sidebarSettings { color: #546275; }
            QPushButton#sidebarSettings:hover { background: #EBF0F6; color: #141C26; }
            QPushButton#sidebarUpdate {
                color: #475569; background: #F3F6FA; border: 1px solid #D5DEE8;
            }
            QPushButton#sidebarUpdate:hover { background: #E4F4EA; color: #167A40; border-color: #21834C; }
            QPushButton#sidebarUpdate[has_update="true"] {
                background: #E2F5EA; color: #146C38; border: 1px solid #1DB954; font-weight: 800;
            }
            QPushButton#sidebarUpdate[has_update="true"]:hover {
                background: #1DB954; color: #FFFFFF;
            }
            QFrame#updateWarningBanner {
                background: #E8F7EE; border: 1px solid #21834C; border-radius: 14px;
            }
            QLabel#updateBannerTitle { color: #123522; font-weight: 700; }
            QPushButton#updateBannerAction { background: #1DB954; color: #FFFFFF; }
            QPushButton#updateBannerClose { color: #546275; }
            QPushButton#updateBannerClose:hover { background: rgba(20, 28, 38, 14); color: #141C26; }
            QWidget#trackRow:hover, QListWidget::item:hover { background: #EFF3F8; color: #141C26; }
            QListWidget::item:selected { background: #E4F3EA; border: 1px solid #A8D8BA; }

            QPushButton#playButton, QPushButton#accentButton { background: #1DB954; color: #FFFFFF; }
            QPushButton#playButton:hover, QPushButton#accentButton:hover { background: #179443; }
            QPushButton#bottomFavorite:hover, QPushButton#bottomDislike:hover { background: rgba(20, 28, 38, 14); }
            QPushButton#bottomFavorite:checked { background: transparent; }
            QPushButton#bottomFavorite:checked:hover { background: rgba(29, 185, 84, 22); }
            QPushButton#bottomDislike:checked { background: #F7E6E6; }

            QPushButton#rowPlay, QPushButton#rowFavorite, QPushButton#rowRemove {
                background: transparent; color: #263342; border: none; border-radius: 17px;
            }
            QPushButton#rowPlay[revealed="true"] { background: rgba(20, 28, 38, 12); }
            QPushButton#rowPlay:hover { background: #1DB954; color: #FFFFFF; }
            QPushButton#filterButton, QPushButton#themeButton {
                background: #EFF3F7; color: #263342; border-color: #D5DEE8;
            }
            QPushButton#rowFavorite:checked { color: #167A40; background: rgba(29, 185, 84, 20); }
            QPushButton#rowRemove { background: transparent; color: transparent; }
            QPushButton#rowRemove[revealed="true"], QPushButton#rowRemove:focus { background: #E1E8F0; color: #243140; }
            QFrame#likesHeroHeader {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #E4F4EA, stop:1 #FFFFFF);
                border: 1px solid #C2E5D0; border-radius: 16px;
            }
            QPushButton#transportButton { color: #4E5C6E; }
            QPushButton#transportButton:hover, QPushButton#iconButton:hover { background: #EBF0F6; color: #167A40; }
            QPushButton#transportButton:checked { background: #E1F3E8; color: #167A40; }
            QPushButton#trackArtistLink { color: #5C697C; }
            QPushButton#trackArtistLink:hover, QPushButton#textButton { color: #167A40; }
            QPushButton#textButton:hover { background: #EBF0F6; }

            QLineEdit { background: #F3F6FA; color: #141C26; border-color: #D5DEE8; }
            QLineEdit:focus { background: #FFFFFF; border-color: #21834C; }
            QSlider::groove:horizontal, QSlider#seekSlider::groove:horizontal { background: #CFD8E3; }
            QSlider::sub-page:horizontal, QSlider#seekSlider::sub-page:horizontal { background: #21834C; }
            QSlider::handle:horizontal, QSlider#seekSlider::handle:horizontal { background: #21834C; }

            QTabBar::tab { background: transparent; color: #5C697C; }
            QTabBar::tab:selected { background: transparent; color: #141C26; border-bottom-color: #21834C; }
            QTabBar::tab:hover:!selected { background: #EFF3F8; color: #141C26; }

            QMenu#darkMenu, QMenu { background: #FFFFFF; color: #18202A; border-color: #D5DEE8; }
            QMenu#darkMenu::item, QMenu::item { color: #18202A; }
            QMenu#darkMenu::item:selected, QMenu::item:selected { background: #E2F3E8; color: #167A40; }

            QFrame#radioCard { background: #FFFFFF; border-color: #D5DEE8; }
            QLabel#radioTrackTitle { color: #141C26; }
            QLabel#radioStatus { color: #5C697C; }
            QDialog#settingsDialog { background: #F2F5F9; }

            QPushButton#bottomArtistLink, QPushButton#expandedArtist { color: #5C697C; }
            QPushButton#bottomArtistLink:hover:enabled, QPushButton#expandedArtist:hover:enabled { color: #141C26; }
            QPushButton#expandedArtist:hover:enabled { background: rgba(20, 28, 38, 12); }
            QLabel#expandedTitle { color: #141C26; }
            QWidget#coverPage, QLabel#expandedCover { background: transparent; border: none; }
            QFrame#sidebarDivider { background: #DFE6EE; }
            QLabel#sidebarSectionTitle { color: #647285; }
            QPushButton#sidebarAddButton { color: #546275; }
            QPushButton#sidebarAddButton:hover { background: #EBF0F6; color: #141C26; }
            QLabel#sidebarMediaCover { background: transparent; border: none; }
            QFrame#searchBox { background: #F2F5F9; border-color: #D6DFE9; }
            QFrame#searchBox[focused="true"] { background: #FFFFFF; border-color: #21834C; }
            QLineEdit#catalogSearch, QLineEdit#catalogSearch:hover, QLineEdit#catalogSearch:focus { color: #162230; }
            QLabel#searchShortcut { background: #E6ECF3; color: #5E6C80; border-color: #D4DEE8; }
            QPushButton#searchSubmit { background: #21834C; color: #FFFFFF; }
            QPushButton#searchSubmit:hover { background: #29995A; }
            QPushButton#searchSubmit:pressed { background: #196B3D; }
            QPushButton#searchSubmit:disabled { background: #DCE6E0; color: #788C80; }
        """
        if self.backdrop.has_wallpaper:
            dark_styles += r"""
                QFrame#sidebar, QFrame#queuePanel { background: rgba(14, 18, 25, 205); border-color: rgba(255, 255, 255, 24); }
                QFrame#centerPanel { background: rgba(18, 23, 31, 182); border-color: rgba(255, 255, 255, 22); }
                QFrame#playerBar { background: rgba(18, 24, 33, 224); border-color: rgba(255, 255, 255, 28); }
                QFrame#searchBox { background: rgba(24, 30, 40, 210); }
                QFrame#likesAccountCard, QLabel#recentEmpty { background: rgba(24, 30, 40, 190); }
                QScrollArea#startCardsScroll, QScrollArea#startCardsScroll QWidget#qt_scrollarea_viewport,
                QWidget#startCardsWidget, QListWidget { background: transparent; }
            """
            light_styles += r"""
                QFrame#sidebar, QFrame#queuePanel { background: rgba(252, 254, 255, 222); border-color: rgba(210, 220, 232, 190); }
                QFrame#centerPanel { background: rgba(252, 254, 255, 206); border-color: rgba(210, 220, 232, 180); }
                QFrame#playerBar { background: rgba(252, 254, 255, 236); border-color: rgba(205, 216, 228, 210); }
                QFrame#searchBox { background: rgba(244, 247, 251, 220); }
                QFrame#likesAccountCard, QLabel#recentEmpty { background: rgba(246, 249, 252, 205); }
                QScrollArea#startCardsScroll, QScrollArea#startCardsScroll QWidget#qt_scrollarea_viewport,
                QWidget#startCardsWidget, QListWidget { background: transparent; }
            """
        self.backdrop.set_appearance(self.theme, self.wallpaper_dim)
        self.setStyleSheet(dark_styles if self.theme == "dark" else dark_styles + light_styles)
        refresh_native_title_bars(self.theme)
        if self.mini_player is not None:
            self.mini_player.apply_theme()
        icon_color = "#D2DAE5" if self.theme == "dark" else "#526075"
        for button, name in ((self.previous_button, "previous"), (self.next_button, "next")):
            button.setIcon(control_icon(name, icon_color))
        self.shuffle_button.setIcon(control_icon("shuffle", "#1DB954" if self.shuffle_enabled else icon_color))
        self.repeat_button.setIcon(control_icon("repeat", "#1DB954" if self.repeat_mode != "off" else icon_color))
        if hasattr(self, "bottom_mini_button"):
            self.bottom_mini_button.setIcon(control_icon("mini", icon_color))
        self.bottom_queue_button.setIcon(control_icon("queue", "#1DB954" if self.queue_open else icon_color))
        self.volume_icon.setPixmap(control_icon("volume", icon_color).pixmap(18, 18))
        self.search_icon.setPixmap(control_icon("search", icon_color).pixmap(20, 20))
        self.sidebar_settings_button.setIcon(control_icon("settings", icon_color))
        if hasattr(self, "artist_header"):
            self.artist_header.setStyleSheet("")
            avatar_url = self.artist_avatar.property("requested_image") if hasattr(self, "artist_avatar") else ""
            if avatar_url in getattr(self, "pixmap_cache", {}):
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
                menu.setStyleSheet("QMenu{background:#1A2029;color:#F4F7FA;border:1px solid #2E3846;border-radius:10px;padding:7px;} QMenu::item{padding:10px 22px 10px 14px;border-radius:7px;} QMenu::item:selected{background:#23372C;color:#66E099;}")
            else:
                menu.setStyleSheet("QMenu{background:#FFFFFF;color:#18202A;border:1px solid #D5DEE8;border-radius:10px;padding:7px;} QMenu::item{padding:10px 22px 10px 14px;border-radius:7px;} QMenu::item:selected{background:#E2F3E8;color:#167A40;}")

    # ---------------------------------------------------------
    # Все сигналы.
    # ---------------------------------------------------------

    def connect_signals(self):
        for i, button in enumerate(self.nav_buttons):
            button.clicked.connect(lambda checked=False, index=i: self.set_source(self.nav_data[index][2]))

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
        self.sync_account_button.clicked.connect(self.sync_selected_likes)
        self.disconnect_account_button.clicked.connect(self.disconnect_youtube_account)
        # Строки TrackRow сами обрабатывают один клик; не подключаем itemClicked,
        # чтобы одно нажатие не добавляло одну песню в очередь дважды.
        self.source_list.customContextMenuRequested.connect(self.open_result_menu)
        self.likes_tabs.currentChanged.connect(self.on_likes_tab_changed)
        self.likes_search_input.textChanged.connect(self.on_likes_search_changed)
        for list_widget in (self.source_list, self.youtube_likes_list,
                            self.soundcloud_likes_list, self.likes_list,
                            self.user_playlist_list, self.queue_list):
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
            player.seekableChanged.connect(lambda seekable, i=index: self._apply_recovery_seek(i))

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

    def set_wallpaper_image(self, image):
        """Keep an app-owned copy; never alter or delete the selected original."""
        try:
            destination = app_data_directory() / "background.png"
        except OSError:
            return False
        if image.isNull():
            try:
                destination.unlink(missing_ok=True)
            except OSError:
                return False
            self.wallpaper_path = ""
        else:
            output = QSaveFile(str(destination))
            if not output.open(QIODevice.OpenModeFlag.WriteOnly):
                return False
            if not image.save(output, "PNG"):
                output.cancelWriting()
                return False
            if not output.commit():
                return False
            self.wallpaper_path = str(destination)
        self.settings.setValue("wallpaper_path", self.wallpaper_path)
        self.settings.sync()
        self.backdrop.set_image(image)
        self.apply_styles()
        return True

    def open_settings(self):
        dialog = SettingsDialog(self)
        try:
            dialog.exec()
        finally:
            dialog.deleteLater()

    def show_about(self):
        upd = self._available_update_info or {}
        upd_line = (
            f"Доступна новая версия: v{upd.get('latest_version')} (нажмите «Обновить» в меню слева)\n"
            if upd.get("is_newer")
            else f"Установлена актуальная версия: v{APP_VERSION}\n"
        )
        QMessageBox.about(
            self, "О программе",
            f"Aurora Music Player · v{APP_VERSION}\n"
            f"{upd_line}"
            f"Репозиторий: github.com/{GITHUB_REPO}\n\n"
            "Локальные лайки хранятся в favorites.json. Импорт YouTube Music использует cookie-файл или сессию браузера; пароль Google приложение не запрашивает."
        )

    def dismiss_update_banner(self):
        self._update_banner_dismissed = True
        if hasattr(self, "update_warning_banner"):
            self.update_warning_banner.hide()

    def _refresh_update_ui(self):
        info = self._available_update_info or {}
        has_newer = bool(info.get("is_newer"))
        latest_ver = str(info.get("latest_version") or APP_VERSION)
        if hasattr(self, "sidebar_update_button"):
            if has_newer:
                self.sidebar_update_button.setText(f"⬇ Обновить до v{latest_ver}")
                self.sidebar_update_button.setToolTip(
                    f"Вышла новая версия v{latest_ver} (у вас v{APP_VERSION}). Нажмите для обновления!"
                )
            else:
                self.sidebar_update_button.setText(f"↻ Обновить · v{APP_VERSION}")
                self.sidebar_update_button.setToolTip(
                    f"Текущая версия v{APP_VERSION}. Нажмите, чтобы проверить обновления на GitHub."
                )
            self.sidebar_update_button.setProperty("has_update", has_newer)
            self.sidebar_update_button.style().unpolish(self.sidebar_update_button)
            self.sidebar_update_button.style().polish(self.sidebar_update_button)

        if hasattr(self, "top_update_button"):
            self.top_update_button.setText(f"⬇ v{latest_ver}")
            self.top_update_button.setProperty("has_update", has_newer)
            self.top_update_button.setVisible(has_newer)

        if hasattr(self, "update_warning_banner"):
            if has_newer and not self._update_banner_dismissed:
                pub = f" от {info['published_at']}" if info.get("published_at") else ""
                self.update_banner_label.setText(
                    f"⚠ Доступна новая версия Aurora v{latest_ver}{pub} (установлена v{APP_VERSION}). "
                    f"Нажмите «Обновить сейчас», чтобы автоматически скачать и установить новую версию."
                )
                self.update_warning_banner.show()
            else:
                self.update_warning_banner.hide()

        if hasattr(self, "update_app_action"):
            self.update_app_action.setText(
                f"⬇ Обновить до v{latest_ver}…" if has_newer else f"Проверить обновления (v{APP_VERSION})…"
            )

    def check_for_updates(self, manual=False):
        if self._force_exit:
            return
        if self._update_checker_worker is not None and self._update_checker_worker.isRunning():
            if manual:
                self.show_toast("Проверка обновлений на GitHub уже выполняется…", 2500)
            return
        if manual:
            self.set_status("Проверяю наличие новой версии на GitHub…")
            if hasattr(self, "sidebar_update_button"):
                self.sidebar_update_button.setText("⏳ Проверка…")
        worker = AppUpdateCheckerWorker(GITHUB_REPO, APP_VERSION, self)
        self._update_checker_worker = worker
        worker.update_checked.connect(lambda info, m=manual: self._on_update_checked(info, manual=m))
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _on_update_checked(self, info, manual=False):
        self._update_checker_worker = None
        if not isinstance(info, dict):
            return
        self._available_update_info = dict(info)
        if info.get("is_newer"):
            self._update_banner_dismissed = False
        self._refresh_update_ui()

        if info.get("is_newer"):
            latest_ver = info.get("latest_version", "")
            msg = f"Доступна новая версия Aurora v{latest_ver}! Нажмите «Обновить» для автоматической установки."
            self.set_status(msg)
            self.show_toast(msg, 6500)
            if getattr(self, "tray_icon", None) is not None and self.tray_icon.isVisible():
                try:
                    self.tray_icon.showMessage(
                        f"Доступно обновление Aurora v{latest_ver}",
                        "Откройте плеер и нажмите «Обновить сейчас» для установки новой версии.",
                        QSystemTrayIcon.MessageIcon.Information,
                        4500,
                    )
                except Exception:
                    pass
            if manual:
                self._show_update_dialog(info)
        elif manual:
            self._show_update_dialog(info)

    def on_update_button_clicked(self):
        if self._update_installer_worker is not None and self._update_installer_worker.isRunning():
            self.show_toast("Скачивание и установка обновления уже выполняются…", 3000)
            return
        info = self._available_update_info
        if isinstance(info, dict) and info.get("is_newer"):
            self._show_update_dialog(info)
        else:
            self.check_for_updates(manual=True)

    def _prompt_and_install_update(self, info):
        self._show_update_dialog(info)

    def _show_update_dialog(self, info):
        info = dict(info or {})
        repo = str(info.get("repo") or _detect_github_repo(GITHUB_REPO))
        latest_ver = str(info.get("latest_version") or APP_VERSION)
        has_newer = bool(info.get("is_newer"))
        is_ok = bool(info.get("ok"))
        notes = str(info.get("notes") or "").strip()
        release_url = str(info.get("release_url") or f"https://github.com/{repo}/releases")
        actions_url = str(info.get("actions_url") or f"https://github.com/{repo}/actions/workflows/windows-build.yml")

        dialog = QDialog(self)
        dialog.setObjectName("auroraUpdateDialog")
        dialog.setWindowTitle("Обновление Aurora Music Player")
        dialog.setMinimumWidth(480)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)

        title_lbl = QLabel(
            f"Доступна новая версия v{latest_ver}" if has_newer else f"Aurora Music Player · v{APP_VERSION}",
            dialog,
        )
        title_lbl.setObjectName("updateDialogTitle")
        title_lbl.setWordWrap(True)
        layout.addWidget(title_lbl)

        if has_newer:
            extra_commits = " (найдены новые коммиты в Git)" if info.get("has_git_commits") else ""
            body_text = (
                f"Установлена версия: v{APP_VERSION}\n"
                f"Актуальная версия на GitHub: v{latest_ver}{extra_commits}\n\n"
                "Нажмите «Обновить и перезапустить», чтобы автоматически установить свежую версию "
                "и перезапустить плеер."
            )
            if notes:
                body_text += f"\n\nЧто нового:\n{notes[:500]}"
        elif is_ok:
            if info.get("no_releases_yet"):
                body_text = (
                    f"У вас установлена актуальная версия Aurora v{APP_VERSION}.\n\n"
                    "В разделе GitHub Releases пока нет опубликованных тегов, но вы можете обновить "
                    "приложение напрямую из ветки main или открыть страницу сборок GitHub Actions (.exe)."
                )
            else:
                body_text = (
                    f"У вас установлена актуальная версия Aurora v{APP_VERSION}.\n\n"
                    "Вы можете принудительно обновить файлы из репозитория GitHub или открыть страницу готовых .exe релизов."
                )
        else:
            err_detail = str(info.get("error") or "репозиторий приватный или нет опубликованных релизов")
            body_text = (
                f"Текущая версия: Aurora v{APP_VERSION}\n"
                f"Репозиторий: github.com/{repo}\n\n"
                f"Статус API GitHub: {err_detail}.\n"
                "Вы можете запустить обновление напрямую (через Git / ветку main) или открыть страницу готовых .exe сборок в браузере."
            )

        desc_lbl = QLabel(body_text, dialog)
        desc_lbl.setObjectName("updateDialogDesc")
        desc_lbl.setWordWrap(True)
        layout.addWidget(desc_lbl)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        install_btn = QPushButton(
            "⬇ Обновить и перезапустить" if has_newer else "↻ Переустановить с GitHub",
            dialog,
        )
        install_btn.setObjectName("accentButton")
        install_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        releases_btn = QPushButton("GitHub Releases (.exe) ↗", dialog)
        releases_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        actions_btn = QPushButton("GitHub Actions ↗", dialog)
        actions_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        close_btn = QPushButton("Закрыть", dialog)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        btn_row.addWidget(install_btn)
        btn_row.addWidget(releases_btn)
        btn_row.addWidget(actions_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        action_taken = [None]

        def on_install():
            action_taken[0] = "install"
            dialog.accept()

        def on_releases():
            QDesktopServices.openUrl(QUrl(release_url))

        def on_actions():
            QDesktopServices.openUrl(QUrl(actions_url))

        install_btn.clicked.connect(on_install)
        releases_btn.clicked.connect(on_releases)
        actions_btn.clicked.connect(on_actions)
        close_btn.clicked.connect(dialog.reject)

        if self.theme == "light":
            dialog.setStyleSheet("""
                QDialog#auroraUpdateDialog { background-color: #F5F7FA; color: #18202A; }
                QDialog#auroraUpdateDialog QLabel { color: #18202A; background: transparent; font-size: 13.5px; }
                QDialog#auroraUpdateDialog QLabel#updateDialogTitle { color: #111822; font-size: 19px; font-weight: 800; }
                QDialog#auroraUpdateDialog QLabel#updateDialogDesc { color: #475569; }
                QDialog#auroraUpdateDialog QPushButton {
                    background: #E6ECF4; color: #18202A; border: 1px solid #CBD5E1;
                    border-radius: 10px; padding: 9px 14px; font-weight: 600;
                }
                QDialog#auroraUpdateDialog QPushButton:hover { background: #FFFFFF; border-color: #1DB954; color: #146C38; }
                QDialog#auroraUpdateDialog QPushButton#accentButton {
                    background: #1DB954; color: #FFFFFF; border: none; font-weight: 800;
                }
                QDialog#auroraUpdateDialog QPushButton#accentButton:hover { background: #169C46; }
            """)
        else:
            dialog.setStyleSheet("""
                QDialog#auroraUpdateDialog { background-color: #161B23; color: #F2F5F9; border: 1px solid #283241; }
                QDialog#auroraUpdateDialog QLabel { color: #F2F5F9; background: transparent; font-size: 13.5px; }
                QDialog#auroraUpdateDialog QLabel#updateDialogTitle { color: #FFFFFF; font-size: 19px; font-weight: 800; }
                QDialog#auroraUpdateDialog QLabel#updateDialogDesc { color: #A8B3C4; }
                QDialog#auroraUpdateDialog QPushButton {
                    background: #212834; color: #F2F5F9; border: 1px solid #323D4E;
                    border-radius: 10px; padding: 9px 14px; font-weight: 600;
                }
                QDialog#auroraUpdateDialog QPushButton:hover { background: #2A3444; border-color: #5CE092; color: #FFFFFF; }
                QDialog#auroraUpdateDialog QPushButton#accentButton {
                    background: #1DB954; color: #09140D; border: none; font-weight: 800;
                }
                QDialog#auroraUpdateDialog QPushButton#accentButton:hover { background: #2FE06D; color: #09140D; }
            """)

        dialog.exec()
        dialog.deleteLater()
        if action_taken[0] == "install":
            self.start_self_update(info)

    def start_self_update(self, info=None):
        if self._update_installer_worker is not None and self._update_installer_worker.isRunning():
            return
        repo = _detect_github_repo(GITHUB_REPO)
        target_info = dict(info or self._available_update_info or {
            "latest_version": APP_VERSION,
            "source_url": f"https://raw.githubusercontent.com/{repo}/main/player_aurora_smart_beautiful_fixed_ui_repaint.py",
            "release_url": f"https://github.com/{repo}/releases",
        })
        self.show_toast("Начинаю загрузку обновления с GitHub…", 4000)
        self.set_status("Скачиваю обновление с GitHub…")
        if hasattr(self, "sidebar_update_button"):
            self.sidebar_update_button.setEnabled(False)
            self.sidebar_update_button.setText("⏳ Обновление…")
        if hasattr(self, "update_banner_install_btn"):
            self.update_banner_install_btn.setEnabled(False)
            self.update_banner_install_btn.setText("⏳ Загрузка…")
        worker = AppUpdateInstallerWorker(target_info, self)
        self._update_installer_worker = worker
        worker.progress_changed.connect(self._on_update_progress)
        worker.update_ready_to_restart.connect(self._on_update_ready_to_restart)
        worker.update_failed.connect(self._on_update_failed)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _on_update_progress(self, pct, status_text):
        self.set_status(status_text)
        if hasattr(self, "sidebar_update_button"):
            self.sidebar_update_button.setText(f"⏳ {pct}%")
        if hasattr(self, "update_banner_install_btn"):
            self.update_banner_install_btn.setText(f"⏳ {pct}%")

    def _on_update_ready_to_restart(self, target_script, message):
        self._update_installer_worker = None
        if hasattr(self, "sidebar_update_button"):
            self.sidebar_update_button.setEnabled(True)
        if hasattr(self, "update_banner_install_btn"):
            self.update_banner_install_btn.setEnabled(True)
        self.set_status(message)
        self.show_toast(message + " Перезапускаю плеер…", 4000)
        self.save_preferences()
        try:
            if target_script == "__python_restart__":
                subprocess.Popen([sys.executable, str(Path(__file__).resolve())], close_fds=True)
            elif sys.platform == "win32" and Path(target_script).is_file():
                creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
                subprocess.Popen(["cmd.exe", "/c", str(target_script)], creationflags=creation_flags, close_fds=True)
        except Exception as exc:
            QMessageBox.warning(self, "Перезапуск", f"Обновление скачано, но автозапуск не удался: {exc}")
            return
        QTimer.singleShot(300, self.request_app_exit)

    def _on_update_failed(self, error_message):
        self._update_installer_worker = None
        if hasattr(self, "sidebar_update_button"):
            self.sidebar_update_button.setEnabled(True)
        if hasattr(self, "update_banner_install_btn"):
            self.update_banner_install_btn.setEnabled(True)
            self.update_banner_install_btn.setText("⬇ Обновить сейчас")
        self._refresh_update_ui()
        self.set_status(f"Ошибка обновления: {error_message}")
        answer = QMessageBox.warning(
            self,
            "Не удалось установить обновление автоматически",
            f"При скачивании обновления возникла ошибка:\n{error_message}\n\n"
            "Открыть страницу GitHub Releases, чтобы скачать готовый AuroraMusicPlayer.exe вручную?",
            QMessageBox.StandardButton.Open | QMessageBox.StandardButton.Close,
            QMessageBox.StandardButton.Open,
        )
        if answer == QMessageBox.StandardButton.Open:
            QDesktopServices.openUrl(QUrl(f"https://github.com/{GITHUB_REPO}/releases"))

    def save_preferences(self):
        if self.mini_player is not None:
            self.settings.setValue("mini_geometry", self.mini_player.saveGeometry())
        self.settings.setValue("volume", int(round(self.volume * 100)))
        self.settings.setValue("search_limit", self.result_limit)
        self.settings.setValue("audio_quality", self.audio_quality)
        self.settings.setValue("minimize_to_tray", self.minimize_to_tray)
        self.settings.setValue("hide_on_minimize", self.hide_on_minimize)
        self.settings.setValue("fade_duration_ms", self.fade_duration_ms)
        self.settings.setValue("fade_steps", round(self.fade_duration_ms / 30))
        self.settings.remove("sidebar_collapsed")
        self.settings.setValue("repeat_mode", self.repeat_mode)
        self.settings.setValue("shuffle", self.shuffle_enabled)
        self.settings.setValue("autoplay_playlists", self.autoplay_playlists)
        self.settings.setValue("theme", self.theme)
        self.settings.setValue("spotify_theme", self.theme)
        self.settings.setValue("download_dir", self.download_dir)
        self.settings.setValue("wallpaper_path", self.wallpaper_path)
        self.settings.setValue("wallpaper_dim", self.wallpaper_dim)
        self.settings.setValue("youtube_cookie_file", self.youtube_cookie_file)
        self.settings.setValue("youtube_auth_mode", self.youtube_auth_mode)
        self.settings.setValue("youtube_auth_browser", self.youtube_auth_browser)
        self.settings.sync()
        self.save_playback_session()

    def _session_track(self, track):
        """Persist catalog metadata and local paths, never resolved streams/auth."""
        saved = self._recent_track_metadata(track)
        if saved is None:
            return None
        if saved["source"] == "youtube":
            video_id = self.youtube_video_id(saved)
            if not re.fullmatch(r"[A-Za-z0-9_-]{6,64}", video_id or ""):
                return None
            saved["url"] = "https://music.youtube.com/watch?v=" + video_id
            saved["video_id"] = video_id
        elif saved["source"] == "soundcloud":
            try:
                parsed = urlsplit(saved["url"])
            except ValueError:
                return None
            if parsed.hostname not in ("soundcloud.com", "www.soundcloud.com"):
                return None
            saved["url"] = urlunsplit(("https", "soundcloud.com", parsed.path, "", ""))
        for key in ("title", "artist", "artist_display"):
            if key in saved:
                saved[key] = saved[key][:1024]
        try:
            saved["duration"] = max(0, min(7 * 86400, int(float(track.get("duration") or 0))))
        except (TypeError, ValueError, OverflowError):
            saved["duration"] = 0
        if track.get("queue_id"):
            saved["queue_id"] = str(track["queue_id"])[:128]
        return saved

    def schedule_session_save(self):
        if self._session_ready and not self._force_exit:
            self._session_queue_dirty = True
            self.session_save_timer.start(750)

    def save_playback_session(self):
        if not self._session_ready:
            return
        if self._session_queue_dirty or not self._session_revision:
            tracks = [saved for track in self.queue_tracks[:10000]
                      if (saved := self._session_track(track)) is not None]
            revision = uuid4().hex
            try:
                payload = json.dumps({"version": 1, "revision": revision, "queue": tracks}, ensure_ascii=False)
                if len(payload.encode("utf-8")) > 12 * 1024 * 1024:
                    raise ValueError("Слишком большой файл очереди")
                temporary = self.session_file.with_suffix(".tmp")
                temporary.write_text(payload, encoding="utf-8")
                temporary.replace(self.session_file)
            except (OSError, ValueError) as error:
                logging.getLogger("aurora").warning("Не удалось сохранить очередь: %s", error)
                return
            self._session_revision = revision
            self._session_queue_dirty = False
        self.session_save_timer.stop()
        self.save_playback_checkpoint()

    def save_playback_checkpoint(self):
        if not self._session_ready:
            return
        if self._session_queue_dirty or not self._session_revision:
            if self.queue_tracks or self.current_track:
                self.save_playback_session()
            return
        restored = self._restored_playback
        mix = (restored or {}).get("supermix") or self.supermix_session
        mix_state = ({"mix_id": mix.get("mix_id", ""), "anchor": mix.get("anchor", "")}
                     if isinstance(mix, dict) else None)
        position = (restored["position"] if restored is not None else
                    self._last_progress_position if (self._network_recovery is not None or self.player.source().isEmpty())
                    else self.player.position())
        current = self._session_track(self.current_track)
        duration = self.playback_duration_ms() if self._remote_playback() else self.player.duration()
        if current is not None and duration > 0:
            current["duration"] = duration / 1000
        checkpoint = {"revision": self._session_revision, "current": current,
                      "position": max(0, int(position)), "source": self.current_source,
                      "mode": (restored or {}).get("mode", self.queue_mode), "supermix": mix_state,
                      "repeat": self.repeat_mode, "shuffle": self.shuffle_enabled}
        blob = json.dumps(checkpoint, ensure_ascii=False)
        if blob != self._last_checkpoint_blob:
            self.settings.setValue("playback_checkpoint_json", blob)
            self.settings.sync()
            self._last_checkpoint_blob = blob

    def restore_playback_session(self):
        try:
            if not self.session_file.is_file():
                return
            if self.session_file.stat().st_size > 12 * 1024 * 1024:
                raise ValueError("Слишком большой файл очереди")
            data = json.loads(self.session_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("queue"), list):
                return
            revision = data.get("revision")
            if not isinstance(revision, str) or not revision:
                return
            try:
                checkpoint = json.loads(str(self.settings.value("playback_checkpoint_json", "{}") or "{}"))
            except ValueError:
                checkpoint = {}
            if not isinstance(checkpoint, dict) or checkpoint.get("revision") != revision:
                checkpoint = {}
            tracks, seen = [], set()
            for item in data["queue"][:10000]:
                saved = self._session_track(item)
                if saved is None:
                    continue
                uid = saved.get("queue_id")
                if not uid or uid in seen:
                    uid = uuid4().hex
                saved["queue_id"] = uid
                seen.add(uid)
                tracks.append(saved)
            current = self._session_track(checkpoint.get("current"))
            if current is None and tracks:
                current = tracks[0]
            if current:
                matched = next((t for t in tracks if t["queue_id"] == current.get("queue_id")), None)
                if matched is not None:
                    current = {**matched, **current}
            position = max(0, min(7 * 86400 * 1000, int(checkpoint.get("position", 0))))
            if current and current.get("duration"):
                position = min(position, max(0, current["duration"] * 1000 - 1000))
            self.queue_tracks = tracks
            self.current_track = current
            self.refresh_queue_list()
            self._session_revision = revision
            self.repeat_mode = checkpoint.get("repeat") if checkpoint.get("repeat") in ("off", "one", "all") else self.repeat_mode
            self.refresh_repeat_button()
            # Update the toggle without starting prefetch during restoration.
            self.shuffle_enabled = bool(checkpoint.get("shuffle", self.shuffle_enabled))
            self.shuffle_button.blockSignals(True)
            self.shuffle_button.setChecked(self.shuffle_enabled)
            self.shuffle_button.blockSignals(False)
            self.apply_styles()
            source = checkpoint.get("source")
            if source in ("youtube", "soundcloud", "likes") and source != self.current_source:
                self.set_source(source)
            if current:
                self._restored_playback = {"position": position, "mode": checkpoint.get("mode", "manual"),
                                           "supermix": checkpoint.get("supermix")}
                self.bottom_title.setText(current.get("title") or "Без названия")
                self.bottom_artist.setText(current.get("artist") or "")
                self.show_cover(current.get("thumbnail", ""))
                restored_duration_ms = max(0, int((current.get("duration") or 0) * 1000))
                self.position_label.setText(self.format_position(position))
                self.duration_label.setText(self.format_position(restored_duration_ms))
                self.seek_slider.setRange(0, restored_duration_ms)
                self.seek_slider.setValue(min(position, restored_duration_ms) if restored_duration_ms else 0)
                self.update_bottom_track_actions()
                self.set_status("Очередь восстановлена. Нажми ▶, чтобы продолжить с прежнего места.")
        except (OSError, ValueError, TypeError, AttributeError) as error:
            logging.getLogger("aurora").warning("Не удалось восстановить очередь: %s", error)

    def resume_saved_session(self):
        saved = self._restored_playback
        if saved is None or self.current_track is None:
            return
        mix = saved.get("supermix")
        if (isinstance(mix, dict) and str(mix.get("mix_id", "")).startswith("RDTMAK5uy_")
                and self.youtube_auth_kwargs()):
            self.queue_mode = "supermix"
            self.supermix_session = {"mix_id": mix["mix_id"], "anchor": str(mix.get("anchor") or ""),
                                    "seen": {self.youtube_video_id(t) for t in self.queue_tracks},
                                    "waiting": False, "failures": 0}
        else:
            mode = saved.get("mode")
            self.queue_mode = ("youtube_likes" if mode == "supermix" else
                               mode if mode in ("youtube_likes", "soundcloud_likes") else "manual")
        self.play_track(self.current_track, self.current_queue_index,
                        start_position=saved["position"], restore_session=True)

    def on_shuffle_changed(self, enabled):
        self.shuffle_enabled = bool(enabled)
        self.shuffle_future = None
        if not self.shuffle_enabled:
            self._shuffle_history.clear()
        self.shuffle_button.setIcon(control_icon(
            "shuffle", "#1DB954" if self.shuffle_enabled else ("#D2DAE5" if self.theme == "dark" else "#526075")))
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
            "repeat", "#1DB954" if self.repeat_mode != "off" else ("#D2DAE5" if self.theme == "dark" else "#526075")))
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
        if self.radio_mode_active or self.queue_mode in ("radio", "supermix"):
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
        if self.queue_mode == "supermix":
            self.maybe_refill_supermix()

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
        self.radio_seed_track = dict(current)
        self.radio_artist_context = str(
            getattr(self, "active_artist_profile", "") or ""
        ).strip() if self.artist_profile_open else ""
        self.radio_seen_urls = set()
        self.radio_seen_signatures = set()
        for item in self.queue_tracks:
            self._remember_radio_track(item)
        self._remember_radio_track(current)
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

        if self.queue_mode == "supermix":
            if self.supermix_session is not None:
                self.supermix_session["anchor"] = self.youtube_video_id(self.current_track or {})
            self.maybe_refill_supermix()
            next_index = self.peek_next_index()
            if next_index is not None:
                self.play_queue_index(next_index)
            else:
                self._wait_for_supermix()
            return

        if self._is_youtube_likes_playback():
            next_index = self.peek_next_index()
            if next_index is not None:
                self.play_queue_index(next_index)
                return
            self._finish_transition_pending = False
            self._finish_guard_url = str((self.current_track or {}).get("url") or "")
            self.set_status("Лайки YouTube Music закончились.", "youtube")
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
            self.radio_seed_track = dict(last_track)
            self.radio_seen_urls = set()
            self.radio_seen_signatures = set()
            for item in self.queue_tracks:
                self._remember_radio_track(item)
            self._remember_radio_track(last_track)
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
    # Показ очереди по требованию.
    # ---------------------------------------------------------

    def toggle_queue(self):
        """Выдвигает очередь в самом приложении, не создавая новое окно."""
        self.queue_open = not self.queue_open
        self.queue_animation.stop()
        self.queue_animation.setStartValue(self.queue_panel.maximumWidth())
        self.queue_animation.setEndValue(320 if self.queue_open else 0)
        self.queue_animation.start()
        self.bottom_queue_button.setToolTip(
            "Скрыть очередь" if self.queue_open else "Открыть очередь"
        )
        self.bottom_queue_button.setIcon(control_icon(
            "queue", "#1DB954" if self.queue_open else ("#D2DAE5" if self.theme == "dark" else "#526075")
        ))

    def fade_to_page(self, page):
        """Короткое затухание при смене внутреннего экрана (без отдельного окна)."""
        was_cover = self.view_stack.currentWidget() is getattr(self, "cover_page", None)
        is_cover = page is getattr(self, "cover_page", None)
        if not is_cover and was_cover:
            if hasattr(self, "_cover_expand_anim"):
                self._cover_expand_anim.stop()
            self.expanded_cover.hide()
            self.expanded_cover.clear_artwork()
        if self.page_animation is not None:
            self.page_animation.stop()
            self.page_animation.deleteLater()
            if self._animated_page is not None:
                self._animated_page.setGraphicsEffect(None)
            self.page_animation = None
        stack_layout = self.view_stack.layout()
        if is_cover:
            if isinstance(stack_layout, QStackedLayout):
                stack_layout.setStackingMode(QStackedLayout.StackingMode.StackAll)
            self.view_stack.setCurrentWidget(page)
            for i in range(self.view_stack.count()):
                candidate = self.view_stack.widget(i)
                if candidate is not None:
                    candidate.setVisible(candidate is self._cover_return_page or candidate is page)
            return
        if isinstance(stack_layout, QStackedLayout):
            stack_layout.setStackingMode(QStackedLayout.StackingMode.StackOne)
        self.view_stack.setCurrentWidget(page)
        if was_cover and page is self._cover_return_page:
            return
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
        self.active_user_playlist_id = ""
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
        self._sync_sidebar_playing_state()

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
        self.page_description.clear()
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
        self.refresh_mini_player()

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

    YOUTUBE_EXTRA_MIX_SPECS = (
        ("my_mix_1", "Мой микс 1", "Персональная волна #1 • YouTube Music", "#1D4ED8", "#38BDF8"),
        ("my_mix_2", "Мой микс 2", "Персональная волна #2 • YouTube Music", "#047857", "#A3E635"),
        ("my_mix_3", "Мой микс 3", "Персональная волна #3 • YouTube Music", "#9D174D", "#FB7185"),
        ("discover_mix", "Микс открытий", "Новые треки по вкусу • YouTube Music", "#5B21B6", "#E879F9"),
        ("new_release_mix", "Новинки", "Свежие релизы артистов • YouTube Music", "#C2410C", "#FDE047"),
        ("replay_mix", "На повторе", "Главные хиты профиля • YouTube Music", "#7E22CE", "#22D3EE"),
    )

    def _set_supermix_busy(self, busy):
        active_key = getattr(self, "_active_youtube_mix_key", "supermix") or "supermix"
        for card in self.start_cards:
            if card.title == "Супермикс":
                is_target = busy and active_key == "supermix"
                card.setEnabled(not is_target)
                card.subtitle = ("Загружаю твою подборку…" if is_target
                                 else "Персональная подборка YouTube Music")
                card.setCursor(Qt.CursorShape.BusyCursor if is_target else Qt.CursorShape.PointingHandCursor)
                card.update()
        default_subs = {k: sub for k, _, sub, _, _ in self.YOUTUBE_EXTRA_MIX_SPECS}
        catalog = getattr(self, "youtube_mix_catalog", {}) or {}
        for card in getattr(self, "youtube_mix_cards", []):
            key = getattr(card, "artwork_style", "")
            is_target = busy and active_key == key
            card.setEnabled(not is_target)
            cat_desc = str((catalog.get(key) or {}).get("description") or "").strip()
            card.subtitle = "Загружаю микс YouTube Music…" if is_target else (cat_desc or default_subs.get(key, card.subtitle))
            card.setCursor(Qt.CursorShape.BusyCursor if is_target else Qt.CursorShape.PointingHandCursor)
            card.update()
        self.refresh_supermix_card()

    def refresh_supermix_card(self):
        if not hasattr(self, "player"):
            return
        session = self.supermix_session
        state = "idle"
        active_key = (session.get("mix_key") if isinstance(session, dict) and session.get("mix_key") else getattr(self, "_active_youtube_mix_key", "supermix")) or "supermix"
        if self.supermix_worker is not None:
            state = "loading"
        elif session is not None and self.queue_mode == "supermix":
            uid = (self.current_track or {}).get("queue_id")
            current_is_mix = bool(uid and any(track.get("queue_id") == uid for track in self.queue_tracks))
            playback = self.player.playbackState()
            if current_is_mix and playback == QMediaPlayer.PlaybackState.PlayingState:
                state = "playing"
            elif current_is_mix and playback == QMediaPlayer.PlaybackState.PausedState:
                state = "paused"
            else:
                state = "loading" if self.requested_track is not None else "waiting"
        for card in self.start_cards:
            if card.artwork_style == "supermix":
                card.set_playback_state(state if active_key == "supermix" else "idle")
        for card in getattr(self, "youtube_mix_cards", []):
            card.set_playback_state(state if card.artwork_style == active_key else "idle")
        self._sync_sidebar_playing_state()

    def toggle_supermix(self):
        self.toggle_youtube_mix("supermix")

    def toggle_youtube_mix(self, mix_key="supermix"):
        mix_key = str(mix_key or "supermix").strip() or "supermix"
        session_key = (self.supermix_session.get("mix_key") or "supermix") if isinstance(self.supermix_session, dict) else "supermix"
        if self.supermix_session is not None and self.queue_mode == "supermix" and session_key == mix_key:
            if self.supermix_session["waiting"]:
                self.maybe_refill_supermix()
            else:
                uid = (self.current_track or {}).get("queue_id")
                current_is_mix = bool(uid and any(track.get("queue_id") == uid for track in self.queue_tracks))
                if current_is_mix:
                    self.toggle_playback()
                elif self.requested_track is None and self.pending_slot is None:
                    # Retry the first track if its stream failed; leave previous audio alone while loading.
                    self.play_queue_index(0)
            return
        if mix_key == "supermix":
            self.play_supermix()
        else:
            self.play_youtube_mix(mix_key)

    def _cancel_supermix(self):
        if self.supermix_worker is not None:
            self.supermix_worker.cancel()
            self.supermix_worker = None
            self._set_supermix_busy(False)

    def _youtube_disliked_video_ids(self):
        return {self.youtube_video_id({"url": key.split("|", 1)[1]})
                for key in self.disliked_track_keys if key.startswith("youtube|")}

    def _stop_supermix_session(self):
        """Старый ответ не должен дополнять вручную выбранную музыку."""
        self._cancel_supermix()
        self.supermix_retry_timer.stop()
        self.supermix_session = None
        if self.supermix_refill_worker is not None:
            self.supermix_refill_worker.cancel()
            self.supermix_refill_worker = None
        self.refresh_supermix_card()

    def _make_supermix_worker(self, **kwargs):
        auth = self.youtube_auth_kwargs()
        return SupermixWorker(
            self.youtube_auth_mode, cookie_file=auth.get("cookie_file", ""),
            browser_spec=auth.get("cookies_from_browser", ""), parent=self, **kwargs
        )

    def _prewarm_youtube_startup(self):
        """В фоне прогревает cookies браузера, сессии SoundCloud и общий пул yt-dlp при старте, чтобы клик по треку или Миксу срабатывал мгновенно."""
        def _prewarm_all():
            try:
                auth = self.youtube_auth_kwargs()
                browser_spec = str(auth.get("cookies_from_browser") or "").strip()
                if self.youtube_auth_mode == "browser" and browser_spec:
                    try:
                        YouTubeMusicAuth._cookies_from_browser(browser_spec)
                    except Exception:
                        pass
                # Прогреваем клиент SoundCloud (client_id + TCP/TLS keepalive сессия)
                try:
                    StreamWorker.get_soundcloud_client_id()
                    StreamWorker._get_soundcloud_session()
                except Exception:
                    pass
                # Прогреваем общий экземпляр yt-dlp
                try:
                    StreamWorker._warmup_shared_ydl()
                except Exception:
                    pass
            except Exception:
                pass

        threading.Thread(target=_prewarm_all, daemon=True, name="StartupPrewarm").start()

    def _known_mix_Lookup(self, mix_key):
        """Возвращает сохранённые (mix_id, cover_url) для мгновенного запуска микса без get_home()."""
        if os.environ.get("QT_QPA_PLATFORM") == "offscreen" or "unittest" in sys.modules:
            return "", ""
        catalog = getattr(self, "youtube_mix_catalog", {}) or {}
        entry = catalog.get(mix_key)
        if isinstance(entry, dict):
            mid = str(entry.get("mix_id") or "").strip()
            cov = str(entry.get("cover_url") or "").strip()
            if mid:
                return mid, cov
        return "", ""

    def play_supermix(self):
        """Открывает настоящий My Supermix; до ответа сохраняет текущую очередь."""
        if not self.youtube_auth_kwargs():
            self.connect_youtube_account()
            return
        self._active_youtube_mix_key = "supermix"
        self._cancel_supermix()
        known_mid, known_cov = self._known_mix_Lookup("supermix")
        extra_kw = {"excluded_ids": self._youtube_disliked_video_ids()}
        if known_mid:
            extra_kw["known_mix_id"] = known_mid
            extra_kw["known_cover_url"] = known_cov or self.supermix_cover_url
        worker = self._make_supermix_worker(**extra_kw)
        self.supermix_worker = worker
        worker.result_ready.connect(lambda result, meta, w=worker: self.on_supermix_ready(w, result, meta))
        worker.failed.connect(lambda message, w=worker: self.on_supermix_error(w, message))
        worker.finished.connect(lambda w=worker: self.on_supermix_finished(w))
        worker.finished.connect(worker.deleteLater)
        self._set_supermix_busy(True)
        self.set_status("Открываю My Supermix подключённого аккаунта YouTube Music…", "youtube")
        worker.start()

    def play_youtube_mix(self, mix_key="supermix"):
        """Открывает выбранный персональный микс YouTube Music (Мой микс 1–3, Открытия, Новинки, На повторе)."""
        mix_key = str(mix_key or "supermix").strip() or "supermix"
        if mix_key == "supermix":
            self.play_supermix()
            return
        if not self.youtube_auth_kwargs():
            self.connect_youtube_account()
            return
        self._active_youtube_mix_key = mix_key
        self._cancel_supermix()
        known_mid, known_cov = self._known_mix_Lookup(mix_key)
        extra_kw = {
            "mix_key": mix_key,
            "excluded_ids": self._youtube_disliked_video_ids(),
        }
        if known_mid:
            extra_kw["known_mix_id"] = known_mid
            extra_kw["known_cover_url"] = known_cov
        worker = self._make_supermix_worker(**extra_kw)
        self.supermix_worker = worker
        worker.result_ready.connect(lambda result, meta, w=worker: self.on_supermix_ready(w, result, meta))
        worker.failed.connect(lambda message, w=worker: self.on_supermix_error(w, message))
        worker.finished.connect(lambda w=worker: self.on_supermix_finished(w))
        worker.finished.connect(worker.deleteLater)
        self._set_supermix_busy(True)
        titles = {k: title for k, title, _, _, _ in self.YOUTUBE_EXTRA_MIX_SPECS}
        mix_label = titles.get(mix_key, "Микс YouTube Music")
        self.set_status(f"Открываю «{mix_label}» подключённого аккаунта YouTube Music…", "youtube")
        worker.start()

    def _fresh_supermix_tracks(self, tracks, seen=()):
        excluded = set(seen) | self._youtube_disliked_video_ids()
        result = []
        for track in tracks:
            video_id = self.youtube_video_id(track)
            if video_id and video_id not in excluded and not self.is_disliked(track):
                result.append(dict(track))
                excluded.add(video_id)
        return result

    def on_supermix_ready(self, worker, tracks, metadata):
        if worker is not self.supermix_worker or self._force_exit:
            return
        result = self._fresh_supermix_tracks(tracks)
        mix_id = str(metadata.get("mix_id") or "")
        if not result or not mix_id:
            self.on_supermix_error(worker, "My Supermix не вернул доступных песен. Попробуй ещё раз позже.")
            return
        mix_key = str(metadata.get("mix_key") or getattr(self, "_active_youtube_mix_key", "supermix") or "supermix")
        self._active_youtube_mix_key = mix_key
        if not hasattr(self, "youtube_mix_catalog") or not isinstance(self.youtube_mix_catalog, dict):
            self.youtube_mix_catalog = {}
        if isinstance(metadata.get("catalog"), dict):
            self.youtube_mix_catalog.update(metadata["catalog"])
        cover_url = str(metadata.get("cover_url") or "")
        if mix_id:
            prev_entry = self.youtube_mix_catalog.get(mix_key) if isinstance(self.youtube_mix_catalog.get(mix_key), dict) else {}
            self.youtube_mix_catalog[mix_key] = {
                "mix_id": mix_id,
                "title": str(metadata.get("mix_title") or prev_entry.get("title") or ""),
                "description": str(prev_entry.get("description") or ""),
                "cover_url": cover_url or str(prev_entry.get("cover_url") or ""),
            }
        session = {"mix_id": mix_id, "seen": {self.youtube_video_id(t) for t in result},
                   "anchor": "", "waiting": False, "failures": 0}
        if mix_key != "supermix":
            session["mix_key"] = mix_key
        if mix_key == "supermix" and cover_url:
            self.supermix_cover_url = cover_url
            self.settings.setValue("supermix_cover_url", cover_url)
        if not hasattr(self, "youtube_mix_covers") or not isinstance(self.youtube_mix_covers, dict):
            self.youtube_mix_covers = {}
        if cover_url:
            self.youtube_mix_covers[mix_key] = cover_url
        for cat_key, cat_info in self.youtube_mix_catalog.items():
            if isinstance(cat_info, dict) and cat_info.get("cover_url"):
                self.youtube_mix_covers[cat_key] = str(cat_info["cover_url"])
                if cat_key == "supermix" and not self.supermix_cover_url:
                    self.supermix_cover_url = str(cat_info["cover_url"])
        try:
            self.settings.setValue("youtube_mix_catalog_json", json.dumps(self.youtube_mix_catalog, ensure_ascii=False))
        except Exception:
            pass
        titles = {k: title for k, title, _, _, _ in self.YOUTUBE_EXTRA_MIX_SPECS}
        mix_label = "My Supermix" if mix_key == "supermix" else titles.get(mix_key, metadata.get("mix_title") or "Микс YouTube Music")
        self._start_music_queue(result, "youtube", f"{mix_label} · {len(result)} треков · продолжение загружается автоматически.",
                                recommendations=True, supermix_session=session)
        self._update_supermix_cover()
        self._update_youtube_mix_covers()

    def _update_supermix_cover(self):
        if self.supermix_cover_url:
            for card in self.start_cards:
                if card.title == "Супермикс":
                    self.request_card_cover(self.supermix_cover_url, card)

    def _update_youtube_mix_covers(self):
        covers = getattr(self, "youtube_mix_covers", {}) or {}
        catalog = getattr(self, "youtube_mix_catalog", {}) or {}
        for card in getattr(self, "youtube_mix_cards", []):
            key = getattr(card, "artwork_style", "")
            url = covers.get(key) or (catalog.get(key) or {}).get("cover_url") or ""
            if url:
                self.request_card_cover(url, card)
            cat_desc = str((catalog.get(key) or {}).get("description") or "").strip()
            if cat_desc and card.subtitle != cat_desc:
                card.subtitle = cat_desc
                card.setToolTip(f"{card.title} — {cat_desc}")
                card.update()

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

    def maybe_refill_supermix(self):
        session = self.supermix_session
        if (session is None or self.queue_mode != "supermix" or self._force_exit
                or self.supermix_refill_worker is not None or self.supermix_retry_timer.isActive()):
            return
        index = self.requested_index if self.requested_track is not None else self.current_queue_index
        remaining = len(self.queue_tracks) - max(-1, index) - 1
        if remaining > 5 and not session["waiting"]:
            return
        worker = self._make_supermix_worker(
            mix_id=session["mix_id"], anchor=session["anchor"],
            excluded_ids=session["seen"] | self._youtube_disliked_video_ids()
        )
        self.supermix_refill_worker = worker
        worker.result_ready.connect(
            lambda tracks, meta, w=worker, ss=session: self.on_supermix_refill_ready(w, ss, tracks))
        worker.failed.connect(
            lambda message, w=worker, ss=session: self.on_supermix_refill_error(w, ss, message))
        worker.finished.connect(lambda w=worker, ss=session: self.on_supermix_refill_finished(w, ss))
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _is_current_supermix_refill(self, worker, session):
        return (session is self.supermix_session and worker is self.supermix_refill_worker
                and self.queue_mode == "supermix" and not self._force_exit)

    def on_supermix_refill_ready(self, worker, session, tracks):
        if not self._is_current_supermix_refill(worker, session):
            return
        fresh = self._fresh_supermix_tracks(tracks, session["seen"])
        if not fresh:
            self.on_supermix_refill_error(worker, session, "My Supermix пока не вернул новых песен.")
            return
        session["failures"] = 0
        self.supermix_retry_timer.stop()
        for track in fresh:
            track["queue_id"] = uuid4().hex
            self.queue_tracks.append(track)
            session["seen"].add(self.youtube_video_id(track))
            self.append_queue_item(track, len(self.queue_tracks) - 1)
        self.update_queue_count()
        self.shuffle_future = None
        if session["waiting"] and self.requested_track is None and self.pending_slot is None:
            session["waiting"] = False
            index = self.peek_next_index()
            if index is not None:
                self._finish_transition_pending = True
                self._finish_guard_url = str((self.current_track or {}).get("url") or "")
                self.play_queue_index(index)
        else:
            QTimer.singleShot(0, self.prepare_next_track)

    def on_supermix_refill_error(self, worker, session, message):
        if not self._is_current_supermix_refill(worker, session):
            return
        session["failures"] += 1
        # Пустые ответы и сбои не вызывают цикл запросов; новая попытка — с задержкой.
        delay = (5, 15, 30, 60)[min(session["failures"] - 1, 3)]
        self.supermix_retry_timer.start(delay * 1000)
        self.set_status(message + f" Повторю через {delay} с.", "youtube")

    def on_supermix_refill_finished(self, worker, session):
        if self._is_current_supermix_refill(worker, session):
            self.supermix_refill_worker = None
            if not self.supermix_retry_timer.isActive():
                # Небольшая порция может оставить очередь ниже порога.
                QTimer.singleShot(0, self.maybe_refill_supermix)

    def _wait_for_supermix(self):
        self._finish_transition_pending = False
        if self.supermix_session is not None:
            self.supermix_session["waiting"] = True
            self.set_status("My Supermix: жду продолжение очереди…", "youtube")
            self.refresh_supermix_card()
            self.maybe_refill_supermix()

    def _start_music_queue(self, tracks, source, message, recommendations=False, supermix_session=None):
        self._stop_supermix_session()
        self.cancel_pending_request()
        self.queue_tracks = []
        self._queue_live_rows.clear()
        self.queue_list.clear()
        self.current_queue_index = -1
        self.shuffle_future = None
        self.radio_mode_active = False
        # Кнопки Next и автопереход остаются внутри очереди лайков.
        self.queue_mode = "supermix" if recommendations else ("youtube_likes" if source == "youtube" else "manual")
        self.supermix_session = supermix_session
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
        self.refresh_home_likes_counts()
        auth = self.soundcloud_auth_kwargs()
        for kind, url in (("likes", base + "/likes"),):
            worker = SearchWorker(
                "", "soundcloud", "relevance", 100, self,
                direct_url=url, cache_enabled=False,
                paginate_all=(kind == "likes"), max_total=10000, **auth
            )
            self.soundcloud_profile_workers[kind] = worker
            self.refresh_connection_badge()
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
        youtube_count = len(self._youtube_likes_for_display())
        soundcloud_count = sum(bool(isinstance(t, dict) and t.get("url")) for t in self.soundcloud_liked_tracks)
        local_count = sum(bool(isinstance(t, dict) and t.get("url")) for t in self.favorites.values())
        combined_count = len(self.get_combined_likes())
        self.likes_tabs.setTabText(0, f"YouTube Music · {youtube_count}")
        self.likes_tabs.setTabText(1, f"SoundCloud · {soundcloud_count}")
        self.likes_tabs.setTabText(2, f"Мои лайки · {local_count}")
        self.likes_title.setText(f"{combined_count} треков в библиотеке")
        self.refresh_home_likes_counts({"youtube": youtube_count, "soundcloud": soundcloud_count})
        self.refresh_connection_badge()
        self._update_likes_collage()

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
        self.refresh_home_likes_counts()
        self.refresh_connection_badge()

    def on_soundcloud_account_finished(self, kind, worker):
        if self.soundcloud_profile_workers.get(kind) is not worker:
            return
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
        self.refresh_home_likes_counts()
        self.refresh_connection_badge()

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

    # ---------------------------------------------------------
    # Локальные пользовательские плейлисты и папки (Drag & Drop + Экспорт/Импорт)
    # ---------------------------------------------------------

    @staticmethod
    def _sanitize_playlist_track(track):
        if not isinstance(track, dict):
            return None
        url = str(track.get("url") or "").strip()
        if not url:
            return None
        source = str(track.get("source") or "").strip()
        if source not in ("youtube", "soundcloud", "local"):
            lower = url.lower()
            if "soundcloud.com" in lower:
                source = "soundcloud"
            elif any(h in lower for h in ("youtube.com", "youtu.be")):
                source = "youtube"
            else:
                source = "local"
        cleaned = {
            "source": source,
            "url": url,
            "title": str(track.get("title") or Path(url).stem or "Без названия").strip(),
            "artist": str(track.get("artist") or track.get("artist_display") or "Исполнитель неизвестен").strip(),
        }
        for optional_key in ("artist_display", "profile_artist_name", "artist_url", "thumbnail", "video_id"):
            if track.get(optional_key):
                cleaned[optional_key] = str(track[optional_key])
        if track.get("duration") not in (None, ""):
            try:
                cleaned["duration"] = int(float(track["duration"]))
            except (TypeError, ValueError):
                pass
        return cleaned

    @staticmethod
    def _russian_track_count(count):
        count = max(0, int(count or 0))
        if 11 <= count % 100 <= 14:
            word = "треков"
        elif count % 10 == 1:
            word = "трек"
        elif 2 <= count % 10 <= 4:
            word = "трека"
        else:
            word = "треков"
        return f"{count} {word}"

    def load_user_playlists(self):
        self.user_playlist_folders = []
        self.collapsed_playlist_folders = set()
        playlists = []
        try:
            if hasattr(self, "user_playlists_file") and self.user_playlists_file.exists():
                raw = json.loads(self.user_playlists_file.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    folders = raw.get("folders", [])
                    if isinstance(folders, list):
                        for fname in folders:
                            cleaned_f = str(fname or "").strip()
                            if cleaned_f and cleaned_f not in self.user_playlist_folders:
                                self.user_playlist_folders.append(cleaned_f)
                    collapsed = raw.get("collapsed_folders", [])
                    if isinstance(collapsed, list):
                        self.collapsed_playlist_folders = {str(f).strip() for f in collapsed if str(f).strip()}
                    raw_list = raw.get("playlists", [])
                elif isinstance(raw, list):
                    raw_list = raw
                else:
                    raw_list = []
                for item in raw_list:
                    if not isinstance(item, dict) or not str(item.get("title") or "").strip():
                        continue
                    pid = str(item.get("id") or f"pl_{uuid4().hex[:10]}")
                    folder = str(item.get("folder") or "").strip()
                    if folder and folder not in self.user_playlist_folders:
                        self.user_playlist_folders.append(folder)
                    tracks = []
                    for t in item.get("tracks", []) if isinstance(item.get("tracks"), list) else []:
                        clean_t = self._sanitize_playlist_track(t)
                        if clean_t is not None:
                            tracks.append(clean_t)
                    playlists.append({
                        "id": pid,
                        "title": str(item.get("title")).strip(),
                        "folder": folder,
                        "created_at": float(item.get("created_at") or time.time()),
                        "updated_at": float(item.get("updated_at") or time.time()),
                        "tracks": tracks,
                    })
        except (OSError, ValueError, TypeError) as error:
            logging.getLogger("aurora").info(f"[Music Player] Не удалось загрузить user_playlists.json: {error}")
        return playlists

    def save_user_playlists(self):
        if not hasattr(self, "user_playlists_file"):
            return
        try:
            payload = {
                "version": 1,
                "folders": list(self.user_playlist_folders),
                "collapsed_folders": sorted(self.collapsed_playlist_folders),
                "playlists": self.user_playlists,
            }
            temp = self.user_playlists_file.with_suffix(".tmp")
            temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            temp.replace(self.user_playlists_file)
        except OSError as error:
            logging.getLogger("aurora").warning(f"[Music Player] Не удалось сохранить user_playlists.json: {error}")

    def get_user_playlist_by_id(self, playlist_id):
        pid = str(playlist_id or "").strip()
        if not pid:
            return None
        for pl in getattr(self, "user_playlists", []):
            if isinstance(pl, dict) and pl.get("id") == pid:
                return pl
        return None

    def open_sidebar_add_menu(self):
        menu = self.make_context_menu()
        self._add_menu_action(
            menu, "Создать локальный плейлист…",
            lambda: self.create_user_playlist_dialog(),
            icon_name="playlist-add", accent=True,
        )
        self._add_menu_action(
            menu, "Создать папку плейлистов…",
            lambda: self.create_playlist_folder_dialog(),
            icon_name="folder",
        )
        menu.addSeparator()
        self._add_menu_action(
            menu, "Импортировать плейлист из файла…",
            lambda: self.import_user_playlist_from_file(),
            icon_name="import",
        )
        if getattr(self, "user_playlists", []):
            self._add_menu_action(
                menu, "Экспортировать все плейлисты…",
                lambda: self.export_all_user_playlists(),
                icon_name="export",
            )
        menu.addSeparator()
        self._add_menu_action(
            menu, "Добавить плейлист по ссылке…",
            lambda: self.add_custom_playlist_dialog(),
            icon_name="external",
        )
        btn = getattr(self, "sidebar_add_playlist_button", None)
        pos = btn.mapToGlobal(QPoint(0, btn.height() + 4)) if btn is not None else self.mapToGlobal(QPoint(40, 60))
        menu.exec(pos)

    def create_user_playlist_dialog(self, initial_folder="", initial_track=None):
        dialog = QDialog(self)
        dialog.setWindowTitle("Создать локальный плейлист")
        dialog.setMinimumWidth(460)
        style_dialog_for_theme(dialog, "createUserPlaylistDialog", self.theme)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)

        heading = QLabel("Новый плейлист")
        heading.setObjectName("settingsTitle")
        layout.addWidget(heading)

        name_input = QLineEdit()
        name_input.setPlaceholderText("Например: Ночной драйв, Тренировка, Любимые ремиксы")
        layout.addWidget(QLabel("Название плейлиста"))
        layout.addWidget(name_input)

        folder_combo = QComboBox()
        folder_combo.addItem("Без папки (в корне медиатеки)", "")
        for folder in self.user_playlist_folders:
            folder_combo.addItem(f"Папка: {folder}", folder)
        if initial_folder and initial_folder in self.user_playlist_folders:
            folder_combo.setCurrentIndex(self.user_playlist_folders.index(initial_folder) + 1)

        new_folder_input = QLineEdit()
        new_folder_input.setPlaceholderText("Или введи имя новой папки (необязательно)")
        layout.addWidget(QLabel("Папка"))
        layout.addWidget(folder_combo)
        layout.addWidget(new_folder_input)

        hint = QLabel(
            "В локальный плейлист можно добавлять треки из YouTube Music, SoundCloud и с компьютера, "
            "перетаскивать их мышкой (Drag & Drop) и экспортировать в файл."
        )
        hint.setObjectName("mutedText")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel_btn = QPushButton("Отмена")
        create_btn = QPushButton("Создать")
        create_btn.setObjectName("accentButton")
        buttons.addWidget(cancel_btn)
        buttons.addWidget(create_btn)
        layout.addLayout(buttons)
        cancel_btn.clicked.connect(dialog.reject)

        created_playlist = [None]

        def do_create():
            title = name_input.text().strip()
            if not title:
                QMessageBox.warning(dialog, "Название", "Введи название нового плейлиста.")
                return
            folder = new_folder_input.text().strip() or str(folder_combo.currentData() or "").strip()
            if folder and folder not in self.user_playlist_folders:
                self.user_playlist_folders.append(folder)
            tracks = []
            clean_initial = self._sanitize_playlist_track(initial_track) if initial_track else None
            if clean_initial is not None:
                tracks.append(clean_initial)
            pl = {
                "id": f"pl_{uuid4().hex[:10]}",
                "title": title,
                "folder": folder,
                "created_at": time.time(),
                "updated_at": time.time(),
                "tracks": tracks,
            }
            self.user_playlists.append(pl)
            self.save_user_playlists()
            self._sidebar_library_signature = None
            self.refresh_sidebar_library()
            created_playlist[0] = pl
            dialog.accept()

        create_btn.clicked.connect(do_create)
        name_input.returnPressed.connect(do_create)
        name_input.setFocus()
        if dialog.exec() == QDialog.DialogCode.Accepted and created_playlist[0] is not None:
            pl = created_playlist[0]
            if initial_track is not None:
                self.show_toast(f"Создан плейлист «{pl['title']}» и добавлен трек")
            else:
                self.open_user_playlist(pl["id"])
                self.show_toast(f"Создан плейлист «{pl['title']}»")
            return pl
        return None

    def create_playlist_folder_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Создать папку плейлистов")
        dialog.setMinimumWidth(420)
        style_dialog_for_theme(dialog, "createPlaylistFolderDialog", self.theme)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)

        heading = QLabel("Новая папка")
        heading.setObjectName("settingsTitle")
        layout.addWidget(heading)
        folder_input = QLineEdit()
        folder_input.setPlaceholderText("Название папки (например: По жанрам, В машину, Работа)")
        layout.addWidget(QLabel("Название папки"))
        layout.addWidget(folder_input)
        hint = QLabel("В папки можно перетаскивать плейлисты мышкой прямо в левой панели «Моя медиатека».")
        hint.setObjectName("mutedText")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel_btn = QPushButton("Отмена")
        create_btn = QPushButton("Создать папку")
        create_btn.setObjectName("accentButton")
        buttons.addWidget(cancel_btn)
        buttons.addWidget(create_btn)
        layout.addLayout(buttons)
        cancel_btn.clicked.connect(dialog.reject)

        def do_create_folder():
            name = folder_input.text().strip()
            if not name:
                QMessageBox.warning(dialog, "Папка", "Введи название папки.")
                return
            if name not in self.user_playlist_folders:
                self.user_playlist_folders.append(name)
            self.collapsed_playlist_folders.discard(name)
            self.save_user_playlists()
            self._sidebar_library_signature = None
            self.refresh_sidebar_library()
            self.show_toast(f"Создана папка «{name}»")
            dialog.accept()

        create_btn.clicked.connect(do_create_folder)
        folder_input.returnPressed.connect(do_create_folder)
        folder_input.setFocus()
        dialog.exec()

    def rename_playlist_folder_dialog(self, old_name):
        old_name = str(old_name or "").strip()
        if not old_name:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Переименовать папку")
        dialog.setMinimumWidth(400)
        style_dialog_for_theme(dialog, "renameFolderDialog", self.theme)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)
        heading = QLabel("Переименовать папку")
        heading.setObjectName("settingsTitle")
        layout.addWidget(heading)
        inp = QLineEdit(old_name)
        layout.addWidget(inp)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel_btn = QPushButton("Отмена")
        save_btn = QPushButton("Сохранить")
        save_btn.setObjectName("accentButton")
        buttons.addWidget(cancel_btn)
        buttons.addWidget(save_btn)
        layout.addLayout(buttons)
        cancel_btn.clicked.connect(dialog.reject)

        def do_rename():
            new_name = inp.text().strip()
            if not new_name:
                return
            if new_name != old_name:
                self.user_playlist_folders = [new_name if f == old_name else f for f in self.user_playlist_folders]
                # Убираем дубликаты с сохранением порядка
                seen_f = []
                for f in self.user_playlist_folders:
                    if f not in seen_f:
                        seen_f.append(f)
                self.user_playlist_folders = seen_f
                if old_name in self.collapsed_playlist_folders:
                    self.collapsed_playlist_folders.discard(old_name)
                    self.collapsed_playlist_folders.add(new_name)
                for pl in self.user_playlists:
                    if pl.get("folder") == old_name:
                        pl["folder"] = new_name
                self.save_user_playlists()
                self._sidebar_library_signature = None
                self.refresh_sidebar_library()
                if self.active_user_playlist_id:
                    self.refresh_active_user_playlist_view()
            dialog.accept()

        save_btn.clicked.connect(do_rename)
        inp.returnPressed.connect(do_rename)
        inp.selectAll()
        inp.setFocus()
        dialog.exec()

    def delete_playlist_folder(self, folder_name):
        folder_name = str(folder_name or "").strip()
        if not folder_name:
            return
        in_folder = [pl for pl in self.user_playlists if pl.get("folder") == folder_name]
        msg = (
            f"Удалить папку «{folder_name}»?\n"
            f"Плейлисты внутри неё ({len(in_folder)} шт.) не удалятся и переместятся в корень медиатеки."
        )
        ans = QMessageBox.question(
            self, "Удалить папку", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        self.user_playlist_folders = [f for f in self.user_playlist_folders if f != folder_name]
        self.collapsed_playlist_folders.discard(folder_name)
        for pl in self.user_playlists:
            if pl.get("folder") == folder_name:
                pl["folder"] = ""
        self.save_user_playlists()
        self._sidebar_library_signature = None
        self.refresh_sidebar_library()
        if self.active_user_playlist_id:
            self.refresh_active_user_playlist_view()
        self.show_toast(f"Папка «{folder_name}» удалена")

    def toggle_playlist_folder_collapsed(self, folder_name):
        folder_name = str(folder_name or "").strip()
        if not folder_name:
            return
        if folder_name in self.collapsed_playlist_folders:
            self.collapsed_playlist_folders.discard(folder_name)
        else:
            self.collapsed_playlist_folders.add(folder_name)
        self.save_user_playlists()
        self._sidebar_library_signature = None
        self.refresh_sidebar_library()

    def open_sidebar_folder_menu(self, folder_name, widget, pos):
        menu = self.make_context_menu()
        collapsed = folder_name in self.collapsed_playlist_folders
        self._add_menu_action(
            menu, "Развернуть папку" if collapsed else "Свернуть папку",
            lambda f=folder_name: self.toggle_playlist_folder_collapsed(f),
            icon_name="folder", accent=True,
        )
        self._add_menu_action(
            menu, "Новый плейлист в этой папке…",
            lambda f=folder_name: self.create_user_playlist_dialog(initial_folder=f),
            icon_name="playlist-add",
        )
        menu.addSeparator()
        self._add_menu_action(
            menu, "Переименовать папку…",
            lambda f=folder_name: self.rename_playlist_folder_dialog(f),
            icon_name="edit",
        )
        self._add_menu_action(
            menu, "Удалить папку",
            lambda f=folder_name: self.delete_playlist_folder(f),
            icon_name="remove",
        )
        menu.exec(widget.mapToGlobal(pos))

    def open_sidebar_playlist_menu(self, playlist_id, widget, pos):
        pl = self.get_user_playlist_by_id(playlist_id)
        if pl is None:
            return
        menu = self.make_context_menu()
        tracks = pl.get("tracks", [])
        self._add_menu_action(
            menu, "Открыть плейлист",
            lambda pid=playlist_id: self.open_user_playlist(pid),
            icon_name="folder", accent=True,
        )
        self._add_menu_action(
            menu, "Слушать плейлист",
            lambda pid=playlist_id: self.play_user_playlist(pid, 0, shuffle=False),
            icon_name="play", enabled=bool(tracks),
        )
        self._add_menu_action(
            menu, "Перемешать плейлист",
            lambda pid=playlist_id: self.play_user_playlist(pid, 0, shuffle=True),
            icon_name="shuffle", enabled=bool(tracks),
        )
        menu.addSeparator()
        folder_menu = menu.addMenu(menu_action_icon("folder", self.theme), "Переместить в папку")
        folder_menu.setObjectName("darkMenu")
        folder_menu.setStyleSheet(menu.styleSheet())
        current_folder = str(pl.get("folder") or "")
        root_act = folder_menu.addAction(
            ("✓ " if not current_folder else "") + "Без папки (в корень)",
            lambda pid=playlist_id: self.on_sidebar_playlist_dropped_into_folder(pid, ""),
        )
        root_act.setEnabled(bool(current_folder))
        if self.user_playlist_folders:
            folder_menu.addSeparator()
            for fname in self.user_playlist_folders:
                is_cur = fname == current_folder
                folder_menu.addAction(
                    ("✓ " if is_cur else "") + fname,
                    lambda pid=playlist_id, f=fname: self.on_sidebar_playlist_dropped_into_folder(pid, f),
                )
        folder_menu.addSeparator()
        folder_menu.addAction(
            "＋ Новая папка…",
            lambda pid=playlist_id: self.edit_user_playlist_dialog(pid),
        )
        self._add_menu_action(
            menu, "Переименовать / Папка…",
            lambda pid=playlist_id: self.edit_user_playlist_dialog(pid),
            icon_name="edit",
        )
        menu.addSeparator()
        self._add_menu_action(
            menu, "Экспортировать в файл…",
            lambda pid=playlist_id: self.export_user_playlist(pid),
            icon_name="export",
        )
        self._add_menu_action(
            menu, "Импортировать треки из файла…",
            lambda pid=playlist_id: self.import_user_playlist_from_file(target_playlist_id=pid),
            icon_name="import",
        )
        menu.addSeparator()
        self._add_menu_action(
            menu, "Удалить плейлист",
            lambda pid=playlist_id: self.delete_user_playlist(pid),
            icon_name="remove",
        )
        menu.exec(widget.mapToGlobal(pos))

    def on_sidebar_playlist_dropped_into_folder(self, playlist_id, folder_name):
        pl = self.get_user_playlist_by_id(playlist_id)
        if pl is None:
            return
        folder_name = str(folder_name or "").strip()
        if folder_name and folder_name not in self.user_playlist_folders:
            self.user_playlist_folders.append(folder_name)
        pl["folder"] = folder_name
        pl["updated_at"] = time.time()
        if folder_name:
            self.collapsed_playlist_folders.discard(folder_name)
        self.save_user_playlists()
        self._sidebar_library_signature = None
        self.refresh_sidebar_library()
        if self.active_user_playlist_id == playlist_id:
            self.refresh_active_user_playlist_view()
        if folder_name:
            self.show_toast(f"Плейлист «{pl['title']}» перемещён в папку «{folder_name}»")
        else:
            self.show_toast(f"Плейлист «{pl['title']}» перемещён в корень медиатеки")

    def on_sidebar_track_dropped(self, target_id, track):
        target_id = str(target_id or "")
        if target_id.startswith("folder:"):
            folder_name = target_id.split(":", 1)[1]
            in_folder = [pl for pl in self.user_playlists if pl.get("folder") == folder_name]
            if in_folder:
                self.add_track_to_user_playlist(in_folder[0]["id"], track)
            else:
                self.create_user_playlist_dialog(initial_folder=folder_name, initial_track=track)
            return
        self.add_track_to_user_playlist(target_id, track)

    def add_track_to_user_playlist(self, playlist_id, track, insert_index=None, show_feedback=True):
        pl = self.get_user_playlist_by_id(playlist_id)
        clean = self._sanitize_playlist_track(track)
        if pl is None or clean is None:
            return False
        tracks = pl.setdefault("tracks", [])
        if insert_index is not None and 0 <= int(insert_index) <= len(tracks):
            tracks.insert(int(insert_index), clean)
        else:
            tracks.append(clean)
        pl["updated_at"] = time.time()
        self.save_user_playlists()
        self._sidebar_library_signature = None
        self.refresh_sidebar_library()
        if self.active_user_playlist_id == playlist_id:
            self.refresh_active_user_playlist_view()
        if show_feedback:
            self.show_toast(f"Добавлено в «{pl['title']}»: {clean.get('title') or 'трек'}")
        return True

    def open_user_playlist(self, playlist_id):
        pl = self.get_user_playlist_by_id(playlist_id)
        if pl is None:
            return
        if self.current_source in self.saved_queries:
            self.saved_queries[self.current_source] = self.search_input.text()
        self.active_user_playlist_id = pl["id"]
        self._playlist_search_query = ""
        if hasattr(self, "playlist_search_input"):
            self.playlist_search_input.blockSignals(True)
            self.playlist_search_input.clear()
            self.playlist_search_input.blockSignals(False)
        for button in getattr(self, "nav_buttons", []):
            button.setChecked(False)
        self.refresh_active_user_playlist_view()
        self._sync_sidebar_playing_state()
        self.last_library_page = self.playlist_page
        self.fade_to_page(self.playlist_page)

    def on_playlist_search_changed(self, text):
        self._playlist_search_query = str(text or "").strip().casefold()
        self.refresh_active_user_playlist_view()

    def refresh_active_user_playlist_view(self):
        if not hasattr(self, "playlist_page"):
            return
        pl = self.get_user_playlist_by_id(self.active_user_playlist_id)
        if pl is None:
            return
        folder = str(pl.get("folder") or "").strip()
        self.playlist_folder_badge.setText(
            f"ПАПКА: {folder.upper()}  •  ЛОКАЛЬНЫЙ ПЛЕЙЛИСТ" if folder else "ЛОКАЛЬНЫЙ ПЛЕЙЛИСТ"
        )
        self.playlist_title_button.setText(str(pl.get("title") or "Мой плейлист"))
        all_tracks = [t for t in pl.get("tracks", []) if isinstance(t, dict) and t.get("url")]
        total_sec = sum(max(0, int(t.get("duration") or 0)) for t in all_tracks)
        dur_part = f" • {max(1, total_sec // 60)} мин" if total_sec >= 60 else ""
        self.playlist_meta_label.setText(
            f"{self._russian_track_count(len(all_tracks))}{dur_part} • Перетаскивай треки мышкой (Drag & Drop) для сортировки"
        )
        self.playlist_play_button.setEnabled(bool(all_tracks))
        self.playlist_shuffle_button.setEnabled(bool(all_tracks))

        cover_url = next((normalize_artwork_url(t.get("thumbnail", "")) for t in all_tracks if t.get("thumbnail")), "")
        self.playlist_header.setStyleSheet("")
        if cover_url:
            self.request_image(cover_url, self.playlist_cover_label)
        else:
            self.playlist_cover_label.setProperty("requested_image", "")
            self.playlist_cover_label.setPixmap(make_service_artwork("user_playlist", 248))

        query = str(getattr(self, "_playlist_search_query", "") or "").strip().casefold()
        filtered = []
        for real_index, track in enumerate(all_tracks):
            if query:
                haystack = f"{track.get('title', '')} {track.get('artist', '')} {track.get('artist_display', '')}".casefold()
                if query not in haystack:
                    continue
            filtered.append((real_index, track))

        self.user_playlist_empty.setVisible(not all_tracks)
        self.user_playlist_list.setUpdatesEnabled(False)
        self.user_playlist_list.clear()
        for display_pos, (real_index, track) in enumerate(filtered, start=1):
            item = QListWidgetItem()
            item_track = dict(track)
            item_track["_playlist_index"] = real_index
            item.setData(Qt.ItemDataRole.UserRole, item_track)
            item.setSizeHint(QSize(200, 72))
            self.user_playlist_list.addItem(item)
            row = self._create_user_playlist_row(item, item_track, real_index, display_pos)
            row.drag_source_kind = f"user_playlist:{pl['id']}"
            row.drag_source_index = real_index
        self.user_playlist_list.setUpdatesEnabled(True)
        self.schedule_visible_artwork(self.user_playlist_list)

    def _create_user_playlist_row(self, item, track, real_index, display_pos):
        pid = self.active_user_playlist_id
        youtube_rating_row = str(track.get("source") or "") == "youtube"
        row = TrackRow(
            track,
            is_favorite=(self.is_youtube_music_liked(track) if youtube_rating_row else self.is_favorite(track)),
            index=display_pos,
            parent=self.user_playlist_list.viewport(),
            show_source=True,
        )
        self.user_playlist_list.setItemWidget(item, row)
        row.play_button.clicked.connect(
            lambda checked=False, p=pid, idx=real_index: self.play_user_playlist(p, idx, shuffle=False)
        )
        row.play_requested.connect(
            lambda _t, p=pid, idx=real_index: self.play_user_playlist(p, idx, shuffle=False)
        )
        row.artist_requested.connect(
            lambda artist_data, src=track.get("source"): self.search_artist_name(artist_data, src)
        )
        if youtube_rating_row:
            row.favorite_button.clicked.connect(
                lambda checked=False, t=dict(track), b=row.favorite_button:
                    self.set_youtube_music_like(t, bool(checked), b)
            )
        else:
            row.favorite_button.clicked.connect(
                lambda checked=False, t=dict(track), b=row.favorite_button: self.toggle_favorite(t, b)
            )
        self.set_pixmap_safe(row.thumbnail_label, self.fallback_cover)
        current = self.current_track or {}
        matches = bool(
            current.get("url")
            and current.get("url") == track.get("url")
            and current.get("source") == track.get("source")
        )
        row.set_playing(matches, matches and self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState)
        requested = self.requested_track or {}
        if requested.get("url") == track.get("url") and requested.get("source") == track.get("source"):
            row.set_loading(True)
        return row

    def play_user_playlist(self, playlist_id, start_index=0, shuffle=False):
        pl = self.get_user_playlist_by_id(playlist_id)
        if pl is None:
            return
        tracks = [dict(t) for t in pl.get("tracks", []) if isinstance(t, dict) and t.get("url")]
        if not tracks:
            self.show_toast("В этом плейлисте пока нет треков")
            return
        if shuffle:
            random.shuffle(tracks)
            ordered = tracks
        else:
            start_index = max(0, min(int(start_index or 0), len(tracks) - 1))
            ordered = tracks[start_index:] + tracks[:start_index]
        self._stop_supermix_session()
        self.cancel_pending_request()
        self.queue_tracks = []
        self._queue_live_rows.clear()
        self.queue_list.clear()
        self.current_queue_index = -1
        self.shuffle_future = None
        self.radio_mode_active = False
        self.queue_mode = f"user_playlist:{pl['id']}"
        for item in ordered:
            queued = dict(item)
            queued["queue_id"] = uuid4().hex
            self.queue_tracks.append(queued)
        self.refresh_queue_list()
        self.update_queue_count()
        self.toggle_queue_if_hidden()
        self._sync_sidebar_playing_state()
        self.play_queue_index(0)

    def play_active_user_playlist(self, shuffle=False):
        if self.active_user_playlist_id:
            self.play_user_playlist(self.active_user_playlist_id, 0, shuffle=shuffle)

    def remove_track_from_user_playlist(self, playlist_id, track_index):
        pl = self.get_user_playlist_by_id(playlist_id)
        if pl is None:
            return
        tracks = pl.get("tracks", [])
        if not (0 <= int(track_index) < len(tracks)):
            return
        removed = tracks.pop(int(track_index))
        pl["updated_at"] = time.time()
        self.save_user_playlists()
        self._sidebar_library_signature = None
        self.refresh_sidebar_library()
        if self.active_user_playlist_id == playlist_id:
            self.refresh_active_user_playlist_view()
        self.show_toast(f"Удалено из «{pl['title']}»: {removed.get('title') or 'трек'}")

    def move_track_in_user_playlist(self, playlist_id, from_index, to_index):
        pl = self.get_user_playlist_by_id(playlist_id)
        if pl is None:
            return
        tracks = pl.get("tracks", [])
        n = len(tracks)
        if not (0 <= from_index < n):
            return
        to_index = max(0, min(int(to_index), n))
        if from_index == to_index or from_index + 1 == to_index:
            return
        item = tracks.pop(from_index)
        if to_index > from_index:
            to_index -= 1
        tracks.insert(to_index, item)
        pl["updated_at"] = time.time()
        self.save_user_playlists()
        self._sidebar_library_signature = None
        self.refresh_sidebar_library()
        if self.active_user_playlist_id == playlist_id:
            self.refresh_active_user_playlist_view()

    def on_user_playlist_track_dropped(self, target_row, track, source_kind, source_index):
        pid = self.active_user_playlist_id
        if not pid:
            return
        if source_kind == f"user_playlist:{pid}" and source_index >= 0 and not self._playlist_search_query:
            self.move_track_in_user_playlist(pid, source_index, target_row)
        else:
            self.add_track_to_user_playlist(pid, track, insert_index=target_row)

    def on_user_playlist_files_dropped(self, paths):
        pid = self.active_user_playlist_id
        if not pid or not paths:
            return
        self._import_dropped_files(paths, target_playlist_id=pid)

    def on_queue_track_dropped(self, target_row, track, source_kind, source_index):
        if source_kind == "queue" and 0 <= source_index < len(self.queue_tracks):
            n = len(self.queue_tracks)
            target_row = max(0, min(int(target_row), n))
            if source_index == target_row or source_index + 1 == target_row:
                return
            moved = self.queue_tracks.pop(source_index)
            if target_row > source_index:
                target_row -= 1
            self.queue_tracks.insert(target_row, moved)
            self.shuffle_future = None
            self.refresh_queue_list()
            if self.current_track is not None:
                QTimer.singleShot(0, self.prepare_next_track)
            return
        clean = self._sanitize_playlist_track(track)
        if clean is None:
            return
        self._stop_supermix_session()
        self.queue_mode = "manual"
        queued = dict(clean)
        queued["queue_id"] = uuid4().hex
        target_row = max(0, min(int(target_row), len(self.queue_tracks)))
        self.queue_tracks.insert(target_row, queued)
        self.refresh_queue_list()
        self.show_toast(f"Добавлено в очередь: {queued.get('title') or 'трек'}")
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.prepare_next_track()

    def on_queue_files_dropped(self, paths):
        if not paths:
            return
        tracks = []
        for p in paths:
            tracks.extend(self._extract_tracks_from_file_path(Path(p)))
        if not tracks:
            return
        for t in tracks:
            self.add_to_queue(t, False)
        self.show_toast(f"Добавлено в очередь: {self._russian_track_count(len(tracks))}")

    def add_current_queue_to_active_playlist(self):
        pl = self.get_user_playlist_by_id(self.active_user_playlist_id)
        if pl is None:
            return
        candidates = list(self.queue_tracks)
        if not candidates and isinstance(self.current_track, dict):
            candidates = [self.current_track]
        if not candidates:
            self.show_toast("Очередь сейчас пуста")
            return
        existing_urls = {str(t.get("url") or "") for t in pl.get("tracks", [])}
        added = 0
        for item in candidates:
            clean = self._sanitize_playlist_track(item)
            if clean and clean["url"] not in existing_urls:
                pl.setdefault("tracks", []).append(clean)
                existing_urls.add(clean["url"])
                added += 1
        if added:
            pl["updated_at"] = time.time()
            self.save_user_playlists()
            self._sidebar_library_signature = None
            self.refresh_sidebar_library()
            self.refresh_active_user_playlist_view()
            self.show_toast(f"В «{pl['title']}» добавлено {self._russian_track_count(added)} из очереди")
        else:
            self.show_toast("Все треки из очереди уже есть в этом плейлисте")

    def edit_active_user_playlist(self):
        if self.active_user_playlist_id:
            self.edit_user_playlist_dialog(self.active_user_playlist_id)

    def edit_user_playlist_dialog(self, playlist_id):
        pl = self.get_user_playlist_by_id(playlist_id)
        if pl is None:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Настройки плейлиста")
        dialog.setMinimumWidth(450)
        style_dialog_for_theme(dialog, "editUserPlaylistDialog", self.theme)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)

        heading = QLabel("Изменить плейлист")
        heading.setObjectName("settingsTitle")
        layout.addWidget(heading)

        name_input = QLineEdit(str(pl.get("title") or ""))
        layout.addWidget(QLabel("Название"))
        layout.addWidget(name_input)

        folder_combo = QComboBox()
        folder_combo.addItem("Без папки (в корне медиатеки)", "")
        current_folder = str(pl.get("folder") or "").strip()
        for folder in self.user_playlist_folders:
            folder_combo.addItem(f"Папка: {folder}", folder)
        if current_folder and current_folder in self.user_playlist_folders:
            folder_combo.setCurrentIndex(self.user_playlist_folders.index(current_folder) + 1)

        new_folder_input = QLineEdit()
        new_folder_input.setPlaceholderText("Или создай новую папку и перемести туда")
        layout.addWidget(QLabel("Папка"))
        layout.addWidget(folder_combo)
        layout.addWidget(new_folder_input)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel_btn = QPushButton("Отмена")
        save_btn = QPushButton("Сохранить")
        save_btn.setObjectName("accentButton")
        buttons.addWidget(cancel_btn)
        buttons.addWidget(save_btn)
        layout.addLayout(buttons)
        cancel_btn.clicked.connect(dialog.reject)

        def do_save():
            title = name_input.text().strip()
            if not title:
                QMessageBox.warning(dialog, "Название", "Название плейлиста не может быть пустым.")
                return
            folder = new_folder_input.text().strip() or str(folder_combo.currentData() or "").strip()
            if folder and folder not in self.user_playlist_folders:
                self.user_playlist_folders.append(folder)
            pl["title"] = title
            pl["folder"] = folder
            pl["updated_at"] = time.time()
            self.save_user_playlists()
            self._sidebar_library_signature = None
            self.refresh_sidebar_library()
            if self.active_user_playlist_id == playlist_id:
                self.refresh_active_user_playlist_view()
            self.show_toast(f"Плейлист «{title}» обновлён")
            dialog.accept()

        save_btn.clicked.connect(do_save)
        name_input.returnPressed.connect(do_save)
        name_input.selectAll()
        name_input.setFocus()
        dialog.exec()

    def delete_user_playlist(self, playlist_id):
        pl = self.get_user_playlist_by_id(playlist_id)
        if pl is None:
            return
        title = str(pl.get("title") or "Плейлист")
        ans = QMessageBox.question(
            self, "Удалить плейлист",
            f"Удалить локальный плейлист «{title}» ({self._russian_track_count(len(pl.get('tracks', [])))})?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        self.user_playlists = [item for item in self.user_playlists if item.get("id") != playlist_id]
        self.save_user_playlists()
        was_active = self.active_user_playlist_id == playlist_id
        if was_active:
            self.active_user_playlist_id = ""
            self.set_source(self.current_source if self.current_source in ("youtube", "soundcloud", "likes") else "youtube")
        self._sidebar_library_signature = None
        self.refresh_sidebar_library()
        self.show_toast(f"Плейлист «{title}» удалён")

    def export_user_playlist(self, playlist_id):
        pl = self.get_user_playlist_by_id(playlist_id)
        if pl is None:
            return
        safe_name = DownloadWorker._sanitize_filename(pl.get("title") or "playlist")
        default_path = str(self.get_download_directory() / f"{safe_name}.json")
        filename, selected_filter = QFileDialog.getSaveFileName(
            self,
            f"Экспортировать плейлист «{pl.get('title')}»",
            default_path,
            "Плейлист Aurora JSON (*.json);;Плейлист M3U8 (*.m3u8 *.m3u)",
        )
        if not filename:
            return
        target = Path(filename)
        if "m3u" in (selected_filter or "").lower() or target.suffix.lower() in (".m3u", ".m3u8"):
            if target.suffix.lower() not in (".m3u", ".m3u8"):
                target = target.with_suffix(".m3u8")
            lines = ["#EXTM3U", f"#PLAYLIST:{pl.get('title') or 'Плейлист'}"]
            if pl.get("folder"):
                lines.append(f"#EXTGRP:{pl.get('folder')}")
            for t in pl.get("tracks", []):
                dur = int(t.get("duration") or -1)
                artist = str(t.get("artist") or "Unknown").replace("\n", " ")
                title = str(t.get("title") or "Track").replace("\n", " ")
                lines.append(f"#EXTINF:{dur},{artist} - {title}")
                if t.get("thumbnail"):
                    lines.append(f"#EXTIMG:{t['thumbnail']}")
                lines.append(str(t.get("url") or ""))
            try:
                target.write_text("\n".join(lines) + "\n", encoding="utf-8")
                self.show_toast(f"Плейлист экспортирован в {target.name}")
            except OSError as error:
                QMessageBox.warning(self, "Ошибка экспорта", f"Не удалось записать файл:\n{error}")
            return

        if target.suffix.lower() != ".json":
            target = target.with_suffix(".json")
        payload = {
            "format": "aurora_playlist_v1",
            "exported_at": datetime.now().isoformat(timespec="seconds"),
            "title": pl.get("title") or "Мой плейлист",
            "folder": pl.get("folder") or "",
            "tracks": pl.get("tracks", []),
        }
        try:
            target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            self.show_toast(f"Плейлист экспортирован в {target.name}")
        except OSError as error:
            QMessageBox.warning(self, "Ошибка экспорта", f"Не удалось записать файл:\n{error}")

    def export_all_user_playlists(self):
        if not getattr(self, "user_playlists", []):
            self.show_toast("Нет локальных плейлистов для экспорта")
            return
        default_path = str(self.get_download_directory() / "aurora_playlists_backup.json")
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Экспортировать все плейлисты и папки",
            default_path,
            "Архив плейлистов Aurora JSON (*.json)",
        )
        if not filename:
            return
        target = Path(filename)
        if target.suffix.lower() != ".json":
            target = target.with_suffix(".json")
        payload = {
            "format": "aurora_playlists_bundle_v1",
            "exported_at": datetime.now().isoformat(timespec="seconds"),
            "folders": list(self.user_playlist_folders),
            "playlists": self.user_playlists,
        }
        try:
            target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            self.show_toast(f"Экспортировано плейлистов: {len(self.user_playlists)}")
        except OSError as error:
            QMessageBox.warning(self, "Ошибка экспорта", f"Не удалось сохранить файл:\n{error}")

    def _extract_tracks_from_file_path(self, path: Path):
        suffix = path.suffix.lower()
        if suffix in (".mp3", ".flac", ".m4a", ".wav", ".ogg", ".opus"):
            stem = path.stem
            if " - " in stem:
                artist, title = stem.split(" - ", 1)
            else:
                artist, title = "Локальный файл", stem
            return [{
                "source": "local",
                "url": QUrl.fromLocalFile(str(path.resolve())).toString(),
                "title": title.strip() or stem,
                "artist": artist.strip() or "Локальный файл",
            }]
        if suffix in (".m3u", ".m3u8"):
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                return []
            tracks = []
            pending_title = ""
            pending_artist = ""
            pending_dur = None
            pending_img = ""
            for raw_line in content.splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                if line.startswith("#EXTINF:"):
                    meta = line[len("#EXTINF:"):]
                    if "," in meta:
                        dur_str, label = meta.split(",", 1)
                        try:
                            d_val = int(float(dur_str.strip().split()[0]))
                            pending_dur = d_val if d_val > 0 else None
                        except (ValueError, IndexError):
                            pending_dur = None
                    else:
                        label = meta
                    if " - " in label:
                        pending_artist, pending_title = label.split(" - ", 1)
                    else:
                        pending_artist, pending_title = "", label
                elif line.startswith("#EXTIMG:"):
                    pending_img = line[len("#EXTIMG:"):].strip()
                elif not line.startswith("#"):
                    url = line
                    if not url.startswith(("http://", "https://", "file://")):
                        candidate = (path.parent / url).resolve()
                        if candidate.exists():
                            url = QUrl.fromLocalFile(str(candidate)).toString()
                    raw_track = {
                        "url": url,
                        "title": pending_title.strip() or Path(url).stem or "Трек",
                        "artist": pending_artist.strip() or "Исполнитель неизвестен",
                    }
                    if pending_dur:
                        raw_track["duration"] = pending_dur
                    if pending_img:
                        raw_track["thumbnail"] = pending_img
                    clean = self._sanitize_playlist_track(raw_track)
                    if clean is not None:
                        tracks.append(clean)
                    pending_title = ""
                    pending_artist = ""
                    pending_dur = None
                    pending_img = ""
            return tracks
        if suffix == ".json":
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return []
            raw_tracks = []
            if isinstance(data, list):
                raw_tracks = data
            elif isinstance(data, dict):
                if isinstance(data.get("tracks"), list):
                    raw_tracks = data["tracks"]
                elif isinstance(data.get("playlists"), list):
                    for pl in data["playlists"]:
                        if isinstance(pl, dict) and isinstance(pl.get("tracks"), list):
                            raw_tracks.extend(pl["tracks"])
            return [t for t in (self._sanitize_playlist_track(item) for item in raw_tracks) if t is not None]
        return []

    def _import_dropped_files(self, paths, target_playlist_id=None):
        imported_tracks = []
        for raw_p in paths:
            p = Path(raw_p)
            if p.is_file():
                imported_tracks.extend(self._extract_tracks_from_file_path(p))
        if not imported_tracks:
            return
        pl = self.get_user_playlist_by_id(target_playlist_id)
        if pl is not None:
            pl.setdefault("tracks", []).extend(imported_tracks)
            pl["updated_at"] = time.time()
            self.save_user_playlists()
            self._sidebar_library_signature = None
            self.refresh_sidebar_library()
            if self.active_user_playlist_id == pl["id"]:
                self.refresh_active_user_playlist_view()
            self.show_toast(f"Импортировано в «{pl['title']}»: {self._russian_track_count(len(imported_tracks))}")

    def import_user_playlist_from_file(self, filepath=None, target_playlist_id=None):
        if not filepath:
            filepath, _ = QFileDialog.getOpenFileName(
                self,
                "Импортировать плейлист из файла",
                str(self.get_download_directory()),
                "Файлы плейлистов (*.json *.m3u8 *.m3u);;JSON плейлисты (*.json);;M3U / M3U8 плейлисты (*.m3u8 *.m3u)",
            )
        if not filepath:
            return
        path = Path(filepath)
        if not path.is_file():
            return

        if path.suffix.lower() == ".json":
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as error:
                QMessageBox.warning(self, "Ошибка импорта", f"Не удалось прочитать JSON-файл:\n{error}")
                return
            if isinstance(data, dict) and isinstance(data.get("playlists"), list) and not target_playlist_id:
                added_count = 0
                for fname in data.get("folders", []) if isinstance(data.get("folders"), list) else []:
                    cf = str(fname or "").strip()
                    if cf and cf not in self.user_playlist_folders:
                        self.user_playlist_folders.append(cf)
                last_id = ""
                for raw_pl in data["playlists"]:
                    if not isinstance(raw_pl, dict) or not str(raw_pl.get("title") or "").strip():
                        continue
                    tracks = [
                        t for t in (self._sanitize_playlist_track(item) for item in (raw_pl.get("tracks") or []))
                        if t is not None
                    ]
                    folder = str(raw_pl.get("folder") or "").strip()
                    if folder and folder not in self.user_playlist_folders:
                        self.user_playlist_folders.append(folder)
                    new_pl = {
                        "id": f"pl_{uuid4().hex[:10]}",
                        "title": str(raw_pl.get("title")).strip(),
                        "folder": folder,
                        "created_at": time.time(),
                        "updated_at": time.time(),
                        "tracks": tracks,
                    }
                    self.user_playlists.append(new_pl)
                    last_id = new_pl["id"]
                    added_count += 1
                if added_count:
                    self.save_user_playlists()
                    self._sidebar_library_signature = None
                    self.refresh_sidebar_library()
                    if last_id:
                        self.open_user_playlist(last_id)
                    self.show_toast(f"Импортировано плейлистов: {added_count}")
                    return

            tracks = self._extract_tracks_from_file_path(path)
            if not tracks and not (isinstance(data, dict) and data.get("title")):
                QMessageBox.warning(self, "Импорт плейлиста", "В выбранном файле не найдено поддерживаемых треков.")
                return
            if target_playlist_id:
                target_pl = self.get_user_playlist_by_id(target_playlist_id)
                if target_pl is not None:
                    target_pl.setdefault("tracks", []).extend(tracks)
                    target_pl["updated_at"] = time.time()
                    self.save_user_playlists()
                    self._sidebar_library_signature = None
                    self.refresh_sidebar_library()
                    if self.active_user_playlist_id == target_pl["id"]:
                        self.refresh_active_user_playlist_view()
                    self.show_toast(f"В «{target_pl['title']}» импортировано {self._russian_track_count(len(tracks))}")
                    return
            title = (str(data.get("title") or "").strip() if isinstance(data, dict) else "") or path.stem
            folder = (str(data.get("folder") or "").strip() if isinstance(data, dict) else "")
            if folder and folder not in self.user_playlist_folders:
                self.user_playlist_folders.append(folder)
            new_pl = {
                "id": f"pl_{uuid4().hex[:10]}",
                "title": title,
                "folder": folder,
                "created_at": time.time(),
                "updated_at": time.time(),
                "tracks": tracks,
            }
            self.user_playlists.append(new_pl)
            self.save_user_playlists()
            self._sidebar_library_signature = None
            self.refresh_sidebar_library()
            self.open_user_playlist(new_pl["id"])
            self.show_toast(f"Импортирован плейлист «{title}» ({self._russian_track_count(len(tracks))})")
            return

        # Импорт .m3u / .m3u8
        tracks = self._extract_tracks_from_file_path(path)
        if not tracks:
            QMessageBox.warning(self, "Импорт плейлиста", "Не удалось найти треки в файле M3U/M3U8.")
            return
        if target_playlist_id:
            target_pl = self.get_user_playlist_by_id(target_playlist_id)
            if target_pl is not None:
                target_pl.setdefault("tracks", []).extend(tracks)
                target_pl["updated_at"] = time.time()
                self.save_user_playlists()
                self._sidebar_library_signature = None
                self.refresh_sidebar_library()
                if self.active_user_playlist_id == target_pl["id"]:
                    self.refresh_active_user_playlist_view()
                self.show_toast(f"В «{target_pl['title']}» импортировано {self._russian_track_count(len(tracks))}")
                return
        playlist_title = path.stem
        try:
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.strip().startswith("#PLAYLIST:"):
                    custom_title = line.strip()[len("#PLAYLIST:"):].strip()
                    if custom_title:
                        playlist_title = custom_title
                    break
        except OSError:
            pass
        new_pl = {
            "id": f"pl_{uuid4().hex[:10]}",
            "title": playlist_title,
            "folder": "",
            "created_at": time.time(),
            "updated_at": time.time(),
            "tracks": tracks,
        }
        self.user_playlists.append(new_pl)
        self.save_user_playlists()
        self._sidebar_library_signature = None
        self.refresh_sidebar_library()
        self.open_user_playlist(new_pl["id"])
        self.show_toast(f"Импортирован плейлист «{playlist_title}» ({self._russian_track_count(len(tracks))})")

    def open_user_playlist_track_menu(self, point):
        item = self.user_playlist_list.itemAt(point)
        if item is None:
            return
        track = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(track, dict):
            return
        real_index = int(track.get("_playlist_index", self.user_playlist_list.row(item)))
        pid = self.active_user_playlist_id
        pl = self.get_user_playlist_by_id(pid)
        total = len(pl.get("tracks", [])) if pl else 0
        menu = self.make_context_menu()
        self._add_menu_action(
            menu, "Воспроизвести с этого трека",
            lambda p=pid, idx=real_index: self.play_user_playlist(p, idx, shuffle=False),
            icon_name="play", accent=True,
        )
        self._populate_track_context_menu(menu, track, include_play=False, include_queue_add=True)
        menu.addSeparator()
        self._add_menu_action(
            menu, "Переместить выше",
            lambda p=pid, idx=real_index: self.move_track_in_user_playlist(p, idx, idx - 1),
            icon_name="arrow-up", enabled=(real_index > 0 and not self._playlist_search_query),
        )
        self._add_menu_action(
            menu, "Переместить ниже",
            lambda p=pid, idx=real_index: self.move_track_in_user_playlist(p, idx, idx + 2),
            icon_name="arrow-down", enabled=(real_index < total - 1 and not self._playlist_search_query),
        )
        menu.addSeparator()
        self._add_menu_action(
            menu, "Удалить из плейлиста",
            lambda p=pid, idx=real_index: self.remove_track_from_user_playlist(p, idx),
            icon_name="remove",
        )
        menu.exec(self.user_playlist_list.viewport().mapToGlobal(point))

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
        tracks = self.soundcloud_liked_tracks if source == "soundcloud" else self._youtube_likes_for_display()
        subtitle = f"{len(tracks)} любимых треков" if tracks else "Вся твоя любимая музыка"
        card = SpotifyPlaylistCard(
            "Мои лайки", subtitle, "♥", "#1DB954", "#181818", self.home_tiles,
            action_icon="open", artwork_style="soundcloud-likes" if source == "soundcloud" else "likes",
            tile_mode=source != "soundcloud"
        )
        card.clicked.connect(lambda checked=False, src=source: self.open_likes_library(src))
        card.setProperty("likes_source", source)
        self.start_cards.append(card)

    def refresh_home_likes_counts(self, counts=None):
        if counts is None:
            counts = {"youtube": len(self._youtube_likes_for_display()),
                      "soundcloud": sum(bool(isinstance(t, dict) and t.get("url"))
                                        for t in self.soundcloud_liked_tracks)}
        for card in self.start_cards:
            source = card.property("likes_source")
            if source not in counts:
                continue
            count = counts[source]
            busy = self.youtube_sync_worker is not None if source == "youtube" else self._soundcloud_likes_loading
            if 11 <= count % 100 <= 14:
                ending, favorite = "треков", "любимых"
            elif count % 10 == 1:
                ending, favorite = "трек", "любимый"
            elif 2 <= count % 10 <= 4:
                ending, favorite = "трека", "любимых"
            else:
                ending, favorite = "треков", "любимых"
            subtitle = (f"{count} {ending} · обновление…" if busy else
                        f"{count} {favorite} {ending}" if count else "Вся твоя любимая музыка")
            if card.subtitle != subtitle:
                card.subtitle = subtitle
                card.setAccessibleName(f"{card.title}: {subtitle}")
                card.setToolTip(f"{card.title} — {subtitle}")
                card.update()
        self.refresh_sidebar_library()

    def _build_sidebar_user_playlist_widget(self, pl, indent_level=0):
        pid = str(pl.get("id") or "")
        title = str(pl.get("title") or "Мой плейлист")
        tracks = pl.get("tracks", []) if isinstance(pl.get("tracks"), list) else []
        subtitle = f"Плейлист • {self._russian_track_count(len(tracks))}"
        item = SidebarMediaItem(
            title, subtitle, "user_playlist", self.sidebar_library_widget,
            playlist_id=pid, folder_name=str(pl.get("folder") or ""), indent_level=indent_level,
        )
        item.track_key = f"user_playlist|{pid}"
        item.clicked.connect(lambda checked=False, p=pid: self.open_user_playlist(p))
        item.track_dropped.connect(self.on_sidebar_track_dropped)
        item.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        item.customContextMenuRequested.connect(
            lambda pos, p=pid, w=item: self.open_sidebar_playlist_menu(p, w, pos)
        )
        cover_url = next((normalize_artwork_url(t.get("thumbnail", "")) for t in tracks if isinstance(t, dict) and t.get("thumbnail")), "")
        if cover_url:
            self.request_image(cover_url, item.cover_label)
        return item

    def refresh_sidebar_library(self):
        """Заполняет блок «Моя медиатека» в левой панели сервисами, миксами, папками и плейлистами."""
        if not hasattr(self, "sidebar_library_layout") or getattr(self, "_force_exit", False):
            return
        source = self.current_source if self.current_source in ("youtube", "soundcloud") else "youtube"
        yt_likes = self._youtube_likes_for_display()
        sc_likes = [t for t in self.soundcloud_liked_tracks if isinstance(t, dict) and t.get("url")]
        active_likes = sc_likes if source == "soundcloud" else yt_likes
        likes_count = len(active_likes)
        likes_subtitle = f"Плейлист • {likes_count} треков" if likes_count else "Плейлист • Любимая музыка"
        if len(getattr(self, "nav_buttons", [])) >= 3 and hasattr(self.nav_buttons[2], "set_subtitle"):
            self.nav_buttons[2].set_subtitle(likes_subtitle)

        custom_entries = tuple(
            (str(p.get("title") or ""), str(p.get("url") or ""), str(p.get("source") or "youtube"))
            for p in getattr(self, "custom_playlists", [])
            if isinstance(p, dict) and p.get("url")
        )
        user_pl_entries = tuple(
            (
                str(p.get("id") or ""),
                str(p.get("title") or ""),
                str(p.get("folder") or ""),
                len(p.get("tracks", [])) if isinstance(p.get("tracks"), list) else 0,
                next((str(t.get("thumbnail") or "") for t in (p.get("tracks") or []) if isinstance(t, dict) and t.get("thumbnail")), ""),
            )
            for p in getattr(self, "user_playlists", [])
            if isinstance(p, dict) and p.get("id")
        )
        folder_entries = tuple(getattr(self, "user_playlist_folders", []))
        collapsed_entries = tuple(sorted(getattr(self, "collapsed_playlist_folders", set())))
        signature = (
            source,
            likes_subtitle,
            str(getattr(self, "supermix_cover_url", "") or ""),
            custom_entries,
            user_pl_entries,
            folder_entries,
            collapsed_entries,
        )
        if signature == getattr(self, "_sidebar_library_signature", None):
            self._sync_sidebar_playing_state()
            return
        self._sidebar_library_signature = signature

        for item in getattr(self, "sidebar_library_items", []):
            self.sidebar_library_layout.removeWidget(item)
            item.hide()
            item.deleteLater()
        self.sidebar_library_items = []

        for idx in range(self.sidebar_library_layout.count() - 1, -1, -1):
            layout_item = self.sidebar_library_layout.itemAt(idx)
            if layout_item is not None and layout_item.widget() is None:
                self.sidebar_library_layout.takeAt(idx)

        supermix_item = SidebarMediaItem("Супермикс", "Микс • YouTube Music", "supermix", self.sidebar_library_widget)
        supermix_item.track_key = "__supermix__"
        supermix_item.clicked.connect(lambda checked=False: self.toggle_supermix())
        self.sidebar_library_layout.addWidget(supermix_item)
        self.sidebar_library_items.append(supermix_item)

        shuffle_item = SidebarMediaItem("Перемешать лайки", "Микс • Из твоих лайков", "shuffle", self.sidebar_library_widget)
        shuffle_item.track_key = "__shuffle__"
        shuffle_item.clicked.connect(lambda checked=False, src=source: self.play_personal_mix(src))
        self.sidebar_library_layout.addWidget(shuffle_item)
        self.sidebar_library_items.append(shuffle_item)

        for mix_key, mix_title, mix_sub, _, _ in self.YOUTUBE_EXTRA_MIX_SPECS:
            short_sub = mix_sub.split("•")[0].strip() + " • YouTube"
            ym_item = SidebarMediaItem(mix_title, short_sub, mix_key, self.sidebar_library_widget)
            ym_item.track_key = f"__ytmix__|{mix_key}"
            ym_item.clicked.connect(lambda checked=False, mk=mix_key: self.toggle_youtube_mix(mk))
            self.sidebar_library_layout.addWidget(ym_item)
            self.sidebar_library_items.append(ym_item)

        # Папки пользовательских плейлистов и вложенные в них плейлисты
        all_folders = list(getattr(self, "user_playlist_folders", []))
        for pl in getattr(self, "user_playlists", []):
            fname = str(pl.get("folder") or "").strip()
            if fname and fname not in all_folders:
                all_folders.append(fname)

        for fname in all_folders:
            folder_playlists = [
                pl for pl in getattr(self, "user_playlists", [])
                if isinstance(pl, dict) and str(pl.get("folder") or "").strip() == fname
            ]
            is_collapsed = fname in getattr(self, "collapsed_playlist_folders", set())
            count_pl = len(folder_playlists)
            sub = f"Папка • {count_pl} плейлистов" if count_pl else "Папка • Перетащи сюда плейлист"
            folder_item = SidebarMediaItem(
                fname, sub, "folder", self.sidebar_library_widget,
                folder_name=fname, is_folder=True, folder_collapsed=is_collapsed,
            )
            folder_item.track_key = f"folder|{fname}"
            folder_item.clicked.connect(lambda checked=False, f=fname: self.toggle_playlist_folder_collapsed(f))
            folder_item.playlist_dropped.connect(self.on_sidebar_playlist_dropped_into_folder)
            folder_item.track_dropped.connect(self.on_sidebar_track_dropped)
            folder_item.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            folder_item.customContextMenuRequested.connect(
                lambda pos, f=fname, w=folder_item: self.open_sidebar_folder_menu(f, w, pos)
            )
            self.sidebar_library_layout.addWidget(folder_item)
            self.sidebar_library_items.append(folder_item)
            if not is_collapsed:
                for pl in folder_playlists:
                    pl_widget = self._build_sidebar_user_playlist_widget(pl, indent_level=1)
                    self.sidebar_library_layout.addWidget(pl_widget)
                    self.sidebar_library_items.append(pl_widget)

        # Локальные плейлисты без папки
        for pl in getattr(self, "user_playlists", []):
            if not isinstance(pl, dict) or str(pl.get("folder") or "").strip():
                continue
            pl_widget = self._build_sidebar_user_playlist_widget(pl, indent_level=0)
            self.sidebar_library_layout.addWidget(pl_widget)
            self.sidebar_library_items.append(pl_widget)

        # Плейлисты по внешней ссылке
        for title, url, pl_source in custom_entries:
            pl_item = SidebarMediaItem(title, "Плейлист • По ссылке", "playlist", self.sidebar_library_widget)
            pl_item.track_key = f"playlist|{url}"
            pl_item.clicked.connect(lambda checked=False, t=title, u=url, s=pl_source: self.start_playlist_url(t, u, s))
            self.sidebar_library_layout.addWidget(pl_item)
            self.sidebar_library_items.append(pl_item)

        self.sidebar_library_layout.addStretch(1)
        self._sync_sidebar_playing_state()

    def _sync_sidebar_playing_state(self):
        session = getattr(self, "supermix_session", None)
        supermix_active = bool(session is not None and getattr(self, "queue_mode", "") == "supermix")
        active_mix_key = (session.get("mix_key") or "supermix") if isinstance(session, dict) else "supermix"
        q_mode = str(getattr(self, "queue_mode", "") or "")
        active_pid = str(getattr(self, "active_user_playlist_id", "") or "")
        for item in getattr(self, "sidebar_library_items", []):
            if item.track_key == "__supermix__":
                item.set_playing(supermix_active and active_mix_key == "supermix")
                item.set_active_selected(False)
            elif item.track_key.startswith("__ytmix__|"):
                mk = item.track_key.split("|", 1)[1]
                item.set_playing(supermix_active and active_mix_key == mk)
                item.set_active_selected(False)
            elif item.track_key.startswith("user_playlist|"):
                pid = item.track_key.split("|", 1)[1]
                item.set_playing(q_mode == f"user_playlist:{pid}")
                item.set_active_selected(pid == active_pid)
            else:
                item.set_playing(False)
                item.set_active_selected(False)

    def rebuild_start_cards(self):
        """Карточки коллекции и настоящая история прослушиваний выбранного сервиса."""
        if not hasattr(self, "home_tiles_layout"):
            return
        while self.home_tiles_layout.count():
            self.home_tiles_layout.takeAt(0)
        for card in self.start_cards:
            card.hide()
            card.deleteLater()
        for card in getattr(self, "youtube_mix_cards", []):
            card.hide()
            card.deleteLater()
        self.start_cards = []
        self.youtube_mix_cards = []
        source = self.current_source if self.current_source in ("youtube", "soundcloud") else "youtube"
        self._add_likes_start_card(source)
        if source == "youtube":
            supermix = SpotifyPlaylistCard(
                "Супермикс", "Персональная подборка YouTube Music", "🪄", "#EC412B", "#F5AF45",
                self.home_tiles, artwork_style="supermix", tile_mode=True
            )
            supermix.clicked.connect(lambda checked=False: self.toggle_supermix())
            self.start_cards.append(supermix)
            mix = SpotifyPlaylistCard(
                "Перемешать лайки", "Любимые треки в новом порядке", "🎧", "#315C62", "#171C22",
                self.home_tiles, artwork_style="shuffle", tile_mode=True
            )
            mix.clicked.connect(lambda checked=False, src=source: self.play_personal_mix(src))
            self.start_cards.append(mix)
            for mix_key, mix_title, mix_sub, col_a, col_b in self.YOUTUBE_EXTRA_MIX_SPECS:
                extra_card = SpotifyPlaylistCard(
                    mix_title, mix_sub, "♫", col_a, col_b,
                    self.home_tiles, artwork_style=mix_key, tile_mode=True
                )
                extra_card.clicked.connect(lambda checked=False, mk=mix_key: self.toggle_youtube_mix(mk))
                self.youtube_mix_cards.append(extra_card)
            self._set_supermix_busy(self.supermix_worker is not None)
            self._update_supermix_cover()
            self._update_youtube_mix_covers()
        self._home_layout_signature = None
        self.layout_home_tiles()
        self.refresh_recent_tracks()
        self.refresh_supermix_card()
        self.refresh_home_likes_counts()
        self.refresh_sidebar_library()

    def eventFilter(self, watched, event):
        if watched is getattr(self, "search_input", None) and event.type() in (QEvent.Type.FocusIn, QEvent.Type.FocusOut):
            self.search_shell.setProperty("focused", event.type() == QEvent.Type.FocusIn)
            self.search_shell.style().unpolish(self.search_shell)
            self.search_shell.style().polish(self.search_shell)
            self.search_shell.update()
        if watched is getattr(self, "search_shell", None) and event.type() == QEvent.Type.Resize:
            self.search_shortcut.setVisible(self.search_shell.width() >= 430)
        if (event.type() == QEvent.Type.Resize and hasattr(self, "start_cards_scroll")
                and watched is self.start_cards_scroll.viewport() and not self._force_exit):
            QTimer.singleShot(0, self.layout_home_tiles)
        if event.type() in (QEvent.Type.Resize, QEvent.Type.Show) and not self._force_exit:
            for name in ("youtube_likes_list", "soundcloud_likes_list", "likes_list", "queue_list", "user_playlist_list"):
                list_widget = getattr(self, name, None)
                if list_widget is not None and watched is list_widget.viewport():
                    QTimer.singleShot(0, lambda lw=list_widget: self._ensure_row_window(lw))
                    self.schedule_visible_artwork(list_widget)
                    break
        return super().eventFilter(watched, event)

    def layout_home_tiles(self):
        if not hasattr(self, "home_tiles_layout") or self._force_exit:
            return
        width = max(180, self.start_cards_scroll.viewport().width())
        self.page_description.hide()
        columns = 3 if width >= 650 else 2 if width >= 360 else 1
        all_cards = list(self.start_cards) + list(getattr(self, "youtube_mix_cards", []))
        horizontal = len(all_cards) == 1 and not all_cards[0].tile_mode
        if horizontal:
            columns = 1
        max_tile_w = 340 if columns == 3 else 224
        card_w = width - 2 if horizontal else min(max_tile_w, (width - (columns - 1) * 16 - 4) // columns)
        card_h = 148 if horizontal else min(224, card_w) + 52
        signature = (columns, card_w, card_h, len(all_cards))
        if signature == getattr(self, "_home_layout_signature", None):
            return
        self._home_layout_signature = signature
        while self.home_tiles_layout.count():
            self.home_tiles_layout.takeAt(0)
        for index, card in enumerate(all_cards):
            card.setFixedSize(card_w, card_h)
            self.home_tiles_layout.addWidget(card, index // columns, index % columns,
                                            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        for column in range(4):
            self.home_tiles_layout.setColumnStretch(column, 1 if column == columns else 0)
        self.home_tiles_layout.invalidate()
        self.start_cards_layout.invalidate()

    @staticmethod
    def _recent_track_metadata(track):
        if (not isinstance(track, dict) or not track.get("url")
                or track.get("source") not in ("youtube", "soundcloud", "local")):
            return None
        # Persist only public catalog metadata, never resolved streams or auth data.
        fields = (
            "source", "url", "title", "artist", "artist_display",
            "profile_artist_name", "artist_url", "thumbnail", "video_id"
        )
        return {key: str(track[key]) for key in fields if track.get(key)}

    def load_recent_tracks(self):
        try:
            raw = json.loads(str(self.settings.value("recent_tracks_json", "[]") or "[]"))
            if not isinstance(raw, list):
                return []
            tracks, seen = [], set()
            for item in raw:
                track = self._recent_track_metadata(item)
                if track and self.favorite_key(track) not in seen:
                    tracks.append(track)
                    seen.add(self.favorite_key(track))
            return tracks[:self.RECENT_TRACK_LIMIT]
        except (ValueError, TypeError):
            return []

    def record_recent_track(self, track):
        saved = self._recent_track_metadata(track)
        if saved is None:
            return
        key = self.favorite_key(saved)
        self.recent_tracks = [saved] + [item for item in self.recent_tracks if self.favorite_key(item) != key]
        self.recent_tracks = self.recent_tracks[:self.RECENT_TRACK_LIMIT]
        self.settings.setValue("recent_tracks_json", json.dumps(self.recent_tracks, ensure_ascii=False))
        self.refresh_recent_tracks()

    def toggle_recent_tracks(self):
        source = self.current_source if self.current_source in ("youtube", "soundcloud") else "youtube"
        if source in self._recent_expanded_sources:
            self._recent_expanded_sources.discard(source)
        else:
            self._recent_expanded_sources.add(source)
        self.refresh_recent_tracks()
        self.update_playing_row_highlight()

    def refresh_recent_tracks(self):
        if not hasattr(self, "recent_rows_layout"):
            return
        source = self.current_source if self.current_source in ("youtube", "soundcloud") else "youtube"
        history = [track for track in self.recent_tracks if track.get("source") == source and not self.is_disliked(track)]
        expanded = source in self._recent_expanded_sources
        tracks = history if expanded else history[:self.RECENT_PREVIEW_COUNT]
        self.recent_more_button.setVisible(len(history) > self.RECENT_PREVIEW_COUNT)
        self.recent_more_button.setText("Свернуть" if expanded else f"Показать все · {len(history)}")
        heading = "Недавно слушал"
        if not tracks:
            own_tracks = self.soundcloud_liked_tracks if source == "soundcloud" else self._youtube_likes_for_display()
            tracks = [dict(track) for track in own_tracks if isinstance(track, dict) and track.get("url") and not self.is_disliked(track)][:self.RECENT_PREVIEW_COUNT]
            heading = "Из твоих лайков"
        signature = (source, heading, expanded, tuple((self.favorite_key(t), t.get("title"), t.get("artist"), t.get("thumbnail")) for t in tracks))
        if signature == getattr(self, "_recent_rows_signature", None):
            return
        self._recent_rows_signature = signature
        while self.recent_rows_layout.count():
            widget = self.recent_rows_layout.takeAt(0).widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        self.recent_heading.setText(heading if tracks else "Недавно слушал")
        self.recent_rows = []
        current = self.current_track if isinstance(self.current_track, dict) else None
        current_url = str((current or {}).get("url") or "")
        current_source = str((current or {}).get("source") or "")
        is_actually_playing = bool(
            hasattr(self, "player")
            and self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        )
        requested = self.requested_track if isinstance(self.requested_track, dict) else None
        requested_url = str((requested or {}).get("url") or "")
        requested_source = str((requested or {}).get("source") or "")
        duration_lookup = {}
        for pool in (self.youtube_liked_tracks, self.soundcloud_liked_tracks, list(self.favorites.values()), self.queue_tracks):
            for item in pool:
                if isinstance(item, dict) and item.get("url") and item.get("duration"):
                    duration_lookup[str(item["url"])] = item["duration"]
        for track in tracks:
            enriched = dict(track)
            if not enriched.get("duration") and str(enriched.get("url") or "") in duration_lookup:
                enriched["duration"] = duration_lookup[str(enriched["url"])]
            is_fav = (
                self.is_youtube_music_liked(enriched)
                if enriched.get("source") == "youtube"
                else self.is_favorite(enriched)
            )
            row = TrackRow(enriched, compact=True, is_favorite=is_fav, removable=False, parent=self.recent_rows_widget)
            row.setFixedHeight(64)
            row.play_requested.connect(lambda selected: self.add_to_queue(selected, True))
            row.artist_requested.connect(
                lambda artist_data, src=enriched.get("source"): self.search_artist_name(artist_data, src)
            )
            if hasattr(row, "favorite_button"):
                if enriched.get("source") == "youtube":
                    vid = self.youtube_video_id(enriched)
                    row.favorite_button.setEnabled(vid not in self._youtube_rating_pending)
                    row.favorite_button.clicked.connect(
                        lambda checked, t=dict(enriched), b=row.favorite_button: self.set_youtube_music_like(t, checked, b)
                    )
                else:
                    row.favorite_button.clicked.connect(
                        lambda checked=False, t=dict(enriched), b=row.favorite_button: self.toggle_favorite(t, b)
                    )
            if hasattr(row, "menu_button"):
                row.menu_button.clicked.connect(
                    lambda checked=False, t=dict(enriched), b=row.menu_button: self._open_recent_row_menu(t, b)
                )
            row.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            row.customContextMenuRequested.connect(
                lambda pos, t=dict(enriched), r=row: self._open_recent_row_menu(t, r, pos)
            )
            matches_current = bool(
                current_url and str(track.get("url") or "") == current_url
                and str(track.get("source") or "") == current_source
            )
            matches_loading = bool(
                requested_url and str(track.get("url") or "") == requested_url
                and str(track.get("source") or "") == requested_source
            )
            row.set_playing(matches_current, animate=(matches_current and is_actually_playing))
            if matches_loading:
                row.set_loading(True)
            self.request_image(track.get("thumbnail", ""), row.thumbnail_label)
            self.recent_rows.append(row)
            self.recent_rows_layout.addWidget(row)
        if not tracks:
            empty = QLabel("Здесь появятся последние прослушанные треки.\nНайди музыку или открой свои лайки.")
            empty.setObjectName("recentEmpty")
            empty.setWordWrap(True)
            empty.setMinimumHeight(90)
            self.recent_rows_layout.addWidget(empty)
        self.refresh_sidebar_library()

    def _open_recent_row_menu(self, track, anchor_widget, local_pos=None):
        if not isinstance(track, dict) or not track.get("url"):
            return
        menu = self.make_context_menu()
        self._populate_track_context_menu(menu, track)
        global_pos = anchor_widget.mapToGlobal(local_pos if local_pos is not None else QPoint(0, anchor_widget.height()))
        menu.exec(global_pos)

    def refresh_connection_badge(self):
        """Состояние подключения и обновления относится к выбранной вкладке лайков."""
        if not hasattr(self, "connection_badge"):
            return
        index = self.likes_tabs.currentIndex()
        if index == 2:
            self.connection_badge.setText("● На устройстве")
            self.connection_badge.setToolTip("Локальное избранное хранится на этом компьютере")
            self.connection_badge.setProperty("connected", False)
            self.sync_account_button.hide()
        else:
            youtube = index == 0
            service = "YouTube Music" if youtube else "SoundCloud"
            connected = bool(self.youtube_auth_kwargs()) if youtube else self.soundcloud_is_connected()
            busy = (self.youtube_sync_worker is not None if youtube else
                    self._soundcloud_likes_loading or "likes" in self.soundcloud_profile_workers)
            self.connection_badge.setText("● Обновляется" if busy else ("● Подключено" if connected else "● Сохранено"))
            self.connection_badge.setToolTip(service + (": идёт синхронизация" if busy else
                                                       ": аккаунт подключён" if connected else ": сохранённая библиотека"))
            self.connection_badge.setProperty("connected", connected)
            self.sync_account_button.show()
            self.sync_account_button.setText(("⟳ " if not busy else "… ") + ("YouTube" if youtube else "SoundCloud"))
            self.sync_account_button.setToolTip("Синхронизировать лайки " + service)
            self.sync_account_button.setEnabled(connected and not busy)
        self.connection_badge.style().unpolish(self.connection_badge)
        self.connection_badge.style().polish(self.connection_badge)

    def sync_selected_likes(self):
        index = self.likes_tabs.currentIndex()
        if index == 0:
            self.sync_youtube_likes()
        elif index == 1:
            if self.soundcloud_is_connected():
                self.load_soundcloud_account_content(force=True)
            else:
                self.connect_soundcloud_account()

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
            elif tracks and not self._force_exit and self.prefetch_worker is None:
                QTimer.singleShot(350, lambda: self._warmup_first_search_result(tracks[0]))

    def _warmup_first_search_result(self, track):
        if self._force_exit or not isinstance(track, dict) or not track.get("url"):
            return
        if self.requested_track is not None or self.pending_slot is not None:
            return
        if self.prefetch_worker is not None:
            return
        key = self._key(track)
        if not key or self.get_cached_stream(key) or self.prefetch_failed_until.get(key, 0) > time.monotonic():
            return
        auth_kwargs = (
            self.youtube_auth_kwargs() if track.get("source") == "youtube"
            else (self.soundcloud_auth_kwargs() if track.get("source") == "soundcloud" else {})
        )
        worker = StreamWorker(track, self, audio_quality=self.audio_quality, **auth_kwargs)
        self.prefetch_worker = worker
        self.prefetch_target = key
        worker.metadata_ready.connect(
            lambda data, k=key, w=worker: self.accept_stream_metadata(k, data) if not w._cancel_requested else None
        )
        worker.stream_ready.connect(
            lambda stream, title, elapsed, k=key: self.prefetch_ready(k, stream, title, elapsed)
        )
        worker.failed.connect(lambda error, k=key: self.prefetch_failed(k, error))
        worker.finished.connect(self.prefetch_finished)
        worker.finished.connect(worker.deleteLater)
        worker.start()

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
        base = self.dominant_color(pixmap)
        if self.theme == "light":
            soft = SpotifyPlaylistCard._blend(base, QColor("#FFFFFF"), 0.78)
            mid = SpotifyPlaylistCard._blend(base, QColor("#F5F8FC"), 0.90)
            border = SpotifyPlaylistCard._blend(base, QColor("#D5DEE8"), 0.65)
            self.artist_header.setStyleSheet(
                "QFrame#artistHeader { background: qlineargradient("
                "x1:0, y1:0, x2:1, y2:1, "
                f"stop:0 {soft.name()}, stop:0.55 {mid.name()}, stop:1 #FFFFFF); "
                f"border: 1px solid {border.name()}; border-radius: 16px; }}"
            )
            return
        color = base.lighter(135)
        mid = SpotifyPlaylistCard._blend(color, QColor("#18202B"), 0.55)
        border = SpotifyPlaylistCard._blend(color, QColor("#2A3444"), 0.65)
        self.artist_header.setStyleSheet(
            "QFrame#artistHeader { background: qlineargradient("
            "x1:0, y1:0, x2:1, y2:1, "
            f"stop:0 {color.name()}, stop:0.55 {mid.name()}, stop:1 #161B23); "
            f"border: 1px solid {border.name()}; border-radius: 16px; }}"
        )

    def _apply_playlist_header_color(self, pixmap):
        if not hasattr(self, "playlist_header"):
            return
        base = self.dominant_color(pixmap)
        if self.theme == "light":
            soft = SpotifyPlaylistCard._blend(base, QColor("#FFFFFF"), 0.78)
            mid = SpotifyPlaylistCard._blend(base, QColor("#F5F8FC"), 0.90)
            border = SpotifyPlaylistCard._blend(base, QColor("#D5DEE8"), 0.65)
            self.playlist_header.setStyleSheet(
                "QFrame#artistHeader { background: qlineargradient("
                "x1:0, y1:0, x2:1, y2:1, "
                f"stop:0 {soft.name()}, stop:0.55 {mid.name()}, stop:1 #FFFFFF); "
                f"border: 1px solid {border.name()}; border-radius: 16px; }}"
            )
            return
        color = base.lighter(135)
        mid = SpotifyPlaylistCard._blend(color, QColor("#18202B"), 0.55)
        border = SpotifyPlaylistCard._blend(color, QColor("#2A3444"), 0.65)
        self.playlist_header.setStyleSheet(
            "QFrame#artistHeader { background: qlineargradient("
            "x1:0, y1:0, x2:1, y2:1, "
            f"stop:0 {color.name()}, stop:0.55 {mid.name()}, stop:1 #161B23); "
            f"border: 1px solid {border.name()}; border-radius: 16px; }}"
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
        if avatar in self.pixmap_cache:
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
        self._stop_supermix_session()
        self.cancel_pending_request()
        self.queue_tracks = []
        self._queue_live_rows.clear()
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
        self._stop_supermix_session()
        self.cancel_pending_request()
        self.queue_tracks = []
        self._queue_live_rows.clear()
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
        self._create_result_row(list_widget, item, track, index_number)

    def _create_result_row(self, list_widget, item, track, index_number):
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
            parent=list_widget.viewport(),
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
        current = self.current_track or {}
        matches = bool(current.get("url") and current.get("url") == track.get("url")
                       and current.get("source") == track.get("source"))
        row.set_playing(matches, matches and self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState)
        requested = self.requested_track or {}
        if requested.get("url") == track.get("url") and requested.get("source") == track.get("source"):
            row.set_loading(True)
        return row

    def update_playing_row_highlight(self):
        """Подсветка сверяется по URL+источнику; на паузе строка остаётся зелёной."""
        current = self.current_track
        current_url = str((current or {}).get("url", ""))
        current_source = str((current or {}).get("source", ""))
        is_actually_playing = bool(
            current and self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        )
        for list_widget in (getattr(self, "source_list", None), getattr(self, "youtube_likes_list", None),
                             getattr(self, "soundcloud_likes_list", None), getattr(self, "likes_list", None),
                             getattr(self, "user_playlist_list", None)):
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

        self.refresh_supermix_card()
        current_uid = (current or {}).get("queue_id")
        for index in range(self.queue_list.count()):
            row = self.queue_list.itemWidget(self.queue_list.item(index))
            if isinstance(row, TrackRow):
                matches = bool(current_uid and row.track.get("queue_id") == current_uid)
                row.set_playing(matches, animate=(matches and is_actually_playing))
        for row in getattr(self, "recent_rows", []):
            matches = bool(current_url and row.track.get("url") == current_url and row.track.get("source") == current_source)
            row.set_playing(matches, animate=(matches and is_actually_playing))
        self._sync_sidebar_playing_state()

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
        self._likes_display_tracks[kind] = tracks
        self._likes_loading_more.add(kind)
        list_widget.setUpdatesEnabled(False)
        list_widget.clear()
        self._likes_live_rows[kind].clear()
        end = min(len(tracks), self._likes_render_batch)
        for index in range(end):
            self._add_likes_item(list_widget, tracks[index])
        self._likes_rendered_counts[kind] = end
        self._likes_list_signatures[kind] = self._likes_signature(tracks)
        list_widget.setUpdatesEnabled(True)
        self._likes_loading_more.discard(kind)
        self._ensure_likes_row_window(list_widget)
        if end:
            self.schedule_visible_artwork(list_widget)

    def _append_likes_rows(self, list_widget):
        kind = self._likes_kind_for_widget(list_widget)
        if not kind or kind in self._likes_loading_more:
            return
        tracks = self._likes_display_tracks.get(kind, [])
        start = self._likes_rendered_counts.get(kind, 0)
        if start >= len(tracks):
            return
        end = min(len(tracks), start + self._likes_render_batch)
        self._likes_loading_more.add(kind)
        list_widget.setUpdatesEnabled(False)
        for index in range(start, end):
            self._add_likes_item(list_widget, tracks[index])
        list_widget.setUpdatesEnabled(True)
        self._likes_rendered_counts[kind] = end
        self._likes_list_signatures[kind] = self._likes_signature(tracks)
        self._likes_loading_more.discard(kind)
        self._ensure_likes_row_window(list_widget)
        self.schedule_visible_artwork(list_widget)

    @staticmethod
    def _add_likes_item(list_widget, track):
        # Lightweight items keep ordering, selection and the scroll geometry.
        # The expensive child widgets exist only around the viewport.
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, dict(track))
        item.setSizeHint(QSize(200, 72))
        list_widget.addItem(item)

    def _ensure_likes_row_window(self, list_widget):
        self._ensure_row_window(list_widget)

    def _ensure_row_window(self, list_widget):
        """Keep lightweight items for every track, but widgets only near the viewport."""
        if self._force_exit:
            return
        queue = list_widget is self.queue_list
        kind = "queue" if queue else self._likes_kind_for_widget(list_widget)
        if (not kind or kind in self._row_windows_updating
                or (queue and self._queue_rebuilding)
                or (not queue and kind in self._likes_loading_more)):
            return
        self._row_windows_updating.add(kind)
        try:
            height = 64 if queue else 72
            count = list_widget.count()
            top = list_widget.indexAt(QPoint(10, 8)).row() if list_widget.isVisible() else 0
            if top < 0:
                top = list_widget.verticalScrollBar().value() // (height + 2 * list_widget.spacing())
            visible = max(1, list_widget.viewport().height() // height + 2) if list_widget.isVisible() else 1
            first = max(0, top - 8)
            end = min(count, max(first + 24, top + visible + 8))
            wanted = set(range(first, end))
            live = self._queue_live_rows if queue else self._likes_live_rows[kind]
            focused = QApplication.focusWidget()
            for index, row in list(live.items()):
                item = list_widget.item(index)
                attached = item is not None and list_widget.itemWidget(item) is row
                if attached and index not in wanted and focused is not None and row.isAncestorOf(focused):
                    continue
                if not attached or index not in wanted:
                    if attached:
                        row._eq_timer.stop()
                        row.hide()
                        list_widget.removeItemWidget(item)  # Qt schedules deletion.
                    live.pop(index, None)
            for index in range(first, end):
                if index not in live:
                    item = list_widget.item(index)
                    if queue:
                        live[index] = self._create_queue_row(item, self.queue_tracks[index])
                    else:
                        track = item.data(Qt.ItemDataRole.UserRole)
                        live[index] = self._create_result_row(list_widget, item, track, index + 1)
        finally:
            self._row_windows_updating.discard(kind)

    def maybe_load_more_likes(self, list_widget):
        if self._force_exit:
            return
        kind = self._likes_kind_for_widget(list_widget)
        if not kind or kind in self._likes_loading_more:
            return
        tracks = self._likes_display_tracks.get(kind, [])
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
        self._ensure_row_window(list_widget)

    def refresh_likes_list(self, append_soundcloud_tracks=None, force_rebuild=False):
        """Обновляет данные списков; TrackRow создаются только рядом с экраном."""
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
        self._likes_display_tracks = display_tracks

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
        self.likes_title.setText(f"{len(combined)} треков в библиотеке")
        self.refresh_home_likes_counts({"youtube": len(youtube_tracks), "soundcloud": len(soundcloud_tracks)})
        self._update_likes_collage()

        if self.youtube_auth_mode == "browser" and self.youtube_auth_browser:
            profile_suffix = f" · профиль {self.youtube_auth_profile}" if self.youtube_auth_profile else ""
            auth_label = f"Браузер: {self.youtube_auth_browser}{profile_suffix}"
        elif self.youtube_cookie_file:
            auth_label = f"Файл сессии: {Path(self.youtube_cookie_file).name}"
        else:
            auth_label = "Аккаунт не подключён"
        has_auth = bool(self.youtube_auth_kwargs())
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
        self.refresh_connection_badge()
        self.refresh_recent_tracks()
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
                self._stop_supermix_session()
                self.supermix_cover_url = ""
                self.youtube_auth_mode = "file"
                self.youtube_cookie_file = str(cookie_path.resolve())
                self.youtube_auth_profile = ""
                self.settings.setValue("youtube_cookie_file", self.youtube_cookie_file)
                self.settings.setValue("youtube_auth_mode", "file")
                self.settings.setValue("youtube_auth_browser", browser_combo.currentData())
                self.settings.setValue("youtube_auth_profile", "")
            else:
                self._stop_supermix_session()
                self.supermix_cover_url = ""
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
        self._stop_supermix_session()
        self.supermix_cover_url = ""
        self.youtube_mix_catalog = {}
        self.youtube_mix_covers = {}
        YouTubeMusicAuth.invalidate_browser_cookie_cache()
        self.youtube_cookie_file = ""
        self.youtube_auth_mode = "file"
        self.youtube_auth_browser = "chrome"
        self.youtube_auth_profile = ""
        for key in ("youtube_cookie_file", "youtube_auth_mode", "youtube_auth_browser", "youtube_auth_profile", "youtube_mix_catalog_json", "supermix_cover_url"):
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
        self.set_status("Подключаюсь к YouTube Music и загружаю плейлист «Понравившиеся»…", "likes")
        self._youtube_sync_page_seen = False
        worker = SearchWorker(
            "", "youtube", "relevance", 100, self,
            direct_url="https://music.youtube.com/playlist?list=LM",
            cache_enabled=False, paginate_all=True, max_total=10000, **auth_kwargs
        )
        self.youtube_sync_worker = worker
        self.refresh_connection_badge()
        self.refresh_home_likes_counts()
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
                self._likes_display_tracks["youtube"] = []
                self._likes_live_rows["youtube"].clear()
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
        self.refresh_connection_badge()
        self.refresh_home_likes_counts()
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
        row = list_widget.itemWidget(item)
        if isinstance(row, TrackRow) and isinstance(getattr(row, "track", None), dict):
            merged = dict(track) if isinstance(track, dict) else {}
            merged.update({k: v for k, v in row.track.items() if v not in (None, "")})
            track = merged
        if not isinstance(track, dict):
            return
        menu = self.make_context_menu()
        self._populate_track_context_menu(menu, track)
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

        for row in getattr(self, "recent_rows", []):
            row_track = getattr(row, "track", None)
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
            was_blocked = button.blockSignals(True)
            try:
                button.setChecked(liked)
                button.setIcon(control_icon("heart" if liked else "heart-outline", "#1DB954" if liked else "#B3B3B3", 22))
                button.setEnabled(not pending)
            finally:
                button.blockSignals(was_blocked)

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
        self.dislike_action.setEnabled(available and not disliked)
        self.refresh_current_track_views()
        self.refresh_mini_player()

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
            self.bottom_artist.setText("")
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
        self._stop_supermix_session()
        self.cancel_pending_request()
        self.queue_tracks = []
        self._queue_live_rows.clear()
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
                  if isinstance(track, dict) and track.get("url") and not self.is_disliked(track)]
        if not tracks:
            self.set_status("Сначала дождись загрузки треков исполнителя.", source)
            return
        artist = str(getattr(self, "active_artist_profile", "") or "").strip()
        artist_key = artist.casefold()
        matching = [track for track in tracks if str(track.get("artist", "")).casefold() == artist_key] or tracks
        seed = random.choice(matching[:min(12, len(matching))])
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
        if hasattr(self, "view_stack") and hasattr(self, "browse_page"):
            if self.view_stack.currentWidget() is not self.browse_page:
                self.fade_to_page(self.browse_page)
        self.start_search()

    def _enrich_track_for_radio(self, track):
        """Дополняет трек самыми свежими метаданными из коллекций плеера перед запуском радио."""
        if not isinstance(track, dict):
            return {}
        enriched = dict(track)
        url = str(enriched.get("url") or "").strip()
        source = str(enriched.get("source") or "").strip()
        if url:
            pools = [
                [self.current_track] if isinstance(self.current_track, dict) else [],
                [self.requested_track] if isinstance(self.requested_track, dict) else [],
                self.queue_tracks,
                self.source_results.get(source, []) if source else [],
                self.youtube_liked_tracks,
                self.soundcloud_liked_tracks,
                list(self.favorites.values()),
                getattr(self, "recent_tracks", []),
            ]
            for pool in pools:
                for candidate in pool:
                    if not isinstance(candidate, dict) or str(candidate.get("url") or "").strip() != url:
                        continue
                    for k, v in candidate.items():
                        if v in (None, ""):
                            continue
                        if k == "title" and str(v).strip() == "Без названия" and SearchWorker._clean_radio_text(enriched.get("title")):
                            continue
                        if k == "artist" and str(v).strip() == "Исполнитель неизвестен" and SearchWorker._clean_radio_text(enriched.get("artist")):
                            continue
                        if not enriched.get(k) or enriched.get(k) in ("Без названия", "Исполнитель неизвестен"):
                            enriched[k] = v
        if source == "youtube" and not enriched.get("video_id"):
            vid = YouTubeRatingWorker._video_id(enriched)
            if vid:
                enriched["video_id"] = vid
        if source == "soundcloud":
            _, slug_user, slug_title = SearchWorker._extract_soundcloud_slug_parts(url)
            if not SearchWorker._clean_radio_text(enriched.get("artist")) and slug_user:
                enriched["artist"] = slug_user
            if not SearchWorker._clean_radio_text(enriched.get("title")) and slug_title:
                enriched["title"] = slug_title
        return enriched

    def _remember_radio_track(self, track):
        if not isinstance(track, dict):
            return
        key = self.radio_track_key(track)
        if key:
            self.radio_seen_urls.add(key)
            self.radio_recent_history.append(key)
        vid = YouTubeRatingWorker._video_id(track) if track.get("source") == "youtube" else ""
        if vid:
            self.radio_seen_urls.add(vid)
            self.radio_recent_history.append(vid)
        sig = SearchWorker._radio_song_signature(track)
        if sig[1]:
            self.radio_seen_signatures.add(sig)
            self.radio_recent_history.append(f"sig:{sig[0]}|{sig[1]}")

    def start_radio(self, track, artist_context=None):
        """Запускает радио по конкретному треку; для профиля артиста сохраняет контекст для будущих пополнений."""
        self._stop_supermix_session()
        track = self._enrich_track_for_radio(track)
        if track.get("source") not in ("youtube", "soundcloud"):
            QMessageBox.information(self, "Радио", "Радио доступно для треков YouTube и SoundCloud.")
            return
        if self.radio_worker is not None and self.radio_worker.isRunning():
            self.radio_worker.cancel()
        if self.radio_refill_worker is not None and self.radio_refill_worker.isRunning():
            self.radio_refill_worker.cancel()
        self.radio_refill_worker = None
        self.radio_mode_active = False
        self.radio_seed_track = dict(track)
        self.radio_refill_attempt_key = ""
        self.radio_refill_added_urls = set()
        self.radio_refill_added_count = 0
        self.radio_refill_last_error = ""
        self._radio_refill_failed_attempts = 0
        self.radio_refill_round = 0
        self.radio_launch_counter = getattr(self, "radio_launch_counter", 0) + 1
        self.radio_refill_next_allowed_at = 0.0
        self.radio_artist_context = SearchWorker._clean_radio_text(artist_context)
        self.radio_seen_urls = set()
        self.radio_seen_signatures = set()
        self._remember_radio_track(track)
        self._radio_waiting_for_tracks = False
        self._radio_retry_scheduled = False
        if self.radio_dialog is not None:
            self.radio_dialog.hide()
            self.radio_dialog.deleteLater()
            self.radio_dialog = None
        artist = SearchWorker._clean_radio_text(track.get("artist_display") or track.get("artist"))
        title = SearchWorker._clean_radio_text(track.get("title"))
        query = (f"{self.radio_artist_context} mix" if self.radio_artist_context
                 else f"{artist} {title}".strip()).strip()
        if not query:
            query = title or artist or "popular music mix"
        self.radio_candidates = []
        self.radio_note = ""
        dialog = RadioDialog(self, track)
        self.radio_dialog = dialog
        if track.get("thumbnail"):
            self.request_image(track.get("thumbnail"), dialog.cover)
        dialog.show_animated()
        display_label = f"{artist} — {title}".strip(" —") or query
        self.set_status(f"Радио: подбираю похожие треки к «{display_label}»…", track.get("source"))
        auth_kwargs = self.youtube_auth_kwargs() if track.get("source") == "youtube" else self.soundcloud_auth_kwargs()
        excluded_keys = set(self.radio_seen_urls) | set(self.disliked_track_keys)
        worker = SearchWorker(
            query, track.get("source"), "relevance", 75, self,
            cache_enabled=False,
            radio_seed_track=track,
            radio_excluded_keys=excluded_keys,
            radio_excluded_signatures=set(self.radio_seen_signatures),
            radio_recent_keys=set(self.radio_recent_history),
            radio_round=self.radio_launch_counter - 1,
            radio_artist_context=self.radio_artist_context,
            **auth_kwargs,
        )
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
        self._queue_live_rows.clear()
        self.queue_list.clear()
        self.current_queue_index = -1
        self.shuffle_future = None
        self.radio_mode_active = True
        self.queue_mode = "radio"
        self.radio_seen_urls = set()
        self.radio_seen_signatures = set()
        if isinstance(self.radio_seed_track, dict):
            self._remember_radio_track(self.radio_seed_track)
        self.radio_refill_attempt_key = ""
        self.radio_refill_added_count = 0
        self.radio_refill_next_allowed_at = 0.0
        self._radio_refill_failed_attempts = 0
        self._radio_waiting_for_tracks = False
        for track in tracks:
            key = self.radio_track_key(track)
            vid = YouTubeRatingWorker._video_id(track) if track.get("source") == "youtube" else ""
            sig = SearchWorker._radio_song_signature(track)
            if key in self.radio_seen_urls or (vid and vid in self.radio_seen_urls):
                continue
            if sig[1] and sig in self.radio_seen_signatures:
                continue
            queued = dict(track)
            queued["queue_id"] = uuid4().hex
            self.queue_tracks.append(queued)
            self._remember_radio_track(queued)
            if len(self.queue_tracks) >= 75:
                break
        if not self.queue_tracks:
            self.set_status("В радио не осталось новых треков.")
            return
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
        # Выбираем опорный трек для пополнения: чередуем последний трек очереди,
        # текущий трек и исходный трек радио, чтобы подборка не зацикливалась.
        seed_candidates = []
        if self.queue_tracks:
            tail_slice = self.queue_tracks[-min(5, len(self.queue_tracks)):]
            seed_candidates.extend(reversed(tail_slice))
        if isinstance(self.current_track, dict):
            seed_candidates.append(self.current_track)
        if isinstance(self.requested_track, dict):
            seed_candidates.append(self.requested_track)
        if isinstance(self.radio_seed_track, dict):
            seed_candidates.append(self.radio_seed_track)
        valid_seeds = [
            self._enrich_track_for_radio(s) for s in seed_candidates
            if isinstance(s, dict) and s.get("source") in ("youtube", "soundcloud")
        ]
        if not valid_seeds:
            return
        seed = valid_seeds[self.radio_refill_round % len(valid_seeds)]
        source = str(seed.get("source", ""))
        anchor_key = f"{self.radio_track_key(seed)}|{self.radio_refill_round}"
        if anchor_key == self.radio_refill_attempt_key:
            return
        self.radio_refill_attempt_key = anchor_key
        seed_artist = SearchWorker._clean_radio_text(seed.get("artist_display") or seed.get("artist"))
        seed_title = SearchWorker._clean_radio_text(seed.get("title"))
        artist_context = SearchWorker._clean_radio_text(getattr(self, "radio_artist_context", ""))
        if artist_context:
            query_variants = [
                f"{artist_context} popular songs",
                f"{artist_context} radio mix",
                f"{artist_context} related artists",
                f"{seed_artist} {seed_title}".strip(),
                f"songs similar to {seed_title} {seed_artist}".strip(),
            ]
        else:
            query_variants = [
                f"{seed_artist} {seed_title}".strip(),
                f"{seed_artist} related songs".strip(),
                f"songs similar to {seed_title} {seed_artist}".strip(),
                f"{seed_artist} popular songs".strip(),
                f"{seed_title} similar tracks".strip(),
            ]
        query_variants = [q.strip() for q in query_variants if q.strip()]
        if not query_variants:
            query_variants = [seed_title or seed_artist or "popular music mix"]
        self.radio_refill_round += 1
        query = query_variants[(self.radio_refill_round - 1) % len(query_variants)]
        auth_kwargs = self.youtube_auth_kwargs() if source == "youtube" else self.soundcloud_auth_kwargs()
        for queued_item in self.queue_tracks:
            self._remember_radio_track(queued_item)
        excluded_keys = set(self.radio_seen_urls) | set(self.disliked_track_keys)
        worker = SearchWorker(
            query, source, "relevance", 75, self,
            cache_enabled=False,
            radio_seed_track=seed,
            radio_excluded_keys=excluded_keys,
            radio_excluded_signatures=set(self.radio_seen_signatures),
            radio_recent_keys=set(self.radio_recent_history),
            radio_round=self.radio_refill_round,
            radio_artist_context=artist_context,
            **auth_kwargs,
        )
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
            vid = YouTubeRatingWorker._video_id(track) if track.get("source") == "youtube" else ""
            sig = SearchWorker._radio_song_signature(track)
            if not track.get("url") or key in self.radio_seen_urls or (vid and vid in self.radio_seen_urls):
                continue
            if sig[1] and sig in self.radio_seen_signatures:
                continue
            self._remember_radio_track(track)
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
        """Современное контекстное меню в палитре Aurora с поддержкой векторных иконок."""
        menu = QMenu(self)
        menu.setObjectName("darkMenu")
        menu.setMinimumWidth(248)
        if self.theme == "dark":
            menu.setStyleSheet(
                "QMenu {"
                "  background-color: #161C24;"
                "  color: #F2F6FA;"
                "  border: 1px solid #2A3544;"
                "  border-radius: 12px;"
                "  padding: 6px;"
                "}"
                "QMenu::item {"
                "  padding: 9px 22px 9px 12px;"
                "  border-radius: 8px;"
                "  margin: 2px 3px;"
                "  font-weight: 600;"
                "  font-size: 13px;"
                "}"
                "QMenu::item:selected {"
                "  background-color: #1E3428;"
                "  color: #66E099;"
                "}"
                "QMenu::item:disabled {"
                "  color: #556274;"
                "  background: transparent;"
                "}"
                "QMenu::icon {"
                "  padding-left: 8px;"
                "  padding-right: 4px;"
                "}"
                "QMenu::separator {"
                "  height: 1px;"
                "  background: #25303E;"
                "  margin: 5px 10px;"
                "}"
            )
        else:
            menu.setStyleSheet(
                "QMenu {"
                "  background-color: #FFFFFF;"
                "  color: #18202A;"
                "  border: 1px solid #D5DEE8;"
                "  border-radius: 12px;"
                "  padding: 6px;"
                "}"
                "QMenu::item {"
                "  padding: 9px 22px 9px 12px;"
                "  border-radius: 8px;"
                "  margin: 2px 3px;"
                "  font-weight: 600;"
                "  font-size: 13px;"
                "}"
                "QMenu::item:selected {"
                "  background-color: #E2F3E8;"
                "  color: #167A40;"
                "}"
                "QMenu::item:disabled {"
                "  color: #9AA6B8;"
                "  background: transparent;"
                "}"
                "QMenu::icon {"
                "  padding-left: 8px;"
                "  padding-right: 4px;"
                "}"
                "QMenu::separator {"
                "  height: 1px;"
                "  background: #E2E8F0;"
                "  margin: 5px 10px;"
                "}"
            )
        return menu

    def _add_menu_action(self, menu, text, callback, icon_name=None, enabled=True, accent=False):
        action = menu.addAction(text, callback)
        if icon_name:
            action.setIcon(menu_action_icon(icon_name, self.theme, accent=accent))
        action.setEnabled(bool(enabled))
        return action

    def _add_playlist_submenu(self, menu, track):
        if not isinstance(track, dict) or not track.get("url"):
            return
        pl_menu = menu.addMenu(
            menu_action_icon("playlist-add", self.theme, accent=True),
            "Добавить в плейлист",
        )
        pl_menu.setStyleSheet(menu.styleSheet())
        t_key = self.favorite_key(track)
        playlists = [p for p in getattr(self, "user_playlists", []) if isinstance(p, dict) and p.get("id")]
        for pl in playlists:
            pid = str(pl.get("id") or "")
            title = str(pl.get("title") or "Мой плейлист")
            folder = str(pl.get("folder") or "").strip()
            tracks = pl.get("tracks", []) if isinstance(pl.get("tracks"), list) else []
            already_in = any(isinstance(item, dict) and self.favorite_key(item) == t_key for item in tracks)
            prefix = "✓ " if already_in else ""
            label = f"{prefix}{folder} / {title} ({len(tracks)})" if folder else f"{prefix}{title} ({len(tracks)})"
            self._add_menu_action(
                pl_menu, label,
                lambda p=pid, t=dict(track): self.add_track_to_user_playlist(p, t),
                icon_name="playlist-add", accent=already_in,
            )
        if playlists:
            pl_menu.addSeparator()
        self._add_menu_action(
            pl_menu, "Новый плейлист с этим треком…",
            lambda t=dict(track): self.create_user_playlist_dialog(initial_track=t),
            icon_name="plus", accent=True,
        )

    def _populate_track_context_menu(self, menu, track, include_play=True, include_queue_add=True):
        if include_play:
            self._add_menu_action(
                menu, "Воспроизвести",
                lambda t=dict(track): self.add_to_queue(t, True),
                icon_name="play", accent=True,
            )
        if include_queue_add:
            self._add_menu_action(
                menu, "Добавить в очередь",
                lambda t=dict(track): self.add_to_queue(t, False),
                icon_name="queue-add",
            )
        self._add_playlist_submenu(menu, track)
        if track.get("source") in ("youtube", "soundcloud"):
            self._add_menu_action(
                menu, "Запустить радио по треку",
                lambda t=dict(track): self.start_radio(t),
                icon_name="radio",
            )
        if track.get("source") != "local":
            menu.addSeparator()
            if self.offline_path_for(track):
                self._add_menu_action(
                    menu, "Скачано · Открыть папку",
                    lambda t=dict(track): self.open_download_folder(t),
                    icon_name="downloaded", accent=True,
                )
            else:
                self._add_menu_action(
                    menu, "Скачать трек",
                    lambda t=dict(track): self.download_track(t),
                    icon_name="download",
                )
        artist = self.artist_card_name(track) or str(track.get("artist") or "").strip()
        has_artist = bool(
            track.get("source") != "local"
            and artist
            and artist not in ("Исполнитель неизвестен", "Unknown artist")
        )
        has_web = str(track.get("url", "")).startswith(("https://", "http://"))
        if has_artist or has_web:
            menu.addSeparator()
            if has_artist:
                self._add_menu_action(
                    menu, "Найти треки исполнителя",
                    lambda t=dict(track): self.find_artist(t),
                    icon_name="artist",
                )
            if has_web:
                self._add_menu_action(
                    menu, "Открыть на сайте",
                    lambda t=dict(track): self.open_track_website(t),
                    icon_name="external",
                )

    def open_result_menu(self, point):
        item = self.source_list.itemAt(point)
        if item is None:
            return
        track = item.data(Qt.ItemDataRole.UserRole)
        row = self.source_list.itemWidget(item)
        if isinstance(row, TrackRow) and isinstance(getattr(row, "track", None), dict):
            merged = dict(track) if isinstance(track, dict) else {}
            merged.update({k: v for k, v in row.track.items() if v not in (None, "")})
            track = merged
        if not isinstance(track, dict):
            return
        menu = self.make_context_menu()
        self._populate_track_context_menu(menu, track)
        menu.exec(self.source_list.viewport().mapToGlobal(point))

    def find_artist(self, track):
        """Ищем популярные треки по клику на исполнителя."""
        self.search_artist_name(dict(track) if isinstance(track, dict) else track, track.get("source") if isinstance(track, dict) else None)

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
        self.refresh_connection_badge()
        lists = (self.youtube_likes_list, self.soundcloud_likes_list, self.likes_list)
        if 0 <= int(index) < len(lists):
            list_widget = lists[int(index)]
            self._ensure_likes_row_window(list_widget)
            self.schedule_visible_artwork(list_widget)
            QTimer.singleShot(0, lambda lw=list_widget: self.maybe_load_more_likes(lw))

    def schedule_visible_artwork(self, list_widget):
        """Небольшой debounce: загружаем обложки только у видимых строк списка."""
        if list_widget is None or self._force_exit:
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
        if self._force_exit or list_widget is None or not list_widget.isVisible():
            return
        self._ensure_row_window(list_widget)
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
        # Не конкурируем с активным извлечением аудиопотока выбранного трека.
        if self.requested_track is not None or self.stream_worker is not None:
            return
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
        stream_url = str(updates.pop("stream_url", "") or "")
        if stream_url and url:
            self.save_stream(url, stream_url, str(updates.get("title") or ""))
            if (self.requested_track is not None
                    and self._key(self.requested_track) == url
                    and self.pending_slot is None):
                if self.stream_worker is not None:
                    self.stream_worker.cancel()
                self.start_pending_media(QUrl(stream_url), "предзагрузка метаданных")
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
                            self.soundcloud_likes_list, self.likes_list,
                            getattr(self, "user_playlist_list", None)):
            if list_widget is None:
                continue
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
            if isinstance(label, ExpandedArtwork):
                label.set_artwork(image)
                if label is getattr(self, "expanded_cover", None):
                    self.cover_page.set_cover_accent(image)
                    self._position_expanded_cover()
                return
            side = max(1, min(label.width(), label.height()))
            ratio = label.devicePixelRatioF()
            circular = bool(label.property("circular_image"))
            key = (image.cacheKey(), side, ratio, circular)
            rendered = self.thumbnail_cache.get(key)
            if rendered is None:
                pixels = max(1, round(side * ratio))
                rendered = (circular_pixmap(image, pixels) if circular else
                            rounded_pixmap(image, pixels, round((13 if side >= 140 else 8) * ratio)))
                rendered.setDevicePixelRatio(ratio)
                self._cache_pixmap(self.thumbnail_cache, key, rendered, self.THUMBNAIL_CACHE_BYTES, 512)
            else:
                self.thumbnail_cache.move_to_end(key)
            label.setPixmap(rendered)
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
            self.image_waiters[url].append(weakref.ref(label))
        else:
            self.image_waiters[url] = [weakref.ref(label)]
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
            self.image_waiters[url].append(weakref.ref(card))
        else:
            self.image_waiters[url] = [weakref.ref(card)]
            self.image_backlog.append(url)
        self.pump_images()

    def pump_images(self):
        while self.active_images < self.image_limit and self.image_backlog:
            url = self.image_backlog.popleft()
            targets = []
            for reference in self.image_waiters.get(url, []):
                target = reference()
                try:
                    if target is not None and target.property("requested_image") == url:
                        targets.append(reference)
                except RuntimeError:
                    pass
            if not targets:
                self.image_waiters.pop(url, None)
                continue
            self.image_waiters[url] = targets
            self.active_images += 1
            request = QNetworkRequest(QUrl(url))
            request.setRawHeader(b"User-Agent", b"Mozilla/5.0")
            request.setTransferTimeout(10_000)
            reply = self.network_manager.get(request)
            reply.readyRead.connect(lambda r=reply: r.abort()
                                    if r.bytesAvailable() > self.ARTWORK_MAX_DOWNLOAD else None)
            reply.finished.connect(lambda r=reply, u=url: self.image_finished(u, r))

    @staticmethod
    def _pixmap_bytes(pixmap):
        return 0 if pixmap is None or pixmap.isNull() else pixmap.width() * pixmap.height() * pixmap.depth() // 8

    @classmethod
    def _cache_pixmap(cls, cache, key, pixmap, max_bytes, max_entries):
        cache[key] = pixmap
        cache.move_to_end(key)
        used = sum(cls._pixmap_bytes(value) for value in cache.values())
        while cache and (len(cache) > max_entries or used > max_bytes):
            _, removed = cache.popitem(last=False)
            used -= cls._pixmap_bytes(removed)

    def _decode_artwork(self, data):
        if not 0 < len(data) <= self.ARTWORK_MAX_DOWNLOAD:
            return None
        buffer = QBuffer()
        buffer.setData(data)
        buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        reader = QImageReader(buffer)
        reader.setAutoTransform(True)
        size = reader.size()
        if not size.isValid() or size.width() * size.height() > self.ARTWORK_MAX_PIXELS:
            return None
        bound = QSize(self.ARTWORK_MAX_SIDE, self.ARTWORK_MAX_SIDE)
        if size.width() > bound.width() or size.height() > bound.height():
            reader.setScaledSize(size.scaled(bound, Qt.AspectRatioMode.KeepAspectRatio))
        image = reader.read()
        if image.isNull():
            return None
        # Some image plugins ignore setScaledSize; bound the retained bitmap too.
        if image.width() > bound.width() or image.height() > bound.height():
            image = image.scaled(bound, Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
        return QPixmap.fromImage(image)

    def image_finished(self, url, reply):
        try:
            data = bytes(reply.readAll())
            pixmap = self._decode_artwork(data)
            self._cache_pixmap(self.pixmap_cache, url, pixmap, self.ARTWORK_CACHE_BYTES, 250)
            for reference in self.image_waiters.pop(url, []):
                label = reference()
                if label is None:
                    continue
                # Проверяем URL, чтобы старая загрузка не заменила новую обложку.
                try:
                    is_current = label.property("requested_image") == url
                except RuntimeError:
                    continue
                if is_current and pixmap is not None:
                    if isinstance(label, SpotifyPlaylistCard):
                        label.set_cover(pixmap)
                    else:
                        self.set_pixmap_safe(label, pixmap)
                    if label is getattr(self, "bottom_cover", None):
                        self._apply_chameleon_accent(pixmap)
                    if label is getattr(self, "artist_avatar", None):
                        self._apply_artist_header_color(pixmap)
                    if label is getattr(self, "playlist_cover_label", None):
                        self._apply_playlist_header_color(pixmap)
                    if self.mini_player is not None and label is self.mini_player.cover:
                        self.mini_player.set_cover_accent(pixmap)
            if hasattr(self, "likes_collage_cover") and url in getattr(self, "_likes_collage_urls", ()):
                self._update_likes_collage()
        finally:
            reply.deleteLater()
            self.active_images = max(0, self.active_images - 1)
            # LRU уже удерживает кэш в заданном размере, не сбрасывая все обложки сразу.
            self.pump_images()

    def _apply_chameleon_accent(self, pixmap):
        self.player_bar.set_cover_accent(pixmap)
        if hasattr(self, "cover_page"):
            self.cover_page.set_cover_accent(pixmap)
        self.chameleon_accent = QColor(self.player_bar.accent)
        self.chameleon_bright = QColor(self.player_bar.accent_bright)
        if hasattr(self, "seek_slider"):
            self.seek_slider.update()
        if hasattr(self, "volume_slider"):
            self.volume_slider.update()
        if hasattr(self, "expanded_cover") and self.expanded_cover.isVisible():
            self.expanded_cover.update()
        self.update_playing_row_highlight()

    def _update_likes_collage(self, *_args):
        if not hasattr(self, "likes_collage_cover"):
            return
        idx = self.likes_tabs.currentIndex() if hasattr(self, "likes_tabs") else 0
        if idx == 0:
            tracks = self._youtube_likes_for_display()
        elif idx == 1:
            tracks = [t for t in self.soundcloud_liked_tracks if isinstance(t, dict) and t.get("url")]
        else:
            tracks = [t for t in self.favorites.values() if isinstance(t, dict) and t.get("url")]
        if not tracks:
            tracks = self.get_combined_likes()
        pixmaps = []
        urls = []
        for t in tracks[:12]:
            u = normalize_artwork_url(t.get("thumbnail", ""))
            if not u or u in urls:
                continue
            urls.append(u)
            cached = self.pixmap_cache.get(u) or self.thumbnail_cache.get(u)
            if cached is not None and not cached.isNull():
                pixmaps.append(cached)
            if len(pixmaps) >= 4:
                break
        self._likes_collage_urls = tuple(urls[:4])
        self.likes_collage_cover.set_covers(pixmaps)

    def play_active_likes_tab(self, shuffle=False):
        idx = self.likes_tabs.currentIndex() if hasattr(self, "likes_tabs") else 0
        if idx == 0:
            tracks = list(self._likes_tracks_for_kind("youtube") if hasattr(self, "_likes_tracks_for_kind") else self._youtube_likes_for_display())
            if not tracks:
                return
            if shuffle:
                self.shuffle_enabled = True
                self.shuffle_button.setChecked(True)
                chosen = random.choice(tracks)
            else:
                chosen = tracks[0]
            self.play_youtube_likes_from(chosen)
        elif idx == 1:
            tracks = list(self._likes_tracks_for_kind("soundcloud") if hasattr(self, "_likes_tracks_for_kind") else self.soundcloud_liked_tracks)
            tracks = [t for t in tracks if isinstance(t, dict) and t.get("url")]
            if not tracks:
                return
            if shuffle:
                self.shuffle_enabled = True
                self.shuffle_button.setChecked(True)
                chosen = random.choice(tracks)
            else:
                chosen = tracks[0]
            self.play_soundcloud_likes_from(chosen)
        else:
            tracks = [dict(t) for t in self.favorites.values() if isinstance(t, dict) and t.get("url")]
            if not tracks:
                return
            if shuffle:
                random.shuffle(tracks)
            self._stop_supermix_session()
            self.queue_mode = "manual"
            self.radio_mode_active = False
            self.queue_tracks = [dict(t, queue_id=uuid4().hex) for t in tracks]
            self.refresh_queue_list()
            self.play_queue_index(0)

    def show_cover(self, url):
        # Main thumbnail and the expanded view share the existing bounded cache.
        self._apply_chameleon_accent(self.pixmap_cache.get(normalize_artwork_url(url)))
        if hasattr(self, "seek_slider"):
            seed_str = str((self.current_track or {}).get("url") or url or "aurora")
            self.seek_slider._wave_seed = sum((i + 1) * ord(ch) for i, ch in enumerate(seed_str[:64]))
            self.seek_slider.update()
        labels = [self.bottom_cover]
        if self.view_stack.currentWidget() is self.cover_page:
            labels.append(self.expanded_cover)
        for label in labels:
            if not url:
                label.setProperty("requested_image", "")
                self.set_pixmap_safe(label, self.fallback_cover)
            else:
                self.request_image(url, label)

    # ---------------------------------------------------------
    # Очередь. Она не исчезает при сворачивании правой колонки.
    # ---------------------------------------------------------

    def add_to_queue(self, track, play_now=False):
        self._stop_supermix_session()
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
        if not self._queue_rebuilding:
            self._ensure_row_window(self.queue_list)
            self.schedule_visible_artwork(self.queue_list)

    def _create_queue_row(self, item, queued):
        row = TrackRow(queued, compact=True, parent=self.queue_list.viewport())
        row.setCursor(Qt.CursorShape.PointingHandCursor)
        uid = queued.get("queue_id")
        row.drag_source_kind = "queue"
        row.drag_source_index = self.index_for_uid(uid)
        self.queue_list.setItemWidget(item, row)
        row.remove_button.clicked.connect(lambda checked=False, u=uid: self.remove_queue_uid(u))
        # Обложка и название — кликабельные элементы TrackRow. Разрешаем
        # воспроизведение по одному клику и ищем позицию по queue_id, чтобы
        # перестановка/удаление строк не запускали неверный трек.
        row.play_requested.connect(
            lambda _track, u=uid: self.play_queue_index(self.index_for_uid(u))
        )
        row.artist_requested.connect(
            lambda artist_data, src=queued.get("source"): self.search_artist_name(artist_data, src)
        )
        self.set_pixmap_safe(row.thumbnail_label, self.fallback_cover)
        current_uid = (self.current_track or {}).get("queue_id")
        is_actually_playing = bool(
            hasattr(self, "player")
            and self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        )
        matches_current = bool(uid and uid == current_uid)
        row.set_playing(matches_current, animate=(matches_current and is_actually_playing))
        requested_uid = (self.requested_track or {}).get("queue_id")
        if bool(uid and uid == requested_uid):
            row.set_loading(True)
        return row

    def refresh_queue_list(self):
        """Перерисовываем после удаления или смены порядка."""
        self._queue_rebuilding = True
        try:
            self._queue_live_rows.clear()
            self.queue_list.clear()
            for index, track in enumerate(self.queue_tracks):
                self.append_queue_item(track, index)
        finally:
            self._queue_rebuilding = False
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
        self._ensure_row_window(self.queue_list)
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
        queued_track = self.queue_tracks[index]
        menu = self.make_context_menu()
        self._add_menu_action(
            menu, "Воспроизвести",
            lambda u=uid: self.play_queue_index(self.index_for_uid(u)),
            icon_name="play", accent=True,
        )
        self._add_playlist_submenu(menu, queued_track)
        if queued_track.get("source") in ("youtube", "soundcloud"):
            self._add_menu_action(
                menu, "Запустить радио по треку",
                lambda t=dict(queued_track): self.start_radio(t),
                icon_name="radio",
            )
        if queued_track.get("source") != "local":
            menu.addSeparator()
            if self.offline_path_for(queued_track):
                self._add_menu_action(
                    menu, "Скачано · Открыть папку",
                    lambda t=dict(queued_track): self.open_download_folder(t),
                    icon_name="downloaded", accent=True,
                )
            else:
                self._add_menu_action(
                    menu, "Скачать трек",
                    lambda t=dict(queued_track): self.download_track(t),
                    icon_name="download",
                )
        menu.addSeparator()
        self._add_menu_action(
            menu, "Переместить выше",
            lambda u=uid: self.move_queue_index(self.index_for_uid(u), -1),
            icon_name="arrow-up", enabled=(index > 0),
        )
        self._add_menu_action(
            menu, "Переместить ниже",
            lambda u=uid: self.move_queue_index(self.index_for_uid(u), 1),
            icon_name="arrow-down", enabled=(index < len(self.queue_tracks) - 1),
        )
        menu.addSeparator()
        self._add_menu_action(
            menu, "Удалить из очереди",
            lambda u=uid: self.remove_queue_uid(u),
            icon_name="remove",
        )
        menu.exec(self.queue_list.viewport().mapToGlobal(point))

    def update_queue_count(self):
        count = len(self.queue_tracks)
        self.queue_count.setText(f"{count} треков")
        if hasattr(self, "queue_source_badge"):
            mode = getattr(self, "queue_mode", "manual")
            if getattr(self, "radio_mode_active", False):
                badge_text = "Радиоволна"
            elif mode == "supermix":
                badge_text = "Супермикс"
            elif mode == "youtube_likes":
                badge_text = "YouTube Лайки"
            elif mode == "soundcloud_likes":
                badge_text = "SoundCloud Лайки"
            elif mode == "user_playlist":
                badge_text = "Плейлист"
            else:
                badge_text = "Очередь"
            self.queue_source_badge.setText(badge_text)
        self.schedule_session_save()

    def clear_queue(self):
        self._stop_supermix_session()
        # Сохраняем уже воспроизводимый трек; новая очередь будет пустой.
        self.queue_mode = "manual"
        self._soundcloud_queue_waiting = False
        self._soundcloud_queue_anchor_url = ""
        self.cancel_pending_request()
        self.queue_tracks.clear()
        self._shuffle_history.clear()
        self._queue_live_rows.clear()
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
                                self.soundcloud_likes_list, self.likes_list, self.queue_list,
                                getattr(self, "user_playlist_list", None)):
                if list_widget is None:
                    continue
                for row_index in range(list_widget.count()):
                    row = list_widget.itemWidget(list_widget.item(row_index))
                    if not isinstance(row, TrackRow):
                        continue
                    row_track = row.track
                    if (str(row_track.get("url") or "") == target_url
                            and str(row_track.get("source") or "") == target_source):
                        row.set_loading(True)
            for row in getattr(self, "recent_rows", []):
                if isinstance(row, TrackRow):
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
                and not str(getattr(self, "queue_mode", "")).startswith("user_playlist:")
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
            elif self.queue_mode == "supermix":
                self._wait_for_supermix()
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
                and not str(getattr(self, "queue_mode", "")).startswith("user_playlist:")
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
        url_str = str(cached.get("url") or "")
        if url_str.startswith("http://127.0.0.1:") and "/stream/" in url_str:
            if not LocalStreamProxy.instance().is_stream_url_alive(url_str):
                self.stream_cache.pop(track_url, None)
                return None
        elif url_str.startswith("file:"):
            local_p = QUrl(url_str).toLocalFile()
            if not local_p or not Path(local_p).is_file():
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
        if len(self.stream_cache) > 150:
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
            self.audio_outputs[old].setVolume(0.0)
            with QSignalBlocker(self.players[old]):
                self.players[old].stop()
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
        for row in getattr(self, "recent_rows", []):
            if isinstance(row, TrackRow) and getattr(row, "_loading", False):
                row.set_loading(False)

    def cancel_pending_request(self, cancel_supermix=True):
        """Отменяем запуск неактуального трека, оставляя текущий звук."""
        if cancel_supermix:
            self._cancel_supermix()
        self.request_id += 1
        self.requested_track = None
        self.requested_index = -1
        self.stream_pending_track = None
        if self.stream_worker is not None:
            self.stream_worker.cancel()
        self._network_recovery = None
        self._requested_start_position = 0
        self.stop_fade()
        self.pending_media_timer.stop()
        if self.pending_slot is not None:
            slot = self.pending_slot
            self.pending_slot = None
            self.pending_media_url = None
            self.audio_outputs[slot].setVolume(0.0)
            with QSignalBlocker(self.players[slot]):
                self.players[slot].stop()
                self.players[slot].setSource(QUrl())
            self.standby_key = None
            self.standby_ready = False
        self._clear_loading_indicators()
        QTimer.singleShot(0, self.pump_artwork_workers)

    def prepare_next_track(self):
        """Находим следующую песню и прогреваем её вторым QMediaPlayer.

        Сначала yt-dlp получает временную ссылку в отдельном QThread,
        затем неактивный QMediaPlayer открывает источник БЕЗ воспроизведения.
        На Windows реальная буферизация может начаться только при play().
        """
        if self._force_exit or self.requested_track is not None or self.pending_slot is not None:
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
        auth_kwargs = (
            self.youtube_auth_kwargs() if track.get("source") == "youtube"
            else (self.soundcloud_auth_kwargs() if track.get("source") == "soundcloud" else {})
        )
        worker = StreamWorker(track, self, audio_quality=self.audio_quality, **auth_kwargs)
        self.prefetch_worker = worker
        worker.metadata_ready.connect(lambda data, k=key, w=worker:
                                      self.accept_stream_metadata(k, data) if not w._cancel_requested else None)
        worker.stream_ready.connect(
            lambda stream, title, elapsed, k=key:
                self.prefetch_ready(k, stream, title, elapsed)
        )
        worker.failed.connect(lambda error, k=key: self.prefetch_failed(k, error))
        worker.finished.connect(self.prefetch_finished)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def preload_in_qt(self, track, media_url):
        """Загружаем локальный источник в резервном проигрывателе, а для HTTP-прокси прогреваем буфер в ОЗУ."""
        if self.requested_track is not None or self.pending_slot is not None:
            return
        if self.fade_timer.isActive():
            QTimer.singleShot(120, self.prepare_next_track)
            return
        if not media_url.isLocalFile():
            # Для сетевых потоков (LocalStreamProxy) данные уже предзагружаются в ОЗУ
            # потоком BufferedStreamEntry. Не открываем сокет QMediaPlayer за несколько минут
            # до старта, чтобы FFmpeg на Windows не уходил в StalledMedia на паузе.
            url_str = media_url.toString()
            if url_str.startswith("http://127.0.0.1:") and "/stream/" in url_str:
                entry = LocalStreamProxy.instance().get_entry_by_url(url_str)
                if entry is not None:
                    entry.start()
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
        if self.prefetch_worker is not None and self.prefetch_target != key:
            self.prefetch_worker.cancel()
        if self.stream_worker is not None:
            if self.stream_target == key and not self.stream_worker._cancel_requested:
                self.set_status("Аудиоссылка для выбранного трека уже запрашивается…")
                return
            self.stream_worker.cancel()
            self.stream_worker = None
            self.stream_target = None
        # One cancelled request may finish in the background while the latest
        # selection starts immediately. Rapid clicks cannot spawn unlimited threads.
        if len(self._stream_workers) >= 3:
            self.stream_pending_track = dict(track)
            self.set_status("Готовлю последний выбранный трек…")
            return
        self.stream_pending_track = None
        self.stream_target = key
        self.set_status("Получаю ссылку на новый трек, предыдущий пока играет…")
        avoid_format = self._stream_details.get(key, {}).get("format_id", "") if self._network_recovery is not None else ""
        auth_kwargs = (
            self.youtube_auth_kwargs() if track.get("source") == "youtube"
            else (self.soundcloud_auth_kwargs() if track.get("source") == "soundcloud" else {})
        )
        worker = StreamWorker(track, self, audio_quality=self.audio_quality, avoid_format_id=avoid_format,
                              resume_position_ms=(self._network_recovery or {}).get("position", self._requested_start_position),
                              **auth_kwargs)
        self.stream_worker = worker
        self._stream_workers.add(worker)
        key = self.stream_target
        worker.metadata_ready.connect(lambda data, k=key, w=worker:
                                      self.accept_stream_metadata(k, data)
                                      if w is self.stream_worker and not w._cancel_requested else None)
        worker.stream_ready.connect(
            lambda stream, title, elapsed, k=key, w=worker:
                self.stream_ready(k, stream, title, elapsed)
                if w is self.stream_worker and not w._cancel_requested else None
        )
        worker.failed.connect(lambda message, k=key, w=worker:
                              self.stream_error(k, message)
                              if w is self.stream_worker and not w._cancel_requested else None)
        worker.finished.connect(lambda w=worker: self.stream_finished(w))
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def play_track(self, track, index, start_position=0, restore_session=False):
        """Запоминаем запрос и подготавливаем музыку на другом QMediaPlayer."""
        if self.supermix_session is not None and (self.queue_mode != "supermix" or index < 0):
            self._stop_supermix_session()
            self.queue_mode = "manual"
        elif self.supermix_session is not None:
            self.supermix_session["waiting"] = False
        self.cancel_pending_request(cancel_supermix=self.supermix_session is None)
        if not restore_session:
            self._restored_playback = None
        self._requested_start_position = max(0, int(start_position))
        self._network_recovery_attempts = 0
        self.requested_track = dict(track)
        self.requested_index = index
        self.request_started = time.perf_counter()
        self.pending_refreshed = False
        key = self._key(track)
        if not key:
            self.set_status("В выбранном треке нет ссылки.")
            self.requested_track = None
            return
        if self.prefetch_worker is not None and self.prefetch_target != key:
            self.prefetch_worker.cancel()

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

    @staticmethod
    def track_duration_ms(track):
        if not isinstance(track, dict) or track.get("is_live"):
            return 0
        try:
            seconds = float(track.get("duration") or 0)
            return int(seconds * 1000) if math.isfinite(seconds) and 0 < seconds <= 604800 else 0
        except (TypeError, ValueError, OverflowError):
            return 0

    def accept_stream_metadata(self, key, data):
        self._stream_details[key] = dict(data)
        self._stream_details.move_to_end(key)
        while len(self._stream_details) > 64:
            self._stream_details.popitem(last=False)
        duration = self.track_duration_ms(data)
        queue_changed = False
        for track in [self.requested_track, self.current_track, *self.queue_tracks]:
            if isinstance(track, dict) and self._key(track) == key:
                if duration or data.get("is_live"):
                    changed = track.get("duration") != duration / 1000 or track.get("is_live", False) != data.get("is_live", False)
                    track["duration"] = duration / 1000
                    track["is_live"] = bool(data.get("is_live"))
                    queue_changed |= changed
        if queue_changed:
            self.schedule_session_save()
        # Signed URLs and cookies are deliberately excluded from diagnostics.
        logging.getLogger("aurora").info("Аудиопоток: host=%s; format=%s; protocol=%s; duration_ms=%d",
                                       data.get("hostname", ""), data.get("format_id", ""),
                                       data.get("protocol", ""), duration)

    def playback_duration_ms(self):
        duration = self._last_duration
        if self._remote_playback():
            duration = max(duration, self.track_duration_ms(self.current_track))
        return duration

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
            recovering = self._network_recovery is not None
            if recovering:
                self._network_recovery = None
                self._playback_wanted = False
                self.playback_watchdog.stop()
            self.set_status("Не удалось восстановить поток. Проверь доступ к аудиосерверу." if recovering else
                            "Не удалось получить аудиопоток. Предыдущий трек продолжает играть.")
            logging.getLogger("aurora").warning("Ошибка аудиопотока: %s", message)
            self.show_toast("Не удалось подготовить трек: " + str(message)[:180], 4500)
            if auto_transition:
                self.recover_auto_transition_failure(failed_track, failed_index)
        else:
            logging.getLogger("aurora").info(f"[Music Player] Старая ошибка извлечения: {message}")

    def stream_finished(self, worker):
        self._stream_workers.discard(worker)
        if worker is self.stream_worker:
            self.stream_worker = None
            self.stream_target = None
        elif self.stream_worker is not None and not self.stream_worker._cancel_requested:
            return
        if self._force_exit:
            return
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
        else:
            QTimer.singleShot(0, self.pump_artwork_workers)

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
        self._recovery_seek_applied = False
        self.pending_media_timer.start(self.PENDING_MEDIA_TIMEOUT_MS)
        self.request_origin = origin
        self.audio_outputs[slot].setVolume(0.0)
        if player.source() != media_url or self._network_recovery is not None:
            self.standby_key = None
            self.standby_ready = False
            with QSignalBlocker(player):
                player.stop()
                if not player.source().isEmpty():
                    player.setSource(QUrl())
            player.setSource(media_url)
        # Запускаем сразу, не ожидая LoadedMedia; звук переключится по движению позиции.
        if self.pending_slot != slot or self.requested_track is None:
            return
        self._apply_recovery_seek(slot)
        player.play()
        if self.pending_slot == slot:
            self.set_status("Восстанавливаю звук с прежней позиции…" if self._network_recovery else
                            "Загружаю звук на втором плеере; предыдущий продолжает играть…")
        logging.getLogger("aurora").info(f"[Music Player] Qt запускает второй поток ({origin})")

    def on_pending_media_timeout(self):
        """Ограничивает ожидание Qt; обработчик ошибки сохраняет старый трек."""
        if self.pending_slot is None or self.requested_track is None:
            return
        self.on_slot_error(
            self.pending_slot, QMediaPlayer.Error.ResourceError,
            "Новый трек не начал воспроизведение за отведённое время. Попробуй ещё раз."
        )

    def _remote_playback(self):
        track = self.current_track or {}
        return (track.get("source") in ("youtube", "soundcloud")
                and not self.player.source().isLocalFile())

    def _ended_early(self):
        duration = self.playback_duration_ms()
        position = self._last_progress_position
        if duration <= 0 or position <= 0:
            return False
        qt_dur = self.player.duration()
        if qt_dur > 0 and abs(qt_dur - duration) <= 4500 and qt_dur - position <= 1200:
            return False
        return duration - position > 3000

    def check_playback_health(self):
        """Recover a frozen network stream; pauses and user selections are exempt."""
        if (self._force_exit or not self._playback_wanted or not self._remote_playback()
                or self.is_seeking or self.requested_track is not None
                or self.pending_slot is not None
                or self._finish_transition_pending
                or getattr(self, "_radio_waiting_for_tracks", False)
                or getattr(self, "_soundcloud_queue_waiting", False)
                or bool(self.supermix_session and self.supermix_session.get("waiting"))
                or self.player.playbackState() == QMediaPlayer.PlaybackState.PausedState):
            return
        if (self.player.mediaStatus() == QMediaPlayer.MediaStatus.EndOfMedia
                and not self._ended_early()):
            return
        duration = self.playback_duration_ms()
        if duration > 0 and self._last_progress_position >= duration - 800:
            return
        if time.monotonic() - self._last_progress_at >= self.PLAYBACK_STALL_SECONDS:
            self.recover_current_stream("нет данных от сервера")

    def release_media_slot(self, slot):
        """Dispose a broken demuxer and its connection before another attempt."""
        player = self.players[slot]
        if player.source().isEmpty():
            return
        host = player.source().host()
        self.audio_outputs[slot].setVolume(0.0)
        # stop/setSource can emit synchronous state/error callbacks. The previous
        # position is already captured; those callbacks must not erase it or recurse.
        with QSignalBlocker(player):
            player.stop()
            player.setSource(QUrl())
        logging.getLogger("aurora").info("Освобождён источник: slot=%d; host=%s", slot, host)
        if slot == self.active_slot:
            self.on_slot_playback_state(slot, QMediaPlayer.PlaybackState.StoppedState)

    def recover_current_stream(self, reason):
        if (self._force_exit or not self._playback_wanted or not self._remote_playback()
                or self.requested_track is not None or self.pending_slot is not None
                or self._finish_transition_pending):
            return False
        if self._network_recovery_attempts >= self.MAX_STREAM_RECOVERIES:
            self.release_media_slot(self.active_slot)
            self._playback_wanted = False
            self.playback_watchdog.stop()
            self.set_status("Аудиосервер недоступен. Проверь подключение и настройки «Запрета» или прокси, затем нажми ▶.")
            self.show_toast("Не удалось получить аудио после повторных подключений.", 4500)
            return True
        track = dict(self.current_track)
        position = self._last_progress_position
        duration = self.playback_duration_ms()
        self.cancel_pending_request(cancel_supermix=False)
        self._network_recovery_attempts += 1
        self._network_recovery = {"position": position, "duration": duration}
        self.requested_track = track
        self.requested_index = self.current_queue_index
        self.request_started = time.perf_counter()
        # This already IS a refresh. Do not chain the ordinary startup retry.
        self.pending_refreshed = True
        self.stream_cache.pop(self._key(track), None)
        self.standby_key = None
        self.standby_ready = False
        self.release_media_slot(self.active_slot)
        self.release_media_slot(self.idle_slot())
        logging.getLogger("aurora").info("Восстановление потока: %s; позиция %d мс; попытка %d",
                                       reason, position, self._network_recovery_attempts)
        self.start_stream_extraction(track)
        self.set_status("Соединение прервалось. Восстанавливаю трек с прежней позиции…")
        return True

    def _apply_recovery_seek(self, slot):
        recovery = self._network_recovery
        position = recovery["position"] if recovery is not None else self._requested_start_position
        if ((recovery is None and position <= 0) or slot != self.pending_slot or self._recovery_seek_applied
                or self.players[slot].source() != self.pending_media_url):
            return
        duration = self.players[slot].duration()
        if not self.players[slot].source().isLocalFile():
            duration = max(duration, self.track_duration_ms(self.requested_track), (recovery or {}).get("duration", 0))
        if duration > 0:
            position = min(position, max(0, duration - 1000))
            if recovery is not None:
                recovery["position"] = position
            self._requested_start_position = position
        if position > 0 and not self.players[slot].isSeekable():
            return
        self._recovery_seek_applied = True
        if position > 0:
            self.players[slot].setPosition(position)

    def on_slot_position(self, slot, position):
        """Отслеживает позицию обоих плееров и безопасно запускает автопереход."""
        if slot == self.pending_slot:
            if self._network_recovery is not None or self._requested_start_position > 0:
                self._apply_recovery_seek(slot)
                target = (self._network_recovery["position"] if self._network_recovery is not None else
                          self._requested_start_position)
                # setPosition emits positionChanged too. Wait for actual playback
                # beyond that position before making the recovered slot audible.
                if not self._recovery_seek_applied or position <= target:
                    return
            if (position > 0 and not self.pending_position_seen
                    and self.players[slot].source() == self.pending_media_url):
                self.pending_position_seen = True
                elapsed = time.perf_counter() - (self.request_started or time.perf_counter())
                qt_elapsed = time.perf_counter() - (self.pending_started or time.perf_counter())
                logging.getLogger("aurora").info(f"[Music Player] Новый поток начал менять позицию: всего {elapsed:.1f} с; Qt: {qt_elapsed:.1f} с")
                self.commit_switch(elapsed, qt_elapsed)
            return
        if slot != self.active_slot or self.player.source().isEmpty():
            return
        if position > 0 and position != self._last_progress_position:
            self._last_progress_position = position
            self._last_progress_at = time.monotonic()
            if (self._network_recovery_attempts > 0
                    and self._recovery_committed_position is not None
                    and position - self._recovery_committed_position >= 15000):
                self._network_recovery_attempts = 0
                self._recovery_committed_position = None
        if not self.is_seeking:
            self.seek_slider.setValue(position)
        self.position_label.setText(self.format_position(position))
        if self.mini_player is not None and self.mini_player.isVisible():
            self.mini_player.sync_position()

        # Проверка дешёвая: порог очереди и worker защищают от повторных запросов.
        if self.queue_mode == "supermix":
            self.maybe_refill_supermix()
        # Пополняем радио заранее, пока текущая композиция ещё звучит.
        if self.radio_mode_active:
            now = time.monotonic()
            if now - self._last_radio_refill_check > 4.0:
                self._last_radio_refill_check = now
                self.maybe_refill_radio()

        duration = self.playback_duration_ms() if self._remote_playback() else self.player.duration()
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
        if self.queue_mode == "supermix":
            return self.supermix_session is not None or self.peek_next_index() is not None
        if self._is_youtube_likes_playback():
            return self.peek_next_index() is not None
        if self.radio_mode_active:
            return self.peek_next_index() is not None or bool(self.current_track)
        return self.search_neighbor_track(1) is not None or self.peek_next_index() is not None

    def on_slot_duration(self, slot, duration):
        if slot != self.active_slot:
            return
        if duration > 0:
            self._last_duration = max(self._last_duration, duration) if self._remote_playback() else duration
        duration = self.playback_duration_ms() if self._remote_playback() else duration
        self.seek_slider.setRange(0, max(0, duration))
        self.seek_slider.setEnabled(duration > 0 and self.player.isSeekable())
        self.duration_label.setText(self.format_position(duration))

    def on_slot_status(self, slot, status):
        if self.players[slot].source().isEmpty():
            return
        if slot == self.pending_slot:
            if status in (QMediaPlayer.MediaStatus.LoadedMedia,
                          QMediaPlayer.MediaStatus.BufferingMedia,
                          QMediaPlayer.MediaStatus.BufferedMedia):
                self.pending_ever_loaded = True
                self._apply_recovery_seek(slot)
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
                logging.getLogger("aurora").info("Конец потока: source=%s; host=%s; position_ms=%d; qt_duration_ms=%d; expected_ms=%d",
                                               (self.current_track or {}).get("source", ""), self.player.source().host(),
                                               self._last_progress_position, self.player.duration(), self.playback_duration_ms())
                if self._ended_early() and self.recover_current_stream("поток завершился до конца трека"):
                    return
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
                             or self.supermix_session is not None
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
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self.play_button.setIcon(control_icon(
            "pause" if playing else "play", "#FFFFFF"
        ))
        if hasattr(self, "player_bar"):
            self.player_bar.sync_visualizer_state(playing)
        if hasattr(self, "expanded_cover"):
            self.expanded_cover.sync_vinyl_state()
        self.update_playing_row_highlight()
        self.refresh_mini_player()
        self.save_playback_checkpoint()

    def commit_switch(self, elapsed, qt_elapsed):
        """Второй плеер уже начал проигрывать — можно переключать звук."""
        if self.pending_slot is None or self.requested_track is None:
            return
        self.pending_media_timer.stop()
        recovery = self._network_recovery
        new = self.pending_slot
        old = self.active_slot
        self.active_slot = new
        self.player = self.players[new]
        self.audio_output = self.audio_outputs[new]
        self.current_track = self.requested_track
        if recovery is None and self.shuffle_enabled and isinstance(self.current_track, dict):
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
        self._network_recovery = None
        self._restored_playback = None
        self._requested_start_position = 0
        self._playback_wanted = True
        self._last_progress_at = time.monotonic()
        self._last_progress_position = self.player.position()
        self._recovery_committed_position = self._last_progress_position if recovery is not None else None
        self._last_duration = self.player.duration() or (recovery or {}).get("duration", 0)
        if not self._last_duration:
            try:
                self._last_duration = max(0, int(float(self.current_track.get("duration") or 0) * 1000))
            except (ValueError, TypeError, OverflowError):
                self._last_duration = 0
        if self._remote_playback():
            self._last_duration = max(self._last_duration, self.track_duration_ms(self.current_track), (recovery or {}).get("duration", 0))
            self.playback_watchdog.start()
        else:
            self.playback_watchdog.stop()

        title = self.current_track.get("title") or "Без названия"
        artist = self.current_track.get("artist") or ""
        self.bottom_title.setText(title)
        self.bottom_title.setToolTip(title)
        self.bottom_artist.setText(self.bottom_artist.fontMetrics().elidedText(
            artist, Qt.TextElideMode.ElideRight, max(80, self.bottom_artist.width() - 3)))
        self.bottom_artist.setToolTip(artist)
        self.show_cover(self.current_track.get("thumbnail", ""))
        if recovery is None:
            self.record_recent_track(self.current_track)
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
        QTimer.singleShot(0, self.pump_artwork_workers)
        self.set_status(f"Играет: {title}")
        self.save_playback_checkpoint()

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
            self.audio_outputs[old].setVolume(0.0)
            with QSignalBlocker(self.players[old]):
                self.players[old].stop()
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
            self.audio_outputs[old].setVolume(0.0)
            with QSignalBlocker(self.players[old]):
                self.players[old].stop()
                self.players[old].setSource(QUrl())
            # Когда бывший основной плеер освободился — предзагрузим следующую.
            QTimer.singleShot(0, self.prepare_next_track)

    def on_slot_error(self, slot, error, message):
        if (self._force_exit or error == QMediaPlayer.Error.NoError
                or (slot != self.pending_slot and self.players[slot].source().isEmpty())):
            return
        logging.getLogger("aurora").info(f"[Music Player] Ошибка Qt слота {slot}: {message}")
        if slot == self.pending_slot:
            self.pending_media_timer.stop()
            self.pending_slot = None
            self.pending_media_url = None
            self.release_media_slot(slot)
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
                recovering = self._network_recovery is not None
                if recovering:
                    self._network_recovery = None
                    self._playback_wanted = False
                    self.playback_watchdog.stop()
                self.set_status("Не удалось восстановить поток. Проверь доступ к аудиосерверу." if recovering else
                                "Новый трек не удалось открыть, старая музыка продолжает играть.")
                self.show_toast(message or "Неподдерживаемый аудиопоток", 4500)
            return
        if slot != self.active_slot:
            # Ошибка предзагрузки — ничего не ломаем в основном плеере.
            if self.standby_key is not None:
                self.stream_cache.pop(self.standby_key, None)
                self.prefetch_failed_until[self.standby_key] = time.monotonic() + 120
            self.standby_key = None
            self.standby_ready = False
            self.release_media_slot(slot)
            return
        self.release_media_slot(slot)
        if self.requested_track is not None or self.pending_slot is not None:
            # A manual selection is already loading. A dead previous source must
            # neither cancel that request nor report the error again every frame.
            return
        if self._finish_transition_pending:
            failed_track = dict(self.requested_track or self.current_track or {})
            failed_index = (self.requested_index if self.requested_track is not None
                            else self.current_queue_index)
            self.set_status("Ошибка аудио при автопереходе; пробую следующий трек.")
            self.recover_auto_transition_failure(failed_track, failed_index)
            return
        if self.recover_current_stream("ошибка сетевого потока"):
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
        self.refresh_mini_player()

    def toggle_playback(self):
        if self._restored_playback is not None:
            if self.requested_track is not None:
                self.cancel_pending_request(cancel_supermix=False)
                self._playback_wanted = False
                self.set_status("Продолжение отменено. Нажми ▶, когда будешь готов.")
            else:
                self.resume_saved_session()
            return
        if self._network_recovery is not None:
            self.cancel_pending_request(cancel_supermix=False)
            self._playback_wanted = False
            self.playback_watchdog.stop()
            self.player.pause()
            self.set_status("Воспроизведение на паузе.")
            return
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._playback_wanted = False
            self.player.pause()
        elif not self.player.source().isEmpty():
            self._playback_wanted = True
            self._network_recovery_attempts = 0
            self._last_progress_at = time.monotonic()
            if self._remote_playback():
                self.playback_watchdog.start()
            duration = self.player.duration()
            if duration > 0 and self.player.position() >= duration - 300:
                self.player.setPosition(0)
                self._finish_guard_url = ""
                self._finish_transition_pending = False
            self.player.play()
        elif self.requested_track is not None:
            self.set_status("Новый трек ещё подготавливается…")
        elif self.current_track is not None and self.player.source().isEmpty():
            self.play_track(self.current_track, self.current_queue_index,
                            start_position=self._last_progress_position)
        elif 0 <= self.current_queue_index < len(self.queue_tracks):
            self.play_queue_index(self.current_queue_index)
        elif self.queue_tracks:
            self.play_queue_index(0)
        else:
            message = "Выбери трек в лайках или найди его через поиск."
            self.set_status(message)
            self.show_toast(message)
            if self.current_source != "likes":
                self.search_input.setFocus()

    def stop_all(self):
        self._restored_playback = None
        self._playback_wanted = False
        self.playback_watchdog.stop()
        self._stop_supermix_session()
        self.cancel_pending_request()
        for player, output in zip(self.players, self.audio_outputs):
            player.stop()
            output.setVolume(0.0)
        self.audio_outputs[self.active_slot].setVolume(self.volume)
        self.play_button.setIcon(control_icon("play", "#FFFFFF"))
        self._last_progress_position = 0
        self.set_status("Воспроизведение остановлено.")
        self.save_playback_checkpoint()

    def seek_pressed(self):
        self.is_seeking = True

    def seek_released(self):
        if self.player.isSeekable():
            position = self.seek_slider.value()
            self._last_progress_position = position
            self._last_progress_at = time.monotonic()
            self.player.setPosition(position)
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
        self.playback_watchdog.stop()
        self.save_preferences()
        self.checkpoint_timer.stop()
        self.session_save_timer.stop()
        if self.mini_player is not None:
            self.mini_player.hide()
        for player in self.players:
            player.stop()
        if self.tray_icon is not None:
            self.tray_icon.hide()
        event.accept()


def run_smoke_test():
    """Exercise the actual frozen Qt/audio bundle with isolated, disposable data."""
    global _SMOKE_DIRECTORY
    import tempfile
    import wave
    with tempfile.TemporaryDirectory(prefix="aurora-smoke-") as directory:
        root = Path(directory)
        _SMOKE_DIRECTORY = root
        for variable, folder in (("LOCALAPPDATA", "cache"), ("APPDATA", "data"),
                                 ("XDG_CONFIG_HOME", "config"), ("XDG_DATA_HOME", "data"),
                                 ("XDG_CACHE_HOME", "cache"), ("XDG_RUNTIME_DIR", "runtime")):
            path = root / folder
            path.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.environ[variable] = str(path)
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        set_windows_app_id()
        app = QApplication([sys.argv[0]])
        configure_application(app)
        if app.windowIcon().pixmap(32, 32).isNull():
            raise RuntimeError("Иконка приложения недоступна")
        app.setStyle("Fusion")
        setup_font(app)
        window = MusicPlayer(settings=QSettings(str(root / "settings.ini"), QSettings.Format.IniFormat))
        for player in window.players:
            player.setAudioOutput(None)
        # Paint the main window before hiding it: mini-only startup misses
        # failures in sidebar/card paintEvent handlers in the frozen build.
        window.show()
        app.processEvents()
        if window.grab().isNull():
            raise RuntimeError("Не удалось отрисовать главное окно")
        window.show_mini_player()
        path = root / "sample.wav"
        with wave.open(str(path), "wb") as sound:
            sound.setparams((1, 2, 44100, 0, "NONE", "not compressed"))
            sound.writeframes(b"\x00\x00" * 44100 * 2)
        result = [1]
        def finish(code):
            result[0] = code
            timer.stop()
            window._force_exit = True
            window.stop_all()
            for player in window.players:
                player.setSource(QUrl())
            window.close()
            window.deleteLater()
            app.exit(code)
        timer = QTimer(window)
        timer.setInterval(100)
        timer.timeout.connect(lambda: finish(0) if window.current_track and window.player.position() > 0 else None)
        QTimer.singleShot(15000, lambda: finish(1))
        window.play_track({"source": "local", "url": str(path), "title": "Smoke test"}, -1)
        timer.start()
        app.exec()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
        _SMOKE_DIRECTORY = None
        return result[0]


def main():
    if "--smoke-test" in sys.argv:
        sys.exit(run_smoke_test())
    try:
        setup_logging()
        set_windows_app_id()
        app = QApplication(sys.argv)
        configure_application(app)
        app.setStyle("Fusion")
        family = setup_font(app)
        window = MusicPlayer()
        window.setProperty("fontFamily", family)
        media_filter = WindowsMediaKeyFilter(window) if sys.platform == "win32" else None
        if media_filter is not None:
            app.installNativeEventFilter(media_filter)
        window.show()
        window.raise_()
        window.activateWindow()
        try:
            code = app.exec()
        finally:
            if media_filter is not None:
                app.removeNativeEventFilter(media_filter)
        sys.exit(code)
    except SystemExit:
        raise
    except Exception as exc:
        import traceback
        details = traceback.format_exc()
        try:
            err_log = Path(__file__).resolve().parent / "aurora_startup_error.log"
            err_log.write_text(details, encoding="utf-8")
        except Exception:
            pass
        if sys.platform == "win32":
            try:
                ctypes.windll.user32.MessageBoxW(
                    None,
                    f"Не удалось запустить плеер:\n{exc}\n\nПодробности записаны в aurora_startup_error.log",
                    "Aurora Music Player — Ошибка запуска",
                    0x00000010,
                )
            except Exception:
                pass
        raise


if __name__ == "__main__":
    main()
