# install_windows_fetch_task.ps1 - Install a frequent FETCH-ONLY Task Scheduler job.
#
# This is the companion to install_windows_daily_task.ps1. The daily task
# finalizes + sends the report once a day; this task fetches due sources every
# few hours so the day's window is well-populated before it is finalized
# (otherwise a once-daily fetch under-samples the window — see README
# "信息及时性：抓取节奏与报告窗口").
#
# Usage:
#   .\scripts\install_windows_fetch_task.ps1                 # every 3 hours
#   .\scripts\install_windows_fetch_task.ps1 -IntervalHours 2
#
# IMPORTANT: also set RADAR_FETCH_INTERVAL_OVERRIDE_HOURS in .env to the same
# value (e.g. 3). Each source pins fetch_interval_hours: 24 in sources.yaml, which
# beats RADAR_DEFAULT_FETCH_INTERVAL_HOURS — so ONLY the OVERRIDE forces frequent
# fetching for all sources. Without it this task is a no-op.

param(
    [string]$TaskName = "AI Frontier Radar Fetch",
    [int]$IntervalHours = 3
)

$ErrorActionPreference = "Stop"

if ($IntervalHours -lt 1 -or $IntervalHours -gt 24) {
    throw "-IntervalHours must be between 1 and 24."
}

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ProjectRoot "..")).Path
Set-Location $ProjectRoot

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "AI Frontier Radar - Install Fetch Task (frequent)" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Project root: $ProjectRoot" -ForegroundColor Gray
Write-Host "Interval:     every $IntervalHours hour(s)" -ForegroundColor Gray

if (-not (Test-Path (Join-Path $ProjectRoot "logs"))) {
    New-Item -ItemType Directory -Force -Path (Join-Path $ProjectRoot "logs") | Out-Null
}

$ScheduledScript = Join-Path $ProjectRoot "scripts\run_fetch_scheduled.ps1"
if (-not (Test-Path $ScheduledScript)) { throw "Runner not found: $ScheduledScript" }

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$ScheduledScript`"" `
    -WorkingDirectory $ProjectRoot

# Repeat every N hours, indefinitely, starting a minute from now.
$trigger = New-ScheduledTaskTrigger `
    -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Hours $IntervalHours) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
    -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

$description = "AI Frontier Radar: frequent fetch of due sources (every $IntervalHours h) so the daily window is fresh before finalization. No LLM, no report."

Write-Host "Installing task '$TaskName' (every $IntervalHours h)..." -ForegroundColor Green
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description $description `
    -Force | Out-Null

if ($null -eq (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue)) {
    throw "Task '$TaskName' was not registered."
}

Write-Host ""
Write-Host "[SUCCESS] Fetch task installed." -ForegroundColor Green
Write-Host "  Task name:  $TaskName" -ForegroundColor Gray
Write-Host "  Interval:   every $IntervalHours hour(s) (+ catch-up if missed)" -ForegroundColor Gray
Write-Host "  Runner:     $ScheduledScript" -ForegroundColor Gray
Write-Host "  Log:        $(Join-Path $ProjectRoot 'logs\fetch.log')" -ForegroundColor Gray
Write-Host ""
Write-Host "REMINDER: set RADAR_FETCH_INTERVAL_OVERRIDE_HOURS=$IntervalHours in .env," -ForegroundColor Yellow
Write-Host "          else per-source fetch_interval_hours (24) wins and this task no-ops." -ForegroundColor Yellow
