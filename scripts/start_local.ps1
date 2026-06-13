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
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8992
)

$ErrorActionPreference = "Continue"
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

# ── Start uvicorn with transcript logging ───────────────────────────────────
$AppLog = Join-Path $ProjectRoot "logs\app.log"
Write-Host ""
Write-Host "Starting FastAPI server..." -ForegroundColor Green
Write-Host "  Web address:  http://${BindHost}:${Port}" -ForegroundColor Cyan
Write-Host "  App log:     $AppLog" -ForegroundColor Gray
Write-Host ""
Write-Host "------------------------------------------------------------" -ForegroundColor DarkGray
Write-Host "Press Ctrl+C to stop the server." -ForegroundColor Gray
Write-Host ""

# Use Start-Transcript to log all console output to app.log (reliable on PS 5.1).
# Start-Transcript handles external command streams correctly where Tee-Object fails.
try {
    Start-Transcript -Path $AppLog -Append -ErrorAction Stop | Out-Null
} catch {
    # Fallback: create new file if transcript fails
    try { Start-Transcript -Path $AppLog -ErrorAction Stop | Out-Null } catch {
        Write-Host "[WARN] Could not start transcript logging: $_" -ForegroundColor Yellow
    }
}

& $PythonExe -m uvicorn app.main:app --host $BindHost --port $Port

# Stop transcript when uvicorn exits (e.g., Ctrl+C)
try { Stop-Transcript -ErrorAction SilentlyContinue } catch {}
