# Removes the Claude / Lightroom status LED from this PC.
# Run with uninstall.bat (double-click), or: powershell -ExecutionPolicy Bypass -File uninstall.ps1
$dest = Join-Path $env:USERPROFILE ".claude\claude-led"
$settings = Join-Path $env:USERPROFILE ".claude\settings.json"
$taskName = "Claude LED Bluetooth"

Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" |
  Where-Object { $_.CommandLine -match 'claude-led-ble' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if ($python -and (Test-Path "$dest\merge_settings.py") -and (Test-Path $settings)) {
  & $python "$dest\merge_settings.py" $settings "$dest\claude-led.ps1" --remove
}
Remove-Item $dest -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "Claude LED removed."
Read-Host "Press Enter to close"
