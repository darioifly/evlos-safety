@echo off
echo ========================================
echo Starting Video Worker Process
echo ========================================
echo.
echo This process handles:
echo - Camera stream processing
echo - YOLO person detection
echo - Writing detections to database
echo.
cd backend
venv\Scripts\python.exe video_worker.py
pause
