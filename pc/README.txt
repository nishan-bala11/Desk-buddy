DESK BUDDY  (ESP32-S3 N16R8 + 2x GC9A01 round screens + 2 touch sensors + RGB LED)
==================================================================================

What it does
------------
  Idle           - two eyes that wander and blink when you touch the sensors
  Media playing  - anything in the Windows volume / media popup (Spotify, YouTube in a
                   browser, VLC...):
                     left screen  : album cover spinning like a vinyl (videos: still thumbnail)
                     right screen : app, title, artist, progress ring, elapsed / remaining time,
                                    and a volume ring whenever the volume changes
                     touch        : tap LEFT  = play / pause
                                    tap RIGHT = next
                                    hold LEFT / RIGHT = volume down / up
                   Paused for 30 s or nothing playing -> back to the eyes.
  Screens        - the 20 scenes from the Desk Buddy Screen Designer (DeskBuddy\buddy_screens.h):
                   the board picks one from what's happening - music playing or paused, volume
                   changing, a phone notification, Claude's status, the time of day (night mode
                   23:00-06:00, good morning 06:00-08:00). To change them, export a new
                   buddy_screens.h from the designer into the DeskBuddy folder and re-upload.
  Phone          - notifications from your phone (WhatsApp, Messages, Snapchat...) show for 8 s:
                   app logo, sender and message. An iPhone sends them straight to the buddy over
                   Bluetooth, no PC needed: pair once in the iPhone's Settings > Bluetooth ("Desk Buddy
                   0A69" > Pair, then Allow notifications) and it reconnects by itself. What happened
                   goes in the helper's log as [board] lines. Without that pairing, Phone Link on the PC
                   is the fallback: with your phone connected and its Notifications switch on, it passes
                   them to Windows and the helper sends them on (with Windows "Do not disturb" on too).
  Claude screens - status, session time and tokens (from the session's transcript), and your plan's
                   session / weekly usage. Only Claude Code's status line gets the usage, so the
                   installer sets claude-status.py as your status line (unless you have one); it
                   saves the numbers to usage.json for the helper. The Claude desktop app doesn't
                   run status lines, but it records the usage it fetches in plan-usage-history.json
                   (%APPDATA%\Claude, or %LOCALAPPDATA%\Claude-Data\claude_... for the Microsoft
                   Store app), and the helper uses whichever is newer. The desktop app only fetches
                   for a while after you RIGHT-click its tray icon (the Claude icon by the clock;
                   the menu shows "Usage: ..%"): then every 5 minutes for half an hour, every 15
                   after that. A session % older than 5 hours shows as unknown, so if the numbers
                   are missing or look old, right-click that icon once.
                   While Claude works, its current step shows on those screens ("Editing notes.md",
                   "Running tests"). While it waits for you, its question or permission request takes
                   the right screen, until you answer. In a game it shows for 8 s.
  SolidWorks     - while Claude builds in SolidWorks through Claude Code:
                     left screen  : a live picture of the model, cut out on black, about 5 frames a
                                    second while it moves (sketches being drawn, features appearing)
                     right screen : the document, the step, how many steps so far, the last three, and
                                    the song if one is playing
                   While Claude Code is working and SolidWorks is open, any change to the model brings it
                   up, whether Claude uses its SolidWorks tools or scripts of any name (or you change
                   something by hand meanwhile). It holds while Claude works, through the quiet spells of a
                   build, until 20 minutes without a change, or 2 minutes after Claude finishes. Set
                   SW_BUILD_SECONDS in claude-led-ble.py to change that. Notifications and the volume show
                   on the right for a moment, and the touch sensors still work the music. Between tool
                   steps the helper turns SolidWorks' view to isometric and zooms to fit (not while a sketch
                   is open, and not for scripts); set SW_TURN_TO_ISOMETRIC to False to leave the view alone.
                   Claude working from a regular chat doesn't show: only Claude Code runs the hooks this
                   uses. With two copies of SolidWorks open, it shows the one that's changing.
  Mute           - press both touch sensors at once (any time but while racing) to mute / unmute.
  Fantasy        - ESPN fantasy basketball (head-to-head points), set up in fantasy.json (see "ESPN
                   fantasy" below). While an NBA game is on and nothing else is on the screens, they
                   show your matchup, win chance (if ESPN gives projections), lead through the week
                   and the standings, 8 s each, in one style a day: Jumbotron (arena LED scoreboard),
                   Neon, Court (hardwood), then round again. Tap the right sensor for the next page,
                   the left one for the previous (it then stays 30 s). Music and the Claude dashboard
                   stay up and show your score themselves (a banner across the album cover, a row
                   under the usage bars), and so do their volume / notification screens; with the
                   fantasy pages up, a notification or the volume shows on the right screen beside
                   them. When the games start, the buddy shows a "Games are on" notification. Pictures
                   of every page: ..\design\fantasy_styles\basketball.
  RGB LED        - Claude Code / Lightroom Classic status:
                     pulsing white = working, orange = needs you, green = done, off = Claude closed,
                     flashing green / orange = Claude finished and asked you something (the box
                     with buttons at the end of a reply): 30 s, then green, or until you reply
  Racing sim     - while you drive in Nishan Sim (Racing-Sim-main, game\deskbuddy.py):
                     left screen  : turbo boost gauge (turbo cars) or tachometer (the rest) + gear
                     right screen : the game's minimap (heading-up, zooming, stretch ahead bright)
                     RGB LED      : shift light - green, yellow, orange, red, flashing red
                   Leaving the session (or the game closing) goes back to the music / eyes.
  Forza          - Forza Horizon 4 / 5 (and Motorsport 7) while you drive:
                     left screen  : tacho with the gear and your speed (km/h)
                     right screen : in a race your position, lap, lap time, best and last laps;
                                    in free roam your speed, the car's class / PI and top speed
                     RGB LED      : shift light - green, yellow, orange, red, flashing red near the
                                    rev limit
                   In the game: Settings > HUD and Gameplay > Data Out: On, Data Out IP Address
                   127.0.0.1, Data Out IP Port 5300. The Microsoft Store / Game Pass version of
                   Horizon 4 also needs Windows to let it send to the PC itself, once, in an
                   administrator PowerShell:
                     CheckNetIsolation LoopbackExempt -a -n=Microsoft.SunriseBaseGame_8wekyb3d8bbwe
                   (the Steam version doesn't). Menus and pause go back to the music / eyes after 3 s.
                   Without the game: python forza_demo.py drives a made-up 30 s lap.

This board is called "Desk Buddy 0A69" with its own Bluetooth IDs, so it won't connect to
anyone else's buddy or laptop nearby. If you make a copy of this kit for someone else, give it a
new name and IDs (DEVICE_NAME and the UUIDs at the top of DeskBuddy.ino and claude-led-ble.py).
It replaces the "Claude LED B60A" kit (same install folder).

You need
--------
  - ESP32-S3 N16R8, 2x GC9A01, 2x TTP223 touch sensors - wired like gc9a01_eyes_s3_v3
    (both displays share SCL/SDA, no BL pins):
      LEFT  display: SCL 12, SDA 11, CS 10, DC 9,  RST 14
      RIGHT display: SCL 12, SDA 11, CS 16, DC 15, RST 7
      Touch SIG:     left 4, right 5           RGB LED: 48 (onboard)
      No vibration sensor (VIB_PIN is -1 in DeskBuddy.ino). To add an SW420: VCC 3.3V (not 5V),
        GND, DO -> 2, and set VIB_PIN to 2 (bump the desk: the eyes shake, then go dizzy)
  - Windows PC with Bluetooth and Python 3 (python.org, tick "Add python.exe to PATH")
  - Arduino IDE with the "esp32" board package by Espressif
  - Libraries (Library Manager): "GFX Library for Arduino" (moononournation), "JPEGDEC" (Larry Bank)

1. Flash the board
------------------
  Open ..\DeskBuddy\DeskBuddy.ino in Arduino IDE.
  Tools > Board            : ESP32S3 Dev Module
  Tools > PSRAM            : OPI PSRAM        <-- required
  Tools > Flash Size       : 16MB (128Mb)
  Tools > Partition Scheme : 16M Flash (3MB APP/9.9MB FATFS)    <-- has room for wireless updates
  Tools > USB CDC On Boot  : Enabled if plugged into the board's "USB" port
  Upload. The eyes appear straight away.

  Later updates don't need the cable (the board only needs power and the helper connected):
      powershell -ExecutionPolicy Bypass -File update-board.ps1
  It compiles the sketch and the helper sends it over Bluetooth. The screens show the progress, the
  buddy restarts by itself, and the result goes in %USERPROFILE%\.claude\claude-led\firmware\update.log.
  The board only accepts firmware signed with its own key (DeskBuddy\ota_key.h, pc\ota_key.txt): keep
  those private. If new firmware crashes 3 times in its first minute, the board goes back to the old one.

2. Install on the PC
--------------------
  Double-click install.bat. It installs the Python libraries, copies the helper to
  %USERPROFILE%\.claude\claude-led, asks for the board's COM port (USB backup for the LED),
  adds the Claude Code hooks to %USERPROFILE%\.claude\settings.json (backup saved as
  settings.json.bak), and creates the scheduled task "Claude LED Bluetooth" that keeps the
  helper running. Don't pair the board in Windows Bluetooth settings - the helper connects itself.

3. Try it
---------
  - Play a song in Spotify: within a couple of seconds the screens switch to the cover + info.
  - Tap the left sensor to pause, tap the right one to skip, hold to change the volume.
  - Claude: quit and reopen the Claude app, start a NEW Code session and send a message.

  To see what the PC is reading without the board:
      python "%USERPROFILE%\.claude\claude-led\claude-led-ble.py" --test-media

ESPN fantasy basketball (optional)
----------------------------------
  For a head-to-head points league. Open %USERPROFILE%\.claude\claude-led\fantasy.json in Notepad
  and fill in:
    league_id : the number after leagueId= in your league's web address
                (fantasy.espn.com/basketball/league?leagueId=...)
    espn_s2   : } only for a PRIVATE league. In your browser, signed in to espn.com, open the
    swid      : } site's cookies (Chrome: F12 > Application > Cookies > https://www.espn.com)
                  and copy the values of "espn_s2" and "SWID". They work like a password: don't
                  share the file. They change if you sign out of ESPN; copy them again then.
    team_id   : leave empty; set it only if the buddy shows someone else's team.
  Save, then check it once:
      python "%USERPROFILE%\.claude\claude-led\claude-led-ble.py" --test-fantasy
  Reinstalling keeps your fantasy.json.

Tuning
------
  Board (top of DeskBuddy.ino): VINYL_RPM, SPI_HZ (80000000 = smoother spin), TAP_MAX_MS,
    TOUCH_RELEASE_MS (raise it if a hold still turns into a pause / skip), AFTER_VOLUME_MS,
    VOLUME_REPEAT_MS, VOLUME_SHOW_MS, L_ROTATION / R_ROTATION,
    VIB_TRIGGER (higher = needs a harder knock; also turn the SW420's blue pot), DIZZY_MS, DIZZY_R.
  PC (top of claude-led-ble.py): PAUSED_TO_EYES_SECONDS, VOLUME_STEP, BROWSERS (apps whose
    thumbnail doesn't spin), LR_BUSY_* (Lightroom thresholds - measured on another PC).
  After editing the .py, end pythonw.exe in Task Manager; the task restarts it within a minute.

Troubleshooting
---------------
  - Errors: %USERPROFILE%\.claude\claude-led\claude-led-ble.log
  - Right screen says "Enable OPI PSRAM": set Tools > PSRAM to OPI PSRAM and re-upload.
  - "Sketch too big": pick the 16M Flash (3MB APP/9.9MB FATFS) partition scheme.
  - A screen stays black: check its wiring (CS / DC / RST); try SPI_HZ 27000000.
  - LED test without Claude:
      powershell -ExecutionPolicy Bypass -File "%USERPROFILE%\.claude\claude-led\claude-led.ps1" A

Uninstall
---------
  Double-click uninstall.bat (removes the hooks, scheduled task and files).
