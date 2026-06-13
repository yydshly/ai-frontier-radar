@echo off
REM AI Frontier Radar - control panel (GUI).
REM Double-click to open the launcher window (start/stop/status/daily cycle).
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0scripts\launcher.ps1"
