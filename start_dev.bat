@echo off
echo ========================================
echo Person Detection System - Development
echo ========================================
echo.

echo Stopping existing processes...

REM Kill Python processes (backend)
echo Killing backend processes (Python on port 7002)...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":7002" ^| findstr "LISTENING"') do (
    echo Killing process %%a
    taskkill /F /PID %%a >nul 2>&1
)

REM Kill Node/Vite processes (frontend)
echo Killing frontend processes (Node/Vite on port 5173)...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":5173" ^| findstr "LISTENING"') do (
    echo Killing process %%a
    taskkill /F /PID %%a >nul 2>&1
)

REM Give system time to release ports
timeout /t 2 /nobreak >nul

echo.
echo Starting Backend Server...
cd backend
start cmd /k "venv\Scripts\activate && set DEV_MODE=true && python main.py"

timeout /t 3 /nobreak >nul

echo Starting Frontend Dev Server...
cd ..\frontend
start cmd /k "npm run dev"

echo.
echo ========================================
echo Services Started:
echo - Backend: http://localhost:7002
echo - Frontend: http://localhost:5173
echo - API Docs: http://localhost:7002/docs
echo ========================================
