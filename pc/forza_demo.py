"""A made-up 30 s drive sent like Forza's Data Out, to show the buddy's Forza screens without the game:
20 s of a race (the revs climbing through five gears, the shift light going green to flashing red,
position and lap timer on the right screen), then 10 s of free roam (speed, class badge, top speed).
The PC helper must be running (it listens on 127.0.0.1:5300). Run: python forza_demo.py"""
import socket
import struct
import time


def packet(rpm, gear, speed_ms, pos, lap, cur, best, last, rev=7500.0, cls=3, pi=812):
    """A Forza Horizon 4 / 5 "dash" packet (324 bytes) with just the fields the buddy uses."""
    b = bytearray(324)
    struct.pack_into("<iI3f", b, 0, 1, int(time.monotonic() * 1000) & 0xFFFFFFFF, rev, 800.0, rpm)
    struct.pack_into("<3i", b, 212, 1234, cls, pi)
    struct.pack_into("<f", b, 244 + 12, speed_ms)
    struct.pack_into("<4f", b, 244 + 52, best, last, cur, cur)
    struct.pack_into("<HB", b, 244 + 68, lap, pos)
    b[244 + 75] = gear
    return bytes(b)


s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
start = time.monotonic()
while (t := time.monotonic() - start) < 30:
    gear = 1 + int(t / 4) % 5
    racing = t < 20
    s.sendto(packet(rpm=3000 + (t % 4) / 4 * 4300, gear=gear, speed_ms=10 + gear * 9 + (t % 4) * 2,
                    pos=(3 if t < 10 else 2) if racing else 0, lap=(0 if t < 12 else 1) if racing else 0,
                    cur=((61.0 + t) if t < 12 else (t - 12)) if racing else 0,
                    best=73.0 if 12 <= t < 20 else 0, last=73.0 if 12 <= t < 20 else 0), ("127.0.0.1", 5300))
    time.sleep(1 / 60)
print("done: the buddy goes back to its screens in 3 s")
