@echo off
echo ============================================
echo   Build: Blog Auto Post Tool
echo ============================================
echo.

cd /d "%~dp0"

echo [1/3] Building exe...

python -m PyInstaller ^
  --onefile ^
  --windowed ^
  --name "blog-autopost" ^
  --collect-all customtkinter ^
  --collect-all google.genai ^
  --collect-all playwright ^
  --hidden-import PIL._tkinter_finder ^
  --hidden-import PIL._imaging ^
  --hidden-import dotenv ^
  --hidden-import src.app ^
  --hidden-import src.post ^
  --hidden-import src.publisher ^
  --hidden-import src.config ^
  src\app.py

if not exist "dist\blog-autopost.exe" (
    echo [FAIL] Build failed.
    pause
    exit /b 1
)

ren "dist\blog-autopost.exe" "은지의블로그.exe"

echo.
echo [2/3] Copying data files...
if not exist "dist\data" mkdir "dist\data"
if exist "data\style_guide.md" copy /y "data\style_guide.md" "dist\data\" >nul
if exist "data\exemplars.md"   copy /y "data\exemplars.md"   "dist\data\" >nul
if exist "크로미움_설치.bat"   copy /y "크로미움_설치.bat"   "dist\" >nul
if exist "사용설명서.txt"       copy /y "사용설명서.txt"       "dist\" >nul

echo.
echo [3/3] Creating .env template...
if not exist "dist\.env" (
    echo GEMINI_API_KEY=PUT_YOUR_KEY_HERE> "dist\.env"
    echo NAVER_ID=>> "dist\.env"
    echo NAVER_PW=>> "dist\.env"
    echo BLOG_ID=>> "dist\.env"
    echo CATEGORY_NAME=>> "dist\.env"
)

echo.
echo ============================================
echo   Build complete! Check dist\ folder.
echo ============================================
pause