# Updates the buddy's firmware over Bluetooth, no USB cable: compiles ..\DeskBuddy and hands the result to
# the PC helper, which sends it to the board. The board only needs power and the helper connected.
# Usage: powershell -ExecutionPolicy Bypass -File update-board.ps1
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$cli = Join-Path $env:LOCALAPPDATA "Programs\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe"
$fqbn = "esp32:esp32:esp32s3:FlashSize=16M,PartitionScheme=app3M_fat9M_16MB,PSRAM=opi"
$build = Join-Path $env:TEMP "deskbuddy-build"
$firmware = Join-Path $env:USERPROFILE ".claude\claude-led\firmware"
$log = Join-Path $firmware "update.log"

Write-Host "Compiling..."
& $cli compile --fqbn $fqbn --output-dir $build (Join-Path $here "..\DeskBuddy")
if ($LASTEXITCODE -ne 0) { Write-Host "It didn't compile, so nothing was sent."; exit 1 }

New-Item -ItemType Directory -Force $firmware | Out-Null
$before = if (Test-Path $log) { (Get-Content $log).Count } else { 0 }
Copy-Item (Join-Path $build "DeskBuddy.ino.bin") (Join-Path $firmware "update.tmp") -Force
Move-Item (Join-Path $firmware "update.tmp") (Join-Path $firmware "update.bin") -Force   # the helper only sees it whole

Write-Host "Sent to the helper. Waiting for the board (a few minutes)..."
$end = (Get-Date).AddMinutes(10)
while ((Get-Date) -lt $end) {
  Start-Sleep -Seconds 2
  if ((Test-Path $log) -and (Get-Content $log).Count -gt $before) {
    Get-Content $log | Select-Object -Skip $before
    exit 0
  }
}
Write-Host "No answer after 10 minutes: is the board on and connected to the helper?"
exit 1
