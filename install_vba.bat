@echo off
REM =====================================================================
REM Optional one-click Excel VBA setup.
REM
REM Run this AFTER install.bat if you want to use the Excel macro front-end
REM in addition to the browser UI.  This step:
REM
REM   1. Re-builds frontend\RaidSystem.xlsx (if missing)
REM   2. Imports every .bas / .cls file from frontend\vba\ into the workbook
REM   3. Saves the result as frontend\RaidSystem.xlsm
REM
REM Pre-requisite (one-time, manual):
REM   File -> Options -> Trust Center -> Trust Center Settings ->
REM   Macro Settings -> [X] Trust access to the VBA project object model
REM
REM The browser UI (run.bat) does NOT need this step.
REM =====================================================================
setlocal EnableExtensions
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo [ERROR] venv not found.  Run install.bat first.
    pause
    exit /b 1
)
call "venv\Scripts\activate.bat"

if not exist "frontend\RaidSystem.xlsx" (
    echo Building Excel starter workbook ...
    python frontend\build_xlsm.py
)

echo.
echo ====================================================
echo  Importing VBA modules into RaidSystem.xlsm ...
echo ====================================================
echo.

cscript //nologo frontend\import_vba.vbs
if errorlevel 1 (
    echo.
    echo [ERROR] VBA import failed.  See messages above.
    echo.
    echo Common cause: "Trust access to the VBA project object model"
    echo is OFF.  Turn it ON in:
    echo    Excel -> File -> Options -> Trust Center -> Trust Center Settings
    echo    -> Macro Settings -> [X] Trust access to the VBA project object model
    echo and re-run install_vba.bat.
    pause
    exit /b 2
)

echo.
echo ====================================================
echo  EXCEL UI READY
echo ====================================================
echo.
echo Open this file in Excel:
echo    %CD%\frontend\RaidSystem.xlsm
echo.
pause
endlocal
