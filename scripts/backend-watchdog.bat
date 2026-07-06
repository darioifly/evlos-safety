@echo off
REM ============================================================================
REM backend-watchdog.bat — riavvia evlos-safety se la porta 7002 non risponde.
REM Eseguito dalla Scheduled Task EvlosSafetyWatchdog ogni 3 minuti (SYSTEM).
REM Stesso pattern di EvlosWorkerWatchdog (potree).
REM ============================================================================
netstat -ano | findstr LISTENING | findstr :7002 >nul
if errorlevel 1 (
    echo [%date% %time%] porta 7002 giu', riavvio EvlosSafetyBackend >> C:\Users\iflys\projects\evlos-safety\backend\logs\watchdog.log
    schtasks /Run /TN EvlosSafetyBackend
)
