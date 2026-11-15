# Sends a one-letter status to the ESP32 status LED (Bluetooth helper first, USB as backup).
# Usage: claude-led.ps1 W|A|D|O
param([string]$State = "O")

$HelperPort = 47800   # claude-led-ble.py listens here
$Port       = "COM9"  # USB backup (Device Manager > Ports) - install.ps1 sets this

# Claude Code passes hook details as JSON on stdin; the helper uses the transcript path to notice
# when you stop a prompt, and the short list below for what Claude is doing and asking.
$transcript = ""
$info = ""
if ([Console]::IsInputRedirected) {
  try {
    $hook = [Console]::In.ReadToEnd() | ConvertFrom-Json
    $transcript = $hook.transcript_path
    $i = $hook.tool_input
    $question = if ($i.questions) { $i.questions[0].question } else { $null }
    # The SolidWorks tools report a failed step as ordinary text
    $failed = $hook.tool_name -match 'solidworks' -and ($hook.tool_response | ConvertTo-Json -Compress -Depth 4) -match 'Error in solidworks'
    # Claude also drives SolidWorks with scripts from the shell, not only with its SolidWorks tools
    $swScript = $hook.tool_name -in 'Bash', 'PowerShell' -and "$($i.command)" -match 'sldworks|solidworks|win32com|sldprt|sldasm'
    $info = @{ event = $hook.hook_event_name; tool = $hook.tool_name; message = $hook.message; file = $i.file_path
               desc = $i.description; pattern = $i.pattern; question = $question; failed = $failed
               sw_script = $swScript } | ConvertTo-Json -Compress
  } catch { }
}

try {
  $tcp = New-Object System.Net.Sockets.TcpClient
  if ($tcp.ConnectAsync("127.0.0.1", $HelperPort).Wait(300)) {
    $stream = $tcp.GetStream()
    $stream.ReadTimeout = 1500
    $bytes = [System.Text.Encoding]::UTF8.GetBytes("$State`t$transcript`t$info`n")
    $stream.Write($bytes, 0, $bytes.Length)
    $reply = $stream.ReadByte()
    $tcp.Close()
    if ($reply -eq [byte][char]'1') { exit 0 }   # delivered over Bluetooth
  } else { $tcp.Close() }
} catch { }

try {
  $sp = New-Object System.IO.Ports.SerialPort $Port, 115200
  $sp.DtrEnable = $false   # don't reset the board when opening the port
  $sp.RtsEnable = $false
  $sp.WriteTimeout = 500
  $sp.Open()
  $sp.Write($State)
  $sp.Close()
} catch { }   # never block Claude Code if the board is unreachable
exit 0
