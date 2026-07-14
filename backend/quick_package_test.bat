@echo off
cd /d "%~dp0\.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0quick_test.ps1" -Package -Pause
exit /b %ERRORLEVEL%
