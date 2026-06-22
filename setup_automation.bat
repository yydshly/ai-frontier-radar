@echo off
REM AI Frontier Radar - first-time automation setup.
REM Configures source sync + frequent fetch + daily report scheduled tasks.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup_windows_automation.ps1"
echo.
pause
