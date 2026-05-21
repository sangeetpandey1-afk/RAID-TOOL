@echo off
title RAID Management System - Server
color 0A
echo ============================================
echo   RAID Management System - Starting...
echo ============================================
echo.

:: Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found! Install Python from python.org
    echo         Make sure "Add to PATH" is checked during install.
    pause
    exit /b 1
)

:: Install dependencies if needed
echo [1/3] Checking dependencies...
pip install -r requirements.txt --quiet 2>nul
if errorlevel 1 (
    echo [WARN] Some packages may have failed. Trying anyway...
)

:: Generate templates if missing
if not exist "templates\provisional_consumer.docx" (
    echo [2/3] Generating document templates...
    python scripts\generate_templates.py
) else (
    echo [2/3] Templates already exist. Skipping.
)

:: Start server
echo [3/3] Starting server...
echo.
echo ============================================
echo   Server running at:
echo   http://localhost:5000
echo.
echo   Mobile app:
echo   http://localhost:5000/mobile/qr
echo.
echo   Press Ctrl+C to stop
echo ============================================
echo.

python -m backend.app

pause
