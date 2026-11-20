# Desk Buddy

ESP32-S3 N16R8 desk gadget: two round GC9A01 screens (eyes, music, 20 designed scenes, racing
gauge + minimap), two TTP223 touch sensors, an SW420 vibration sensor and the onboard RGB LED.
A Windows helper talks to it over Bluetooth LE. Setup for people: `pc/README.txt`.

## Layout

| Path | What |
|---|---|
| `DeskBuddy/DeskBuddy.ino` | Firmware (eyes, scenes, media, sim, LED, BLE) |
| `DeskBuddy/buddy_screens.h` | The 20 scenes exported from the Desk Buddy Screen Designer |
| `DeskBuddy/fantasy_screens.h` | ESPN fantasy basketball pages in three styles (Jumbotron, Neon, Court), made by hand |
| `DeskBuddy/claude_screens.h` | Claude's current step and question, the SolidWorks pages, made by hand |
| `DeskBuddy/ota_key.h`, `pc/ota_key.txt` | The key that signs wireless firmware updates. Private, unique to this buddy; never print or share them |
| `design/desk_buddy_design.json` | Design master - import into the Screen Designer to edit scenes |
| `design/fantasy_styles/` | Pictures of the fantasy pages (`basketball/` = what's built; the rest = the styles first offered) and `preview/`, the Python that draws them |
| `pc/claude-led-ble.py` | PC helper (BLE, media, volume, notifications, Claude status/usage, sim relay, fantasy) |
| `pc/claude-status.py` | Claude Code status line that saves plan usage to `usage.json` |
| `pc/install.bat` / `install.ps1` / `merge_settings.py` | Installer (copies to `%USERPROFILE%\.claude\claude-led`, adds hooks, scheduled task "Claude LED Bluetooth") |
| `pc/sw-capture.ps1` | Pictures SolidWorks' model window for the left screen |
| `pc/update-board.ps1` | Compiles and sends new firmware over Bluetooth, no USB |
| `pc/MERGE_NOTES.md` | BLE contract and what to carry over when merging other sketches |
| `racing-sim/game/` | The two Nishan Sim files changed for the board (only in the transfer zip) |

## Moving to a new PC

1. Arduino IDE + "esp32" board package (Espressif, built against core 3.3.12), libraries
   "GFX Library for Arduino" 1.6.9 and "JPEGDEC" 1.8.4.
2. Python 3 on PATH, then run `pc/install.bat`. The board's COM port will differ from COM9.
3. Racing sim: copy `racing-sim/game/deskbuddy.py` and `race.py` over the same files in
   `Racing-Sim-main/game/` (built on the Racing-Sim-main (2).zip version).
4. `pc/fantasy.json` still needs the ESPN fantasy basketball `league_id` (and cookies for a private league).
5. Phone notifications come straight from the iPhone over Bluetooth (paired with the board). Phone Link is only a fallback.

## Flashing

Without a cable, once the board has this partition scheme: `pc/update-board.ps1` (it logs to
`firmware/update.log` in the helper's folder). By USB, with the bundled arduino-cli (path under the
Arduino IDE's `resources/app/lib/backend/resources/`):

```
arduino-cli compile --upload -p COMx --fqbn "esp32:esp32:esp32s3:FlashSize=16M,PartitionScheme=app3M_fat9M_16MB,PSRAM=opi" DeskBuddy
```

- PSRAM must be OPI, or the right screen shows "Enable OPI PSRAM".
- USB CDC On Boot: Enabled when the board is plugged into its native "USB" port, Disabled for
  its UART ("COM") port. Add `,CDCOnBoot=cdc` to the FQBN for the first.
- Confirm a flash by resetting via RTS and looking for "Bluetooth ready" in the 115200 boot log.

## Wiring (v3, shared SPI bus)

- SCK 12, MOSI 11, MISO 13 (not connected; claimed by the bus)
- Left display: CS 10, DC 9, RST 14
- Right display: CS 16, DC 15, RST 7
- Buttons: left 4, right 5, each a 2-pin push button to GND (`INPUT_PULLUP`, active LOW, 30 ms
  `TOUCH_CONFIRM_MS`). They replaced the TTP223 touch sensors (2026-11-08), whose ghost touches came from the
  3D-printed plug over each pad. Firmware for buttons must not go to a board still fitted with TTP223s:
  their idle LOW reads as a held press.
- No BL pins and no vibration sensor (`VIB_PIN` -1; an SW420's DO would go on 2, powered from 3.3 V)
- RGB LED: 48

## Bluetooth contract

- Device name: "Desk Buddy 0A69"
- Service: `0cd20001-355a-4a08-8be1-4e7212f9c170`
- Characteristics:
  - CMD `…0002`. Text messages W/A/D/O/Y (LED; Y = flashing green / orange for 30 s after Claude finishes with a question box), N, P, V, X, T, F (fantasy matchup), L (fantasy standings), K (clock), U (Claude status + usage); binary G/S/Q (sim begin/state/quit). A line starting with `>` on the USB serial port is handled like a CMD message, to try screens without the helper.
  - IMG `…0003`
  - TOUCH `…0004`. Notify, actions `p n b + - m`; `b` (previous song) is a double click on the right button, `m` is the both-sensors mute chord.
  - TRACK `…0005`
  - OTA `…0006`. Signed firmware updates. Also on CMD: J (Claude's step), ? (its question), M (SolidWorks). `>@L` / `>@R` on USB dumps a screen's framebuffer, to check a layout without seeing it.
- Claude Code hooks reach the helper on TCP 47800.
- The game sends telemetry on UDP 47801.

## Things learned the hard way

- **Claude install path.** The helper must recognise both Claude installs, the Microsoft Store
  one (`\WindowsApps\Claude_`) and the regular installer (`\AnthropicClaude\`), from the
  window's exe path, or the LED stays dark.
- **Plan usage %.** The Claude desktop app never runs status lines, and no hook carries rate
  limits. The helper uses whichever source is newer:
  - `plan-usage-history.json`, which the app writes on each usage fetch (samples `{t, u:{fh, sd}}`), in `%APPDATA%\Claude` or, for the Store app, `%LOCALAPPDATA%\Packages\Claude_*\LocalCache\Roaming\Claude` or (newer Store versions, e.g. 3.6556) `%LOCALAPPDATA%\Claude-Data\claude_*`. All three are checked. From the app's code (3.6556): a right-click on the tray icon fetches (a left-click only opens the window), then it polls every 5 min for 30 min and every 15 min after, until a server-set "tray opened within N hours" window lapses or the PC is idle 10 min. Samples are at least 4.5 min apart, and a session % older than 5 hours counts as unknown (-1). Verified 2026-10-27: a right-click gave 44% / 57% on the board.
  - `usage.json` from the terminal status line.
- **Credentials.** Never read the app's credential/token files to get usage.
- **Each buddy needs its own Bluetooth name and IDs.** The helper connects to the first buddy
  advertising `DEVICE_NAME` (no pairing, no address check). This buddy started with the friend's
  kit's name and IDs ("Desk Buddy B60A", `6f1a…`), so the friend's laptop connected to it and sent
  it the friend's data (2026-10-28). It now has its own random ones ("Desk Buddy 0A69", `0cd2…`) in
  `DeskBuddy.ino` and `claude-led-ble.py`. Keep them when merging a newer kit from the friend, and
  give any copy made for someone else new ones.
- **Kits on the old wiring.** Kits built on the earlier desk_buddy sketch use the old v2 wiring
  (two SPI buses, BL pins). Port their features into this v3 `DeskBuddy.ino`, and three-way merge
  the helper (`git merge-file`, base = previous kit) so local changes survive.
- **Designed scenes are the slow path.** The time-of-day idle scenes (sleepy eyes 21:00-23:00,
  night mode, good morning) only appear once the helper has sent the clock; before that the
  idle scene is the sketch's own fast eyes. A scene frame is drawn into PSRAM, compared with
  what's on the screen and sent over the shared 40 MHz bus, so PSRAM bandwidth and SPI set the
  frame rate. `flushIfChanged` sends only the rectangle that changed, and `buddy::eye()` in
  `buddy_screens.h` is hand-optimised (pixel-identical, checked against the original). Re-exporting
  `buddy_screens.h` from the designer brings the slow `eye()` back. Moving eyes went from ~10 fps
  to ~25 fps. The Serial Monitor prints each scene's frame rate when it ends.
  In a scene, each sensor blinks the eye on its own screen, as in the plain eyes: `buddyDrawScene()`
  takes the right screen's `BuddyData` separately (`dRight`, another hand edit in `buddy_screens.h`).
  Scenes with an eye on one screen only (night mode, good morning, notifications) blink it with
  either sensor: `buddy::onEye` (a third hand edit) reports which screens a frame drew eyes on.
- **Fantasy pages (2026-10-28).** The owner's league is ESPN fantasy *basketball*, head-to-head points
  (the friend's kit was football): the helper reads `games/fba`, a season is numbered by the year it
  ends (2026-27 = 2027), and "live" means an NBA game is on. The owner picked three styles (Jumbotron,
  Neon, Court) out of seven offered, the rest are only pictures in `design/fantasy_styles`, and wants
  **one style a day** (the PC's day number in `K`, `% 3`), not styles cycling every few seconds.
  - The owner didn't want fantasy taking over: its pages only replace "nothing else on" (a scene whose
    `when` is exactly `BUDDY_WHEN_IDLE`: the eyes, night / morning / sleepy), and with idle +
    notification / volume they stay on the left with the designed notification card / volume ring on
    the right (scene 2xx / 3xx). Everything else keeps its designed scene with the score drawn over it
    in its own style (`ff::overlay`): a banner on the album cover (music, and music + volume), a pill on
    the notification card (music + notification), a row under the Claude usage bars, or under the
    tokens when a notification has the left screen.
  - On the fantasy pages the touch sensors flip pages (`updateTouch` with tap actions `>` / `<`,
    handled on the board; no holds), and a picked page stays `FANTASY_HOLD_MS`. When the matchup turns
    live the board makes its own "Games are on" notification (`fantasyAlert`), because the PC's `T`
    messages are dropped while the iPhone sends notifications directly.
  - ESPN gives this league no projections, so the win-chance page doesn't show (checked 2026-10-28).
  - When no game is on, the helper reads the league every 10 min but the public NBA scoreboard every
    minute (`_tipped_off`), so the pages come up within a minute of a tip-off.
  - `fantasy_screens.h` is hand-made with `buddy_screens.h`'s helpers and embedded fonts, so a
    re-export from the designer keeps it, but only if the design still uses the fonts it names.
  - The design's Inter 400 12 px font has a broken "+" (a 6x1 dash): text with a "+" uses 13 px.
  - The LED style draws the GFX library's 5x7 font (`font/glcdfont.h`, included inside `namespace ff`).
  - `DeskBuddy.ino`'s `fantasyScene()` decides when they show (over the eyes / Claude dashboard, every
    other turn with music; not over a notification, the volume or Claude needing you).
  - Not yet checked against a real league or on the screens: ESPN may give no projections for
    basketball (then the PROJ text and the win-chance page are left out). `--test-fantasy` prints the
    messages; to see the pages without a game on, type `>F...` / `>L...` lines into the USB serial port.
  - A notification beside the pages was only checked on the board on 2026-10-31, during a real game, after
    the owner said they weren't showing. A real iPhone push and two real texts each came up as "... +
    notification"; the push took 6 s. The board's own alert went to scene 19 with Claude working, 11 with music
    and 13 with both. That logic hadn't changed, so what the owner saw was most likely the iPhone link being
    down (see below), which can't be proved: the older firmware logged nothing. The check reads which scene the
    board picked, not the pixels. Each notification now leaves `[board] Notification: <app> x<count>`, then
    `Shown with fantasy ...` or `Shown in scene <n>`, in the helper's log, so a missing `Notification:` line
    means the board never got it. `Fantasy: games on` / `no games on` mark when the pages can show.
  - To test this with no USB while Claude is busy, a script can stand in for the helper: stop it, take TCP 47800
    so the scheduled task's copy exits at once (answer hooks with `1`), connect by name, subscribe to TOUCH to
    read the `#` lines, send `U` with status O, then `F` live 0 and live 1. Going live makes the board's own
    alert, so no phone is needed; the PC's `T` is dropped while the iPhone is connected. Send `F` live 0 at the
    end and start the task: the helper sends the real matchup again.
  - `design/fantasy_styles/preview` redraws the pictures with the real fonts (Pillow). It mirrors the
    C++ by hand, so change both together.
- **Claude and music come before the racing pages (2026-11-14).** The owner asked for it: `simYields()` hands the
  screens and LED back while Claude is W / A / Y or music is playing (paused doesn't count), and the game's next
  frame after takes them again. Seen on the board with Claude working during a test drive.
  An open question with reply buttons also counts, until it's answered (2026-11-15): the board's Claude status is
  `D` by then, so the sim kept the screens and the question only got its 8 s card beside the gauges, with the
  buttons still on music. Confirmed on the board with the game running.
- **Forza (2026-10-29).** The helper listens for Forza's Data Out on UDP 127.0.0.1:5300 (`ForzaRelay`)
  and turns each packet into the racing sim's own `G` / `S` messages (`forza_messages`), so the board's
  gauge and shift light work unchanged; frame flag 4 swaps the minimap for a lap / position screen fed
  by `R` (`drawRaceInfo`). Horizon 4 / 5 packets are 324 bytes with the "dash" part at offset 244
  (Motorsport 7: 311 bytes, at 232). Forza gives no shift points, so the light uses 75 % / 92 % of the
  rev limit (`FORZA_SHIFT`), and it's always the tacho. Lap number = laps done. Works with the owner's
  Steam copy of Horizon 4 (2026-10-29; nothing arrives until the game's Data Out is on, 127.0.0.1:5300).
  The Store version would also need a loopback exemption (README) - a system setting the owner runs.
  While driving, a notification / volume change takes the right screen for a moment (`drawSimOver`),
  the lap screen's bottom lines show the song and Claude's status, and the sensors still work the music.
  `pc/forza_demo.py` drives a made-up lap for testing without the game.
- **SolidWorks (2026-10-30).** The Solidworks-MCP-Server tools fire Claude Code's normal hooks, so
  `claude-led.ps1` passes the tool name to the helper (`SolidWorksFeed`). The owner wants a live stream,
  not a picture per step: while Claude builds and for 2 min after, `sw-capture.ps1` stays running and answers
  `SaveBMP` frames on request (the graphics area without its toolbars). Unchanged frames are skipped by hash.
  Measured (2026-10-30, spinning model, on battery): 151 frames in 30 s, about 5 a second. Each frame: SolidWorks
  draws in about 0.05 s, the cut-out takes 0.125 s (Python's flood fill, `SW_MASK_SIZE`, now the limit), Bluetooth
  0.03 s. SaveBMP alone does 33 a second. Things that bit:
  - **Never use SaveAs3 here.** Frames land in the middle of Claude's steps, and SaveAs3 quit its open
    sketch, so the next tools failed with "No active sketch" (2026-10-30). SaveBMP left the sketch open,
    also at full stream rate through sketch, circle, rectangle and extrude.
  - Grabbing the window instead (PrintWindow) comes back black: the model is drawn with OpenGL.
  - Frames are written without Bluetooth responses: with them a frame took 0.27 s. A lost write makes the
    board drop that frame (the length won't match), so when the picture stops moving the last frame goes
    again with responses. How many frames get lost in flight hasn't been counted.
  - Starting PowerShell takes over a second, so the one process stays up. It reads commands on stdin.
  - **Claude mostly builds with scripts, and between runs it writes the next one for many minutes.** On real
    builds (2026-10-30) a stream started by tool names, then by words in shell commands, kept dropping out, and
    words matched commands that weren't building. So the model itself decides now: while Claude is busy
    (`W` / `A`) and SLDWORKS.exe runs, frames go at 1 a second just to compare, a change brings the pages up
    and raises the rate to 10, and `held()` keeps them up until 20 min without a change (`SW_BUILD_SECONDS`), or
    2 min once Claude has finished. A change made by hand while Claude is busy brings them up too.
    `claude-led.ps1`'s `sw_script` now only names the step: a command that mentions SolidWorks becomes a step if
    the model changed while it ran, which with two sessions can still be the wrong session's command.
    Script steps never turn the view.
  - `>@L` / `>@R` can lose bytes while SolidWorks loads the PC: a shifted edge ring means the read-back is bad,
    not the screen. It also stops the board's loop for 10 s, and a Bluetooth write can fail with "Unreachable".
  - Sessions can run a second SolidWorks, and `GetActiveObject` reaches only the first. Later copies are in the
    running object table as `SolidWorks_PID_<id>` (the first has only its class entry, so it's found both ways;
    `GetProcessID` tells them apart). `sw-capture.ps1` follows the copy that's changing: once a second each copy
    saves a 200 x 94 picture and its hash is compared, and a changed copy takes over from one still for 3 s.
    Seen once on real builds (2026-10-30): it moved from a still copy to the changing one, and the board then
    showed that one live. The step text isn't tied to a copy: it can come from a session working in the other,
    or from any shell command that mentions SolidWorks.
  - PowerShell's normal `$sw.ActiveDoc` fails (TYPE_E_ELEMENTNOTFOUND or null, SolidWorks' type library
    doesn't load), so the script goes through `InvokeMember`.
  - Saving a picture to a very long path silently writes nothing (exit 4). The picture lives in `%TEMP%`.
  - The background is a soft radial gradient whose greys overlap the model's. Comparing colours doesn't
    work; `make_model_jpeg` floods from the corners and stops at sharp edges.
  - After a sketch the view stays flat-on, so the script turns it to isometric between steps (not while a
    sketch is open). That moves the owner's view: `SW_TURN_TO_ISOMETRIC` turns it off.
  - The tools report a failure as ordinary text, so `claude-led.ps1` looks for "Error in solidworks" and
    those steps don't count.
- **Wireless updates (2026-10-30).** The app partitions changed from `huge_app` to `app3M_fat9M_16MB` (nvs
  at the same offset, so the iPhone's pairing survives), which took one last USB flash. Firmware goes over
  BLE into PSRAM, then HMAC-SHA256 with the key in `ota_key.h` / `ota_key.txt`, then to the other slot, so a
  dropped link or a bad image can't touch what's running. Measured: 848 KB sent in 162 s, installed in 3 s.
  A wrong-key image and signed garbage were both refused and the board kept running. The stock bootloader
  has no rollback, so `otaBootCheck` does it: 3 boots that don't reach `OTA_HEALTHY_MS` go back to the old
  slot (not tested with a really crashing build). The counter is in RTC memory, so a power cut resets it.
  On 2026-10-31 one update sent every byte, got no answer for 120 s and left the old firmware running; the retry
  worked. Probably, though not proven: `loop()` compared `now` with `otaLastAt`, which the Bluetooth task can set
  just after `now` was read, and unsigned that wraps to a huge silence, so the board dropped the update and ignored
  the rest. It's a signed compare now, and a drop logs `[board] Update: dropped after N of M bytes`.
- **Unknown plan usage shows "--".** The helper sends -1 when it doesn't know (the Claude app's newest
  sample is over 5 hours old, the session window): `BuddyData::sessionKnown / weeklyKnown` and
  `field()` in `buddy_screens.h` are another hand edit (keep them if you re-export). The fix for the
  number itself is a right-click on the Claude tray icon, which makes the app fetch again.
- **Touch debounce.** TTP223 outputs flicker as a finger lands or shifts. Without debounce, a flicker
  cut a volume hold short and the rest became a tap (pause / skip). Measured on this buddy (2026-10-27):
  about 75 dropouts of 60-185 ms in 6 minutes of holds, and longer ones chopped a hold into a run of taps.
  A press now ends only `TOUCH_RELEASE_MS` (300) after the last touched reading, volume steps go out
  only while touched, and `AFTER_VOLUME_MS` (1 s) after a volume hold a touch can't tap. The mute chord
  re-arms only after both are off for the same 300 ms. Taps, holds and ignored dropouts are printed
  to the Serial Monitor ("Touch: ...").
  Because of that window a quick double click arrives as one press that was let go and pressed again
  (`Touch::clicks`); on the "next" button it sends `b`, previous song (2026-11-19, confirmed on the board).
  Single clicks keep their timing. A slow double click (over `TAP_MAX_MS` from the first press) becomes a volume hold.
- **Volume follows the default device.** The helper starts at log-on, but the default output can
  change later (Realtek's jack switches between "Speakers" and "Headphones", a monitor or Bluetooth
  set connects). `Volume` asks Windows for the default playback device before every step or mute and
  every 3 s for the screens' reading, and reconnects when its ID changes. It used to keep the device
  from start-up, so holds and the mute chord moved a device nobody was listening to.
- **iPhone notifications go straight to the board (ANCS), not through Phone Link.** That's the owner's setup:
  check this route first (`ancsTask` in `DeskBuddy.ino`). While it's connected (`iphoneDirect`) the board drops
  the helper's `T` messages, so Phone Link only matters as a fallback. The iPhone can only come back to a board
  that's advertising, and with the helper and iPhone both connected the board stops advertising, so "no adverts
  heard" means the iPhone is connected or locked out. On 2026-10-31 notifications stopped with no adverts heard
  in two 15 s scans (9 other devices heard). `updateAdvertising` now restarts advertising every
  `ADVERTISE_CHECK_MS` unless ANCS is up, and `ancsSetup` no longer leaves a returning, already encrypted iPhone
  connected without subscribing. The board usually isn't on USB, so `ancsNote` also sends its iPhone lines to the
  helper's log as `[board] ...` (a TOUCH notification starting with `#`). Never put notification text in them.
  After that update the iPhone reconnected and subscribed within seconds of the restart, so the pairing was fine.
  Which fault it was isn't known: the old firmware had no logging, and the restart alone may have cleared it.
  The boot line counts the iPhone under "other devices" (bonds keep its public identity address), so
  "0 phone(s)" there is normal.
  A `Notification:` line in the log doesn't prove this route: it's written for Phone Link's `T` messages too. Look
  for `iPhone: notifications connected` with no `iPhone: disconnected` after it. On 2026-10-31 the link flapped
  from 17:08 and ended at 17:16:43. Every failure there was code 7 (the link had already gone), so the iPhone or
  the radio dropped it, not the board. From then on notifications only arrived through Phone Link, and the iPhone
  stayed away for 18 hours even though Phone Link (also Bluetooth) showed it was in range until at least 01:26, and
  a board restart at 11:05 didn't bring it back, where the restarts at 13:59 and 16:09 had within seconds. The board
  was advertising with the ANCS solicitation and kept its bond, so that half of it is on the phone's side; a
  peripheral can't call a phone back. It came back by itself about 11:21, a minute after the helper was restarted,
  with no firmware change yet; what prompted it isn't known. It then returned within seconds of the 11:24 update's
  restart. Connects, failed connects, drop reasons and the restart reason now go to the log, and the helper logs
  `[helper] connected to the board` / `lost the board`.
- **Phone notifications (iPhone + Phone Link).** The helper reads Windows' notification history
  (`wpndatabase.db`), so it only sees what Phone Link hands to Windows. Phone Link keeps its own list
  in memory only (nothing on disk). Learned on 2026-10-27:
  - Phone Link stopped handing anything to Windows for 3.5 hours after a burst of Snapchat
    "paused banners for 3 minutes" notices. It still listed the notifications in its own window.
    Settings and the window being open weren't the cause; restarting Phone Link fixed it.
  - Windows "Do not disturb" hides the pop-ups but still saves notifications, so the buddy gets them.
  - An iPhone's texts come through Phone Link's Messages feature under the phone's device id (a GUID).
    `phone_app_name` maps that to "Messages"; Snapchat's iOS id is `com.toyopagroup.picaboo`.
  - When checking notifications, print only app ids, times and lengths, never the text.
- **Old "Claude LED" kit.** An earlier kit ran `%USERPROFILE%\.claude\claude-led-ble.py`, which looks
  for a device named "Claude LED" on the Nordic UART UUIDs, so it can't reach this board. Its hooks
  call `.claude\claude-led.ps1`. `install.ps1` stops that helper, and `merge_settings.py` replaces
  every hook containing `claude-led.ps1`, old or new.
- **Tuned values.**
  - `VIB_TRIGGER` is 25, tuned by feel on the friend's buddy (15 was "way too touchy"). This buddy has no vibration sensor (`VIB_PIN` -1).
  - Night mode runs 23:00-06:00, good morning 06:00-08:00 and sleepy eyes 21:00-23:00, each set in the design JSON and in `buddy_screens.h`. Good morning ran to 11:00 in the friend's design; this buddy's owner moved it to 08:00 (2026-10-28), so keep that when taking a newer design or `buddy_screens.h` from the friend.

- Answering Claude from the board (2026-11-14): when the next-step box asks a question with reply buttons, the left screen shows the question and the right shows the first two reply labels. Left button = top, right = bottom. The board sends `1`/`2`, and the helper brings the Claude app to the front (an Alt tap then SetForegroundWindow, since Windows blocks background apps from taking the focus; it types only if Claude really has the focus, otherwise the card stays up for another press) and types the label + Enter. First it opens the chat that asked with `claude://code/continue?session=local_<id>` (the id comes from the app's claude-code-sessions/local_*.json whose cliSessionId matches the transcript; an undocumented link, so an app update could break it). The question is kept even if the board is away, and sent again on reconnect. While it is open, other sessions cannot take the screens. Confirmed working live.
  The question goes as an acknowledged write (`write_cmd(..., confirm=True)`) and a failure is logged: once
  (2026-11-15) it never reached the board as a write without response. A new turn in the asking chat clears it,
  including one started by a background task finishing.
- Background tasks (2026-11-15): a turn that ends while a background command or agent it started is still running
  shows as `W`, not `D` (`background_running`: a start with no `<task-id>` finish note and no `TaskStop`; one with
  neither is ignored after an hour). `pc/test_background.py` checks it. Seen live: the board got `W` for the chat
  for the whole minute a background task ran.
- Bluetooth drops: on 2026-11-15 the link dropped about once a minute while the racing sim streamed, and about once
  in 10 minutes otherwise. Wireless updates failed then; USB worked. Cause not found. A failed reconnect is
  logged as `[helper] reconnect failed: ...`.
