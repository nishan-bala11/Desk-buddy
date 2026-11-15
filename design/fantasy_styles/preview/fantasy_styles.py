"""Seven looks for the fantasy pages, drawn with the buddy's fonts and drawing calls (see
preview_fantasy.py), to pick one from. Each style: Matchup, Win chance and Season pages, left + right.
Run: python fantasy_styles.py <buddy_screens.h> <out folder> <glcdfont.h>"""
import math
import os
import re
import sys

from PIL import Image, ImageDraw, ImageFont

import preview_fantasy as pf
from preview_fantasy import (ALIGN_CENTER as C, ALIGN_LEFT as L, ALIGN_RIGHT as R, VALIGN_MIDDLE as MID, F,
                             bar, fit, line, lround, ordinal, pct, pill, ring, text, textAt, textWidth)

OUT, GLCD = sys.argv[2], sys.argv[3]
rgb = lambda r, g, b: ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)

I11, I15, I16, I18 = pf.I11, pf.I15, pf.I16, pf.I18
R12, R13, R14, R15 = pf.R12, pf.R13, pf.R14, pf.R15
B75, B49, RB17 = pf.B75, pf.B49, pf.RB17
B22, I22, I28 = F("g_Bebas_Neue_400_22"), F("g_Inter_700_22"), F("g_Inter_700_28")
N15, RB15 = F("g_Nunito_800_15"), F("g_Roboto_700_15")

# The GFX library's built-in 5x7 font (5 columns per character, bit 0 at the top)
GLYPHS = [int(v, 16) for v in re.findall(r"0x[0-9A-Fa-f]{2}", re.search(r"font\[\] PROGMEM = \{(.*?)\};", open(GLCD).read(), re.S).group(1))]


def classic_w(s, size):
    return len(s) * 6 * size - size if s else 0


def classic(g, x, y, s, size, color, align=C):
    """Text in the built-in 5x7 font, size x size squares per dot; y = top (buddy::text with FONT_CLASSIC)."""
    w = classic_w(s, size)
    x0 = x - w // 2 if align == C else x - w if align == R else x
    for k, ch in enumerate(s):
        for i in range(5):
            col = GLYPHS[ord(ch) * 5 + i]
            for j in range(8):
                if col >> j & 1:
                    g.fillRect(x0 + k * 6 * size + i * size, y + j * size, size, size, color)


def led(g, x, y, s, pitch, r, on, off=None, align=C):
    """Dot-matrix text: each dot of the 5x7 font a round 'LED' (unlit ones in 'off'); y = top."""
    w = len(s) * 6 * pitch - pitch
    x0 = x - w // 2 if align == C else x - w if align == R else x
    for k, ch in enumerate(s):
        for i in range(6 if off is not None and k < len(s) - 1 else 5):
            col = GLYPHS[ord(ch) * 5 + i] if i < 5 else 0
            for j in range(7):
                c = on if col >> j & 1 else off
                if c is not None:
                    g.fillCircle(x0 + (k * 6 + i) * pitch + pitch // 2, y + j * pitch + pitch // 2, r, c)


def glow(g, x, y, s, color, halo, align, f, valign=None):
    for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2), (-1, -1), (1, 1), (-1, 1), (1, -1)):
        if valign is None:
            text(g, x + dx, y + dy, s, 1, halo, align, 0, 1, f)
        else:
            textAt(g, x + dx, y + dy, valign, s, 1, halo, align, 0, 1, f)
    if valign is None:
        text(g, x, y, s, 1, color, align, 0, 1, f)
    else:
        textAt(g, x, y, valign, s, 1, color, align, 0, 1, f)


def shadow(g, x, y, s, color, sh, align, f, valign=None, off=3):
    for dx, dy, c in ((off, off, sh), (0, 0, color)):
        if valign is None:
            text(g, x + dx, y + dy, s, 1, c, align, 0, 1, f)
        else:
            textAt(g, x + dx, y + dy, valign, s, 1, c, align, 0, 1, f)


def fillEllipse(g, x, y, rx, ry, c):
    g.d.ellipse([x - rx, y - ry, x + rx, y + ry], fill=pf.c565(c))


D = pf.SAMPLE
CH = pf.winChance(D)                     # 0.67
CHP = lround(CH * 100)
SHARE = D["my"] / (D["my"] + D["opp"])
LEAD = D["my"] - D["opp"]
EDGE = max(D["myProj"], D["my"]) - max(D["oppProj"], D["opp"])
DONE = D["my"] / D["myProj"]
up = str.upper


# ============================================================ 2. Jumbotron (stadium LED board)
AMB, AMB_OFF = rgb(255, 176, 0), rgb(44, 28, 4)
LRED, LRED_OFF = rgb(255, 44, 30), rgb(48, 10, 8)
LGRN, LGRN_OFF = rgb(40, 255, 90), rgb(8, 46, 16)


def panel(g):
    g.fillScreen(0)
    for y in range(1, 240, 6):
        for x in range(1, 240, 6):
            g.fillRect(x, y, 2, 2, rgb(22, 22, 22))


def ledRing(g, v, on, off):
    n = 60
    for i in range(n):
        a = math.radians(i * 360 / n)
        g.fillCircle(lround(120 + 112 * math.sin(a)), lround(120 - 112 * math.cos(a)), 3, on if i < v * n else off)


def jumboMatchupL(g):
    panel(g)
    ledRing(g, SHARE, AMB, AMB_OFF)
    led(g, 120, 32, "YOU", 3, 1, AMB)
    led(g, 120, 60, up(D["myTeam"])[:13], 2, 1, AMB)
    led(g, 120, 94, f"{D['my']:.1f}", 6, 2, AMB, AMB_OFF)
    led(g, 120, 154, f"PROJ {D['myProj']:.1f}", 2, 1, AMB)
    led(g, 120, 176, f"{D['record']} {up(ordinal(D['rank']))}", 2, 1, AMB)


def jumboMatchupR(g):
    panel(g)
    ledRing(g, 1 - SHARE, LRED, LRED_OFF)
    led(g, 120, 32, "OPP", 3, 1, LRED)
    led(g, 120, 60, up(D["oppTeam"])[:13], 2, 1, LRED)
    led(g, 120, 94, f"{D['opp']:.1f}", 6, 2, LRED, LRED_OFF)
    led(g, 120, 154, f"PROJ {D['oppProj']:.1f}", 2, 1, LRED)
    led(g, 120, 174, f"{'+' if LEAD >= 0 else '-'}{abs(LEAD):.1f}", 3, 1, LGRN if LEAD >= 0 else LRED)


def jumboChanceL(g):
    panel(g)
    led(g, 120, 40, "WIN", 3, 1, AMB)
    led(g, 120, 76, f"{CHP}%", 7, 3, LGRN, LGRN_OFF)
    lit = lround(20 * CH)
    for i in range(20):
        for row in range(3):
            g.fillCircle(44 + i * 8, 140 + row * 8, 3, LGRN if i < lit else LGRN_OFF)
    led(g, 120, 176, f"WEEK {D['week']}", 2, 1, AMB)


def jumboChanceR(g):
    panel(g)
    led(g, 120, 36, "PROJECTED", 2, 1, AMB)
    led(g, 120, 70, f"YOU {max(D['myProj'], D['my']):.1f}", 3, 1, AMB, AMB_OFF)
    led(g, 120, 106, f"OPP {max(D['oppProj'], D['opp']):.1f}", 3, 1, LRED, LRED_OFF)
    led(g, 120, 146, f"EDGE {EDGE:+.1f}", 2, 1, LGRN if EDGE >= 0 else LRED)
    led(g, 120, 168, f"{pct(DONE * 100)}% SCORED", 2, 1, AMB)


def jumboSeasonL(g):
    panel(g)
    w, l = (int(v) for v in D["record"].split("-")[:2])
    ledRing(g, w / (w + l), AMB, AMB_OFF)
    led(g, 120, 34, "SEASON", 3, 1, AMB)
    led(g, 120, 70, D["record"], 7, 3, AMB, AMB_OFF)
    led(g, 120, 134, f"{up(ordinal(D['rank']))} PLACE", 2, 1, AMB)
    led(g, 120, 156, f"STREAK {D['streak']}", 2, 1, LGRN)
    led(g, 120, 178, f"PF {D['pointsFor']}", 2, 1, AMB)


def jumboSeasonR(g):
    panel(g)
    led(g, 120, 32, "STANDINGS", 2, 1, AMB)
    for i, (place, team, record) in enumerate(D["rows"]):
        y = 58 + i * 26
        c = LGRN if place == D["rank"] else AMB
        led(g, 30, y, str(place), 2, 1, c, align=L)
        led(g, 52, y, up(team)[:9], 2, 1, c, align=L)
        led(g, 212, y, record, 2, 1, c, align=R)


# ============================================================ 3. Broadcast (TV score graphic)
NAVY, PANEL, BBLUE, BRED = rgb(8, 20, 48), rgb(18, 38, 82), rgb(0, 92, 230), rgb(210, 20, 45)
LIGHT, GOLD = rgb(222, 230, 242), rgb(255, 200, 40)


def castMatchup(g, me):
    g.fillScreen(NAVY)
    if me:
        g.fillRoundRect(80, 18, 80, 20, 4, BRED)
        text(g, 120, 22, f"LIVE  WK {D['week']}", 1, 0xFFFF, C, 0, 1, I11)
    else:
        text(g, 120, 22, f"VS  {D['oppRecord']}  {up(ordinal(D['oppPlace']))}", 1, LIGHT, C, 0, 1, I11)
    g.fillRect(0, 46, 240, 34, BBLUE if me else BRED)
    name = up(D["myTeam"] if me else D["oppTeam"])
    text(g, 120, 53, fit(name, I18, 196), 1, 0xFFFF, C, 0, 1, I18)
    textAt(g, 120, 122, MID, f"{D['my'] if me else D['opp']:.1f}", 1, 0xFFFF, C, 0, 1, B75)
    g.fillRect(0, 162, 240, 28, LIGHT)
    if me:
        t = f"PROJ {D['myProj']:.1f}   {D['record']}  {up(ordinal(D['rank']))}"
    else:
        t = f"PROJ {D['oppProj']:.1f}"
    text(g, 120, 167, t, 1, NAVY, C, 0, 1, I15)
    if not me:
        pill(g, 120, 198, f"YOU {LEAD:+.1f}", 1, GOLD, NAVY, 10, 3, 4, 0, I15)


def castChanceL(g):
    g.fillScreen(NAVY)
    g.fillRect(0, 36, 240, 26, LIGHT)
    text(g, 120, 41, "WIN PROBABILITY", 1, NAVY, C, 0, 1, I15)
    textAt(g, 120, 112, MID, f"{CHP}%", 1, 0xFFFF, C, 0, 1, B75)
    x0, x1 = 30, 210
    split = x0 + lround((x1 - x0) * CH)
    g.fillRect(x0, 156, split - x0, 22, BBLUE)
    g.fillRect(split, 156, x1 - split, 22, BRED)
    text(g, x0 + 6, 161, "YOU", 1, 0xFFFF, L, 0, 1, I11)
    text(g, x1 - 6, 161, "OPP", 1, 0xFFFF, R, 0, 1, I11)
    text(g, 120, 190, f"WEEK {D['week']}", 1, LIGHT, C, 0, 1, I11)


def castChanceR(g):
    g.fillScreen(NAVY)
    g.fillRect(0, 36, 240, 26, LIGHT)
    text(g, 120, 41, "PROJECTED FINAL", 1, NAVY, C, 0, 1, I15)
    for k, (name, v, col) in enumerate(((D["myTeam"], max(D["myProj"], D["my"]), BBLUE),
                                        (D["oppTeam"], max(D["oppProj"], D["opp"]), BRED))):
        y = 76 + k * 48
        g.fillRect(20, y, 200, 40, col)
        t = f"{v:.1f}"
        text(g, 210, y + 7, t, 1, 0xFFFF, R, 0, 1, I22)
        text(g, 30, y + 12, fit(up(name), I15, 180 - 20 - textWidth(I22, t, 1)), 1, 0xFFFF, L, 0, 1, I15)
    text(g, 120, 178, f"{pct(DONE * 100)}% OF YOUR PROJECTION SCORED", 1, LIGHT, C, 0, 1, I11)


def castSeasonL(g):
    g.fillScreen(NAVY)
    g.fillRect(0, 36, 240, 26, LIGHT)
    text(g, 120, 41, "SEASON", 1, NAVY, C, 0, 1, I15)
    textAt(g, 120, 104, MID, D["record"], 1, 0xFFFF, C, 0, 1, B75)
    g.fillRect(0, 144, 240, 30, BBLUE)
    text(g, 120, 149, f"{up(ordinal(D['rank']))} PLACE", 1, 0xFFFF, C, 0, 1, I18)
    text(g, 120, 184, f"STREAK {D['streak']}   PF {D['pointsFor']}", 1, LIGHT, C, 0, 1, I11)


def castSeasonR(g):
    g.fillScreen(NAVY)
    g.fillRect(0, 30, 240, 26, BBLUE)
    text(g, 120, 35, "STANDINGS", 1, 0xFFFF, C, 0, 1, I15)
    for i, (place, team, record) in enumerate(D["rows"]):
        y = 64 + i * 26
        mine = place == D["rank"]
        g.fillRect(22, y - 4, 196, 25, GOLD if mine else PANEL if i % 2 == 0 else NAVY)
        tc = NAVY if mine else 0xFFFF
        text(g, 32, y, str(place), 1, tc if mine else LIGHT, L, 0, 1, I15)
        text(g, 208, y, record, 1, tc, R, 0, 1, I15)
        text(g, 54, y, fit(up(team), I15 if mine else R15, 208 - 8 - 54 - textWidth(I15, record, 1), 24), 1, tc, L, 0, 1,
             I15 if mine else R15)


# ============================================================ 4. Gridiron (on the field)
TURF1, TURF2, SH = rgb(38, 132, 56), rgb(31, 114, 47), rgb(12, 52, 22)
EZ_YOU, EZ_OPP, BALL = rgb(0, 72, 168), rgb(176, 22, 32), rgb(132, 66, 28)


def field(g, vertical=False):
    for k in range(10):
        c = TURF1 if k % 2 == 0 else TURF2
        if vertical:
            g.fillRect(k * 24, 0, 24, 240, c)
            g.fillRect(k * 24, 0, 2, 240, 0xFFFF)
        else:
            g.fillRect(0, k * 24, 240, 24, c)
            g.fillRect(0, k * 24, 240, 2, 0xFFFF)
    for k in range(20):   # hash marks
        if vertical:
            g.fillRect(k * 12, 86, 2, 6, 0xFFFF)
            g.fillRect(k * 12, 148, 2, 6, 0xFFFF)
        else:
            g.fillRect(86, k * 12, 6, 2, 0xFFFF)
            g.fillRect(148, k * 12, 6, 2, 0xFFFF)


def football(g, x, y):
    fillEllipse(g, x, y, 24, 14, BALL)
    g.fillRect(x - 10, y - 1, 20, 2, 0xFFFF)
    for k in (-6, -2, 2, 6):
        g.fillRect(x + k, y - 4, 2, 8, 0xFFFF)
    g.fillRect(x - 18, y - 6, 2, 12, 0xFFFF)
    g.fillRect(x + 16, y - 6, 2, 12, 0xFFFF)


def gridMatchup(g, me):
    field(g)
    g.fillRect(0, 0, 240, 64, EZ_YOU if me else EZ_OPP)
    shadow(g, 120, 34, up(D["myTeam"] if me else D["oppTeam"]), 0xFFFF, SH, C, B22, off=2)
    shadow(g, 120, 126, f"{D['my'] if me else D['opp']:.1f}", 0xFFFF, SH, C, B75, valign=MID)
    pill(g, 120, 168, f"PROJ {D['myProj'] if me else D['oppProj']:.1f}", 1, SH, 0xFFFF, 10, 3, 11, 0, I15)
    if me:
        shadow(g, 120, 198, f"{D['record']}  |  {up(ordinal(D['rank']))}", 0xFFFF, SH, C, I11, off=1)
    else:
        pill(g, 120, 196, f"{LEAD:+.1f}", 1, 0xFFFF, SH, 10, 2, 9, 0, I15)


def gridChanceL(g):
    field(g, vertical=True)
    g.fillRect(0, 0, 24, 240, EZ_YOU)
    g.fillRect(216, 0, 24, 240, EZ_OPP)
    shadow(g, 120, 70, f"{CHP}%", 0xFFFF, SH, C, B49, valign=MID)
    football(g, 24 + lround(192 * CH), 122)
    shadow(g, 120, 158, "WIN CHANCE", 0xFFFF, SH, C, B22, off=2)
    shadow(g, 120, 188, "THE BALL IS YOUR CHANCE", 0xFFFF, SH, C, I11, off=1)


def gridChanceR(g):
    field(g)
    shadow(g, 120, 32, "PROJECTED", 0xFFFF, SH, C, B22, off=2)
    for k, (name, v, col) in enumerate(((D["myTeam"], max(D["myProj"], D["my"]), EZ_YOU),
                                        (D["oppTeam"], max(D["oppProj"], D["opp"]), EZ_OPP))):
        y = 66 + k * 50
        g.fillRoundRect(26, y, 188, 42, 8, col)
        t = f"{v:.1f}"
        text(g, 204, y + 9, t, 1, 0xFFFF, R, 0, 1, I22)
        text(g, 36, y + 13, fit(up(name), I15, 168 - 20 - textWidth(I22, t, 1)), 1, 0xFFFF, L, 0, 1, I15)
    pill(g, 120, 176, f"EDGE {EDGE:+.1f}", 1, SH, 0xFFFF, 10, 3, 11, 0, I15)


def gridSeasonL(g):
    field(g)
    g.fillRect(0, 0, 240, 64, rgb(196, 146, 20))
    shadow(g, 120, 34, "SEASON", 0xFFFF, SH, C, B22, off=2)
    shadow(g, 120, 112, D["record"], 0xFFFF, SH, C, B75, valign=MID)
    shadow(g, 120, 150, f"{up(ordinal(D['rank']))} PLACE", 0xFFFF, SH, C, I18, off=2)
    shadow(g, 120, 182, f"STREAK {D['streak']}  |  PF {D['pointsFor']}", 0xFFFF, SH, C, I11, off=1)


def gridSeasonR(g):
    g.fillScreen(rgb(26, 56, 38))
    ring(g, 120, 120, 119, 9, 0, 360, rgb(122, 82, 40), False, 0, 1.0)
    chalk, yellow = rgb(232, 238, 228), rgb(255, 228, 90)
    text(g, 120, 32, "STANDINGS", 1, chalk, C, 0, 1, N15)
    line(g, 74, 54, 166, 54, 2, chalk)
    for i, (place, team, record) in enumerate(D["rows"]):
        y = 64 + i * 26
        mine = place == D["rank"]
        c = yellow if mine else chalk
        if mine:
            g.fillTriangle(20, y + 2, 20, y + 14, 28, y + 8, yellow)
        text(g, 34, y, str(place), 1, c, L, 0, 1, N15)
        text(g, 208, y, record, 1, c, R, 0, 1, N15)
        text(g, 56, y, fit(team, N15, 208 - 8 - 56 - textWidth(N15, record, 1), 24), 1, c, L, 0, 1, N15)


# ============================================================ 5. Neon (synthwave glow)
NBG, CYAN, CYAN_G, MAG, MAG_G = rgb(10, 6, 28), rgb(0, 236, 255), rgb(0, 64, 86), rgb(255, 46, 200), rgb(78, 10, 64)
NTRACK, LAV = rgb(32, 22, 64), rgb(150, 124, 220)


def neonRing(g, v, c, halo, r=112):
    ring(g, 120, 120, r, 3, 0, 360, c, True, NTRACK, 0)
    ring(g, 120, 120, r + 4, 11, 0, 360, halo, False, 0, v)
    ring(g, 120, 120, r, 3, 0, 360, c, False, 0, v)


def neonMatchup(g, me):
    g.fillScreen(NBG)
    c, h = (CYAN, CYAN_G) if me else (MAG, MAG_G)
    neonRing(g, SHARE if me else 1 - SHARE, c, h)
    if me:
        glow(g, 120, 34, f"LIVE  WEEK {D['week']}", MAG, MAG_G, C, I11)
    else:
        text(g, 120, 34, f"VS  {D['oppRecord']}  {ordinal(D['oppPlace'])}", 1, LAV, C, 0, 1, I11)
    glow(g, 120, 56, fit(D["myTeam"] if me else D["oppTeam"], I18, 168), 0xFFFF, h, C, I18)
    glow(g, 120, 120, f"{D['my'] if me else D['opp']:.1f}", 0xFFFF, h, C, B75, valign=MID)
    text(g, 120, 160, f"PROJ {D['myProj'] if me else D['oppProj']:.1f}", 1, LAV, C, 0, 1, R15)
    if me:
        glow(g, 120, 184, f"{D['record']}  |  {ordinal(D['rank'])}", CYAN, CYAN_G, C, I15)
    else:
        glow(g, 120, 182, f"YOU {LEAD:+.1f}", CYAN, CYAN_G, C, I18)


def neonChanceL(g):
    g.fillScreen(NBG)
    cx, cy, r = 120, 130, 92
    ring(g, cx, cy, r, 3, 240, 240, CYAN, True, NTRACK, 0)
    ring(g, cx, cy, r + 4, 11, 240, 240, CYAN_G, False, 0, CH)
    ring(g, cx, cy, r, 3, 240, 240, CYAN, False, 0, CH)
    for k in range(9):   # ticks
        a = 240 + k * 30
        rad = math.radians(a)
        line(g, lround(cx + math.sin(rad) * (r - 12)), lround(cy - math.cos(rad) * (r - 12)),
             lround(cx + math.sin(rad) * (r - 20)), lround(cy - math.cos(rad) * (r - 20)), 2, LAV)
    a = math.radians(240 + 240 * CH)
    line(g, cx, cy, lround(cx + math.sin(a) * (r - 16)), lround(cy - math.cos(a) * (r - 16)), 5, MAG_G)
    line(g, cx, cy, lround(cx + math.sin(a) * (r - 16)), lround(cy - math.cos(a) * (r - 16)), 3, MAG)
    g.fillCircle(cx, cy, 7, MAG)
    glow(g, 120, 176, f"{CHP}%", 0xFFFF, CYAN_G, C, B49, valign=MID)
    text(g, 120, 210, "WIN CHANCE", 1, CYAN, C, 0, 1, I11)


def neonChanceR(g):
    g.fillScreen(NBG)
    glow(g, 120, 40, "PROJECTED", MAG, MAG_G, C, I15)
    top = max(D["myProj"], D["oppProj"])
    for k, (name, v, c, h) in enumerate(((D["myTeam"], max(D["myProj"], D["my"]), CYAN, CYAN_G),
                                         (D["oppTeam"], max(D["oppProj"], D["opp"]), MAG, MAG_G))):
        y = 70 + k * 52
        t = f"{v:.1f}"
        glow(g, 200, y, t, 0xFFFF, h, R, I18)
        text(g, 40, y + 2, fit(name, I15, 150 - textWidth(I18, t, 1)), 1, c, L, 0, 1, I15)
        g.fillRoundRect(38, y + 25, 164, 12, 6, h)
        g.fillRoundRect(40, y + 27, lround(160 * v / top), 8, 4, c)
    text(g, 120, 180, f"{pct(DONE * 100)}% OF YOUR PROJECTION", 1, LAV, C, 0, 1, R12)


def neonSeasonL(g):
    g.fillScreen(NBG)
    w, l = (int(v) for v in D["record"].split("-")[:2])
    neonRing(g, w / (w + l), MAG, MAG_G)
    glow(g, 120, 40, "SEASON", MAG, MAG_G, C, I15)
    glow(g, 120, 102, D["record"], 0xFFFF, CYAN_G, C, B75, valign=MID)
    glow(g, 120, 144, f"{ordinal(D['rank'])} place", CYAN, CYAN_G, C, I18)
    text(g, 120, 172, f"Streak {D['streak']}", 1, LAV, C, 0, 1, R14)
    text(g, 120, 192, f"{D['pointsFor']} points for", 1, LAV, C, 0, 1, R14)


def neonSeasonR(g):
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
            g.fillCircle(30, y + 8, 4, CYAN)
            glow(g, 58, y, fit(team, f, room), 0xFFFF, CYAN_G, L, f)
            glow(g, 206, y, record, CYAN, CYAN_G, R, I15)
        else:
            text(g, 40, y, str(place), 1, LAV, L, 0, 1, I15)
            text(g, 58, y, fit(team, f, room), 1, LAV, L, 0, 1, f)
            text(g, 206, y, record, 1, LAV, R, 0, 1, I15)


# ============================================================ 6. Paper (light, editorial)
PAPER, INK, PGRAY, PLINE = rgb(244, 240, 230), rgb(28, 28, 32), rgb(128, 124, 116), rgb(212, 206, 194)
ORANGE, SLATE, PGREEN = rgb(255, 102, 20), rgb(62, 92, 142), rgb(30, 150, 72)


def paperMatchup(g, me):
    g.fillScreen(PAPER)
    ring(g, 120, 120, 117, 4, 0, 360, ORANGE if me else SLATE, True, PLINE, SHARE if me else 1 - SHARE)
    text(g, 120, 38, f"YOU  |  WEEK {D['week']}" if me else f"THEM  |  {D['oppRecord']}, {ordinal(D['oppPlace'])}", 1, PGRAY, C, 0, 1, I11)
    text(g, 120, 58, fit(D["myTeam"] if me else D["oppTeam"], I18, 172), 1, INK, C, 0, 1, I18)
    textAt(g, 120, 120, MID, f"{D['my'] if me else D['opp']:.1f}", 1, INK, C, 0, 1, B75)
    g.drawFastHLine(80, 157, 80, PLINE)
    text(g, 120, 164, f"PROJ {D['myProj'] if me else D['oppProj']:.1f}", 1, PGRAY, C, 0, 1, R14)
    if me:
        text(g, 120, 186, f"{D['record']}  |  {ordinal(D['rank'])}", 1, INK, C, 0, 1, I15)
    else:
        pill(g, 120, 186, f"{LEAD:+.1f}", 1, PGREEN if LEAD >= 0 else rgb(200, 50, 40), PAPER, 10, 3, 11, 0, I15)


def paperChanceL(g):
    g.fillScreen(PAPER)
    g.fillCircle(120, 110, 74, PLINE)
    g.fillArc(120, 110, 74, 1, -90, -90 + 360 * CH, ORANGE)
    g.fillCircle(120, 110, 50, PAPER)
    textAt(g, 120, 110, MID, f"{CHP}%", 1, INK, C, 0, 1, I28)
    text(g, 120, 196, "CHANCE TO WIN", 1, PGRAY, C, 0, 1, I11)


def paperChanceR(g):
    g.fillScreen(PAPER)
    text(g, 120, 44, "PROJECTED", 1, PGRAY, C, 0, 1, I11)
    top = max(D["myProj"], D["oppProj"])
    for k, (name, v, c) in enumerate(((D["myTeam"], max(D["myProj"], D["my"]), ORANGE),
                                      (D["oppTeam"], max(D["oppProj"], D["opp"]), SLATE))):
        y = 70 + k * 50
        t = f"{v:.1f}"
        text(g, 200, y, t, 1, INK, R, 0, 1, I18)
        text(g, 40, y + 2, fit(name, I15, 150 - textWidth(I18, t, 1)), 1, INK, L, 0, 1, I15)
        bar(g, 40, y + 26, 160, 6, 3, 0, 0, 0, c, True, PLINE, v / top)
    text(g, 120, 172, f"{pct(DONE * 100)}% of your projection so far", 1, PGRAY, C, 0, 1, R12)


def paperSeasonL(g):
    g.fillScreen(PAPER)
    w, l = (int(v) for v in D["record"].split("-")[:2])
    ring(g, 120, 120, 117, 4, 0, 360, ORANGE, True, PLINE, w / (w + l))
    text(g, 120, 40, "SEASON", 1, PGRAY, C, 0, 1, I11)
    textAt(g, 120, 100, MID, D["record"], 1, INK, C, 0, 1, B75)
    text(g, 120, 142, f"{ordinal(D['rank'])} place", 1, INK, C, 0, 1, I18)
    text(g, 120, 170, f"Streak {D['streak']}", 1, PGRAY, C, 0, 1, R14)
    text(g, 120, 190, f"{D['pointsFor']} points for", 1, PGRAY, C, 0, 1, R14)


def paperSeasonR(g):
    g.fillScreen(PAPER)
    text(g, 120, 36, "STANDINGS", 1, PGRAY, C, 0, 1, I11)
    for i, (place, team, record) in enumerate(D["rows"]):
        y = 60 + i * 27
        mine = place == D["rank"]
        if i:
            g.drawFastHLine(30, y - 6, 180, PLINE)
        if mine:
            g.fillRect(24, y - 2, 4, 18, ORANGE)
        c = ORANGE if mine else INK
        f = I15 if mine else R15
        text(g, 36, y, str(place), 1, c if mine else PGRAY, L, 0, 1, I15)
        text(g, 206, y, record, 1, c, R, 0, 1, I15)
        text(g, 58, y, fit(team, f, 206 - 8 - 58 - textWidth(I15, record, 1)), 1, c, L, 0, 1, f)


# ============================================================ 7. Arcade (8-bit)
YEL, ACYAN, PINK, AGRN, AGRAY = rgb(255, 230, 0), rgb(0, 230, 255), rgb(255, 60, 170), rgb(60, 255, 90), rgb(54, 54, 74)


def blockRing(g, v, c):
    n = 40
    for i in range(n):
        a = math.radians(i * 360 / n + 4.5)
        x, y = lround(120 + 110 * math.sin(a)), lround(120 - 110 * math.cos(a))
        g.fillRect(x - 4, y - 4, 8, 8, c if i < v * n else AGRAY)


def arcadeMatchup(g, me):
    g.fillScreen(0)
    blockRing(g, SHARE if me else 1 - SHARE, AGRN if me else PINK)
    classic(g, 120, 34, "1UP" if me else "2UP", 2, PINK if me else ACYAN)
    classic(g, 120, 58, up(D["myTeam"] if me else D["oppTeam"])[:13], 2, YEL)
    classic(g, 120, 100, f"{D['my'] if me else D['opp']:.1f}", 5, 0xFFFF)
    classic(g, 120, 150, f"PROJ {D['myProj'] if me else D['oppProj']:.1f}", 2, ACYAN)
    if me:
        classic(g, 120, 174, f"{D['record']} {up(ordinal(D['rank']))}", 2, YEL)
    else:
        classic(g, 120, 172, f"{LEAD:+.1f}", 3, AGRN if LEAD >= 0 else rgb(255, 50, 50))


def arcadeChanceL(g):
    g.fillScreen(0)
    classic(g, 120, 40, "WIN CHANCE", 2, PINK)
    classic(g, 120, 78, f"{CHP}%", 6, 0xFFFF)
    lit = lround(10 * CH)
    for i in range(10):
        g.fillRect(36 + i * 17, 140, 14, 14, AGRN if i < lit else AGRAY)
    classic(g, 120, 174, f"WEEK {D['week']}", 2, ACYAN)


def arcadeChanceR(g):
    g.fillScreen(0)
    classic(g, 120, 40, "PROJECTED", 2, YEL)
    classic(g, 120, 74, f"1UP {max(D['myProj'], D['my']):.1f}", 3, 0xFFFF)
    classic(g, 120, 108, f"2UP {max(D['oppProj'], D['opp']):.1f}", 3, ACYAN)
    classic(g, 120, 148, f"EDGE {EDGE:+.1f}", 2, AGRN if EDGE >= 0 else rgb(255, 50, 50))
    classic(g, 120, 170, f"{pct(DONE * 100)}% DONE", 2, PINK)


def arcadeSeasonL(g):
    g.fillScreen(0)
    w, l = (int(v) for v in D["record"].split("-")[:2])
    blockRing(g, w / (w + l), YEL)
    classic(g, 120, 40, "SEASON", 2, PINK)
    classic(g, 120, 76, D["record"], 6, 0xFFFF)
    classic(g, 120, 134, f"{up(ordinal(D['rank']))} PLACE", 2, YEL)
    classic(g, 120, 156, f"STREAK {D['streak']}", 2, ACYAN)
    classic(g, 120, 178, f"PF {D['pointsFor']}", 2, ACYAN)


def arcadeSeasonR(g):
    g.fillScreen(0)
    classic(g, 120, 30, "HIGH SCORES", 2, PINK)
    colors = (ACYAN, YEL, 0xFFFF, rgb(255, 150, 40), ACYAN)
    for i, (place, team, record) in enumerate(D["rows"]):
        y = 58 + i * 26
        c = AGRN if place == D["rank"] else colors[i]
        classic(g, 26, y, up(ordinal(place)), 2, c, L)
        classic(g, 70, y, up(team)[:8], 2, c, L)
        classic(g, 214, y, record, 2, c, R)


# ============================================================ the sheets
STYLES = [
    ("1 Rings", "black, rings that fill with your share, big condensed numbers (what's built now)",
     [("Matchup", pf.matchupLeft, pf.matchupRight), ("Win chance", pf.chanceLeft, pf.chanceRight),
      ("Season", pf.seasonLeft, pf.seasonRight)], True),
    ("2 Jumbotron", "stadium scoreboard: dot-matrix LED numbers in amber, red and green",
     [("Matchup", jumboMatchupL, jumboMatchupR), ("Win chance", jumboChanceL, jumboChanceR),
      ("Season", jumboSeasonL, jumboSeasonR)], False),
    ("3 Broadcast", "TV score graphic: navy, team-colour bands, white strips",
     [("Matchup", lambda g: castMatchup(g, True), lambda g: castMatchup(g, False)),
      ("Win chance", castChanceL, castChanceR), ("Season", castSeasonL, castSeasonR)], False),
    ("4 Gridiron", "on the field: turf stripes, end zones, a football for your win chance, chalkboard standings",
     [("Matchup", lambda g: gridMatchup(g, True), lambda g: gridMatchup(g, False)),
      ("Win chance", gridChanceL, gridChanceR), ("Season", gridSeasonL, gridSeasonR)], False),
    ("5 Neon", "synthwave: glowing cyan (you) and magenta (them) on deep purple, a needle gauge",
     [("Matchup", lambda g: neonMatchup(g, True), lambda g: neonMatchup(g, False)),
      ("Win chance", neonChanceL, neonChanceR), ("Season", neonSeasonL, neonSeasonR)], False),
    ("6 Paper", "light and minimal: warm white, ink-black numbers, one orange accent, a donut chart",
     [("Matchup", lambda g: paperMatchup(g, True), lambda g: paperMatchup(g, False)),
      ("Win chance", paperChanceL, paperChanceR), ("Season", paperSeasonL, paperSeasonR)], False),
    ("7 Arcade", "8-bit: pixel font, 1UP vs 2UP, block bars, the standings as a high-score table",
     [("Matchup", lambda g: arcadeMatchup(g, True), lambda g: arcadeMatchup(g, False)),
      ("Win chance", arcadeChanceL, arcadeChanceR), ("Season", arcadeSeasonL, arcadeSeasonR)], False),
]


def font(size, bold=False):
    for name in (("segoeuib.ttf" if bold else "segoeui.ttf"), "arial.ttf"):
        try:
            return ImageFont.truetype(os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", name), size)
        except OSError:
            pass
    return ImageFont.load_default()


def shot(fn, wrap):
    """One screen as it looks through the round glass."""
    g = pf.Canvas()
    if wrap:
        fn(g, D)
    else:
        fn(g)
    mask = Image.new("L", (240, 240), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, 239, 239], fill=255)
    out = Image.new("RGB", (240, 240), (44, 44, 50))
    out.paste(g.img, (0, 0), mask)
    return out


def style_sheet(name, about, pages, wrap, scale=1.5):
    S, gap, head, lab = int(240 * scale), 26, 70, 30
    W = 2 * S + 3 * gap
    img = Image.new("RGB", (W, head + len(pages) * (S + lab + gap) + gap), (22, 22, 26))
    dr = ImageDraw.Draw(img)
    dr.text((gap, 14), f"Style {name}", fill=(240, 240, 240), font=font(26, True))
    dr.text((gap, 46), about, fill=(170, 170, 178), font=font(15))
    for i, (page, left, right) in enumerate(pages):
        y = head + i * (S + lab + gap)
        dr.text((gap, y + 4), f"{page}  (left screen, right screen)", fill=(200, 200, 206), font=font(16, True))
        for j, fn in enumerate((left, right)):
            img.paste(shot(fn, wrap).resize((S, S), Image.LANCZOS), (gap + j * (S + gap), y + lab))
    return img


def overview():
    """Every style's Matchup page on one sheet."""
    S, gap, lab = 240, 22, 34
    cell_w = 2 * S + gap
    cols, rows = 2, (len(STYLES) + 1) // 2
    img = Image.new("RGB", (cols * cell_w + (cols + 1) * gap * 2, 64 + rows * (S + lab + gap * 2)), (22, 22, 26))
    dr = ImageDraw.Draw(img)
    dr.text((gap * 2, 16), "Fantasy screen styles: the Matchup page (left screen = you, right = them)",
            fill=(240, 240, 240), font=font(22, True))
    for k, (name, about, pages, wrap) in enumerate(STYLES):
        cx, cy = gap * 2 + (k % cols) * (cell_w + gap * 2), 64 + (k // cols) * (S + lab + gap * 2)
        dr.text((cx, cy + 4), name, fill=(240, 240, 240), font=font(18, True))
        for j, fn in enumerate(pages[0][1:]):
            img.paste(shot(fn, wrap), (cx + j * (S + gap), cy + lab))
    return img


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    overview().save(os.path.join(OUT, "all_styles_matchup.png"))
    for name, about, pages, wrap in STYLES:
        style_sheet(name, about, pages, wrap).save(os.path.join(OUT, f"style_{name.replace(' ', '_').lower()}.png"))
    print("saved", len(STYLES), "styles to", OUT)
