# uninstall_windows_daily_task.ps1 — Remove the AI Frontier Radar Daily Cycle task.
#
# Usage:
#   .\scripts\uninstall_windows_daily_task.ps1

param(
    [string]$TaskName = "AI Frontier Radar Daily Cycle"
)

$ErrorActionPreference = "Stop"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "AI Frontier Radar — Uninstall Daily Task" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

try {
    $existing = schtasks /Query /TN $TaskName /FO LIST 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Task '$TaskName' does not exist. Nothing to remove." -ForegroundColor Gray
        return
    }

    Write-Host "[INFO] Found task: $TaskName" -ForegroundColor Gray
    Write-Host "[INFO] Deleting task..." -ForegroundColor Yellow

    schtasks /Delete /TN $TaskName /F 2>$null

    if ($LASTEXITCODE -eq 0) {
        Write-Host "[SUCCESS] Task '$TaskName' has been removed." -ForegroundColor Green
    } else {
        Write-Host "[ERROR] Failed to delete task. Exit code: $LASTEXITCODE" -ForegroundColor Red
        throw "schtasks /Delete failed"
    }

} catch {
    Write-Host "[ERROR] $_" -ForegroundColor Red
    throw
}

Write-Host ""
