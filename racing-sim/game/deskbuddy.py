"""
DeskBuddy link: streams the driving session to the DeskBuddy desk display
(ESP32-S3 with two round screens and an RGB LED) through its PC helper
(%USERPROFILE%\\.claude\\claude-led\\claude-led-ble.py), which forwards it
over Bluetooth.

  left screen   turbo boost gauge (turbo cars) or a tachometer (the rest)
  right screen  the minimap: the same heading-up, zooming view as ui/minimap.py
  RGB LED       shift light from the car's HUD shift points:
                green, yellow, orange, red, flashing red

UDP to 127.0.0.1:47801, fire and forget: when the helper isn't running the
packets go nowhere, and the game never waits on it or fails because of it.

Packets (little-endian):
  'G' car    u8 turbo, f32 rpm_max, shift_start, shift_end, limiter, gauge_min, gauge_max
  'T' track  u16 main points, u16 pit points, f32 metres per unit, f32 metres between
             main points, then int16 (x, y) pairs: the circuit, then the pit lane
  'S' frame  f32 rpm, boost (bar, gauge), i8 gear, u16 km/h, f32 x, y (m, track-centred),
             map heading, arrow angle, visible radius (m), s (m), look-ahead (m), u8 flags
  'Q' the session is over
"""
import math
import socket
import struct
import time

PORT = 47801
FRAME_HZ = 30
RESEND_SECONDS = 5.0      # car + track again, for a helper started after the race
TRACK_STEP = 10.0         # metres between minimap points sent to the board
MAX_POINTS = 2400         # circuit points (the board holds 6000 in all)
FLAG_PIT, FLAG_PAUSED = 1, 2


class DeskBuddyLink:
    def __init__(self):
        self.sock = None
        self.car_msg = self.track_msg = None
        self.cx = self.cy = 0.0
        self.next_frame = self.next_resend = 0.0

    def _send(self, data):
        try:
            if self.sock is None:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.sock.setblocking(False)
            self.sock.sendto(data, ('127.0.0.1', PORT))
        except OSError:
            pass

    # -------------------------------------------------------- session
    def begin(self, car, track):
        """RaceScene.enter(): describe the car and the circuit."""
        try:
            self.car_msg = self._car_msg(car)
            self.track_msg = self._track_msg(track)
        except Exception:
            self.car_msg = self.track_msg = None      # never let the display break the game
            return
        self.next_frame = 0.0
        self.next_resend = 0.0

    def end(self):
        """RaceScene.exit(): the board goes back to its eyes."""
        if self.car_msg is not None:
            self._send(b'Q')
        self.car_msg = self.track_msg = None

    def update(self, car, view, timer, paused):
        """RaceScene.update(), after the minimap view has moved."""
        if self.car_msg is None:
            return
        now = time.perf_counter()
        if now < self.next_frame:
            return
        self.next_frame = now + 1.0 / FRAME_HZ
        if now >= self.next_resend:
            self.next_resend = now + RESEND_SECONDS
            self._send(self.car_msg)
            self._send(self.track_msg)
        if view.heading is None:
            return
        try:
            eng = car.engine
            flags = (FLAG_PIT if getattr(timer, 'in_pit', False) else 0) | (FLAG_PAUSED if paused else 0)
            gear = max(-1, min(20, car.gearbox.gear))
            kmh = int(min(65535.0, abs(car.u) * 3.6))
            self._send(b'S' + struct.pack('<ffbHfffffffB', eng.rpm, eng.boost_gauge, gear, kmh,
                                          view.x - self.cx, view.y - self.cy,
                                          math.fmod(view.heading, 2.0 * math.pi), view.marker_angle(),
                                          view.radius, view.s, view.ahead, flags))
        except Exception:
            pass

    # ------------------------------------------------------- messages
    @staticmethod
    def _car_msg(car):
        cfg, eng, H = car.cfg, car.engine, car.cfg.HUD
        turbo = cfg.TURBO is not None
        if turbo:
            # the boost the controller holds (wastegate) or the pop-off valve's cap
            top = eng.turbo.wg_boost if eng.turbo.wg_boost is not None else cfg.TURBO['boost_limit']
            gmin, gmax = -1.0, math.ceil((top - eng.ambient + 0.15) * 2.0) / 2.0
        else:
            gmin, gmax = 0.0, H['rpm_max']
        return b'G' + struct.pack('<Bffffff', 1 if turbo else 0, H['rpm_max'], H['shift_start'],
                                  H['shift_end'], cfg.ENGINE['limiter_rpm'], gmin, gmax)

    def _track_msg(self, track):
        k = max(1, int(round(TRACK_STEP / track.step)))
        if track.n / k > MAX_POINTS:
            k = math.ceil(track.n / MAX_POINTS)
        main = list(zip(track.xs[::k], track.ys[::k]))
        pit = getattr(track, 'pit', None)
        pit_pts = []
        if pit is not None:
            kp = max(1, int(round(TRACK_STEP / pit.step)))
            pit_pts = list(zip(pit.xs[::kp], pit.ys[::kp]))
        pts = main + pit_pts
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        self.cx = 0.5 * (min(xs) + max(xs))
        self.cy = 0.5 * (min(ys) + max(ys))
        ext = max(max(abs(x - self.cx) for x in xs), max(abs(y - self.cy) for y in ys))
        scale = max(0.01, ext / 32000.0)                 # metres per int16 unit
        body = struct.pack(f'<{2 * len(pts)}h',
                           *(int(round(v / scale)) for x, y in pts for v in (x - self.cx, y - self.cy)))
        return b'T' + struct.pack('<HHff', len(main), len(pit_pts), scale, k * track.step) + body


link = DeskBuddyLink()
