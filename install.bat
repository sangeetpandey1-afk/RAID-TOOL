@echo off
REM =====================================================================
REM RAID-TOOL one-click installer for Windows.
REM
REM Run from the repo root by simply double-clicking install.bat.
REM
REM What it does:
REM   1. Verifies Python 3.10+
REM   2. Creates a local venv\ (only first run)
REM   3. Upgrades pip and installs requirements.txt
REM   4. Generates the 9 default Word templates
REM   5. Builds the Excel starter workbook (frontend\RaidSystem.xlsx)
REM   6. Initializes the SQLite DB by importing the backend module
REM
REM After install completes, double-click run.bat to launch the system.
REM =====================================================================
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

echo.
echo ====================================================
echo  RAID-TOOL Installer
echo  Repo: %CD%
echo ====================================================
echo.

REM --- 1. Python ------------------------------------------------------
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found in PATH.
    echo         Install Python 3.10 or newer from https://www.python.org/downloads/
    echo         Make sure to tick "Add Python to PATH" during install.
    echo.
    pause
    exit /b 1
)

for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo [1/6] Python found: !PYVER!

REM --- 2. venv --------------------------------------------------------
if exist "venv\Scripts\python.exe" (
    echo [2/6] venv already exists, reusing.
) else (
    echo [2/6] Creating virtual environment in venv\ ...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] venv creation failed.
        pause
        exit /b 2
    )
)

call "venv\Scripts\activate.bat"
if errorlevel 1 (
    echo [ERROR] could not activate venv.
    pause
    exit /b 3
)

REM --- 3. pip install -------------------------------------------------
echo [3/6] Upgrading pip ...
python -m pip install --upgrade pip --quiet --disable-pip-version-check
if errorlevel 1 (
    echo [WARN] pip upgrade failed but continuing.
)

echo [4/6] Installing dependencies from requirements.txt ...
python -m pip install -r requirements.txt --disable-pip-version-check
if errorlevel 1 (
    echo [ERROR] dependency installation failed.  See messages above.
    pause
    exit /b 4
)

REM --- 4. Templates ---------------------------------------------------
echo [5/6] Generating Word templates ...
python scripts\generate_default_templates.py
if errorlevel 1 (
    echo [WARN] template generation failed.  Documents may use fallback layout.
)

REM --- 5. Excel starter -----------------------------------------------
echo [6/6] Building Excel starter workbook ...
python frontend\build_xlsm.py
if errorlevel 1 (
    echo [WARN] xlsx build failed.  Browser UI will still work.
)

REM --- 6. DB warm-up so first run is instant --------------------------
echo Initializing database schema ...
python -c "from backend.app import app; print('Routes:', len(list(app.url_map.iter_rules())))"
if errorlevel 1 (
    echo [WARN] backend smoke import failed — see messages above.
)

echo.
echo ====================================================
echo  INSTALL COMPLETE
echo ====================================================
echo.
echo  Browser UI:   http://localhost:5000/frontend/
echo  API:          http://localhost:5000/api/health
echo  Excel UI:     frontend\RaidSystem.xlsx (optional)
echo.
echo  To start the system, double-click  run.bat
echo.
pause
endlocal
