@echo off
title ORBIT Control Center
cd /d "%~dp0"

if /i "%1"=="--cli" goto :cli

:: Launch the GUI Control Center without keeping a black console window open
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" "orbit_launcher.py"
    exit /b 0
)
if exist "venv\Scripts\pythonw.exe" (
    start "" "venv\Scripts\pythonw.exe" "orbit_launcher.py"
    exit /b 0
)
where pythonw >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    start "" pythonw "orbit_launcher.py"
    exit /b 0
)

:cli
echo ========================================================
echo            Starting ORBIT (CLI Fallback)
echo ========================================================
if exist ".venv\Scripts\python.exe" (
    start "ORBIT Backend" cmd /k ".venv\Scripts\python.exe app.py --server"
) else (
    start "ORBIT Backend" cmd /k "python app.py --server"
)
start "ORBIT Frontend" cmd /k "npm --prefix frontend run dev"
