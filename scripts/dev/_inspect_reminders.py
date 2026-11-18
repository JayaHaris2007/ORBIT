"""Inspect reminders stored in assistant.db."""

from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from memory import MemoryStore  # noqa: E402

DB_PATH = ROOT_DIR / "assistant.db"
store = MemoryStore(DB_PATH)

print(f"Inspecting database at: {DB_PATH}")
reminders = store.list_reminders(active_only=False)
print("total reminders:", len(reminders))
for r in reminders:
    print(r.get("id"), r.get("active"), r.get("run_at"), "|", r.get("text"))
active = store.list_reminders(active_only=True)
print("active:", len(active))
