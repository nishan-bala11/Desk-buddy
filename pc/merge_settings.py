"""Adds (or removes) the Claude LED hooks in ~/.claude/settings.json, keeping everything else.
Also sets claude-status.py (next to claude-led.ps1) as the status line, which passes the plan's
session / weekly usage to the buddy, unless you already have a status line of your own.

Usage: python merge_settings.py <settings.json> <path to claude-led.ps1> [--remove]
"""
import json
import os
import sys

settings_path, script_path = sys.argv[1], sys.argv[2].replace("\\", "/")
remove = "--remove" in sys.argv
MARK = "claude-led.ps1"


def cmd(letter: str) -> dict:
    return {"type": "command",
            "command": f'powershell -NoProfile -ExecutionPolicy Bypass -File "{script_path}" {letter}'}


OURS = {
    "UserPromptSubmit": [{"hooks": [cmd("W")]}],
    "PreToolUse": [
        {"matcher": "AskUserQuestion", "hooks": [cmd("A")]},
        {"matcher": "^(?!AskUserQuestion$).*", "hooks": [cmd("W")]},
    ],
    "PermissionRequest": [{"hooks": [cmd("A")]}],
    "PostToolUse": [{"hooks": [cmd("W")]}],
    "Notification": [{"hooks": [cmd("A")]}],
    "Stop": [{"hooks": [cmd("D")]}],
}

settings = {}
if os.path.exists(settings_path):
    with open(settings_path, encoding="utf-8-sig") as f:
        text = f.read().strip()
        settings = json.loads(text) if text else {}

hooks = settings.setdefault("hooks", {})

# Drop any earlier Claude LED entries so re-running the installer doesn't duplicate them
for event in list(hooks):
    hooks[event] = [g for g in hooks[event]
                    if not any(MARK in h.get("command", "") for h in g.get("hooks", []))]
    if not hooks[event]:
        del hooks[event]

if not remove:
    for event, groups in OURS.items():
        hooks.setdefault(event, []).extend(groups)
if not hooks:
    del settings["hooks"]

# Status line: ours only where there is none (yours is left alone), removed only if it's ours
STATUS_MARK = "claude-status.py"
status_script = os.path.join(os.path.dirname(script_path), STATUS_MARK).replace("\\", "/")
current = settings.get("statusLine")
ours = isinstance(current, dict) and STATUS_MARK in current.get("command", "")
if remove:
    if ours:
        del settings["statusLine"]
elif current is None or ours:
    python = sys.executable.replace("\\", "/")
    settings["statusLine"] = {"type": "command", "command": f'"{python}" "{status_script}"'}

os.makedirs(os.path.dirname(settings_path), exist_ok=True)
with open(settings_path, "w", encoding="utf-8") as f:
    json.dump(settings, f, indent=2)
print("Removed Claude LED hooks" if remove else "Added Claude LED hooks", "in", settings_path)
