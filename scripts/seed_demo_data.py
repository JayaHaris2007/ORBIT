"""Safe Demo Data Seeder for recording ORBIT showcase videos.

Usage:
    python scripts/seed_demo_data.py --seed      # Backs up assistant.db, then seeds rich showcase data
    python scripts/seed_demo_data.py --restore   # Restores your original assistant.db after filming
    python scripts/seed_demo_data.py --status    # Shows current backup & demo status

Never touches your real data without saving a backup to ``backups/assistant_pre_demo.db`` first.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from learning import code_rag, progress, schema as learning_schema  # noqa: E402
from memory import LOCAL_TIMEZONE, MemoryStore  # noqa: E402

DEFAULT_DB_PATH = BASE_DIR / "assistant.db"
BACKUP_DIR = BASE_DIR / "backups"
BACKUP_DB_PATH = BACKUP_DIR / "assistant_pre_demo.db"
DEMO_CODE_FOLDER = BASE_DIR / "scratch" / "demo_code_folder"


def _create_sample_code_folder(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "hello_basics.cpp").write_text(
        "#include <iostream>\n"
        "using namespace std;\n\n"
        "int main() {\n"
        "    int level = 1;\n"
        "    cout << \"ORBIT C++ workspace ready, level \" << level << endl;\n"
        "    return 0;\n"
        "}\n",
        encoding="utf-8",
    )
    (folder / "while_loop.cpp").write_text(
        "#include <iostream>\n"
        "using namespace std;\n\n"
        "int main() {\n"
        "    int n = 10, sum = 0, i = 1;\n"
        "    while (i <= n) {\n"
        "        if (i % 2 == 0) sum += i;\n"
        "        i++;\n"
        "    }\n"
        "    cout << \"Even sum: \" << sum << endl;\n"
        "    return 0;\n"
        "}\n",
        encoding="utf-8",
    )
    (folder / "binary_search.cpp").write_text(
        "#include <iostream>\n"
        "#include <vector>\n"
        "using namespace std;\n\n"
        "int binarySearch(const vector<int>& nums, int target) {\n"
        "    int low = 0, high = (int)nums.size() - 1;\n"
        "    while (low <= high) {\n"
        "        int mid = low + (high - low) / 2;\n"
        "        if (nums[mid] == target) return mid;\n"
        "        if (nums[mid] < target) low = mid + 1;\n"
        "        else high = mid - 1;\n"
        "    }\n"
        "    return -1;\n"
        "}\n",
        encoding="utf-8",
    )
    (folder / "useCounter.tsx").write_text(
        "import { useState, useEffect } from 'react';\n\n"
        "export function SessionTimer() {\n"
        "    const [seconds, setSeconds] = useState(0);\n"
        "    useEffect(() => {\n"
        "        const id = setInterval(() => setSeconds((s) => s + 1), 1000);\n"
        "        return () => clearInterval(id);\n"
        "    }, []);\n"
        "    return <span>{seconds}s</span>;\n"
        "}\n",
        encoding="utf-8",
    )
    return folder


def backup_database(db_path: Path, backup_path: Path, *, force: bool = False) -> bool:
    if not db_path.exists():
        return False
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    if backup_path.exists() and not force:
        print(f"[info] Existing backup preserved at {backup_path} (use --force-backup to overwrite).")
        return True
    shutil.copy2(db_path, backup_path)
    print(f"[ok] Backed up original database -> {backup_path}")
    return True


def restore_database(db_path: Path, backup_path: Path) -> None:
    if not backup_path.exists():
        raise FileNotFoundError(f"No backup found at {backup_path}. Nothing was restored.")
    for suffix in ("-wal", "-shm"):
        sidecar = Path(f"{db_path}{suffix}")
        if sidecar.exists():
            sidecar.unlink()
    shutil.copy2(backup_path, db_path)
    print(f"[ok] Restored original database from {backup_path} -> {db_path}")


def seed_demo_database(
    db_path: Path = DEFAULT_DB_PATH,
    code_folder: Path = DEMO_CODE_FOLDER,
) -> dict[str, int]:
    """Populate a clean, visually rich ORBIT showcase database for video recording."""
    store = MemoryStore(db_path)
    try:
        learning_schema.init(db_path)
        store.clear_all_data()
        # Also clear learning tables so re-seeding is idempotent
        with learning_schema.connect() as conn:
            conn.execute("DELETE FROM topic_code_evidence")
            conn.execute("DELETE FROM learning_code_chunks")
            conn.execute("DELETE FROM learning_code_files")
            conn.execute("DELETE FROM learning_folders")
            conn.execute("DELETE FROM learning_activities")
            conn.execute("DELETE FROM task_topic_links")
            conn.execute("DELETE FROM topic_prerequisites")
            conn.execute("DELETE FROM topics")
            conn.execute("DELETE FROM roadmaps")

        now_local = datetime.now(LOCAL_TIMEZONE)
        today = now_local.date()

        # 1. Clean starter chat ready for live camera demo
        chat = store.create_chat("ORBIT Demo Session")

        # 2. Tasks (mix of open priorities + completed for crisp Analytics)
        store.create_task(
            "Record ORBIT architecture & voice walkthrough video",
            priority="high",
            due_at=(now_local + timedelta(hours=3)).isoformat(),
            description="Capture 1080p live demo + animated slides",
        )
        store.create_task(
            "Benchmark sentence-streamed Phonon TTS latency",
            priority="high",
            due_at=(now_local + timedelta(days=1)).isoformat(),
            description="Compare first-audio latency across qwen3.5:4b and llama3.2:3b",
        )
        store.create_task(
            "Practice Two Pointers & Sliding Window problems",
            priority="medium",
            due_at=(now_local + timedelta(days=2)).isoformat(),
            description="Solve 3 medium C++ problems in local practice folder",
        )
        t_done_1 = store.create_task("Optimize SQLite WAL thread-local connections", priority="high")
        t_done_2 = store.create_task("Reduce Lucide icon bundle size by 98%", priority="medium")
        store.update_task(t_done_1["id"], completed=True)
        store.update_task(t_done_2["id"], completed=True)

        # 3. Daily Habits with rich 18-day streak & heatmap history
        habits_spec = [
            ("Deep Work Coding (90m)", "Code", 16),
            ("DSA Practice", "Brain", 12),
            ("System Design Reading", "BookOpen", 9),
            ("Evening Walk", "Activity", 14),
        ]
        for h_name, h_icon, streak_days in habits_spec:
            h = store.create_habit(h_name, icon=h_icon)
            for days_ago in range(1, streak_days + 1):
                d_str = (today - timedelta(days=days_ago)).isoformat()
                store.set_habit_completion(h["id"], d_str, True)
            # Mark first two done today so Habits + Analytics show live progress
            if h_name in ("Deep Work Coding (90m)", "DSA Practice"):
                store.set_habit_completion(h["id"], today.isoformat(), True)

        # 4. Long-term Memories
        memories_seed = [
            "My name is Alex and I am building ORBIT, a 100% local personal AI assistant.",
            "I prefer concise, practical engineering explanations with working code examples.",
            "I am currently mastering C++ with DSA and Full-Stack FastAPI + React systems.",
        ]
        for mem in memories_seed:
            store.add_memory(mem)

        # 5. Upcoming Reminders
        store.create_reminder(
            "Review C++ Functions & References notes",
            (now_local + timedelta(hours=2)).isoformat(),
            chat_id=chat["id"],
        )
        store.create_reminder(
            "Daily evening habit check-in",
            (now_local + timedelta(hours=5)).isoformat(),
            recurrence="every day",
            chat_id=chat["id"],
        )

        # 6. Learning Roadmaps + Linked Local Code Folder (triggers live Code RAG suggestions!)
        cpp_import = progress.import_learning_path(
            name="C++ with DSA",
            category="technical",
            topics=[
                "Basics & Compilation",
                "Variables & Data Types",
                "Control Flow",
                "Functions",
                "Arrays & Sliding Window",
                "Sorting & Binary Search",
                "Pointers & References",
                "Dynamic Programming",
            ],
            auto_generate_if_empty=False,
        )
        cpp_rm = cpp_import["roadmap"]
        cpp_topics = cpp_import["roadmap_detail"]["topics"]
        # Mark first 2 completed so Control Flow shows a live Code RAG suggestion!
        progress.update_topic(cpp_topics[0]["id"], status="completed")
        progress.update_topic(cpp_topics[1]["id"], status="completed")

        fs_import = progress.import_learning_path(
            name="Full-Stack React & FastAPI",
            category="technical",
            topics=[
                "React Components & Hooks",
                "TypeScript Interfaces",
                "REST APIs & Routing",
                "SQLite WAL & FTS5",
                "WebSocket Streaming",
            ],
            auto_generate_if_empty=False,
        )
        fs_topics = fs_import["roadmap_detail"]["topics"]
        progress.update_topic(fs_topics[0]["id"], status="completed")
        progress.update_topic(fs_topics[1]["id"], status="learning")

        # Create & sync real demo code folder to C++ roadmap
        folder = _create_sample_code_folder(code_folder)
        code_rag.link_folder_to_roadmap(cpp_rm["id"], str(folder), sync_now=True)

        return {
            "tasks": len(store.list_tasks(include_completed=True)),
            "habits": len(store.list_habits()),
            "memories": len(store.list_memories()),
            "reminders": len(store.list_reminders()),
            "roadmaps": 2,
        }
    finally:
        store.close()
        learning_schema.close_connections()


def main() -> None:
    parser = argparse.ArgumentParser(description="Safe demo-data seeder for ORBIT showcase videos.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--seed", action="store_true", help="Backup assistant.db and seed showcase demo data.")
    group.add_argument("--restore", action="store_true", help="Restore original assistant.db from backup.")
    group.add_argument("--status", action="store_true", help="Print database and backup status.")
    parser.add_argument("--force-backup", action="store_true", help="Overwrite existing pre-demo backup.")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH, help="Target SQLite DB path.")
    args = parser.parse_args()

    if args.status:
        print(f"DB path     : {args.db_path} (exists={args.db_path.exists()})")
        print(f"Backup path : {BACKUP_DB_PATH} (exists={BACKUP_DB_PATH.exists()})")
        print(f"Code folder : {DEMO_CODE_FOLDER} (exists={DEMO_CODE_FOLDER.exists()})")
        return

    if args.restore:
        restore_database(args.db_path, BACKUP_DB_PATH)
        return

    if args.seed:
        if args.db_path == DEFAULT_DB_PATH:
            backup_database(args.db_path, BACKUP_DB_PATH, force=args.force_backup)
        summary = seed_demo_database(args.db_path, DEMO_CODE_FOLDER)
        print(f"[ok] Seeded ORBIT demo workspace: {summary}")
        print(f"[ok] Sample practice folder linked: {DEMO_CODE_FOLDER}")
        print("[tip] When done recording, restore your real data with: python scripts/seed_demo_data.py --restore")


if __name__ == "__main__":
    main()
