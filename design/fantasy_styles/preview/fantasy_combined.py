"""The buddy's own screens (music, music + Claude, Claude dashboard) with the fantasy score added while
an NBA game is on, in their style: a score banner across the bottom of the album cover, a score block
under the Claude usage bars. Ports of the designed scenes from buddy_screens.h for the pictures.
Run: python fantasy_combined.py <buddy_screens.h> <out folder> <glcdfont.h>"""
import math
import os

from PIL import Image, ImageDraw

import fantasy_bball as fb
import fantasy_styles as fs
import preview_fantasy as pf
from preview_fantasy import (ALIGN_CENTER as C, ALIGN_LEFT as L, ALIGN_RIGHT as R, VALIGN_MIDDLE as MID, F, bar,
                             line, lround, pill, ring, text, textAt, textWidth)

rgb = fs.rgb
I20, I22, I16, I18, I15, I11 = F("g_Inter_700_20"), F("g_Inter_700_22"), F("g_Inter_700_16"), F("g_Inter_700_18"), pf.I15, pf.I11
R15, R12, N15, RB15, RB18, B22, B49 = pf.R15, pf.R12, F("g_Nunito_800_15"), F("g_Roboto_700_15"), F("g_Roboto_700_18"), F("g_Bebas_Neue_400_22"), pf.B49
FSB9 = F("FreeSansBold9pt7b")

# What's on right now (made up, apart from your real score)
D = {"title": "Blinding Lights", "artist": "The Weeknd", "app": "Spotify", "playing": True, "pos": 102, "dur": 200,
     "claude": "W", "session": 0.50, "weekly": 0.76, "session_time": "1:23:45", "tokens": "12.5M",
     "week": 2, "my": 309.0, "opp": 389.0}
SPOTIFY = rgb(30, 215, 96)


def levelColor(v, medium, high, mx):
    p = v * 100 + 0.0001
    return rgb(255, 59, 48) if p >= mx else rgb(255, 140, 26) if p >= high else rgb(255, 214, 10) if p >= medium else rgb(41, 151, 255)


STATUS = {"W": (rgb(220, 220, 200), "Working"), "A": (rgb(255, 90, 30), "Needs you"), "D": (rgb(40, 200, 80), "Done")}


def playPause(g, x, y, S, playing, c):
    S = max(S, 2)
    if playing:
        bw, gap = (S * 2 + 1) // 3, (S + 1) // 2
        g.fillRect(x - gap // 2 - bw, y - S, bw, 2 * S, c)
        g.fillRect(x + (gap - gap // 2), y - S, bw, 2 * S, c)
    else:
        xl = x - S * 3 // 4
        g.fillTriangle(xl, y - S, xl, y + S, x + S, y, c)


def visualizer(g, x, y, w, h, bars, gap, r, ms, c):
    bw = max(1, (w - gap * (bars - 1)) // bars)
    t = (ms % 600000) / 1000.0
    for i in range(bars):
        speed = 2.6 + 0.9 * ((i * 7) % 5) / 4.0
        level = 0.2 + 0.8 * abs(math.sin(t * speed + i * 1.3)) * (0.55 + 0.45 * abs(math.sin(t * 1.7 + i * 2.1)))
        bh = max(2, int(math.floor(h * level + 0.5)))
        g.fillRoundRect(x + i * (bw + gap), y + h - bh, bw, bh, r, c)


def mmss(s):
    return f"{s // 60}:{s % 60:02d}"


# ---- the designed scenes (buddy_screens.h), as they are
def cover(g):   # buddyDraw_media_playing_left: the spinning cover (placeholder record here) and the app logo
    g.fillScreen(0)
    pf.coverPlaceholder(g)


def mediaRight(g):   # buddyDraw_media_playing_right
    g.fillScreen(0)
    ring(g, 120, 120, 119, 10, 0, 360, SPOTIFY, True, 0x2946, D["pos"] / D["dur"])
    text(g, 120, 66, D["title"], 1, 0xEF5E, C, 15, 1, I20)
    text(g, 120, 92, D["artist"], 1, 0x8C72, C, 15, 1, N15)
    text(g, 54, 125, mmss(D["pos"]), 1, 0xEF5E, L, 0, 1, RB18)
    text(g, 190, 125, "-" + mmss(D["dur"] - D["pos"]), 1, 0x8C72, R, 0, 1, RB18)
    playPause(g, 120, 132, 12, D["playing"], 0xEF5E)
    visualizer(g, 70, 149, 100, 40, 9, 2, 4, 23456, SPOTIFY)
    pill(g, 120, 33, D["app"], 1, SPOTIFY, 0x0000, 8, 3, 12, 14, FSB9)
    line(g, 88, 89, 152, 89, 1, 0x5AEB)
    bar(g, 69, 190, 103, 7, 6, 0, 0, 3, levelColor(0.62, 50, 75, 90), True, 0x2105, 0.62)


def audioClaudeRight(g):   # buddyDraw_audio_claude_right
    g.fillScreen(0)
    playPause(g, 120, 97, 6, D["playing"], 0xEF5E)
    line(g, 88, 68, 152, 68, 1, 0x528A)
    text(g, 120, 46, D["title"], 1, 0xEF5E, C, 15, 1, I20)
    text(g, 120, 69, D["artist"], 1, 0x8C72, C, 15, 1, N15)
    text(g, 86, 88, mmss(D["pos"]), 1, 0xEF5E, C, 15, 1, RB15)
    text(g, 157, 88, "-" + mmss(D["dur"] - D["pos"]), 1, 0x8C72, C, 15, 1, RB15)
    bar(g, 40, 108, 162, 4, 6, 0, 0, 3, SPOTIFY, True, 0x2105, D["pos"] / D["dur"])
    line(g, 24, 116, 216, 115, 2, 0x4208)
    pill(g, 120, 22, D["app"], 1, SPOTIFY, 0x0000, 5, 3, 18, 14, FSB9)
    ring(g, 120, 120, 119, 8, 0, 360, levelColor(D["session"], 50, 75, 90), True, 0x2105, D["session"])
    sc, st = STATUS[D["claude"]]
    text(g, 120, 122, "Claude", 1, sc, C, 15, 1, I22)
    text(g, 120, 152, st, 1, sc, C, 15, 1, I16)
    text(g, 120, 179, D["session_time"], 1, 0xEF5E, C, 15, 1, B22)
    text(g, 120, 212, D["tokens"], 1, 0xEF5E, C, 15, 1, R12)


def claudeLeft(g):   # buddyDraw_claude_dashboard_bold_idle_left
    g.fillScreen(0)
    sc = STATUS[D["claude"]][0]
    text(g, 40, 62, "CLAUDE ", 1, sc, L, 0, 1, I16)
    text(g, 40, 92, "Session", 1, sc, L, 0, 1, R15)
    text(g, 200, 92, f"{round(D['session'] * 100)}%", 1, levelColor(D["session"], 50, 75, 90), R, 0, 1, I15)
    bar(g, 40, 112, 160, 10, 5, 0, 0, 3, levelColor(D["session"], 50, 75, 90), True, 0x31A7, D["session"])
    text(g, 40, 134, "This week", 1, sc, L, 0, 1, R15)
    text(g, 200, 134, f"{round(D['weekly'] * 100)}%", 1, levelColor(D["weekly"], 25, 50, 75), R, 0, 1, I15)
    bar(g, 40, 154, 160, 10, 5, 0, 0, 3, levelColor(D["weekly"], 25, 50, 75), True, 0x31A7, D["weekly"])


def claudeRight(g):   # buddyDraw_claude_dashboard_bold_idle_right
    g.fillScreen(0)
    sc, st = STATUS[D["claude"]]
    ring(g, 120, 120, 119, 8, 0, 360, sc, False, 0x2946, 1.0)
    pill(g, 120, 73, st, 1, sc, 0x10A3, 14, 6, 16, 14, I18)
    textAt(g, 120, 137, MID, D["session_time"], 1, 0xFFFF, C, 0, 1, B49)
    text(g, 120, 170, f"{D['tokens']} tokens", 1, 0x9CD4, C, 0, 1, R15)
    for a, b in (((115, 43), (108, 51)), ((108, 51), (115, 59)), ((125, 43), (132, 51)), ((132, 51), (125, 59)), ((121, 42), (119, 60))):
        line(g, *a, *b, 3, 0xEF5E)


# ---- what fantasy adds while a game is on
WIN, LOSE, TIE = 0x368B, 0xFA27, 0xFDE5
NAVY = 0x10A3   # the Claude dashboard's pill text colour


def leadColor(l):
    return WIN if l > 0.05 else LOSE if l < -0.05 else TIE


def leadWords(l):
    return f"UP {l:.1f}" if l > 0.05 else f"DOWN {-l:.1f}" if l < -0.05 else "TIED"


def coverBanner(g):
    """Over the bottom of the album cover: the two scores, and up or down in the lead's colour."""
    l = D["my"] - D["opp"]
    g.fillRoundRect(48, 160, 144, 50, 14, NAVY)
    g.fillRoundRect(48, 160, 144, 4, 2, leadColor(l))   # a strip of the lead's colour along the top
    text(g, 120, 168, f"{fb.pts(D['my'])} - {fb.pts(D['opp'])}", 1, 0xEF5E, C, 0, 1, I18)
    text(g, 120, 192, f"{leadWords(l)}  |  WK {D['week']}", 1, leadColor(l), C, 0, 1, I11)


def claudeScore(g):
    """Under the Claude usage bars: your fantasy score."""
    l = D["my"] - D["opp"]
    line(g, 64, 176, 176, 176, 1, 0x31A7)
    text(g, 40, 184, "Fantasy", 1, STATUS[D["claude"]][0], L, 0, 1, R15)
    text(g, 200, 184, f"{fb.pts(D['my'])}-{fb.pts(D['opp'])}", 1, 0xEF5E, R, 0, 1, I15)
    text(g, 120, 206, leadWords(l), 1, leadColor(l), C, 0, 1, I11)


def coverWithScore(g):
    cover(g)
    coverBanner(g)


def claudeWithScore(g):
    claudeLeft(g)
    claudeScore(g)


# ---- notifications and the volume while a game is on
N = {"app": "Fantasy", "title": "Games are on", "text": "Week 2 - you 309.0, Grooters 389.0", "time": "7:31 PM"}
APP_BLUE = rgb(60, 150, 255)   # buddy::appColor for an app it has no colour for
I400_15, MONO13 = F("g_Inter_400_15"), F("g_Roboto_Mono_500_13")


def card(g):   # buddyDraw_idle_eyes_notfication_right (the app logo is a plain circle here)
    g.fillScreen(0)
    g.fillCircle(120, 50, 16, APP_BLUE)
    g.fillRoundRect(26, 96, 192, 85, 16, APP_BLUE)
    g.fillRoundRect(27, 97, 190, 83, 16, 0x10C4)
    text(g, 120, 190, N["time"], 1, 0x8C72, C, 0, 1, MONO13)
    text(g, 119, 98, N["title"], 1, 0xEF5E, C, 15, 1, I20)
    words, lines, cur = N["text"].split(), [], ""
    for w in words:   # text() wraps at spaces onto 3 lines of 15 characters
        if len(cur) + len(w) + (1 if cur else 0) > 15:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    lines.append(cur)
    for k, ln in enumerate(lines[:3]):
        text(g, 34, 121 + k * 19, ln, 1, 0xEF5E, L, 0, 1, I400_15)
    line(g, 60, 120, 180, 120, 1, APP_BLUE)


def cardScore(g):
    l = D["my"] - D["opp"]
    pill(g, 120, 72, f"{fb.pts(D['my'])} - {fb.pts(D['opp'])}", 1, leadColor(l), 0x0000, 8, 2, 8, 0, I11)


def cardWithScore(g):
    card(g)
    cardScore(g)


def volumeRight(g):   # buddyDraw_media_playing_volume_right
    g.fillScreen(0)
    ring(g, 120, 120, 119, 10, 0, 360, 0xFFFF, True, 0x2946, 0.62)
    g.fillRect(109, 69, 6, 8, 0x9CD4)
    g.fillTriangle(115, 69, 123, 63, 123, 83, 0x9CD4)
    g.fillTriangle(115, 69, 123, 83, 115, 77, 0x9CD4)
    g.fillArc(123, 73, 10, 8, -45, 45, 0x9CD4)
    textAt(g, 120, 124, MID, "62%", 1, 0xFFFF, C, 0, 1, pf.B75)
    text(g, 120, 159, "VOLUME", 1, 0x9CD4, C, 0, 1, F("g_Roboto_700_17"))


def claudeRightWithScore(g):
    claudeRight(g)
    l = D["my"] - D["opp"]
    text(g, 120, 194, f"{fb.pts(D['my'])} - {fb.pts(D['opp'])}", 1, leadColor(l), C, 0, 1, I15)


def fantasyLeft(g):   # today's style (Jumbotron), the Matchup page's left screen
    fb.D.update({"my": D["my"], "opp": D["opp"], "week": D["week"], "myProj": 0, "oppProj": 0, "myTeam": "Bron biggest meatrider",
                 "record": "1-0", "rank": 5})
    fb.jMatchup(g, True)


PAGES = [
    ("Music on: the music screen, with your score across the cover", coverWithScore, mediaRight),
    ("Music + Claude working: same banner, the right screen as now", coverWithScore, audioClaudeRight),
    ("Claude open, no music: the dashboard, with your score under the usage", claudeWithScore, claudeRight),
    ("Music + changing the volume: the banner stays on the cover", coverWithScore, volumeRight),
    ("Music + a notification: the card takes the cover's place, so the score sits on it", cardWithScore, mediaRight),
    ("Nothing else on + a notification: today's fantasy page stays on the left", fantasyLeft, card),
    ("Claude + a notification: the score under the tokens on the Claude screen", card, claudeRightWithScore),
]

if __name__ == "__main__":
    OUT = fs.OUT
    os.makedirs(OUT, exist_ok=True)
    sheet = Image.new("RGB", (2 * 360 + 3 * 26, 70 + len(PAGES) * (360 + 30 + 26) + 26), (22, 22, 26))
    dr = ImageDraw.Draw(sheet)
    dr.text((26, 14), "While a game is on: your score on the buddy's own screens", fill=(240, 240, 240), font=fs.font(26, True))
    dr.text((26, 46), "notifications and volume keep their own screens; with nothing else on, today's fantasy style takes over",
            fill=(170, 170, 178), font=fs.font(15))
    for i, (name, left, right) in enumerate(PAGES):
        y = 70 + i * (360 + 30 + 26)
        dr.text((26, y + 4), name, fill=(200, 200, 206), font=fs.font(16, True))
        for j, fn in enumerate((left, right)):
            sheet.paste(fs.shot(fn, False).resize((360, 360), Image.LANCZOS), (26 + j * (360 + 26), y + 30))
    sheet.save(os.path.join(OUT, "with_your_score.png"))
    print("saved")
