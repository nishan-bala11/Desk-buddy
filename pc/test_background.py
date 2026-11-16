"""Checks background_running() on made-up transcripts: python test_background.py"""
import importlib.util, sys, os, json, tempfile
from datetime import datetime, timezone
spec = importlib.util.spec_from_file_location("h", os.path.join(os.path.dirname(os.path.abspath(__file__)), "claude-led-ble.py")); h = importlib.util.module_from_spec(spec); spec.loader.exec_module(h)
now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
old = "2026-01-01T00:00:00.000Z"
def tr(*lines):
    f = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False); f.write("\n".join(lines)); f.close(); return f.name
start = lambda i, ts: json.dumps({"timestamp": ts, "message": {"content": [{"type": "tool_result", "content": f"Command running in background with ID: {i}. Output"}]}})
note = lambda i: json.dumps({"message": {"content": f"<task-notification>\n<task-id>{i}</task-id>\n"}})
stop = lambda i: json.dumps({"message": {"content": [{"type": "tool_use", "name": "TaskStop", "input": {"task_id": i}}]}})
assert h.background_running(tr(start("b1", now)))
assert not h.background_running(tr(start("b1", now), note("b1")))
assert not h.background_running(tr(start("b1", now), stop("b1")))
assert not h.background_running(tr(start("b1", old)))
assert not h.background_running(tr("{}"))
print("self-test ok")
