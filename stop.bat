@echo off
echo Stopping Person Detection System Backend...

REM Find and kill only the backend Python process (listening on port 7002)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":7002" ^| findstr "LISTENING"') do (
    echo Killing backend process (PID: %%a)
    powershell.exe -Command "Stop-Process -Id %%a -Force" 2>nul
    if errorlevel 1 (
        echo Retrying with taskkill...
        taskkill /F /PID %%a 2>nul
    )
)

echo Backend stopped!
echo.
echo Note: Frontend is still running. To stop it, press Ctrl+C in the frontend terminal.
pause
