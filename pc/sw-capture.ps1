# The live picture of SolidWorks' model window. The helper keeps this running while Claude builds and asks
# for one frame at a time on stdin; each answer is the document's title (empty = no picture this time).
#   frame <width> <height>   saves the picture to <file> (0 0 = the window's own size)
#   turn                     isometric, zoomed to fit, unless a sketch is open (Claude sketches looking straight at it)
# Frames land in the middle of Claude's steps: SaveBMP is safe there, but SaveAs3 quits an open sketch.
# With several copies of SolidWorks open (a Claude session can start its own), this follows the one that's
# changing: once a second every copy draws a small picture, and a copy whose picture changed takes over
# from one that has been still for $SwitchAfterMs.
# Usage: sw-capture.ps1 <file.bmp>
param([string]$Out)

$swIsometricView = 7
$CheckEveryMs = 1000
$FindCopiesEveryMs = 5000
$SwitchAfterMs = 3000
$Thumb = "$Out.thumb.bmp"

# The first copy started is the one GetActiveObject finds; each later one is listed as SolidWorks_PID_<id>
Add-Type -TypeDefinition @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
public static class SolidWorksCopies {
  [DllImport("ole32.dll")] static extern int GetRunningObjectTable(int r, out IRunningObjectTable t);
  [DllImport("ole32.dll")] static extern int CreateBindCtx(int r, out IBindCtx c);
  public static List<object> Listed() {
    var found = new List<object>();
    IRunningObjectTable rot; IEnumMoniker e; IBindCtx ctx;
    GetRunningObjectTable(0, out rot); rot.EnumRunning(out e); CreateBindCtx(0, out ctx);
    var one = new IMoniker[1];
    while (e.Next(1, one, IntPtr.Zero) == 0) {
      string name; one[0].GetDisplayName(ctx, null, out name);
      if (name.StartsWith("SolidWorks_PID_", StringComparison.OrdinalIgnoreCase)) {
        object o; rot.GetObject(one[0], out o);
        found.Add(o);
      }
    }
    return found;
  }
}
"@

# SolidWorks' type library doesn't load here, so PowerShell's own $sw.Member calls fail: this asks by name
function Call($obj, [string]$name, [object[]]$arguments = @()) {
  $how = [Reflection.BindingFlags]::InvokeMethod -bor [Reflection.BindingFlags]::GetProperty
  [System.__ComObject].InvokeMember($name, $how, $null, $obj, $arguments)
}

$copies = @{}      # process id -> @{ app; picture = hash of its small picture; changed = when it last changed (ms) }
$clock = [Diagnostics.Stopwatch]::StartNew()
$current = $null   # the process id being streamed
$checkAt = 0
$findAt = 0
$md5 = [Security.Cryptography.MD5]::Create()

function Find-Copies {
  $apps = @()
  try { $apps += [Runtime.InteropServices.Marshal]::GetActiveObject("SldWorks.Application") } catch { }
  try { $apps += [SolidWorksCopies]::Listed() } catch { }
  foreach ($app in $apps) {
    try { $id = Call $app "GetProcessID" } catch { continue }
    if (-not $copies.ContainsKey($id)) { $copies[$id] = @{ app = $app; picture = ""; changed = -1 } }
  }
}

function Check-Copies {
  foreach ($id in @($copies.Keys)) {
    $copy = $copies[$id]
    try {
      $doc = Call $copy.app "ActiveDoc"
      $picture = ""
      if ($null -ne $doc) {
        Call $doc "SaveBMP" @($Thumb, 200, 94) | Out-Null
        $picture = [BitConverter]::ToString($md5.ComputeHash([IO.File]::ReadAllBytes($Thumb)))
      }
      if ($copy.picture -and $picture -ne $copy.picture) { $copy.changed = $clock.ElapsedMilliseconds }
      $copy.picture = $picture
    } catch {
      $copies.Remove($id)       # closed; if it was only busy, Find-Copies brings it back
    }
  }
  if ($null -eq $script:current -or -not $copies.ContainsKey($script:current)) { $script:current = @($copies.Keys)[0] }
  if ($null -eq $script:current) { return }
  $still = $clock.ElapsedMilliseconds - $copies[$script:current].changed
  foreach ($id in @($copies.Keys)) {
    if ($still -ge $SwitchAfterMs -and $copies[$id].changed -gt $copies[$script:current].changed) { $script:current = $id }
  }
}

Find-Copies
if ($copies.Count -eq 0) { exit 2 }

while ($null -ne ($line = [Console]::In.ReadLine())) {
  $words = $line.Split(" ")
  $title = ""
  try {
    $now = $clock.ElapsedMilliseconds
    if ($now -ge $findAt) { Find-Copies; $findAt = $now + $FindCopiesEveryMs }
    if ($now -ge $checkAt) { Check-Copies; $checkAt = $now + $CheckEveryMs }
    if ($null -ne $current) {
      $doc = Call $copies[$current].app "ActiveDoc"
      if ($words[0] -eq "turn") {
        # Claude's SolidWorks tools work in the copy GetActiveObject finds
        $doc = Call ([Runtime.InteropServices.Marshal]::GetActiveObject("SldWorks.Application")) "ActiveDoc"
        if ($null -ne $doc -and $null -eq (Call $doc "GetActiveSketch2")) {
          Call $doc "ShowNamedView2" @("", $swIsometricView) | Out-Null
          Call $doc "ViewZoomtofit2" | Out-Null
        }
      } elseif ($null -ne $doc) {
        Call $doc "SaveBMP" @($Out, [int]$words[1], [int]$words[2]) | Out-Null
      }
      if ($null -ne $doc) { $title = Call $doc "GetTitle" }
    }
  } catch { $title = "" }
  [Console]::Out.WriteLine($title)
  [Console]::Out.Flush()
}
