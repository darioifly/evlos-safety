@echo off
echo ========================================
echo Person Detection System - Setup
echo ========================================
echo.

echo [1/4] Creating Python virtual environment...
cd backend
python -m venv venv

echo [2/4] Installing Python dependencies...
call venv\Scripts\activate
pip install -r requirements.txt

echo [3/4] Installing Node.js dependencies...
cd ..\frontend
call npm install

echo [4/4] Creating .env file...
cd ..
if not exist .env (
    copy .env.example .env
    echo Created .env file - Please edit with your settings
) else (
    echo .env file already exists - skipping
)

echo.
echo ========================================
echo Setup Complete!
echo.
echo Next steps:
echo 1. Edit .env file with your NxWitness credentials
echo 2. Run start_dev.bat for development mode
echo 3. Or run start_prod.bat for production mode
echo ========================================
pause
