@echo off
setlocal EnableExtensions
title Aurora Music Player
pushd "%~dp0"

if exist ".build-venv\Scripts\python.exe" (
    ".build-venv\Scripts\python.exe" "player_aurora_smart_beautiful_fixed_ui_repaint.py" %*
    goto end
)
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" "player_aurora_smart_beautiful_fixed_ui_repaint.py" %*
    goto end
)

where py >nul 2>&1
if not errorlevel 1 (
    py -3 "player_aurora_smart_beautiful_fixed_ui_repaint.py" %*
    goto end
)

python "player_aurora_smart_beautiful_fixed_ui_repaint.py" %*

:end
if errorlevel 1 (
    echo.
    echo Произошла ошибка при запуске. Подробности сохранены в aurora_startup_error.log
    pause
)
popd
