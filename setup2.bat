@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo ====================================================
echo   Naver Auto Posting - Setup
echo ====================================================
echo.
echo [1/3] Installing Python packages...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [X] Installation failed. Please check Python installation.
    echo     https://www.python.org/downloads/
    pause
    exit /b 1
)

echo.
echo [2/3] Downloading Playwright Chromium...
python -m playwright install chromium
if errorlevel 1 (
    echo [X] Chromium download failed.
    pause
    exit /b 1
)

echo.
echo [3/3] Setup Completed Successfully!
echo.
echo Next Steps:
echo   1. Copy '.env.example' and rename it to '.env'
echo   2. Open '.env' and enter your ANTHROPIC_API_KEY
echo   3. Drag and drop your image folder onto 'publish.bat'
echo.
pause