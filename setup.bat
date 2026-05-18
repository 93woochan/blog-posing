@echo off
REM ============================================================
REM   네이버 자동 포스팅 - 최초 1회만 실행 (의존성 설치)
REM   더블클릭하면 됩니다.
REM ============================================================
chcp 65001 > nul
cd /d "%~dp0"

echo.
echo ====================================================
echo   네이버 자동 포스팅 - 초기 셋업
echo ====================================================
echo.
echo 1/3 Python 패키지 설치 중...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo X 패키지 설치 실패. Python 이 설치되어 있는지 확인하세요.
    echo   https://www.python.org/downloads/ ^( Add to PATH 체크 필수 ^)
    pause
    exit /b 1
)

echo.
echo 2/3 Playwright Chromium 다운로드 중 ^(약 200MB^)...
python -m playwright install chromium
if errorlevel 1 (
    echo X Chromium 다운로드 실패.
    pause
    exit /b 1
)

echo.
echo 3/3 셋업 완료!
echo.
echo 다음 단계:
echo   1. .env.example 을 .env 로 복사
echo   2. 메모장으로 .env 열고 ANTHROPIC_API_KEY 채우기 ^(선택 사항^)
echo   3. publish.bat 에 사진 폴더를 끌어다 놓으면 자동 포스팅 시작
echo.
pause
