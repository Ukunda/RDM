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
pip install PyQt5 python-vlc pyinstaller

echo.
echo [2/3] Creating executable...
pyinstaller --onefile --windowed --name "RandomClipPlayer" --icon=NONE random_clip_player.py

echo.
echo [3/3] Build complete!
echo.
echo ========================================
echo   Executable location:
echo   dist\RandomClipPlayer.exe
echo ========================================
echo.
echo NOTE: Make sure VLC media player is installed on your system!
echo       Download from: https://www.videolan.org/vlc/
echo.
pause
