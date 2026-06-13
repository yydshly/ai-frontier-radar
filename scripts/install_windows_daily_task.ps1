# install_windows_daily_task.ps1 — Install a Windows Task Scheduler job for the daily cycle.
#
# Usage:
#   .\scripts\install_windows_daily_task.ps1
#
# What it does:
# - Creates a daily task "AI Frontier Radar Daily Cycle" that runs at 08:05
# - Calls scripts\run_daily_cycle.py --apply
# - Appends stdout/stderr to logs\daily_cycle.log
#
# NOTE: Does NOT read or print any API keys from .env.

param(
    [string]$TaskName = "AI Frontier Radar Daily Cycle",
    [string]$RunTime = "08:05",
    [string]$ScriptName = "run_daily_cycle.py",
    [string]$ScriptArgs = "--apply"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ProjectRoot "..")).Path
Set-Location $ProjectRoot

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "AI Frontier Radar — Install Daily Task" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Project root: $ProjectRoot" -ForegroundColor Gray

# ── Directory setup ──────────────────────────────────────────────────────────
$LogsDir = Join-Path $ProjectRoot "logs"
$RuntimeRunsDir = Join-Path $ProjectRoot "runtime\daily_cycle_runs"
foreach ($dir in @($LogsDir, $RuntimeRunsDir)) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Force -Path $dir | Out-Null
        Write-Host "[CREATED] $dir" -ForegroundColor Yellow
    }
}

# ── Python selection ────────────────────────────────────────────────────────
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    Write-Host "[INFO] .venv not found. Using python from PATH." -ForegroundColor Yellow
    $PythonExe = "python"
}
Write-Host "Python: $PythonExe" -ForegroundColor Gray

# ── Script path ─────────────────────────────────────────────────────────────
$ScriptPath = Join-Path $ProjectRoot "scripts\$ScriptName"
if (-not (Test-Path $ScriptPath)) {
    Write-Host "[ERROR] $ScriptPath not found!" -ForegroundColor Red
    throw "Script not found: $ScriptPath"
}
Write-Host "Script: $ScriptPath" -ForegroundColor Gray
Write-Host "Args:   $ScriptArgs" -ForegroundColor Gray

# ── Log path ─────────────────────────────────────────────────────────────────
$DailyLog = Join-Path $ProjectRoot "logs\daily_cycle.log"
Write-Host "Log:   $DailyLog" -ForegroundColor Gray
Write-Host ""

# ── Build the scheduled action ───────────────────────────────────────────────
# We use cmd.exe /c to run an inline command so that:
#   1. Working directory is set to ProjectRoot
#   2. stdout/stderr are redirected to daily_cycle.log
# The outer quotes around Python path handle spaces in directory names.
$PythonQuoted = "`"$PythonExe`""
$ScriptQuoted = "`"$ScriptPath`""
$DailyLogQuoted = "`"$DailyLog`""
$ProjectRootQuoted = "`"$ProjectRoot`""

# Build the command that gets passed to cmd.exe /c
$ActionCommand = "cd /d $ProjectRootQuoted && $PythonQuoted $ScriptQuoted $ScriptArgs >> $DailyLogQuoted 2>&1"

Write-Host "Installing Windows Task Scheduler task..." -ForegroundColor Green
Write-Host "  Task name:  $TaskName" -ForegroundColor Gray
Write-Host "  Run time:   $RunTime daily" -ForegroundColor Gray
Write-Host "  Command:    $ActionCommand" -ForegroundColor DarkGray
Write-Host ""

# ── Remove existing task if present ─────────────────────────────────────────
try {
    $existing = schtasks /Query /TN $TaskName /FO LIST 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[INFO] Task '$TaskName' already exists. Deleting old task..." -ForegroundColor Yellow
        schtasks /Delete /TN $TaskName /F 2>$null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[WARN] Failed to delete old task (may already be gone)." -ForegroundColor Yellow
        }
    }
} catch {
    # Task doesn't exist — that's fine, we'll create it.
}

# ── Create the task ──────────────────────────────────────────────────────────
$createResult = schtasks /Create `
    /TN $TaskName `
    /SC DAILY `
    /ST $RunTime `
    /TR "cmd.exe /c $ActionCommand" `
    /F `
    2>&1

if ($LASTEXITCODE -eq 0) {
    Write-Host "[SUCCESS] Task '$TaskName' installed." -ForegroundColor Green
} else {
    Write-Host "[ERROR] Failed to create task. Exit code: $LASTEXITCODE" -ForegroundColor Red
    Write-Host $createResult -ForegroundColor Red
    throw "schtasks /Create failed with exit code $LASTEXITCODE"
}

# ── Verify and show task info ───────────────────────────────────────────────
Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Task Summary" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Task name:    $TaskName" -ForegroundColor Gray
Write-Host "  Run time:     $RunTime daily" -ForegroundColor Gray
Write-Host "  Project root: $ProjectRoot" -ForegroundColor Gray
Write-Host "  Python:       $PythonExe" -ForegroundColor Gray
Write-Host "  Script:       $ScriptPath $ScriptArgs" -ForegroundColor Gray
Write-Host "  Log:          $DailyLog" -ForegroundColor Gray
Write-Host ""

try {
    $info = schtasks /Query /TN $TaskName /FO LIST 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[INFO] Task details:" -ForegroundColor Gray
        Write-Host $info -ForegroundColor DarkGray
    }
} catch {
    Write-Host "[WARN] Could not retrieve task details." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "NOTE: Ensure .env is configured with your API keys before the task runs." -ForegroundColor Yellow
Write-Host "Log output will be appended to: $DailyLog" -ForegroundColor Gray
