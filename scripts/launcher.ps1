# launcher.ps1 - AI Frontier Radar Local Launcher (GUI)
#
# Usage:
#   .\scripts\launcher.ps1
#
# A simple GUI launcher that wraps the existing PowerShell scripts.
# Uses Windows Forms (built into PowerShell) — no extra dependencies.

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

# ── Project root ─────────────────────────────────────────────────────────────
$Script:ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Script:ProjectRoot = (Resolve-Path (Join-Path $Script:ProjectRoot "..")).Path

# ── Constants ────────────────────────────────────────────────────────────────
$Port = 8765
$HomeUrl = "http://127.0.0.1:${Port}"
$StatusUrl = "http://127.0.0.1:${Port}/local-status"
$LogsDir = Join-Path $ProjectRoot "logs"

# ── Helpers ──────────────────────────────────────────────────────────────────

function Start-ScriptInNewWindow {
    param([string]$FilePath, [string]$Args = "")
    $fullPath = Join-Path $ProjectRoot $FilePath
    $pwsh = "powershell.exe"
    $psArgs = @(
        "-NoExit",
        "-ExecutionPolicy", "Bypass",
        "-File", "`"$fullPath`""
    )
    if ($Args) { $psArgs += $Args }
    Start-Process $pwsh -ArgumentList $psArgs -WindowStyle Normal
}

function Start-PythonScriptInNewWindow {
    param([string]$ScriptPath, [string]$PythonArgs = "")
    $fullPath = Join-Path $ProjectRoot $ScriptPath
    $bundledPython = Join-Path $ProjectRoot "python\python.exe"   # portable bundle
    $venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"  # dev venv
    $python = if (Test-Path $bundledPython) { $bundledPython }
              elseif (Test-Path $venvPython) { $venvPython }
              else { "python" }
    $pwsh = "powershell.exe"
    $cmd = "& `"$python`" `"$fullPath`" $PythonArgs"
    $psArgs = @(
        "-NoExit",
        "-ExecutionPolicy", "Bypass",
        "-Command", $cmd
    )
    Start-Process $pwsh -ArgumentList $psArgs -WindowStyle Normal
}

function Open-Url {
    param([string]$Url)
    Start-Process $Url
}

function Ensure-LogsDir {
    if (-not (Test-Path $LogsDir)) {
        New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null
    }
    Start-Process explorer.exe $LogsDir
}

# ── Build Form ────────────────────────────────────────────────────────────────
$Form = New-Object System.Windows.Forms.Form
$Form.Text = "AI Frontier Radar Local Launcher"
$Form.Size = New-Object System.Drawing.Size(420, 480)
$Form.StartPosition = "CenterScreen"
$Form.FormBorderStyle = "FixedDialog"
$Form.MaximizeBox = $false
$Form.MinimizeBox = $false

# Title label
$TitleLabel = New-Object System.Windows.Forms.Label
$TitleLabel.Text = "AI Frontier Radar"
$TitleLabel.Font = New-Object System.Drawing.Font("Segoe UI", 14, [System.Drawing.FontStyle]::Bold)
$TitleLabel.TextAlign = "TopCenter"
$TitleLabel.AutoSize = $false
$TitleLabel.Width = 380
$TitleLabel.Height = 35
$TitleLabel.Location = New-Object System.Drawing.Point(20, 20)
$Form.Controls.Add($TitleLabel)

# Subtitle label
$SubLabel = New-Object System.Windows.Forms.Label
$SubLabel.Text = "Local Launcher"
$SubLabel.Font = New-Object System.Drawing.Font("Segoe UI", 10)
$SubLabel.TextAlign = "TopCenter"
$SubLabel.AutoSize = $false
$SubLabel.Width = 380
$SubLabel.Height = 25
$SubLabel.Location = New-Object System.Drawing.Point(20, 55)
$Form.Controls.Add($SubLabel)

# Separator line
$Sep = New-Object System.Windows.Forms.Label
$Sep.Text = ""
$Sep.AutoSize = $false
$Sep.Width = 380
$Sep.Height = 1
$Sep.BackColor = [System.Drawing.Color]::FromArgb(200, 200, 200)
$Sep.Location = New-Object System.Drawing.Point(20, 85)
$Form.Controls.Add($Sep)

# Buttons - start from y=100, height=40, spacing=10
$btnW = 380
$btnH = 40
$btnX = 20
$btnY = 100
$spacing = 10

$buttons = @()

# Button 1: Start Web Service
$b1 = New-Object System.Windows.Forms.Button
$b1.Text = "Start Web Service"
$b1.Size = New-Object System.Drawing.Size($btnW, $btnH)
$b1.Location = New-Object System.Drawing.Point($btnX, $btnY)
$b1.FlatStyle = "Standard"
$b1.Add_Click({ Start-ScriptInNewWindow "scripts\start_local.ps1" })
$Form.Controls.Add($b1)
$buttons += $b1

# Button 2: Stop Web Service
$b2 = New-Object System.Windows.Forms.Button
$b2.Text = "Stop Web Service"
$b2.Size = New-Object System.Drawing.Size($btnW, $btnH)
$b2.Location = New-Object System.Drawing.Point($btnX, ($btnY += $btnH + $spacing))
$b2.FlatStyle = "Standard"
$b2.Add_Click({ Start-ScriptInNewWindow "scripts\stop_local.ps1" })
$Form.Controls.Add($b2)
$buttons += $b2

# Button 3: Open Home
$b3 = New-Object System.Windows.Forms.Button
$b3.Text = "Open Home"
$b3.Size = New-Object System.Drawing.Size($btnW, $btnH)
$b3.Location = New-Object System.Drawing.Point($btnX, ($btnY += $btnH + $spacing))
$b3.FlatStyle = "Standard"
$b3.Add_Click({ Open-Url $HomeUrl })
$Form.Controls.Add($b3)
$buttons += $b3

# Button 4: Open Local Status
$b4 = New-Object System.Windows.Forms.Button
$b4.Text = "Open Local Status"
$b4.Size = New-Object System.Drawing.Size($btnW, $btnH)
$b4.Location = New-Object System.Drawing.Point($btnX, ($btnY += $btnH + $spacing))
$b4.FlatStyle = "Standard"
$b4.Add_Click({ Open-Url $StatusUrl })
$Form.Controls.Add($b4)
$buttons += $b4

# Button 5: Show Status
$b5 = New-Object System.Windows.Forms.Button
$b5.Text = "Show Status"
$b5.Size = New-Object System.Drawing.Size($btnW, $btnH)
$b5.Location = New-Object System.Drawing.Point($btnX, ($btnY += $btnH + $spacing))
$b5.FlatStyle = "Standard"
$b5.Add_Click({ Start-ScriptInNewWindow "scripts\status_local.ps1" })
$Form.Controls.Add($b5)
$buttons += $b5

# Button 6: Open Logs Folder
$b6 = New-Object System.Windows.Forms.Button
$b6.Text = "Open Logs Folder"
$b6.Size = New-Object System.Drawing.Size($btnW, $btnH)
$b6.Location = New-Object System.Drawing.Point($btnX, ($btnY += $btnH + $spacing))
$b6.FlatStyle = "Standard"
$b6.Add_Click({ Ensure-LogsDir })
$Form.Controls.Add($b6)
$buttons += $b6

# Button 7: Run Daily Cycle Once
$b7 = New-Object System.Windows.Forms.Button
$b7.Text = "Run Daily Cycle Once"
$b7.Size = New-Object System.Drawing.Size($btnW, $btnH)
$b7.Location = New-Object System.Drawing.Point($btnX, ($btnY += $btnH + $spacing))
$b7.FlatStyle = "Standard"
$b7.Add_Click({ Start-ScriptInNewWindow "scripts\run_daily_cycle_once.ps1" })
$Form.Controls.Add($b7)
$buttons += $b7

# Button 8: Exit
$b8 = New-Object System.Windows.Forms.Button
$b8.Text = "Exit"
$b8.Size = New-Object System.Drawing.Size($btnW, $btnH)
$b8.Location = New-Object System.Drawing.Point($btnX, ($btnY += $btnH + $spacing))
$b8.FlatStyle = "Standard"
$b8.Add_Click({ $Form.Close() })
$Form.Controls.Add($b8)
$buttons += $b8

# Status bar at bottom
$StatusBar = New-Object System.Windows.Forms.Label
$StatusBar.Text = "Web: http://127.0.0.1:${Port}   |   Project: $ProjectRoot"
$StatusBar.Font = New-Object System.Drawing.Font("Segoe UI", 8)
$StatusBar.TextAlign = "BottomCenter"
$StatusBar.AutoSize = $false
$StatusBar.Width = 380
$StatusBar.Height = 20
$StatusBar.Location = New-Object System.Drawing.Point(20, ($btnY += $btnH + 15))
$StatusBar.ForeColor = [System.Drawing.Color]::Gray
$Form.Controls.Add($StatusBar)

# Show form
$Form.Add_Shown({ $Form.Activate() })
[void]$Form.ShowDialog()
