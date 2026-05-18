@echo off
cd /d "%~dp0"
echo [1/2] customtkinter, pyinstaller ?? ?...
python -m pip install customtkinter pyinstaller

echo.
echo [2/2] exe ?? ?... (? ? ??)
pyinstaller --name NaverAutoPost ^
  --onedir ^
  --windowed ^
  --collect-all customtkinter ^
  --collect-all google.genai ^
  --collect-all playwright ^
  --hidden-import PIL ^
  --hidden-import dotenv ^
  --add-data "data;data" ^
  --add-data ".env.example;." ^
  src/app.py

echo.
echo ====================================================
echo ?? ??! dist\NaverAutoPost\ ?? ??
echo ?? PC? ?? ??? ?????.
echo .env ??? ?? ?? ??!
echo ====================================================
pause