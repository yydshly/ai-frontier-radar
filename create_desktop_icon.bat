@echo off
REM Create friendly, icon-bearing shortcuts (in this folder AND on the Desktop).
REM Run this once after extracting the portable folder for a recognizable launcher.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\create_shortcuts.ps1" -Desktop
echo.
pause
