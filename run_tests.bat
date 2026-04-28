@echo off
echo ================================================================
echo PrecoBot v2.1 - Running Tests
echo ================================================================
echo.

cd /d %~dp0

echo Running test_all.py...
e:\Code\.venv\Scripts\python.exe tests\test_all.py

echo.
echo ================================================================
echo Test run complete
echo ================================================================
pause
