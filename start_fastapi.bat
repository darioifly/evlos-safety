@echo off
echo ========================================
echo Starting FastAPI Server (SQLite Mode)
echo ========================================
echo.
echo This server handles HTTP/WebSocket requests
echo Video processing runs in separate video_worker.py
echo.
cd backend
venv\Scripts\python.exe main_sqlite.py
pause
