@echo off
setlocal EnableExtensions DisableDelayedExpansion
title Aurora Music Player - EXE builder

pushd "%~dp0"
if errorlevel 1 (
    echo ERROR: Cannot open the folder containing this script.
    if not defined CI pause
    exit /b 1
)

set "PLAYER_SOURCE=player_aurora_smart_beautiful_fixed_ui_repaint.py"
set "PLAYER_NAME=AuroraMusicPlayer"
set "PLAYER_WINDOW_OPTION=--windowed"
set "PLAYER_BUILD_PYTHON=.build-venv\Scripts\python.exe"
set "PLAYER_PYTHON_COMMAND="
set "PLAYER_FONT_OPTIONS="
set "PLAYER_BUILD_MODE=--onedir"

:options
if "%~1"=="" goto source
if /i "%~1"=="debug" (
    set "PLAYER_NAME=AuroraMusicPlayer-debug"
    set "PLAYER_WINDOW_OPTION=--console"
)
if /i "%~1"=="single" set "PLAYER_BUILD_MODE=--onefile"
shift
goto options

:source
set "PLAYER_OUTPUT=dist\%PLAYER_NAME%\%PLAYER_NAME%.exe"
if "%PLAYER_BUILD_MODE%"=="--onefile" set "PLAYER_OUTPUT=dist\%PLAYER_NAME%.exe"

if not exist "%PLAYER_SOURCE%" if exist "player.py" set "PLAYER_SOURCE=player.py"
if not exist "%PLAYER_SOURCE%" goto missing_source
if exist "%PLAYER_BUILD_PYTHON%" goto dependencies

echo [1/3] Looking for Python and creating the build environment...
for %%V in (3.13 3.12 3.14) do (
    if not defined PLAYER_PYTHON_COMMAND (
        py -%%V -c "import sys; sys.exit(0 if sys.maxsize > 2**32 else 1)" >nul 2>&1
        if not errorlevel 1 set "PLAYER_PYTHON_COMMAND=py -%%V"
    )
)
if not defined PLAYER_PYTHON_COMMAND (
    python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) and sys.maxsize > 2**32 else 1)" >nul 2>&1
    if not errorlevel 1 set "PLAYER_PYTHON_COMMAND=python"
)
if not defined PLAYER_PYTHON_COMMAND goto missing_python

%PLAYER_PYTHON_COMMAND% -m venv .build-venv
if errorlevel 1 goto failed

:dependencies
echo [2/3] Installing or updating build dependencies. Internet is required.
"%PLAYER_BUILD_PYTHON%" -m pip install --upgrade pip "pyinstaller>=6.16,<7" "PyQt6>=6.8,<7" "yt-dlp[default]" "ytmusicapi>=1.12,<2"
if errorlevel 1 goto failed

if exist "fonts\*.ttf" set "PLAYER_FONT_OPTIONS=--add-data=fonts/*.ttf:fonts"
if exist "fonts\*.otf" set "PLAYER_FONT_OPTIONS=%PLAYER_FONT_OPTIONS% --add-data=fonts/*.otf:fonts"

echo [3/3] Building %PLAYER_NAME%.exe. Keep this window open until the build finishes.
"%PLAYER_BUILD_PYTHON%" -m PyInstaller --noconfirm --clean %PLAYER_BUILD_MODE% %PLAYER_WINDOW_OPTION% --name "%PLAYER_NAME%" --distpath dist --workpath build --specpath build --collect-all yt_dlp --collect-all ytmusicapi %PLAYER_FONT_OPTIONS% "%PLAYER_SOURCE%"
if errorlevel 1 goto failed
if not exist "%PLAYER_OUTPUT%" goto failed

echo.
echo BUILD SUCCEEDED
echo Your EXE: "%CD%\%PLAYER_OUTPUT%"
if "%PLAYER_BUILD_MODE%"=="--onedir" echo Keep the entire %PLAYER_NAME% folder, including _internal, together.
echo You can now open that EXE. Python is not required to run the built application.
goto success

:missing_source
echo ERROR: Put build_exe.bat next to %PLAYER_SOURCE% and try again.
goto failed

:missing_python
echo ERROR: Python was not found. Install 64-bit Python 3.13 or 3.12 from python.org.
echo Include the Python launcher or enable "Add python.exe to PATH" during installation.
goto failed

:failed
echo.
echo BUILD FAILED. See the error above. Keep or copy that error for troubleshooting.
if not defined CI pause
popd
exit /b 1

:success
if not defined CI pause
popd
exit /b 0
