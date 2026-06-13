# stop_local.ps1 - Stop the FastAPI Web service running on port 8765.
#
# Usage:
#   .\scripts\stop_local.ps1
#
# This script only stops the Web service on port 8765.
# It does not stop Daily Cycle jobs or Windows scheduled tasks.

$ErrorActionPreference = "Continue"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "AI Frontier Radar - Stop Web Service" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

$Port = 8765

function Get-ListeningProcessIdsOnPort {
    param([int]$Port)

    $processIds = @()

    try {
        $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        if ($connections) {
            foreach ($conn in $connections) {
                if ($conn.OwningProcess) {
                    $processIds += [int]$conn.OwningProcess
                }
            }
        }
    } catch {
        Write-Host "[INFO] Get-NetTCPConnection failed, will try netstat." -ForegroundColor Yellow
    }

    # Always fallback to netstat if Get-NetTCPConnection found nothing.
    if (-not $processIds -or $processIds.Count -eq 0) {
        try {
            $lines = netstat -ano | Select-String ":$Port" | Select-String "LISTENING"
            foreach ($line in $lines) {
                $parts = ($line.ToString() -split "\s+") | Where-Object { $_ -ne "" }
                if ($parts.Count -gt 0) {
                    $maybePid = $parts[-1]
                    if ($maybePid -match "^\d+$") {
                        $processIds += [int]$maybePid
                    }
                }
            }
        } catch {
            Write-Host "[WARN] netstat fallback failed: $_" -ForegroundColor Yellow
        }
    }

    return $processIds | Sort-Object -Unique
}

$ProcessIds = Get-ListeningProcessIdsOnPort -Port $Port

if (-not $ProcessIds -or $ProcessIds.Count -eq 0) {
    Write-Host "No process is listening on port ${Port}." -ForegroundColor Gray
    Write-Host "Web service is not running." -ForegroundColor Gray
    Write-Host ""
    exit 0
}

foreach ($procId in $ProcessIds) {
    try {
        $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
        $procName = if ($proc) { $proc.ProcessName } else { "Unknown" }
        Write-Host "Found process on port ${Port}:" -ForegroundColor Gray
        Write-Host "  PID:    $procId" -ForegroundColor Gray
        Write-Host "  Name:   $procName" -ForegroundColor Gray
        Stop-Process -Id $procId -Force -ErrorAction Stop
        Write-Host "[STOPPED] PID $procId ($procName)" -ForegroundColor Green
    } catch {
        Write-Host "[ERROR] Failed to stop PID ${procId} : $_" -ForegroundColor Red
    }
}

# Re-verify the port is free.
Start-Sleep -Seconds 1
$Remaining = Get-ListeningProcessIdsOnPort -Port $Port
if ($Remaining -and $Remaining.Count -gt 0) {
    Write-Host "[WARN] Port ${Port} is still occupied by PID(s): $($Remaining -join ', ')" -ForegroundColor Yellow
} else {
    Write-Host "[OK] Web service stopped, port ${Port} is free." -ForegroundColor Green
}

Write-Host ""
