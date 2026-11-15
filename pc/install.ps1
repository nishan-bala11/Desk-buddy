# Installs the Desk Buddy PC helper (status LED + media screens) on this PC.
# Run with install.bat (double-click), or: powershell -ExecutionPolicy Bypass -File install.ps1
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$dest = Join-Path $env:USERPROFILE ".claude\claude-led"
$settings = Join-Path $env:USERPROFILE ".claude\settings.json"
$taskName = "Claude LED Bluetooth"

Write-Host "`n=== Desk Buddy installer ===`n"

# 1. Python
$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python -or $python -match "WindowsApps") {
  Write-Host "Python 3 is required. Install it from https://www.python.org/downloads/"
  Write-Host "(tick 'Add python.exe to PATH' during setup), then run this installer again."
  Read-Host "Press Enter to exit"; exit 1
}
$pythonw = Join-Path (Split-Path $python) "pythonw.exe"
Write-Host "Python: $python"

Write-Host "Installing Python libraries (bleak, psutil, pillow, pycaw, winrt media)..."
& $python -m pip install --quiet --disable-pip-version-check bleak psutil pillow pycaw "winrt-Windows.Media.Control"
if ($LASTEXITCODE -ne 0) { Write-Host "pip install failed."; Read-Host "Press Enter to exit"; exit 1 }

# 2. Stop an old copy of the helper, then copy files
Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue | Stop-ScheduledTask -ErrorAction SilentlyContinue
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" |
  Where-Object { $_.CommandLine -match 'claude-led-ble' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

New-Item -ItemType Directory -Force $dest | Out-Null
Copy-Item "$here\claude-led-ble.py", "$here\claude-led.ps1", "$here\claude-status.py", "$here\merge_settings.py", "$here\sw-capture.ps1" $dest -Force
# The key that signs firmware updates sent over Bluetooth (the same one is in ..\DeskBuddy\ota_key.h)
if (Test-Path "$here\ota_key.txt") { Copy-Item "$here\ota_key.txt" $dest -Force }
# ESPN fantasy settings: only the first time, so a reinstall keeps your league id and cookies
if (-not (Test-Path (Join-Path $dest "fantasy.json"))) { Copy-Item "$here\fantasy.json" $dest }
Write-Host "Files copied to $dest"

# 3. USB backup COM port
$ports = Get-CimInstance Win32_PnPEntity | Where-Object { $_.Name -match '\(COM\d+\)' -and $_.Name -notmatch 'Bluetooth' }
$guess = ($ports | Where-Object { $_.Name -match 'CH34|CP210|USB' } | Select-Object -First 1).Name
Write-Host "`nUSB serial ports found:"
if ($ports) { $ports | ForEach-Object { Write-Host "  $($_.Name)" } } else { Write-Host "  (none - plug the ESP32 in by USB to see it)" }
$default = if ($guess -match '\((COM\d+)\)') { $Matches[1] } else { "COM3" }
$com = Read-Host "COM port of the ESP32 for USB backup [$default]"
if (-not $com) { $com = $default }
$ps1 = Join-Path $dest "claude-led.ps1"
(Get-Content $ps1 -Raw) -replace '\$Port\s+=\s+"COM\d+"', "`$Port       = `"$com`"" |
  Set-Content $ps1 -Encoding ASCII -NoNewline
Write-Host "USB backup set to $com"

# 4. Claude Code hooks (merged into existing settings, nothing else touched)
if (Test-Path $settings) { Copy-Item $settings "$settings.bak" -Force; Write-Host "Backed up settings.json to settings.json.bak" }
& $python (Join-Path $dest "merge_settings.py") $settings $ps1

# 5. Keep the Bluetooth helper running (at log-on, and re-checked every minute)
$action   = New-ScheduledTaskAction -Execute $pythonw -Argument "`"$(Join-Path $dest 'claude-led-ble.py')`"" -WorkingDirectory $dest
$logon    = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$every    = New-ScheduledTaskTrigger -Once -At (Get-Date).AddSeconds(10) -RepetitionInterval (New-TimeSpan -Minutes 1)
$opts     = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $logon, $every -Settings $opts -Force | Out-Null
Start-ScheduledTask -TaskName $taskName
Write-Host "Bluetooth helper started (scheduled task '$taskName')"

Write-Host "`nDone! Next:"
Write-Host "  1. Flash DeskBuddy\DeskBuddy.ino to the ESP32-S3 (see README.txt)."
Write-Host "  2. Restart the Claude app, then start a new Code session."
Read-Host "`nPress Enter to close"
