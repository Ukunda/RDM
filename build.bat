@echo off
echo ========================================
echo   Random Clip Player - Build Script
echo ========================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    exit /b 1
)

echo [1/2] Installing dependencies...
pip install -q -r requirements.txt >nul 2>&1

echo [2/2] Building with PyInstaller...
python -m PyInstaller RandomClipPlayer.spec --clean --noconfirm
if errorlevel 1 (
    echo ERROR: Build failed
    exit /b 1
)

echo.
echo ========================================
echo   Build complete!
echo   dist\RandomClipPlayer.exe
echo ========================================
echo.
pause
