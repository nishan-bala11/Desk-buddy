# Desk Buddy – notes for merging with other sketches

For whoever (or whichever Claude) merges `DeskBuddy/DeskBuddy.ino` into another version of the
eyes sketch. Everything below is what the PC helper (`claude-led-ble.py`) expects from the board.

## Starting point

`DeskBuddy.ino` runs on the gc9a01_eyes_s3_v3 wiring: both GC9A01s share one SPI bus (SCK 12,
MOSI 11) through `Arduino_HWSPI`, each with its own CS, DC and RST, and no BL pins. Kits on the
older v2 wiring (two buses, BL pins) differ only in the pin block, the `busL` / `busR` lines and
the BL setup in `setup()`. The sketch has three modes:

1. **`MODE_EYES`**: the sketch's own eyes (touch-to-blink, wander; dizzy after a bump if an SW420 is fitted on `VIB_PIN`),
   redrawn in small strips where they changed. Used for the "Idle eyes" scene.
2. **`MODE_SCENE`**: every other scene from `buddy_screens.h` (Desk Buddy Screen Designer), drawn
   into two `Arduino_Canvas` framebuffers in PSRAM about 30 times a second. Only the rectangle
   that changed since the last frame is sent (`flushIfChanged` compares against `shownL` / `shownR`).
   Anything that draws to a screen outside a scene has to make the next scene re-send in full
   (`sceneForce`, or `curScene = -1`). `pickScene()` turns what's happening into the
   designer's `BUDDY_WHEN_` bits and lets `buddyPickScene()` choose. Three hand edits of the
   designer's export in `buddy_screens.h` to keep when merging: a faster `buddy::eye()`,
   `buddyDrawScene()`'s optional `dRight` (the right screen gets `rightEye.lid`, so each sensor
   blinks its own eye), and the `buddy::onEye` hook (scenes with one eye blink it with either sensor).
3. **`MODE_SIM`**: the racing sim. Left screen boost gauge or tacho, right screen minimap, LED as a
   shift light. It ends on `Q` or after 3 s without telemetry.

Also: the **BLE server** (`setupBLE`, `CmdCB`, `ImgCB`, `TrackCB`, `ServerCB`, `sendTouch`), the
**RGB status LED** on GPIO 48 (`applyLed`, `updateLed`), and **touch** (`updateTouch`,
`updateMuteChord`). One ESP32 advertises one name, so any other BLE feature (e.g. phone gyro) should
be added as **extra characteristics on this same service**, not a second `BLEDevice::init`.

## Bluetooth contract (must match the PC helper)

| Item | Value |
|---|---|
| Device name | `Desk Buddy 0A69` (`DEVICE_NAME` in both files). Unique to this buddy: keep it and the UUIDs below when merging a kit from the friend (theirs is `Desk Buddy B60A`, `6f1a…`) |
| Service | `0cd20001-355a-4a08-8be1-4e7212f9c170` |
| CMD (write / write-no-response) | `0cd20002-…` |
| IMG (write) | `0cd20003-…` |
| TOUCH (notify) | `0cd20004-…` |
| TRACK (write) | `0cd20005-…` |
| OTA (write) | `0cd20006-…` |

**CMD text messages** (fields separated by `0x1F`):

| Message | Meaning |
|---|---|
| `W` `A` `D` `O` `Y` (1 byte) | LED: pulsing white / orange / green / off (Claude and Lightroom combined, "busy wins"). `Y` = flashing green / orange: Claude finished with a question for you (the app's next-step box); the helper sends `D` 30 s later, or the next letter sooner |
| `N<title>␟<artist>␟<app>␟<spin 0/1>` | New track. ASCII only. `spin=0` for browser videos. `app` is one of the Screen Designer's names (Spotify, YouTube, YouTube Music, Chrome, Edge, Firefox, VLC, Apple Music, Netflix...) |
| `P<playing 0/1>␟<position ms>␟<duration ms>` | Progress. Sent on play/pause, seeks, and every 5 s; the board interpolates in between |
| `V<volume 0-100>␟<muted 0/1>` | Master volume. The first one after connecting isn't a change; later changes count as "volume being changed" for 1.5 s |
| `X` | Nothing playing (paused 30 s, or nothing in the media flyout) |
| `T<app>␟<title>␟<message>␟<count>␟<HH:MM>` | Phone notification (Phone Link). ASCII, message ≤ 120 chars. Repeats come again with the new count. Counts as "notification arrives" for 8 s |
| `F<week>␟<your team>␟<opponent>␟<your score>␟<their score>␟<your proj>␟<their proj>␟<record>␟<rank>␟<live 0/1>` | ESPN fantasy basketball matchup (head-to-head points; projections 0 when ESPN gives none). Every minute while NBA games are on, every 10 min otherwise, and after every reconnect. "Live" puts the fantasy pages (`fantasy_screens.h`) on the screens |
| `R<position>␟<laps done>␟<lap s>␟<best s>␟<last s>␟<class>␟<PI>␟<top km/h>` | Forza's race info for the right screen while a sim frame has flag 4 (Forza sends no track outline, so no minimap). Position 0 = free roam. 4 a second while driving |
| `L<streak>␟<points for>␟<their record>␟<their place>` then `␟<place>␟<team>␟<record>` per row | The season around the matchup: your streak ("W3"), points for, the opponent's record and place, and the standings shown (the top 5, or the top 4 and you). Sent with `F` when it changes |
| `K<hour>␟<minute>␟<second>␟<date>␟<day number>` | The time (24-hour), date ("Tue 27 Oct") and day number (days since year 1, Python's `toordinal()`; picks the fantasy style of the day); the board keeps it ticking from `millis()`. Sent every minute and after every reconnect |
| `U<status W/A/D/O>␟<session ms>␟<tokens>␟<session %>␟<weekly %>` | Claude's own status (not mixed with Lightroom), how long the session has run, tokens used (input + output + cache writes), plan usage (-1 = unknown). Sent when it changes and every minute |

| `J<what>␟<target>` | What Claude is doing ("Editing", "notes.md"), from the hooks. `J` alone clears it. Shown on the Claude screens while its status is `W` |
| `?<title>␟<text>` | Claude's question ("NEEDS YOU" / "ASKS"). `?` alone clears it. A card on the right screen (`cs::askCard`) |
| `M<document>␟<step>␟<steps done>␟<recent>␟<recent>␟<recent>` | Claude building in SolidWorks. The pages (`cs::swLeft` / `swRight`, scene 50 + 1 notification / + 2 volume) stay `SW_SHOW_MS` after the last one. A new document drops the old picture |

**CMD binary messages** (racing sim, little-endian, see `SimCar` / `SimFrame`): `G<car>` starts a
session, `S<frame>` is telemetry (~30 Hz), `Q` ends it. The game sends them to the helper on UDP
47801 and the helper forwards them.

**IMG**: the cover as a 240×240 **baseline** JPEG (~10 KB): `B` + uint32 little-endian length,
then `C` + data chunks (MTU-sized, written with response, in order), then `E`. Decoded into
`cover` (RGB565 in PSRAM) by JPEGDEC. The SolidWorks stream comes the same way with `M` in place of
`B` and goes to `modelPic`, written without responses at about 5 frames a second; one picture at a time
(`image_lock` in the helper).

**OTA**: a firmware image: `B` + uint32 little-endian size + 32-byte HMAC-SHA256 of the image (key in
`ota_key.h` / `ota_key.txt`), then `C` + data chunks, then `E`. It's held in PSRAM until complete and
signed, then written to the other app slot. The board answers on TOUCH before restarting.

**TRACK**: the minimap outline, sent like the cover: `B<u16 main points, u16 pit points, f32 metres
per unit, f32 metres per point>`, `C<int16 x, y pairs...>`, `E`.

**TOUCH notifications** (1 byte): `p` play/pause, `n` next, `b` previous (not bound to a gesture
yet), `+` / `-` volume up/down by 4%, `m` mute / unmute (both sensors at once). Not touches: `u` / `x`,
a firmware update installed / refused.

## Requirements / gotchas

- **OPI PSRAM must be enabled**: the cover, the JPEG buffer, both canvases, what each screen shows
  and the sim backgrounds (about 1 MB) live there. The sketch halts with a message on the right
  screen if PSRAM is missing.
- **Partition scheme**: `app3M_fat9M_16MB`, two 3 MB app slots (BLE + JPEGDEC + GFX + the scenes' fonts
  don't fit the default, and wireless updates need the second slot).
- BLE callbacks run on the BLE task: they only queue text (`msgQueue`) or copy JPEG / track bytes;
  all drawing happens in `loop()`. Keep it that way when merging.
- Arduino-ESP32 3.x: `getValue()` returns `String`. `BLE2902` is only added without NimBLE (NimBLE
  adds the notify descriptor itself). The LED goes through `rgbLedWrite` (core 3.3.12).
- Pins in use: 4, 5 (touch), 7, 9–12, 14–16 (screens), 13 (MISO, claimed by the shared bus,
  nothing connected), 48 (LED). Free: 1, 2, 6, 8, 17, 18, 21, 38–42, 47.
- The PC helper reconnects automatically and resends the LED colour, track, cover, progress,
  volume, fantasy matchup, clock and Claude info after every reconnect, so the board never needs
  to store anything.
