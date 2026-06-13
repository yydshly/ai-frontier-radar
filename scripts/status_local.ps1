# status_local.ps1 - Show local run status for AI Frontier Radar.
#
# Usage:
#   .\scripts\status_local.ps1
#
# This script:
# - Does NOT start the web service
# - Does NOT run the daily cycle
# - Does NOT call any LLM
# - Does NOT access the network
# - Is fully read-only

param(
    [string]$TaskName = "AI Frontier Radar Daily Cycle",
    [int]$WebPort = 8765
)

$ErrorActionPreference = "Continue"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ProjectRoot "..")).Path
Set-Location $ProjectRoot

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "AI Frontier Radar Local Status" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Project root
Write-Host "Project root:" -ForegroundColor White
Write-Host "  $ProjectRoot" -ForegroundColor Gray
Write-Host ""

# Web service status
Write-Host "Web Service:" -ForegroundColor White
$webAddress = "http://127.0.0.1:${WebPort}"
Write-Host "  Address: $webAddress" -ForegroundColor Gray

try {
    $Connections = Get-NetTCPConnection -LocalPort $WebPort -State Listen -ErrorAction SilentlyContinue
} catch {
    $Connections = @()
}

if ($Connections -and $Connections.Count -gt 0) {
    $PID = $Connections[0].OwningProcess
    $Process = Get-Process -Id $PID -ErrorAction SilentlyContinue
    $ProcessName = if ($Process) { $Process.ProcessName } else { "Unknown" }
    Write-Host "  Status: Running" -ForegroundColor Green
    Write-Host "  PID:  $PID ($ProcessName)" -ForegroundColor Gray
} else {
    Write-Host "  Status: Not running" -ForegroundColor Yellow
}
Write-Host ""

# Windows scheduled task status
Write-Host "Windows Scheduled Task:" -ForegroundColor White
Write-Host "  Task name: $TaskName" -ForegroundColor Gray

try {
    $taskInfo = schtasks /Query /TN $TaskName /FO LIST 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  Status: Installed" -ForegroundColor Green
        foreach ($line in $taskInfo) {
            if ($line -match "Next Run Time:\s*(.+)") {
                Write-Host ("  Next run: " + $matches[1].Trim()) -ForegroundColor Gray
            }
            if ($line -match "Last Run Time:\s*(.+)") {
                Write-Host ("  Last run: " + $matches[1].Trim()) -ForegroundColor Gray
            }
            if ($line -match "Last Result:\s*(.+)") {
                Write-Host ("  Last result: " + $matches[1].Trim()) -ForegroundColor Gray
            }
        }
    } else {
        Write-Host "  Status: Not installed" -ForegroundColor Yellow
    }
} catch {
    Write-Host "  Status: Not installed" -ForegroundColor Yellow
}
Write-Host ""

# Key directories
Write-Host "Key Directories:" -ForegroundColor White

$checks = @(
    @{Label="Config (.env)"; Path=Join-Path $ProjectRoot ".env"},
    @{Label="Sources config"; Path=Join-Path $ProjectRoot "config\sources.yaml"},
    @{Label="Data directory"; Path=Join-Path $ProjectRoot "data"},
    @{Label="Runtime directory"; Path=Join-Path $ProjectRoot "runtime"},
    @{Label="Logs directory"; Path=Join-Path $ProjectRoot "logs"},
    @{Label="Web log"; Path=Join-Path $ProjectRoot "logs\app.log"},
    @{Label="Daily cycle log"; Path=Join-Path $ProjectRoot "logs\daily_cycle.log"},
    @{Label="Latest report"; Path=Join-Path $ProjectRoot "runtime\daily_cycle_runs\latest.json"}
)

foreach ($item in $checks) {
    $path = $item.Path
    if (Test-Path $path) {
        Write-Host ("  [EXISTS] " + $item.Label) -ForegroundColor Green
        Write-Host ("            " + $path) -ForegroundColor DarkGray
    } else {
        Write-Host ("  [MISSING] " + $item.Label) -ForegroundColor Yellow
        Write-Host ("            " + $path) -ForegroundColor DarkGray
    }
}
Write-Host ""

# Latest daily cycle run
Write-Host "Latest Daily Cycle Run:" -ForegroundColor White

$latestJson = Join-Path $ProjectRoot "runtime\daily_cycle_runs\latest.json"
if (-not (Test-Path $latestJson)) {
    Write-Host "  Not run yet." -ForegroundColor Yellow
} else {
    try {
        $content = Get-Content $latestJson -Raw -Encoding UTF8
        $report = $content | ConvertFrom-Json -ErrorAction Stop

        $statusColor = if ($report.status -eq "success") { "Green" } else { "Red" }
        Write-Host ("  Status:     " + $report.status) -ForegroundColor $statusColor
        Write-Host ("  Mode:       " + $report.mode) -ForegroundColor Gray
        Write-Host ("  Started:    " + $report.started_at) -ForegroundColor Gray
        Write-Host ("  Finished:   " + $report.finished_at) -ForegroundColor Gray
        Write-Host ("  Duration:   " + $report.duration_seconds + " seconds") -ForegroundColor Gray

        if ($report.PSObject.Properties.Name -contains "report_status") {
            Write-Host ("  Report:     " + $report.report_status) -ForegroundColor Gray
        }
        if ($report.PSObject.Properties.Name -contains "audio_status") {
            Write-Host ("  Audio:      " + $report.audio_status) -ForegroundColor Gray
        }
        if ($report.PSObject.Properties.Name -contains "fetch_due") {
            Write-Host ("  Fetch:      due=" + $report.fetch_due + " started=" + $report.fetch_started) -ForegroundColor Gray
        }
        if ($report.PSObject.Properties.Name -contains "summary_targets") {
            Write-Host ("  Summary:    targets=" + $report.summary_targets + " completed=" + $report.summary_completed) -ForegroundColor Gray
        }

        if ($report.errors -and $report.errors.Count -gt 0) {
            Write-Host ("  Errors:     " + $report.errors.Count) -ForegroundColor Yellow
        } else {
            Write-Host "  Errors:     None" -ForegroundColor Gray
        }
    } catch {
        Write-Host "  Report unreadable." -ForegroundColor Red
        Write-Host "  Check logs\daily_cycle.log for details." -ForegroundColor Gray
    }
}

Write-Host ""
