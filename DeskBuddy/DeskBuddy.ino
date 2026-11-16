/*
  DeskBuddy - ESP32-S3 N16R8 + 2x GC9A01 (240x240 round) + 2 touch sensors + onboard RGB LED
  ---------------------------------------------------------------------------------------------
  Merged from gc9a01_eyes_s3_v3 (shared SPI bus, no BL pins), claude_status_led and desk_buddy.

  What it does
    - The screens show the scenes designed in the Desk Buddy Screen Designer (buddy_screens.h,
      20 scenes): buddyPickScene() picks one from what's happening - music playing or paused,
      volume changing, a phone notification, Claude's status, the time of day.
        "Idle eyes" (nothing else going on): two eyes that wander and blink when you touch the
        sensors. With an SW420 vibration sensor fitted (VIB_PIN), bumping the desk makes the
        irises shake, then roll around dizzily.
        touch while music is playing or paused: tap left = play/pause, tap right = next,
        hold left/right = volume down/up
        both sensors at once (any time but racing): mute / unmute
      Regenerate buddy_screens.h in the designer and re-upload to change the screens.
    - RGB LED (GPIO 48): Claude Code / Lightroom status from the PC helper
        pulsing white = working, orange = needs you, green = done, off = Claude closed,
        flashing green / orange = Claude finished and asked you something (30 s, then green)
    - Racing sim (Nishan Sim, while you drive):
        left screen  = turbo boost gauge (turbo cars) or tachometer (the rest), with the gear
        right screen = the game's minimap: heading-up, zooming, the stretch ahead highlighted
        RGB LED      = shift light: green, yellow, orange, red, flashing red at the shift point
        The session ending (or 3 s without data) goes back to the music or the eyes.

  Libraries (Library Manager):
    "GFX Library for Arduino" by moononournation
    "JPEGDEC" by Larry Bank
    BLE comes with the esp32 core.

  Arduino IDE, Tools menu (esp32 core by Espressif):
    Board            : ESP32S3 Dev Module
    Flash Size       : 16MB (128Mb)
    PSRAM            : OPI PSRAM          <-- REQUIRED (cover art + screen buffer live there)
    Partition Scheme : Huge APP (3MB No OTA/1MB SPIFFS)   (BLE needs the space)
    USB CDC On Boot  : Enabled  -> Serial over the native "USB" port
                       Disabled -> Serial over the "COM"/UART port

  Both displays share SCL and SDA (one SPI bus); each has its own CS, DC
  and RST, so the sketch talks to one at a time.

  LEFT display -> ESP32-S3:
    VCC -> 3.3V      GND -> GND
    SCL -> GPIO 12   SDA -> GPIO 11   (shared with right display)
    CS  -> GPIO 10   DC  -> GPIO 9
    RST -> GPIO 14

  RIGHT display -> ESP32-S3:
    VCC -> 3.3V      GND -> GND
    SCL -> GPIO 12   SDA -> GPIO 11   (shared with left display)
    CS  -> GPIO 16   DC  -> GPIO 15
    RST -> GPIO 7

  Buttons (2-pin push buttons, either way round; the pins' internal pull-ups, no resistors):
    Left  button: GPIO 4 -> button -> GND
    Right button: GPIO 5 -> button -> GND
  (The TTP223 touch sensors these replaced gave ghost touches in the case. To go back to them:
   TOUCH_ACTIVE HIGH and pinMode INPUT, with VCC -> 3.3V, GND -> GND, SIG -> GPIO 4 / 5.)

  Vibration sensor (SW420 module: VCC / GND / DO): none on this buddy (VIB_PIN -1). To add one:
    VCC -> 3.3V (not 5V - DO would then put 5V on the pin), GND -> GND, DO -> a free pin such as
    GPIO 2, and set VIB_PIN to it. Its blue potentiometer sets the sensitivity; VIB_TRIGGER below
    fine-tunes it in software.

  RGB LED: onboard WS2812 on GPIO 48 (some boards use 38 - change LED_PIN).

  If you remap anything, avoid these on an N16R8:
    35, 36, 37    on the header, but wired to the octal PSRAM
    0, 3, 45, 46  boot strapping pins
    19, 20        native USB D- / D+
    43, 44        UART0 TX / RX (the COM port)
    38 or 48      RGB LED on most boards (which one depends on the board)
    13            SPI MISO (claimed by the bus, nothing connected)
    (22-25 don't exist on the S3, and 26-34 aren't broken out.)

  Bluetooth (the PC helper claude-led-ble.py connects by name; both must match):
    Device "Desk Buddy 0A69", service 0cd20001-355a-4a08-8be1-4e7212f9c170
      ...0002 CMD   (write)  : W/A/D/O/Y = LED status (Y = flashing green / orange)
                               N<title>\x1f<artist>\x1f<app>\x1f<spin 0/1> = now playing
                               P<playing 0/1>\x1f<pos ms>\x1f<duration ms> = progress
                               V<volume 0-100>\x1f<muted 0/1>             = volume
                               X = nothing playing (back to the eyes)
                               T<app>\x1f<title>\x1f<message>\x1f<count>\x1f<HH:MM> = phone notification
                               F<week>\x1f<team>\x1f<opponent>\x1f<score>\x1f<their score>\x1f<proj>
                                \x1f<their proj>\x1f<record>\x1f<rank>\x1f<live 0/1> = ESPN fantasy matchup
                               L<streak>\x1f<points for>\x1f<their record>\x1f<their place>, then
                                \x1f<place>\x1f<team>\x1f<record> for up to 5 teams = the standings
                                (fantasy_screens.h)
                               K<hour>\x1f<minute>\x1f<second>\x1f<date>\x1f<day number> = the time (the board
                                has no clock); the day number picks the fantasy style of the day
                               U<status W/A/D/O>\x1f<session ms>\x1f<tokens>\x1f<session %>\x1f<weekly %>
                                = Claude: its own status (not mixed with Lightroom) and usage (-1 = unknown)
      ...0003 IMG   (write)  : B<uint32 length> / C<jpeg bytes>... / E  = 240x240 cover JPEG
      ...0004 TOUCH (notify) : p = play/pause, n = next, + / - = volume up/down, m = mute / unmute
      ...0005 TRACK (write)  : B<u16 main, u16 pit, f32 m/unit, f32 m/point> / C<int16 x,y...> / E
                               = racing sim minimap outline
    Racing sim on CMD (binary, little-endian; see SimCar / SimFrame):
      G<car> = start a session   S<frame> = telemetry (~30 Hz)   Q = session over
      R<position>\x1f<laps done>\x1f<lap s>\x1f<best s>\x1f<last s>\x1f<class>\x1f<PI>\x1f<top km/h> (text)
        = lap / position for the right screen when a frame has flag 4 (Forza, no minimap)
    USB serial still accepts W/A/D/O/Y for the LED.

  Drawing: the "Idle eyes" scene uses the sketch's own eyes, which redraw only what changed (lid
  edges, iris box) in small strips. Every other scene is drawn into two canvases (PSRAM) about 30
  times a second, and a screen is only sent when its picture actually changed. BLE callbacks only
  queue data, and all drawing happens in loop(). Nothing in loop() blocks.
*/

#include <Arduino_GFX_Library.h>
#include "buddy_screens.h"
#include "fantasy_screens.h"   // fantasy basketball pages, made by hand (not from the Screen Designer)
#include "claude_screens.h"    // Claude's current step and question, the SolidWorks pages, made by hand too
#include "ota_key.h"           // signs wireless firmware updates
#include <JPEGDEC.h>
#include <Update.h>
#include <esp_ota_ops.h>
#include <mbedtls/md.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
#include <BLESecurity.h>
#if defined(CONFIG_NIMBLE_ENABLED)
#include <host/ble_hs.h>   // iPhone notifications (ANCS) talk to NimBLE directly
#endif

// Types up here, before any function, so the Arduino IDE's generated prototypes can see them.
enum LidState { OPEN, CLOSING, CLOSED, OPENING };
enum Mode { MODE_EYES, MODE_SCENE, MODE_SIM };   // the fast eyes, a designed scene, the racing sim
enum VibState { VIB_IDLE, VIB_SHAKING, VIB_DIZZY };

// Racing sim messages, exactly as game/deskbuddy.py packs them
struct __attribute__((packed)) SimCar {
  uint8_t turbo;
  float rpmMax, shiftStart, shiftEnd, limiter;
  float gaugeMin, gaugeMax;   // boost in bar (turbo) or rpm (tacho)
};

struct __attribute__((packed)) SimFrame {
  float rpm, boost;           // boost: bar above ambient
  int8_t gear;                // -1 R, 0 N
  uint16_t kmh;
  float x, y;                 // m, same origin as the track points
  float heading;              // map rotation (rad)
  float marker;               // car arrow angle on screen (rad, clockwise)
  float radius;               // visible radius (m)
  float s, ahead;             // m along the lap, highlighted look-ahead (m)
  uint8_t flags;              // 1 = in the pit lane, 2 = paused, 4 = no map: lap / position screen (Forza)
};

// Lap and position for the right screen in place of the minimap (Forza), from the "R" message
struct RaceInfo {
  uint8_t pos;                // race position, 0 = not racing (free roam)
  uint16_t lap;               // laps done (the one being driven is lap + 1)
  float cur, best, last;      // lap times (s), 0 = none yet
  char cls[4];                // the car's class ("A", "S1"...) and performance index
  uint16_t pi;
  uint16_t top;               // top speed this drive (km/h)
};

struct Eye {
  Arduino_GFX *gfx;
  int pin;
  LidState state;
  float lid;          // 0 = open, 1 = closed
  float drawnLid;
  float drawnGX, drawnGY;
  bool lastTouch;
  uint32_t closedAt;
  float ox, oy;       // shake / dizzy offset added to the shared gaze
};

struct Touch {
  int pin;
  bool down;
  bool held;          // became a hold (volume repeat) or part of a mute, so no tap on release
  bool volume;        // this press changed the volume
  bool wasTouched;    // the previous reading
  uint32_t downAt;
  uint32_t lastRepeat;
  uint32_t touchedAt;     // last time the sensor read touched; the press ends TOUCH_RELEASE_MS after it
  uint32_t volumeEndAt;   // when the last volume hold ended (0 = none yet)
};

struct Msg { uint16_t len; char data[250]; };

// ---------------- Pins: shared SPI bus ----------------
#define SPI_SCK   12
#define SPI_MOSI  11
#define SPI_MISO  13   // not wired; set explicitly so the core doesn't pick a pin

// ---------------- Pins: left display ----------------
#define L_CS    10
#define L_DC    9
#define L_RST   14

// ---------------- Pins: right display ----------------
#define R_CS    16
#define R_DC    15
#define R_RST   7

// ---------------- Pins: touch + LED ----------------
#define TOUCH_LEFT_PIN   4
#define TOUCH_RIGHT_PIN  5
#define TOUCH_ACTIVE     LOW    // buttons to GND: pressed pulls the pin LOW (the pull-up holds it HIGH)
#define LED_PIN          48     // onboard RGB LED (38 on some boards)
#define VIB_PIN          -1     // SW420 vibration sensor DO; -1 = none fitted (this buddy has none)

// ---------------- Display options ----------------
const int32_t SPI_HZ = 40000000;  // try 80000000 for a smoother vinyl; 27000000 if you see glitches
#define L_ROTATION 0              // 0-3, change if a display is mounted rotated
#define R_ROTATION 0

// ---------------- Bluetooth ----------------
#define DEVICE_NAME  "Desk Buddy 0A69"   // must match DEVICE_NAME in claude-led-ble.py
#define SERVICE_UUID "0cd20001-355a-4a08-8be1-4e7212f9c170"
#define CMD_UUID     "0cd20002-355a-4a08-8be1-4e7212f9c170"
#define IMG_UUID     "0cd20003-355a-4a08-8be1-4e7212f9c170"
#define TOUCH_UUID   "0cd20004-355a-4a08-8be1-4e7212f9c170"
#define TRACK_UUID   "0cd20005-355a-4a08-8be1-4e7212f9c170"
#define OTA_UUID     "0cd20006-355a-4a08-8be1-4e7212f9c170"

// ---------------- Behaviour ----------------
const bool HOLD_TO_CLOSE = true;   // keep the eye shut while you hold the sensor
const bool EYES_WANDER   = true;   // pupils glance around on their own

const float    CLOSE_MS = 70.0f;   // time for lid to close
const float    OPEN_MS  = 120.0f;  // time for lid to open
const uint32_t HOLD_MS  = 60;      // minimum time fully closed
const uint32_t FRAME_MS = 16;      // ~60 fps cap

const float    VINYL_RPM        = 20.0f;  // spin speed of the cover (a real record is 33.3)
const uint32_t TAP_MAX_MS       = 450;    // touch shorter than this = tap
const uint32_t TAP_MIN_MS       = 40;     // touch shorter than this = a glitch, not a tap
const uint32_t TOUCH_RELEASE_MS = 300;    // let go for less than this = the sensor flickering, the press goes on
const uint32_t TOUCH_CONFIRM_MS = 30;     // a button must read pressed this long before it counts (contact bounce and spikes are shorter)
const uint32_t AFTER_VOLUME_MS  = 1000;   // after a volume hold, touches can't pause or skip for this long
const uint32_t VOLUME_REPEAT_MS = 180;    // while holding: one volume step this often
const uint32_t VOLUME_SHOW_MS   = 1500;   // how long a volume change counts as "volume being changed"
const uint32_t NOTIF_SHOW_MS    = 8000;   // how long a phone notification counts as arriving
const uint32_t SCENE_FRAME_MS   = 33;     // designed scenes: drawn ~30 times a second
const uint32_t CLAUDE_DONE_SHOW_MS = 60000;   // after Claude finishes, its scenes stay this long, then the eyes
const uint32_t FANTASY_PAGE_MS  = 8000;   // during NBA games: each fantasy page stays this long
const uint32_t FANTASY_HOLD_MS  = 30000;  // and one picked with a tap on a sensor this long
const uint32_t SW_SHOW_MS       = 120000; // the SolidWorks pages stay this long after Claude's last step
const uint32_t ASK_DRIVING_MS   = 8000;   // while driving, Claude's question takes the right screen this long
const uint32_t OTA_MAX          = 0x300000;   // a firmware update can't be bigger than the app partition
const uint32_t OTA_QUIET_MS     = 15000;  // no firmware data this long: the update was dropped
const uint32_t OTA_HEALTHY_MS   = 60000;  // new firmware running this long counts as good

// Vibration: the irises shake while it's vibrating, then roll around dizzily (eyes mode only)
const float    VIB_TRIGGER = 25.0f;   // sensor edges (decaying count) that count as a shake; raise if too touchy
const float    VIB_DECAY_MS = 300.0f; // how fast that count fades: taps fade out, sustained shaking adds up
const uint32_t VIB_HOLD_MS = 250;     // shaking lasts this long after the last edge
const uint32_t DIZZY_MS    = 3500;    // dizzy spell after the shaking stops
const float    SHAKE_PX    = 10.0f;   // iris jitter while shaking
const float    DIZZY_R     = 32.0f;   // radius of the dizzy circles (px)
const float    DIZZY_RPS   = 1.6f;    // dizzy circles per second at the start (slows as it wears off)
const float    DIZZY_DROOP = 0.3f;    // lids sag this far while dizzy (0 = open, 1 = shut)

// Racing sim
const uint32_t SIM_TIMEOUT_MS = 3000; // no telemetry this long -> back to the music / eyes
const uint32_t SHIFT_FLASH_MS = 60;   // flashing red: on / off this long each
const float    MAP_ANCHOR     = 0.30f; // car sits this far below the centre (fraction of the radius), as in the game
const int      MAP_R          = 116;  // minimap disc radius (px)

// ---------------- Geometry (full-screen eye) ----------------
#define SCR 240
const float CX = SCR / 2 - 0.5f;   // pixel-centre of the screen
const float CY = SCR / 2 - 0.5f;

const float EYE_R     = 118.0f;    // eyeball fills the round panel
const float OUTLINE   = 6.0f;
const float IRIS_R    = 60.0f;
const float IRIS_RIM  = 10.0f;     // dark ring at the iris edge
const float PUPIL_R   = 28.0f;
const float LASH_U    = 7.0f;      // upper lash thickness
const float LASH_L    = 5.0f;      // lower lash thickness

const int   GAZE_X    = 30;        // how far the iris wanders (px)
const int   GAZE_Y    = 20;

const float SHINE1_X = -22, SHINE1_Y = -22, SHINE1_R = 12;   // relative to iris centre
const float SHINE2_X =  17, SHINE2_Y =  17, SHINE2_R = 6;

const float EYE_R2     = EYE_R * EYE_R;
const float OUTLINE_R2 = (EYE_R - OUTLINE) * (EYE_R - OUTLINE);
const float IRIS_R2    = IRIS_R * IRIS_R;
const float IRIS_IN2   = (IRIS_R - IRIS_RIM) * (IRIS_R - IRIS_RIM);
const float PUPIL_R2   = PUPIL_R * PUPIL_R;

// ---------------- Colours ----------------
#ifndef RGB565   // Arduino_GFX already defines the same macro
#define RGB565(r, g, b) ((uint16_t)((((r) & 0xF8) << 8) | (((g) & 0xFC) << 3) | ((b) >> 3)))
#endif
const uint16_t COL_BG        = RGB565(0, 0, 0);
const uint16_t COL_OUTLINE   = RGB565(40, 40, 50);
const uint16_t COL_SCLERA    = RGB565(235, 235, 240);
const uint16_t COL_IRIS      = RGB565(40, 140, 220);
const uint16_t COL_IRIS_DARK = RGB565(20, 70, 130);
const uint16_t COL_PUPIL     = RGB565(5, 5, 10);
const uint16_t COL_SHINE     = RGB565(255, 255, 255);
const uint16_t COL_LID       = RGB565(120, 70, 90);
const uint16_t COL_LASH      = RGB565(30, 15, 20);

const uint16_t COL_TRACK    = RGB565(40, 40, 48);
const uint16_t COL_TEXT      = RGB565(235, 235, 240);
const uint16_t COL_DIM       = RGB565(140, 140, 150);

// ---------------- Displays ----------------
// Arduino_HWSPI goes through the Arduino SPI class, which is built for
// several devices sharing one bus, each with its own CS.
Arduino_DataBus *busL = new Arduino_HWSPI(L_DC, L_CS, SPI_SCK, SPI_MOSI, SPI_MISO, &SPI, true);
Arduino_DataBus *busR = new Arduino_HWSPI(R_DC, R_CS, SPI_SCK, SPI_MOSI, SPI_MISO, &SPI, true);
Arduino_GFX *gfxL = new Arduino_GC9A01(busL, L_RST, L_ROTATION, true /* IPS */);
Arduino_GFX *gfxR = new Arduino_GC9A01(busR, R_RST, R_ROTATION, true /* IPS */);
Arduino_Canvas *leftCanvas = nullptr;    // left screen for the scenes and the sim (framebuffer in PSRAM)
Arduino_Canvas *rightCanvas = nullptr;   // right screen, the same

// Strip buffer shared by both screens: up to 24 full-width rows (~11 KB, internal RAM)
#define STRIP_PIXELS (SCR * 24)
static uint16_t strip[STRIP_PIXELS];

// ---------------- Eye state ----------------
Eye leftEye  = { nullptr, TOUCH_LEFT_PIN,  OPEN, 0, 0, 0, 0, false, 0 };
Eye rightEye = { nullptr, TOUCH_RIGHT_PIN, OPEN, 0, 0, 0, 0, false, 0 };

float gazeX = 0, gazeY = 0, targetX = 0, targetY = 0;
uint32_t nextGazeAt = 0;
uint32_t lastFrame = 0;

// ---------------- Vibration state ----------------
volatile uint32_t vibEdges = 0;            // counted by the pin interrupt
float vibLevel = 0;                        // decaying edge count
VibState vibState = VIB_IDLE;
uint32_t lastVibAt = 0, dizzyAt = 0;
float dizzyPhase = 0;
float droop = 0;                           // lid sag shared by both eyes

// ---------------- Media state ----------------
Mode mode = MODE_EYES;
char mTitle[64] = "", mArtist[48] = "", mApp[20] = "";
bool mSpin = true;
bool mPlaying = false;
uint32_t mPosMs = 0, mDurMs = 0, mPosAt = 0;   // position mPosMs was true at millis() == mPosAt
int  mVolume = -1;
bool mMuted = false;
uint32_t volumeShownAt = 0;                // 0 = no change yet
bool mediaActive = false;                  // something playing or paused (N ... X)

uint16_t *cover = nullptr;                 // 240x240 RGB565, PSRAM
bool coverValid = false;
float vinylAngle = 0;                      // radians

// Incoming cover JPEG (written by the BLE task, decoded in loop)
const uint32_t JPG_MAX = 96 * 1024;
uint8_t *jpgBuf = nullptr;                 // PSRAM
volatile uint32_t jpgLen = 0, jpgExpected = 0;
volatile bool jpgReady = false;
volatile bool jpgIsModel = false;          // the picture coming in is the SolidWorks model, not the cover
uint16_t *modelPic = nullptr;              // 240x240 RGB565, PSRAM
bool modelValid = false;

QueueHandle_t msgQueue;
JPEGDEC jpeg;

// ---------------- Scene state (buddy_screens.h) ----------------
int curScene = -1;                         // scene on the screens (-1 = none / not drawn yet)
bool sceneForce = true;                    // send both screens next draw, changed or not
uint32_t lastSceneDraw = 0;
uint16_t *shownL = nullptr, *shownR = nullptr;   // what each screen shows now (PSRAM)
uint8_t eyeSides = 0;    // screens the scene drew an eye on in its last frame (bit 0 left, bit 1 right)
uint8_t drawnEyes = 0;   // filled in by buddy::onEye while a frame is drawn
uint32_t statFrames = 0;                                     // printSceneStats(): frames where something moved
uint64_t statDrawUs = 0, statSendUs = 0, statPixels = 0;     // 64-bit: a scene can stay up for hours

// Phone notification (T)
char nApp[24] = "", nTitle[48] = "", nText[128] = "", nTime[8] = "";
uint16_t nCount = 1;
uint32_t notifUntil = 0;                   // millis() it stops counting as arriving (0 = none)
bool notifToReport = false;                // a new one: loop() says where it went, for the helper's log

// ESPN fantasy basketball (F; the standings "L" go to fantasy_screens.h)
uint8_t fWeek = 0, fRank = 0;
char fMyTeam[32] = "", fOppTeam[32] = "", fRecord[12] = "";
float fMyScore = 0, fOppScore = 0, fMyProj = 0, fOppProj = 0;
bool fLive = false;

// Clock (K) - kept ticking from millis() between messages
bool clockKnown = false;
uint32_t clockSec = 0, clockAt = 0;        // seconds after midnight at millis() == clockAt
char clockDate[24] = "";

// Claude (U): its own status and usage
char claudeStatus = 0;                     // 0 = no U message yet: use the LED letter
uint32_t claudeSessionMs = 0, claudeAt = 0, claudeTokens = 0;
uint8_t claudeSession = 0, claudeWeekly = 0;
bool claudeSessionKnown = false, claudeWeeklyKnown = false;   // the PC sends -1 when it doesn't know (shown as "--")

// ---------------- Racing sim state ----------------
SimCar simCar = {};
SimFrame simFrame = {};
bool simDirty = false;                     // a new frame to draw
uint32_t simLastAt = 0;
uint16_t *gaugeBg = nullptr;               // dial face without needle, drawn once per car (PSRAM)
uint16_t *mapBg = nullptr;                 // empty minimap disc (PSRAM)
float gaugeAngleShown = -1;                // needle angle on screen (skip redraws that change nothing)
int8_t gaugeGearShown = 99;
int gaugeKmhShown = -1;
RaceInfo race = {};                        // Forza's lap / position screen ("R"), and what it shows now
char raceShown[64] = "";

// Track outline (written by the BLE task, drawn in loop)
const uint32_t TRACK_MAX = 6000;           // points, circuit + pit lane
int16_t *trackPts = nullptr;               // x, y pairs in trackScale metres (PSRAM)
volatile uint16_t trackMain = 0, trackPit = 0;
volatile uint32_t trackBytes = 0, trackExpected = 0;
volatile bool trackReady = false;
float trackScale = 1.0f, trackStep = 10.0f;

// ---------------- RGB LED state ----------------
char ledState = 'O';
#define PULSE_MS 2000                     // white pulse: one full fade in + out
uint32_t lastPulse = 0;
#define ASK_FLASH_MS 500                  // Claude asked you something: green, then orange, this long each
uint32_t askPhase = UINT32_MAX;           // which half of that flash is showing (UINT32_MAX = none yet)

// ---------------- Touch state ----------------
Touch touchL = { TOUCH_LEFT_PIN,  false, false, false, false, 0, 0, 0, 0 };
Touch touchR = { TOUCH_RIGHT_PIN, false, false, false, false, 0, 0, 0, 0 };

// ---------------- Bluetooth ----------------
BLECharacteristic *touchChar = nullptr;
volatile bool bleConnected = false;
volatile bool restartAdvertising = false;   // set from the BLE task on disconnect
uint32_t advertiseAt = 0;                   // when to restart advertising (0 = not scheduled)

void ancsCheck(uint16_t conn);   // iPhone notifications, below
void ancsNote(const char *fmt, ...);
volatile bool iphoneDirect = false;   // the iPhone is sending its notifications to the buddy itself

class ServerCB : public BLEServerCallbacks {
  // After the first connection keep advertising, so the PC helper and the iPhone can both connect
  void onConnect(BLEServer *s) override {
    bleConnected = true;
    if (s->getConnectedCount() == 0) restartAdvertising = true;
  }
#if defined(CONFIG_NIMBLE_ENABLED)
  void onConnect(BLEServer *s, ble_gap_conn_desc *desc) override {
    ancsNote("Bluetooth: connected (%s address)", desc->peer_ota_addr.type == BLE_ADDR_PUBLIC ? "public" : "random");
    ancsCheck(desc->conn_handle);
  }
#endif
  void onDisconnect(BLEServer *s) override {
    bleConnected = s->getConnectedCount() > 0;
    restartAdvertising = true;
  }
};

// Text commands go through a queue so all drawing happens in loop().
class CmdCB : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *c) override {
    Msg m;
    m.len = min(c->getLength(), sizeof(m.data) - 1);
    memcpy(m.data, c->getData(), m.len);
    m.data[m.len] = 0;
    // While the iPhone sends its notifications here itself, the PC's copies from Phone Link would
    // show them twice (and Phone Link only passes on some apps anyway)
    if (m.data[0] == 'T' && iphoneDirect) return;
    if (m.len) xQueueSend(msgQueue, &m, 0);
  }
};

class ImgCB : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *c) override {
    const uint8_t *d = c->getData();   // the written value in place: no String copy per write
    size_t n = c->getLength();
    if (!n || !jpgBuf) return;
    if ((d[0] == 'B' || d[0] == 'M') && n >= 5) {   // B = album cover, M = the SolidWorks model
      uint32_t t0 = millis();
      while (jpgReady && millis() - t0 < 200) delay(2);   // previous cover still being decoded
      memcpy((void *)&jpgExpected, d + 1, 4);
      jpgIsModel = d[0] == 'M';
      jpgLen = 0;
    } else if (d[0] == 'C') {
      if (jpgLen + n - 1 <= JPG_MAX) {
        memcpy(jpgBuf + jpgLen, d + 1, n - 1);
        jpgLen += n - 1;
      }
    } else if (d[0] == 'E') {
      if (jpgLen > 0 && jpgLen == jpgExpected) jpgReady = true;
    }
  }
};

// A firmware update comes in whole to PSRAM (B<u32 size><32-byte signature>, C<data>..., E). Nothing
// touches the flash until all of it is here and its signature checks out, in otaInstall().
uint8_t *otaBuf = nullptr;
uint8_t otaSig[32];
volatile uint32_t otaSize = 0, otaGot = 0, otaLastAt = 0;
volatile uint8_t otaState = 0;   // 0 none, 1 receiving, 2 all here
const uint32_t OTA_TRIES_MAGIC = 0x0DA7A500;
RTC_NOINIT_ATTR uint32_t otaTries;   // after an update: boots so far, kept through crashes

class OtaCB : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *c) override {
    const uint8_t *d = c->getData();   // the written value in place: no String copy per write
    size_t n = c->getLength();
    if (!n) return;
    if (d[0] == 'B' && n == 37) {
      uint32_t size;
      memcpy(&size, d + 1, 4);
      if (!otaBuf) otaBuf = (uint8_t *)ps_malloc(OTA_MAX);
      if (!otaBuf || !size || size > OTA_MAX) return;
      memcpy(otaSig, d + 5, 32);
      otaSize = size;
      otaGot = 0;
      otaLastAt = millis();
      otaState = 1;
    } else if (d[0] == 'C' && otaState == 1) {
      if (otaGot + n - 1 <= otaSize) {
        memcpy(otaBuf + otaGot, d + 1, n - 1);
        otaGot += n - 1;
      }
      otaLastAt = millis();
    } else if (d[0] == 'E' && otaState == 1) {
      if (otaGot == otaSize) otaState = 2;
    }
  }
};

class TrackCB : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *c) override {
    const uint8_t *d = c->getData();   // the written value in place: no String copy per write
    size_t n = c->getLength();
    if (!n || !trackPts) return;
    if (d[0] == 'B' && n >= 13) {
      trackReady = false;
      uint16_t m, p;
      memcpy(&m, d + 1, 2);
      memcpy(&p, d + 3, 2);
      memcpy(&trackScale, d + 5, 4);
      memcpy(&trackStep, d + 9, 4);
      if ((uint32_t)m + p > TRACK_MAX) m = p = 0;   // too big: no map rather than a broken one
      trackMain = m;
      trackPit = p;
      trackExpected = ((uint32_t)m + p) * 4;
      trackBytes = 0;
    } else if (d[0] == 'C') {
      if (trackBytes + n - 1 <= trackExpected) {
        memcpy((uint8_t *)trackPts + trackBytes, d + 1, n - 1);
        trackBytes += n - 1;
      }
    } else if (d[0] == 'E') {
      trackReady = trackExpected > 0 && trackBytes == trackExpected;
    }
  }
};

void ancsBegin();

void setupBLE() {
  BLEDevice::init(DEVICE_NAME);
  BLEDevice::setMTU(517);   // bigger packets = faster cover art
  ancsBegin();

  BLEServer *server = BLEDevice::createServer();
  server->setCallbacks(new ServerCB());
  BLEService *service = server->createService(SERVICE_UUID);

  BLECharacteristic *cmd = service->createCharacteristic(
      CMD_UUID, BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_WRITE_NR);
  cmd->setCallbacks(new CmdCB());

  BLECharacteristic *img = service->createCharacteristic(
      IMG_UUID, BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_WRITE_NR);
  img->setCallbacks(new ImgCB());

  BLECharacteristic *trk = service->createCharacteristic(
      TRACK_UUID, BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_WRITE_NR);
  trk->setCallbacks(new TrackCB());

  BLECharacteristic *ota = service->createCharacteristic(
      OTA_UUID, BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_WRITE_NR);
  ota->setCallbacks(new OtaCB());

  touchChar = service->createCharacteristic(TOUCH_UUID, BLECharacteristic::PROPERTY_NOTIFY);
#ifndef CONFIG_NIMBLE_ENABLED   // NimBLE (the S3 default on core 3.3+) adds this descriptor itself
  touchChar->addDescriptor(new BLE2902());
#endif

  service->start();

  BLEAdvertising *adv = BLEDevice::getAdvertising();
  adv->setScanResponse(true);
#if defined(CONFIG_NIMBLE_ENABLED)
  // "Looking for Apple's notification service" (ANCS solicitation) lists the buddy in the iPhone's
  // Bluetooth settings. With the flags it fills the packet, so the name goes in the scan response
  // (the PC helper finds the buddy by name, not by SERVICE_UUID)
  static const uint8_t solicitAncs[] = {17, 0x15, 0xD0, 0x00, 0x2D, 0x12, 0x1E, 0x4B, 0x0F, 0xA4,
                                        0x99, 0x4E, 0xCE, 0xB5, 0x31, 0xF4, 0x05, 0x79};
  BLEAdvertisementData advData, scanData;
  advData.setFlags(0x06);   // general discoverable, LE only
  advData.addData((char *)solicitAncs, sizeof(solicitAncs));
  scanData.setName(DEVICE_NAME);
  adv->setAdvertisementData(advData);
  adv->setScanResponseData(scanData);
#else
  adv->addServiceUUID(SERVICE_UUID);
#endif
  BLEDevice::startAdvertising();
  Serial.println("Bluetooth ready: advertising as \"" DEVICE_NAME "\"");
}

void sendTouch(char action) {
  if (!bleConnected || !touchChar) return;
  touchChar->setValue((uint8_t *)&action, 1);
  touchChar->notify();
}

// Let the PC reconnect after a disconnect (short pause first, without delay())
const uint32_t ADVERTISE_CHECK_MS = 5000;
void updateAdvertising(uint32_t now) {
  if (restartAdvertising) {
    restartAdvertising = false;
    advertiseAt = now + 200;
    if (advertiseAt == 0) advertiseAt = 1;
  }
  if (advertiseAt && (int32_t)(now - advertiseAt) >= 0) {
    advertiseAt = 0;
    BLEDevice::startAdvertising();
  }
  // The iPhone can only come back to a board that's advertising, so a missed restart mustn't lock it out
  static uint32_t checkedAt = 0;
  if (!iphoneDirect && !advertiseAt && now - checkedAt >= ADVERTISE_CHECK_MS) {
    checkedAt = now;
    if (!BLEDevice::getAdvertising()->isAdvertising()) {
      ancsNote("Advertising was off (%u connected)", (unsigned)BLEDevice::getServer()->getConnectedCount());
      BLEDevice::startAdvertising();
    }
  }
}

// ---------------- iPhone notifications (ANCS) ----------------
// The iPhone sends its notifications straight to the buddy over Bluetooth, the way it does to a
// smartwatch (Apple Notification Center Service): no Phone Link and no PC needed. Pair once in the
// iPhone's Settings > Bluetooth ("Desk Buddy 0A69" > Pair, then Allow notifications); after that it
// reconnects by itself. The PC helper's connection is the one that subscribes to TOUCH; any other
// connection is checked for ANCS. Each new notification goes to handleMsg() as a "T" message, like
// the ones the PC helper used to send from Phone Link.
#if defined(CONFIG_NIMBLE_ENABLED)
static const ble_uuid128_t ANCS_SVC = BLE_UUID128_INIT(0xD0, 0x00, 0x2D, 0x12, 0x1E, 0x4B, 0x0F, 0xA4, 0x99, 0x4E, 0xCE, 0xB5, 0x31, 0xF4, 0x05, 0x79);
static const ble_uuid128_t ANCS_NS = BLE_UUID128_INIT(0xBD, 0x1D, 0xA2, 0x99, 0xE6, 0x25, 0x58, 0x8C, 0xD9, 0x42, 0x01, 0x63, 0x0D, 0x12, 0xBF, 0x9F);   // Notification Source
static const ble_uuid128_t ANCS_CP = BLE_UUID128_INIT(0xD9, 0xD9, 0xAA, 0xFD, 0xBD, 0x9B, 0x21, 0x98, 0xA8, 0x49, 0xE1, 0x45, 0xF3, 0xD8, 0xD1, 0x69);   // Control Point
static const ble_uuid128_t ANCS_DS = BLE_UUID128_INIT(0xFB, 0x7B, 0x7C, 0xCE, 0x6A, 0xB3, 0x44, 0xBE, 0xB5, 0x4B, 0xD6, 0x24, 0xE9, 0xC6, 0xEA, 0x22);   // Data Source

// iPhone app ids -> the names the Screen Designer knows (as PHONE_APPS in the PC helper)
static const char *const IOS_APPS[][2] = {
  {"com.apple.MobileSMS", "Messages"},       {"net.whatsapp.WhatsApp", "WhatsApp"},      {"com.toyopagroup.picaboo", "Snapchat"},
  {"com.burbn.instagram", "Instagram"},      {"com.facebook.Messenger", "Messenger"},    {"ph.telegra.Telegraph", "Telegram"},
  {"com.google.Gmail", "Gmail"},             {"com.apple.mobilemail", "Mail"},           {"com.microsoft.Office.Outlook", "Outlook"},
  {"com.apple.mobilephone", "Phone"},        {"com.apple.facetime", "FaceTime"},         {"com.zhiliaoapp.musically", "TikTok"},
  {"com.ss.iphone.ugc.Ame", "TikTok"},       {"com.microsoft.skype.teams", "Teams"},     {"com.tinyspeck.chatlyio", "Slack"},
  {"com.hammerandchisel.discord", "Discord"}, {"com.spotify.client", "Spotify"},         {"com.google.ios.youtube", "YouTube"},
  {"com.apple.Preferences", "Settings"},     {"com.apple.Health", "Health"},             {"com.apple.Passbook", "Wallet"},
  {"com.apple.mobiletimer", "Clock"},        {"com.apple.reminders", "Reminders"},       {"com.apple.mobilecal", "Calendar"},
  {"com.apple.findmy", "Find My"},           {"com.apple.shortcuts", "Shortcuts"},       {"com.apple.AppStore", "App Store"},
  {"com.life360.safetymap", "Life360"},      {"com.ubercab.UberClient", "Uber"},         {"com.google.Classroom", "Classroom"},
  {"com.theweathernetwork.weathereyeiphone", "Weather Network"},                         {"com.pratikstephen.StepUp", "StepUp"},
};

static QueueHandle_t ancsConns;     // new connections to check (handles)
static QueueHandle_t ancsUids;      // new notifications to fetch (UIDs)
static QueueHandle_t ancsNotes;     // what happened with the iPhone, waiting to go to the PC helper's log
static SemaphoreHandle_t ancsStep;  // the GATT step or pairing in flight has finished...
static volatile int ancsRc;         // ...with this result (0 = ok)
static volatile uint16_t ancsConn = BLE_HS_CONN_HANDLE_NONE;   // the connection being checked, then the iPhone
static volatile uint16_t pcConn = BLE_HS_CONN_HANDLE_NONE;     // the PC helper's
static uint16_t ancsStart, ancsEnd, nsHandle, cpHandle, dsHandle, nsCccd, dsCccd;
static uint8_t dsBuf[512];          // a Data Source answer, put together from its pieces
static volatile uint16_t dsLen;

// The board is rarely on USB, so each line also goes to the helper's log (never a notification's text)
void ancsNote(const char *fmt, ...) {
  char line[64] = "#";
  va_list args;
  va_start(args, fmt);
  vsnprintf(line + 1, sizeof(line) - 1, fmt, args);
  va_end(args);
  Serial.println(line + 1);
  if (ancsNotes) xQueueSend(ancsNotes, line, 0);
}

// In loop(): passes the lines on once the helper is listening
void ancsSendNotes() {
  char line[64];
  if (!touchChar || pcConn == BLE_HS_CONN_HANDLE_NONE || !xQueueReceive(ancsNotes, line, 0)) return;
  touchChar->setValue((uint8_t *)line, strlen(line));
  touchChar->notify();
}

// UTF-8 -> the plain ASCII the screens' fonts have: curly quotes and dashes become plain ones,
// accents are dropped, emoji and the rest are left out (as the PC helper's ascii_text does)
static void toAscii(const uint8_t *s, size_t n, char *out, size_t size) {
  static const char LATIN1[] = "AAAAAAACEEEEIIIIDNOOOOOxOUUUUYTsaaaaaaaceeeeiiiidnooooo/ouuuuyty";   // U+00C0-U+00FF
  size_t o = 0;
  for (size_t i = 0; i < n && o + 1 < size;) {
    uint32_t c = s[i];
    int k = c < 0x80 ? 1 : (c & 0xE0) == 0xC0 ? 2 : (c & 0xF0) == 0xE0 ? 3 : (c & 0xF8) == 0xF0 ? 4 : 1;
    if (k > 1) {
      c &= 0x3F >> (k - 1);
      for (int j = 1; j < k; j++) c = (c << 6) | (i + j < n ? s[i + j] & 0x3F : 0);
    }
    i += k;
    char one[2] = {0, 0};
    const char *rep = one;
    if (c >= 0x20 && c < 0x7F) one[0] = (char)c;
    else if (c < 0x20 || c == 0xA0 || c == 0xB7 || c == 0x2022) one[0] = ' ';
    else if (c == 0x2018 || c == 0x2019 || c == 0x2032) one[0] = '\'';
    else if (c == 0x201C || c == 0x201D) one[0] = '"';
    else if (c == 0x2013 || c == 0x2014) one[0] = '-';
    else if (c == 0x2026) rep = "...";
    else if (c >= 0xC0 && c <= 0xFF) one[0] = LATIN1[c - 0xC0];
    for (; *rep && o + 1 < size; rep++) {
      if (*rep == ' ' && (o == 0 || out[o - 1] == ' ')) continue;   // no leading or double spaces
      out[o++] = *rep;
    }
  }
  while (o && out[o - 1] == ' ') o--;
  out[o] = 0;
}

static void iosAppName(const char *id, char *out, size_t size) {
  for (auto &a : IOS_APPS) {
    if (!strcmp(id, a[0])) {
      strlcpy(out, a[1], size);
      return;
    }
  }
  // An app not in the list: the last part of its id, capitalised ("com.acme.Notes" -> "Notes"), or the
  // part before it when the last is only "ios" / "iphone" / "app" ("net.blip.ios" -> "Blip")
  char buf[64];
  strlcpy(buf, id, sizeof(buf));
  char *last = strrchr(buf, '.');
  if (last && (!strcasecmp(last + 1, "ios") || !strcasecmp(last + 1, "iphone") || !strcasecmp(last + 1, "app"))) {
    *last = 0;
    last = strrchr(buf, '.');
  }
  strlcpy(out, last ? last + 1 : buf, size);
  if (out[0] >= 'a' && out[0] <= 'z') out[0] -= 'a' - 'A';
}

// Every GAP event of every connection (registered with BLEDevice::setCustomGapHandler); runs in the
// NimBLE task, so it only records things and wakes ancsTask()
static int ancsGapEvent(struct ble_gap_event *e, void *arg) {
  switch (e->type) {
    case BLE_GAP_EVENT_CONNECT:     // something tried to connect and it didn't take
      if (e->connect.status != 0) ancsNote("Bluetooth: connecting failed (%d)", e->connect.status);
      break;
    case BLE_GAP_EVENT_SUBSCRIBE:   // the PC helper subscribes to TOUCH right after connecting
      if (touchChar && e->subscribe.attr_handle == touchChar->getHandle() && e->subscribe.cur_notify) pcConn = e->subscribe.conn_handle;
      break;
    case BLE_GAP_EVENT_ENC_CHANGE:   // pairing / encryption finished
      if (e->enc_change.conn_handle == ancsConn) {
        ancsRc = e->enc_change.status;
        xSemaphoreGive(ancsStep);
      }
      break;
    case BLE_GAP_EVENT_NOTIFY_RX: {
      if (e->notify_rx.conn_handle != ancsConn) break;
      uint8_t buf[256];
      uint16_t n = 0;
      ble_hs_mbuf_to_flat(e->notify_rx.om, buf, sizeof(buf), &n);
      if (e->notify_rx.attr_handle == nsHandle && n >= 8) {
        // Notification Source: EventID 0 = added; flag 4 = it was already on the phone when we subscribed
        if (buf[0] == 0 && !(buf[1] & 0x04)) {
          uint32_t uid;
          memcpy(&uid, buf + 4, 4);
          xQueueSend(ancsUids, &uid, 0);
        }
      } else if (e->notify_rx.attr_handle == dsHandle && dsLen + n <= sizeof(dsBuf)) {
        memcpy(dsBuf + dsLen, buf, n);
        dsLen += n;
      }
      break;
    }
    case BLE_GAP_EVENT_DISCONNECT:
      // Reason: 520 (0x208) out of range or the radio stalled, 531 (0x213) the other side hung up,
      // 534 (0x216) the buddy hung up
      ancsNote("Bluetooth: %s dropped (%d)", e->disconnect.conn.conn_handle == pcConn ? "PC" : e->disconnect.conn.conn_handle == ancsConn ? "iPhone" : "other", e->disconnect.reason);
      if (e->disconnect.conn.conn_handle == pcConn) pcConn = BLE_HS_CONN_HANDLE_NONE;
      if (e->disconnect.conn.conn_handle == ancsConn) {
        ancsConn = BLE_HS_CONN_HANDLE_NONE;
        ancsRc = BLE_HS_ENOTCONN;
        xSemaphoreGive(ancsStep);
      }
      break;
    default: break;
  }
  return 0;
}

// GATT results (also in the NimBLE task): record them, and say when the step is done
static int ancsSvcFound(uint16_t conn, const struct ble_gatt_error *err, const struct ble_gatt_svc *svc, void *arg) {
  if (err->status == 0 && svc) {
    ancsStart = svc->start_handle;
    ancsEnd = svc->end_handle;
  } else {
    ancsRc = err->status == BLE_HS_EDONE ? 0 : err->status;
    xSemaphoreGive(ancsStep);
  }
  return 0;
}

static int ancsChrFound(uint16_t conn, const struct ble_gatt_error *err, const struct ble_gatt_chr *chr, void *arg) {
  if (err->status == 0 && chr) {
    if (ble_uuid_cmp(&chr->uuid.u, &ANCS_NS.u) == 0) nsHandle = chr->val_handle;
    else if (ble_uuid_cmp(&chr->uuid.u, &ANCS_CP.u) == 0) cpHandle = chr->val_handle;
    else if (ble_uuid_cmp(&chr->uuid.u, &ANCS_DS.u) == 0) dsHandle = chr->val_handle;
  } else {
    ancsRc = err->status == BLE_HS_EDONE ? 0 : err->status;
    xSemaphoreGive(ancsStep);
  }
  return 0;
}

static int ancsDscFound(uint16_t conn, const struct ble_gatt_error *err, uint16_t chrValHandle, const struct ble_gatt_dsc *dsc, void *arg) {
  if (err->status == 0 && dsc) {
    if (ble_uuid_u16(&dsc->uuid.u) == 0x2902) {   // a CCCD belongs to the characteristic just before it
      uint16_t h = dsc->handle, owner = 0;
      for (uint16_t v : {nsHandle, cpHandle, dsHandle}) {
        if (v < h && v > owner) owner = v;
      }
      if (owner == nsHandle) nsCccd = h;
      else if (owner == dsHandle) dsCccd = h;
    }
  } else {
    ancsRc = err->status == BLE_HS_EDONE ? 0 : err->status;
    xSemaphoreGive(ancsStep);
  }
  return 0;
}

static int ancsWritten(uint16_t conn, const struct ble_gatt_error *err, struct ble_gatt_attr *attr, void *arg) {
  ancsRc = err->status;
  xSemaphoreGive(ancsStep);
  return 0;
}

// Waits for the step just started (rc = what starting it returned); true if it went fine
static bool ancsWait(int rc, uint32_t ms) {
  if (rc != 0) {
    ancsRc = rc;
    return false;
  }
  if (xSemaphoreTake(ancsStep, pdMS_TO_TICKS(ms)) != pdTRUE) {
    ancsRc = BLE_HS_ETIMEOUT;
    return false;
  }
  return ancsRc == 0;
}

static bool ancsFindService(uint16_t conn) {
  ancsStart = ancsEnd = 0;
  xSemaphoreTake(ancsStep, 0);
  return ancsWait(ble_gattc_disc_svc_by_uuid(conn, &ANCS_SVC.u, ancsSvcFound, nullptr), 5000) && ancsStart;
}

// Encrypts the link. The first time, the iPhone asks "Pair?" (Just Works: no code to type), so allow
// a minute for that
static bool ancsSecure(uint16_t conn) {
  struct ble_gap_conn_desc d;
  if (ble_gap_conn_find(conn, &d) != 0) return false;
  if (d.sec_state.encrypted) return true;
  xSemaphoreTake(ancsStep, 0);
  int rc = ble_gap_security_initiate(conn);
  return ancsWait(rc == BLE_HS_EALREADY ? 0 : rc, 60000);   // EALREADY: the iPhone started it itself
}

static bool ancsSubscribe(uint16_t conn, uint16_t cccd) {
  static const uint8_t on[2] = {1, 0};
  xSemaphoreTake(ancsStep, 0);
  return ancsWait(ble_gattc_write_flat(conn, cccd, on, sizeof(on), ancsWritten, nullptr), 60000);
}

// Gives up on a phone that didn't pair or subscribe. Dropping its connection lets you try again by
// tapping the buddy in the iPhone's Bluetooth settings (otherwise it stays "Connected" doing nothing)
static bool ancsGiveUp(uint16_t conn) {
  ble_gap_terminate(conn, BLE_ERR_REM_USER_CONN_TERM);
  return false;
}

// Is this connection an iPhone? If so pair, find ANCS's characteristics and subscribe
static bool ancsSetup(uint16_t conn) {
  ancsConn = conn;
  nsHandle = cpHandle = dsHandle = nsCccd = dsCccd = 0;
  if (!ancsFindService(conn)) {
    // iOS may only show it to a paired device: pair with a random-address peer (phones use those)
    // once it's clear it isn't the PC helper. A returning iPhone may have encrypted the link itself by
    // now, so look again then too: stopping here would leave it "Connected" doing nothing
    vTaskDelay(pdMS_TO_TICKS(6000));
    struct ble_gap_conn_desc d;
    if (conn == pcConn || ble_gap_conn_find(conn, &d) != 0 || d.peer_ota_addr.type == BLE_ADDR_PUBLIC) return false;
    ancsNote("iPhone?: pairing, then looking for its notifications");
    if (!ancsSecure(conn) || !ancsFindService(conn)) {
      ancsNote("iPhone?: no notification service (%d)", ancsRc);
      return ancsGiveUp(conn);
    }
  }
  ancsNote("iPhone: found its notification service, pairing");
  if (!ancsSecure(conn)) {
    // 1288 (0x508, 0x500 + the iPhone's reason 8): the iPhone said no. Its "Pair" popup was cancelled
    // or closed, or it still has an old pairing with the buddy (Forget This Device, then pair again)
    ancsNote("iPhone: pairing failed (%d)", ancsRc);
    return ancsGiveUp(conn);
  }
  ancsNote("iPhone: paired");
  xSemaphoreTake(ancsStep, 0);
  if (!ancsWait(ble_gattc_disc_all_chrs(conn, ancsStart, ancsEnd, ancsChrFound, nullptr), 5000) || !nsHandle || !cpHandle || !dsHandle) {
    ancsNote("iPhone: notification service incomplete (%d)", ancsRc);
    return ancsGiveUp(conn);
  }
  xSemaphoreTake(ancsStep, 0);
  ancsWait(ble_gattc_disc_all_dscs(conn, min(nsHandle, min(cpHandle, dsHandle)), ancsEnd, ancsDscFound, nullptr), 5000);
  if (!nsCccd) nsCccd = nsHandle + 1;   // where the CCCD almost always is
  if (!dsCccd) dsCccd = dsHandle + 1;
  xQueueReset(ancsUids);
  // Data Source first, then Notification Source (as Apple asks). The first time, the iPhone asks
  // whether to allow notifications
  if (!ancsSubscribe(conn, dsCccd) || !ancsSubscribe(conn, nsCccd)) {
    ancsNote("iPhone: couldn't subscribe (%d)", ancsRc);
    return ancsGiveUp(conn);
  }
  ancsNote("iPhone: notifications connected");
  return true;
}

// Asks for a notification's app, title and message. The answer comes on Data Source, maybe in pieces:
// command 0, the UID, then (attribute id, 16-bit length, value) for each attribute asked for
static bool ancsFetch(uint16_t conn, uint32_t uid, char *id, size_t idSize, char *title, char *msg) {
  const uint8_t cmd[] = {0, (uint8_t)uid, (uint8_t)(uid >> 8), (uint8_t)(uid >> 16), (uint8_t)(uid >> 24),
                         0,                              // app id
                         1, sizeof(nTitle) - 1, 0,       // title, up to this many bytes
                         3, sizeof(nText) - 1, 0};       // message
  dsLen = 0;
  xSemaphoreTake(ancsStep, 0);
  if (!ancsWait(ble_gattc_write_flat(conn, cpHandle, cmd, sizeof(cmd), ancsWritten, nullptr), 3000)) return false;
  for (uint32_t t0 = millis(); millis() - t0 < 3000; vTaskDelay(pdMS_TO_TICKS(20))) {
    uint16_t n = dsLen, p = 5;
    if (n < 5 || dsBuf[0] != 0 || memcmp(dsBuf + 1, cmd + 1, 4) != 0) continue;
    int found = 0;
    while (found < 3 && p + 3 <= n) {
      uint16_t len = dsBuf[p + 1] | (dsBuf[p + 2] << 8);
      if (p + 3 + len > n) break;   // the rest is still on its way
      const uint8_t *v = dsBuf + p + 3;
      if (dsBuf[p] == 0) {
        size_t k = min((size_t)len, idSize - 1);
        memcpy(id, v, k);
        id[k] = 0;
      } else if (dsBuf[p] == 1) {
        toAscii(v, len, title, sizeof(nTitle));
      } else if (dsBuf[p] == 3) {
        toAscii(v, len, msg, sizeof(nText));
      }
      p += 3 + len;
      found++;
    }
    if (found == 3) return true;
  }
  return false;
}

static void ancsTask(void *) {
  char id[64], app[sizeof(nApp)], title[sizeof(nTitle)], msg[sizeof(nText)];
  static char last[sizeof(nApp) + sizeof(nTitle) + sizeof(nText)];   // the previous notification,
  uint32_t lastAt = 0, count = 0;                                     // when it came and how many in a row
  for (;;) {
    uint16_t conn;
    xQueueReceive(ancsConns, &conn, portMAX_DELAY);
    vTaskDelay(pdMS_TO_TICKS(1500));   // by now the PC helper has subscribed to TOUCH
    struct ble_gap_conn_desc d;
    if (conn == pcConn || ble_gap_conn_find(conn, &d) != 0) continue;
    if (!ancsSetup(conn)) {
      ancsConn = BLE_HS_CONN_HANDLE_NONE;
      continue;
    }
    iphoneDirect = true;
    while (ancsConn == conn) {
      uint32_t uid;
      if (xQueueReceive(ancsUids, &uid, pdMS_TO_TICKS(1000)) != pdTRUE) continue;
      if (!ancsFetch(conn, uid, id, sizeof(id), title, msg)) {
        ancsNote("iPhone: couldn't read a notification (%d)", ancsRc);
        continue;
      }
      iosAppName(id, app, sizeof(app));
      // The same notification again within a minute (someone blowing up your phone) is counted, as
      // the PC helper does with Phone Link's
      char key[sizeof(last)];
      snprintf(key, sizeof(key), "%s\x1f%s\x1f%s", app, title, msg);
      count = !strcmp(key, last) && millis() - lastAt < 60000 ? count + 1 : 1;
      strlcpy(last, key, sizeof(last));
      lastAt = millis();
      char at[8] = "";
      if (clockKnown) {
        uint32_t s = (clockSec + (millis() - clockAt) / 1000) % 86400;
        snprintf(at, sizeof(at), "%02u:%02u", (unsigned)(s / 3600), (unsigned)(s / 60 % 60));
      }
      Msg m;
      int len = snprintf(m.data, sizeof(m.data), "T%s\x1f%s\x1f%s\x1f%u\x1f%s", app, title, msg, (unsigned)count, at);
      m.len = min(len, (int)sizeof(m.data) - 1);
      xQueueSend(msgQueue, &m, 0);
    }
    iphoneDirect = false;
    ancsNote("iPhone: disconnected");
  }
}

void ancsBegin() {
  // Bond with the phone (Just Works), but only start pairing where ancsSetup() asks for it: the
  // library would otherwise pair every connection, and the PC helper doesn't pair
  new BLESecurity();   // no input or display, and both keys exchanged
  BLESecurity::setAuthenticationMode(true, false, true);   // bonding, no MITM, secure connections
  BLESecurity::setForceAuthentication(false);
  ancsConns = xQueueCreate(4, sizeof(uint16_t));
  ancsUids = xQueueCreate(8, sizeof(uint32_t));
  ancsNotes = xQueueCreate(12, 64);
  ancsStep = xSemaphoreCreateBinary();
  BLEDevice::setCustomGapHandler(ancsGapEvent);
  xTaskCreate(ancsTask, "ancs", 6144, nullptr, 1, nullptr);
  // The devices the buddy is paired with, kept across restarts and uploads (phones pair with a
  // random address, a PC with its public one)
  ble_addr_t peers[8];
  int n = 0, phones = 0;
  ble_store_util_bonded_peers(peers, &n, 8);
  for (int i = 0; i < n; i++) phones += peers[i].type != BLE_ADDR_PUBLIC;
  ancsNote("Bluetooth: paired with %d phone(s) and %d other device(s)", phones, n - phones);
  ancsNote("Restart reason %d", (int)esp_reset_reason());   // 1 power on, 3 update, 4 crash, 5-7 froze, 9 low power
}

void ancsCheck(uint16_t conn) {
  if (ancsConns) xQueueSend(ancsConns, &conn, 0);
}
#else
void ancsBegin() {}
void ancsCheck(uint16_t conn) {}
void ancsNote(const char *fmt, ...) {}
void ancsSendNotes() {}
#endif

// ---------------- RGB LED ----------------
void setColor(uint8_t r, uint8_t g, uint8_t b) {
  rgbLedWrite(LED_PIN, r, g, b);   // built into the ESP32 Arduino core (no library needed)
}

void applyLed(char c) {
  if (!c || !strchr("WADOY", c)) return;
  ledState = c;
  if (mode == MODE_SIM) return;   // the shift light has the LED; exitSim() puts this colour back
  switch (c) {
    case 'W': break;                           // white  - working (pulses in updateLed)
    case 'Y': askPhase = UINT32_MAX; break;    // green / orange - asked you something (flashes in updateLed)
    case 'A': setColor(255, 50, 0); break;     // orange - waiting for input
    case 'D': setColor(0, 150, 0);  break;     // green  - finished
    case 'O': setColor(0, 0, 0);    break;     // off
  }
}

// Shift light across the car's HUD shift points: green below them, then yellow, orange, red,
// and flashing red from the shift point up.
void updateShiftLed(uint32_t now) {
  if (now - lastPulse < 20) return;
  lastPulse = now;
  float rpm = simFrame.rpm, s0 = simCar.shiftStart, s1 = simCar.shiftEnd;
  if (rpm >= s1) {
    bool on = (now / SHIFT_FLASH_MS) % 2 == 0;
    setColor(on ? 255 : 0, 0, 0);
  } else if (rpm < s0) {
    setColor(0, 150, 0);
  } else {
    float f = (rpm - s0) / (s1 - s0);
    if (f < 1.0f / 3)      setColor(255, 150, 0);   // yellow
    else if (f < 2.0f / 3) setColor(255, 50, 0);    // orange
    else                   setColor(255, 0, 0);     // red
  }
}

void updateLed(uint32_t now) {
  if (mode == MODE_SIM) { updateShiftLed(now); return; }
  // Flash green and orange after Claude finished with a question for you (the PC helper stops it after 30 s)
  if (ledState == 'Y') {
    uint32_t phase = now / ASK_FLASH_MS;
    if (phase != askPhase) {
      askPhase = phase;
      if (phase % 2 == 0) setColor(0, 150, 0);   // green
      else                setColor(255, 50, 0);  // orange
    }
    return;
  }
  // Pulse white (smooth fade in and out) while working
  if (ledState == 'W' && now - lastPulse >= 20) {
    lastPulse = now;
    float phase = (now % PULSE_MS) / (float)PULSE_MS;               // 0..1
    float level = 0.5f - 0.5f * cosf(phase * 2.0f * PI);            // 0..1..0
    level = 0.05f + 0.95f * level * level;                          // never fully off, eased
    setColor(150 * level, 150 * level, 100 * level);
  }
}

// ---------------- Eye rendering ----------------
// Upper lid travels further than the lower one; they meet below centre.
static inline float lidUpper(float lid) { return -EYE_R + lid * 1.5f * EYE_R; }
static inline float lidLower(float lid) { return  EYE_R - lid * 0.5f * EYE_R; }

static inline bool inCircle(float x, float y, float cx, float cy, float r) {
  x -= cx; y -= cy;
  return x * x + y * y < r * r;
}

static inline uint16_t eyePixel(float dx, float dy, float upper, float lower, float gx, float gy) {
  float r2 = dx * dx + dy * dy;
  if (r2 > EYE_R2)     return COL_BG;
  if (r2 > OUTLINE_R2) return COL_OUTLINE;
  if (dy < upper)      return (dy > upper - LASH_U) ? COL_LASH : COL_LID;
  if (dy > lower)      return (dy < lower + LASH_L) ? COL_LASH : COL_LID;

  float ix = dx - gx, iy = dy - gy;
  float d2 = ix * ix + iy * iy;
  if (d2 >= IRIS_R2) return COL_SCLERA;
  if (inCircle(ix, iy, SHINE1_X, SHINE1_Y, SHINE1_R) ||
      inCircle(ix, iy, SHINE2_X, SHINE2_Y, SHINE2_R)) return COL_SHINE;
  if (d2 < PUPIL_R2) return COL_PUPIL;
  if (d2 < IRIS_IN2) return COL_IRIS;
  return COL_IRIS_DARK;
}

// Render and push a screen rectangle (pixel coords, clipped) in strips.
void drawRegion(Eye &e, float lid, float gx, float gy,
                float fx0, float fy0, float fx1, float fy1) {
  int x0 = max(0,   (int)floorf(fx0));
  int y0 = max(0,   (int)floorf(fy0));
  int x1 = min(SCR, (int)ceilf(fx1));
  int y1 = min(SCR, (int)ceilf(fy1));
  if (x1 <= x0 || y1 <= y0) return;

  const int w = x1 - x0;
  const int rowsPerStrip = STRIP_PIXELS / w;
  const float upper = lidUpper(lid);
  const float lower = lidLower(lid);

  for (int y = y0; y < y1; y += rowsPerStrip) {
    int h = min(rowsPerStrip, y1 - y);
    uint16_t *p = strip;
    for (int yy = y; yy < y + h; yy++) {
      float dy = yy - CY;
      for (int xx = x0; xx < x1; xx++) {
        *p++ = eyePixel(xx - CX, dy, upper, lower, gx, gy);
      }
    }
    e.gfx->draw16bitRGBBitmap(x0, y, strip, w, h);
  }
}

// Where this eye should look right now, and how far its lid is down (blink or dizzy droop).
static inline float eyeGX(const Eye &e)  { return gazeX + e.ox; }
static inline float eyeGY(const Eye &e)  { return gazeY + e.oy; }
static inline float eyeLid(const Eye &e) { return fmaxf(e.lid, droop); }

void drawFullEye(Eye &e) {
  drawRegion(e, eyeLid(e), eyeGX(e), eyeGY(e), 0, 0, SCR, SCR);
  e.drawnLid = eyeLid(e);
  e.drawnGX = eyeGX(e);
  e.drawnGY = eyeGY(e);
}

// Redraw only what changed since the last frame.
void refreshEye(Eye &e) {
  const float tgx = eyeGX(e), tgy = eyeGY(e);
  bool gazeMoved = fabsf(tgx - e.drawnGX) > 0.3f || fabsf(tgy - e.drawnGY) > 0.3f;
  bool lidMoved  = eyeLid(e) != e.drawnLid;
  if (!gazeMoved && !lidMoved) return;

  const float ogx = e.drawnGX, ogy = e.drawnGY;
  const float gx  = gazeMoved ? tgx : ogx;
  const float gy  = gazeMoved ? tgy : ogy;
  const float lid = eyeLid(e);

  if (lidMoved) {
    // Band swept by the upper lid edge (+ lash)
    float a = lidUpper(e.drawnLid), b = lidUpper(lid);
    drawRegion(e, lid, gx, gy, 0, fminf(a, b) - LASH_U - 1 + CY, SCR, fmaxf(a, b) + 1 + CY);
    // Band swept by the lower lid edge (+ lash)
    a = lidLower(e.drawnLid); b = lidLower(lid);
    drawRegion(e, lid, gx, gy, 0, fminf(a, b) - 1 + CY, SCR, fmaxf(a, b) + LASH_L + 1 + CY);
  }

  if (gazeMoved) {
    // Box covering the iris at its old and new positions
    drawRegion(e, lid, gx, gy,
               fminf(ogx, gx) - IRIS_R - 1 + CX, fminf(ogy, gy) - IRIS_R - 1 + CY,
               fmaxf(ogx, gx) + IRIS_R + 1 + CX, fmaxf(ogy, gy) + IRIS_R + 1 + CY);
  }

  e.drawnLid = lid;
  e.drawnGX = gx;
  e.drawnGY = gy;
}

// ---------------- Touch filter ----------------
// In a case, the sensors pick up short spikes (nearby wires, the case wall). A reading only counts
// once it has stayed touched for TOUCH_CONFIRM_MS. Spikes are counted and sent to the helper's log
// once a minute, so a noisy sensor shows up without USB.
struct TouchFilter { uint32_t highSince; bool high; uint32_t spikes; };
TouchFilter filterL = {0, false, 0}, filterR = {0, false, 0};
uint32_t spikeReportAt = 0;

bool isTouched(int pin, uint32_t now) {
  TouchFilter &f = pin == TOUCH_LEFT_PIN ? filterL : filterR;
  bool raw = digitalRead(pin) == TOUCH_ACTIVE;
  if (raw && !f.high) f.highSince = now;
  if (!raw && f.high && now - f.highSince < TOUCH_CONFIRM_MS) f.spikes++;
  f.high = raw;
  return raw && now - f.highSince >= TOUCH_CONFIRM_MS;
}

void reportTouchSpikes(uint32_t now) {
  if (now - spikeReportAt < 60000) return;
  spikeReportAt = now;
  if (filterL.spikes || filterR.spikes)
    ancsNote("Touch: ignored spikes left %lu right %lu", (unsigned long)filterL.spikes, (unsigned long)filterR.spikes);
  filterL.spikes = filterR.spikes = 0;
}

// ---------------- Blink logic ----------------
void updateEye(Eye &e, uint32_t now, float dt) {
  bool touched = isTouched(e.pin, now);
  bool pressed = touched && !e.lastTouch;   // rising edge
  e.lastTouch = touched;

  if (pressed && (e.state == OPEN || e.state == OPENING)) {
    e.state = CLOSING;
  }

  switch (e.state) {
    case OPEN:
      break;

    case CLOSING:
      e.lid += dt / CLOSE_MS;
      if (e.lid >= 1.0f) {
        e.lid = 1.0f;
        e.state = CLOSED;
        e.closedAt = now;
      }
      break;

    case CLOSED:
      if (now - e.closedAt >= HOLD_MS && !(HOLD_TO_CLOSE && touched)) {
        e.state = OPENING;
      }
      break;

    case OPENING:
      e.lid -= dt / OPEN_MS;
      if (e.lid <= 0.0f) {
        e.lid = 0.0f;
        e.state = OPEN;
      }
      break;
  }
}

void updateGaze(uint32_t now, float dt) {
  if (!EYES_WANDER) return;
  if (now >= nextGazeAt) {
    targetX = random(-GAZE_X, GAZE_X + 1);
    targetY = random(-GAZE_Y, GAZE_Y + 1);
    nextGazeAt = now + random(1200, 4000);
  }
  float k = min(1.0f, dt * 0.015f);   // smoothing
  gazeX += (targetX - gazeX) * k;
  gazeY += (targetY - gazeY) * k;
}

// ---------------- Vibration: shake, then dizzy ----------------
// The SW420's output chatters while it vibrates, so count edges (either polarity works).
void IRAM_ATTR onVibration() { vibEdges = vibEdges + 1; }

void resetVibration() {
  vibEdges = 0;
  vibLevel = 0;
  vibState = VIB_IDLE;
  droop = 0;
  leftEye.ox = leftEye.oy = rightEye.ox = rightEye.oy = 0;
}

// Call before updateGaze(): it holds the wander target at the centre while shaken / dizzy.
void updateVibration(uint32_t now, float dt) {
  uint32_t edges = vibEdges;
  vibEdges = 0;
  vibLevel = vibLevel * expf(-dt / VIB_DECAY_MS) + edges;

  if (vibLevel >= VIB_TRIGGER || (vibState == VIB_SHAKING && edges)) {
    if (vibState != VIB_SHAKING) Serial.printf("Vibration: shaking (level %.0f)\n", vibLevel);
    vibState = VIB_SHAKING;
    lastVibAt = now;
  } else if (vibState == VIB_SHAKING && now - lastVibAt > VIB_HOLD_MS) {
    Serial.println("Vibration: dizzy");
    vibState = VIB_DIZZY;
    dizzyAt = now;
    dizzyPhase = 0;
  } else if (vibState == VIB_DIZZY && now - dizzyAt > DIZZY_MS) {
    vibState = VIB_IDLE;
  }

  float ox = 0, oy = 0, droopTarget = 0;
  if (vibState == VIB_SHAKING) {
    // Fast wobble, slightly different per axis so it looks rattled rather than circular
    float t = now * 0.001f;
    ox = SHAKE_PX * sinf(t * 2 * PI * 9);
    oy = SHAKE_PX * 0.6f * sinf(t * 2 * PI * 7 + 1);
  } else if (vibState == VIB_DIZZY) {
    float k = (now - dizzyAt) / (float)DIZZY_MS;                                // 0..1
    float r = DIZZY_R * min(1.0f, (now - dizzyAt) / 250.0f) * (1 - k) * (1 - k);  // swell in, fade out
    dizzyPhase += dt * 0.001f * DIZZY_RPS * 2 * PI * (1 - 0.6f * k);             // slows as it wears off
    ox = r * cosf(dizzyPhase);
    oy = r * sinf(dizzyPhase);
    droopTarget = DIZZY_DROOP * (1 - k);
  }
  // Right eye mirrors the left, so they roll in and out of each other: properly dizzy
  leftEye.ox = ox;   leftEye.oy = oy;
  rightEye.ox = -ox; rightEye.oy = oy;
  droop += (droopTarget - droop) * min(1.0f, dt * 0.01f);
  if (droop < 0.002f && droopTarget == 0) droop = 0;

  if (vibState != VIB_IDLE) {
    targetX = targetY = 0;          // look straight ahead while it's happening
    nextGazeAt = now + 800;         // then pause a moment before wandering again
  }
}

// ---------------- Cover art ----------------
int jpegDraw(JPEGDRAW *p) {
  for (int y = 0; y < p->iHeight; y++) {
    int sy = p->y + y;
    if (sy < 0 || sy >= SCR) continue;
    int w = min(p->iWidth, SCR - p->x);
    uint16_t *dest = jpgIsModel ? modelPic : cover;
    if (w > 0) memcpy(&dest[sy * SCR + p->x], &p->pPixels[y * p->iWidth], w * 2);
  }
  return 1;
}

void decodeCover() {
  if (!jpgReady) return;
  bool ok = jpeg.openRAM(jpgBuf, jpgLen, jpegDraw);
  if (ok) {
    jpeg.setPixelType(RGB565_LITTLE_ENDIAN);
    ok = jpeg.decode(0, 0, 0);
    jpeg.close();
  }
  jpgReady = false;
  if (ok) (jpgIsModel ? modelValid : coverValid) = true;
}

uint32_t currentPosMs() {
  uint32_t pos = mPosMs + (mPlaying ? millis() - mPosAt : 0);
  return (mDurMs && pos > mDurMs) ? mDurMs : pos;
}

// ---------------- Designed scenes (buddy_screens.h) ----------------
// Everything the scenes can show, from the PC helper's messages and the board's own state
void fillBuddyData(BuddyData &d, uint32_t now) {
  d.title = mTitle;
  d.artist = mArtist;
  d.app = mApp;
  d.playing = mPlaying;
  d.posMs = currentPosMs();
  d.durMs = mDurMs;
  d.volume = mVolume < 0 ? 0 : mVolume;
  d.muted = mMuted;

  char claude = claudeStatus ? claudeStatus : ledState;
  d.claude = claude == 'Y' ? 'D' : claude;   // the scenes treat "asked you something" as done
  d.sessionUsage = claudeSession;
  d.weeklyUsage = claudeWeekly;
  d.sessionKnown = claudeSessionKnown;
  d.weeklyKnown = claudeWeeklyKnown;
  d.sessionMs = claudeSessionMs ? claudeSessionMs + (now - claudeAt) : 0;
  d.tokens = claudeTokens;

  if (clockKnown) {
    uint32_t s = (clockSec + (now - clockAt) / 1000) % 86400;
    d.hour = s / 3600;
    d.minute = (s / 60) % 60;
    d.second = s % 60;
  } else {
    d.hour = 12;   // no time yet: noon, so no night / morning scene shows by mistake
  }
  d.date = clockDate;

  d.notifApp = nApp;
  d.notifTitle = nTitle;
  d.notifText = nText;
  d.notifCount = nCount;
  d.notifTime = nTime;

  d.ffWeek = fWeek;
  d.ffMyTeam = fMyTeam;
  d.ffOppTeam = fOppTeam;
  d.ffMyScore = fMyScore;
  d.ffOppScore = fOppScore;
  d.ffMyProj = fMyProj;
  d.ffOppProj = fOppProj;
  d.ffRecord = fRecord;
  d.ffRank = fRank;

  d.cover = coverValid ? cover : nullptr;
  d.coverAngle = vinylAngle;
  d.lid = leftEye.lid;   // drawScene() sets each screen's own
  d.gazeX = gazeX / GAZE_X;
  d.gazeY = gazeY / GAZE_Y;
  d.ms = now;
}

// What's happening, as the designer's BUDDY_WHEN_ bits
char shownClaude = 0;               // Claude status the scenes last saw, and since when
uint32_t shownClaudeSince = 0;

uint16_t sceneWhen(uint32_t now, const BuddyData &d) {
  uint16_t w = 0;
  if (mediaActive) w |= mPlaying ? BUDDY_WHEN_MEDIA : BUDDY_WHEN_PAUSED;
  else             w |= BUDDY_WHEN_IDLE;
  if (volumeShownAt && now - volumeShownAt < VOLUME_SHOW_MS) w |= BUDDY_WHEN_VOLUME;
  if (notifUntil && (int32_t)(notifUntil - now) > 0) w |= BUDDY_WHEN_NOTIFICATION;
  // Claude open counts while it works or needs you, and for a minute after it finishes; after
  // that the Claude app being open doesn't hold the dashboard up, so the eyes come back
  if (d.claude != shownClaude) {
    shownClaude = d.claude;
    shownClaudeSince = now;
  }
  if (!(d.claude == 'D' && now - shownClaudeSince > CLAUDE_DONE_SHOW_MS)) w |= buddyClaudeWhen(d.claude);
  if (fLive) w |= BUDDY_WHEN_FANTASY_LIVE;
  return w;
}

// The fantasy pages take turns every FANTASY_PAGE_MS. A tap on a sensor flips to the next (right) or
// previous (left) one, which then stays FANTASY_HOLD_MS before they take turns again
uint32_t fantasySlot = 3000;   // which turn it is (starts high so flipping back never goes below 0)
uint32_t fantasySlotAt = 0;
bool fantasyHeld = false;

uint32_t fantasyTurn(uint32_t now) {
  if (now - fantasySlotAt >= (fantasyHeld ? FANTASY_HOLD_MS : FANTASY_PAGE_MS)) {
    fantasySlot++;
    fantasySlotAt = now;
    fantasyHeld = false;
  }
  return fantasySlot;
}

void fantasyFlip(int by) {
  fantasySlot += by;
  fantasySlotAt = millis();
  fantasyHeld = true;
  Serial.printf("Touch: fantasy page %s\n", by > 0 ? "next" : "back");
}

// While an NBA game is on: with nothing else on the screens (the eyes or a time-of-day scene), the
// fantasy pages in today's style take turns (fantasy_screens.h), and a notification or the volume
// shows on the right screen beside them. Music and the Claude dashboard stay and show the score
// themselves (ff::overlay() in drawScene).
int fantasyScene(int scene, const BuddyData &d, uint32_t now) {
  if (!fLive || !fWeek) return scene;
  uint16_t when = BUDDY_SCENES[scene].when;
  int with = when == BUDDY_WHEN_IDLE ? 0
           : when == (BUDDY_WHEN_IDLE | BUDDY_WHEN_NOTIFICATION) ? ff::WITH_NOTIFICATION
           : when == (BUDDY_WHEN_IDLE | BUDDY_WHEN_VOLUME) ? ff::WITH_VOLUME : -1;
  if (with < 0) return scene;
  return ff::pageScene(fantasyTurn(now), d) + with;
}

// A notification has come in (a repeat with a new count keeps it up longer). The helper's log gets
// its app and where it went, never its text
void showNotification() {
  notifUntil = millis() + NOTIF_SHOW_MS;
  if (!notifUntil) notifUntil = 1;
  notifToReport = mode != MODE_SIM;
  ancsNote("Notification: %s x%u", nApp, (unsigned)nCount);
}

// When the games start (the matchup turns live), a notification on the buddy says so
void fantasyAlert() {
  char a[12], b[12];
  ff::pts(a, sizeof a, fMyScore);
  ff::pts(b, sizeof b, fOppScore);
  strlcpy(nApp, "Fantasy", sizeof(nApp));
  strlcpy(nTitle, "Games are on", sizeof(nTitle));
  if (!strcmp(fOppTeam, "BYE")) snprintf(nText, sizeof(nText), "Week %u - a bye week, you have %s", (unsigned)fWeek, a);
  else snprintf(nText, sizeof(nText), "Week %u - you %s, %s %s", (unsigned)fWeek, a, fOppTeam, b);
  nCount = 1;
  nTime[0] = 0;
  if (clockKnown) {
    uint32_t s = (clockSec + (millis() - clockAt) / 1000) % 86400;
    snprintf(nTime, sizeof(nTime), "%02u:%02u", (unsigned)(s / 3600), (unsigned)(s / 60 % 60));
  }
  showNotification();
}

// What Claude is doing right now, its question, and its work in SolidWorks (from the PC's J, ? and M)
cs::Activity activity;
cs::Ask ask;
cs::SolidWorks solidWorks;

bool swActive(uint32_t now) { return solidWorks.at && now - solidWorks.at < SW_SHOW_MS; }

// Claude's question has the right screen, except while a notification or the volume has it for a moment
bool askShows(uint32_t now) {
  return ask.title[0] && !(notifUntil && (int32_t)(notifUntil - now) > 0)
      && !(volumeShownAt && now - volumeShownAt < VOLUME_SHOW_MS);
}

int pickScene(uint32_t now) {
  BuddyData d;
  fillBuddyData(d, now);
  uint16_t when = sceneWhen(now, d);
  // While Claude builds in SolidWorks: the model on the left and the steps on the right, with a
  // notification or the volume on the right for a moment. The song stays on the right, the sensors still work it.
  if (swActive(now)) {
    return cs::SW_SCENE + (when & BUDDY_WHEN_NOTIFICATION ? cs::SW_WITH_NOTIFICATION
                         : when & BUDDY_WHEN_VOLUME ? cs::SW_WITH_VOLUME : 0);
  }
  int scene = buddyPickScene(when, d);
  scene = fantasyScene(scene < 0 ? BUDDY_SCENE_IDLE_EYES : scene, d, now);   // nothing fits: the eyes
  return scene == BUDDY_SCENE_IDLE_EYES && ask.title[0] ? BUDDY_SCENE_CLAUDE_DASHBOARD_BOLD : scene;   // the eyes can't show a card
}

// The solid pages Claude's step and question go over, once the scene underneath is drawn
void drawClaudeOver(int scene, uint32_t now, const BuddyData &d) {
  if (askShows(now) && ask.opt[0][0]) {
    cs::askChoice(leftCanvas, rightCanvas, ask);
  } else if (askShows(now)) {
    cs::askCard(rightCanvas, ask);
  } else if (activity.what[0] && d.claude == 'W') {
    if (scene == BUDDY_SCENE_CLAUDE_DASHBOARD_BOLD || scene == BUDDY_SCENE_CLAUDE_DASHBOARD_BOLD_IDLE) {
      cs::dashboardActivity(rightCanvas, activity, d);
    } else if (scene == BUDDY_SCENE_AUDIO_CLAUDE || scene == BUDDY_SCENE_AUDIO_CLAUDE_ANY_STATUS) {
      cs::audioActivity(rightCanvas, activity, d);
    }
  }
}

// Send a canvas to its screen: only the rectangle that changed since the last send (all of it if
// forced). Sending is the slow part (~30 ms for a whole screen at 40 MHz), and moving eyes, a
// ticking clock or a progress ring change only part of the picture. Returns the pixels sent.
uint32_t flushIfChanged(Arduino_Canvas *c, Arduino_GFX *gfx, Arduino_DataBus *bus, uint16_t *shown, bool force) {
  uint16_t *fb = c->getFramebuffer();
  int y0 = 0, y1 = SCR - 1, x0 = 0, x1 = SCR - 1;
  if (!force) {
    while (y0 < SCR && memcmp(fb + y0 * SCR, shown + y0 * SCR, SCR * 2) == 0) y0++;
    if (y0 == SCR) return 0;   // the same picture
    while (memcmp(fb + y1 * SCR, shown + y1 * SCR, SCR * 2) == 0) y1--;
    x0 = SCR;
    x1 = -1;
    for (int y = y0; y <= y1; y++) {   // the columns that changed in those rows
      const uint16_t *a = fb + y * SCR, *b = shown + y * SCR;
      int l = 0, r = SCR - 1;
      while (l < x0 && a[l] == b[l]) l++;
      while (r > x1 && a[r] == b[r]) r--;
      if (l < x0) x0 = l;
      if (r > x1) x1 = r;
    }
  }
  int w = x1 - x0 + 1, h = y1 - y0 + 1;
  for (int y = y0; y <= y1; y++) memcpy(shown + y * SCR + x0, fb + y * SCR + x0, w * 2);
  gfx->startWrite();
  static_cast<Arduino_TFT *>(gfx)->writeAddrWindow(x0, y0, w, h);
  for (int y = y0; y <= y1; y++) bus->writePixels(fb + y * SCR + x0, w);
  gfx->endWrite();
  return (uint32_t)w * h;
}

void drawScene(uint32_t now) {
  BuddyData d;
  fillBuddyData(d, now);
  BuddyData dR = d;
  // Each sensor blinks the eye on its own side, as in the plain eyes; a scene with an eye on one
  // screen only (night mode, good morning...) blinks it with either sensor
  bool oneEye = eyeSides == 1 || eyeSides == 2;
  float either = fmaxf(leftEye.lid, rightEye.lid);
  d.lid = oneEye ? either : leftEye.lid;
  dR.lid = oneEye ? either : rightEye.lid;
  drawnEyes = 0;
  uint32_t t0 = micros();
  if (cs::isSwScene(curScene)) {
    cs::swLeft(leftCanvas, modelValid ? modelPic : nullptr);
    int with = curScene - cs::SW_SCENE;
    if (with == cs::SW_WITH_NOTIFICATION) buddyDraw_idle_eyes_notfication_right(rightCanvas, d);
    else if (with == cs::SW_WITH_VOLUME) buddyDraw_idle_eyes_volume_right(rightCanvas, d);
    else cs::swRight(rightCanvas, solidWorks, d, mediaActive && mPlaying ? mTitle : "");
  } else if (curScene >= ff::SCENE_FIRST) {
    ff::draw(curScene, leftCanvas, rightCanvas, d);
  } else {
    buddyDrawScene(curScene, leftCanvas, rightCanvas, d, &dR);
    if (fLive && fWeek) ff::overlay(curScene, leftCanvas, rightCanvas, d);   // the score on music / Claude
  }
  drawClaudeOver(curScene, now, d);
  eyeSides = drawnEyes;
  uint32_t t1 = micros();
  uint32_t px = flushIfChanged(leftCanvas, gfxL, busL, shownL, sceneForce)
              + flushIfChanged(rightCanvas, gfxR, busR, shownR, sceneForce);
  if (px && !sceneForce) {   // something moved (the first, forced frame of a scene doesn't count)
    statFrames++;
    statDrawUs += t1 - t0;
    statSendUs += micros() - t1;
    statPixels += px;
  }
  sceneForce = false;
  lastSceneDraw = now;
}

// How smoothly the scene that's ending moved, for the Serial Monitor (115200)
void printSceneStats() {
  if (mode == MODE_SCENE && statFrames) {
    float ms = (statDrawUs + statSendUs) / 1000.0f / statFrames;
    Serial.printf("  scene %d: %lu moving frames, %.1f ms each (draw %.1f + compare/send %.1f) = %.0f fps, %.0f%% of the pixels sent\n",
                  curScene, (unsigned long)statFrames, ms, statDrawUs / 1000.0f / statFrames, statSendUs / 1000.0f / statFrames,
                  1000.0f / fmaxf(ms, (float)SCENE_FRAME_MS), statPixels * 100.0f / (statFrames * 2.0f * SCR * SCR));
  }
  statFrames = 0;
  statDrawUs = statSendUs = statPixels = 0;
}

// Centered text, size 2 = 12 px per char; wraps onto at most `lines` lines of `maxChars`.
int drawCentered(Arduino_GFX *g, const char *text, int y, int size, uint16_t color, int maxChars, int lines) {
  g->setTextSize(size);
  g->setTextColor(color);
  int charW = 6 * size, lineH = 8 * size + 4;
  const char *p = text;
  for (int line = 0; line < lines && *p; line++) {
    int n = min((int)strlen(p), maxChars);
    bool last = line == lines - 1;
    if (!last && (int)strlen(p) > maxChars) {   // break at a space
      int cut = n;
      while (cut > 0 && p[cut] != ' ') cut--;
      if (cut > maxChars / 2) n = cut;
    }
    char buf[40];
    if (last && (int)strlen(p) > maxChars) {
      n = maxChars - 2;
      memcpy(buf, p, n);
      buf[n++] = '.'; buf[n++] = '.';
    } else {
      memcpy(buf, p, n);
    }
    buf[n] = 0;
    g->setCursor((SCR - n * charW) / 2, y);
    g->print(buf);
    y += lineH;
    p += n;
    while (*p == ' ') p++;
  }
  return y;
}

// ---------------- Racing sim: left screen gauge ----------------
const float GAUGE_A0 = 135.0f, GAUGE_SWEEP = 270.0f;   // dial from bottom-left round to bottom-right (deg, clockwise)
const uint16_t COL_ACCENT    = RGB565(255, 98, 62);    // the game's accent colour (needle, car arrow)
const uint16_t COL_BEZEL     = RGB565(70, 72, 80);
const uint16_t COL_MAP_TRACK = RGB565(105, 108, 118);  // circuit away from the car

float gaugeAngle(float v) {
  float lo = simCar.gaugeMin, hi = simCar.gaugeMax;
  if (hi <= lo) return GAUGE_A0;
  float f = (v - lo) / (hi - lo);
  f = f < 0 ? 0 : (f > 1 ? 1 : f);
  return GAUGE_A0 + GAUGE_SWEEP * f;
}

// Point at radius r, angle a (deg, clockwise from 3 o'clock) around the screen centre
static inline int16_t polX(float a, float r) { return SCR / 2 + r * cosf(a * DEG_TO_RAD); }
static inline int16_t polY(float a, float r) { return SCR / 2 + r * sinf(a * DEG_TO_RAD); }

void thickLine(Arduino_GFX *g, int x0, int y0, int x1, int y1, uint16_t col) {
  g->drawLine(x0, y0, x1, y1, col);
  g->drawLine(x0 + 1, y0, x1 + 1, y1, col);
  g->drawLine(x0, y0 + 1, x1, y1 + 1, col);
}

void gearText(char *out, int8_t gear) {
  if (gear < 0) strcpy(out, "R");
  else if (gear == 0) strcpy(out, "N");
  else sprintf(out, "%d", gear);
}

// Dial face for the current car (no needle): drawn once into gaugeBg, copied under the needle each frame.
// Turbo cars: boost in bar, vacuum below zero tinted blue. The rest: rpm x1000, red from the shift point.
void buildGaugeBg() {
  Arduino_Canvas *g = leftCanvas;
  bool turbo = simCar.turbo;
  float lo = simCar.gaugeMin, hi = simCar.gaugeMax;
  g->fillScreen(COL_BG);
  g->fillCircle(120, 120, 119, RGB565(46, 46, 54));   // bezel
  g->fillCircle(120, 120, 115, RGB565(12, 12, 16));   // face
  g->fillArc(120, 120, 108, 98, GAUGE_A0, GAUGE_A0 + GAUGE_SWEEP, COL_TRACK);
  if (turbo) g->fillArc(120, 120, 108, 98, GAUGE_A0, gaugeAngle(0), RGB565(24, 36, 64));
  else       g->fillArc(120, 120, 108, 98, gaugeAngle(simCar.shiftEnd), GAUGE_A0 + GAUGE_SWEEP, RGB565(110, 20, 20));

  // Ticks: turbo every 0.5 bar (1 bar on big scales) with 5 minor steps; tacho every 1000 rpm
  // (2000 for F1 revs) with one minor step between. Numbers on whole bars / thousands.
  float major = turbo ? (hi - lo > 3.01f ? 1.0f : 0.5f) : (hi > 12000 ? 2000.0f : 1000.0f);
  int minorPer = turbo ? 5 : 2;
  float stepV = major / minorPer;
  g->setTextSize(2);
  g->setTextColor(COL_TEXT);
  for (int i = 0; ; i++) {
    float v = lo + i * stepV;
    if (v > hi + stepV * 0.01f) break;
    float a = gaugeAngle(v);
    if (i % minorPer == 0) {
      thickLine(g, polX(a, 95), polY(a, 95), polX(a, 84), polY(a, 84), COL_TEXT);
      bool label = turbo ? fabsf(v - roundf(v)) < 0.01f : true;
      if (label) {
        char buf[8];
        sprintf(buf, "%d", turbo ? (int)roundf(v) : (int)roundf(v / 1000));
        int w = strlen(buf) * 12;
        g->setCursor(polX(a, 70) - w / 2, polY(a, 70) - 8);
        g->print(buf);
      }
    } else {
      g->drawLine(polX(a, 95), polY(a, 95), polX(a, 90), polY(a, 90), COL_DIM);
    }
  }
  drawCentered(g, turbo ? "BOOST bar" : "RPM x1000", 86, 1, COL_DIM, 20, 1);
  memcpy(gaugeBg, g->getFramebuffer(), SCR * SCR * 2);
}

void drawGauge() {
  bool turbo = simCar.turbo;
  float v = turbo ? simFrame.boost : simFrame.rpm;
  float a = gaugeAngle(v);
  int8_t gear = simFrame.gear;
  int kmh = simFrame.kmh;
  if (fabsf(a - gaugeAngleShown) < 0.4f && gear == gaugeGearShown && kmh == gaugeKmhShown) return;   // nothing visible changed
  gaugeAngleShown = a;
  gaugeGearShown = gear;
  gaugeKmhShown = kmh;

  Arduino_Canvas *g = leftCanvas;
  memcpy(g->getFramebuffer(), gaugeBg, SCR * SCR * 2);

  // Value arc: turbo from zero to the needle (blue boost, dim vacuum); tacho from the bottom,
  // coloured like the shift light
  if (turbo) {
    float z = gaugeAngle(0);
    uint16_t col = v >= 0 ? RGB565(70, 160, 255) : RGB565(50, 80, 140);
    if (fabsf(a - z) > 0.5f) g->fillArc(120, 120, 108, 98, fminf(a, z), fmaxf(a, z), col);
  } else {
    float r = simFrame.rpm;
    uint16_t col = r < simCar.shiftStart ? RGB565(40, 200, 80) : (r < simCar.shiftEnd ? RGB565(255, 190, 0) : RGB565(255, 40, 40));
    if (a - GAUGE_A0 > 0.5f) g->fillArc(120, 120, 108, 98, GAUGE_A0, a, col);
  }

  // Readouts under the hub (the needle never points straight down, so they stay clear)
  char buf[12], gtxt[4];
  gearText(gtxt, gear);
  if (turbo) {
    snprintf(buf, sizeof(buf), "%+.2f", v);
    drawCentered(g, buf, 142, 3, COL_TEXT, 8, 1);
    drawCentered(g, gtxt, 174, 3, COL_ACCENT, 3, 1);
    snprintf(buf, sizeof(buf), "%d", kmh);
    drawCentered(g, buf, 204, 2, COL_DIM, 4, 1);
  } else {   // the gear big, the speed under it (the needle shows the revs)
    drawCentered(g, gtxt, 134, 5, COL_TEXT, 3, 1);
    snprintf(buf, sizeof(buf), "%d", kmh);
    drawCentered(g, buf, 182, 2, COL_TEXT, 4, 1);
    drawCentered(g, "KM/H", 202, 1, COL_DIM, 4, 1);
  }

  // Needle: a long thin wedge with a short tail, and the hub cap
  float ar = a * DEG_TO_RAD, ca = cosf(ar), sa = sinf(ar);
  int tx = 120 + 100 * ca, ty = 120 + 100 * sa;
  int bx = 120 - 16 * ca, by = 120 - 16 * sa;
  int px = -sa * 4, py = ca * 4;
  g->fillTriangle(tx, ty, 120 + px, 120 + py, 120 - px, 120 - py, COL_ACCENT);
  g->fillTriangle(bx, by, 120 + px, 120 + py, 120 - px, 120 - py, COL_ACCENT);
  g->fillCircle(120, 120, 10, RGB565(60, 60, 68));
  g->fillCircle(120, 120, 4, COL_ACCENT);
  g->flush();
}

// ---------------- Racing sim: right screen minimap ----------------
// The game's minimap (ui/minimap.py): heading-up, the car fixed below the centre, the circuit
// turning and zooming around it; the next stretch bright and fading out, the rest muted.

// Empty disc: dark glass, lighter in the middle (as the game's), and a fine bezel
void buildMapBg() {
  Arduino_Canvas *g = rightCanvas;
  g->fillScreen(COL_BG);
  for (int j = 24; j > 0; j--) {
    float f = j / 24.0f, t = powf(f, 1.6f);
    g->fillCircle(120, 120, MAP_R * f, RGB565((int)(24 - 18 * t), (int)(27 - 20 * t), (int)(33 - 24 * t)));
  }
  g->drawCircle(120, 120, MAP_R, COL_BEZEL);
  memcpy(mapBg, g->getFramebuffer(), SCR * SCR * 2);
}

void drawArrow(Arduino_GFX *g, float x, float y, float ang) {
  float ca = cosf(ang), sa = sinf(ang);
  auto P = [&](float px, float py, int16_t &ox, int16_t &oy) {
    ox = x + px * ca - py * sa;
    oy = y + px * sa + py * ca;
  };
  const float L = 12.0f, W = 8.5f, o = 2.0f;
  int16_t tx, ty, rx, ry, nx, ny, lx, ly;
  P(0, -L - o, tx, ty); P(W + o, L * 0.62f + o, rx, ry); P(0, L * 0.22f + o * 0.6f, nx, ny); P(-W - o, L * 0.62f + o, lx, ly);
  g->fillTriangle(tx, ty, rx, ry, nx, ny, COL_BG);
  g->fillTriangle(tx, ty, nx, ny, lx, ly, COL_BG);
  P(0, -L, tx, ty); P(W, L * 0.62f, rx, ry); P(0, L * 0.22f, nx, ny); P(-W, L * 0.62f, lx, ly);
  g->fillTriangle(tx, ty, rx, ry, nx, ny, COL_ACCENT);
  g->fillTriangle(tx, ty, nx, ny, lx, ly, COL_ACCENT);
}

void drawMinimap() {
  Arduino_Canvas *g = rightCanvas;
  memcpy(g->getFramebuffer(), mapBg, SCR * SCR * 2);
  const SimFrame &f = simFrame;
  const float R = MAP_R, ax = 120, ay = 120 + MAP_ANCHOR * R;
  const float sc = R / fmaxf(f.radius, 1.0f);                 // px per metre
  const float th = PI / 2 - f.heading, c = cosf(th), s = sinf(th);
  const float clip2 = (R + 10) * (R + 10);

  if (trackReady) {
    const float k = trackScale;
    auto toScreen = [&](int i, float &sx, float &sy) {
      float wx = trackPts[2 * i] * k - f.x, wy = trackPts[2 * i + 1] * k - f.y;
      sx = ax + (wx * c - wy * s) * sc;
      sy = ay - (wx * s + wy * c) * sc;
    };
    auto inside = [&](float sx, float sy) {
      float dx = sx - 120, dy = sy - 120;
      return dx * dx + dy * dy < clip2;
    };
    float x0 = 0, y0 = 0, x1, y1;

    // pit lane, thin and quiet (brighter while you're in it)
    uint16_t pitCol = (f.flags & 1) ? RGB565(150, 152, 160) : RGB565(85, 87, 95);
    for (int i = 0; i < trackPit; i++) {
      toScreen(trackMain + i, x1, y1);
      if (i > 0 && (inside(x0, y0) || inside(x1, y1))) g->drawLine(x0, y0, x1, y1, pitCol);
      x0 = x1; y0 = y1;
    }

    // the circuit
    int n = trackMain;
    float L = n * trackStep, span = f.ahead + 25.0f, sBack = f.s - 25.0f;
    toScreen(n - 1, x0, y0);
    for (int i = 0; i < n; i++) {
      toScreen(i, x1, y1);
      if (inside(x0, y0) || inside(x1, y1)) {
        float d = fmodf(i * trackStep - sBack + 2 * L, L);   // metres into the bright stretch
        uint16_t col = COL_MAP_TRACK;
        if (d < span) {
          float fr = d / span, b = fr < 0.55f ? 1.0f : 1.0f - (fr - 0.55f) / 0.45f;
          col = RGB565((int)(105 + 150 * b), (int)(108 + 147 * b), (int)(118 + 132 * b));
        }
        thickLine(g, x0, y0, x1, y1, col);
      }
      x0 = x1; y0 = y1;
    }

    // start / finish line across the circuit
    toScreen(0, x0, y0);
    toScreen(1, x1, y1);
    float dx = x1 - x0, dy = y1 - y0, len = sqrtf(dx * dx + dy * dy);
    if (len > 0.01f && inside(x0, y0)) {
      float nx = -dy / len * 6, ny = dx / len * 6;
      thickLine(g, x0 - nx, y0 - ny, x0 + nx, y0 + ny, COL_TEXT);
    }
  }

  // cover whatever spilled past the disc, then the bezel and the north mark
  g->fillArc(120, 120, 122, MAP_R + 1, 0, 360, COL_BG);
  g->drawCircle(120, 120, MAP_R, COL_BEZEL);
  g->setTextSize(1);
  g->setTextColor(COL_DIM);
  g->setCursor(120 - sinf(th) * (R - 9) - 3, 120 - cosf(th) * (R - 9) - 4);
  g->print('N');

  drawArrow(g, ax, ay, f.marker);
  g->flush();
}

// ---------------- Racing sim: right screen lap / position (Forza: no track outline, so no minimap) ----------------
// In a race: your position, the lap and its time, your best and last laps. Free roam: your speed, the
// car's class and PI, and the top speed of the drive. Redrawn only when what it shows changes.
void fmtLap(char *out, size_t n, float s) {   // 83.45 -> "1:23.45"
  if (s <= 0) { strlcpy(out, "-:--.--", n); return; }
  int m = (int)(s / 60);
  snprintf(out, n, "%d:%05.2f", m, s - m * 60);
}

uint16_t classColor(const char *c) {   // Forza's class badge colours
  if (!strcmp(c, "D")) return RGB565(60, 180, 230);
  if (!strcmp(c, "C")) return RGB565(240, 200, 40);
  if (!strcmp(c, "B")) return RGB565(250, 140, 30);
  if (!strcmp(c, "A")) return RGB565(230, 50, 50);
  if (!strcmp(c, "S1")) return RGB565(170, 80, 220);
  if (!strcmp(c, "S2")) return RGB565(40, 90, 220);
  return RGB565(60, 200, 90);   // X
}

void drawRaceInfo() {
  bool racing = race.pos || race.cur > 0;
  char key[64], buf[24], t[16];
  // the bottom two lines: the song playing, and Claude's status (the LED is the shift light now)
  char claude = claudeStatus ? claudeStatus : ledState;
  if (claude == 'Y') claude = 'D';
  bool showClaude = claude == 'W' || claude == 'A' || claude == 'D';
  const char *song = mediaActive && mPlaying ? mTitle : "";
  if (racing) snprintf(key, sizeof(key), "R%u %u %.2f %.2f %.2f", race.pos, race.lap, race.cur, race.best, race.last);
  else snprintf(key, sizeof(key), "F%u %s %u %u", simFrame.kmh, race.cls, race.pi, race.top);
  snprintf(key + strlen(key), sizeof(key) - strlen(key), "|%c|%.20s", showClaude ? claude : '-', song);
  if (!strcmp(key, raceShown)) return;
  strlcpy(raceShown, key, sizeof(raceShown));

  Arduino_Canvas *g = rightCanvas;
  g->fillScreen(COL_BG);
  g->fillCircle(120, 120, 119, RGB565(46, 46, 54));   // bezel and face, as the gauge's
  g->fillCircle(120, 120, 115, RGB565(12, 12, 16));
  if (racing) {
    if (race.pos) {
      snprintf(buf, sizeof(buf), "P%u", race.pos);
      drawCentered(g, buf, 30, 4, COL_ACCENT, 4, 1);
    }
    snprintf(buf, sizeof(buf), "LAP %u", race.lap + 1);
    drawCentered(g, buf, 72, 2, COL_DIM, 8, 1);
    fmtLap(t, sizeof(t), race.cur);
    drawCentered(g, t, 100, 3, COL_TEXT, 9, 1);
    fmtLap(t, sizeof(t), race.best);
    snprintf(buf, sizeof(buf), "BEST %s", t);
    drawCentered(g, buf, 146, 2, RGB565(70, 220, 110), 13, 1);
    fmtLap(t, sizeof(t), race.last);
    snprintf(buf, sizeof(buf), "LAST %s", t);
    drawCentered(g, buf, 172, 2, COL_TEXT, 13, 1);
  } else {
    if (race.cls[0]) {   // the class badge: "A 800"
      snprintf(buf, sizeof(buf), "%s %u", race.cls, race.pi);
      int w = strlen(buf) * 12 + 16;
      g->fillRoundRect(120 - w / 2, 38, w, 24, 6, classColor(race.cls));
      drawCentered(g, buf, 43, 2, COL_BG, 8, 1);
    }
    snprintf(buf, sizeof(buf), "%u", simFrame.kmh);
    drawCentered(g, buf, 82, 6, COL_TEXT, 4, 1);
    drawCentered(g, "KM/H", 140, 2, COL_DIM, 6, 1);
    if (race.top) {
      snprintf(buf, sizeof(buf), "TOP %u", race.top);
      drawCentered(g, buf, 172, 2, COL_ACCENT, 10, 1);
    }
  }
  if (song[0]) drawCentered(g, song, 196, 1, COL_DIM, 22, 1);
  if (showClaude) {
    snprintf(buf, sizeof(buf), "CLAUDE: %s", claude == 'W' ? "WORKING" : claude == 'A' ? "NEEDS YOU" : "DONE");
    drawCentered(g, buf, 208, 1, buddy::statusColor(claude), 20, 1);
  }
  g->flush();
}

// While driving, a notification or the volume takes the right screen for a moment (the designed
// cards, as on the other screens); redrawn only when what it shows changes
int simOver = 0;            // 0 none, 1 notification, 2 volume, 3 Claude's question
char simOverKey[80] = "";
uint32_t askAt = 0;         // when Claude's question arrived

void drawSimOver(uint32_t now, int over) {
  char key[80];
  if (over == 1) snprintf(key, sizeof(key), "N%s|%s|%s|%u", nApp, nTitle, nText, nCount);
  else if (over == 2) snprintf(key, sizeof(key), "V%d %d", mVolume, mMuted);
  else snprintf(key, sizeof(key), "A%s", ask.text);
  if (!strcmp(key, simOverKey)) return;
  strlcpy(simOverKey, key, sizeof(simOverKey));
  BuddyData d;
  fillBuddyData(d, now);
  if (over == 1) buddyDraw_idle_eyes_notfication_right(rightCanvas, d);
  else if (over == 2) buddyDraw_media_playing_volume_right(rightCanvas, d);
  else cs::askCard(rightCanvas, ask);
  rightCanvas->flush();
}

// ---------------- Modes ----------------
void enterEyes() {
  mode = MODE_EYES;
  leftEye.lid = rightEye.lid = 0;
  leftEye.state = rightEye.state = OPEN;
  resetVibration();
  drawFullEye(leftEye);
  drawFullEye(rightEye);
}

// The owner wants Claude (working, waiting, asking) and playing music shown over the racing pages:
// while either is on, the sim gives the screens and LED back, and its next frame after takes them again.
bool simYields() {
  char c = claudeStatus ? claudeStatus : ledState;
  return mPlaying || c == 'W' || c == 'A' || c == 'Y' || (ask.title[0] && ask.opt[0][0]);   // a question the buttons answer: until answered
}

// A driving session: the sim takes both screens and the LED
void enterSim() {
  if (mode != MODE_SIM) {
    Serial.println("Sim: session started");
    memset(&simFrame, 0, sizeof(simFrame));
    simFrame.radius = 300;
  }
  mode = MODE_SIM;
  buildGaugeBg();               // per car: turbo gauge or tacho, its own scale
  gaugeAngleShown = -1;
  raceShown[0] = 0;             // the lap screen draws afresh too
  simLastAt = millis();
  simDirty = true;
}

void exitSim() {
  if (mode != MODE_SIM) return;
  Serial.println("Sim: session over");
  mode = MODE_SCENE;            // first, so applyLed() shows the Claude colour again
  curScene = -1;                // loop() picks the scene (or the eyes) and redraws both screens
  applyLed(ledState);
}

// Splits "a\x1fb\x1fc" in place; returns field count.
int splitFields(char *s, char **out, int max) {
  int n = 0;
  out[n++] = s;
  for (char *p = s; *p && n < max; p++) {
    if (*p == 0x1f) { *p = 0; out[n++] = p + 1; }
  }
  return n;
}

void handleMsg(Msg &m) {
  char *d = m.data;
  if (m.len == 1 && strchr("WADOY", d[0])) { applyLed(d[0]); return; }

  // Racing sim (binary)
  if (d[0] == 'G' && m.len >= 1 + sizeof(SimCar)) {
    memcpy(&simCar, d + 1, sizeof(SimCar));
    if (!simYields()) enterSim();
    return;
  }
  if (d[0] == 'S' && m.len >= 1 + sizeof(SimFrame)) {
    if (mode != MODE_SIM && simCar.rpmMax > 0 && !simYields()) enterSim();
    memcpy(&simFrame, d + 1, sizeof(SimFrame));
    simLastAt = millis();
    simDirty = true;
    return;
  }
  if (d[0] == 'Q' && m.len == 1) { exitSim(); return; }
  if (d[0] == 'J') {   // what Claude is doing: J<what>␟<target>, or J alone when it stops
    char *r[2];
    int n = splitFields(d + 1, r, 2);
    strlcpy(activity.what, r[0], sizeof(activity.what));
    strlcpy(activity.target, n > 1 ? r[1] : "", sizeof(activity.target));
    return;
  }
  if (d[0] == '?') {   // Claude's question: ?<title>␟<text>[␟<option 1>␟<option 2>], or ? alone when it's answered
    char *r[4];
    int n = splitFields(d + 1, r, 4);
    strlcpy(ask.title, r[0], sizeof(ask.title));
    strlcpy(ask.text, n > 1 ? r[1] : "", sizeof(ask.text));
    for (int i = 0; i < 2; i++) strlcpy(ask.opt[i], n > 2 + i ? r[2 + i] : "", sizeof(ask.opt[i]));
    askAt = millis();
    return;
  }
  if (d[0] == 'M') {   // SolidWorks: M<document>␟<step>␟<steps done>␟<recent>␟<recent>␟<recent>
    char *r[3 + cs::RECENT];
    int n = splitFields(d + 1, r, 3 + cs::RECENT);
    if (n >= 3) {
      if (strcmp(r[0], solidWorks.doc)) modelValid = false;   // another model: no picture of the old one
      strlcpy(solidWorks.doc, r[0], sizeof(solidWorks.doc));
      strlcpy(solidWorks.step, r[1], sizeof(solidWorks.step));
      solidWorks.steps = atoi(r[2]);
      for (int i = 0; i < cs::RECENT; i++) strlcpy(solidWorks.recent[i], 3 + i < n ? r[3 + i] : "", sizeof(solidWorks.recent[i]));
      solidWorks.at = millis();
      if (!solidWorks.at) solidWorks.at = 1;
    }
    return;
  }
  if (d[0] == '@') {   // over USB: a screen's picture as it is drawn, to check a layout without looking at it
    Arduino_Canvas *c = d[1] == 'L' ? leftCanvas : rightCanvas;
    Serial.print("\nDUMP240\n");
    Serial.write((uint8_t *)c->getFramebuffer(), SCR * SCR * 2);
    Serial.flush();
    return;
  }
  if (d[0] == 'R') {   // Forza's lap / position (text)
    char *r[8];
    int n = splitFields(d + 1, r, 8);
    if (n >= 7) {
      race.pos = atoi(r[0]);
      race.lap = atoi(r[1]);
      race.cur = atof(r[2]);
      race.best = atof(r[3]);
      race.last = atof(r[4]);
      strlcpy(race.cls, r[5], sizeof(race.cls));
      race.pi = atoi(r[6]);
      race.top = n > 7 ? atoi(r[7]) : 0;
      simDirty = true;
    }
    return;
  }

  // Everything else only updates the data; loop() picks and draws the scene for it
  char *f[4 + 3 * ff::ROWS];
  switch (d[0]) {
    case 'N': {
      int n = splitFields(d + 1, f, 4);
      strlcpy(mTitle,  n > 0 ? f[0] : "", sizeof(mTitle));
      strlcpy(mArtist, n > 1 ? f[1] : "", sizeof(mArtist));
      strlcpy(mApp,    n > 2 ? f[2] : "", sizeof(mApp));
      mSpin = n > 3 ? f[3][0] == '1' : true;
      coverValid = false;      // placeholder record until the cover arrives
      vinylAngle = 0;
      mPosMs = mDurMs = 0;
      mPosAt = millis();
      mediaActive = true;
      break;
    }
    case 'P': {
      int n = splitFields(d + 1, f, 3);
      if (n == 3) {
        mPlaying = f[0][0] == '1';
        mPosMs = strtoul(f[1], nullptr, 10);
        mDurMs = strtoul(f[2], nullptr, 10);
        mPosAt = millis();
      }
      break;
    }
    case 'V': {
      int n = splitFields(d + 1, f, 2);
      if (n == 2) {
        int vol = atoi(f[0]);
        bool muted = f[1][0] == '1';
        // the first one, and the helper's resend after a reconnect, aren't changes
        if (mVolume >= 0 && (vol != mVolume || muted != mMuted)) volumeShownAt = millis();
        mVolume = vol;
        mMuted = muted;
      }
      break;
    }
    case 'X':
      mediaActive = false;
      mPlaying = false;
      break;
    case 'T': {
      int n = splitFields(d + 1, f, 5);
      strlcpy(nApp,   n > 0 ? f[0] : "", sizeof(nApp));
      strlcpy(nTitle, n > 1 ? f[1] : "", sizeof(nTitle));
      strlcpy(nText,  n > 2 ? f[2] : "", sizeof(nText));
      nCount = n > 3 ? max(1, atoi(f[3])) : 1;
      strlcpy(nTime,  n > 4 ? f[4] : "", sizeof(nTime));
      showNotification();
      break;
    }
    case 'F': {
      int n = splitFields(d + 1, f, 10);
      if (n == 10) {
        fWeek = atoi(f[0]);
        strlcpy(fMyTeam, f[1], sizeof(fMyTeam));
        strlcpy(fOppTeam, f[2], sizeof(fOppTeam));
        fMyScore = atof(f[3]);
        fOppScore = atof(f[4]);
        fMyProj = atof(f[5]);
        fOppProj = atof(f[6]);
        strlcpy(fRecord, f[7], sizeof(fRecord));
        fRank = atoi(f[8]);
        bool wasLive = fLive;
        fLive = f[9][0] == '1';
        ff::onMatchup(fWeek, fOppTeam, fMyScore, fOppScore);   // for the lead chart
        if (fLive != wasLive) ancsNote(fLive ? "Fantasy: games on" : "Fantasy: no games on");
        if (fLive && !wasLive) fantasyAlert();
      }
      break;
    }
    case 'L': {
      int n = splitFields(d + 1, f, 4 + 3 * ff::ROWS);
      if (n >= 4) ff::onLeague(f, n);
      break;
    }
    case 'K': {
      int n = splitFields(d + 1, f, 5);
      if (n >= 3) {
        clockSec = atoi(f[0]) * 3600UL + atoi(f[1]) * 60UL + atoi(f[2]);
        clockAt = millis();
        clockKnown = true;
        strlcpy(clockDate, n > 3 ? f[3] : "", sizeof(clockDate));
        if (n > 4) ff::day = strtoul(f[4], nullptr, 10);   // picks the fantasy style of the day
      }
      break;
    }
    case 'U': {
      int n = splitFields(d + 1, f, 5);
      if (n == 5) {
        claudeStatus = f[0][0] ? f[0][0] : 'O';
        claudeSessionMs = strtoul(f[1], nullptr, 10);
        claudeAt = millis();
        claudeTokens = strtoul(f[2], nullptr, 10);
        int s = atoi(f[3]), w = atoi(f[4]);   // -1 = not known yet
        claudeSession = s < 0 ? 0 : min(s, 100);
        claudeWeekly = w < 0 ? 0 : min(w, 100);
        claudeSessionKnown = s >= 0;
        claudeWeeklyKnown = w >= 0;
        Serial.printf("Claude: %c, session %lus, %lu tokens, usage %d%% / %d%%\n", claudeStatus,
                      claudeSessionMs / 1000, claudeTokens, s, w);
      }
      break;
    }
  }
}

// ---------------- Firmware updates over Bluetooth ----------------
// The app has two slots: the new firmware goes in the one not running, and only starts once it's all
// written. Until it has run OTA_HEALTHY_MS, otaTries counts its boots; three that crash go back to the old slot.
void otaProgress(const char *title, uint32_t done, uint32_t total) {
  static uint32_t lastAt = 0;
  if (millis() - lastAt < 200 && done != total) return;
  lastAt = millis();
  char t[12];
  snprintf(t, sizeof t, "%u%%", (unsigned)(total ? (uint64_t)done * 100 / total : 0));
  for (Arduino_Canvas *g : {leftCanvas, rightCanvas}) {
    g->fillScreen(COL_BG);
    buddy::ring(g, 120, 120, 112, 10, 0.0f, 360.0f, COL_IRIS, true, COL_TRACK, total ? (float)done / total : 0);
    drawCentered(g, title, 86, 2, COL_DIM, 14, 1);
    drawCentered(g, t, 112, 4, COL_TEXT, 5, 1);
    g->flush();
  }
}

void otaClose() {
  otaState = 0;
  free(otaBuf);
  otaBuf = nullptr;
  mode = MODE_SCENE;     // the screens went to the progress ring: loop() picks what's next afresh
  curScene = -1;
}

bool otaSigned() {
  uint8_t mac[32];
  const mbedtls_md_info_t *info = mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
  return mbedtls_md_hmac(info, OTA_KEY, sizeof(OTA_KEY), otaBuf, otaSize, mac) == 0
      && !memcmp(mac, otaSig, sizeof(mac));
}

void otaInstall() {
  Serial.printf("Update: %lu bytes here, checking\n", (unsigned long)otaSize);
  otaProgress("CHECKING", 0, 1);
  bool ok = otaSigned();
  if (!ok) Serial.println("Update: wrong signature");
  if (ok) ok = Update.begin(otaSize, U_FLASH);
  for (uint32_t at = 0; ok && at < otaSize; at += 4096) {
    uint32_t n = min((uint32_t)4096, otaSize - at);
    ok = Update.write(otaBuf + at, n) == n;
    otaProgress("INSTALLING", at + n, otaSize);
  }
  if (ok) ok = Update.end(true);
  else Update.abort();
  sendTouch(ok ? 'u' : 'x');
  if (!ok) {
    Serial.printf("Update: failed (%s)\n", Update.errorString());
    otaClose();
    return;
  }
  Serial.println("Update: installed, restarting");
  otaTries = OTA_TRIES_MAGIC;
  delay(500);
  ESP.restart();
}

// Only touches anything right after an update
void otaBootCheck() {
  if ((otaTries & 0xFFFFFF00) != OTA_TRIES_MAGIC) return;
  uint32_t tries = otaTries & 0xFF;
  if (tries >= 3) {
    otaTries = 0;
    const esp_partition_t *old = esp_ota_get_next_update_partition(nullptr);
    Serial.println("Update: the new firmware keeps crashing, going back");
    if (old) esp_ota_set_boot_partition(old);
    ESP.restart();
  }
  otaTries = OTA_TRIES_MAGIC | (tries + 1);
}

// ---------------- Touch ----------------
// Both sensors at once = mute / unmute, any time but while racing. Until both are let go,
// neither press counts as a tap or a volume hold.
bool bothDown = false;
uint32_t anyTouchAt = 0;   // last time either sensor read touched

void updateMuteChord(uint32_t now) {
  bool l = isTouched(TOUCH_LEFT_PIN, now), r = isTouched(TOUCH_RIGHT_PIN, now);
  reportTouchSpikes(now);
  if (l || r) anyTouchAt = now;
  if (l && r) {
    if (!bothDown) {
      bothDown = true;
      sendTouch('m');
      Serial.println("Touch: mute");
    }
  } else if (bothDown && now - anyTouchAt >= TOUCH_RELEASE_MS) {
    bothDown = false;   // both let go (longer than a flicker)
  }
}

// Music playing or paused: tap left = play/pause, tap right = next, hold left/right = volume down/up (repeats).
// On the fantasy pages: tap right = next page, tap left = back ('>' / '<', handled here; no holds).
// A TTP223 can flicker as a finger lands or shifts, which used to cut a hold short and turn the rest
// into a tap (pausing or skipping). Now a press only ends TOUCH_RELEASE_MS after the sensor last read
// touched, its length counts only the time actually touched, and for AFTER_VOLUME_MS after a volume
// hold a touch can only carry on with the volume.
void updateTouch(Touch &t, char tapAction, char holdAction, uint32_t now) {
  const char *side = t.pin == TOUCH_LEFT_PIN ? "left" : "right";
  bool touched = isTouched(t.pin, now);
  if (touched && !t.wasTouched && t.down)
    Serial.printf("Touch: %s flickered off for %lu ms (ignored)\n", side, (unsigned long)(now - t.touchedAt));
  t.wasTouched = touched;
  if (touched) t.touchedAt = now;
  if (touched && !t.down) {
    t.down = true;
    t.downAt = now;
    t.volume = false;
    t.held = bothDown || (t.volumeEndAt && now - t.volumeEndAt < AFTER_VOLUME_MS);
  } else if (t.down && now - t.touchedAt < TOUCH_RELEASE_MS) {   // still pressed
    if (bothDown) t.held = true;   // part of a mute
    // volume steps only while actually touched, so the release window adds none after letting go
    else if (holdAction && touched && t.touchedAt - t.downAt >= TAP_MAX_MS && now - t.lastRepeat >= VOLUME_REPEAT_MS) {
      if (!t.volume) Serial.printf("Touch: %s hold (volume %s)\n", side, holdAction == '+' ? "up" : "down");
      t.held = t.volume = true;
      t.lastRepeat = now;
      sendTouch(holdAction);
    }
  } else if (t.down) {   // let go
    t.down = false;
    if (t.volume) t.volumeEndAt = now;
    uint32_t len = t.touchedAt - t.downAt;
    if (!t.held && len >= TAP_MIN_MS) {
      Serial.printf("Touch: %s tap (%lu ms)\n", side, (unsigned long)len);
      if (tapAction == '>' || tapAction == '<') fantasyFlip(tapAction == '>' ? 1 : -1);
      else sendTouch(tapAction);
    }
  }
}

// ---------------- Setup / loop ----------------
void setup() {
  Serial.begin(115200);
  otaBootCheck();
  setColor(0, 0, 0);

  pinMode(TOUCH_LEFT_PIN, INPUT_PULLUP);    // buttons to GND
  pinMode(TOUCH_RIGHT_PIN, INPUT_PULLUP);
#if VIB_PIN >= 0
  pinMode(VIB_PIN, INPUT_PULLUP);   // the module has its own pull-up; this one just keeps an unplugged pin quiet
  attachInterrupt(digitalPinToInterrupt(VIB_PIN), onVibration, CHANGE);
#endif

  if (!gfxL->begin(SPI_HZ)) Serial.println("Left GC9A01 init failed");
  if (!gfxR->begin(SPI_HZ)) Serial.println("Right GC9A01 init failed");
  gfxL->fillScreen(COL_BG);
  gfxR->fillScreen(COL_BG);

  if (!psramFound()) {
    Serial.println("PSRAM not found - set Tools > PSRAM to \"OPI PSRAM\"");
    gfxR->setTextSize(2);
    gfxR->setTextColor(RGB565(255, 80, 80));
    gfxR->setCursor(30, 110);
    gfxR->print("Enable OPI PSRAM");
    while (true) delay(1000);
  }
  cover  = (uint16_t *)ps_malloc(SCR * SCR * 2);
  modelPic = (uint16_t *)ps_malloc(SCR * SCR * 2);
  jpgBuf = (uint8_t *)ps_malloc(JPG_MAX);
  rightCanvas = new Arduino_Canvas(SCR, SCR, gfxR);
  rightCanvas->begin(GFX_SKIP_OUTPUT_BEGIN);
  leftCanvas = new Arduino_Canvas(SCR, SCR, gfxL);
  leftCanvas->begin(GFX_SKIP_OUTPUT_BEGIN);
  buddy::onEye = [](Arduino_GFX *g) { drawnEyes |= g == leftCanvas ? 1 : g == rightCanvas ? 2 : 0; };
  shownL   = (uint16_t *)ps_malloc(SCR * SCR * 2);
  shownR   = (uint16_t *)ps_malloc(SCR * SCR * 2);
  gaugeBg  = (uint16_t *)ps_malloc(SCR * SCR * 2);
  mapBg    = (uint16_t *)ps_malloc(SCR * SCR * 2);
  trackPts = (int16_t *)ps_malloc(TRACK_MAX * 4);
  buildMapBg();

  msgQueue = xQueueCreate(24, sizeof(Msg));

  leftEye.gfx  = gfxL;
  rightEye.gfx = gfxR;

  randomSeed(esp_random());
  drawFullEye(leftEye);
  drawFullEye(rightEye);

  setupBLE();
  lastFrame = millis();
}

void loop() {
  // Bluetooth messages and cover art
  Msg m;
  while (xQueueReceive(msgQueue, &m, 0) == pdTRUE) handleMsg(m);
  if (jpgReady) decodeCover();

  // USB serial still works for the LED. A line starting with '>' is handled like a Bluetooth message,
  // to try screens without the PC helper (e.g. a fantasy matchup: ">F8" 0x1F "My team" 0x1F ...)
  static Msg typed;
  static bool typing = false;
  while (Serial.available()) {
    char c = Serial.read();
    if (typing) {
      if (c == '\n' || c == '\r') {
        typing = false;
        typed.data[typed.len] = 0;
        if (typed.len) handleMsg(typed);
      } else if (typed.len < sizeof(typed.data) - 1) {
        typed.data[typed.len++] = c;
      }
    } else if (c == '>') {
      typing = true;
      typed.len = 0;
    } else if (strchr("WADOY", c)) {
      applyLed(c);
    }
  }

  uint32_t now = millis();
  updateAdvertising(now);
  ancsSendNotes();
  updateLed(now);

  if (otaTries && now > OTA_HEALTHY_MS && (otaTries & 0xFFFFFF00) == OTA_TRIES_MAGIC) {
    otaTries = 0;   // the new firmware works
    Serial.println("Update: running fine");
  }
  if (otaState == 2) {
    otaInstall();
    return;
  }
  if (otaState == 1) {
    // signed: the Bluetooth task can set otaLastAt just after 'now' was read, and that isn't a long silence
    if ((int32_t)(now - otaLastAt) > (int32_t)OTA_QUIET_MS) {
      ancsNote("Update: dropped after %lu of %lu bytes", (unsigned long)otaGot, (unsigned long)otaSize);
      otaClose();
    } else {
      otaProgress("RECEIVING", otaGot, otaSize);
    }
    return;
  }

  if (now - lastFrame < FRAME_MS) return;
  float dt = min(50.0f, (float)(now - lastFrame));
  lastFrame = now;

  if (mode == MODE_SIM) {
    vibEdges = 0;   // no dizzy eyes while driving
    updateMuteChord(now);   // the touch sensors still work the music while driving
    if (mediaActive) {
      updateTouch(touchL, 'p', '-', now);
      updateTouch(touchR, 'n', '+', now);
    }
    if (now - simLastAt > SIM_TIMEOUT_MS || simYields()) {
      exitSim();    // the game went quiet (closed, crashed, or the PC helper stopped), or Claude / music comes first
      return;
    }
    int over = notifUntil && (int32_t)(notifUntil - now) > 0 ? 1
             : volumeShownAt && now - volumeShownAt < VOLUME_SHOW_MS ? 2
             : ask.title[0] && now - askAt < ASK_DRIVING_MS ? 3 : 0;
    if (over != simOver) {   // the right screen changes over: draw whichever is next afresh
      simOver = over;
      simOverKey[0] = raceShown[0] = 0;
      simDirty = true;
    }
    if (simDirty) {
      simDirty = false;
      drawGauge();
      if (over) drawSimOver(now, over);
      else if (simFrame.flags & 4) drawRaceInfo();   // Forza: lap / position in place of the minimap
      else drawMinimap();
    } else if (over) {
      drawSimOver(now, over);   // a new count or volume between frames
    } else if (simFrame.flags & 4) {
      drawRaceInfo();           // the song or Claude changed between frames
    }
    return;
  }

  // Touch: both at once mutes; media controls while something is playing or paused, blinks otherwise
  updateMuteChord(now);
  if (mode == MODE_SCENE && askShows(now) && ask.opt[0][0]) {   // Claude's buttons: left = top, right = bottom
    updateTouch(touchL, '1', 0, now);
    updateTouch(touchR, '2', 0, now);
  } else if (mediaActive) {
    updateTouch(touchL, 'p', '-', now);
    updateTouch(touchR, 'n', '+', now);
  } else if (mode == MODE_SCENE && curScene >= ff::SCENE_FIRST) {   // the fantasy pages: flip through them
    updateTouch(touchL, '<', 0, now);
    updateTouch(touchR, '>', 0, now);
  } else {
    updateEye(leftEye, now, dt);
    updateEye(rightEye, now, dt);
    touchL.down = touchR.down = false;
  }
  if (mSpin && mPlaying) {
    vinylAngle += dt * VINYL_RPM * 2 * PI / 60000.0f;
    if (vinylAngle > 2 * PI) vinylAngle -= 2 * PI;
  }

  int scene = pickScene(now);
  if (notifToReport) {
    notifToReport = false;
    char named[40];
    if (scene >= ff::SCENE_FIRST) ancsNote("Shown with fantasy %s", ff::name(scene, named, sizeof named));
    else ancsNote("Shown in scene %d", scene);
  }
  if (scene == BUDDY_SCENE_IDLE_EYES) {
    // The plain eyes: the sketch's own, which redraw only what moved and go dizzy when shaken
    if (mode != MODE_EYES) {
      printSceneStats();
      Serial.println("Scene: idle eyes");
      enterEyes();
      curScene = scene;
    }
    updateVibration(now, dt);
    updateGaze(now, dt);
    refreshEye(leftEye);
    refreshEye(rightEye);
    return;
  }

  vibEdges = 0;     // the dizzy shake is the plain eyes' trick
  updateGaze(now, dt);   // a scene's eyes look around too
  if (mode != MODE_SCENE || scene != curScene) {
    printSceneStats();
    char named[32];
    if (scene >= ff::SCENE_FIRST) Serial.printf("Scene: %d (fantasy %s)\n", scene, ff::name(scene, named, sizeof named));
    else Serial.printf("Scene: %d\n", scene);
    if (mode == MODE_EYES) resetVibration();
    mode = MODE_SCENE;
    curScene = scene;
    sceneForce = true;  // the screens show something else: send both
    eyeSides = 0;       // not known for this scene until it has drawn a frame
    drawScene(now);
  } else if (now - lastSceneDraw >= SCENE_FRAME_MS) {
    drawScene(now);
  }
}
