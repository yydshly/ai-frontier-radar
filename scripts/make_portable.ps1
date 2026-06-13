# make_portable.ps1 - Build a self-contained PORTABLE folder of AI Frontier Radar.
#
# Produces dist\AIFrontierRadar\ containing:
#   - python\         an embeddable CPython (matching this project's 3.10) with
#                     all requirements pip-installed. No system Python needed on
#                     the target machine.
#   - app\ scripts\ config\ data\   the application + (optionally) current data.
#   - .env.example    placeholder config WITHOUT any API key (see -IncludeEnv).
#   - start_app.bat / control_panel.bat   double-click entry points.
#   - README_PORTABLE.txt   setup instructions for the recipient.
#
# The whole folder can be zipped, copied to another Windows x64 machine, and run
# by double-clicking start_app.bat (after the recipient fills in .env).
#
# Usage:
#   .\scripts\make_portable.ps1                 # default: bundle data, no .env key
#   .\scripts\make_portable.ps1 -Zip            # also produce a .zip
#   .\scripts\make_portable.ps1 -NoData         # ship an empty DB (fresh start)
#   .\scripts\make_portable.ps1 -IncludeEnv     # bundle the REAL .env (self-use only!)
#
# ASCII-only console output (avoids GBK console encoding issues on zh-CN Windows).

param(
    [string]$PythonVersion = "3.10.11",
    [string]$OutputName = "AIFrontierRadar",
    [switch]$NoData,        # omit data\ (ship a fresh, empty install)
    [switch]$IncludeEnv,    # bundle the real .env WITH secrets (self-use backups only)
    [switch]$Zip            # also produce dist\<OutputName>.zip
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ScriptDir "..")).Path
Set-Location $ProjectRoot

$DistDir  = Join-Path $ProjectRoot "dist"
$CacheDir = Join-Path $DistDir "_cache"
$OutDir   = Join-Path $DistDir $OutputName
$PyDir    = Join-Path $OutDir "python"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "AI Frontier Radar - Build portable folder" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "Project root : $ProjectRoot" -ForegroundColor Gray
Write-Host "Output       : $OutDir" -ForegroundColor Gray
Write-Host "Python embed : $PythonVersion (win amd64)" -ForegroundColor Gray
Write-Host "Include data : $(if ($NoData) { 'no (fresh)' } else { 'yes' })" -ForegroundColor Gray
Write-Host "Include .env : $(if ($IncludeEnv) { 'REAL .env (secrets!)' } else { 'no (.env.example only)' })" -ForegroundColor Gray
Write-Host ""

# Warn if the local service is running (DB files may be locked / mid-write).
try {
    $resp = Invoke-WebRequest -Uri "http://127.0.0.1:8765" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
    if ([int]$resp.StatusCode -ge 200) {
        Write-Host "[WARN] The local service appears to be RUNNING on :8765." -ForegroundColor Yellow
        Write-Host "       Stop it first (scripts\stop_local.ps1) so the database copy is clean." -ForegroundColor Yellow
        Write-Host ""
    }
} catch { }

# --- Clean output, keep cache ------------------------------------------------
New-Item -ItemType Directory -Force -Path $CacheDir | Out-Null
if (Test-Path $OutDir) {
    Write-Host "Removing previous $OutDir ..." -ForegroundColor Gray
    Remove-Item -Recurse -Force $OutDir
}
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

# --- 1. Embeddable Python ----------------------------------------------------
$EmbedName = "python-$PythonVersion-embed-amd64.zip"
$EmbedZip  = Join-Path $CacheDir $EmbedName
$EmbedUrl  = "https://www.python.org/ftp/python/$PythonVersion/$EmbedName"
if (-not (Test-Path $EmbedZip)) {
    Write-Host "[1/5] Downloading $EmbedName ..." -ForegroundColor Green
    Invoke-WebRequest -Uri $EmbedUrl -OutFile $EmbedZip -UseBasicParsing
} else {
    Write-Host "[1/5] Using cached $EmbedName" -ForegroundColor Green
}
Write-Host "      Extracting embeddable Python -> python\" -ForegroundColor Gray
Expand-Archive -Path $EmbedZip -DestinationPath $PyDir -Force

# Enable site-packages + import site in the ._pth so pip-installed packages load.
$pthMajorMinor = ($PythonVersion -split '\.')[0,1] -join ''
$pthFile = Join-Path $PyDir "python$pthMajorMinor._pth"
if (-not (Test-Path $pthFile)) { throw "Embeddable _pth not found: $pthFile" }
# ".." = the folder ABOVE python\ (i.e. the app root), so `import app` resolves
# regardless of the process working directory. _pth paths are relative to
# python.exe's directory; without this, embeddable Python ignores cwd and the
# app package is not importable.
@(
    "python$pthMajorMinor.zip",
    ".",
    "..",
    "Lib\site-packages",
    "import site"
) | Set-Content -Path $pthFile -Encoding ASCII
Write-Host "      Patched $($pthFile | Split-Path -Leaf) (app root + site-packages + import site)" -ForegroundColor Gray

$PyExe = Join-Path $PyDir "python.exe"

# --- 2. Bootstrap pip into the embeddable Python -----------------------------
$GetPip = Join-Path $CacheDir "get-pip.py"
if (-not (Test-Path $GetPip)) {
    Write-Host "[2/5] Downloading get-pip.py ..." -ForegroundColor Green
    Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $GetPip -UseBasicParsing
} else {
    Write-Host "[2/5] Using cached get-pip.py" -ForegroundColor Green
}
Write-Host "      Installing pip into embeddable Python ..." -ForegroundColor Gray
& $PyExe $GetPip --no-warn-script-location
if ($LASTEXITCODE -ne 0) { throw "get-pip.py failed (exit $LASTEXITCODE)" }

# --- 3. Install project requirements -----------------------------------------
$Req = Join-Path $ProjectRoot "requirements.txt"
Write-Host "[3/5] Installing requirements (this can take a few minutes) ..." -ForegroundColor Green
& $PyExe -m pip install --no-warn-script-location --no-cache-dir -r $Req
if ($LASTEXITCODE -ne 0) { throw "pip install -r requirements.txt failed (exit $LASTEXITCODE)" }

# Repair sdist-only modules that build to an EMPTY wheel under embeddable Python.
# feedparser needs the top-level `sgmllib` module (shipped by sgmllib3k, which is
# sdist-only on PyPI); its sdist build drops the .py file under the embeddable
# interpreter, leaving only dist-info. Backfill it from the dev venv (this build
# machine has a working copy).
$portableSP = Join-Path $PyDir "Lib\site-packages"
$sgmllibDst = Join-Path $portableSP "sgmllib.py"
if (-not (Test-Path $sgmllibDst)) {
    $sgmllibSrc = Join-Path $ProjectRoot ".venv\Lib\site-packages\sgmllib.py"
    if (Test-Path $sgmllibSrc) {
        Copy-Item $sgmllibSrc $sgmllibDst -Force
        Write-Host "      Repaired missing sgmllib.py (copied from .venv)" -ForegroundColor Yellow
    } else {
        Write-Host "[WARN] sgmllib.py missing and no .venv copy found - feedparser may fail." -ForegroundColor Red
    }
}

# Smoke-test the bundled interpreter so a broken bundle can never ship silently.
Write-Host "      Verifying bundled imports ..." -ForegroundColor Gray
& $PyExe -c "import feedparser, trafilatura, lxml, sqlalchemy, uvicorn, fastapi, httpx, pydantic, yaml; print('bundled imports OK')"
if ($LASTEXITCODE -ne 0) { throw "Bundled-import smoke test failed (exit $LASTEXITCODE)" }

# --- 4. Copy application payload ---------------------------------------------
Write-Host "[4/5] Copying application files ..." -ForegroundColor Green

function Copy-Tree($name, [string[]]$excludeDirs = @(), [string[]]$excludeFiles = @()) {
    $src = Join-Path $ProjectRoot $name
    if (-not (Test-Path $src)) { Write-Host "      (skip $name - not found)" -ForegroundColor DarkGray; return }
    $dst = Join-Path $OutDir $name
    $xd = @("__pycache__") + $excludeDirs | ForEach-Object { Join-Path $src $_ }
    $xf = @("*.pyc") + $excludeFiles
    $args = @($src, $dst, "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/NP", "/R:1", "/W:1")
    if ($xd.Count) { $args += "/XD"; $args += $xd }
    if ($xf.Count) { $args += "/XF"; $args += $xf }
    robocopy @args | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy $name failed (exit $LASTEXITCODE)" }
    Write-Host "      + $name\" -ForegroundColor Gray
}

Copy-Tree "app"
Copy-Tree "scripts"
Copy-Tree "config"
if (-not $NoData) {
    # Bundle current data (db + reports + audio) but not local backups.
    Copy-Tree "data" -excludeDirs @("backups")
    Write-Host "      (bundled current data\; excluded data\backups\)" -ForegroundColor DarkGray
} else {
    New-Item -ItemType Directory -Force -Path (Join-Path $OutDir "data") | Out-Null
    Write-Host "      (empty data\ - fresh start)" -ForegroundColor DarkGray
}

# Empty runtime dirs the app/scheduler expect.
New-Item -ItemType Directory -Force -Path (Join-Path $OutDir "logs") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $OutDir "runtime\daily_cycle_runs") | Out-Null

# Loose files.
Copy-Item (Join-Path $ProjectRoot "requirements.txt") $OutDir -Force
foreach ($bat in @("start_app.bat", "control_panel.bat")) {
    $p = Join-Path $ProjectRoot $bat
    if (Test-Path $p) { Copy-Item $p $OutDir -Force }
}

# Config: always ship .env.example. Optionally the real .env (self-use only).
Copy-Item (Join-Path $ProjectRoot ".env.example") $OutDir -Force
if ($IncludeEnv) {
    $realEnv = Join-Path $ProjectRoot ".env"
    if (Test-Path $realEnv) {
        Copy-Item $realEnv $OutDir -Force
        Write-Host "      + .env (REAL secrets bundled - do NOT redistribute)" -ForegroundColor Yellow
    } else {
        Write-Host "      (no .env to bundle)" -ForegroundColor DarkGray
    }
}

# Verify the bundled Python can import the copied app from the output root
# (proves the _pth ".." entry resolves the app package).
Write-Host "      Verifying 'import app.main' from output root ..." -ForegroundColor Gray
Push-Location $OutDir
& $PyExe -c "import app.main; print('app import OK')"
$appImportExit = $LASTEXITCODE
Pop-Location
if ($appImportExit -ne 0) { throw "Bundled 'import app.main' failed (exit $appImportExit) - check python\$('python'+$pthMajorMinor)._pth" }

# --- 5. README ---------------------------------------------------------------
Write-Host "[5/5] Writing README_PORTABLE.txt ..." -ForegroundColor Green
$readme = @"
AI Frontier Radar - Portable
============================================================

This folder is self-contained: it includes its own Python runtime under
python\, so you do NOT need to install Python.

Requirements: 64-bit Windows 10/11.

------------------------------------------------------------
First-time setup
------------------------------------------------------------
1. Copy ".env.example" to ".env" (same folder).
2. Open ".env" in a text editor and fill in your API key:
       MINIMAX_API_KEY=your-real-key-here
   (Leave the other values as-is unless you know you need to change them.)

------------------------------------------------------------
Start the app
------------------------------------------------------------
- Double-click  start_app.bat
  Starts the web service and opens http://127.0.0.1:8765 in your browser.

- Double-click  control_panel.bat
  A small control window: start / stop / status / run the daily cycle.

------------------------------------------------------------
Daily auto-report (optional but recommended)
------------------------------------------------------------
To have the report build itself every morning (and catch up if the PC was
off), open PowerShell IN THIS FOLDER and run:

    powershell -ExecutionPolicy Bypass -File scripts\install_windows_daily_task.ps1

Logs go to logs\daily_cycle.log. Remove the task later with:

    powershell -ExecutionPolicy Bypass -File scripts\uninstall_windows_daily_task.ps1

------------------------------------------------------------
Notes
------------------------------------------------------------
- Your data lives in data\. Back up that folder to keep your articles/reports.
- This build targets Windows x64 + Python $PythonVersion. Do not mix the
  python\ folder with a different OS/architecture.
"@
$readme | Set-Content -Path (Join-Path $OutDir "README_PORTABLE.txt") -Encoding UTF8

# --- Optional zip ------------------------------------------------------------
if ($Zip) {
    $zipPath = Join-Path $DistDir "$OutputName.zip"
    if (Test-Path $zipPath) { Remove-Item -Force $zipPath }
    Write-Host "Compressing -> $zipPath ..." -ForegroundColor Green
    Compress-Archive -Path $OutDir -DestinationPath $zipPath
}

# --- Summary -----------------------------------------------------------------
$sizeMB = [math]::Round((Get-ChildItem -Recurse $OutDir | Measure-Object -Property Length -Sum).Sum / 1MB, 1)
Write-Host ""
Write-Host "[SUCCESS] Portable build complete." -ForegroundColor Green
Write-Host "  Folder : $OutDir" -ForegroundColor Gray
Write-Host "  Size   : $sizeMB MB" -ForegroundColor Gray
if ($Zip) { Write-Host "  Zip    : $(Join-Path $DistDir "$OutputName.zip")" -ForegroundColor Gray }
Write-Host ""
Write-Host "Test it: open the folder and double-click start_app.bat" -ForegroundColor Cyan
Write-Host "(Recipient must create .env from .env.example with their API key first.)" -ForegroundColor Yellow
