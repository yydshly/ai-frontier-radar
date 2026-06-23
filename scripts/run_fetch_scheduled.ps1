# run_fetch_scheduled.ps1 - non-interactive FETCH-ONLY runner for Task Scheduler.
#
# Runs run_due_sources_once.py --apply: fetches due sources only (no finalize, no
# report, no LLM summary). Meant to run frequently (every few hours) so the
# current daily window accumulates fresh content BEFORE it is finalized by the
# once-daily run_daily_cycle task. See README "信息及时性：抓取节奏与报告窗口".
#
# Appends output to logs\fetch.log and exits with the runner's exit code.

$ErrorActionPreference = "Continue"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ProjectRoot "..")).Path
Set-Location $ProjectRoot

$LogsDir = Join-Path $ProjectRoot "logs"
if (-not (Test-Path $LogsDir)) { New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null }
$FetchLog = Join-Path $LogsDir "fetch.log"

$Mutex = New-Object System.Threading.Mutex($false, "Global\AIFrontierRadar.Fetch")
$PipelineMutex = New-Object System.Threading.Mutex($false, "Global\AIFrontierRadar.AutomationPipeline")
$HasMutex = $false
$HasPipelineMutex = $false
try {
    $HasMutex = $Mutex.WaitOne(0)
} catch [System.Threading.AbandonedMutexException] {
    $HasMutex = $true
}
if (-not $HasMutex) {
    "===== $(Get-Date -Format 'yyyy-MM-ddTHH:mm:ss') fetch skipped: another fetch runner is active =====" |
        Out-File -FilePath $FetchLog -Append -Encoding utf8
    $Mutex.Dispose()
    $PipelineMutex.Dispose()
    exit 0
}

try {
    $HasPipelineMutex = $PipelineMutex.WaitOne(0)
} catch [System.Threading.AbandonedMutexException] {
    $HasPipelineMutex = $true
}
if (-not $HasPipelineMutex) {
    "===== $(Get-Date -Format 'yyyy-MM-ddTHH:mm:ss') fetch skipped: daily cycle or another automation pipeline is active =====" |
        Out-File -FilePath $FetchLog -Append -Encoding utf8
    $Mutex.ReleaseMutex()
    $Mutex.Dispose()
    $PipelineMutex.Dispose()
    exit 0
}

try {
$PythonExe = Join-Path $ProjectRoot "python\python.exe"          # portable bundle
if (-not (Test-Path $PythonExe)) { $PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe" }  # dev venv
if (-not (Test-Path $PythonExe)) { $PythonExe = "python" }       # system PATH

$ScriptPath = Join-Path $ProjectRoot "scripts\run_due_sources_once.py"
$SyncScript = Join-Path $ProjectRoot "scripts\sync_sources_from_config.py"

# The two explicit safety gates required by run_due_sources_once.py --apply.
$env:RADAR_SCHEDULER_ENABLED = "true"
$env:AUTO_SUMMARY_MAX_PER_FETCH_RUN = "0"   # fetch only — never trigger LLM summaries
$env:PYTHONIOENCODING = "utf-8"

"" | Out-File -FilePath $FetchLog -Append -Encoding utf8
"===== $(Get-Date -Format 'yyyy-MM-ddTHH:mm:ss') fetch start (python=$PythonExe) =====" |
    Out-File -FilePath $FetchLog -Append -Encoding utf8

# A fresh/portable install may have an empty DB. Sync configured sources before
# due-source computation so the task never depends on visiting /sources first.
& $PythonExe -u $SyncScript --apply 2>&1 | Out-File -FilePath $FetchLog -Append -Encoding utf8
if ($LASTEXITCODE -ne 0) {
    "===== source sync failed (exit=$LASTEXITCODE) =====" |
        Out-File -FilePath $FetchLog -Append -Encoding utf8
    exit $LASTEXITCODE
}

& $PythonExe -u $ScriptPath --apply 2>&1 | Out-File -FilePath $FetchLog -Append -Encoding utf8
$exitCode = $LASTEXITCODE

"===== $(Get-Date -Format 'yyyy-MM-ddTHH:mm:ss') fetch end (exit=$exitCode) =====" |
    Out-File -FilePath $FetchLog -Append -Encoding utf8

exit $exitCode
} finally {
    if ($HasPipelineMutex) { $PipelineMutex.ReleaseMutex() }
    if ($HasMutex) { $Mutex.ReleaseMutex() }
    $PipelineMutex.Dispose()
    $Mutex.Dispose()
}
