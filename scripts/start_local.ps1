# start_local.ps1 — Start the FastAPI Web service for AI Frontier Radar.
#
# Usage:
#   .\scripts\start_local.ps1
#
# What it does:
# - Checks prerequisites (.env, config/sources.yaml)
# - Creates logs/, runtime/, data/ directories if absent
# - Starts uvicorn on 127.0.0.1:8000 with stdout/stderr visible and written to logs/app.log

param(
    [string]$Host = "127.0.0.1",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ProjectRoot "..")).Path

Set-Location $ProjectRoot
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "AI Frontier Radar — Local Start" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Project root: $ProjectRoot" -ForegroundColor Gray

# ── Directory setup ──────────────────────────────────────────────────────────
$dirs = @("logs", "runtime", "data")
foreach ($dir in $dirs) {
    $path = Join-Path $ProjectRoot $dir
    if (-not (Test-Path $path)) {
        New-Item -ItemType Directory -Force -Path $path | Out-Null
        Write-Host "[CREATED] $path" -ForegroundColor Yellow
    }
}

# ── Python selection ────────────────────────────────────────────────────────
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    Write-Host "[INFO] .venv not found at $PythonExe" -ForegroundColor Yellow
    Write-Host "[INFO] Falling back to python from PATH" -ForegroundColor Yellow
    $PythonExe = "python"
}
Write-Host "Python: $PythonExe" -ForegroundColor Gray

# ── Prerequisites check ─────────────────────────────────────────────────────
$EnvFile = Join-Path $ProjectRoot ".env"
if (-not (Test-Path $EnvFile)) {
    Write-Host "[WARN] .env not found at $EnvFile" -ForegroundColor Yellow
    Write-Host "[WARN] Please create .env with your API keys before running." -ForegroundColor Yellow
}

$SourcesYaml = Join-Path $ProjectRoot "config\sources.yaml"
if (-not (Test-Path $SourcesYaml)) {
    Write-Host "[WARN] config/sources.yaml not found at $SourcesYaml" -ForegroundColor Yellow
    Write-Host "[WARN] Source configuration is missing. Copy config/sources.yaml.example if available." -ForegroundColor Yellow
}

# ── Start uvicorn ───────────────────────────────────────────────────────────
$AppLog = Join-Path $ProjectRoot "logs\app.log"
Write-Host ""
Write-Host "Starting FastAPI server..." -ForegroundColor Green
Write-Host "  Web address:  http://${Host}:${Port}" -ForegroundColor Cyan
Write-Host "  App log:     $AppLog" -ForegroundColor Gray
Write-Host ""
Write-Host "------------------------------------------------------------" -ForegroundColor DarkGray
Write-Host "Press Ctrl+C to stop the server." -ForegroundColor Gray
Write-Host ""

# Tee stdout+stderr to console AND append to app.log
& $PythonExe -m uvicorn app.main:app --host $Host --port $Port 2>&1 | Tee-Object -FilePath $AppLog -Append
