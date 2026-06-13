# stop_local.ps1 — Stop the FastAPI Web service running on port 8000.
#
# Usage:
#   .\scripts\stop_local.ps1

$ErrorActionPreference = "Stop"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "AI Frontier Radar — Stop Web Service" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

$Port = 8000

# Find processes listening on port 8000
try {
    $Connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
} catch {
    # Fallback to netstat if PowerShell netstat module unavailable
    Write-Host "[INFO] Get-NetTCPConnection not available, falling back to netstat..." -ForegroundColor Yellow
    $Output = netstat -ano | findstr ":${Port}"
    if ($Output -match "\s+(\d+)\s*$") {
        $Connections = @([PSCustomObject]@{OwningProcess = [int]$matches[1]})
    } else {
        $Connections = @()
    }
}

if ($Connections -and $Connections.Count -gt 0) {
    foreach ($conn in $Connections) {
        $PID = $conn.OwningProcess
        try {
            $Process = Get-Process -Id $PID -ErrorAction SilentlyContinue
            $ProcessName = if ($Process) { $Process.ProcessName } else { "Unknown" }
            Write-Host "Found process on port ${Port}:" -ForegroundColor Gray
            Write-Host "  PID:    $PID" -ForegroundColor Gray
            Write-Host "  Name:   $ProcessName" -ForegroundColor Gray
            Stop-Process -Id $PID -Force -ErrorAction Stop
            Write-Host "[STOPPED] PID $PID ($ProcessName)" -ForegroundColor Green
        } catch {
            Write-Host "[ERROR] Failed to stop PID $PID : $_" -ForegroundColor Red
        }
    }
} else {
    Write-Host "No process is listening on port ${Port}." -ForegroundColor Gray
    Write-Host "Web service is not running." -ForegroundColor Gray
}

Write-Host ""
