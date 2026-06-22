# run_fetch_once.ps1 - user-friendly one-time fetch-only run.

$ErrorActionPreference = "Continue"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ProjectRoot "..")).Path
Set-Location $ProjectRoot

$BundledPython = Join-Path $ProjectRoot "python\python.exe"
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$PythonExe = if (Test-Path $BundledPython) { $BundledPython }
             elseif (Test-Path $VenvPython) { $VenvPython }
             else { "python" }

$env:RADAR_SCHEDULER_ENABLED = "true"
$env:AUTO_SUMMARY_MAX_PER_FETCH_RUN = "0"
$env:PYTHONIOENCODING = "utf-8"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "AI Frontier Radar - Fetch Sources Once" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "This fetches due sources only. It does not generate or send a report." -ForegroundColor Gray

& $PythonExe -u (Join-Path $ProjectRoot "scripts\sync_sources_from_config.py") --apply
if ($LASTEXITCODE -eq 0) {
    & $PythonExe -u (Join-Path $ProjectRoot "scripts\run_due_sources_once.py") --apply --show-skipped --show-running
}
$exitCode = $LASTEXITCODE

Write-Host ""
Write-Host "Fetch finished. Exit code: $exitCode" -ForegroundColor $(if ($exitCode -eq 0) { "Green" } else { "Red" })
Write-Host "Press any key to close..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
exit $exitCode
