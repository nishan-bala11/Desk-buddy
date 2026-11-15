"""Claude Code status line for the Desk Buddy.

Claude Code runs this with the session's details as JSON on stdin. Only the status line gets the
plan's usage limits, so this saves the session (5-hour) and weekly (7-day) usage to usage.json next
to it, where the buddy's PC helper (claude-led-ble.py) reads it for the Claude screens, and prints
them as the status line.
"""
import json
import os
import sys
import time

USAGE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "usage.json")


def main() -> None:
    try:
        info = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        info = {}
    limits = info.get("rate_limits") or {}
    saved = {"at": time.time(), "session_id": info.get("session_id", "")}
    for key in ("five_hour", "seven_day"):
        w = limits.get(key) or {}
        saved[key] = w.get("used_percentage")
        saved[key + "_resets_at"] = w.get("resets_at")
    try:
        tmp = USAGE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(saved, f)
        os.replace(tmp, USAGE_FILE)   # the helper never reads half a file
    except OSError:
        pass
    parts = [f"{label} {saved[key]:.0f}%" for label, key in (("Session", "five_hour"), ("Week", "seven_day"))
             if saved[key] is not None]
    print("  |  ".join(parts))   # ASCII: Windows pipes the output in the ANSI code page


if __name__ == "__main__":
    main()
