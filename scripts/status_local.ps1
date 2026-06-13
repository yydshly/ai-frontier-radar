# status_local.ps1 — Show local run status for AI Frontier Radar.
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
    [int]$WebPort = 8000
)

$ErrorActionPreference = "Continue"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ProjectRoot "..")).Path
Set-Location $ProjectRoot

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "AI Frontier Radar Local Status" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ── Project root ─────────────────────────────────────────────────────────────
Write-Host "项目目录：" -ForegroundColor White
Write-Host "  $ProjectRoot" -ForegroundColor Gray
Write-Host ""

# ── Web service status ───────────────────────────────────────────────────────
Write-Host "Web 服务：" -ForegroundColor White

$webAddress = "http://127.0.0.1:${WebPort}"
Write-Host "  地址: $webAddress" -ForegroundColor Gray

try {
    $Connections = Get-NetTCPConnection -LocalPort $WebPort -State Listen -ErrorAction SilentlyContinue
} catch {
    $Connections = @()
}

if ($Connections -and $Connections.Count -gt 0) {
    $PID = $Connections[0].OwningProcess
    $Process = Get-Process -Id $PID -ErrorAction SilentlyContinue
    $ProcessName = if ($Process) { $Process.ProcessName } else { "Unknown" }
    Write-Host "  状态: 运行中" -ForegroundColor Green
    Write-Host "  PID:  $PID ($ProcessName)" -ForegroundColor Gray
} else {
    Write-Host "  状态: 未运行" -ForegroundColor Yellow
}
Write-Host ""

# ── Windows scheduled task status ─────────────────────────────────────────────
Write-Host "Windows 定时任务：" -ForegroundColor White
Write-Host "  任务名: $TaskName" -ForegroundColor Gray

try {
    $taskInfo = schtasks /Query /TN $TaskName /FO LIST 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  状态: 已安装" -ForegroundColor Green
        # Parse "Next Run Time" and "Last Run Time" from output
        foreach ($line in $taskInfo) {
            if ($line -match "Next Run Time:\s*(.+)") { Write-Host "  下次运行: $($matches[1].Trim())" -ForegroundColor Gray }
            if ($line -match "Last Run Time:\s*(.+)") { Write-Host "  上次运行: $($matches[1].Trim())" -ForegroundColor Gray }
            if ($line -match "Last Result:\s*(.+)") { Write-Host "  上次结果: $($matches[1].Trim())" -ForegroundColor Gray }
        }
    } else {
        Write-Host "  状态: 未安装" -ForegroundColor Yellow
    }
} catch {
    Write-Host "  状态: 未安装" -ForegroundColor Yellow
}
Write-Host ""

# ── Key directories ──────────────────────────────────────────────────────────
Write-Host "关键目录：" -ForegroundColor White

$checks = @{
    "配置文件"          = Join-Path $ProjectRoot ".env"
    "来源配置"          = Join-Path $ProjectRoot "config\sources.yaml"
    "数据目录"          = Join-Path $ProjectRoot "data"
    "运行产物目录"      = Join-Path $ProjectRoot "runtime"
    "日志目录"          = Join-Path $ProjectRoot "logs"
    "Web 日志"          = Join-Path $ProjectRoot "logs\app.log"
    "每日任务日志"      = Join-Path $ProjectRoot "logs\daily_cycle.log"
    "最近执行报告"      = Join-Path $ProjectRoot "runtime\daily_cycle_runs\latest.json"
}

foreach ($label in $checks.Keys) {
    $path = $checks[$label]
    if (Test-Path $path) {
        Write-Host "  [存在] $label" -ForegroundColor Green
        Write-Host "          $path" -ForegroundColor DarkGray
    } else {
        Write-Host "  [缺失] $label" -ForegroundColor Yellow
        Write-Host "          $path" -ForegroundColor DarkGray
    }
}
Write-Host ""

# ── Latest daily cycle run ───────────────────────────────────────────────────
Write-Host "最近每日任务：" -ForegroundColor White

$latestJson = Join-Path $ProjectRoot "runtime\daily_cycle_runs\latest.json"
if (-not (Test-Path $latestJson)) {
    Write-Host "  尚未执行每日任务。" -ForegroundColor Yellow
} else {
    try {
        $content = Get-Content $latestJson -Raw -Encoding UTF8
        $report = $content | ConvertFrom-Json -ErrorAction Stop

        Write-Host "  状态:    $($report.status)" -ForegroundColor $(if ($report.status -eq "success") { "Green" } else { "Red" })
        Write-Host "  模式:    $($report.mode)" -ForegroundColor Gray
        Write-Host "  开始时间: $($report.started_at)" -ForegroundColor Gray
        Write-Host "  结束时间: $($report.finished_at)" -ForegroundColor Gray
        Write-Host "  耗时:    $($report.duration_seconds) 秒" -ForegroundColor Gray

        if ($report.PSObject.Properties.Name -contains "report_status") {
            Write-Host "  日报状态: $($report.report_status)" -ForegroundColor Gray
        }
        if ($report.PSObject.Properties.Name -contains "audio_status") {
            Write-Host "  音频状态: $($report.audio_status)" -ForegroundColor Gray
        }
        if ($report.PSObject.Properties.Name -contains "fetch_due") {
            Write-Host "  来源同步: due=$($report.fetch_due) started=$($report.fetch_started)" -ForegroundColor Gray
        }
        if ($report.PSObject.Properties.Name -contains "summary_targets") {
            Write-Host "  中文摘要: targets=$($report.summary_targets) completed=$($report.summary_completed)" -ForegroundColor Gray
        }

        if ($report.errors -and $report.errors.Count -gt 0) {
            Write-Host "  错误数:  $($report.errors.Count)" -ForegroundColor Yellow
        } else {
            Write-Host "  错误:    无" -ForegroundColor Gray
        }
    } catch {
        Write-Host "  最近执行报告无法读取。" -ForegroundColor Red
        Write-Host "  请查看 logs\daily_cycle.log 获取详情。" -ForegroundColor Gray
    }
}

Write-Host ""
