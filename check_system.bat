@echo off
echo ========================================
echo System Requirements Check
echo ========================================
echo.

echo [1/6] Checking Python...
python --version
if %errorlevel% neq 0 (
    echo ERROR: Python not found!
    echo Please install Python 3.9 or higher
) else (
    echo OK: Python installed
)
echo.

echo [2/6] Checking Node.js...
node --version
if %errorlevel% neq 0 (
    echo ERROR: Node.js not found!
    echo Please install Node.js 18.x or higher
) else (
    echo OK: Node.js installed
)
echo.

echo [3/6] Checking npm...
npm --version
if %errorlevel% neq 0 (
    echo ERROR: npm not found!
) else (
    echo OK: npm installed
)
echo.

echo [4/6] Checking NVIDIA GPU...
nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv
if %errorlevel% neq 0 (
    echo WARNING: NVIDIA driver not found or GPU not available
    echo GPU acceleration will not be available - system will use CPU
) else (
    echo OK: NVIDIA GPU detected
)
echo.

echo [5/6] Checking CUDA...
nvcc --version
if %errorlevel% neq 0 (
    echo WARNING: CUDA toolkit not found
    echo GPU acceleration may not be available
) else (
    echo OK: CUDA toolkit installed
)
echo.

echo [6/6] Checking project files...
if exist backend\main.py (
    echo OK: Backend files found
) else (
    echo ERROR: Backend files missing!
)

if exist frontend\package.json (
    echo OK: Frontend files found
) else (
    echo ERROR: Frontend files missing!
)

if exist .env (
    echo OK: .env configuration found
) else (
    echo WARNING: .env not found - will be created during setup
)
echo.

echo ========================================
echo Check Complete
echo ========================================
echo.
echo Next steps:
echo 1. If Python/Node.js missing: Install them first
echo 2. If all OK: Run setup.bat
echo 3. After setup: Run start_dev.bat or start_prod.bat
echo ========================================
pause
