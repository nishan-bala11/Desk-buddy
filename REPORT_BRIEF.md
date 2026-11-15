# Desk Buddy: facts for a project report

Instructions for whoever writes the report: use only the facts below. Where something is listed under
"Unknown", say it's unknown rather than estimating. Keep the difference between "measured", "tested once" and
"not tested". Nothing here covers the report's audience, length or format, so ask the owner about those.

## What it is

Desk Buddy is a small desk gadget with two round screens that act as a pair of animated eyes and as live status
displays. An ESP32-S3 board runs the firmware. A Python helper on a Windows PC feeds it data over Bluetooth Low
Energy (BLE). An iPhone can also connect to the board directly.

It began as a friend's kit. The owner's version was then given its own Bluetooth identity and extended. The
firmware and helper features described here were developed with Claude Code, mostly between 2026-10-27 and
2026-10-31.

## Parts

| Part | Details |
|---|---|
| Controller | ESP32-S3 N16R8 dev board (16 MB flash, 8 MB OPI PSRAM). Module: "ESP32S3 Dev Module" in the Arduino IDE |
| Screens | 2 x GC9A01 round LCD, 240 x 240 pixels, no backlight pins used |
| Touch | 2 x TTP223 capacitive touch sensors |
| Light | RGB LED built into the board (GPIO 48) |
| USB serial | CH343 chip, used for flashing and debugging |
| Optional, not fitted | SW420 vibration sensor (code supports it, disabled with `VIB_PIN` -1) |
| PC | Windows 11 Home laptop with MediaTek MT7921 Bluetooth |
| Phone | iPhone |

Wiring:
- Shared SPI bus: SCK 12, MOSI 11. MISO 13 is claimed by the bus but not connected.
- Left screen: CS 10, DC 9, RST 14.
- Right screen: CS 16, DC 15, RST 7.
- Touch: left 4, right 5.
- SPI runs at 40 MHz.

## Features

- **Eyes:** idle animation that blinks on touch. Eye-based scenes run at about 25 fps after optimisation (about 10 before).
- **Music and media:** anything in the Windows media controls shows on the screens, with album art spinning like a
  vinyl record, title, artist, progress and volume. Touch controls play/pause, next and volume.
- **20 designed scenes:** made in a separate Screen Designer tool and chosen by context (music, time of day and so on).
- **iPhone notifications:** app, sender and message on the screen, sent straight from the phone to the board.
- **Claude Code status:** session time, tokens, plan usage, the current step, and Claude's question when it needs an answer.
- **Fantasy basketball:** ESPN head-to-head points league, with three visual styles (Jumbotron, Neon, Court), one per day.
- **Racing:** live gauges and a minimap for the owner's own racing sim, plus Forza Horizon 4 / 5 and Motorsport 7 telemetry.
- **SolidWorks:** a live picture of the model on the left screen while Claude builds it, with step information on the right.
- **Wireless firmware updates:** signed updates sent over Bluetooth, no USB cable.

## Software and libraries

Firmware:
- Arduino framework, Espressif "esp32" board package 3.3.12
- GFX Library for Arduino (moononournation) 1.6.9: drives the screens
- JPEGDEC (Larry Bank) 1.8.4: decodes album art and model pictures
- Included with the ESP32 package: BLE library, NimBLE host, Update / OTA functions, mbedTLS (HMAC-SHA256)
- Build setting: 16 MB flash, `app3M_fat9M_16MB` partitions (two 3 MB app slots), OPI PSRAM

PC helper:
- Python 3.12
- bleak 3.0.2: Bluetooth
- Pillow 12.3.0: image work
- psutil 7.2.2: finding processes
- pycaw (20260927) and comtypes 1.4.17: Windows volume
- winrt packages 3.2.1: Windows media session information
- PowerShell scripts: Claude Code hooks, SolidWorks capture, firmware update
- arduino-cli bundled with the Arduino IDE: compiling

## How the libraries and methods were chosen

- **GFX Library and JPEGDEC:** these came with the existing kit and its documented install list. The working record
  doesn't show a comparison of alternatives, so don't claim one. Exact versions were read from the installed
  libraries' `library.properties` files.
- **BLE and security functions:** these ship with the ESP32 board package, so no extra library was needed. Other
  libraries are installed on the PC, including BLEOTA, but this sketch doesn't include them.
- **Wireless updates:** custom-built because the update had to be signed and held in PSRAM until verified.
- **Confirming behaviour:** where it mattered, library source code and the package's build configuration were read
  directly. For example, the configuration allows 3 BLE connections and 3 bonds, and `BLEServer.cpp` shows when
  its connection count changes.
- **iPhone notifications:** these use Apple Notification Center Service (ANCS), Apple's Bluetooth notification protocol.
- **Trial and measurement:** the SolidWorks method came from testing what worked:
  - `SaveAs3` quit Claude's open sketch, so it was rejected.
  - `PrintWindow` returned a black picture because the model is drawn with OpenGL.
  - `SaveBMP` was safe during a sketch and managed 33 frames a second, so it was used.
  - PowerShell's normal SolidWorks calls failed, so calls go through `InvokeMember`.

## How data moves

- **Claude Code to helper:** hooks send events over local TCP port 47800.
- **Spotify and other media to helper:** the desktop app reports what's playing to Windows' media controls, and the
  helper checks those controls about every 0.5 s. It reads the title, artist, position and album art there, so it
  doesn't use a Spotify account or the Spotify API. Browsers and VLC work the same way.
- **Album art to board:** the helper makes a 240 x 240 JPEG (quality 80) and sends it over BLE, where JPEGDEC decodes it.
- **Touch back to media:** the board sends touches to the helper over BLE. The helper uses the same Windows controls for
  play/pause, next and previous, and changes the volume on the PC's audio output through pycaw.
- **Racing sim to helper:** UDP port 47801. Forza Data Out uses UDP port 5300.
- **Helper to board:** BLE characteristics for commands, images, touch, track data and firmware. Negotiated packet size is 517.
- **iPhone to board:** a direct bonded BLE connection using ANCS.
- **SolidWorks:** a long-running PowerShell process saves a picture on request. Python removes the background, then
  sends a JPEG (quality 60) over BLE.

## Measurements

| Item | Result |
|---|---|
| SolidWorks stream, simple spinning part | About 5 frames a second (151 frames in 30 s, on battery) |
| SolidWorks stream, real builds | Roughly 1 to 2 frames a second (SolidWorks' drawing time is the limit) |
| Per-frame cost, simple part | SolidWorks 0.05 s, background removal 0.125 s, Bluetooth 0.03 s |
| Firmware update | 848 KB sent in 151 to 162 s, installed in 3 to 4 s |
| Firmware size | 848,599 bytes, 26% of the 3 MB app slot |
| RAM | 64,068 bytes of global variables, 19% of internal RAM |
| Full compile | About 1.5 min on charger, over 10 min on battery |

## Limitations

Screens and Bluetooth:
- BLE bandwidth and the shared SPI bus limit picture quality and frame rate.
- SolidWorks frames are sent without acknowledgement, so frames can be lost. The loss rate hasn't been counted.
- Screen text is plain ASCII: emoji are dropped and accented letters are simplified.
- Phone Link notifications are limited to 120 characters. It's only a fallback, and it passes on only some apps.

Windows and Claude dependence:
- The helper is Windows only and must be running for everything except iPhone notifications and the eyes.
- Claude status and SolidWorks streaming work with Claude Code only, because they rely on its hooks.
- Plan usage percentages rely on the Claude desktop app's cached samples or the terminal status line, and can go stale.

SolidWorks:
- A hand change while Claude is working also brings up the stream.
- Step text can come from the wrong session or from an unrelated command.
- The view isn't turned automatically for script-based builds.

iPhone:
- Pairing is required once.
- If the phone stays connected but Apple's service goes quiet, the board can't detect it.
- The phone must reconnect itself, because the board can't call it back. On 2026-10-31 the link dropped repeatedly
  and then ended at 17:16. The phone stayed away for 18 hours, even with the board advertising, and a board restart
  didn't bring it back. It returned at about 11:21 on 2026-11-01. Neither the cause nor what brought it back is known.

Fantasy and games:
- ESPN gives this league no projections, so the win-chance page doesn't show.
- A private league needs the owner's ESPN cookies.
- Forza gives no shift points, so the shift light uses 75% and 92% of the rev limit.
- The Microsoft Store version of Forza Horizon 4 would need a Windows loopback exemption. The owner's copy is on Steam.

Security:
- Firmware updates are signed with a shared secret key (HMAC-SHA256), and that key is stored on the board and the PC.
- Normal BLE commands aren't authenticated. The helper finds the board by name, with no pairing. A friend's laptop
  once connected to this board by accident when it still had the kit's IDs, which is why it now has unique ones.
- The project documents no secure boot or flash encryption.

Update safety:
- The stock bootloader has no rollback, so the firmware does it itself: 3 boots that fail to reach 60 s return to
  the old slot. The counter is lost on a power cut.

## Problems found and fixed

- Touch sensors flicker, which turned volume holds into stray taps. Fixed with a 300 ms release debounce.
  About 75 dropouts of 60 to 185 ms were measured in 6 minutes of holds.
- The SolidWorks stream dropped out because it depended on tool names, then on words in commands. It now watches the
  model for changes and holds the pages through quiet spells.
- A very long save path made SolidWorks silently write nothing. Pictures now go in the temp folder.
- Background removal by colour failed on SolidWorks' gradient background. It now floods from the corners and stops at
  sharp edges.
- On 2026-10-31 iPhone notifications stopped. Neither scan heard the board advertising. The exact cause is unknown
  because the old firmware had no logging, and the restart itself may have cleared it. Two fixes went in: the board
  retries a returning iPhone instead of leaving it connected but idle, and it restarts advertising if that's off.
  iPhone status now goes to the helper's log.

## Test status

Confirmed:
- The four Claude and SolidWorks features were seen working on the real board.
- Both question cards from real Claude turns (2026-11-13): "NEEDS YOU" with the LED orange while Claude
  waited on a question, and "ASKS" with the green / orange flash when a turn ended with one.
- A wrong-key firmware image and signed garbage were both refused, and the board kept running.
- After the iPhone fix, the log shows it reconnecting by itself (once in 3 seconds on 2026-10-31) and real
  notifications being received and shown between 16:09 and 17:08 that day. Notifications after 17:16 came through
  the Phone Link fallback, so they don't count as evidence for the direct route.

Not tested:
- Rollback with a firmware build that really crashes.
- The SolidWorks hold through a long quiet spell.
- Switching back and forth between two SolidWorks copies (one switch was seen).
- SPI above 40 MHz, or at 27 MHz.

## Unknown

- Total parts cost, supplier and exact board brand
- Power draw and how the board is powered day to day
- Enclosure design and physical size
- Long-term reliability
- Why these display and JPEG libraries were originally picked over others
- Who the report is for
