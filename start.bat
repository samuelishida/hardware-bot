@echo off
echo ========================================
echo PrecoBot - Quick Start
echo ========================================
echo.

set PYTHON=e:\Code\.venv\Scripts\python.exe

if not exist "%PYTHON%" (
    echo ERROR: Python not found at %PYTHON%
    exit /b 1
)

echo [1/5] Checking dependencies...
%PYTHON% -c "import discord, playwright, aiosqlite" 2>nul
if errorlevel 1 (
    echo Installing dependencies...
    %PYTHON% -m pip install -r requirements.txt -q
)
echo [OK] Dependencies

echo [2/5] Checking Chromium...
%PYTHON% -m playwright install chromium >nul 2>&1
echo [OK] Chromium

echo [3/5] Checking database...
%PYTHON% -c "from db.database import init_db; import asyncio; asyncio.run(init_db())" 2>nul
if errorlevel 1 (
    echo ERROR: Database initialization failed
    exit /b 1
)
echo [OK] Database

echo.
echo ========================================
echo Choose an option:
echo ========================================
echo 1. Start bot (normal)
echo 2. Run all tests
echo 3. Test scrapers only
echo 4. Test sites only
echo 5. Check configuration
echo 6. Exit
echo ========================================
echo.

set /p choice="Enter choice (1-6): "

if "%choice%"=="1" (
    echo Starting PrecoBot...
    %PYTHON% main.py
) else if "%choice%"=="2" (
    echo Running all tests...
    echo === Test 1: Configuration ===
    %PYTHON% test_bot_start.py
    echo === Test 2: Sites ===
    %PYTHON% test_sites.py
    echo === Test 3: Scrapers ===
    %PYTHON% test_scrapers.py
    echo All tests completed!
) else if "%choice%"=="3" (
    echo Testing scrapers...
    %PYTHON% test_scrapers.py
) else if "%choice%"=="4" (
    echo Testing sites...
    %PYTHON% test_sites.py
) else if "%choice%"=="5" (
    echo Checking configuration...
    %PYTHON% test_bot_start.py
) else if "%choice%"=="6" (
    echo Exiting...
    exit /b 0
) else (
    echo Invalid choice!
    exit /b 1
)

echo.
echo ========================================
echo Operation completed!
echo ========================================
pause
