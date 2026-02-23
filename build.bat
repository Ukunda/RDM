@echo off
echo ========================================
echo   Random Clip Player - Build Script
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python from https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/3] Installing required packages...
pip install PySide6 python-mpv requests websocket-client Nuitka

echo.
echo [2/3] Creating executable with Nuitka...
REM --windows-disable-console hides the console in release builds.
python -m nuitka --standalone --onefile ^
    --windows-disable-console ^
    --include-data-dir=lib=lib ^
    --enable-plugin=pyside6 ^
    --output-filename=RandomClipPlayer.exe ^
    random_clip_player.py

echo.
echo [3/3] Build complete!
echo.
echo ========================================
echo   Executable location:
echo   dist\RandomClipPlayer.exe
echo ========================================
echo.
pause
