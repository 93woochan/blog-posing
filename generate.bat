@echo off
chcp 65001 > nul
cd /d "%~dp0"

REM Drag and Drop Folder Path
SET TARGET=%~1

REM [Optional] If you want to double-click instead of drag-and-drop, 
REM remove the 'REM' from the line below and write your folder path.
REM SET TARGET=C:\your_folder_path_here

if "%TARGET%"=="" (
    echo.
    echo ====================================================
    echo   Naver Auto Posting - Generator
    echo ====================================================
    echo.
    echo [ERROR] No target folder selected!
    echo.
    echo Usage: 
    echo   Drag and drop your photo folder onto this 'generate.bat' file.
    echo.
    pause
    exit /b 0
)

echo.
echo ====================================================
echo   Target Folder: %TARGET%
echo ====================================================
echo.
echo Running Python script...
python -m src.post "%TARGET%"

echo.
echo ====================================================
pause