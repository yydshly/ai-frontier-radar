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

$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) { $PythonExe = "python" }

$ScriptPath = Join-Path $ProjectRoot "scripts\run_daily_cycle.py"

"" | Out-File -FilePath $DailyLog -Append -Encoding utf8
"===== $(Get-Date -Format 'yyyy-MM-ddTHH:mm:ss') daily cycle start (python=$PythonExe) =====" |
    Out-File -FilePath $DailyLog -Append -Encoding utf8

# -u for unbuffered output. Force UTF-8 so Chinese is readable and the file
# isn't a mix of UTF-16 (PS '*>>' default) and the UTF-8 markers above.
$env:PYTHONIOENCODING = "utf-8"
& $PythonExe -u $ScriptPath --apply 2>&1 | Out-File -FilePath $DailyLog -Append -Encoding utf8
$exitCode = $LASTEXITCODE

"===== $(Get-Date -Format 'yyyy-MM-ddTHH:mm:ss') daily cycle end (exit=$exitCode) =====" |
    Out-File -FilePath $DailyLog -Append -Encoding utf8

exit $exitCode
