# Application icon

`aurora.ico` contains the existing headphone artwork from `make_service_artwork`
in 16, 24, 32, 48, 64, 128 and 256 px. The same icon is used by Qt windows,
the tray and the PyInstaller EXE resource. It is generated locally, without downloads.

To regenerate it with PyQt6 installed:

```bash
python tools/generate_app_icon.py
```
