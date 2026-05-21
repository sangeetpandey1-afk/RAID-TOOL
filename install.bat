@echo off
title RAID System - First Time Setup
color 0E
echo ============================================
echo   RAID System - First Time Installation
echo ============================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not installed!
    echo         Download from: https://www.python.org/downloads/
    echo         IMPORTANT: Check "Add Python to PATH" during install!
    pause
    exit /b 1
)

echo [1/3] Installing Python packages...
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Package installation failed!
    pause
    exit /b 1
)

echo.
echo [2/3] Generating document templates...
python scripts\generate_templates.py

echo.
echo [3/3] Testing server startup...
python -c "from backend.app import app; print('SUCCESS: All OK!')"
if errorlevel 1 (
    echo [ERROR] Server test failed!
    pause
    exit /b 1
)

echo.
echo ============================================
echo   Installation COMPLETE!
echo.
echo   To start the server, double-click: run.bat
echo   Or run: python -m backend.app
echo.
echo   Then open: http://localhost:5000
echo   Mobile:    http://localhost:5000/mobile/qr
echo ============================================
pause
