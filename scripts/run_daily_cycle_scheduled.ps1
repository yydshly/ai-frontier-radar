# run_daily_cycle_scheduled.ps1 - non-interactive daily-cycle runner for Task Scheduler.
#
# Unlike run_daily_cycle_once.ps1 (which is interactive and waits for a keypress),
# this runs headless: it appends all output to logs\daily_cycle.log and exits with
# the cycle's exit code. Designed to be the action of the scheduled task.
# ASCII-only log markers (avoids GBK console encoding issues).

$ErrorActionPreference = "Continue"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ProjectRoot "..")).Path
Set-Location $ProjectRoot

$LogsDir = Join-Path $ProjectRoot "logs"
if (-not (Test-Path $LogsDir)) { New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null }
$DailyLog = Join-Path $LogsDir "daily_cycle.log"

$Mutex = New-Object System.Threading.Mutex($false, "Global\AIFrontierRadar.DailyCycle")
$PipelineMutex = New-Object System.Threading.Mutex($false, "Global\AIFrontierRadar.AutomationPipeline")
$HasMutex = $false
$HasPipelineMutex = $false
try {
    $HasMutex = $Mutex.WaitOne(0)
} catch [System.Threading.AbandonedMutexException] {
    $HasMutex = $true
}
if (-not $HasMutex) {
    "===== $(Get-Date -Format 'yyyy-MM-ddTHH:mm:ss') daily cycle skipped: another daily runner is active =====" |
        Out-File -FilePath $DailyLog -Append -Encoding utf8
    $Mutex.Dispose()
    $PipelineMutex.Dispose()
    exit 0
}

# The daily cycle includes its own fetch stage. If a frequent fetch is already
# finishing, wait for it instead of running two source fetches concurrently.
try {
    $HasPipelineMutex = $PipelineMutex.WaitOne([TimeSpan]::FromMinutes(30))
} catch [System.Threading.AbandonedMutexException] {
    $HasPipelineMutex = $true
}
if (-not $HasPipelineMutex) {
    "===== $(Get-Date -Format 'yyyy-MM-ddTHH:mm:ss') daily cycle failed: automation pipeline stayed busy for 30 minutes =====" |
        Out-File -FilePath $DailyLog -Append -Encoding utf8
    $Mutex.ReleaseMutex()
    $Mutex.Dispose()
    $PipelineMutex.Dispose()
    exit 1
}

try {
$PythonExe = Join-Path $ProjectRoot "python\python.exe"          # portable bundle
if (-not (Test-Path $PythonExe)) { $PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe" }  # dev venv
if (-not (Test-Path $PythonExe)) { $PythonExe = "python" }       # system PATH

$ScriptPath = Join-Path $ProjectRoot "scripts\run_daily_cycle.py"
$SyncScript = Join-Path $ProjectRoot "scripts\sync_sources_from_config.py"

"" | Out-File -FilePath $DailyLog -Append -Encoding utf8
"===== $(Get-Date -Format 'yyyy-MM-ddTHH:mm:ss') daily cycle start (python=$PythonExe) =====" |
    Out-File -FilePath $DailyLog -Append -Encoding utf8

# -u for unbuffered output. Force UTF-8 so Chinese is readable and the file
# isn't a mix of UTF-16 (PS '*>>' default) and the UTF-8 markers above.
$env:PYTHONIOENCODING = "utf-8"
& $PythonExe -u $SyncScript --apply 2>&1 | Out-File -FilePath $DailyLog -Append -Encoding utf8
if ($LASTEXITCODE -ne 0) {
    "===== source sync failed (exit=$LASTEXITCODE) =====" |
        Out-File -FilePath $DailyLog -Append -Encoding utf8
    exit $LASTEXITCODE
}
& $PythonExe -u $ScriptPath --apply 2>&1 | Out-File -FilePath $DailyLog -Append -Encoding utf8
$exitCode = $LASTEXITCODE

"===== $(Get-Date -Format 'yyyy-MM-ddTHH:mm:ss') daily cycle end (exit=$exitCode) =====" |
    Out-File -FilePath $DailyLog -Append -Encoding utf8

exit $exitCode
} finally {
    if ($HasPipelineMutex) { $PipelineMutex.ReleaseMutex() }
    if ($HasMutex) { $Mutex.ReleaseMutex() }
    $PipelineMutex.Dispose()
    $Mutex.Dispose()
}
