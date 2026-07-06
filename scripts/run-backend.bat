@echo off
REM ============================================================================
REM run-backend.bat — avvio evlos-safety (FastAPI + YOLO workers) dal venv.
REM Eseguito dalla Scheduled Task EvlosSafetyBackend (ONSTART, SYSTEM).
REM I log applicativi ruotano in backend\logs\ (WindowsSafeRotatingFileHandler);
REM questo file cattura solo lo stdout/stderr di uvicorn.
REM ============================================================================
cd /d C:\Users\iflys\projects\evlos-safety\backend
venv\Scripts\python.exe main_sqlite.py >> logs\backend_stdout.log 2>&1
