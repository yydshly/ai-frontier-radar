# run_daily_cycle_once.ps1 - User-friendly wrapper around run_daily_cycle.py.
#
# Used by the launcher GUI's "Run Daily Cycle Once" button. Provides
# immediate console feedback and uses unbuffered Python (-u) so the user
# sees real-time progress in the new window.

$ErrorActionPreference = "Continue"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ProjectRoot "..")).Path
Set-Location $ProjectRoot

$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    Write-Host "[INFO] .venv not found, using python from PATH." -ForegroundColor Yellow
    $PythonExe = "python"
}

$ScriptPath = Join-Path $ProjectRoot "scripts\run_daily_cycle.py"
$LiveLog = Join-Path $ProjectRoot "logs\daily_cycle.live.log"
$LatestJson = Join-Path $ProjectRoot "runtime\daily_cycle_runs\latest.json"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "AI Frontier Radar - Run Daily Cycle Once" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host ("Project root: " + $ProjectRoot) -ForegroundColor Gray
Write-Host ("Python:      " + $PythonExe) -ForegroundColor Gray
Write-Host ("Command:     " + $PythonExe + " -u " + $ScriptPath + " --apply") -ForegroundColor Gray
Write-Host ""
Write-Host "Do not close this window while the daily cycle is running." -ForegroundColor Yellow
Write-Host "It may take several minutes." -ForegroundColor Yellow
Write-Host ""
Write-Host ("Live log:    " + $LiveLog) -ForegroundColor DarkGray
Write-Host ("Report:      " + $LatestJson) -ForegroundColor DarkGray
Write-Host ""

# Ensure log dir exists
$LogsDir = Join-Path $ProjectRoot "logs"
if (-not (Test-Path $LogsDir)) {
    New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null
}

# Run with -u for unbuffered output.
& $PythonExe -u $ScriptPath --apply
$ExitCode = $LASTEXITCODE

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ("Daily cycle finished. Exit code: " + $ExitCode) -ForegroundColor $(if ($ExitCode -eq 0) { "Green" } else { "Red" })
Write-Host ("Check: " + $LiveLog) -ForegroundColor Gray
Write-Host ("Check: " + $LatestJson) -ForegroundColor Gray
Write-Host ""
Write-Host "Press any key to close this window..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
