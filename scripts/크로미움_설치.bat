@echo off
echo ============================================
echo   Chromium Browser Install (1st time only)
echo ============================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed.
    echo Please install Python 3.11+ from https://python.org
    pause
    exit /b 1
)

echo Installing playwright...
python -m pip install playwright --quiet

echo Downloading Chromium (100~200MB)...
set PLAYWRIGHT_BROWSERS_PATH=%LOCALAPPDATA%\ms-playwright
python -m playwright install chromium

if errorlevel 1 (
    echo [ERROR] Install failed. Check your internet connection.
) else (
    echo Done! You can now run the main app.
)
pause