# install_windows_daily_task.ps1 - Install a RELIABLE Windows Task Scheduler job
# for the daily cycle (finalize previous period + send -> fetch -> summarize ->
# report -> audio -> health report).
#
# Usage:
#   .\scripts\install_windows_daily_task.ps1                 # auto-aligns to anchor
#   .\scripts\install_windows_daily_task.ps1 -RunTime 22:05  # explicit override
#
# When -RunTime is omitted it is auto-derived from RADAR_DAILY_ANCHOR_HOUR in .env
# (anchor hour + 5 min), so the task fires right after the period it finalizes
# closes. The two MUST stay aligned, or the report is finalized a cycle late.
#
# Reliability (the whole point):
#   - StartWhenAvailable: if the PC was OFF/asleep at the scheduled time, the task
#     runs as soon as possible after the machine is available again (the daily
#     cycle then back-fills any missed days). Plain `schtasks /Create` does NOT do
#     this, which is why it was unreliable.
#   - Restart on failure (2x), execution time limit (2h), no overlapping runs.
#
# Runs as the current user (only while logged on, which is the normal desktop
# case). Does NOT read or print any API keys.

param(
    [string]$TaskName = "AI Frontier Radar Daily Cycle",
    [string]$RunTime
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ProjectRoot "..")).Path
Set-Location $ProjectRoot

# ── Auto-align RunTime to the daily anchor (unless explicitly provided) ──────
# The cycle finalizes the period that just closed at the anchor, so the task
# should fire at (anchor hour):05. Read RADAR_DAILY_ANCHOR_HOUR from .env.
if (-not $PSBoundParameters.ContainsKey('RunTime') -or [string]::IsNullOrWhiteSpace($RunTime)) {
    $anchorHour = $null
    $envFile = Join-Path $ProjectRoot ".env"
    if (Test-Path $envFile) {
        $m = Select-String -Path $envFile -Pattern '^\s*RADAR_DAILY_ANCHOR_HOUR\s*=\s*(\d{1,2})' |
            Select-Object -First 1
        if ($m) { $anchorHour = [int]$m.Matches[0].Groups[1].Value }
    }
    if ($null -ne $anchorHour -and $anchorHour -ge 0 -and $anchorHour -le 23) {
        $RunTime = '{0:D2}:05' -f $anchorHour
        Write-Host "Aligned RunTime to RADAR_DAILY_ANCHOR_HOUR=$anchorHour -> $RunTime" -ForegroundColor Green
    } else {
        $RunTime = "08:05"
        Write-Host "RADAR_DAILY_ANCHOR_HOUR not found in .env; defaulting RunTime to $RunTime" -ForegroundColor Yellow
    }
}

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "AI Frontier Radar - Install Daily Task (reliable)" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Project root: $ProjectRoot" -ForegroundColor Gray

# ── Directory setup ──────────────────────────────────────────────────────────
foreach ($dir in @((Join-Path $ProjectRoot "logs"), (Join-Path $ProjectRoot "runtime\daily_cycle_runs"))) {
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
}

# ── The scheduled action runs the non-interactive runner ─────────────────────
$ScheduledScript = Join-Path $ProjectRoot "scripts\run_daily_cycle_scheduled.ps1"
if (-not (Test-Path $ScheduledScript)) {
    throw "Runner not found: $ScheduledScript"
}

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$ScheduledScript`"" `
    -WorkingDirectory $ProjectRoot

$trigger = New-ScheduledTaskTrigger -Daily -At ([datetime]$RunTime)

# StartWhenAvailable is the key reliability flag (catch up missed runs).
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 10) `
    -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

$description = "AI Frontier Radar: daily fetch/summarize/report/audio + back-fill of missed days. Runs at $RunTime; catches up if the PC was off."

Write-Host "Installing task '$TaskName' (daily at $RunTime, catch-up on)..." -ForegroundColor Green
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description $description `
    -Force | Out-Null

# ── Verify ───────────────────────────────────────────────────────────────────
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -eq $task) {
    throw "Task '$TaskName' was not registered."
}

Write-Host ""
Write-Host "[SUCCESS] Task installed." -ForegroundColor Green
Write-Host "  Task name:     $TaskName" -ForegroundColor Gray
Write-Host "  Run time:      $RunTime daily (+ catch-up if missed)" -ForegroundColor Gray
Write-Host "  Runner:        $ScheduledScript" -ForegroundColor Gray
Write-Host "  Log:           $(Join-Path $ProjectRoot 'logs\daily_cycle.log')" -ForegroundColor Gray
Write-Host "  Run record:    $(Join-Path $ProjectRoot 'runtime\daily_cycle_runs\latest.json')" -ForegroundColor Gray
Write-Host ""
Write-Host "Tips:" -ForegroundColor Cyan
Write-Host "  - Test now:     Start-ScheduledTask -TaskName `"$TaskName`"" -ForegroundColor Gray
Write-Host "  - Check status: Get-ScheduledTaskInfo -TaskName `"$TaskName`"" -ForegroundColor Gray
Write-Host "  - Ensure .env has your API keys before the task runs." -ForegroundColor Yellow
Write-Host "  - RunTime must match RADAR_DAILY_ANCHOR_HOUR (omit -RunTime to auto-align)." -ForegroundColor Yellow
Write-Host "  - For working email/Feishu links, set RADAR_PUBLIC_BASE_URL in .env." -ForegroundColor Yellow
Write-Host "  - Task runs while you are logged on; StartWhenAvailable catches up after the PC is on." -ForegroundColor Gray
