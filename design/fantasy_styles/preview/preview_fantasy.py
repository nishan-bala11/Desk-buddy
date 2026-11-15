"""Preview of fantasy_screens.h: draws each page's two 240x240 screens with the real fonts from
buddy_screens.h and the same primitives as Arduino_GFX / the buddy:: helpers, then saves PNGs.
The page code below mirrors fantasy_screens.h line by line (same coordinates, colours, fonts)."""
import math
import re
import sys

from PIL import Image, ImageDraw

HEADER = sys.argv[1]          # buddy_screens.h
OUT = sys.argv[2]             # output folder
SRC = open(HEADER, encoding="utf-8").read()


def c565(c):
    r, g, b = (c >> 11) & 0x1F, (c >> 5) & 0x3F, c & 0x1F
    return (r * 255 // 31, g * 255 // 63, b * 255 // 31)


def lround(x):
    return int(math.floor(x + 0.5)) if x >= 0 else -int(math.floor(-x + 0.5))


# ---- fonts ----
class Font:
    def __init__(self, name):
        bm = re.search(r"buddyFont_%s_bitmaps\[\] PROGMEM = \{(.*?)\};" % name, SRC, re.S).group(1)
        self.bits = [int(v, 16) for v in re.findall(r"0x[0-9A-Fa-f]+", bm)]
        gl = re.search(r"buddyFont_%s_glyphs\[\] PROGMEM = \{(.*?)\n\};" % name, SRC, re.S).group(1)
        self.glyphs = [tuple(int(v) for v in m) for m in re.findall(r"\{ *(-?\d+), *(-?\d+), *(-?\d+), *(-?\d+), *(-?\d+), *(-?\d+) *\}", gl)]
        fm = re.search(r"GFXfont buddyFont_%s PROGMEM = \{[^,]+,[^,]+, (0x[0-9A-F]+), (0x[0-9A-F]+), (\d+) \}" % name, SRC)
        self.first, self.last = int(fm.group(1), 16), int(fm.group(2), 16)
        info = re.search(r"buddyFont_%s_info = \{ &buddyFont_%s, (\d+), (\d+), (\d+) \}" % (name, name), SRC)
        self.ascent, self.lineHeight, self.height = (int(v) for v in info.groups())


FONTS = {}


def F(name):
    if name not in FONTS:
        FONTS[name] = Font(name)
    return FONTS[name]


# ---- a canvas with Arduino_GFX's calls ----
class Canvas:
    def __init__(self):
        self.img = Image.new("RGB", (240, 240))
        self.d = ImageDraw.Draw(self.img)
        self.px = self.img.load()

    def pixel(self, x, y, c):
        if 0 <= x < 240 and 0 <= y < 240:
            self.px[x, y] = c

    def fillScreen(self, c):
        self.d.rectangle([0, 0, 239, 239], fill=c565(c))

    def fillRect(self, x, y, w, h, c):
        if w > 0 and h > 0:
            self.d.rectangle([x, y, x + w - 1, y + h - 1], fill=c565(c))

    def fillRoundRect(self, x, y, w, h, r, c):
        r = min(r, w // 2, h // 2)
        self.d.rounded_rectangle([x, y, x + w - 1, y + h - 1], radius=r, fill=c565(c))

    def fillCircle(self, x, y, r, c):
        self.d.ellipse([x - r, y - r, x + r, y + r], fill=c565(c))

    def fillTriangle(self, x0, y0, x1, y1, x2, y2, c):
        self.d.polygon([(x0, y0), (x1, y1), (x2, y2)], fill=c565(c))

    def drawLine(self, x0, y0, x1, y1, c):
        self.d.line([(x0, y0), (x1, y1)], fill=c565(c))

    def drawFastVLine(self, x, y, h, c):
        if h > 0:
            self.d.line([(x, y), (x, y + h - 1)], fill=c565(c))

    def drawFastHLine(self, x, y, w, c):
        if w > 0:
            self.d.line([(x, y), (x + w - 1, y)], fill=c565(c))

    def fillArc(self, cx, cy, r1, r2, start, end, c):
        if r1 < r2:
            r1, r2 = r2, r1
        r1, r2 = max(r1, 1), max(r2, 1)
        equal = abs(start - end) < 1e-7
        start, end = math.fmod(start, 360), math.fmod(end, 360)
        if start < 0:
            start += 360
        if end < 0:
            end += 360
        if not equal and abs(start - end) <= 0.0001:
            start, end = 0.0, 360.0
        ir = r2 - 1
        ir2, or2 = ir * ir + ir, r1 * r1 + r1
        col = c565(c)
        for y in range(-r1, r1 + 1):
            for x in range(-r1, r1 + 1):
                d2 = x * x + y * y
                if d2 > or2 or d2 <= ir2:
                    continue
                a = math.degrees(math.atan2(y, x)) % 360
                inside = start <= a <= end if start <= end else (a >= start or a <= end)
                if inside:
                    self.pixel(cx + x, cy + y, col)

    def glyph_text(self, x, y, s, size, color, font):   # print() from the baseline, like Adafruit GFX
        col = c565(color)
        for ch in s:
            o = ord(ch)
            if o < font.first or o > font.last:
                continue
            off, w, h, adv, xo, yo = font.glyphs[o - font.first]
            bit, bits = 0, 0
            for yy in range(h):
                for xx in range(w):
                    if not bit & 7:
                        bits = font.bits[off]
                        off += 1
                    bit += 1
                    if bits & 0x80:
                        if size == 1:
                            self.pixel(x + xo + xx, y + yo + yy, col)
                        else:
                            self.fillRect(x + (xo + xx) * size, y + (yo + yy) * size, size, size, color)
                    bits = (bits << 1) & 0xFF
            x += adv * size


# ---- the buddy:: helpers ----
ALIGN_LEFT, ALIGN_CENTER, ALIGN_RIGHT = 0, 1, 2
VALIGN_TOP, VALIGN_MIDDLE, VALIGN_BOTTOM = 0, 1, 2
BAR_RIGHT = 0


def textWidth(f, s, size):
    return sum(f.glyphs[ord(ch) - f.first][3] for ch in s if f.first <= ord(ch) <= f.last) * size


def oneLine(s, maxChars):
    if maxChars > 0 and len(s) > maxChars:
        return s[:max(0, min(61, maxChars - 2))] + ".."
    return s[:63]


def text(g, x, y, s, size, color, align, maxChars, lines, f):
    buf = oneLine(s, maxChars)   # every page uses one line
    w = textWidth(f, buf, size)
    x0 = x - w // 2 if align == ALIGN_CENTER else x - w if align == ALIGN_RIGHT else x
    g.glyph_text(x0, y + f.ascent * size, buf, size, color, f)


def textAt(g, x, y, valign, s, size, color, align, maxChars, lines, f):
    if not s:
        return
    h = f.height * size
    top = y - (h // 2 if valign == VALIGN_MIDDLE else h if valign == VALIGN_BOTTOM else 0)
    text(g, x, top, s, size, color, align, maxChars, lines, f)


def pill(g, x, y, s, size, color, textColor, padX, padY, r, maxChars, f):
    buf = oneLine(s, maxChars)
    w = (textWidth(f, buf, size) if buf else 0) + 2 * padX
    h = f.height * size + 2 * padY
    x0 = x - w // 2
    if r > 0:
        g.fillRoundRect(x0, y, w, h, r, color)
    else:
        g.fillRect(x0, y, w, h, color)
    if buf:
        text(g, x0 + padX, y + padY, buf, size, textColor, ALIGN_LEFT, 0, 1, f)


def ring(g, cx, cy, r, t, start, sweep, color, track, trackColor, v):
    ri = max(1, r - t + 1)
    s = start - 90.0
    if track:
        g.fillArc(cx, cy, r, ri, s, s + sweep, trackColor)
    e = sweep * v
    if e > 0.5:
        g.fillArc(cx, cy, r, ri, s, s + e, color)


def barPart(g, x, y, w, h, r, a, b, c):
    rx, rw = x + a, b - a
    if rw <= 0 or h <= 0:
        return
    if r > 0:
        g.fillRoundRect(rx, y, rw, h, r, c)
    else:
        g.fillRect(rx, y, rw, h, c)


def bar(g, x, y, w, h, r, direction, segments, gap, color, track, trackColor, v):
    v = min(1.0, max(0.0, v))
    if track:
        barPart(g, x, y, w, h, r, 0, w, trackColor)
    fill = int(math.floor(w * v + 0.5))
    if fill > 0:
        barPart(g, x, y, w, h, r, 0, fill, color)


def line(g, x0, y0, x1, y1, w, c):
    if w <= 1:
        g.drawLine(x0, y0, x1, y1, c)
        return
    dx, dy = x1 - x0, y1 - y0
    ln = math.hypot(dx, dy)
    if ln >= 0.5:
        ox, oy = -dy / ln * w * 0.5, dx / ln * w * 0.5
        ax, ay, bx, by = lround(x0 + ox), lround(y0 + oy), lround(x1 + ox), lround(y1 + oy)
        cx, cy, ex, ey = lround(x1 - ox), lround(y1 - oy), lround(x0 - ox), lround(y0 - oy)
        g.fillTriangle(ax, ay, bx, by, cx, cy, c)
        g.fillTriangle(ax, ay, cx, cy, ex, ey, c)
    if w >= 3:
        g.fillCircle(x0, y0, w // 2, c)
        g.fillCircle(x1, y1, w // 2, c)


def ordinal(r):
    k = r % 100
    return f"{r}" + ("th" if 11 <= k <= 13 else "st" if r % 10 == 1 else "nd" if r % 10 == 2 else "rd" if r % 10 == 3 else "th")


def pct(v):
    return lround(min(100.0, max(0.0, v)))


def value_share(d):
    return d["my"] / (d["my"] + d["opp"]) if d["my"] + d["opp"] > 0 else 0.5


def value_proj(d):
    return min(1.0, max(0.0, d["my"] / d["myProj"])) if d["myProj"] > 0 else 0.0


def ff_lead(d):
    r = round((d["my"] - d["opp"]) * 10) / 10
    return f"{'+' if r >= 0 else '-'}{abs(r):.1f}"


# ---- fantasy_screens.h ----
WIN, LOSE, AMBER, LIVE, WIN_DIM, LOSE_DIM = 0x368B, 0xFA27, 0xFDE5, 0xE0E5, 0x1244, 0x50C2
I11, I15, I16, I18 = F("g_Inter_700_11"), F("g_Inter_700_15"), F("g_Inter_700_16"), F("g_Inter_700_18")
R12, R13, R14, R15 = F("g_Inter_400_12"), F("g_Inter_400_13"), F("g_Inter_400_14"), F("g_Inter_400_15")
B75, B49, RB17 = F("g_Bebas_Neue_400_75"), F("g_Bebas_Neue_400_49"), F("g_Roboto_700_17")


def bye(d):
    return d["oppTeam"] == "BYE"


def leadColor(l):
    return WIN if l > 0.05 else LOSE if l < -0.05 else AMBER


def fit(s, f, maxW, n=40):
    out = s[:n - 1]
    if textWidth(f, out, 1) <= maxW:
        return out
    dots = textWidth(f, "..", 1)
    ln = len(out)
    while ln > 0 and (textWidth(f, out[:ln], 1) + dots > maxW or ln + 3 > n):
        ln -= 1
    return out[:ln].rstrip(" ") + ".."


def winChance(d):
    me, them = max(d["myProj"], d["my"]), max(d["oppProj"], d["opp"])
    spread = 2.4 * math.sqrt((me - d["my"]) + (them - d["opp"]))
    if spread < 0.5:
        return 1.0 if me > them else 0.0 if me < them else 0.5
    return 0.5 * (1 + math.erf((me - them) / (spread * 1.41421356)))


def liveBadge(g, y, d):
    pill(g, 120, y, f"LIVE  WEEK {d['week']}", 1, LIVE, 0xFFFF, 8, 3, 9, 0, I11)


def matchupLeft(g, d):
    g.fillScreen(0)
    ring(g, 120, 120, 119, 8, 0, 360, leadColor(d["my"] - d["opp"]), True, 0x2946, value_share(d))
    liveBadge(g, 28, d)
    text(g, 120, 54, fit(d["myTeam"], I18, 172), 1, 0xEF5E, ALIGN_CENTER, 0, 1, I18)
    textAt(g, 120, 118, VALIGN_MIDDLE, f"{d['my']:.1f}", 1, 0xFFFF, ALIGN_CENTER, 0, 1, B75)
    text(g, 120, 160, f"PROJ {d['myProj']:.1f}", 1, 0x8C72, ALIGN_CENTER, 0, 1, R15)
    if d["record"]:
        text(g, 120, 184, f"{d['record']}  |  {ordinal(d['rank'])}", 1, 0x9CD4, ALIGN_CENTER, 0, 1, I15)


def matchupRight(g, d):
    g.fillScreen(0)
    if bye(d):
        ring(g, 120, 120, 119, 8, 0, 360, 0x2946, False, 0, 1.0)
        textAt(g, 120, 108, VALIGN_MIDDLE, "BYE", 1, 0xFFFF, ALIGN_CENTER, 0, 1, B75)
        text(g, 120, 152, "No game this week", 1, 0x8C72, ALIGN_CENTER, 0, 1, R15)
        return
    l = d["my"] - d["opp"]
    ring(g, 120, 120, 119, 8, 0, 360, 0x9CD4, True, 0x2946, 1.0 - value_share(d))
    t = f"VS  {d['oppRecord']}  {ordinal(d['oppPlace'])}" if d["oppRecord"] and d["oppPlace"] else "VS"
    text(g, 120, 30, t, 1, 0x8C72, ALIGN_CENTER, 0, 1, I15)
    text(g, 120, 54, fit(d["oppTeam"], I18, 172), 1, 0xEF5E, ALIGN_CENTER, 0, 1, I18)
    textAt(g, 120, 118, VALIGN_MIDDLE, f"{d['opp']:.1f}", 1, 0xFFFF, ALIGN_CENTER, 0, 1, B75)
    text(g, 120, 160, f"PROJ {d['oppProj']:.1f}", 1, 0x8C72, ALIGN_CENTER, 0, 1, R15)
    pill(g, 120, 182, ff_lead(d), 1, leadColor(l), 0x0000, 12, 4, 13, 0, I18)


def chanceLeft(g, d):
    g.fillScreen(0)
    c = winChance(d)
    decided = c <= 0 or c >= 1
    p = lround(c * 100)
    if not decided:
        p = 1 if p < 1 else 99 if p > 99 else p
    col = WIN if c >= 0.6 else LOSE if c <= 0.4 else AMBER
    ring(g, 120, 120, 112, 16, 225, 270, col, True, 0x2105, c)
    textAt(g, 120, 110, VALIGN_MIDDLE, f"{p}%", 1, 0xFFFF, ALIGN_CENTER, 0, 1, B75)
    text(g, 120, 152, ("YOU WON" if c >= 1 else "YOU LOST") if decided else "WIN CHANCE", 1, 0x9CD4, ALIGN_CENTER, 0, 1, RB17)
    text(g, 120, 194, f"WEEK {d['week']}", 1, 0x8C72, ALIGN_CENTER, 0, 1, I11)


def chanceRight(g, d):
    g.fillScreen(0)
    me, them = max(d["myProj"], d["my"]), max(d["oppProj"], d["opp"])
    top = max(me, them, 1.0)
    mc = WIN if me > them + 0.05 else LOSE if me < them - 0.05 else AMBER
    text(g, 120, 44, "PROJECTED", 1, AMBER, ALIGN_CENTER, 0, 1, I15)
    text(g, 200, 72, f"{me:.1f}", 1, mc, ALIGN_RIGHT, 0, 1, I18)
    text(g, 40, 74, fit(d["myTeam"], I15, 150 - textWidth(I18, f"{me:.1f}", 1)), 1, 0xEF5E, ALIGN_LEFT, 0, 1, I15)
    bar(g, 40, 98, 160, 10, 5, BAR_RIGHT, 0, 0, mc, True, 0x2105, me / top)
    text(g, 200, 120, f"{them:.1f}", 1, 0x9CD4, ALIGN_RIGHT, 0, 1, I18)
    text(g, 40, 122, fit(d["oppTeam"], I15, 150 - textWidth(I18, f"{them:.1f}", 1)), 1, 0xEF5E, ALIGN_LEFT, 0, 1, I15)
    bar(g, 40, 146, 160, 10, 5, BAR_RIGHT, 0, 0, 0x9CD4, True, 0x2105, them / top)
    done = value_proj(d)
    text(g, 120, 172, f"{pct(done * 100)}% OF YOUR PROJECTION", 1, 0x8C72, ALIGN_CENTER, 0, 1, R12)
    bar(g, 70, 192, 100, 6, 3, BAR_RIGHT, 0, 0, 0xEF5E, True, 0x2105, done)


def leadLeft(g, d):
    g.fillScreen(0)
    text(g, 120, 36, "LEAD TRACKER", 1, AMBER, ALIGN_CENTER, 0, 1, I15)
    lead = d["leads"]
    n = len(lead)
    if n < 2:
        text(g, 120, 112, "Waiting for points", 1, 0x8C72, ALIGN_CENTER, 0, 1, R15)
        return
    best, worst = max(lead), min(lead)
    x0, x1, top, bottom = 30, 210, 64, 176
    mid = (top + bottom) // 2
    span = max(10.0, max(abs(best), abs(worst)))
    k = (bottom - top) / 2.0 / span
    for x in range(x0, x1 + 1):
        pos = (x - x0) / (x1 - x0) * (n - 1)
        i = int(pos)
        v = lead[i] + (lead[i + 1] - lead[i]) * (pos - i) if i + 1 < n else lead[n - 1]
        y = lround(mid - v * k)
        if y < mid:
            g.drawFastVLine(x, y, mid - y, WIN_DIM)
        elif y > mid:
            g.drawFastVLine(x, mid + 1, y - mid, LOSE_DIM)
    g.drawFastHLine(x0, mid, x1 - x0 + 1, 0x5AEB)
    for i in range(1, n):
        xa, xb = x0 + (x1 - x0) * (i - 1) // (n - 1), x0 + (x1 - x0) * i // (n - 1)
        ya, yb = lround(mid - lead[i - 1] * k), lround(mid - lead[i] * k)
        line(g, xa, ya, xb, yb, 2, WIN if lead[i - 1] + lead[i] >= 0 else LOSE)
    g.fillCircle(x1, lround(mid - lead[n - 1] * k), 4, 0xFFFF)
    text(g, x0 + 4, top, f"+{lround(span)}", 1, 0x8C72, ALIGN_LEFT, 0, 1, R13)
    text(g, x0 + 4, bottom - 15, f"-{lround(span)}", 1, 0x8C72, ALIGN_LEFT, 0, 1, R13)
    text(g, 120, 190, f"WEEK {d['week']}", 1, 0x8C72, ALIGN_CENTER, 0, 1, I11)


def leadRight(g, d):
    g.fillScreen(0)
    l = d["my"] - d["opp"]
    c = leadColor(l)
    ring(g, 120, 120, 119, 8, 0, 360, c, True, 0x2946, value_share(d))
    text(g, 120, 56, "YOU LEAD BY" if l > 0.05 else "YOU TRAIL BY" if l < -0.05 else "ALL TIED", 1, 0x9CD4, ALIGN_CENTER, 0, 1, RB17)
    textAt(g, 120, 116, VALIGN_MIDDLE, f"{abs(l):.1f}", 1, c, ALIGN_CENTER, 0, 1, B75)
    text(g, 120, 160, f"BEST {max(d['leads']):+.1f}   WORST {min(d['leads']):+.1f}", 1, 0x8C72, ALIGN_CENTER, 0, 1, R13)
    text(g, 120, 182, f"{d['my']:.1f} - {d['opp']:.1f}", 1, 0xEF5E, ALIGN_CENTER, 0, 1, I15)


def seasonLeft(g, d):
    g.fillScreen(0)
    w, l, t = (list(map(int, d["record"].split("-"))) + [0, 0, 0])[:3]
    ring(g, 120, 120, 119, 8, 0, 360, AMBER, True, 0x2946, (w + t * 0.5) / (w + l + t) if w + l + t else 0.0)
    text(g, 120, 40, "SEASON", 1, AMBER, ALIGN_CENTER, 0, 1, I15)
    textAt(g, 120, 100, VALIGN_MIDDLE, d["record"], 1, 0xFFFF, ALIGN_CENTER, 0, 1, B75)
    text(g, 120, 142, f"{ordinal(d['rank'])} place", 1, 0xEF5E, ALIGN_CENTER, 0, 1, I18)
    if d["streak"]:
        text(g, 120, 170, f"Streak {d['streak']}", 1, 0x9CD4, ALIGN_CENTER, 0, 1, R14)
    if d["pointsFor"]:
        text(g, 120, 190, f"{d['pointsFor']} points for", 1, 0x8C72, ALIGN_CENTER, 0, 1, R14)


def seasonRight(g, d):
    g.fillScreen(0)
    text(g, 120, 36, "STANDINGS", 1, AMBER, ALIGN_CENTER, 0, 1, I15)
    for i, (place, team, record) in enumerate(d["rows"]):
        y = 64 + i * 26
        mine = place == d["rank"]
        if mine:
            g.fillRoundRect(26, y - 4, 188, 25, 8, 0x2946)
        text(g, 36, y, f"{place}", 1, AMBER if mine else 0x8C72, ALIGN_LEFT, 0, 1, I15)
        f = I15 if mine else R15
        text(g, 60, y, fit(team, f, 204 - 8 - 60 - textWidth(I15, record, 1), 24), 1, 0xFFFF if mine else 0xEF5E, ALIGN_LEFT, 0, 1, f)
        text(g, 204, y, record, 1, 0xFFFF if mine else 0x9CD4, ALIGN_RIGHT, 0, 1, I15)


def coverPlaceholder(g):   # buddy::cover with no album art (the media scene's left screen), and its rim
    g1, g2, rim, spindle = (34, 34, 38), (22, 22, 26), c565(0x1082), (170, 170, 180)
    for y in range(-119, 120):
        for x in range(-119, 120):
            d2 = x * x + y * y
            if d2 > 119 * 119:
                continue
            rr = int(math.sqrt(d2)) * 119 // 119
            col = rim if d2 > 115 * 115 else (0, 0, 0) if d2 < 25 else spindle if d2 < 81 else (g1 if rr % 6 < 2 else g2)
            g.pixel(120 + x, 120 + y, col)
    g.fillCircle(120, 120, 13, 0x1ED2)   # roughly where the app logo goes (Spotify green)


def musicLeft(g, d):
    g.fillScreen(0)
    coverPlaceholder(g)


def musicRight(g, d):
    g.fillScreen(0)
    l = d["my"] - d["opp"]
    ring(g, 120, 120, 119, 10, 0, 360, 0x1ED2, True, 0x2946, 0.42)   # the song's progress, in the app's colour
    text(g, 120, 38, fit(d["title"], I16, 150, 64), 1, 0xEF5E, ALIGN_CENTER, 0, 1, I16)
    text(g, 120, 60, fit(d["artist"], R13, 170, 64), 1, 0x8C72, ALIGN_CENTER, 0, 1, R13)
    liveBadge(g, 84, d)
    textAt(g, 112, 132, VALIGN_MIDDLE, f"{d['my']:.1f}", 1, leadColor(l), ALIGN_RIGHT, 0, 1, B49)
    line(g, 117, 132, 123, 132, 2, 0x8C72)
    textAt(g, 128, 132, VALIGN_MIDDLE, "BYE" if bye(d) else f"{d['opp']:.1f}", 1, 0xEF5E, ALIGN_LEFT, 0, 1, B49)
    text(g, 112, 162, "YOU", 1, 0x8C72, ALIGN_RIGHT, 0, 1, I11)
    text(g, 128, 162, "THEM", 1, 0x8C72, ALIGN_LEFT, 0, 1, I11)
    if not bye(d):
        pill(g, 120, 182, ff_lead(d), 1, leadColor(l), 0x0000, 10, 3, 11, 0, I15)


PAGES = [("Matchup", matchupLeft, matchupRight), ("Win chance", chanceLeft, chanceRight),
         ("Lead tracker", leadLeft, leadRight), ("Season", seasonLeft, seasonRight),
         ("Music + scores", musicLeft, musicRight)]

# Made-up sample data (what an "F" and "L" message would carry)
SAMPLE = {"week": 8, "myTeam": "Blitz Brigade", "oppTeam": "Touchdown Titans", "my": 87.4, "opp": 74.9,
          "myProj": 118.2, "oppProj": 109.6, "record": "4-3", "rank": 7, "streak": "W2", "pointsFor": "711.6",
          "oppRecord": "6-1", "oppPlace": 2,
          "rows": [(1, "Gridiron Gurus", "6-1"), (2, "Touchdown Titans", "6-1"), (3, "Endzone Elite", "5-2"),
                   (4, "Hail Mary Heroes", "5-2"), (7, "Blitz Brigade", "4-3")],
          "leads": [0, 0, 6.2, 12.8, 9.1, -4.0, -2.6, 3.4, 14.2, 20.1, 16.5, 12.5],
          "title": "Blinding Lights", "artist": "The Weeknd"}


def screen(fn, d):
    g = Canvas()
    fn(g, d)
    mask = Image.new("L", (240, 240), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, 239, 239], fill=255)
    out = Image.new("RGB", (240, 240), (40, 40, 44))   # outside the round glass
    out.paste(g.img, (0, 0), mask)
    return out


def sheet(pages, d, scale=2):
    W, H, gap, label = 240 * scale, 240 * scale, 24, 34
    img = Image.new("RGB", (2 * W + 3 * gap, len(pages) * (H + label + gap) + gap), (24, 24, 28))
    dr = ImageDraw.Draw(img)
    for i, (name, left, right) in enumerate(pages):
        y = gap + i * (H + label + gap)
        dr.text((gap, y + 8), f"{name}   (left screen | right screen)", fill=(220, 220, 220))
        for j, fn in enumerate((left, right)):
            img.paste(screen(fn, d).resize((W, H), Image.NEAREST), (gap + j * (W + gap), y + label))
    return img


if __name__ == "__main__":
    import os
    os.makedirs(OUT, exist_ok=True)
    sheet(PAGES, SAMPLE).save(os.path.join(OUT, "fantasy_pages.png"))
    trailing = dict(SAMPLE, my=61.3, opp=79.8, leads=[0, -3.5, -8.1, -2.0, 4.4, -6.9, -11.7, -18.5])
    sheet(PAGES[:3], trailing).save(os.path.join(OUT, "fantasy_trailing.png"))
    byeweek = dict(SAMPLE, oppTeam="BYE", opp=0, oppProj=0, oppRecord="", oppPlace=0)
    sheet([PAGES[0], PAGES[4]], byeweek).save(os.path.join(OUT, "fantasy_bye.png"))
    print("saved to", OUT)
