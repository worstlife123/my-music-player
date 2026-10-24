"""Export the existing in-app headphone artwork as a multi-size Windows ICO."""
import importlib.util
import os
from pathlib import Path
import struct

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("aurora_icon_source", ROOT / "player_aurora_smart_beautiful_fixed_ui_repaint.py")
player = importlib.util.module_from_spec(spec)
spec.loader.exec_module(player)
app = player.QApplication.instance() or player.QApplication([])
frames = []
for side in (16, 24, 32, 48, 64, 128, 256):
    pixmap = player.make_service_artwork("brand", pixel_size=side)
    pixmap.setDevicePixelRatio(1)
    buffer = player.QBuffer()
    buffer.open(player.QIODevice.OpenModeFlag.WriteOnly)
    if not pixmap.save(buffer, "PNG"):
        raise RuntimeError("Cannot encode application icon")
    frames.append((side, bytes(buffer.data())))
header = struct.pack("<HHH", 0, 1, len(frames))
offset = 6 + 16 * len(frames)
entries = []
for side, data in frames:
    entries.append(struct.pack("<BBBBHHII", side % 256, side % 256, 0, 0, 1, 32, len(data), offset))
    offset += len(data)
output = ROOT / "assets" / "aurora.ico"
output.parent.mkdir(exist_ok=True)
output.write_bytes(header + b"".join(entries) + b"".join(data for _, data in frames))
print(f"Wrote {output.name}: {len(frames)} sizes, {output.stat().st_size} bytes")
