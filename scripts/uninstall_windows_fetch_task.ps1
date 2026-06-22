# uninstall_windows_fetch_task.ps1 - remove the frequent fetch task.

param(
    [string]$TaskName = "AI Frontier Radar Fetch"
)

$ErrorActionPreference = "Stop"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "AI Frontier Radar - Uninstall Fetch Task" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -eq $task) {
    Write-Host "Task '$TaskName' is not installed." -ForegroundColor Gray
    return
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
Write-Host "[SUCCESS] Task '$TaskName' has been removed." -ForegroundColor Green
