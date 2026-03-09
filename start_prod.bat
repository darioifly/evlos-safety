@echo off
echo ========================================
echo Person Detection System - Production
echo ========================================
echo.

echo Building Frontend...
cd frontend
call npm run build

echo.
echo Starting Production Server...
cd ..\backend
call venv\Scripts\activate
python -m uvicorn main:app --host 0.0.0.0 --port 8000

echo.
echo ========================================
echo Server running at http://localhost:8000
echo ========================================
