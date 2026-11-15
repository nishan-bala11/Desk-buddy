"""Draws wiring_diagram.svg, a Fritzing-style picture of the Desk Buddy's wiring."""
import os

W, H = 1320, 980
RED, BLACK, YELLOW, GREEN = "#d6312b", "#2b2b2b", "#e8b90e", "#2f9e44"
BLUE, ORANGE, PURPLE, CYAN, PINK, BROWN = "#2a6fdb", "#ef7d1a", "#8a45c9", "#17a7b8", "#e0559b", "#8a5a2b"
out = []


def add(s):
    out.append(s)


def text(x, y, s, size=13, fill="#222", anchor="start", weight="normal", extra=""):
    add(f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}" text-anchor="{anchor}" font-weight="{weight}" {extra}>{s}</text>')


def pad(x, y):
    add(f'<circle cx="{x}" cy="{y}" r="7" fill="#d9b24c" stroke="#8d6e22" stroke-width="1.5"/>'
        f'<circle cx="{x}" cy="{y}" r="3" fill="#3a3a3a"/>')


def display(x, y, title):
    s = 300
    add(f'<rect x="{x}" y="{y}" width="{s}" height="{s}" rx="26" fill="#1f5fa8" stroke="#123f73" stroke-width="3"/>')
    for hx, hy in ((x + 20, y + 20), (x + 20, y + s - 20)):
        add(f'<circle cx="{hx}" cy="{hy}" r="8" fill="#fff" stroke="#d9b24c" stroke-width="4"/>')
    cx, cy = x + 135, y + 150
    add(f'<circle cx="{cx}" cy="{cy}" r="118" fill="#111" stroke="#555" stroke-width="3"/>')
    add(f'<circle cx="{cx}" cy="{cy}" r="104" fill="url(#glass)"/>')
    add(f'<path d="M{cx-72} {cy-52} A90 90 0 0 1 {cx+20} {cy-86}" fill="none" stroke="#fff" stroke-opacity=".35" stroke-width="7" stroke-linecap="round"/>')
    text(cx, cy + 5, "GC9A01", 19, "#dfe9f5", "middle", "bold")
    text(cx, cy + 27, "240 x 240", 13, "#a9bdd3", "middle")
    text(x, y - 12, title, 18, "#222", "start", "bold")
    pins = {}
    for i, name in enumerate(("VCC", "GND", "SCL", "SDA", "DC", "CS", "RST")):
        py = y + 72 + i * 26
        px = x + s - 14
        pad(px, py)
        text(px - 13, py + 4, name, 10, "#fff", "end", "bold")
        pins[name] = (px, py)
    return pins


def touch(x, y, title):
    add(f'<rect x="{x}" y="{y}" width="130" height="92" rx="7" fill="#c9302c" stroke="#8e1f1c" stroke-width="2.5"/>')
    add(f'<circle cx="{x+50}" cy="{y+46}" r="31" fill="#b32622" stroke="#e8c15c" stroke-width="3"/>')
    add(f'<rect x="{x+38}" y="{y+37}" width="24" height="17" rx="2" fill="#222"/>')
    text(x, y - 10, title, 16, "#222", "start", "bold")
    pins = {}
    for i, name in enumerate(("GND", "I/O", "VCC")):
        py = y + 20 + i * 26
        px = x + 116
        pad(px, py)
        text(px - 12, py + 4, name, 9, "#fff", "end", "bold")
        pins[name] = (px, py)
    return pins


def board(x, y):
    w, h, pitch = 300, 780, 33
    add(f'<rect x="{x+6}" y="{y+7}" width="{w}" height="{h}" rx="10" fill="#000" opacity=".16"/>')
    add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="#17202c" stroke="#0a0f15" stroke-width="3"/>')
    # ESP32-S3 module
    add(f'<rect x="{x+70}" y="{y+22}" width="160" height="245" rx="5" fill="#222c3a" stroke="#465468"/>')
    add(f'<path d="M{x+84} {y+60} h20 v-24 h20 v24 h20 v-24 h20 v24 h20 v-24 h12" fill="none" stroke="#d9b24c" stroke-width="4"/>')
    add(f'<rect x="{x+82}" y="{y+84}" width="136" height="168" rx="3" fill="url(#metal)" stroke="#8a8f96"/>')
    text(x + 150, y + 150, "ESP32-S3", 20, "#333", "middle", "bold")
    text(x + 150, y + 174, "N16R8", 15, "#444", "middle", "bold")
    text(x + 150, y + 196, "16 MB flash", 11, "#555", "middle")
    text(x + 150, y + 212, "8 MB PSRAM", 11, "#555", "middle")
    # parts
    add(f'<rect x="{x+112}" y="{y+390}" width="76" height="76" rx="3" fill="#0d0d0d" stroke="#444"/>')
    text(x + 150, y + 432, "CH343", 13, "#ccc", "middle", "bold")
    add(f'<rect x="{x+132}" y="{y+305}" width="36" height="36" rx="3" fill="#f4f4f4" stroke="#aaa"/>'
        f'<circle cx="{x+150}" cy="{y+323}" r="12" fill="#e7d7ff"/>')
    text(x + 150, y + 358, "RGB LED (GPIO 48)", 10, "#c6d0dc", "middle")
    for bx in (x + 86, x + 188):
        add(f'<rect x="{bx}" y="{y+610}" width="26" height="26" rx="3" fill="#bbb" stroke="#777"/>'
            f'<circle cx="{bx+13}" cy="{y+623}" r="7" fill="#333"/>')
    add(f'<rect x="{x+106}" y="{y+h-46}" width="88" height="62" rx="6" fill="url(#metal)" stroke="#777" stroke-width="2"/>')
    text(x + 150, y + h - 54, "USB", 11, "#c6d0dc", "middle")
    left = ["3V3", "3V3", "RST", "4", "5", "6", "7", "15", "16", "17", "18", "8", "3", "46", "9", "10", "11", "12", "13", "14", "5V", "GND"]
    right = ["GND", "TX", "RX", "1", "2", "42", "41", "40", "39", "38", "37", "36", "35", "0", "45", "48", "47", "21", "20", "19", "GND", "GND"]
    pins = {}
    for i, name in enumerate(left):
        py = y + 28 + i * pitch
        pad(x + 20, py)
        text(x + 34, py + 4, name, 11, "#fff", "start", "bold")
        pins.setdefault(name, (x + 20, py))
    for i, name in enumerate(right):
        py = y + 28 + i * pitch
        pad(x + w - 20, py)
        text(x + w - 34, py + 4, name, 11, "#fff", "end", "bold")
    return pins


def wire(a, b, color, bend=.5):
    (x1, y1), (x2, y2) = a, b
    mx = x1 + (x2 - x1) * bend
    d = f"M{x1} {y1} C{mx} {y1} {mx} {y2} {x2} {y2}"
    add(f'<path d="{d}" fill="none" stroke="#000" stroke-opacity=".35" stroke-width="7.5" stroke-linecap="round"/>')
    add(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="5" stroke-linecap="round"/>')
    add(f'<path d="{d}" fill="none" stroke="#fff" stroke-opacity=".25" stroke-width="1.3" stroke-linecap="round"/>')


add(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="Arial, Helvetica, sans-serif">')
add('<defs><radialGradient id="glass" cx=".4" cy=".35"><stop offset="0" stop-color="#27415f"/><stop offset="1" stop-color="#0a1320"/></radialGradient>'
    '<linearGradient id="metal" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#e6e8eb"/><stop offset=".5" stop-color="#b9bec5"/><stop offset="1" stop-color="#d9dce0"/></linearGradient></defs>')
add(f'<rect width="{W}" height="{H}" fill="#fff"/>')
text(40, 42, "Desk Buddy wiring", 26, "#222", "start", "bold")

L = display(40, 95, "Left screen")
R = display(40, 480, "Right screen")
TL = touch(460, 860, "Left touch")
TR = touch(660, 770, "Right touch")
E = board(980, 80)

wires = []   # drawn after the parts so they sit on top
for d, shift, cs, dc, rst in ((L, .36, "10", "9", "14"), (R, .56, "16", "15", "7")):
    for name, pin, color in (("VCC", "3V3", RED), ("GND", "GND", BLACK), ("SCL", "12", YELLOW), ("SDA", "11", GREEN),
                             ("DC", dc, BLUE), ("CS", cs, ORANGE), ("RST", rst, PURPLE)):
        wires.append((d[name], E[pin], color, shift))
for t, pin, color, shift in ((TL, "4", CYAN, .8), (TR, "5", PINK, .6)):
    wires.append((t["VCC"], E["3V3"], RED, shift))
    wires.append((t["GND"], E["GND"], BLACK, shift))
    wires.append((t["I/O"], E[pin], color, shift))
for w in wires:
    wire(*w)

# Legend
x, y = 40, 835
text(x, y - 18, "Connections", 15, "#222", "start", "bold")
for i, (c, s) in enumerate(((RED, "3V3 power"), (BLACK, "GND"), (YELLOW, "SPI clock: GPIO 12"), (GREEN, "SPI data: GPIO 11"),
                            (BLUE, "DC: left 9, right 15"), (ORANGE, "CS: left 10, right 16"), (PURPLE, "RST: left 14, right 7"),
                            (CYAN, "Left touch: GPIO 4"), (PINK, "Right touch: GPIO 5"))):
    lx, ly = x + (i // 5) * 195, y + (i % 5) * 23
    add(f'<line x1="{lx}" y1="{ly}" x2="{lx+26}" y2="{ly}" stroke="{c}" stroke-width="5" stroke-linecap="round"/>')
    text(lx + 34, ly + 4, s, 12)
add("</svg>")
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "wiring_diagram.svg"), "w", encoding="utf-8") as f:
    f.write("\n".join(out))
