"""Start real Python entry points with an absent or unusable optional browser."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'player_aurora_smart_beautiful_fixed_ui_repaint.py'


class StandaloneStartup(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='aurora-startup-')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        shutil.copyfile(ROOT / SOURCE, self.root / SOURCE)
        shutil.copyfile(ROOT / 'player.py', self.root / 'player.py')
        self.env = dict(os.environ, QT_QPA_PLATFORM='offscreen', PYTHONPATH='')
        if sys.platform.startswith('linux'):
            self.env['QT_AUDIO_BACKEND'] = 'pulseaudio'

    def run_python(self, *args):
        return subprocess.run([sys.executable, *args], cwd=self.root, env=self.env,
                              capture_output=True, text=True, timeout=25)

    def test_import_does_not_load_optional_browser_or_chromium(self):
        result = self.run_python('-c',
            "import runpy,sys,json; m=runpy.run_path(" + repr(SOURCE) + "); "
            "print(json.dumps({'browser': 'youtube_music_backend' in sys.modules, "
            "'chromium': any(k.startswith('PyQt6.QtWebEngine') for k in sys.modules), "
            "'late_import_ready': m['QCoreApplication'].testAttribute(m['Qt'].ApplicationAttribute.AA_ShareOpenGLContexts)}))")
        self.assertEqual(result.returncode, 0, result.stderr)
        state = json.loads(result.stdout)
        self.assertFalse(state['browser'])
        self.assertFalse(state['chromium'])
        self.assertTrue(state['late_import_ready'])

    def test_main_script_opens_and_decodes_audio_without_backend_file(self):
        result = self.run_python(SOURCE, '--smoke-test')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_an_old_sidecar_does_not_prevent_the_window_from_opening(self):
        (self.root / 'youtube_music_backend.py').write_text(
            'QWebEngineProfile = object()\nWEB_DRIVER_PROTOCOL = 1\n', encoding='utf-8')
        result = self.run_python('player.py', '--smoke-test')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_player_entry_point_survives_missing_qt_webengine_and_dll_errors(self):
        for module in ("QWebEngineProfile = None\n",
                       "raise ImportError('DLL load failed while importing QtWebEngineCore')\n",
                       "raise OSError('Qt WebEngine runtime cannot be loaded')\n"):
            with self.subTest(module=module):
                (self.root / 'youtube_music_backend.py').write_text(module, encoding='utf-8')
                shutil.rmtree(self.root / '__pycache__', ignore_errors=True)
                result = self.run_python('player.py', '--smoke-test')
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
