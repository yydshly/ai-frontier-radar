# create_shortcuts.ps1 - Create friendly, icon-bearing shortcuts for the app.
#
# .bat files always show the generic Windows shell icon and cannot embed their
# own. This creates .lnk shortcuts that point at the launchers and carry the
# radar icon (assets\app.ico), so the entry points are visually recognizable.
#
# The shortcuts are built with ABSOLUTE paths resolved from THIS folder, so run
# this on the machine where the app actually lives (e.g. after extracting the
# portable folder) - do not ship prebuilt .lnk files, their paths would be wrong.
#
# Usage:
#   .\scripts\create_shortcuts.ps1            # create shortcuts IN the app folder
#   .\scripts\create_shortcuts.ps1 -Desktop   # also create them on the Desktop

param(
    [switch]$Desktop,
    [string]$IconPath
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ScriptDir "..")).Path

# Icon: custom app.ico if present, else a sensible Windows system icon.
if (-not $IconPath) { $IconPath = Join-Path $ProjectRoot "assets\app.ico" }
if (-not (Test-Path $IconPath)) {
    Write-Host "[INFO] assets\app.ico not found; using a system icon." -ForegroundColor Yellow
    $IconPath = "$env:SystemRoot\System32\imageres.dll,143"   # globe/network glyph
}

$targets = @(
    @{ Name = "启动 AI前沿雷达";   Bat = "start_app.bat";     Desc = "启动 AI 前沿雷达并打开浏览器" },
    @{ Name = "AI前沿雷达 控制台"; Bat = "control_panel.bat"; Desc = "启动/停止/状态/手动执行每日任务" }
)

$destDirs = @($ProjectRoot)
if ($Desktop) { $destDirs += [Environment]::GetFolderPath("Desktop") }

$shell = New-Object -ComObject WScript.Shell
foreach ($dir in $destDirs) {
    foreach ($t in $targets) {
        $bat = Join-Path $ProjectRoot $t.Bat
        if (-not (Test-Path $bat)) {
            Write-Host "[skip] $($t.Bat) not found" -ForegroundColor DarkGray
            continue
        }
        $lnkPath = Join-Path $dir ($t.Name + ".lnk")
        $lnk = $shell.CreateShortcut($lnkPath)
        $lnk.TargetPath = $bat
        $lnk.WorkingDirectory = $ProjectRoot
        $lnk.IconLocation = $IconPath
        $lnk.Description = $t.Desc
        $lnk.WindowStyle = 1
        $lnk.Save()
        Write-Host "[ok] $lnkPath" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "Done. Double-click the new shortcut(s) to launch." -ForegroundColor Cyan
if (-not $Desktop) {
    Write-Host "Tip: re-run with -Desktop to also place them on your Desktop." -ForegroundColor Gray
}
