"""Desk Buddy PC helper: keeps a Bluetooth LE connection to the ESP32 and feeds it everything.

  - Status LED: hooks send "<letter>\t<transcript path>\t<hook details as JSON>\n" (W/A/D/O) to
    127.0.0.1:47800 and get back b"1" if it reached the board over Bluetooth, or b"0" so the hook
    can fall back to USB. The details say what Claude is doing, asking, or building in SolidWorks.
  - Turns Claude's light off while the Claude app's window is closed, back on when it reopens.
  - Switches to green when you stop a prompt (no hook fires for that, so it watches the transcript).
  - Flashes green / orange for 30 s when Claude finishes with a question for you (the Claude app's
    next-step box with buttons), then green. Your next message stops it sooner.
  - Watches Lightroom Classic: busy (export, Denoise / AI) pulses white, then green when done.
    When Claude and Lightroom are both active, "busy wins": orange if Claude needs you, else white
    if either is working, else green if either has finished, else off.
  - Media: whatever shows in the Windows media flyout (Spotify, YouTube in a browser, VLC...):
    title, artist, app, cover / thumbnail, play state, position, plus the master volume.
    In a browser, the app is "YouTube" / "YouTube Music" for those sites, else the browser's name.
  - Phone notifications that Phone Link shows on the PC (WhatsApp, Messages, Snapchat...): app, sender
    and message, read from Windows' notification history.
  - Touch sensors on the buddy control media: play/pause, next, volume up/down.
  - Racing sim (Nishan Sim's game/deskbuddy.py sends UDP to 127.0.0.1:47801): boost gauge / tacho,
    minimap and shift light, forwarded to the board while a driving session runs.
  - Forza (Horizon 4 / 5, Motorsport 7) "Data Out" telemetry on UDP 127.0.0.1:5300: the same tacho
    (with gear and speed) and shift light, and a lap / position screen in place of the minimap.
  - ESPN fantasy basketball (head-to-head points): your matchup this week (teams, live scores,
    projections, record, rank) and the top of the standings, set up in fantasy.json.

Run with pythonw so no window shows.
Requires: pip install bleak psutil pillow pycaw winrt-Windows.Media.Control
Run "python claude-led-ble.py --test-media" to print what it sees without Bluetooth,
"--test-notifications" to print phone notifications as they arrive, "--test-fantasy" to check
your ESPN league once, or "--test-forza" to print what Forza sends.
"""
import sys

# pycaw (via comtypes) would otherwise put this thread in a single-threaded COM apartment, which
# stops WinRT async calls (e.g. reading the cover art) from ever completing. Must be set before import.
sys.coinit_flags = 0   # COINIT_MULTITHREADED

import asyncio
import ctypes
import glob
import hashlib
import hmac
import io
import json
import os
import re
import struct
import subprocess
import tempfile
import time
import unicodedata
import urllib.error
import urllib.request
from collections import deque
from ctypes import wintypes
from datetime import datetime, timezone

import psutil
from bleak import BleakClient, BleakScanner

DEVICE_NAME = "Desk Buddy 0A69"   # must match the sketch
CMD_UUID = "0cd20002-355a-4a08-8be1-4e7212f9c170"     # LED status + media text (write)
IMG_UUID = "0cd20003-355a-4a08-8be1-4e7212f9c170"     # cover art JPEG chunks (write)
TOUCH_UUID = "0cd20004-355a-4a08-8be1-4e7212f9c170"   # touch actions from the buddy (notify)
TRACK_UUID = "0cd20005-355a-4a08-8be1-4e7212f9c170"   # racing sim minimap outline (write)
OTA_UUID = "0cd20006-355a-4a08-8be1-4e7212f9c170"     # firmware updates (write)
LISTEN_PORT = 47800
SIM_PORT = 47801                 # telemetry from the racing sim
SIM_TIMEOUT_SECONDS = 3.0        # no frames this long -> the session is over (game closed or crashed)
FORZA_PORT = 5300                # Forza's "Data Out" (Horizon 4 / 5, Motorsport 7): set the game to 127.0.0.1, this port
FORZA_SHIFT = (0.75, 0.92)       # shift light: yellow from this share of the rev limit, flashing red from this one
FORZA_CLASSES = ("D", "C", "B", "A", "S1", "S2", "X")
CHECK_SECONDS = 0.5
INTERRUPT_MARKER = b"[Request interrupted by user"
ASK_FLASH_SECONDS = 30           # Claude finished with a question for you: the LED flashes green / orange this long
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "claude-led-ble.log")
HIDDEN_TOOLS = ("mcp__ccd_", "ToolSearch", "TodoWrite")   # Claude's own housekeeping: not shown as what it's doing
SW_FRAME_SECONDS = 0.1           # the live picture of the SolidWorks model: at most 10 frames a second
SW_IDLE_FRAME_SECONDS = 1.0      # and one a second once it has been still for SW_STILL_SECONDS
SW_STILL_SECONDS = 10
SW_POLL_SECONDS = 2              # how often to look whether Claude is busy and SolidWorks is open
SW_BUILD_SECONDS = 1200          # a build's quiet spells: the pages hold this long while Claude is busy
SW_FRAME_WIDTH = 900             # SolidWorks draws each frame this wide
SW_QUALITY = 60                  # JPEG quality of a frame: lower = smaller = more frames over Bluetooth
SW_MASK_SIZE = 160               # the model is cut out at this size: Python's flood fill sets the frame rate
SW_ANSWER_SECONDS = 60           # SolidWorks can be busy this long (a heavy rebuild) before a frame is given up on
SW_SHOW_SECONDS = 120            # the board's SW_SHOW_MS: the pages stay up this long after the last step
SW_NEW_BUILD_SECONDS = 600       # no step this long: the next one starts counting from 1
SW_FILL = 0.7                    # the model fills this share of the round screen's width
SW_TURN_TO_ISOMETRIC = True      # False = picture SolidWorks' view as it is, without turning it
SW_EDGE = 40                    # brightness jump (0-255) that counts as the model's outline
SW_LOOK_ONLY = ("get_", "list_", "find_", "capture_", "recognize_", "check_", "look_at", "activate_")   # not build steps
SW_CAPTURE_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sw-capture.ps1")
SW_PICTURE = os.path.join(tempfile.gettempdir(), "deskbuddy-model.bmp")
FIRMWARE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "firmware")
FIRMWARE_FILE = os.path.join(FIRMWARE_DIR, "update.bin")      # update-board.ps1 puts a new firmware here
FIRMWARE_LOG = os.path.join(FIRMWARE_DIR, "update.log")
OTA_KEY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ota_key.txt")   # the board has the same key
OTA_ANSWER_SECONDS = 120         # the board checks and installs it in this long

# Lightroom Classic "busy" detection - tune these if it triggers too easily or not enough
LIGHTROOM_EXE = "lightroom.exe"
LR_BUSY_CPU = 1000.0             # % of one CPU core; idle 0-130%, scrolling ~450% avg, export bursts ~1200%
LR_BUSY_IO = 10_000_000          # bytes/s written/sent; idle ~20 KB/s, scrolling 1-3 MB/s, export ~40 MB/s
LR_BUSY_GPU = 30.0               # % GPU compute (Denoise and other AI tools run here, ~90%)
LR_WINDOW_SECONDS = 5            # average over this long, so short blips don't count
LR_IDLE_SECONDS = 8              # must stay quiet this long before it counts as finished

# Media
PAUSED_TO_EYES_SECONDS = 30      # paused this long -> buddy goes back to its eyes
VOLUME_STEP = 0.04               # per touch-and-hold step
COVER_SIZE = 240
COVER_QUALITY = 80               # JPEG quality sent to the board
BROWSERS = ("Chrome", "Edge", "Firefox", "Opera", "Brave", "Vivaldi")   # thumbnails don't spin
BROWSER_EXES = {"chrome.exe", "msedge.exe", "firefox.exe", "opera.exe", "brave.exe", "vivaldi.exe"}
# Sites told apart inside a browser by the tab title ("<video> - YouTube"), checked in this order
SITES = ((" - YouTube Music", "YouTube Music"), (" - YouTube", "YouTube"))
SEP = "\x1f"

# Phone notifications (Phone Link must show notification banners on the PC)
NOTIFICATIONS = True             # False = never send phone notifications to the buddy
NOTIFY_SHOW_TEXT = True          # False = only the app and sender, never the message itself
NOTIFY_IGNORE = ()               # app names to skip, e.g. ("Instagram", "TikTok")
NOTIFY_REPEAT_WINDOW = 60        # the same notification again within this many seconds = a repeat (counted)
NOTIFY_COUNT_EVERY = 4           # while repeats keep coming, send the new count at most this often
NOTIFY_DB = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Windows\Notifications\wpndatabase.db")
# ESPN fantasy basketball (a head-to-head points league): your league id (and, for a private league,
# the espn_s2 / SWID cookies) go in fantasy.json next to this file. ESPN's fantasy data isn't an
# official API, so it can change.
FANTASY = True                   # False = never check ESPN
FANTASY_SETTINGS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fantasy.json")
FANTASY_LIVE_EVERY = 60          # seconds between checks while NBA games are on
FANTASY_IDLE_EVERY = 600         # and the rest of the time
FANTASY_URL = ("https://lm-api-reads.fantasy.espn.com/apis/v3/games/fba/seasons/{season}/segments/0/leagues/{league}"
               "?view=mTeam&view=mMatchupScore&view=mStatus")
NBA_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
# Phone app ids (Android package / iPhone bundle) -> the names the Screen Designer knows
PHONE_APPS = {
    "com.whatsapp": "WhatsApp", "net.whatsapp.WhatsApp": "WhatsApp",
    "com.google.android.apps.messaging": "Messages", "com.samsung.android.messaging": "Messages",
    "com.apple.MobileSMS": "Messages",
    "com.snapchat.android": "Snapchat", "com.toyopagroup.picaboo": "Snapchat",
    "com.instagram.android": "Instagram", "com.burbn.instagram": "Instagram",
    "com.facebook.orca": "Messenger", "com.facebook.Messenger": "Messenger",
    "org.telegram.messenger": "Telegram", "ph.telegra.Telegraph": "Telegram",
    "com.google.android.gm": "Gmail", "com.google.Gmail": "Gmail",
    "com.apple.mobilemail": "Mail", "com.microsoft.office.outlook": "Outlook",
    "com.google.android.dialer": "Phone", "com.samsung.android.dialer": "Phone",
    "com.apple.mobilephone": "Phone", "com.apple.facetime": "FaceTime",
    "com.zhiliaoapp.musically": "TikTok", "com.ss.iphone.ugc.Ame": "TikTok",
    "com.microsoft.teams": "Teams", "com.Slack": "Slack", "com.tinyspeck.chatlyio": "Slack",
    "com.discord": "Discord", "com.hammerandchisel.discord": "Discord",
    "com.spotify.music": "Spotify", "com.google.android.youtube": "YouTube", "com.google.ios.youtube": "YouTube",
    "com.apple.Preferences": "Settings", "com.apple.Health": "Health", "com.apple.Passbook": "Wallet",
    "com.apple.mobiletimer": "Clock", "com.apple.reminders": "Reminders", "com.apple.mobilecal": "Calendar",
    "com.apple.findmy": "Find My", "com.apple.shortcuts": "Shortcuts", "com.apple.AppStore": "App Store",
    "com.life360.safetymap": "Life360", "net.blip.ios": "Blip", "com.ubercab.UberClient": "Uber",
    "com.google.Classroom": "Classroom", "com.theweathernetwork.weathereyeiphone": "Weather Network",
    "com.pratikstephen.StepUp": "StepUp",
}

client: BleakClient | None = None
claude_state = b"D"   # shown when Claude opens before any hook has fired
claude_open = False
lr_state = b"O"       # O = closed / never busy, W = busy, D = finished
shown = b""           # last color sent to the board
transcript = ""       # transcript of the session that sent the latest hook
transcript_pos = 0
running: dict[str, list] = {}   # sessions still working, oldest first: transcript -> [read up to, W or A]
RUNNING_QUIET_SECONDS = 1800    # a session whose transcript is this quiet is gone (closing one fires no hook)
ask_until = 0.0       # monotonic time the "asked you something" flashing stops
activity_msg = b"J"   # what the board last heard Claude is doing
ask_msg = b"?"        # and what it's asking
ask_options = ()      # its reply buttons, which the board's buttons pick
ask_path = ""         # the transcript of the chat that asked
ota_answer: asyncio.Future | None = None   # the board's answer to a firmware update

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def log_line(where: str, text: str) -> None:
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [{where}] {text}\n")
    except OSError:
        pass


def log_error(where: str) -> None:
    import traceback
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [{where}]\n{traceback.format_exc()}\n")
    except OSError:
        pass


# ---------------------------------------------------------------- Claude window

def _process_path(pid: int) -> str:
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(len(buf))
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return buf.value
        return ""
    finally:
        kernel32.CloseHandle(handle)


def is_claude_window_open() -> bool:
    """True if the Claude desktop app has a visible window (minimized still counts)."""
    found = False

    def callback(hwnd, _):
        nonlocal found
        if user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd) > 0:
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            path = _process_path(pid.value).lower()
            # Microsoft Store install (WindowsApps\Claude_...) or the regular installer (AnthropicClaude)
            if path.endswith("\\claude.exe") and ("\\windowsapps\\claude_" in path or "\\anthropicclaude\\" in path):
                found = True
                return False
        return True

    user32.EnumWindows(EnumWindowsProc(callback), 0)
    return found


# ---------------------------------------------------------------- Lightroom

class _PdhValue(ctypes.Structure):
    _fields_ = [("CStatus", wintypes.DWORD), ("doubleValue", ctypes.c_double)]


class _PdhItem(ctypes.Structure):
    _fields_ = [("szName", wintypes.LPWSTR), ("FmtValue", _PdhValue)]


class GpuSampler:
    """Reads per-process GPU compute usage from Windows performance counters."""

    def __init__(self) -> None:
        self.pdh = ctypes.windll.pdh
        self.query = ctypes.c_void_p()
        self.counter = ctypes.c_void_p()
        self.ok = (
            self.pdh.PdhOpenQueryW(None, 0, ctypes.byref(self.query)) == 0
            and self.pdh.PdhAddEnglishCounterW(
                self.query, r"\GPU Engine(*)\Utilization Percentage", 0, ctypes.byref(self.counter)) == 0
        )
        if self.ok:
            self.pdh.PdhCollectQueryData(self.query)

    def compute_percent(self, pids: set[int]) -> float:
        """Total compute-engine utilization (%) for the given process IDs."""
        if not self.ok or self.pdh.PdhCollectQueryData(self.query) != 0:
            return 0.0
        size, count = wintypes.DWORD(0), wintypes.DWORD(0)
        PDH_FMT_DOUBLE = 0x200
        self.pdh.PdhGetFormattedCounterArrayW(self.counter, PDH_FMT_DOUBLE, ctypes.byref(size), ctypes.byref(count), None)
        if not size.value:
            return 0.0
        buf = (ctypes.c_byte * size.value)()
        if self.pdh.PdhGetFormattedCounterArrayW(self.counter, PDH_FMT_DOUBLE, ctypes.byref(size), ctypes.byref(count), buf) != 0:
            return 0.0
        items = ctypes.cast(buf, ctypes.POINTER(_PdhItem))
        tags = {f"pid_{pid}_" for pid in pids}
        total = 0.0
        for i in range(count.value):
            name = (items[i].szName or "").lower()
            if "engtype_compute" in name and any(tag in name for tag in tags):
                total += items[i].FmtValue.doubleValue
        return total


class LightroomWatcher:
    """Samples Lightroom Classic's CPU, I/O and GPU to tell when it's busy."""

    def __init__(self) -> None:
        self.samples: deque[tuple[float, float, int]] = deque()  # (time, cpu seconds, io bytes)
        self.gpu_samples: deque[tuple[float, float]] = deque()   # (time, gpu compute %)
        self.gpu = GpuSampler()
        self.last_busy = 0.0
        self.pids: set[int] = set()

    def _totals(self) -> tuple[float, int] | None:
        procs = [p for p in psutil.process_iter(["name"]) if (p.info["name"] or "").lower() == LIGHTROOM_EXE]
        if not procs:
            return None
        cpu, io_bytes = 0.0, 0
        self.pids = {p.pid for p in procs}
        for p in procs:
            for q in [p, *p.children(recursive=True)]:
                try:
                    t = q.cpu_times()
                    c = q.io_counters()
                    cpu += t.user + t.system
                    io_bytes += c.write_bytes + c.other_bytes
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        return cpu, io_bytes

    def poll(self) -> bytes:
        global lr_state
        totals = self._totals()
        now = time.monotonic()
        if totals is None:
            self.samples.clear()
            self.gpu_samples.clear()
            lr_state = b"O"
            return lr_state

        self.samples.append((now, *totals))
        self.gpu_samples.append((now, self.gpu.compute_percent(self.pids)))
        while now - self.samples[0][0] > LR_WINDOW_SECONDS:
            self.samples.popleft()
        while now - self.gpu_samples[0][0] > LR_WINDOW_SECONDS:
            self.gpu_samples.popleft()
        t0, cpu0, io0 = self.samples[0]
        span = now - t0
        if span >= 1:
            cpu_pct = (totals[0] - cpu0) / span * 100
            io_rate = (totals[1] - io0) / span
            gpu_pct = sum(g for _, g in self.gpu_samples) / len(self.gpu_samples)
            if cpu_pct > LR_BUSY_CPU or io_rate > LR_BUSY_IO or gpu_pct > LR_BUSY_GPU:
                self.last_busy = now
                lr_state = b"W"
            elif lr_state == b"W" and now - self.last_busy > LR_IDLE_SECONDS:
                lr_state = b"D"
        return lr_state


# ---------------------------------------------------------------- Media + volume

def ascii_text(s: str, limit: int) -> str:
    """The board's font is plain ASCII: strip accents, drop anything else."""
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    s = " ".join(s.replace(SEP, " ").split())
    return s[:limit]


def app_label(app_id: str) -> str:
    """The app's name as the Screen Designer knows it, from its media session id."""
    a = (app_id or "").lower()
    if re.fullmatch(r"[0-9a-f]{16}", a):   # Firefox's id is a hash of its install folder
        return "Firefox"
    for key, label in (("spotify", "Spotify"), ("chrome", "Chrome"), ("msedge", "Edge"),
                       ("firefox", "Firefox"), ("opera", "Opera"), ("brave", "Brave"), ("vivaldi", "Vivaldi"),
                       ("vlc", "VLC"), ("applemusic", "Apple Music"), ("itunes", "iTunes"),
                       ("zune", "Media Player"), ("discord", "Discord"), ("amazonmusic", "Amazon Music"),
                       ("amazon music", "Amazon Music"), ("tidal", "TIDAL"), ("deezer", "Deezer"),
                       ("netflix", "Netflix"), ("primevideo", "Prime Video"), ("disney", "Disney+")):
        if key in a:
            return label
    name = a.split("!")[0].split("\\")[-1].removesuffix(".exe")
    return ascii_text(name.split(".")[-1].split("_")[0].title() or "Media", 16)


def browser_window_titles() -> list[str]:
    """Titles of the visible browser windows (each shows its active tab's title)."""
    titles = []

    def callback(hwnd, _):
        n = user32.GetWindowTextLengthW(hwnd)
        if n and user32.IsWindowVisible(hwnd):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if _process_path(pid.value).lower().rsplit("\\", 1)[-1] in BROWSER_EXES:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                titles.append(buf.value)
        return True

    user32.EnumWindows(EnumWindowsProc(callback), 0)
    return titles


class Volume:
    """Master volume of the default playback device through pycaw (Windows Core Audio). The device
    is looked up again before every change and every few seconds: the helper starts at log-on, and
    plugging in headphones or picking another output later would otherwise leave the buddy turning
    a device you aren't listening to."""

    def __init__(self) -> None:
        self.ep = None
        self.dev_id = None
        self.looked_at = 0.0
        self.failed = False   # the last lookup failed (logged once, until one works again)

    def _endpoint(self, fresh: bool = False):
        if not fresh and time.monotonic() - self.looked_at < 3:
            return self.ep
        self.looked_at = time.monotonic()
        try:
            from ctypes import POINTER, cast
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            if hasattr(AudioUtilities, "GetDeviceEnumerator"):
                dev = AudioUtilities.GetDeviceEnumerator().GetDefaultAudioEndpoint(0, 1)   # render, multimedia
            else:   # older pycaw: GetSpeakers() is the device itself
                dev = AudioUtilities.GetSpeakers()
            dev_id = dev.GetId()
            if dev_id != self.dev_id or self.ep is None:
                iface = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                self.ep, self.dev_id = cast(iface, POINTER(IAudioEndpointVolume)), dev_id
            self.failed = False
        except Exception:
            if not self.failed:
                log_error("volume device")
            self.failed = True
            self.ep = self.dev_id = None
        return self.ep

    def get(self) -> tuple[int, bool] | None:
        ep = self._endpoint()
        if ep is None:
            return None
        try:
            return round(ep.GetMasterVolumeLevelScalar() * 100), bool(ep.GetMute())
        except Exception:
            self.ep = None   # the device went away: look it up again
            return None

    def step(self, delta: float) -> None:
        ep = self._endpoint(fresh=True)
        if ep is None:
            return
        try:
            level = min(1.0, max(0.0, ep.GetMasterVolumeLevelScalar() + delta))
            ep.SetMasterVolumeLevelScalar(level, None)
            if level > 0 and ep.GetMute():
                ep.SetMute(0, None)
        except Exception:
            self.ep = None
            log_error("volume step")

    def toggle_mute(self) -> None:
        ep = self._endpoint(fresh=True)
        if ep is None:
            return
        try:
            ep.SetMute(0 if ep.GetMute() else 1, None)
        except Exception:
            self.ep = None
            log_error("volume mute")


async def winrt_result(op, timeout: float = 5.0):
    """Waits for a WinRT async operation by polling its status.
    (Awaiting some of them directly never wakes up the asyncio loop.)"""
    end = time.monotonic() + timeout
    while int(op.status) == 0:   # AsyncStatus.STARTED
        if time.monotonic() > end:
            op.cancel()
            raise TimeoutError("WinRT operation timed out")
        await asyncio.sleep(0.02)
    return op.get_results()


async def read_thumbnail(ref) -> bytes | None:
    if ref is None:
        return None
    from winrt.windows.storage.streams import Buffer, InputStreamOptions
    stream = await winrt_result(ref.open_read_async())
    size = stream.size
    if not size:
        return None
    result = await winrt_result(stream.read_async(Buffer(size), size, InputStreamOptions.NONE))
    return bytes(memoryview(result)[:result.length])


def make_cover_jpeg(raw: bytes) -> bytes:
    """Centre-crop to a square, resize for the round screen, encode as a baseline JPEG."""
    from PIL import Image
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    w, h = img.size
    side = min(w, h)
    img = img.crop(((w - side) // 2, (h - side) // 2, (w + side) // 2, (h + side) // 2))
    img = img.resize((COVER_SIZE, COVER_SIZE), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, "JPEG", quality=COVER_QUALITY, progressive=False, optimize=False)
    return out.getvalue()


class MediaWatcher:
    """Follows the Windows media session (the volume-flyout one) and the master volume."""

    def __init__(self) -> None:
        self.mgr = None
        self.volume = Volume()
        self.key = None             # (app, title, artist) of the song on the board
        self.now_msg = b"X"         # last N.../X message
        self.prog_msg = b""         # last P... message
        self.vol_msg = b""          # last V... message
        self.cover = b""            # last cover JPEG
        self.cover_sent_to = None   # client the cover was sent to
        self.paused_since = None
        self.last_prog_sent = 0.0
        self.img_task: asyncio.Task | None = None
        self.sites: dict[str, str] = {}   # browser -> site last seen playing in it ("" = another site)

    def site_of(self, browser: str, title: str) -> str:
        """YouTube or YouTube Music when that's what the browser is playing, else the browser's name.
        Only a window's active tab shows in its title, so a tab playing in the background keeps the
        site last seen for that browser (a YouTube playlist moving on in a background tab stays YouTube)."""
        if title:
            found = False
            for wt in browser_window_titles():
                i = wt.find(title)
                if i < 0:
                    continue
                found = True
                tail = wt[i:]   # "<title> - YouTube - Google Chrome"
                for suffix, site in SITES:
                    if suffix in tail:
                        self.sites[browser] = site
                        return site
            if found:
                self.sites[browser] = ""
        return self.sites.get(browser) or browser

    async def session(self):
        if self.mgr is None:
            from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as M
            self.mgr = await winrt_result(M.request_async())
        return self.mgr.get_current_session()

    async def snapshot(self):
        """Returns dict of what's playing, or None."""
        s = await self.session()
        if s is None:
            return None
        props = await winrt_result(s.try_get_media_properties_async())
        if props is None or not (props.title or props.artist):
            return None
        pb = s.get_playback_info()
        tl = s.get_timeline_properties()
        playing = int(pb.playback_status) == 4   # GlobalSystemMediaTransportControlsSessionPlaybackStatus.PLAYING
        pos = tl.position.total_seconds() if tl.position else 0.0
        end = tl.end_time.total_seconds() if tl.end_time else 0.0
        if playing and tl.last_updated_time and end > 0:
            # position is a snapshot from last_updated_time; move it forward to now
            updated = tl.last_updated_time
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            pos += max(0.0, (datetime.now(timezone.utc) - updated).total_seconds())
        pos = min(pos, end) if end > 0 else 0.0
        app = app_label(s.source_app_user_model_id or "")
        browser = app in BROWSERS
        if browser:
            app = self.site_of(app, props.title or "")
        return {
            "app": app,
            "spin": not browser,
            "title": ascii_text(props.title, 60),
            "artist": ascii_text(props.artist or props.album_artist, 40),
            "playing": playing,
            "pos": pos,
            "end": end,
            "thumb": props.thumbnail,
        }

    async def poll(self) -> None:
        snap = await self.snapshot()
        now = time.monotonic()

        if snap is not None:
            self.paused_since = None if snap["playing"] else (self.paused_since or now)
        show = snap is not None and not (
            self.paused_since is not None and now - self.paused_since > PAUSED_TO_EYES_SECONDS)

        if not show:
            if self.now_msg != b"X":
                self.now_msg, self.key, self.prog_msg = b"X", None, b""
                await write_cmd(self.now_msg)
        else:
            key = (snap["app"], snap["title"], snap["artist"])
            if key != self.key:
                self.key = key
                self.now_msg = ("N" + SEP.join([snap["title"], snap["artist"], snap["app"],
                                                "1" if snap["spin"] else "0"])).encode()
                await write_cmd(self.now_msg)
                self.cover, self.cover_sent_to = b"", None
                try:
                    raw = await read_thumbnail(snap["thumb"])
                    if raw:
                        self.cover = await asyncio.to_thread(make_cover_jpeg, raw)
                except Exception:
                    log_error("thumbnail")
                self.prog_msg = b""
            prog = f"P{'1' if snap['playing'] else '0'}{SEP}{int(snap['pos'] * 1000)}{SEP}{int(snap['end'] * 1000)}"
            # resend on play/pause, a seek (>2 s off), or every 5 s to correct drift
            old = self.prog_msg.decode().split(SEP) if self.prog_msg else None
            changed = (old is None or old[0] != prog.split(SEP)[0]
                       or abs(int(old[1]) + (now - self.last_prog_sent) * 1000 * (old[0] == "P1")
                              - snap["pos"] * 1000) > 2000
                       or now - self.last_prog_sent > 5)
            if changed:
                self.prog_msg, self.last_prog_sent = prog.encode(), now
                await write_cmd(self.prog_msg)

        vol = self.volume.get()
        if vol is not None:
            msg = f"V{vol[0]}{SEP}{1 if vol[1] else 0}".encode()
            if msg != self.vol_msg:
                self.vol_msg = msg
                await write_cmd(msg)

        if self.cover and self.cover_sent_to is not client and ble_connected() and self.now_msg != b"X":
            if self.img_task is None or self.img_task.done():
                self.cover_sent_to = client
                self.img_task = asyncio.create_task(send_cover(self.cover))

    def resend_all(self) -> None:
        """After a (re)connect, the board needs the whole picture again."""
        self.cover_sent_to = None
        self.prog_msg = b"" if self.now_msg != b"X" else self.prog_msg
        self.vol_msg = b""
        asyncio.create_task(write_cmd(self.now_msg))

    async def handle_touch(self, action: str) -> None:
        try:
            if action in "+-":
                self.volume.step(VOLUME_STEP if action == "+" else -VOLUME_STEP)
                return
            if action == "m":                      # both sensors at once
                self.volume.toggle_mute()
                return
            s = await self.session()
            if s is None:
                return
            if action == "p":
                await winrt_result(s.try_toggle_play_pause_async())
            elif action == "n":
                await winrt_result(s.try_skip_next_async())
            elif action == "b":
                await winrt_result(s.try_skip_previous_async())
        except Exception:
            log_error("touch")


media = MediaWatcher()


# ---------------------------------------------------------------- Phone notifications

def phone_app_name(app_id: str) -> str:
    """'com.whatsapp' / 'net.whatsapp.WhatsApp' -> 'WhatsApp'. An iPhone's texts (iMessage / SMS) come
    through Phone Link's Messages feature under the phone's own device id, a GUID: those are 'Messages'."""
    if re.fullmatch(r"[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", app_id):
        return "Messages"
    if app_id in PHONE_APPS:
        return PHONE_APPS[app_id]
    lower = {k.lower(): v for k, v in PHONE_APPS.items()}
    if app_id.lower() in lower:
        return lower[app_id.lower()]
    return ascii_text(app_id.split(".")[-1].replace("_", " ").title() or "Phone", 20)


def toast_texts(payload) -> list[str]:
    """The text lines of a notification's XML (first is usually the sender, then the message)."""
    if not payload:
        return []
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(payload if isinstance(payload, (bytes, str)) else bytes(payload))
    except ET.ParseError:
        return []
    return [" ".join((t.text or "").split()) for t in root.iter("text")
            if t.get("placement") != "attribution" and (t.text or "").strip()]


class NotificationWatcher:
    """Phone notifications that Phone Link shows on the PC, read from the notification history Windows
    keeps (a SQLite file). Only ones that arrive while the helper runs are sent."""

    QUERY = ("select n.Id, n.Type, n.Payload, h.PrimaryId from Notification n "
             "join NotificationHandler h on h.RecordId = n.HandlerId "
             "where n.Id > ? and h.PrimaryId like 'Microsoft.YourPhone%!YourPhoneNotifications%' order by n.Id")

    def __init__(self) -> None:
        self.last_id: int | None = None   # newest notification already seen
        self.recent: list[dict] = []      # notifications seen lately: note, count, first time, ...
        self.last_new = -1e9              # when a new notification was last sent

    def _rows(self) -> list:
        import sqlite3
        con = sqlite3.connect(f"file:{NOTIFY_DB}?mode=ro", uri=True, timeout=1)
        try:
            if self.last_id is None:   # start from now: don't replay old notifications
                self.last_id = con.execute("select coalesce(max(Id), 0) from Notification").fetchone()[0]
                return []
            return con.execute(self.QUERY, (self.last_id,)).fetchall()
        finally:
            con.close()

    def poll(self) -> list[tuple[str, str, str, int, str]]:
        """Phone notifications to send now, as (app, title, message, count, time received "HH:MM").
        Someone blowing up your phone sends the same notification over and over: it's sent once, then
        re-sent with the new count at most every NOTIFY_COUNT_EVERY seconds while copies keep coming."""
        if not NOTIFICATIONS or not os.path.exists(NOTIFY_DB):
            return []
        now = time.monotonic()
        self.recent = [r for r in self.recent if r["seen"] > now - NOTIFY_REPEAT_WINDOW]
        out = []
        for nid, kind, payload, handler in self._rows():
            self.last_id = max(self.last_id, nid)
            app = phone_app_name(handler.split("YourPhoneNotifications_", 1)[-1])
            if app in NOTIFY_IGNORE:
                continue
            raw = payload.encode() if isinstance(payload, str) else bytes(payload or b"")
            if b"pause again" in raw.lower():
                continue   # Phone Link's own "notifications paused" message, not one from the phone
            texts = toast_texts(payload)
            if len(texts) > 1 and texts[0].lower() == app.lower():
                texts = texts[1:]   # Phone Link starts with the app's name, then sender, then message
            if not texts:
                # a collapsed entry without its text: say something arrived, unless that app's full one just did
                if any(r["seen"] > now - 10 and r["note"][0] == app for r in self.recent):
                    continue
                texts = ["", "New notification"]
            note = (app, texts[0], " ".join(texts[1:]) if NOTIFY_SHOW_TEXT else "")
            same = next((r for r in self.recent if r["note"] == note), None)
            if same:   # the same notification again: count it
                same["count"] += 1
                same["seen"] = now
                continue
            r = {"note": note, "count": 1, "sent_count": 1, "seen": now, "sent": now, "at": time.strftime("%H:%M")}
            self.recent.append(r)
            self.last_new = now
            out.append((*note, 1, r["at"]))
        for r in self.recent:   # counts that went up (but let a new notification stay up a moment first)
            if (r["count"] > r["sent_count"] and now - r["sent"] >= NOTIFY_COUNT_EVERY
                    and now - self.last_new >= NOTIFY_COUNT_EVERY):
                r["sent_count"], r["sent"] = r["count"], now
                out.append((*r["note"], r["count"], r["at"]))
        return out


notifier = NotificationWatcher()


def load_fantasy_settings() -> dict:
    """fantasy.json next to this file: league_id, espn_s2, swid (private leagues), team_id (optional)."""
    try:
        with open(FANTASY_SETTINGS, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return {}
    s = {k: str(raw.get(k) or "").strip() for k in ("league_id", "espn_s2", "swid", "team_id")}
    if s["swid"] and not s["swid"].startswith("{"):
        s["swid"] = "{" + s["swid"].strip("{}") + "}"
    return s if s["league_id"].isdigit() else {}


def espn_get(url: str, cookies: str = "") -> dict:
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    if cookies:
        headers["Cookie"] = cookies
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def fantasy_season(now: datetime | None = None) -> int:
    """ESPN numbers a basketball season by the year it ends: October 2026 - April 2027 is 2027."""
    now = now or datetime.now()
    return now.year + 1 if now.month >= 8 else now.year


def team_name(t: dict) -> str:
    return (t.get("name") or f"{t.get('location', '')} {t.get('nickname', '')}".strip()
            or t.get("abbrev") or f"Team {t.get('id')}")


def record_text(t: dict) -> str:
    """'5-2', or '5-2-1' with ties."""
    rec = t.get("record", {}).get("overall", {})
    return f"{rec.get('wins', 0)}-{rec.get('losses', 0)}" + (f"-{rec['ties']}" if rec.get("ties") else "")


def standings(league: dict) -> list[tuple[int, dict]]:
    """(place, team) in standings order: ESPN's playoff seeds when every team has one, else wins, then
    points scored."""
    teams = league.get("teams", [])
    if teams and all(t.get("playoffSeed") for t in teams):
        return sorted(((int(t["playoffSeed"]), t) for t in teams), key=lambda p: p[0])
    rec = lambda t: t.get("record", {}).get("overall", {})
    order = sorted(teams, key=lambda t: (-rec(t).get("wins", 0), -rec(t).get("pointsFor", 0)))
    return [(i + 1, t) for i, t in enumerate(order)]


def fantasy_summary(league: dict, swid: str = "", team_id: str = "") -> dict | None:
    """This week's matchup for your team, from an ESPN fantasy basketball points league (mTeam +
    mMatchupScore + mStatus views). Your team is team_id if given, else the team the SWID cookie owns.
    Projections are 0 when ESPN doesn't give them (the buddy then leaves them out)."""
    teams = {t["id"]: t for t in league.get("teams", [])}
    me = None
    if str(team_id).isdigit():
        me = teams.get(int(team_id))
    if me is None and swid:
        me = next((t for t in teams.values()
                   if swid.lower() in [str(o).lower() for o in t.get("owners", [])] + [str(t.get("primaryOwner", "")).lower()]), None)
    if me is None:
        return None
    week = league.get("status", {}).get("currentMatchupPeriod") or league.get("scoringPeriodId") or 0
    game = next((g for g in league.get("schedule", []) if g.get("matchupPeriodId") == week
                 and me["id"] in (g.get("home", {}).get("teamId"), g.get("away", {}).get("teamId"))), None)

    def side(s: dict) -> tuple[float, float]:
        score = s.get("totalPointsLive", s.get("totalPoints", 0)) or 0
        proj = s.get("totalProjectedPointsLive", s.get("totalProjectedPoints", 0)) or 0
        return float(score), float(proj)

    mine, theirs, opp = (0.0, 0.0), (0.0, 0.0), None
    if game:
        home_is_me = game.get("home", {}).get("teamId") == me["id"]
        my_side, their_side = (game["home"], game.get("away")) if home_is_me else (game["away"], game["home"])
        mine = side(my_side)
        if their_side:
            opp = teams.get(their_side.get("teamId"))
            theirs = side(their_side)
    rec = me.get("record", {}).get("overall", {})
    table = standings(league)
    place = {t["id"]: p for p, t in table}
    rank = place.get(me["id"], 0)
    shown = table[:5] if rank <= 5 else table[:4] + [(rank, me)]   # the top 5, or the top 4 and you
    streak = {"WIN": "W", "LOSS": "L", "TIE": "T"}.get(str(rec.get("streakType", "")).upper(), "")
    return {"week": int(week), "my_team": team_name(me), "opp_team": team_name(opp) if opp else ("BYE" if game else ""),
            "my_score": mine[0], "opp_score": theirs[0], "my_proj": mine[1], "opp_proj": theirs[1],
            "record": record_text(me), "rank": int(rank),
            "streak": f"{streak}{rec['streakLength']}" if streak and rec.get("streakLength") else "",
            "points_for": float(rec.get("pointsFor", 0) or 0),
            "opp_record": record_text(opp) if opp else "", "opp_rank": place.get(opp["id"], 0) if opp else 0,
            "standings": [(p, team_name(t), record_text(t)) for p, t in shown]}


def nba_games_live() -> bool:
    """True while any NBA game is being played (ESPN's public scoreboard)."""
    board = espn_get(NBA_SCOREBOARD)
    return any(e.get("status", {}).get("type", {}).get("state") == "in" for e in board.get("events", []))


def fantasy_msg(s: dict, live: bool) -> bytes:
    """F<week>␟<your team>␟<opponent>␟<your score>␟<their score>␟<your proj>␟<their proj>␟<record>␟<rank>␟<live 0/1>"""
    num = lambda v: f"{v:.1f}"
    return ("F" + SEP.join([str(s["week"]), ascii_text(s["my_team"], 24), ascii_text(s["opp_team"], 24),
                            num(s["my_score"]), num(s["opp_score"]), num(s["my_proj"]), num(s["opp_proj"]),
                            s["record"], str(s["rank"]), "1" if live else "0"])).encode()


def league_msg(s: dict) -> bytes:
    """L<streak>␟<points for>␟<their record>␟<their place>, then <place>␟<team>␟<record> for each team in
    the standings shown (the top 5, or the top 4 and you)"""
    fields = [s["streak"], f"{s['points_for']:.1f}", s["opp_record"], str(s["opp_rank"])]
    for place, team, record in s["standings"]:
        fields += [str(place), ascii_text(team, 18), record]
    return ("L" + SEP.join(fields)).encode()


class FantasyWatcher:
    """Your ESPN fantasy basketball matchup and the standings, checked every FANTASY_LIVE_EVERY seconds
    while NBA games are on and every FANTASY_IDLE_EVERY otherwise. Off until fantasy.json has a league id."""

    def __init__(self) -> None:
        self.next_at = 0.0
        self.last: list[bytes] = []  # the messages last sent, sent again after a reconnect
        self.warned = ""            # last problem logged, so it's logged once
        self.live = False           # an NBA game was on at the last check
        self.scoreboard_at = 0.0    # when to look at the NBA scoreboard next, while no game is on

    def _tipped_off(self) -> bool:
        """While no game is on the league is only checked every FANTASY_IDLE_EVERY, so meanwhile look
        at the (public) NBA scoreboard every FANTASY_LIVE_EVERY: the pages then come up within a
        minute of a tip-off, not up to ten. Only once the league has been read."""
        now = time.monotonic()
        if self.live or not self.last or now < self.scoreboard_at:
            return False
        self.scoreboard_at = now + FANTASY_LIVE_EVERY
        try:
            return nba_games_live()
        except (OSError, ValueError):
            return False

    def _problem(self, text: str) -> None:
        if text != self.warned:
            self.warned = text
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [fantasy] {text}\n")

    def poll(self) -> list[bytes]:
        """The messages to send now: the matchup (F) and standings (L) ones that changed. None when it
        isn't time yet, fantasy.json isn't set up, or ESPN didn't answer."""
        if not FANTASY or (time.monotonic() < self.next_at and not self._tipped_off()):
            return []
        s = load_fantasy_settings()
        if not s:
            self.next_at = time.monotonic() + 60   # check fantasy.json again in a minute
            return []
        cookies = f"espn_s2={s['espn_s2']}; SWID={s['swid']}" if s["espn_s2"] and s["swid"] else ""
        url = FANTASY_URL.format(season=fantasy_season(), league=s["league_id"])
        try:
            league = espn_get(url, cookies)
        except urllib.error.HTTPError as e:
            self.next_at = time.monotonic() + FANTASY_IDLE_EVERY
            self._problem(f"ESPN said {e.code}: " + ("check espn_s2 and swid in fantasy.json (private leagues need "
                                                     "them, and they change when you sign out)" if e.code in (401, 403)
                                                     else "check league_id in fantasy.json"))
            return []
        except (OSError, ValueError) as e:
            self.next_at = time.monotonic() + 120
            self._problem(f"couldn't reach ESPN: {e}")
            return []
        summary = fantasy_summary(league, s["swid"], s["team_id"])
        if summary is None:
            self.next_at = time.monotonic() + FANTASY_IDLE_EVERY
            self._problem("couldn't tell which team is yours: set team_id in fantasy.json, or check swid")
            return []
        try:
            live = nba_games_live()
        except (OSError, ValueError):
            live = False
        self.warned = ""
        self.live = live
        self.next_at = time.monotonic() + (FANTASY_LIVE_EVERY if live else FANTASY_IDLE_EVERY)
        msgs = [fantasy_msg(summary, live), league_msg(summary)]
        new = [m for m in msgs if m not in self.last]
        self.last = msgs
        return new


fantasy = FantasyWatcher()


# ---------------------------------------------------------------- Clock + Claude for the screens

def clock_msg(now: datetime) -> bytes:
    """K<hour>␟<minute>␟<second>␟<date>␟<day number>: the board keeps time from here (it has no clock of
    its own). The day number (days since year 1) picks the fantasy pages' style of the day."""
    return ("K" + SEP.join([str(now.hour), str(now.minute), str(now.second),
                            f"{now:%a} {now.day} {now:%b}", str(now.toordinal())])).encode()


USAGE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "usage.json")
# The Claude desktop app's own record of the plan usage it has seen (samples of
# {t: ms, u: {fh: session %, sd: weekly %}}). Usage numbers only; it gets a sample now and then.
# The regular installer keeps it in %APPDATA%\Claude. The Microsoft Store app's writes to %APPDATA%
# can land in its package folder instead, and newer Store versions keep their data in
# %LOCALAPPDATA%\Claude-Data\claude_<id>, so all three are checked and the newest sample wins.
APP_USAGE_FILES = (
    os.path.expandvars(r"%APPDATA%\Claude\plan-usage-history.json"),
    os.path.expandvars(r"%LOCALAPPDATA%\Packages\Claude_*\LocalCache\Roaming\Claude\plan-usage-history.json"),
    os.path.expandvars(r"%LOCALAPPDATA%\Claude-Data\claude_*\plan-usage-history.json"),
)
SESSION_WINDOW = 5 * 3600        # the plan's session limit runs over 5 hours
WEEK_WINDOW = 7 * 24 * 3600


def window_pct(pct, at: float, resets_at, length: float, now: float) -> int:
    """A usage window's percentage now: 0 once it has reset (when the reset time is known), -1 when
    unknown (never reported, or reported too long ago to still be true)."""
    if pct is None:
        return -1
    if resets_at:
        return 0 if resets_at < now else int(round(pct))
    return int(round(pct)) if now - at < length else -1


class ClaudeInfo:
    """What the Claude screens show: how long the session has run and the tokens it has used (both
    from the transcript of the session that sent the latest hook), and the plan's session / weekly
    usage from whichever reported last: the status line (claude-status.py saves usage.json; only
    Claude Code in a terminal runs it) or the Claude desktop app (plan-usage-history.json)."""

    def __init__(self) -> None:
        self.path = ""
        self.pos = 0
        self.start = None              # epoch seconds of the session's first transcript entry
        self.usage: dict[str, int] = {}   # message id -> tokens (a message spans several lines)
        self.files: dict[str, tuple[float, object]] = {}   # path -> (mtime, parsed JSON)
        self.app_files: list[str] = []   # the Claude app's usage files found by the last look
        self.app_files_at = None
        self.session_pct = -1
        self.weekly_pct = -1

    @property
    def tokens(self) -> int:
        return sum(self.usage.values())

    def app_usage_files(self) -> list[str]:
        """Where the Claude app keeps plan-usage-history.json on this PC. Looked up once a minute."""
        if self.app_files_at is None or time.monotonic() - self.app_files_at > 60:
            self.app_files_at = time.monotonic()
            self.app_files = [p for pattern in APP_USAGE_FILES for p in glob.glob(pattern)]
        return self.app_files

    def _load(self, path: str):
        """A JSON file, re-read only when it changes; the last good copy if it can't be read."""
        cached = self.files.get(path)
        try:
            mtime = os.path.getmtime(path)
            if cached and cached[0] == mtime:
                return cached[1]
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return cached[1] if cached else None
        self.files[path] = (mtime, data)
        return data

    def read_limits(self) -> None:
        now = time.time()
        # (when, session %, session reset, weekly %, weekly reset) from each source; the newest wins
        sources = []
        s = self._load(USAGE_FILE)
        if isinstance(s, dict):
            sources.append((s.get("at", 0), s.get("five_hour"), s.get("five_hour_resets_at"),
                            s.get("seven_day"), s.get("seven_day_resets_at")))
        for path in self.app_usage_files():
            h = self._load(path)
            samples = h.get("samples") if isinstance(h, dict) else None
            if samples:
                last = samples[-1]
                u = last.get("u") or {}
                sources.append((last.get("t", 0) / 1000, u.get("fh"), None, u.get("sd"), None))
        if not sources:
            return
        at, five, five_reset, seven, seven_reset = max(sources, key=lambda x: x[0])
        self.session_pct = window_pct(five, at, five_reset, SESSION_WINDOW, now)
        self.weekly_pct = window_pct(seven, at, seven_reset, WEEK_WINDOW, now)

    def scan(self, path: str) -> None:
        if path != self.path:
            self.path, self.pos, self.start, self.usage = path, 0, None, {}
        size = file_size(path) if path else 0
        if size <= self.pos:
            return
        with open(path, "rb") as f:
            f.seek(self.pos)
            chunk = f.read(size - self.pos)
        end = chunk.rfind(b"\n") + 1            # whole lines only; the rest next time
        self.pos += end
        for line in chunk[:end].splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if self.start is None and e.get("timestamp"):
                self.start = datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00")).timestamp()
            m = e.get("message") if e.get("type") == "assistant" else None
            u = m.get("usage") if isinstance(m, dict) else None
            if u:
                # cache reads are the same context re-read every turn, so they don't count as used
                self.usage[m.get("id") or str(len(self.usage))] = (
                    u.get("input_tokens", 0) + u.get("output_tokens", 0) + u.get("cache_creation_input_tokens", 0))

    def msg(self, status: bytes) -> bytes:
        """U<status>␟<session ms>␟<tokens>␟<session %>␟<weekly %>"""
        ms = int((time.time() - self.start) * 1000) if self.start else 0
        return ("U" + SEP.join([status.decode(), str(ms), str(self.tokens),
                                str(self.session_pct), str(self.weekly_pct)])).encode()


PROJECTS_DIR = os.path.join(os.path.expanduser("~"), ".claude", "projects")


class ScreenFeed:
    """Sends the clock every minute and the Claude info whenever it changes (and every minute)."""

    def __init__(self) -> None:
        self.claude = ClaudeInfo()
        self.clock_sent = None
        self.u_key = None
        self.u_at = 0.0
        self.latest = ""
        self.latest_at = 0.0

    def latest_transcript(self) -> str:
        """Until a hook names its session (e.g. right after the helper starts): the transcript
        written most recently. Looked up every 30 s."""
        if time.monotonic() - self.latest_at > 30:
            self.latest_at = time.monotonic()
            newest, newest_t = "", 0.0
            try:
                for project in os.scandir(PROJECTS_DIR):
                    if not project.is_dir():
                        continue
                    for f in os.scandir(project.path):
                        if f.name.endswith(".jsonl"):
                            t = f.stat().st_mtime
                            if t > newest_t:
                                newest, newest_t = f.path, t
            except OSError:
                pass
            self.latest = newest
        return self.latest

    async def poll(self) -> None:
        now = datetime.now()
        if (now.hour, now.minute) != self.clock_sent and await write_cmd(clock_msg(now)):
            self.clock_sent = (now.hour, now.minute)
        status = claude_state if claude_open else b"O"
        c = self.claude
        path = transcript or await asyncio.to_thread(self.latest_transcript)
        await asyncio.to_thread(c.scan, path)
        c.read_limits()
        key =(status, c.start, c.tokens // 100, c.session_pct, c.weekly_pct)
        if (key != self.u_key or time.monotonic() - self.u_at > 60) and await write_cmd(c.msg(status)):
            self.u_key, self.u_at = key, time.monotonic()

    def resend(self) -> None:
        self.clock_sent = self.u_key = None


screens = ScreenFeed()


# ---------------------------------------------------------------- Bluetooth

def ble_connected() -> bool:
    return client is not None and client.is_connected


async def write_cmd(data: bytes, confirm: bool = False) -> bool:
    """confirm: wait for the board's acknowledgement (a write without one can be lost on a shaky link)."""
    if ble_connected():
        try:
            await client.write_gatt_char(CMD_UUID, data, response=confirm)
            return True
        except Exception as e:
            if confirm:
                log_line("helper", f"write {data[:1]!r} failed: {e!r}"[:160])
    return False


image_lock = asyncio.Lock()   # the board takes one picture at a time, a cover or the model


async def send_image(start: bytes, jpeg: bytes, confirm: bool = True) -> None:
    """Sends a JPEG in MTU-sized chunks: <start><len>, C<data>..., E. Without confirm it goes several
    times faster; a lost write makes the board drop that picture (the length won't match)."""
    c = client
    async with image_lock:
        chunk = max(20, min(500, (getattr(c, "mtu_size", 23) or 23) - 4))
        await c.write_gatt_char(IMG_UUID, start + struct.pack("<I", len(jpeg)), response=confirm)
        for i in range(0, len(jpeg), chunk):
            await c.write_gatt_char(IMG_UUID, b"C" + jpeg[i:i + chunk], response=confirm)
        await c.write_gatt_char(IMG_UUID, b"E", response=confirm)


async def send_cover(jpeg: bytes) -> None:
    try:
        await send_image(b"B", jpeg)
    except Exception:
        media.cover_sent_to = None   # try again next poll


# ---------------------------------------------------------------- SolidWorks

def model_mask(img):
    """White where the model is. SolidWorks' background is smooth and its colours overlap the model's, but
    the model has a sharp outline: whatever a flood from the corners can reach without crossing a sharp
    edge is background."""
    from PIL import ImageDraw, ImageFilter, ImageOps
    w, h = img.size
    edges = img.convert("L").filter(ImageFilter.FIND_EDGES).point(lambda v: 255 if v > SW_EDGE else 0)
    edges = ImageOps.expand(ImageOps.crop(edges, 1), 1, 0).filter(ImageFilter.MaxFilter(3))
    for corner in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
        if edges.getpixel(corner) == 0:
            ImageDraw.floodfill(edges, corner, 128)
    # the thick edges made the model a little too big, and a second pass takes the light fringe off it too
    return edges.point(lambda v: 0 if v == 128 else 255).filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MinFilter(3))


def make_model_frame(raw: bytes, view: tuple | None) -> tuple[bytes, tuple]:
    """A frame for the round screen: the model on black. view = (centre x, centre y, side) of the square
    last shown, kept while the model still sits well in it, so the picture doesn't jitter."""
    from PIL import Image
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    w, h = img.size
    box = model_mask(img.resize((SW_MASK_SIZE, max(1, SW_MASK_SIZE * h // w)))).getbbox()
    if box:
        k = w / SW_MASK_SIZE
        x0, y0, x1, y1 = (v * k for v in box)
        side = max(x1 - x0, y1 - y0) / SW_FILL
        fits = view and max(x1 - x0, y1 - y0) > view[2] * SW_FILL * 0.8 and (
            x0 > view[0] - view[2] * 0.45 and x1 < view[0] + view[2] * 0.45
            and y0 > view[1] - view[2] * 0.45 and y1 < view[1] + view[2] * 0.45)
        if not fits:
            view = ((x0 + x1) / 2, (y0 + y1) / 2, side)
    elif view is None:
        view = (w / 2, h / 2, max(w, h))
    cx, cy, side = view
    left, top = round(cx - side / 2), round(cy - side / 2)
    square = Image.new("RGB", (round(side), round(side)), img.getpixel((0, 0)))   # past the picture's edges: background
    square.paste(img, (-left, -top))
    frame = square.resize((COVER_SIZE, COVER_SIZE), Image.BICUBIC)
    mask = model_mask(frame.resize((SW_MASK_SIZE, SW_MASK_SIZE), Image.BILINEAR)).resize((COVER_SIZE, COVER_SIZE), Image.BILINEAR)
    frame = Image.composite(frame, Image.new("RGB", frame.size), mask)
    out = io.BytesIO()
    frame.save(out, "JPEG", quality=SW_QUALITY, progressive=False, optimize=False)
    return out.getvalue(), view


def solidworks_running() -> bool:
    return any((p.info["name"] or "").lower() == "sldworks.exe" for p in psutil.process_iter(["name"]))


def sw_step_name(tool: str) -> str:
    """mcp__solidworks__solidworks_create_extrusion -> Create extrusion"""
    name = tool.rsplit("__", 1)[-1].removeprefix("solidworks_").replace("_", " ")
    return "Several steps" if name == "batch" else name.capitalize()


class SolidWorksFeed:
    """The live picture of what Claude builds in SolidWorks. Claude may use its SolidWorks tools or scripts of
    any name, so what starts the pages is the model itself changing: while Claude is busy and SolidWorks is
    open, a slow check watches it. The pages then hold through a build's quiet spells (Claude writing the
    next script) until it has been quiet SW_BUILD_SECONDS, or SW_SHOW_SECONDS once Claude has finished.
    sw-capture.ps1 keeps running meanwhile, since starting PowerShell for each frame takes over a second."""

    def __init__(self) -> None:
        self.doc = ""
        self.step = ""
        self.steps = 0
        self.recent: deque[str] = deque(maxlen=3)
        self.at = 0.0            # monotonic time of the last step
        self.moved = 0.0         # and of the last frame that differed from the one before
        self.told = 0.0          # and of the last message to the board
        self.script = ""         # the shell command running that may touch SolidWorks: its description
        self.script_at = 0.0     # and when it started
        self.watching = False    # Claude is busy and SolidWorks is open
        self.open = True         # SolidWorks is running: closing it ends the pages straight away
        self.poll_at = 0.0
        self.live = asyncio.Event()
        self.turn = False        # turn the view to isometric before the next frame
        self.capture = None      # the running sw-capture.ps1
        self.size = None         # (width, height) SolidWorks draws frames at
        self.view = None
        self.raw_hash = b""
        self.jpeg = b""
        self.frames = 0
        self.sender = None       # the task sending the current frame
        self.confirmed = b""     # the last frame the board is known to have
        self.spent = [0.0, 0.0, 0.0]   # seconds on SolidWorks' drawing, the cut-out and Bluetooth, for the log

    def msg(self) -> bytes:
        """M<document>␟<step>␟<steps done>␟<recent>␟<recent>␟<recent>"""
        return ("M" + SEP.join([ascii_text(self.doc, 30), ascii_text(self.step, 30), str(self.steps),
                                *(ascii_text(r, 25) for r in self.recent)])).encode()

    async def note(self, name: str, finished: bool, counts: bool = True) -> None:
        """A step starting or finished: on the board now, and the stream runs."""
        now = time.monotonic()
        if now - self.at > SW_NEW_BUILD_SECONDS:
            self.steps = 0
            self.recent.clear()
        self.at = self.told = now
        if counts and not finished:
            self.step = name
        elif counts:
            self.steps += 1
            self.recent.appendleft(name)
        self.live.set()
        await write_cmd(self.msg())

    async def on_tool(self, tool: str, finished: bool, failed: bool = False) -> None:
        builds = not tool.rsplit("__", 1)[-1].removeprefix("solidworks_").startswith(SW_LOOK_ONLY)
        if finished and builds and not failed:
            self.turn = SW_TURN_TO_ISOMETRIC
        await self.note(sw_step_name(tool), finished, builds and not (finished and failed))

    async def on_script(self, description: str, finished: bool) -> None:
        """A shell command that mentions SolidWorks. Mentioning isn't building, so it only becomes a step
        if the model changed while it ran. The view isn't turned: a script may rely on it."""
        if not finished:
            self.script, self.script_at = description or "Running a script", time.monotonic()
            return
        name, self.script = self.script, ""
        if name and self.moved >= self.script_at:
            await self.note(name, True)

    def held(self) -> bool:
        """The pages stay up."""
        last = max(self.at, self.moved)
        limit = SW_BUILD_SECONDS if claude_state in (b"W", b"A") else SW_SHOW_SECONDS
        return self.open and last > 0 and time.monotonic() - last < limit

    async def poll(self) -> None:
        now = time.monotonic()
        if now < self.poll_at:
            return
        self.poll_at = now + SW_POLL_SECONDS
        self.open = await asyncio.to_thread(solidworks_running)
        self.watching = claude_state in (b"W", b"A") and self.open
        if self.watching:
            self.live.set()

    async def ask(self, command: str) -> str:
        """One command to sw-capture.ps1. Returns the document's title, empty if there's no picture."""
        if self.capture is None:
            self.capture = await asyncio.create_subprocess_exec(
                "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", SW_CAPTURE_SCRIPT, SW_PICTURE,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            self.capture.stdin.write(command.encode() + b"\n")
            await self.capture.stdin.drain()
            line = await asyncio.wait_for(self.capture.stdout.readline(), SW_ANSWER_SECONDS)
        except (OSError, asyncio.TimeoutError):
            line = b""
        if not line:          # it ended (SolidWorks isn't running) or SolidWorks is stuck
            self.stop_capture()
            await asyncio.sleep(2)
        return line.decode("utf-8", "ignore").strip()

    def stop_capture(self) -> None:
        if self.capture is not None:
            try:
                self.capture.kill()
            except ProcessLookupError:
                pass
        self.capture = None

    async def frame(self) -> None:
        if self.turn:
            self.turn = False
            await self.ask("turn")
        if self.size is None:
            if not await self.ask("frame 0 0"):
                return
            from PIL import Image
            with Image.open(SW_PICTURE) as first:
                self.size = (SW_FRAME_WIDTH, SW_FRAME_WIDTH * first.height // first.width)
        t0 = time.monotonic()
        title = await self.ask(f"frame {self.size[0]} {self.size[1]}")
        t1 = time.monotonic()
        self.spent[0] += t1 - t0
        if not title:
            return
        if title != self.doc:
            if self.doc:
                self.moved = t1           # another document in front counts as a change
            self.doc, self.view, self.raw_hash, self.jpeg, self.confirmed = title, None, b"", b"", b""
            if self.held():
                self.told = t1
                await write_cmd(self.msg())   # first: the board forgets the old model's picture
        with open(SW_PICTURE, "rb") as f:
            raw = f.read()
        digest = hashlib.md5(raw).digest()
        if digest == self.raw_hash:       # nothing moved: make sure the board got the picture it stopped on
            if self.confirmed != self.jpeg and ble_connected():
                if self.sender is not None:
                    await self.sender
                await send_image(b"M", self.jpeg)
                self.confirmed = self.jpeg
            return
        first, self.raw_hash = not self.raw_hash, digest   # the first frame is only what to compare with
        t2 = time.monotonic()
        if not first:
            pages_up = self.held()
            self.moved = t2
            if self.script and self.step != self.script:
                await self.note(self.script, False)        # that shell command is building
            elif not pages_up:
                self.told = t2
                await write_cmd(self.msg())
        jpeg, self.view = await asyncio.to_thread(make_model_frame, raw, self.view)
        self.spent[1] += time.monotonic() - t2
        if jpeg != self.jpeg and ble_connected():
            self.jpeg = jpeg
            if self.sender is not None:
                await self.sender         # the last frame is still going out: the next is ready meanwhile
            self.sender = asyncio.create_task(self.send(jpeg))

    async def send(self, jpeg: bytes) -> None:
        t0 = time.monotonic()
        try:
            await send_image(b"M", jpeg, confirm=False)
            self.frames += 1
        except Exception:
            self.jpeg = b""               # send the next one, even if nothing moves
        self.spent[2] += time.monotonic() - t0

    async def run(self) -> None:
        while True:
            await self.live.wait()
            started, self.frames, self.spent = time.monotonic(), 0, [0.0, 0.0, 0.0]
            while self.watching or self.held():
                await self.poll()
                t0 = time.monotonic()
                try:
                    await self.frame()
                except Exception:
                    log_error("solidworks")
                    await asyncio.sleep(1)
                now = time.monotonic()
                if self.held() and now - self.told > SW_SHOW_SECONDS / 2:   # keeps the pages up on the board
                    self.told = now
                    await write_cmd(self.msg())
                pace = SW_FRAME_SECONDS if now - self.moved < SW_STILL_SECONDS else SW_IDLE_FRAME_SECONDS
                await asyncio.sleep(max(0.0, pace - (now - t0)))
            self.live.clear()
            self.stop_capture()
            self.size = None
            self.raw_hash = b""
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} [solidworks] {self.frames} changed frames "
                        f"in {time.monotonic() - started:.0f} s; seconds drawing {self.spent[0]:.1f}, "
                        f"cutting out {self.spent[1]:.1f}, sending {self.spent[2]:.1f}, "
                        f"chunk {getattr(client, 'mtu_size', 0)}\n")

    async def resend(self) -> None:
        """After a reconnect, while the pages are still up."""
        if self.held():
            await write_cmd(self.msg())
            self.jpeg = self.confirmed = b""   # frame() sends the picture again once it looks
            self.raw_hash = b""


solidworks = SolidWorksFeed()


# ---------------------------------------------------------------- What Claude is doing and asking

def tool_activity(info: dict) -> tuple[str, str] | None:
    """What a tool call looks like on the Claude screens: ("Editing", "notes.md"). None = don't show it."""
    tool = info.get("tool") or ""
    if not tool or tool.startswith(HIDDEN_TOOLS):
        return None
    file = os.path.basename(str(info.get("file") or ""))
    desc = str(info.get("desc") or "")
    if tool in ("Edit", "NotebookEdit"):
        return "Editing", file
    if tool == "Write":
        return "Writing", file
    if tool == "Read":
        return "Reading", file
    if tool in ("Bash", "PowerShell"):
        return "Running", desc or "a command"
    if tool in ("Grep", "Glob"):
        return "Searching", str(info.get("pattern") or "")
    if tool in ("WebSearch", "WebFetch"):
        return "Looking online", ""
    if tool == "Agent":
        return "Running an agent", desc
    if tool.startswith("mcp__"):
        server, _, name = tool[5:].partition("__")
        return ("Using a connector" if "-" in server else "Using " + server.replace("_", " ")), name.replace("_", " ")
    return "Using", tool


def question_text(info: dict) -> str:
    """What Claude is waiting for, from the hook that said so."""
    if info.get("question"):
        return str(info["question"])
    if info.get("event") == "PermissionRequest":
        what = tool_activity(info)
        if not what:
            return "It wants your permission"
        return "Allow: " + (what[1] if what[0] == "Running" else " ".join(what).strip())
    return str(info.get("message") or "It's waiting for you")


async def set_activity(what: str = "", target: str = "") -> None:
    global activity_msg
    msg = ("J" + (ascii_text(what, 23) + SEP + ascii_text(target, 39) if what else "")).encode()
    if msg != activity_msg and await write_cmd(msg):
        activity_msg = msg


async def set_ask(title: str = "", text: str = "", options: tuple = ()) -> None:
    global ask_msg, ask_options, ask_path
    ask_path = transcript
    if ask_options and not options:
        log_line("claude", f"options card replaced: {title or 'cleared'}, state {claude_state!r}, app open {claude_open}")
    ask_options = options if title else ()
    msg = ("?" + (SEP.join([ascii_text(title, 19), ascii_text(text, 170)] + [ascii_text(o, 27) for o in options])
                  if title else "")).encode()
    if msg != ask_msg:
        ask_msg = msg   # kept even if the board is away: the reconnect sends it again
        await write_cmd(msg, confirm=True)


async def on_hook(letter: bytes, info: dict) -> None:
    tool = info.get("tool") or ""
    event = info.get("event") or ""
    if letter == b"A":
        if event != "Notification" or ask_msg == b"?":   # its generic line mustn't replace the real question
            await set_ask("NEEDS YOU", question_text(info))
    elif letter == b"D" and transcript:
        asked, options = await asyncio.to_thread(turn_asked, transcript)
        if asked:
            await set_ask("ASKS", asked, options)
    elif event == "PreToolUse":
        what = tool_activity(info)
        if what:
            await set_activity(*what)
    if event in ("PreToolUse", "PostToolUse"):
        if "solidworks" in tool:
            await solidworks.on_tool(tool, event == "PostToolUse", bool(info.get("failed")))
        elif info.get("sw_script"):
            await solidworks.on_script(str(info.get("desc") or ""), event == "PostToolUse")


async def clear_claude_extras() -> None:
    """Claude's step shows only while it works, and its question until it moves on."""
    if claude_state != b"W":
        await set_activity()
    if not claude_open or claude_state == b"W" or (claude_state == b"D" and time.monotonic() >= ask_until and not ask_options):
        await set_ask()


# ---------------------------------------------------------------- Firmware updates

def firmware_log(line: str) -> None:
    with open(FIRMWARE_LOG, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {line}\n")


async def send_firmware() -> None:
    """Sends update.bin to the board over Bluetooth: B<size><signature>, C<data>..., E. The board
    keeps it in memory, checks the signature, installs it and answers before it restarts."""
    global ota_answer
    with open(FIRMWARE_FILE, "rb") as f:
        data = f.read()
    with open(OTA_KEY_FILE, encoding="ascii") as f:
        key = bytes.fromhex(f.read().strip())
    c = client
    start = time.monotonic()
    ota_answer = asyncio.get_running_loop().create_future()
    signature = hmac.new(key, data, hashlib.sha256).digest()
    await c.write_gatt_char(OTA_UUID, b"B" + struct.pack("<I", len(data)) + signature, response=True)
    chunk = max(20, min(500, (getattr(c, "mtu_size", 23) or 23) - 4))
    for i in range(0, len(data), chunk):
        await c.write_gatt_char(OTA_UUID, b"C" + data[i:i + chunk], response=True)
    await c.write_gatt_char(OTA_UUID, b"E", response=True)
    sent = time.monotonic() - start
    answer = await asyncio.wait_for(ota_answer, OTA_ANSWER_SECONDS)
    if answer != "u":
        raise RuntimeError("the board refused it")
    firmware_log(f"updated: {len(data)} bytes, sent in {sent:.0f} s, installed in {time.monotonic() - start - sent:.0f} s")


async def watch_firmware() -> None:
    while True:
        await asyncio.sleep(2)
        if not (os.path.exists(FIRMWARE_FILE) and ble_connected()):
            continue
        try:
            await send_firmware()
        except Exception as e:
            log_error("firmware")
            firmware_log(f"failed: {str(e) or type(e).__name__}")
        os.replace(FIRMWARE_FILE, FIRMWARE_FILE + ".last")


# ---------------------------------------------------------------- Racing sim

class SimRelay(asyncio.DatagramProtocol):
    """Telemetry from the racing sim (UDP from game/deskbuddy.py), forwarded to the board.
    'G' car and 'S' frames go to CMD as they are; the 'T' track goes to TRACK in chunks."""

    def __init__(self) -> None:
        self.car = b""
        self.track = b""
        self.frame = b""
        self.frame_sent = True
        self.race = b""             # 'R' lap / position (Forza), sent when it changes
        self.race_sent = True
        self.last = 0.0
        self.car_sent_to = None     # client the car / track were sent to (resent after a reconnect)
        self.track_sent_to = None
        self.track_task: asyncio.Task | None = None
        self.wake = asyncio.Event()

    def datagram_received(self, data: bytes, addr) -> None:
        kind = data[:1]
        self.count_message(kind, data)
        if kind == b"G":
            if data != self.car:
                self.car, self.car_sent_to = data, None
            self.last = time.monotonic()
        elif kind == b"T":
            if data != self.track:
                self.track, self.track_sent_to = data, None
            self.last = time.monotonic()
        elif kind == b"S":
            self.frame, self.frame_sent, self.last = data, False, time.monotonic()
        elif kind == b"R":
            if data != self.race:
                self.race, self.race_sent = data, False
        elif kind == b"Q":
            self.end()
        self.wake.set()

    def count_message(self, kind: bytes, data: bytes) -> None:
        """Logs what the game sent in each 5 s while it sends anything: message counts, odd lengths
        and the last frame's rpm / gear, to find why the board's racing pages drop out."""
        now = time.monotonic()
        counts = getattr(self, "counts", None)
        if counts is None or now - self.counts_at >= 5:
            if counts:
                text = " ".join(f"{k}x{n}" for k, n in sorted(counts.items()))
                if len(self.frame) == 41:
                    rpm, _boost, gear, kmh = struct.unpack_from("<ffbH", self.frame, 1)
                    text += f" | last frame rpm {rpm:.0f} gear {gear} {kmh} km/h"
                log_line("sim", text)
            self.counts, self.counts_at = {}, now
        key = kind.decode("ascii", "replace") + ("" if kind != b"S" or len(data) == 41 else f"({len(data)})")
        self.counts[key] = self.counts.get(key, 0) + 1

    def active(self) -> bool:
        return bool(self.car) and time.monotonic() - self.last < SIM_TIMEOUT_SECONDS

    def end(self) -> None:
        if self.car:
            self.car = self.track = self.frame = self.race = b""
            self.car_sent_to = self.track_sent_to = None
            asyncio.get_running_loop().create_task(write_cmd(b"Q"))

    async def run(self) -> None:
        while True:
            try:
                await asyncio.wait_for(self.wake.wait(), timeout=0.5)
            except asyncio.TimeoutError:
                pass
            self.wake.clear()
            try:
                await self._pump()
            except Exception:
                log_error("sim")

    async def _pump(self) -> None:
        if self.car and not self.active():   # the game stopped without saying goodbye
            self.end()
            return
        if not self.active() or not ble_connected():
            return
        if self.car_sent_to is not client:
            if await write_cmd(self.car):
                self.car_sent_to = client
                self.race_sent = not self.race   # after a reconnect the lap screen needs it again
        if self.track and self.track_sent_to is not client and (self.track_task is None or self.track_task.done()):
            self.track_sent_to = client
            self.track_task = asyncio.create_task(send_track(self.track))
        if not self.frame_sent:
            self.frame_sent = True
            await write_cmd(self.frame)
        if not self.race_sent:
            self.race_sent = True
            await write_cmd(self.race)


def forza_messages(data: bytes, top_kmh: float = 0.0) -> tuple[bytes, bytes, bytes, float] | None:
    """One Forza Data Out packet as the racing sim's messages: 'G' the car (a tacho to the rev limit),
    'S' a frame (rpm, boost, gear, speed; flag 4 = the lap screen, as there's no track outline for a
    minimap) and 'R' the race (position, laps done, lap times; class and PI, top speed). Also the top
    speed so far. None in menus or paused, when Forza says no race is on, or for a packet it isn't.
    Horizon 4 / 5 send 324 bytes, with 12 more between the "sled" and "dash" parts than Motorsport 7's 311."""
    dash = {324: 244, 311: 232}.get(len(data))
    if dash is None or not struct.unpack_from("<i", data, 0)[0]:
        return None
    rev_limit, _idle, rpm = struct.unpack_from("<3f", data, 8)
    _car, cls, pi = struct.unpack_from("<3i", data, 212)
    speed, = struct.unpack_from("<f", data, dash + 12)                 # m/s
    boost, = struct.unpack_from("<f", data, dash + 40)                 # psi
    best, last, cur = struct.unpack_from("<3f", data, dash + 52)       # s
    lap, pos = struct.unpack_from("<HB", data, dash + 68)
    gear = data[dash + 75]                                             # 0 = reverse, 11 = neutral
    kmh = max(0.0, speed * 3.6)
    top_kmh = max(top_kmh, kmh)
    top = max(rev_limit, 1000.0)
    car_msg = b"G" + struct.pack("<B6f", 0, top, top * FORZA_SHIFT[0], top * FORZA_SHIFT[1], top, 0.0,
                                 float(-(-int(top) // 1000) * 1000))
    gear = -1 if gear == 0 else 0 if gear > 10 else gear
    frame = b"S" + struct.pack("<ffbH7fB", rpm, boost * 0.0689476, gear, min(65535, round(kmh)),
                               0.0, 0.0, 0.0, 0.0, 300.0, 0.0, 0.0, 4)
    race = ("R" + SEP.join([str(pos), str(lap), f"{max(cur, 0):.2f}", f"{max(best, 0):.2f}", f"{max(last, 0):.2f}",
                            FORZA_CLASSES[cls] if 0 <= cls < len(FORZA_CLASSES) else "", str(max(pi, 0)),
                            str(round(top_kmh))])).encode()
    return car_msg, frame, race, top_kmh


class ForzaRelay(asyncio.DatagramProtocol):
    """Forza's Data Out telemetry (UDP on FORZA_PORT), passed on to the board through the racing sim's
    relay: the same gauge and shift light, and the lap screen in place of the minimap. ~30 frames a
    second (the game sends 60) and the lap screen 4 times a second. In menus or paused the frames stop,
    and the board goes back to its screens after SIM_TIMEOUT_SECONDS."""

    def __init__(self, relay: SimRelay) -> None:
        self.relay = relay
        self.frame_at = self.race_at = 0.0
        self.top = 0.0
        self.car_msg = b""

    def datagram_received(self, data: bytes, addr) -> None:
        now = time.monotonic()
        if now - self.frame_at < 1 / 30:
            return
        msgs = forza_messages(data, self.top)
        if msgs is None:
            return
        car_msg, frame, race, top = msgs
        if car_msg != self.car_msg:   # another car: its own top speed
            self.car_msg, top = car_msg, 0.0
        self.top = top
        self.frame_at = now
        self.relay.datagram_received(car_msg, addr)
        self.relay.datagram_received(frame, addr)
        if now - self.race_at >= 0.25:
            self.race_at = now
            self.relay.datagram_received(race, addr)


sim: SimRelay | None = None


async def send_track(data: bytes) -> None:
    """The 'T' packet as B<header>, C<points>..., E (like the cover art)."""
    c = client
    try:
        chunk = max(20, min(500, (getattr(c, "mtu_size", 23) or 23) - 4))
        await c.write_gatt_char(TRACK_UUID, b"B" + data[1:13], response=True)
        body = data[13:]
        for i in range(0, len(body), chunk):
            await c.write_gatt_char(TRACK_UUID, b"C" + body[i:i + chunk], response=True)
        await c.write_gatt_char(TRACK_UUID, b"E", response=True)
    except Exception:
        if sim is not None:
            sim.track_sent_to = None   # try again next time


def combined_color() -> bytes:
    claude = claude_state if claude_open else b"O"
    if claude == b"A":
        return b"A"
    if claude == b"D" and time.monotonic() < ask_until:
        return b"Y"   # finished with a question for you: flashing green / orange
    if b"W" in (claude, lr_state):
        return b"W"
    if b"D" in (claude, lr_state):
        return b"D"
    return b"O"


async def refresh(force: bool = False) -> bool:
    """Send the combined LED color if it changed. Returns True if the board has it."""
    global shown
    color = combined_color()
    if color == shown and not force:
        return ble_connected()
    ok = await write_cmd(color)
    if ok:
        shown = color
    return ok


def file_size(path: str) -> int:
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def turn_asked(path: str) -> tuple:
    """The question Claude's last turn ended with, if any: the Claude app's next-step box (its
    wrap_up tool) with a question in it, and its reply buttons' labels (not app actions like commit).
    Reads the transcript backwards to your last message."""
    try:
        with open(path, "rb") as f:
            f.seek(max(0, file_size(path) - 512 * 1024))
            lines = f.read().splitlines()
    except OSError:
        return "", ()
    for line in reversed(lines):
        try:
            e = json.loads(line)
        except ValueError:
            continue   # the first line of the chunk is usually cut off
        if not isinstance(e, dict):
            continue
        content = (e.get("message") or {}).get("content")
        if e.get("type") == "assistant" and isinstance(content, list):
            for c in content:
                if isinstance(c, dict) and c.get("type") == "tool_use" and str(c.get("name", "")).endswith("__wrap_up"):
                    i = c.get("input") or {}
                    actions = i.get("actions")
                    if isinstance(actions, str):
                        try:
                            actions = json.loads(actions)
                        except ValueError:
                            actions = []
                    labels = tuple(str(a.get("label")) for a in actions or [] if isinstance(a, dict)
                                   and a.get("label") and not a.get("action"))[:2]
                    return str(i.get("ask") or "").strip(), labels
        elif e.get("type") == "user" and not e.get("isMeta"):
            if isinstance(content, str) or (isinstance(content, list) and not any(
                    isinstance(c, dict) and c.get("type") == "tool_result" for c in content)):
                return "", ()   # back at your message: this turn didn't ask
    return "", ()


async def handle_hook(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    global claude_state, transcript, transcript_pos, ask_until
    try:
        data = await asyncio.wait_for(reader.readline(), timeout=2)
        letter, path, info = (data.decode("utf-8", "ignore").strip().split("\t", 2) + ["", ""])[:3]
        if letter and ask_options and path and path != transcript:
            # another session: note it, but the open question with options keeps the screens until answered
            running.pop(path, None)
            if letter[0] in "WA":
                running[path] = [file_size(path), letter[0].encode()]
            writer.write(b"1")
            await writer.drain()
        elif letter:
            claude_state = letter[0].encode()
            if path:
                transcript, transcript_pos = path, file_size(path)
                running.pop(path, None)
                if claude_state in (b"W", b"A"):
                    running[path] = [transcript_pos, claude_state]
            # Finished with a question box: flash for ASK_FLASH_SECONDS. Any other hook stops it.
            asked = claude_state == b"D" and bool(transcript) and (await asyncio.to_thread(turn_asked, transcript))[0]
            ask_until = time.monotonic() + ASK_FLASH_SECONDS if asked else 0.0
            ok = await refresh()
            # Tell the hook to use USB only when the board missed it; USB sends the raw letter,
            # so only ask for that when the combined color is Claude's own.
            writer.write(b"1" if ok or combined_color() not in (claude_state, b"Y") else b"0")
            await writer.drain()
            await on_hook(claude_state, json.loads(info) if info else {})
    except Exception:
        pass
    finally:
        writer.close()


async def watch_apps() -> None:
    lightroom = LightroomWatcher()
    while True:
        try:
            await _watch_once(lightroom)
        except Exception:
            log_error("watch_apps")
        try:
            await media.poll()
        except Exception:
            log_error("media")
        try:
            for note in await asyncio.to_thread(notifier.poll):
                await write_cmd(notification_msg(*note))
        except Exception:
            log_error("notifications")
        try:
            for msg in await asyncio.to_thread(fantasy.poll):
                await write_cmd(msg)
        except Exception:
            log_error("fantasy")
        try:
            await screens.poll()
        except Exception:
            log_error("screens")
        await asyncio.sleep(CHECK_SECONDS)


def notification_msg(app: str, title: str, text: str, count: int = 1, at: str = "") -> bytes:
    """T<app>␟<title>␟<message>␟<count>␟<HH:MM>: kept short enough for one Bluetooth write."""
    return ("T" + SEP.join([ascii_text(app, 20), ascii_text(title, 40), ascii_text(text, 120),
                            str(min(count, 9999)), at])).encode()


def prune_running() -> None:
    """Drops sessions that were stopped or closed, which fire no hook."""
    for path, entry in list(running.items()):
        size = file_size(path)
        try:
            if time.time() - os.path.getmtime(path) > RUNNING_QUIET_SECONDS:
                del running[path]
            elif size > entry[0]:
                with open(path, "rb") as f:
                    f.seek(entry[0])
                    new = f.read(size - entry[0])
                entry[0] = size
                if INTERRUPT_MARKER in new:
                    del running[path]
        except OSError:
            del running[path]


def back_to_running() -> None:
    """The session on show finished: show the latest one still working, once any question has had its flash."""
    global claude_state, transcript, transcript_pos
    if running and claude_state not in (b"W", b"A") and time.monotonic() >= ask_until and not ask_options:
        transcript = next(reversed(running))
        transcript_pos, claude_state = running[transcript]
        log_line("claude", "back to a session still running")


async def _watch_once(lightroom: LightroomWatcher) -> None:
    global claude_open, claude_state, transcript_pos
    claude_open = is_claude_window_open()
    prune_running()
    back_to_running()

    # A stopped prompt fires no hook; spot it in the transcript instead.
    if claude_state in (b"W", b"A") and transcript:
        size = file_size(transcript)
        if size > transcript_pos:
            try:
                with open(transcript, "rb") as f:
                    f.seek(transcript_pos)
                    new = f.read(size - transcript_pos)
                transcript_pos = size
                if INTERRUPT_MARKER in new:
                    claude_state = b"D"
            except OSError:
                pass

    await asyncio.to_thread(lightroom.poll)
    await refresh()
    await clear_claude_extras()
    await solidworks.poll()


TYPE_ANSWER = r"""
Add-Type -Name U -Namespace W -MemberDefinition '
[DllImport("user32.dll")] public static extern System.IntPtr GetForegroundWindow();
[DllImport("user32.dll")] public static extern int GetWindowThreadProcessId(System.IntPtr h, out int p);
[DllImport("user32.dll")] public static extern bool SetForegroundWindow(System.IntPtr h);
[DllImport("user32.dll")] public static extern bool ShowWindow(System.IntPtr h, int c);
[DllImport("user32.dll")] public static extern bool IsIconic(System.IntPtr h);
[DllImport("user32.dll")] public static extern void keybd_event(byte k, byte s, int f, int e);'
$app = Get-Process claude -ErrorAction SilentlyContinue | ? MainWindowTitle | Select -First 1
if (-not $app) { exit 1 }
$h = $app.MainWindowHandle
if ([W.U]::IsIconic($h)) { [void][W.U]::ShowWindow($h, 9) }
if ([W.U]::GetForegroundWindow() -ne $h) {   # Claude already in front: no Alt, which could open its menu
    [W.U]::keybd_event(0x12, 0, 0, 0); [W.U]::keybd_event(0x12, 0, 2, 0)   # an Alt tap lets a background app take the focus
    [void][W.U]::SetForegroundWindow($h)
}
Start-Sleep -Milliseconds 400
$fg = 0; [void][W.U]::GetWindowThreadProcessId([W.U]::GetForegroundWindow(), [ref]$fg)
if ($fg -ne $app.Id) { exit 2 }   # something else has the keyboard: type nothing, press again
(New-Object -ComObject WScript.Shell).SendKeys(($env:DESKBUDDY_ANSWER -replace '([+^%~(){}\[\]])', '{$1}') + '~')
"""


def app_chat_id(path: str) -> str:
    """The Claude app's id (local_...) for the chat whose transcript this is, from its session files."""
    cli = os.path.splitext(os.path.basename(path))[0]
    base = os.path.join(os.environ["LOCALAPPDATA"], "Claude-Data")
    for f in glob.glob(os.path.join(base, "*", "claude-code-sessions", "**", "local_*.json"), recursive=True):
        try:
            with open(f, encoding="utf-8") as fh:
                if json.load(fh).get("cliSessionId") == cli:
                    return os.path.splitext(os.path.basename(f))[0]
        except (OSError, ValueError):
            pass
    return ""


async def answer_ask(i: int) -> None:
    """Type the picked button's label into the Claude app and send it, as clicking that button does.
    shortcut: types into whichever chat the app has open, so pick only with the asking chat on screen."""
    global ask_until
    if i >= len(ask_options):
        return
    label = ask_options[i]
    chat = await asyncio.to_thread(app_chat_id, ask_path)
    if chat:   # open the chat that asked, so the answer can't land in another one
        os.startfile(f"claude://code/continue?session={chat}")
        await asyncio.sleep(1.5)
    env = dict(os.environ, DESKBUDDY_ANSWER=label)
    r = await asyncio.to_thread(subprocess.run, ["powershell", "-NoProfile", "-Command", TYPE_ANSWER],
                                env=env, creationflags=subprocess.CREATE_NO_WINDOW, capture_output=True)
    log_line("claude", f"board picked option {i + 1} ({len(label)} chars), typed: {r.returncode == 0}")
    if r.returncode == 0:
        ask_until = 0.0
        await set_ask()


def on_touch(_char, data: bytearray) -> None:
    if data[:1] == b"#":   # a line about the iPhone's link, not a touch
        log_line("board", data[1:].decode(errors="replace"))
        return
    for b in bytes(data):
        if chr(b) in "ux":   # the answer to a firmware update, not a touch
            if ota_answer is not None and not ota_answer.done():
                ota_answer.set_result(chr(b))
            continue
        if chr(b) in "12":   # a pick on Claude's question
            asyncio.get_running_loop().create_task(answer_ask(int(chr(b)) - 1))
            continue
        asyncio.get_running_loop().create_task(media.handle_touch(chr(b)))


async def keep_connected() -> None:
    global client
    last_err = ""
    while True:
        try:
            device = await BleakScanner.find_device_by_name(DEVICE_NAME, timeout=10)
            if device is None:
                await asyncio.sleep(3)
                continue
            disconnected = asyncio.Event()
            client = BleakClient(device, disconnected_callback=lambda _: disconnected.set())
            await client.connect()
            try:
                await client.start_notify(TOUCH_UUID, on_touch)
            except Exception:
                # connected before the board's services were readable (it was still booting):
                # start over, or the touch sensors would do nothing until the next reconnect
                log_error("touch notify")
                raise
            await refresh(force=True)  # restore the right color after (re)connecting
            media.resend_all()
            screens.resend()
            for msg in fantasy.last:
                await write_cmd(msg)
            await write_cmd(activity_msg)
            await write_cmd(ask_msg, confirm=True)
            await solidworks.resend()
            log_line("helper", "connected to the board")
            await disconnected.wait()
            log_line("helper", "lost the board")
        except Exception as e:
            if repr(e) != last_err:   # once per new error, so a stuck reconnect shows in the log
                last_err = repr(e)
                log_line("helper", f"reconnect failed: {last_err[:150]}")
            await asyncio.sleep(3)
        finally:
            if client is not None:
                try:
                    await client.disconnect()
                except Exception:
                    pass
            client = None


async def main() -> None:
    global sim
    server = await asyncio.start_server(handle_hook, "127.0.0.1", LISTEN_PORT)
    sim = SimRelay()
    await asyncio.get_running_loop().create_datagram_endpoint(lambda: sim, local_addr=("127.0.0.1", SIM_PORT))
    try:   # Forza's telemetry (another app on that port, such as SimHub, just means no Forza here)
        await asyncio.get_running_loop().create_datagram_endpoint(lambda: ForzaRelay(sim), local_addr=("127.0.0.1", FORZA_PORT))
    except OSError:
        log_error("forza")
    async with server:
        await asyncio.gather(keep_connected(), watch_apps(), sim.run(), solidworks.run(), watch_firmware())


async def test_media() -> None:
    """Print what the buddy would be sent, without Bluetooth."""
    async def fake_write(data: bytes) -> bool:
        print("  ->", data.decode(errors="replace").replace(SEP, " | "))
        return True
    globals()["write_cmd"] = fake_write
    for _ in range(6):
        await media.poll()
        if media.cover:
            print(f"  cover: {len(media.cover)} byte JPEG, {COVER_SIZE}x{COVER_SIZE}")
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "cover-test.jpg"), "wb") as f:
                f.write(media.cover)
            media.cover = b""
        await asyncio.sleep(1)


def test_notifications(seconds: float = 120) -> None:
    """Print phone notifications as they arrive, without Bluetooth."""
    print(f"Watching for Phone Link notifications for {seconds:.0f} s (send yourself a message)...")
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        for note in notifier.poll():
            print("  ->", notification_msg(*note).decode(errors="replace").replace(SEP, " | "))
        time.sleep(1)


def test_forza(seconds: float = 30) -> None:
    """Print what Forza's Data Out sends, once a second, without Bluetooth. The running helper has the
    port, so end pythonw.exe in Task Manager first (the scheduled task starts it again within a minute)."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.bind(("127.0.0.1", FORZA_PORT))
    except OSError:
        print(f"Port {FORZA_PORT} is in use: the helper (or another app, such as SimHub) is listening there already.")
        return
    s.settimeout(1.0)
    print(f"Listening for Forza on 127.0.0.1:{FORZA_PORT} for {seconds:.0f} s (drive: in menus it sends nothing useful)...")
    end, shown, top, got = time.monotonic() + seconds, 0.0, 0.0, False
    while time.monotonic() < end:
        try:
            data, _ = s.recvfrom(1024)
        except socket.timeout:
            continue
        got = True
        msgs = forza_messages(data, top)
        if msgs is None or time.monotonic() - shown < 1:
            continue
        shown, top = time.monotonic(), msgs[3]
        rpm, _boost, gear, kmh = struct.unpack_from("<ffbH", msgs[1], 1)
        print(f"  {rpm:5.0f} rpm  gear {gear}  {kmh} km/h  | race: " + msgs[2][1:].decode().replace(SEP, " | "))
    if not got:
        print("  nothing came: check Data Out in the game's settings (and the loopback exemption for the Microsoft Store version)")


def test_fantasy() -> None:
    """Print your fantasy matchup as the buddy would get it, without Bluetooth."""
    s = load_fantasy_settings()
    if not s:
        print(f"Put your league id in {FANTASY_SETTINGS} first (and espn_s2 / swid for a private league).")
        return
    print(f"Checking ESPN league {s['league_id']} ({fantasy_season()} season)...")
    msgs = fantasy.poll()
    for msg in msgs:
        print("  ->", msg.decode(errors="replace").replace(SEP, " | "))
    if not msgs:
        print(f"  nothing to send; see {LOG_FILE}")


if __name__ == "__main__":
    if "--test-fantasy" in sys.argv:
        test_fantasy()
        sys.exit()
    if "--test-forza" in sys.argv:
        test_forza()
        sys.exit()
    if "--test-media" in sys.argv:
        asyncio.run(test_media())
        sys.exit()
    if "--test-notifications" in sys.argv:
        test_notifications()
        sys.exit()
    while True:   # restart instead of exiting if anything unexpected goes wrong
        try:
            asyncio.run(main())
        except OSError:
            break   # port 47800 already in use: another copy is running (the watchdog task relies on this)
        except Exception:
            log_error("main")
            time.sleep(5)
