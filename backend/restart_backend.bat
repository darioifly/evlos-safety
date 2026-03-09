@echo off
echo ========================================
echo Restarting Backend Server
echo ========================================
echo.

REM Kill ALL Python processes (main server + worker processes)
echo Terminating all Python processes...
taskkill /F /IM python.exe >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo All Python processes terminated
) else (
    echo No Python processes found
)

echo Waiting 3 seconds for cleanup...
timeout /t 3 /nobreak >nul

echo Starting backend (main_sqlite.py)...
cd /d "%~dp0"
call venv\Scripts\activate.bat
python main_sqlite.py
