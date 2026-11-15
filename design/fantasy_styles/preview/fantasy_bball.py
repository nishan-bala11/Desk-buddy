"""The three styles picked (Jumbotron, Neon, Court) for ESPN fantasy basketball, head-to-head points.
Same pages as before: Matchup, Win chance, Season. Uses the helpers in fantasy_styles.py.
Run: python fantasy_bball.py <buddy_screens.h> <out folder> <glcdfont.h>"""
import math
import os

from PIL import Image, ImageDraw

import fantasy_styles as fs
import preview_fantasy as pf
from fantasy_styles import (C, L, R, MID, B22, B49, B75, I11, I15, I18, I22, N15, R12, R14, R15, glow, led, rgb, shadow,
                            fillEllipse, style_sheet)
from preview_fantasy import fit, line, lround, ordinal, pct, pill, ring, text, textAt, textWidth

OUT = fs.OUT

# A mid-season week of a points league (made up)
D = {"week": 9, "myTeam": "Dunk Dynasty", "oppTeam": "Triple Doubles", "my": 742.5, "opp": 689.0,
     "myProj": 1084.0, "oppProj": 1017.0, "record": "6-2", "rank": 3, "streak": "W3", "pointsFor": "8124.5",
     "oppRecord": "7-1", "oppPlace": 1,
     "rows": [(1, "Triple Doubles", "7-1"), (2, "Fast Break Five", "6-2"), (3, "Dunk Dynasty", "6-2"),
              (4, "Buzzer Beaters", "5-3"), (5, "Alley-Oop Army", "4-4")],
     "leads": [0, 35.5, 12.0, -18.5, 22.0, 41.5, 53.5], "title": "Blinding Lights", "artist": "The Weeknd"}
CH = pf.winChance(D)
CHP = lround(CH * 100)
SHARE = D["my"] / (D["my"] + D["opp"])
LEAD = D["my"] - D["opp"]
EDGE = D["myProj"] - D["oppProj"]
DONE = D["my"] / D["myProj"]
up = str.upper


def pts(v):
    """Weekly basketball totals: one decimal under 1000, whole numbers from there (1084)."""
    return f"{v:.0f}" if v >= 999.95 else f"{v:.1f}"


def words(s, n):
    """Whole words within n characters, for the pixel fonts ("TRIPLE DOUBLES", 10 -> "TRIPLE")."""
    s = up(s)
    if len(s) <= n:
        return s
    cut = s[:n + 1].rfind(" ")
    return s[:cut] if cut > 0 else s[:n]


def fitFont(s, fonts, maxW):
    """The first font the whole of s fits in, else the last one with s cut to fit."""
    for f in fonts:
        if textWidth(f, s, 1) <= maxW:
            return s, f
    return fit(s, fonts[-1], maxW), fonts[-1]


# ============================================================ Jumbotron (arena scoreboard)
AMB, AMB_OFF = rgb(255, 176, 0), rgb(30, 19, 3)
LRED, LRED_OFF = rgb(255, 44, 30), rgb(36, 8, 6)
LGRN, LGRN_OFF = rgb(40, 255, 90), rgb(6, 34, 12)


def panel(g):
    g.fillScreen(0)
    for y in range(1, 240, 6):
        for x in range(1, 240, 6):
            g.fillRect(x, y, 2, 2, rgb(16, 16, 16))


def jMatchup(g, me):
    panel(g)
    on, off = (AMB, AMB_OFF) if me else (LRED, LRED_OFF)
    fs.ledRing(g, SHARE if me else 1 - SHARE, on, off)
    led(g, 120, 30, "HOME" if me else "GUEST", 3, 1, on)
    led(g, 120, 58, words(D["myTeam"] if me else D["oppTeam"], 14), 2, 1, on)
    led(g, 120, 92, pts(D["my"] if me else D["opp"]), 6, 2, on, off)
    led(g, 120, 150, f"PROJ {pts(D['myProj'] if me else D['oppProj'])}", 2, 1, on)
    if me:
        led(g, 120, 172, f"{D['record']} {up(ordinal(D['rank']))}", 2, 1, AMB)
    else:   # like a possession arrow: it points at whoever leads (your screen is on the left)
        t = f"\x11 {LEAD:+.1f}" if LEAD >= 0 else f"{LEAD:+.1f} \x10"
        led(g, 120, 170, t, 3, 1, LGRN if LEAD >= 0 else LRED)


def jChanceL(g):
    panel(g)
    led(g, 120, 40, "WIN", 3, 1, AMB)
    led(g, 120, 76, f"{CHP}%", 7, 3, LGRN, LGRN_OFF)
    lit = lround(20 * CH)
    for i in range(20):
        for row in range(3):
            g.fillCircle(44 + i * 8, 140 + row * 8, 3, LGRN if i < lit else LGRN_OFF)
    led(g, 120, 176, f"WEEK {D['week']}", 2, 1, AMB)


def jChanceR(g):
    panel(g)
    led(g, 120, 36, "PROJECTED", 2, 1, AMB)
    led(g, 120, 70, f"HOME {pts(D['myProj'])}", 3, 1, AMB, AMB_OFF)
    led(g, 120, 106, f"GUEST {pts(D['oppProj'])}", 3, 1, LRED, LRED_OFF)
    led(g, 120, 146, f"EDGE {EDGE:+.0f}", 2, 1, LGRN if EDGE >= 0 else LRED)
    led(g, 120, 168, f"{pct(DONE * 100)}% SCORED", 2, 1, AMB)


def jSeasonL(g):
    panel(g)
    w, l = (int(v) for v in D["record"].split("-")[:2])
    fs.ledRing(g, w / (w + l), AMB, AMB_OFF)
    led(g, 120, 34, "SEASON", 3, 1, AMB)
    led(g, 120, 70, D["record"], 7, 3, AMB, AMB_OFF)
    led(g, 120, 134, f"{up(ordinal(D['rank']))} PLACE", 2, 1, AMB)
    led(g, 120, 156, f"STREAK {D['streak']}", 2, 1, LGRN)
    led(g, 120, 178, f"PF {pts(float(D['pointsFor']))}", 2, 1, AMB)


def jSeasonR(g):
    panel(g)
    led(g, 120, 32, "STANDINGS", 2, 1, AMB)
    for i, (place, team, record) in enumerate(D["rows"]):
        y = 58 + i * 26
        c = LGRN if place == D["rank"] else AMB
        led(g, 28, y, str(place), 2, 1, c, align=L)
        led(g, 46, y, words(team, 10), 2, 1, c, align=L)
        led(g, 214, y, record, 2, 1, c, align=R)


# ============================================================ Neon
NBG, CYAN, CYAN_G, MAG, MAG_G = fs.NBG, fs.CYAN, fs.CYAN_G, fs.MAG, fs.MAG_G
NTRACK, LAV = fs.NTRACK, fs.LAV
BALL, BALL_G, SEAM = rgb(255, 128, 30), rgb(90, 40, 8), rgb(20, 10, 4)


def basketball(g, x, y, r, c=BALL, seam=SEAM):
    g.fillCircle(x, y, r, c)
    g.fillRect(x - r, y - 1, 2 * r + 1, 2, seam)                       # across
    g.fillRect(x - 1, y - r, 2, 2 * r + 1, seam)                       # down
    g.fillArc(x - r - 2, y, r + 3, r + 1, -45, 45, seam)               # the two curved seams
    g.fillArc(x + r + 2, y, r + 3, r + 1, 135, 225, seam)


def nMatchup(g, me):
    g.fillScreen(NBG)
    c, h = (CYAN, CYAN_G) if me else (MAG, MAG_G)
    fs.neonRing(g, SHARE if me else 1 - SHARE, c, h)
    if me:
        glow(g, 120, 34, f"LIVE  WEEK {D['week']}", MAG, MAG_G, C, I11)
    else:
        text(g, 120, 34, f"VS  {D['oppRecord']}  {ordinal(D['oppPlace'])}", 1, LAV, C, 0, 1, I11)
    name, f = fitFont(D["myTeam"] if me else D["oppTeam"], [I18, I15], 172)
    glow(g, 120, 56, name, 0xFFFF, h, C, f)
    glow(g, 120, 120, pts(D["my"] if me else D["opp"]), 0xFFFF, h, C, B75, valign=MID)
    text(g, 120, 160, f"PROJ {pts(D['myProj'] if me else D['oppProj'])}", 1, LAV, C, 0, 1, R15)
    if me:
        glow(g, 120, 184, f"{D['record']}  |  {ordinal(D['rank'])}", CYAN, CYAN_G, C, I15)
    else:
        glow(g, 120, 182, f"YOU {LEAD:+.1f}", CYAN, CYAN_G, C, I18)


def nChanceL(g):
    g.fillScreen(NBG)
    cx, cy, r = 120, 130, 92
    ring(g, cx, cy, r, 3, 240, 240, CYAN, True, NTRACK, 0)
    ring(g, cx, cy, r + 4, 11, 240, 240, CYAN_G, False, 0, CH)
    ring(g, cx, cy, r, 3, 240, 240, CYAN, False, 0, CH)
    for k in range(9):   # ticks
        a = math.radians(240 + k * 30)
        line(g, lround(cx + math.sin(a) * (r - 12)), lround(cy - math.cos(a) * (r - 12)),
             lround(cx + math.sin(a) * (r - 20)), lround(cy - math.cos(a) * (r - 20)), 2, LAV)
    a = math.radians(240 + 240 * CH)
    tip = (lround(cx + math.sin(a) * (r - 18)), lround(cy - math.cos(a) * (r - 18)))
    line(g, cx, cy, *tip, 5, MAG_G)
    line(g, cx, cy, *tip, 3, MAG)
    g.fillCircle(cx, cy, 13, BALL_G)        # the hub: a glowing basketball
    basketball(g, cx, cy, 10)
    glow(g, 120, 178, f"{CHP}%", 0xFFFF, CYAN_G, C, B49, valign=MID)
    text(g, 120, 210, "WIN CHANCE", 1, CYAN, C, 0, 1, I11)


def nChanceR(g):
    g.fillScreen(NBG)
    glow(g, 120, 40, "PROJECTED", MAG, MAG_G, C, I15)
    top = max(D["myProj"], D["oppProj"])
    for k, (name, v, c, h) in enumerate(((D["myTeam"], D["myProj"], CYAN, CYAN_G),
                                         (D["oppTeam"], D["oppProj"], MAG, MAG_G))):
        y = 70 + k * 52
        t = pts(v)
        glow(g, 200, y, t, 0xFFFF, h, R, I18)
        text(g, 40, y + 2, fit(name, I15, 150 - textWidth(I18, t, 1)), 1, c, L, 0, 1, I15)
        g.fillRoundRect(38, y + 25, 164, 12, 6, h)
        g.fillRoundRect(40, y + 27, lround(160 * v / top), 8, 4, c)
    text(g, 120, 180, f"{pct(DONE * 100)}% OF YOUR PROJECTION", 1, LAV, C, 0, 1, R12)


def nSeasonL(g):
    g.fillScreen(NBG)
    w, l = (int(v) for v in D["record"].split("-")[:2])
    fs.neonRing(g, w / (w + l), MAG, MAG_G)
    glow(g, 120, 40, "SEASON", MAG, MAG_G, C, I15)
    glow(g, 120, 102, D["record"], 0xFFFF, CYAN_G, C, B75, valign=MID)
    glow(g, 120, 144, f"{ordinal(D['rank'])} place", CYAN, CYAN_G, C, I18)
    text(g, 120, 172, f"Streak {D['streak']}", 1, LAV, C, 0, 1, R14)
    text(g, 120, 192, f"{pts(float(D['pointsFor']))} points for", 1, LAV, C, 0, 1, R14)


def nSeasonR(g):
    g.fillScreen(NBG)
    glow(g, 120, 32, "STANDINGS", MAG, MAG_G, C, I15)
    line(g, 60, 56, 180, 56, 3, CYAN_G)
    line(g, 60, 56, 180, 56, 1, CYAN)
    for i, (place, team, record) in enumerate(D["rows"]):
        y = 66 + i * 26
        mine = place == D["rank"]
        f = I15 if mine else R15
        room = 206 - 8 - 58 - textWidth(I15, record, 1)
        if mine:
            g.fillRoundRect(26, y - 4, 188, 25, 8, rgb(24, 16, 52))
            glow(g, 40, y, str(place), CYAN, CYAN_G, L, I15)
            glow(g, 58, y, fit(team, f, room), 0xFFFF, CYAN_G, L, f)
            glow(g, 206, y, record, CYAN, CYAN_G, R, I15)
        else:
            text(g, 40, y, str(place), 1, LAV, L, 0, 1, I15)
            text(g, 58, y, fit(team, f, room), 1, LAV, L, 0, 1, f)
            text(g, 206, y, record, 1, LAV, R, 0, 1, I15)


# ============================================================ Court (hardwood)
WOOD = (rgb(214, 160, 98), rgb(203, 149, 88), rgb(222, 170, 108))
WSEAM, WSH = rgb(172, 120, 68), rgb(74, 42, 16)
CLINE = rgb(252, 246, 236)
CBLUE, CBLUE_D, CRED, CRED_D = rgb(0, 84, 180), rgb(0, 58, 128), rgb(186, 24, 36), rgb(132, 16, 26)
ORANGE = rgb(236, 112, 28)


def floor(g):
    for k in range(20):
        g.fillRect(k * 12, 0, 12, 240, WOOD[k % 3])
        g.fillRect(k * 12, 0, 1, 240, WSEAM)
        for y in range((k * 37) % 64, 240, 64):   # plank ends, staggered
            g.fillRect(k * 12, y, 12, 1, WSEAM)


def cMatchup(g, me):
    floor(g)
    col, dark = (CBLUE, CBLUE_D) if me else (CRED, CRED_D)
    g.fillRect(0, 0, 240, 62, col)                       # the baseline banner
    g.fillRect(0, 62, 240, 3, CLINE)                     # the baseline
    g.fillRect(84, 65, 72, 34, dark)                     # the lane (the paint), outlined
    for x in (84, 153):
        g.fillRect(x, 65, 3, 35, CLINE)
    g.fillRect(84, 97, 72, 3, CLINE)
    name, f = fitFont(up(D["myTeam"] if me else D["oppTeam"]), [B22, I15], 140)
    shadow(g, 120, 20, name, 0xFFFF, WSH, C, f, off=2)
    rec = f"{D['record']}  |  {up(ordinal(D['rank']))}" if me else f"{D['oppRecord']}  |  {up(ordinal(D['oppPlace']))}"
    text(g, 120, 46, rec, 1, 0xFFFF, C, 0, 1, I11)
    text(g, 120, 75, f"PROJ {pts(D['myProj'] if me else D['oppProj'])}", 1, 0xFFFF, C, 0, 1, I11)
    shadow(g, 120, 146, pts(D["my"] if me else D["opp"]), 0xFFFF, WSH, C, B75, valign=MID)
    if me:
        pill(g, 120, 190, f"LIVE  WEEK {D['week']}", 1, rgb(214, 28, 40), 0xFFFF, 10, 4, 10, 0, I11)
    else:
        pill(g, 120, 188, f"{LEAD:+.1f}", 1, 0xFFFF, WSH, 12, 3, 11, 0, I18)


def cChanceL(g):
    floor(g)
    ring(g, 198, 96, 84, 3, 180, 180, CLINE, False, 0, 1.0)      # the three-point line
    g.fillRect(213, 66, 4, 42, 0xFFFF)                           # backboard
    for x0, x1 in ((186, 190), (193, 195), (203, 201), (210, 206)):   # net
        line(g, x0, 98, x1, 116, 1, 0xFFFF)
    g.drawFastHLine(190, 116, 17, 0xFFFF)
    fillEllipse(g, 198, 96, 14, 5, ORANGE)                       # rim
    fillEllipse(g, 198, 96, 11, 3, WOOD[0])
    # the shot: the further along, the better your chance
    x0, y0, x1, y1, h = 40, 196, 192, 90, 46
    for k in range(26):
        t = k / 25
        x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t - 4 * h * t * (1 - t)
        g.fillCircle(lround(x), lround(y), 2, 0xFFFF if t <= CH else WSEAM)
    t = CH
    bx, by = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t - 4 * h * t * (1 - t)
    basketball(g, lround(bx), lround(by), 13, ORANGE, rgb(40, 20, 8))
    shadow(g, 74, 70, f"{CHP}%", 0xFFFF, WSH, C, B49, valign=MID)
    pill(g, 120, 196, "WIN CHANCE", 1, WSH, 0xFFFF, 10, 4, 10, 0, I11)


def cChanceR(g):
    floor(g)
    shadow(g, 120, 30, "PROJECTED", 0xFFFF, WSH, C, B22, off=2)
    for k, (name, v, col) in enumerate(((D["myTeam"], D["myProj"], CBLUE), (D["oppTeam"], D["oppProj"], CRED))):
        y = 64 + k * 52
        g.fillRoundRect(26, y, 188, 44, 8, col)
        t = pts(v)
        text(g, 204, y + 10, t, 1, 0xFFFF, R, 0, 1, I22)
        n, f = fitFont(up(name), [I15, I11], 168 - 20 - textWidth(I22, t, 1))
        text(g, 36, y + (14 if f is I15 else 16), n, 1, 0xFFFF, L, 0, 1, f)
    pill(g, 120, 178, f"EDGE {EDGE:+.0f}", 1, WSH, 0xFFFF, 10, 3, 11, 0, I15)


def cSeasonL(g):
    floor(g)
    g.fillRect(0, 0, 240, 62, rgb(196, 146, 20))
    g.fillRect(0, 62, 240, 3, CLINE)
    shadow(g, 120, 30, "SEASON", 0xFFFF, WSH, C, B22, off=2)
    shadow(g, 120, 112, D["record"], 0xFFFF, WSH, C, B75, valign=MID)
    pill(g, 120, 152, f"{up(ordinal(D['rank']))} PLACE", 1, WSH, 0xFFFF, 12, 3, 11, 0, I18)
    pill(g, 120, 186, f"STREAK {D['streak']}  |  PF {pts(float(D['pointsFor']))}", 1, rgb(214, 28, 40), 0xFFFF, 10, 4, 10, 0, I11)


def cSeasonR(g):
    g.fillScreen(rgb(26, 56, 38))
    ring(g, 120, 120, 119, 9, 0, 360, rgb(122, 82, 40), False, 0, 1.0)
    chalk, faint, yellow = rgb(232, 238, 228), rgb(64, 96, 76), rgb(255, 228, 90)
    line(g, 99, 197, 109, 207, 2, faint)   # an X and an O at the bottom, like a play drawn on the board
    line(g, 99, 207, 109, 197, 2, faint)
    ring(g, 136, 202, 6, 2, 0, 360, faint, False, 0, 1.0)
    text(g, 120, 30, "STANDINGS", 1, chalk, C, 0, 1, N15)
    line(g, 74, 52, 166, 52, 2, chalk)
    for i, (place, team, record) in enumerate(D["rows"]):
        y = 62 + i * 26
        mine = place == D["rank"]
        c = yellow if mine else chalk
        if mine:
            g.fillTriangle(20, y + 2, 20, y + 14, 28, y + 8, yellow)
        text(g, 34, y, str(place), 1, c, L, 0, 1, N15)
        text(g, 208, y, record, 1, c, R, 0, 1, N15)
        text(g, 56, y, fit(team, N15, 208 - 8 - 56 - textWidth(N15, record, 1), 24), 1, c, L, 0, 1, N15)


# ============================================================ lead tracker + music, in each style
BEST, WORST = max(D["leads"]), min(D["leads"])
PROGRESS = 0.42   # the song's progress, for the previews
I13, I16 = fs.F("g_Inter_400_13"), fs.F("g_Inter_700_16")


def leadAt(x, x0, x1):
    lead, n = D["leads"], len(D["leads"])
    pos = (x - x0) / (x1 - x0) * (n - 1)
    i = int(pos)
    return lead[i] + (lead[i + 1] - lead[i]) * (pos - i) if i + 1 < n else lead[n - 1]


def leadChart(g, x0, x1, top, bottom, up_dim, down_dim, zero, up_c, down_c, halo=None, halo2=None):
    """The lead through the week as an area chart (the area between it and zero, then the line);
    returns where the line ends and the scale."""
    lead, n = D["leads"], len(D["leads"])
    mid = (top + bottom) // 2
    span = max(10.0, abs(BEST), abs(WORST))
    k = (bottom - top) / 2.0 / span
    for x in range(x0, x1 + 1):
        y = lround(mid - leadAt(x, x0, x1) * k)
        if y < mid:
            g.drawFastVLine(x, y, mid - y, up_dim)
        elif y > mid:
            g.drawFastVLine(x, mid + 1, y - mid, down_dim)
    g.drawFastHLine(x0, mid, x1 - x0 + 1, zero)
    for i in range(1, n):
        xa, xb = x0 + (x1 - x0) * (i - 1) // (n - 1), x0 + (x1 - x0) * i // (n - 1)
        ya, yb = lround(mid - lead[i - 1] * k), lround(mid - lead[i] * k)
        upward = lead[i - 1] + lead[i] >= 0
        if halo is not None:
            line(g, xa, ya, xb, yb, 6, halo if upward else halo2)
        line(g, xa, ya, xb, yb, 2, up_c if upward else down_c)
    return x1, lround(mid - lead[n - 1] * k), span


def musicL(g):   # the music scene's left screen: the spinning cover
    g.fillScreen(0)
    pf.coverPlaceholder(g)


# ---- Jumbotron
def jLeadL(g):
    panel(g)
    led(g, 120, 34, "LEAD", 3, 1, AMB)
    cols, rows, x0, y0, p = 21, 13, 40, 66, 8   # an LED bar graph: up from the middle while you lead
    span = max(10.0, abs(BEST), abs(WORST))
    for i in range(cols):
        v = leadAt(x0 + i * p, x0, x0 + (cols - 1) * p)
        h = lround(abs(v) / span * 6)
        for j in range(rows):
            d = 6 - j
            if d == 0:
                c = AMB_OFF if h == 0 else (LGRN if v > 0 else LRED)
            elif d > 0:
                c = LGRN if v > 0 and d <= h else rgb(20, 20, 20)
            else:
                c = LRED if v < 0 and -d <= h else rgb(20, 20, 20)
            g.fillCircle(x0 + i * p, y0 + j * p, 2, c)
    led(g, 120, 176, f"WEEK {D['week']}", 2, 1, AMB)


def jLeadR(g):
    panel(g)
    ahead = LEAD >= 0
    c, off = (LGRN, LGRN_OFF) if ahead else (LRED, LRED_OFF)
    led(g, 120, 44, "YOU LEAD BY" if ahead else "YOU TRAIL BY", 2, 1, c)
    led(g, 120, 76, f"{abs(LEAD):.1f}", 6, 2, c, off)
    led(g, 120, 138, f"BEST {BEST:+.1f}", 2, 1, AMB)
    led(g, 120, 160, f"WORST {WORST:+.1f}", 2, 1, AMB)


def jMusicR(g):
    panel(g)
    fs.ledRing(g, PROGRESS, AMB, AMB_OFF)
    led(g, 120, 40, words(D["title"], 14), 2, 1, AMB)
    led(g, 120, 60, words(D["artist"], 14), 2, 1, rgb(150, 104, 0))
    led(g, 120, 92, f"HOME  {pts(D['my'])}", 2, 1, AMB)
    led(g, 120, 114, f"GUEST {pts(D['opp'])}", 2, 1, LRED)
    t = f"\x11 {LEAD:+.1f}" if LEAD >= 0 else f"{LEAD:+.1f} \x10"
    led(g, 120, 146, t, 3, 1, LGRN if LEAD >= 0 else LRED)
    led(g, 120, 180, f"WEEK {D['week']}", 2, 1, AMB)


# ---- Neon
def nLeadL(g):
    g.fillScreen(NBG)
    glow(g, 120, 36, "LEAD TRACKER", MAG, MAG_G, C, I15)
    x, y, span = leadChart(g, 30, 210, 64, 176, rgb(0, 34, 46), rgb(48, 8, 40), NTRACK, CYAN, MAG, CYAN_G, MAG_G)
    g.fillCircle(x, y, 6, CYAN_G)
    g.fillCircle(x, y, 3, 0xFFFF)
    text(g, 34, 64, f"+{lround(span)}", 1, LAV, L, 0, 1, I13)
    text(g, 34, 161, f"-{lround(span)}", 1, LAV, L, 0, 1, I13)
    text(g, 120, 190, f"WEEK {D['week']}", 1, LAV, C, 0, 1, I11)


def nLeadR(g):
    g.fillScreen(NBG)
    ahead = LEAD >= 0
    c, h = (CYAN, CYAN_G) if ahead else (MAG, MAG_G)
    fs.neonRing(g, SHARE, c, h)
    text(g, 120, 56, "YOU LEAD BY" if ahead else "YOU TRAIL BY", 1, LAV, C, 0, 1, fs.RB17)
    glow(g, 120, 116, f"{abs(LEAD):.1f}", 0xFFFF, h, C, B75, valign=MID)
    text(g, 120, 160, f"BEST {BEST:+.1f}   WORST {WORST:+.1f}", 1, LAV, C, 0, 1, I13)
    glow(g, 120, 182, f"{pts(D['my'])} - {pts(D['opp'])}", CYAN, CYAN_G, C, I15)


def nMusicR(g):
    g.fillScreen(NBG)
    fs.neonRing(g, PROGRESS, CYAN, CYAN_G)
    glow(g, 120, 38, fit(D["title"], I16, 150), 0xFFFF, CYAN_G, C, I16)
    text(g, 120, 60, fit(D["artist"], I13, 170), 1, LAV, C, 0, 1, I13)
    glow(g, 120, 84, f"LIVE  WEEK {D['week']}", MAG, MAG_G, C, I11)
    glow(g, 112, 132, pts(D["my"]), CYAN, CYAN_G, R, B49, valign=MID)
    line(g, 117, 132, 123, 132, 2, LAV)
    glow(g, 128, 132, pts(D["opp"]), MAG, MAG_G, L, B49, valign=MID)
    text(g, 112, 162, "YOU", 1, LAV, R, 0, 1, I11)
    text(g, 128, 162, "THEM", 1, LAV, L, 0, 1, I11)
    glow(g, 120, 182, f"YOU {LEAD:+.1f}", CYAN, CYAN_G, C, I15)


# ---- Court
def cLeadL(g):
    floor(g)
    shadow(g, 120, 28, "LEAD TRACKER", 0xFFFF, WSH, C, B22, off=2)
    g.fillRoundRect(24, 56, 192, 124, 12, WSH)
    x, y, span = leadChart(g, 34, 206, 66, 170, rgb(36, 92, 52), rgb(112, 40, 28), rgb(150, 110, 70),
                           rgb(70, 220, 110), rgb(255, 96, 70))
    basketball(g, x, y, 6, ORANGE, rgb(40, 20, 8))
    pill(g, 120, 190, f"WEEK {D['week']}", 1, rgb(214, 28, 40), 0xFFFF, 10, 4, 10, 0, I11)


def cLeadR(g):
    floor(g)
    ahead = LEAD >= 0
    g.fillRect(0, 0, 240, 62, CBLUE if ahead else CRED)
    g.fillRect(0, 62, 240, 3, CLINE)
    shadow(g, 120, 30, "YOU LEAD BY" if ahead else "YOU TRAIL BY", 0xFFFF, WSH, C, B22, off=2)
    shadow(g, 120, 124, f"{abs(LEAD):.1f}", 0xFFFF, WSH, C, B75, valign=MID)
    pill(g, 120, 164, f"BEST {BEST:+.1f}  |  WORST {WORST:+.1f}", 1, WSH, 0xFFFF, 10, 4, 10, 0, I11)
    pill(g, 120, 190, f"{pts(D['my'])} - {pts(D['opp'])}", 1, 0xFFFF, WSH, 12, 3, 11, 0, I15)


def cMusicR(g):
    floor(g)
    ring(g, 120, 120, 119, 6, 0, 360, rgb(30, 215, 96), True, WSH, PROGRESS)   # the song, in the app's colour
    g.fillRect(0, 26, 240, 52, WSH)                                            # the scorer's table
    text(g, 120, 32, fit(D["title"], I16, 168), 1, 0xFFFF, C, 0, 1, I16)
    text(g, 120, 56, fit(D["artist"], I11, 168), 1, rgb(226, 190, 140), C, 0, 1, I11)
    shadow(g, 112, 124, pts(D["my"]), 0xFFFF, WSH, R, B49, valign=MID, off=2)
    line(g, 117, 124, 123, 124, 2, WSH)
    shadow(g, 128, 124, pts(D["opp"]), 0xFFFF, WSH, L, B49, valign=MID, off=2)
    text(g, 112, 154, "YOU", 1, WSH, R, 0, 1, I11)
    text(g, 128, 154, "THEM", 1, WSH, L, 0, 1, I11)
    pill(g, 120, 176, f"{LEAD:+.1f}", 1, CBLUE if LEAD >= 0 else CRED, 0xFFFF, 12, 3, 11, 0, I15)


STYLES = [
    ("A Jumbotron", "arena scoreboard: dot-matrix LED, HOME vs GUEST, an arrow pointing at whoever leads",
     [("Matchup", lambda g: jMatchup(g, True), lambda g: jMatchup(g, False)), ("Win chance", jChanceL, jChanceR),
      ("Lead tracker", jLeadL, jLeadR), ("Season", jSeasonL, jSeasonR), ("Music + scores", musicL, jMusicR)], False),
    ("B Neon", "glowing cyan (you) and magenta (them), a needle gauge with a basketball for its hub",
     [("Matchup", lambda g: nMatchup(g, True), lambda g: nMatchup(g, False)), ("Win chance", nChanceL, nChanceR),
      ("Lead tracker", nLeadL, nLeadR), ("Season", nSeasonL, nSeasonR), ("Music + scores", musicL, nMusicR)], False),
    ("C Court", "hardwood floor, team-colour baseline and paint, your win chance as a shot heading for the hoop",
     [("Matchup", lambda g: cMatchup(g, True), lambda g: cMatchup(g, False)), ("Win chance", cChanceL, cChanceR),
      ("Lead tracker", cLeadL, cLeadR), ("Season", cSeasonL, cSeasonR), ("Music + scores", musicL, cMusicR)], False),
]


def overview():
    S, gap, lab = 240, 22, 34
    img = Image.new("RGB", (3 * (2 * S + gap) + 4 * gap, 84 + len(STYLES[0][2]) * (S + lab + gap)), (22, 22, 26))
    dr = ImageDraw.Draw(img)
    dr.text((gap, 16), "Fantasy basketball: Jumbotron, Neon, Court, taking turns  (left screen = you, right = them)",
            fill=(240, 240, 240), font=fs.font(22, True))
    for k, (name, about, pages, wrap) in enumerate(STYLES):
        cx = gap + k * (2 * S + gap * 2)
        dr.text((cx, 52), name, fill=(240, 240, 240), font=fs.font(20, True))
        for p, (page, left, right) in enumerate(pages):
            y = 84 + p * (S + lab + gap)
            dr.text((cx, y), page, fill=(190, 190, 198), font=fs.font(15, True))
            for j, fn in enumerate((left, right)):
                img.paste(fs.shot(fn, wrap), (cx + j * (S + 8), y + 24))
    return img


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    overview().save(os.path.join(OUT, "basketball_styles.png"))
    for name, about, pages, wrap in STYLES:
        style_sheet(name, about, pages, wrap).save(os.path.join(OUT, f"basketball_{name.replace(' ', '_').lower()}.png"))
    print("saved to", OUT)
