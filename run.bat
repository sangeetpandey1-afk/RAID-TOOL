@echo off
REM =====================================================================
REM RAID-TOOL launcher for Windows.
REM
REM Activates the venv, opens the browser at http://localhost:5000/, and
REM runs the Flask backend in this console window.
REM
REM Press Ctrl+C in this window to stop the server.
REM =====================================================================
setlocal EnableExtensions
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo [ERROR] venv not found.  Run install.bat first.
    pause
    exit /b 1
)

call "venv\Scripts\activate.bat"
if errorlevel 1 (
    echo [ERROR] could not activate venv.
    pause
    exit /b 2
)

echo.
echo ====================================================
echo  Starting Raid Management System
echo ====================================================
echo.
echo  Browser UI:   http://localhost:5000/
echo  Health:       http://localhost:5000/api/health
echo.
echo  Press Ctrl+C to stop.
echo.

REM Open the browser ~3 seconds after we start, in the background.
start "RAID-TOOL Browser" /min cmd /c "timeout /t 3 /nobreak > nul && start http://localhost:5000/"

REM Run the server in the foreground — Ctrl+C stops it cleanly.
python -m backend.app

REM If the server exits, give the user a chance to read errors.
echo.
echo Server stopped.
pause
endlocal
