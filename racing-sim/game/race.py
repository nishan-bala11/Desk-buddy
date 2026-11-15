"""
Driving session (the 'race' scene): the fixed-step physics loop, the HUD
and the pause menu, unchanged in behaviour from the original main loop.

Simulation runs at a fixed physics_dt (config: SIM.physics_hz) using an
accumulator; rendering runs as fast as the hardware allows and interpolates
between the last two physics states.

Everything a session creates - the physics vehicle (its own config and the
setup chosen in the garage), lap timer, pit stop, exhaust, the minimap's
view state - is created in enter() and released in exit(): the renderer is
pointed back at the studio car, rubber marks / smoke / flames are cleared,
the sound stream stops, the controller vibration stops and the controller
settings are saved. Nothing of a session survives into the next one, and
the circuit's world (built once) is reused untouched.

Controller vibration (input/haptics.py) reads every physics step after the
barrier check (sample(), with the velocity change the barrier applied) and
plays only while the pad is the device driving the car and the session is
not paused.

The time of day (game/daytime.py) is lit before the first frame; in the
day-night cycle its clock runs with the race - by the frame's delta time,
never while paused - and the circuit is relit whenever the sun has moved
(rendering/daylight.py, Renderer.set_daylight). A restart keeps the time;
leaving the session saves where the cycle has got to.
"""
import math
import os
import time

import pygame
from pygame.locals import KEYDOWN

from config import cars
from input.controls import CONTROLLER
from physics.vehicle import Vehicle
from physics.exhaust import Exhaust
from race.pitstop import PitStop
from track.timing import LapTimer
from ui.hud import HELP, MOUSE_HELP, pad_help
from ui.minimap import layout as minimap_layout
from game.scene import Scene
from game.deskbuddy import link as deskbuddy

MAX_STEPS_PER_FRAME = 16
DOUBLE_CLICK = 0.35           # s between two clicks of a double-click (the camera looks ahead again)
YELLOW_MSG = (250, 210, 40)
RELIGHT_MIN = 0.1             # game minutes of the cycle between relighting the circuit (0.025 deg of sun)

# Scripted inputs for verifying visuals against the physics (--demo NAME).
# (start s [m], start speed [km/h], gear, function(t, car) -> (throttle, brake, steer))
DEMOS = {
    'lockup': (1700.0, 290.0, 6, lambda t, c: (0.0, 1.0 if t > 0.3 else 0.0, 0.0)),      # Kemmel
    'wheelspin': (60.0, 0.0, 1, lambda t, c: (1.0, 0.0, 0.0)),                          # grid
    'slide': (3560.0, 190.0, 4, lambda t, c: (0.0, 0.0, 2.4 if t > 0.2 else 0.0)),       # into Pouhon
    'powerslide': (2990.0, 70.0, 2, lambda t, c: (1.0, 0.0, 1.2)),                     # Bruxelles exit
    'kerb': (2390.0, 140.0, 4, lambda t, c: (0.3, 0.0, 0.25)),                         # Les Combes left
    # pull hard in 3rd, then lift: overrun afterfire (the car's exhaust model decides)
    'flames': (1500.0, 150.0, 3, lambda t, c: (1.0 if t < 2.2 else 0.0, 0.0, 0.0)),    # Kemmel
}

# keyboard -> action (shared with the controller's button actions)
KEY_ACTIONS = {
    pygame.K_e: 'upshift', pygame.K_q: 'downshift', pygame.K_r: 'reset', pygame.K_c: 'camera',
    pygame.K_F1: 'telemetry', pygame.K_TAB: 'telemetry', pygame.K_b: 'abs', pygame.K_t: 'tcs',
    pygame.K_h: 'help', pygame.K_LEFTBRACKET: 'bias_down', pygame.K_RIGHTBRACKET: 'bias_up',
    pygame.K_F2: 'pad_debug', pygame.K_ESCAPE: 'pause', pygame.K_l: 'limiter',
    pygame.K_1: 'tyre_soft', pygame.K_2: 'tyre_medium', pygame.K_3: 'tyre_hard',
    pygame.K_4: 'tyre_intermediate', pygame.K_5: 'tyre_wet', pygame.K_0: 'tyre_keep',
    pygame.K_x: 'drs', pygame.K_m: 'mute', pygame.K_g: 'das',
}


def snapshot(car):
    return (car.x, car.y, car.z, car.yaw, car.pitch, car.roll,
            tuple(car.steer_angles), tuple(car.spin), tuple(car.wheel_offset),
            0.5 * (car.zroad[0] + car.zroad[3]),
            tuple(car.omega), tuple(car.fx), tuple(car.fy),
            tuple(car.zw[i] - car.zroad[i] for i in range(4)))


def _lerp_ang(a, b, t):
    d = (b - a + math.pi) % (2.0 * math.pi) - math.pi
    return a + d * t


def interpolate(p, c, t):
    pose = (p[0] + (c[0] - p[0]) * t, p[1] + (c[1] - p[1]) * t, p[2] + (c[2] - p[2]) * t,
            _lerp_ang(p[3], c[3], t), p[4] + (c[4] - p[4]) * t, p[5] + (c[5] - p[5]) * t)
    wheels = []
    for i in range(4):
        steer = p[6][i] + (c[6][i] - p[6][i]) * t
        spin = _lerp_ang(p[7][i], c[7][i], t)
        offset = p[8][i] + (c[8][i] - p[8][i]) * t
        wheels.append((steer, spin, offset, c[10][i], c[11][i], c[12][i], c[13][i]))
    ground = p[9] + (c[9] - p[9]) * t
    return pose, wheels, ground


def grid_s(track):
    """Where a session starts: the circuit's own standing-start position, or
    80 m before the line (Spa's grid)."""
    return getattr(track, 'grid_s', track.length - 80.0)


def grid_d(track):
    """Lateral offset of the start position (+ left): the circuit's pole
    slot (Monza), or the centreline."""
    return getattr(track, 'grid_d', 0.0)


def spawn(car, track, s, gear=0, reset_tires=True, d=0.0):
    x, y, h = track.pose_at(s % track.length, d)
    # where the lap crosses itself (Suzuka) the place alone does not say
    # which road: the car starts on the sample at s
    hint = int(s % track.length / track.step) % track.n if getattr(track, 'crossings', None) else None
    car.reset(x, y, h, gear=gear, reset_tires=reset_tires, hint=hint)


def virtual_pad_script(vp, t):
    """--virtual-pad: a scripted pad to check the controller path end to end
    without hardware (smooth steering sweeps, trigger ramps)."""
    vp.buttons['a'] = 0.2 < t < 0.3 or 3.0 < t < 3.1      # A: into 1st, then 2nd
    vp.axes['leftx'] = 0.45 * math.sin((t - 2.0) * 0.9) if t > 2.0 else 0.0
    vp.axes['righttrigger'] = min(0.8, max(0.0, (t - 0.5) * 0.5)) if t < 6.0 else 0.0
    vp.axes['lefttrigger'] = 0.6 if 6.0 < t < 7.0 else 0.0


class RaceScene(Scene):
    name = 'race'
    menu = False

    def __init__(self, app):
        super().__init__(app)
        self.car = None
        self.pause = None
        self.override = None          # (throttle, brake, steer, seconds left): automation
        self.mouse = dict(drag=None, down=None)

    @property
    def _rects(self):
        """The pause menu's clickable controls while it is open (game/script.py
        click=@name, rects)."""
        st = getattr(self, 'st', None)
        if self.pause is not None and st and st.get('paused'):
            return self.pause.rects()
        return {}

    # ------------------------------------------------------- lifecycle
    def enter(self, car=None, setup=None):
        app = self.app
        a = app.args
        r = app.renderer
        world = app.world
        track = world['track']
        first = app.races == 0 and app.direct
        app.races += 1
        key = car or app.sel_car
        cfg = cars.load(key)
        self.key = key
        self.track = track
        self.car = Vehicle(surface=track, cfg=cfg)
        if setup:
            self.car.apply_setup(setup)
        self.timer = LapTimer(track)
        self.pit = PitStop(track, self.car)
        self.exhaust = Exhaust(cfg.EXHAUST, cfg.ENGINE['limiter_rpm'])
        for o in (self.car, self.timer, self.pit, self.exhaust):
            app.tracked.add(o)
        r.set_car(self.car)
        r.exhaust = self.exhaust
        r.pit_stop = self.pit
        r.effects.reset()
        r.camera.tv_hint = None
        r.camera.inspect = tuple(float(v) for v in a.inspect.split(',')) if a.inspect else None
        r.camera.reset_look()
        r.camera.drag_mode = app.controls.pad.settings.camera['drag']
        self.mouse = dict(drag=None, down=None)
        if first:
            r.camera.mode = a.camera
        controls = app.controls
        controls.set_car(cfg.PEDALS, cfg.STEERING)
        controls.reset()
        if app.haptics is not None:
            app.haptics.begin_session(self.car)
        if app.audio is not None:
            app.audio.set_car(cfg)
        self.minimap = world['minimap']
        self.minimap.view.reset()
        hud = app.hud
        self.demo = None
        self.auto = None
        car, pit = self.car, self.pit
        if first and a.tyres and a.tyres in car.cfg.TIRE_COMPOUNDS:
            for i in range(4):
                car.fit_tyre(i, a.tyres, temp=car.cfg.TIRE_THERMAL['initial_temp'])
            pit.selected = a.tyres
        demo = DEMOS.get(a.demo) if first else None
        if first and a.autopilot == 'pit':
            from race.autopilot import PitAutopilot
            self.auto = PitAutopilot(track, car, pit)
            pit.select(a.tyres or 'soft')
            x, y, hd = track.pose_at(6645.0)
            car.reset(x, y, hd, gear=2, speed=45 / 3.6)
        elif demo:
            self.demo = demo
            x, y, hd = track.pose_at(demo[0])
            car.reset(x, y, hd, gear=demo[2], speed=demo[1] / 3.6)
        elif first and a.pit_start and track.pit is not None and track.pit.player_box is not None:
            bs, bd = track.pit.boxes[track.pit.player_box]
            x, y, hd = track.pit.pose_at(bs - car.a, bd)
            car.reset(x, y, hd, gear=0, reset_tires=False)
        else:
            spawn(car, track, grid_s(track) if (a.start is None or not first) else a.start, gear=0,
                  d=grid_d(track) if (a.start is None or not first) else 0.0)
        if first:
            if a.abs:
                car.abs_enabled = True             # (cars with ABS fitted start with it on)
            if a.tcs:
                car.tcs_enabled = True
            if a.tire_temp is not None or a.tire_wear is not None:
                car.thermal.reset(temp=a.tire_temp, wear=a.tire_wear)
            hud.show_tele = a.telemetry
            hud.show_pad = a.pad_debug or a.virtual_pad
        hud.show_help = not a.screenshot
        hud.help_timer = 12.0 if first else 10.0
        from ui.overlays import PauseMenu
        self.pause = PauseMenu(app, self)
        self.st = dict(prev=snapshot(car), acc=0.0, paused=bool(first and a.paused), reason=None)
        self.st['curr'] = self.st['prev']
        if self.st['paused']:
            self.pause.open()
        self.frames = 0
        self.hud_timer = self.tele_timer = 0.0
        self.fps = 0.0
        self.override = None
        self.pose = None
        self.t_enter = time.perf_counter()
        # the time of day lit before the first frame (no flash of daylight)
        self.lit_at = None
        self.relight()
        app.log(f"race light {app.daytime.describe()}")
        ps = getattr(r.car_r, 'paint_state', None)
        app.log(f"race paint {key}: {ps.scheme['name'] if ps is not None and ps.scheme else 'own colours'}")
        pygame.display.set_caption(f"{cfg.INFO['name']} @ {track.name} - physics sim")
        deskbuddy.begin(self.car, track)         # boost gauge, minimap and shift light on the desk display

    def clock_text(self):
        """The time of day for the HUD: the clock, and the cycle's speed."""
        from rendering.daylight import fmt_hhmm
        d = self.app.daytime
        return fmt_hhmm(d.minutes) + (f" x{d.speed:g}" if d.mode == 'cycle' else "")

    def relight(self, force=True):
        """Light the circuit for the time of day (when the clock has moved
        enough, or forced)."""
        app = self.app
        m = app.daytime.minutes
        if not force and self.lit_at is not None:
            dm = abs((m - self.lit_at + 720.0) % 1440.0 - 720.0)
            if dm < RELIGHT_MIN:
                return
        self.lit_at = m
        app.apply_daylight(app.world['key'])

    def exit(self):
        app = self.app
        r = app.renderer
        app.daytime.save()                       # where the day-night cycle has got to
        if app.audio is not None:
            app.audio.stop()
            try:
                pygame.mixer.stop()               # one-shots (pops, shift clunks)
            except pygame.error:
                pass
        if app.haptics is not None:
            app.haptics.end_session()            # motors off, nothing of this car kept
        if self.pause is not None:
            self.pause.close_all()               # saves changed controller settings
        r.effects.reset()
        r.exhaust = None
        r.pit_stop = None
        r.pit_light_state = 'off'
        if r.crew is not None:
            for m in r.crew.members:
                m.x = None
        # point the renderer back at the studio car: nothing keeps this
        # session's vehicle alive
        show = app.show_cars[self.key]
        r.set_car(show)
        r.camera.inspect = None
        app.controls.reset()
        self.minimap.view.reset()
        deskbuddy.end()
        self.car = self.timer = self.pit = self.exhaust = None
        self.demo = self.auto = None
        self.pause = None
        self.pose = None
        pygame.display.set_caption("Spa - physics sim")

    # -------------------------------------------------------- session
    def has_progress(self):
        """Would leaving lose something the player achieved? (a lap
        started or completed, a pit stop made)"""
        t = self.timer
        return bool(t.running or t.lap > 0 or t.best_lap is not None or (self.pit and self.pit.stops))

    def reset_car(self, full):
        car, track, timer, pit = self.car, self.track, self.timer, self.pit
        r = self.app.renderer
        controls = self.app.controls
        if full:
            spawn(car, track, grid_s(track), gear=0, d=grid_d(track))
            timer.reset()
            r.effects.reset()
            pit.reset()
            self.exhaust.reset()
            self.minimap.view.reset()
        elif pit.holding:
            controls.pad.message = ("Reset not available during the pit stop", 2.5)
            return
        elif pit.in_pit:
            # back on the pit lane (fast lane), not onto the circuit
            x, y, hd = pit.respawn_pose()
            car.reset(x, y, hd, gear=1, reset_tires=False)
            timer.invalidate()
        else:
            # tyre temperature/wear carry over, as on a real car
            spawn(car, track, timer.s, gear=1, reset_tires=False)
            timer.invalidate()
        controls.reset()
        if self.app.haptics is not None:
            self.app.haptics.clear()             # a jump of the car is not an impact
        self.st['prev'] = self.st['curr'] = snapshot(car)
        self.st['acc'] = 0.0

    def resume(self):
        st = self.st
        st['paused'] = False
        st['reason'] = None
        self.pause.close_all()                   # saves changed controller settings
        pygame.key.set_repeat()

    def open_pause(self, reason=None):
        self.end_drag()                          # (the button may be let go over the menu)
        self.st['paused'] = True
        if self.app.haptics is not None:
            self.app.haptics.driving = False
            self.app.haptics.stop()
        if reason:
            self.st['reason'] = reason
        self.pause.open()
        from game.app import KEY_REPEAT
        pygame.key.set_repeat(*KEY_REPEAT)

    def action(self, a):
        car, pit, hud = self.car, self.pit, self.app.hud
        r = self.app.renderer
        audio = self.app.audio
        if a == 'upshift':
            car.gearbox.request_up()
        elif a == 'downshift':
            car.gearbox.request_down()
        elif a == 'reset':
            self.reset_car(False)
        elif a == 'reset_full':
            self.reset_car(True)
        elif a == 'camera':
            r.camera.cycle()
        elif a == 'telemetry':
            hud.show_tele = not hud.show_tele
        elif a == 'pad_debug':
            hud.show_pad = not hud.show_pad
        elif a == 'abs':
            car.abs_enabled = not car.abs_enabled
        elif a == 'tcs':
            car.tcs_enabled = not car.tcs_enabled
        elif a == 'help':
            hud.show_help = not hud.show_help
            hud.help_timer = 1e9
        elif a == 'bias_down':
            car.brakes.adjust_bias(-1)
        elif a == 'bias_up':
            car.brakes.adjust_bias(1)
        elif a == 'pause':
            self.open_pause()
        elif a == 'limiter':
            car.pit_limiter = not car.pit_limiter
        elif a.startswith('tyre_'):
            if a == 'tyre_keep':
                pit.toggle_tyres()
            else:
                pit.select(a[5:])
        elif a == 'drs':
            if car.drs_fitted:
                if car.drs_mode != 'manual':
                    car.drs_mode = 'manual'
                car.drs_request = not car.drs_request
        elif a == 'das':
            # dual-axis steering (W11): pull / push the wheel (switches DAS to manual)
            if car.das_fitted:
                if car.das_mode != 'manual':
                    car.das_mode = 'manual'
                car.das_request = not car.das_request
        elif a == 'mute':
            if audio is not None:
                audio.muted = not audio.muted

    # ---------------------------------------------------------- input
    def on_event(self, ev):
        if ev.type != KEYDOWN:
            if self.st['paused']:
                self.pause.on_event(ev)
            else:
                self.on_mouse(ev)
            return
        if self.st['paused']:
            self.pause.on_event(ev)
            return
        k = ev.key
        a = KEY_ACTIONS.get(k)
        if a == 'reset' and ((ev.mod if hasattr(ev, 'mod') else 0) | pygame.key.get_mods()) & pygame.KMOD_SHIFT:
            a = 'reset_full'
        if a:
            self.action(a)

    def on_mouse(self, ev):
        """The mouse while driving (nothing else in the race takes it - the
        minimap and the HUD don't - and the pause menu has it while paused):
        drag with the left button to look around, the wheel to zoom, a
        double-click to look ahead again (rendering/camera.py)."""
        cam = self.app.renderer.camera
        if cam.inspect is not None:
            return
        m = self.mouse
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            now = time.perf_counter()
            last = m.get('down')
            if (last is not None and now - last[0] < DOUBLE_CLICK
                    and abs(ev.pos[0] - last[1][0]) + abs(ev.pos[1] - last[1][1]) <= 8):
                cam.centre()
                m['down'] = None
                m['drag'] = None
                cam.held = False
                self.app.log(f"camera centred ({cam.name})")
                return
            m['down'] = (now, ev.pos)
            m['drag'] = ev.pos
            cam.held = True
        elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 1:
            if m.get('drag') is not None:
                self.app.log(f"camera look {cam.name} yaw {math.degrees(cam.look_yaw):.0f} "
                             f"pitch {math.degrees(cam.look_pitch):.0f} ({cam.drag_mode})")
            m['drag'] = None
            cam.held = False
        elif ev.type == pygame.MOUSEMOTION and m.get('drag') is not None:
            from ui import theme
            k = theme.ui_scale(self.app.w, self.app.h)
            x0, y0 = m['drag']
            cam.drag((ev.pos[0] - x0) / k, (ev.pos[1] - y0) / k)
            m['drag'] = ev.pos
        elif ev.type == pygame.MOUSEWHEEL:
            cam.wheel(ev.y)
            self.app.log(f"camera zoom {cam.name} {cam.zoom[cam.name]:.2f}")

    def end_drag(self):
        self.mouse['drag'] = None
        self.app.renderer.camera.held = False

    def on_pad(self, actions, edges):
        if self.st['paused']:
            self.pause.on_pad(edges)
            return
        for a in actions:
            # in the pit lane the d-pad left/right picks the tyres
            if self.pit.show_menu and a in ('bias_down', 'bias_up'):
                self.pit.cycle(-1 if a == 'bias_down' else 1)
                continue
            self.action(a)

    def on_nav(self, nav):
        if self.st['paused']:
            self.pause.on_nav(nav)

    def on_device(self, res):
        if res == 'lost_active' and not self.st['paused']:
            self.open_pause("Controller disconnected - reconnect it, or resume to drive with the keyboard")

    # --------------------------------------------------------- update
    def update(self, dt):
        app = self.app
        a = app.args
        st = self.st
        car, track, timer, pit, exhaust = self.car, self.track, self.timer, self.pit, self.exhaust
        controls = app.controls
        self.fps = 0.9 * self.fps + 0.1 * (1.0 / max(dt, 1e-4))
        physics_dt = 1.0 / a.hz
        if app.vpad is not None and a.virtual_pad:
            virtual_pad_script(app.vpad, car.time)
        haptics = app.haptics
        # the mouse camera's choice in Settings (live: the pause menu changes it)
        app.renderer.camera.drag_mode = controls.pad.settings.camera['drag']
        if not st['paused']:
            st['acc'] += min(dt, 0.1)
            steps = 0
            while st['acc'] >= physics_dt and steps < MAX_STEPS_PER_FRAME:
                controls.update(physics_dt, car.u)
                controls.apply(car)
                if self.override is not None:
                    car.throttle, car.brake, car.steer = self.override[:3]
                if self.demo:
                    car.throttle, car.brake, car.steer = self.demo[3](car.time, car)
                if self.auto is not None:
                    self.auto.step()
                pit.control(car)                 # driver holds the brake while the crew works
                car.step(physics_dt)
                exhaust.update(physics_dt, car)  # afterfire state (visual/sound only)
                vx0, vy0 = car.vx, car.vy
                hit = track.constrain(car)
                if hit:
                    timer.invalidate()
                if haptics is not None:          # reads the step; never changes the car
                    haptics.sample(car, physics_dt,
                                   math.hypot(car.vx - vx0, car.vy - vy0) if hit else 0.0, hit)
                timer.update(car, physics_dt)
                pit.update(physics_dt)
                st['prev'], st['curr'] = st['curr'], snapshot(car)
                st['acc'] -= physics_dt
                steps += 1
            if steps == MAX_STEPS_PER_FRAME:
                st['acc'] = 0.0          # hardware can't keep up: slow motion, never unstable
            if self.override is not None:
                t, b, s, left = self.override
                left -= dt
                self.override = (t, b, s, left) if left > 0 else None
            app.renderer.effects.update(min(dt, 0.1))
            # the day-night cycle and the clouds run with the race (the same
            # clamped delta time as the physics: a stall never jumps the sun)
            app.daytime.advance(min(dt, 0.1))
            app.renderer.advance_sky(dt)
            self.relight(force=False)
            hud = app.hud
            hud.help_timer -= dt
            if hud.help_timer <= 0.0:
                hud.show_help = False
                hud.help_timer = 1e9
        if haptics is not None:
            # plays (App.update) only while the pad drives and the race runs
            haptics.driving = not st['paused'] and controls.device == CONTROLLER
        alpha = st['acc'] / physics_dt if not st['paused'] else 1.0
        self.pose = interpolate(st['prev'], st['curr'], alpha)
        pose = self.pose[0]
        self.minimap.view.update(0.0 if st['paused'] else dt, pose[0], pose[1], pose[3], car.speed, timer.s)
        deskbuddy.update(car, self.minimap.view, timer, st['paused'])
        if self.pause is not None:
            self.pause.update(dt)

    # ----------------------------------------------------------- draw
    def draw(self, dt):
        app = self.app
        a = app.args
        r = app.renderer
        st = self.st
        car, timer, pit = self.car, self.timer, self.pit
        controls = app.controls
        hud = app.hud
        w, h = app.w, app.h
        pose, wheels, ground = self.pose
        r.pit_light_state = pit.light
        r.pit_stop = pit
        r.moving = not st['paused']
        r.draw_world(pose, wheels, ground, dt)
        if app.audio is not None:
            app.audio.update(car, self.exhaust, r.camera.cockpit, paused=st['paused'])
        self.hud_timer -= dt
        self.tele_timer -= dt
        gb = car.gearbox
        if self.hud_timer <= 0.0:
            self.hud_timer = 1.0 / 30.0
            hud.draw_bottom(car, controls)
            hud.draw_top(car, timer, self.track, clock=self.clock_text())
            hud.draw_assists(car)
            lines, cols = [], []
            if controls.pad.message:
                lines.append(controls.pad.message[0])
                cols.append(YELLOW_MSG)
            if pit.message:
                lines.append(pit.message)
                cols.append((255, 110, 90) if 'speeding' in pit.message else (240, 240, 240))
            if pit.active:
                hud.draw_pit(car, pit, self.track)
            if hud.show_help and not st['paused']:
                lines += HELP + [MOUSE_HELP, pad_help(controls.pad)]
                cols += [(240, 240, 240)] * (len(HELP) + 2)
            elif gb.rejected_timer > 0 and not lines:
                lines.append("downshift refused: the lower gear would over-rev"
                             if gb.reject_reason == 'overrev' else "gear change refused")
                cols.append((240, 240, 240))
            hud.draw_msg(lines, cols)
            if hud.show_pad:
                hud.draw_pad(controls, car, app.haptics)
        if hud.show_tele and self.tele_timer <= 0.0:
            self.tele_timer = 0.1
            hud.draw_telemetry(car, a.hz, self.fps, r.effects)

        r.begin_2d()
        if not a.nohud and not st['paused']:
            # HUD panels were laid out for 1280x720: scale them with the
            # window, never stretched (one factor for x and y)
            ui = max(0.6, min(1.5, min(w / 1280.0, h / 720.0)))
            m = int(10 * ui)
            if hud.show_tele:
                hud.tele.draw(w - hud.tele.w * ui - m, 4, ui)
            hud.bottom.draw((w - hud.bottom.w * ui) / 2, h - (hud.bottom.h + 10) * ui, ui)
            hud.top.draw(m, m, ui)
            hud.assist.draw(m, 240 * ui, ui)
            if pit.active:
                hud.pit.draw(w - (hud.pit.w + 10) * ui - (hud.tele.w * ui + m if hud.show_tele else 0),
                             m, ui)
            self.minimap.draw(r, w, h, in_pit=getattr(timer, 'in_pit', False))
            if hud.show_pad:
                cx, cy, R, k = minimap_layout(w, h)
                hud.pad.draw(m, cy - R - (hud.pad.h + 34) * ui, ui)
            if controls.pad.message or hud.show_help or gb.rejected_timer > 0 or pit.message:
                hud.msg.draw((w - hud.msg.w * ui) / 2, int(h * 0.30), ui)
        if st['paused']:
            self.pause.draw(w, h, st['reason'])
        r.end_2d()
        self._capture(dt)

    # ------------------------------------------- bench / screenshots
    def _capture(self, dt):
        app = self.app
        a = app.args
        car = self.car
        w, h = app.w, app.h
        if a.bench and not a.screenshot:
            self.frames += 1
            if self.frames == 30:
                self.bench_t0 = time.perf_counter()
                if os.environ.get('F1_PROFILE'):          # dev: profile the benchmark frames only
                    import cProfile
                    self.prof = cProfile.Profile()
                    self.prof.enable()
            elif self.frames == 30 + a.bench:
                from OpenGL.GL import glFinish
                glFinish()
                el = time.perf_counter() - self.bench_t0
                print(f"bench: {a.bench} frames, {el / a.bench * 1000:.2f} ms/frame "
                      f"({a.bench / el:.0f} fps), visible chunks {app.renderer.stats['chunks']}")
                if getattr(self, 'prof', None):
                    import pstats
                    self.prof.disable()
                    pstats.Stats(self.prof).sort_stats('tottime').print_stats(16)
                app.quit()
        if a.resize_to and not (a.screenshot or a.bench):
            self.frames += 1
        if a.resize_to and self.frames == 10:
            # a real OS window resize, as if the user dragged the border
            rw, rh = (int(v) for v in a.resize_to.lower().split('x'))
            try:
                pygame.Window.from_display_module().size = (rw, rh)
            except AttributeError:          # classic pygame: no Window API
                pass
        if a.screenshot:
            self.frames += 1
            shots = [float(v) for v in a.shots.split(',')] if a.shots else None
            take = False
            name = a.screenshot
            if shots:
                k = getattr(self, 'shot_k', 0)
                if k < len(shots) and car.time >= shots[k]:
                    take = True
                    name = a.screenshot.replace('.png', f'_{k:02d}.png')
                    self.shot_k = k + 1
                    if k + 1 == len(shots):
                        app.quit()
            elif (self.frames == 40 and a.shot_time is None) or (
                    a.shot_time is not None and car.time >= a.shot_time):
                take = True
                app.quit()
            if take:
                from OpenGL.GL import glReadPixels, GL_RGB, GL_UNSIGNED_BYTE
                data = glReadPixels(0, 0, w, h, GL_RGB, GL_UNSIGNED_BYTE)
                img = pygame.image.frombytes(bytes(data), (w, h), 'RGB', True)
                pygame.image.save(img, name)
