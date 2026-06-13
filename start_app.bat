@echo off
REM AI Frontier Radar - one-click start.
REM Double-click this file to start the web service and open it in your browser.
REM (Renamable to a Chinese name on Chinese Windows if you prefer.)
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_and_open.ps1"
