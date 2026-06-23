# setup_windows_automation.ps1 - first-time Windows automation setup.
#
# Reuses the existing task installers. It does not start the Web service.
# Actions:
#   1. Validate .env.
#   2. Set RADAR_FETCH_INTERVAL_OVERRIDE_HOURS to the requested interval.
#   3. Initialize the DB and sync configured sources.
#   4. Install the frequent fetch task.
#   5. Install the daily finalization/report task (anchor + 5 minutes).
#   6. Remove legacy/duplicate Radar tasks so only the canonical pair remains.

param(
    [int]$FetchIntervalHours = 3,
    [string]$DailyRunTime
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ProjectRoot "..")).Path
Set-Location $ProjectRoot

if ($FetchIntervalHours -lt 1 -or $FetchIntervalHours -gt 24) {
    throw "-FetchIntervalHours must be between 1 and 24."
}

function Get-ProjectPython {
    $bundled = Join-Path $ProjectRoot "python\python.exe"
    $venv = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if (Test-Path $bundled) { return $bundled }
    if (Test-Path $venv) { return $venv }
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    throw "Python not found. Install dependencies or use the portable package."
}

function Set-EnvValue {
    param([string]$Path, [string]$Name, [string]$Value)
    $lines = @(Get-Content -LiteralPath $Path -Encoding UTF8)
    $pattern = "^\s*" + [regex]::Escape($Name) + "\s*="
    $updated = $false
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match $pattern) {
            $lines[$i] = "$Name=$Value"
            $updated = $true
            break
        }
    }
    if (-not $updated) {
        $lines += "$Name=$Value"
    }
    # Windows PowerShell 5.1's `-Encoding UTF8` writes a BOM. A BOM on the first
    # .env key can confuse some dotenv readers, so write UTF-8 without BOM.
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllLines($Path, $lines, $utf8NoBom)
}

function Remove-ConflictingRadarTasks {
    # -Force replaces a task with the same name, but old releases or previous
    # unpack locations may have registered another name and keep running.
    $canonicalNames = @(
        "AI Frontier Radar Fetch",
        "AI Frontier Radar Daily Cycle"
    )
    $knownRunnerPattern = 'run_fetch_scheduled\.ps1|run_daily_cycle_scheduled\.ps1|run_daily_cycle_once\.ps1|run_due_sources_once\.py|run_daily_cycle\.py'
    $removed = 0

    foreach ($task in @(Get-ScheduledTask -ErrorAction Stop)) {
        if ($canonicalNames -contains $task.TaskName) {
            continue
        }

        $actionText = (($task.Actions | ForEach-Object {
            "$($_.Execute) $($_.Arguments) $($_.WorkingDirectory)"
        }) -join " ")
        $isRadarNamedTask = $task.TaskName -like "AI Frontier Radar*"
        $usesKnownRadarRunner = $actionText -match $knownRunnerPattern
        if (-not $isRadarNamedTask -and -not $usesKnownRadarRunner) {
            continue
        }

        Write-Host "[CLEANUP] Removing conflicting task: $($task.TaskName)" -ForegroundColor Yellow
        Unregister-ScheduledTask -TaskName $task.TaskName -TaskPath $task.TaskPath -Confirm:$false
        $removed++
    }

    if ($removed -eq 0) {
        Write-Host "[OK] No legacy or duplicate automation tasks found." -ForegroundColor Green
    } else {
        Write-Host "[OK] Removed $removed legacy/duplicate automation task(s)." -ForegroundColor Green
    }
}

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "AI Frontier Radar - Automation Setup" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Project root:    $ProjectRoot" -ForegroundColor Gray
Write-Host "Fetch interval:  every $FetchIntervalHours hour(s)" -ForegroundColor Gray

$EnvFile = Join-Path $ProjectRoot ".env"
if (-not (Test-Path $EnvFile)) {
    throw ".env not found. Copy .env.example to .env and fill required API keys first."
}

Set-EnvValue -Path $EnvFile -Name "RADAR_FETCH_INTERVAL_OVERRIDE_HOURS" -Value $FetchIntervalHours
Write-Host "[OK] RADAR_FETCH_INTERVAL_OVERRIDE_HOURS=$FetchIntervalHours" -ForegroundColor Green

$PythonExe = Get-ProjectPython
Write-Host "[STEP] Initializing DB and syncing sources..." -ForegroundColor Yellow
& $PythonExe -u (Join-Path $ProjectRoot "scripts\sync_sources_from_config.py") --apply
if ($LASTEXITCODE -ne 0) {
    throw "Source synchronization failed (exit $LASTEXITCODE)."
}

Write-Host "[STEP] Installing frequent fetch task..." -ForegroundColor Yellow
& (Join-Path $ProjectRoot "scripts\install_windows_fetch_task.ps1") -IntervalHours $FetchIntervalHours

Write-Host "[STEP] Installing daily report task..." -ForegroundColor Yellow
$dailyInstaller = Join-Path $ProjectRoot "scripts\install_windows_daily_task.ps1"
if ([string]::IsNullOrWhiteSpace($DailyRunTime)) {
    & $dailyInstaller
} else {
    & $dailyInstaller -RunTime $DailyRunTime
}

Write-Host "[STEP] Filtering legacy and duplicate automation tasks..." -ForegroundColor Yellow
Remove-ConflictingRadarTasks

Write-Host ""
Write-Host "[SUCCESS] Automation is configured." -ForegroundColor Green
Write-Host "  Frequent fetch: every $FetchIntervalHours hour(s)" -ForegroundColor Gray
Write-Host "  Daily report:   anchor + 5 minutes (or explicit override)" -ForegroundColor Gray
Write-Host "  Task filter:    only the canonical fetch + daily tasks remain" -ForegroundColor Gray
Write-Host "  Check status:   .\scripts\status_local.ps1" -ForegroundColor Gray
Write-Host "  Fetch log:      logs\fetch.log" -ForegroundColor Gray
Write-Host "  Daily log:      logs\daily_cycle.log" -ForegroundColor Gray
