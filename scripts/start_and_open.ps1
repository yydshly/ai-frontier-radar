# start_and_open.ps1 - one-click: start the web service (if needed) and open the browser.
#
# Usage (normally launched by start_app.bat with double-click):
#   .\scripts\start_and_open.ps1
#
# Behavior:
#   - If the service is already responding, just open the browser.
#   - Otherwise start it (in its own minimized window, logs preserved), wait
#     until it is ready, then open the browser.
# ASCII-only console output (avoids GBK console encoding issues).

param(
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8765
)

$ErrorActionPreference = "Continue"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ScriptDir "..")).Path
$HomeUrl = "http://${BindHost}:${Port}"

function Test-WebReady {
    try {
        $resp = Invoke-WebRequest -Uri $HomeUrl -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
        return [int]$resp.StatusCode -ge 200
    } catch {
        return $false
    }
}

Write-Host "AI Frontier Radar - starter" -ForegroundColor Cyan
Write-Host "Web: $HomeUrl" -ForegroundColor Gray

if (Test-WebReady) {
    Write-Host "Service already running. Opening browser..." -ForegroundColor Green
    Start-Process $HomeUrl
    return
}

# Start the web service in its own (minimized) window so logs stay visible and
# this starter can return after opening the browser. uvicorn keeps running there.
$startScript = Join-Path $ProjectRoot "scripts\start_local.ps1"
if (-not (Test-Path $startScript)) {
    Write-Host "[ERROR] Not found: $startScript" -ForegroundColor Red
    return
}
Start-Process "powershell.exe" -ArgumentList @(
    "-NoExit", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$startScript`""
) -WindowStyle Minimized

Write-Host "Starting service, waiting until ready (up to ~40s)..." -ForegroundColor Yellow
$ready = $false
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Seconds 1
    if (Test-WebReady) { $ready = $true; break }
    Write-Host "." -NoNewline
}
Write-Host ""
if ($ready) {
    Write-Host "Ready. Opening browser." -ForegroundColor Green
} else {
    Write-Host "Timed out waiting; opening browser anyway (it may still be starting)." -ForegroundColor Yellow
}
Start-Process $HomeUrl
