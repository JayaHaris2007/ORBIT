"""Tests for local folder learning auto-tracker, Suggest & Confirm workflow, and Hybrid Code RAG."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app
from learning import code_rag, progress, schema
from memory import MemoryStore


@pytest.fixture
def isolated_learning_env(tmp_path, monkeypatch):
    db_path = tmp_path / "test_code_rag.db"
    store = MemoryStore(db_path)
    schema.init(db_path)
    monkeypatch.setattr(app, "memory_store", store)

    # Create a C++ with DSA roadmap with core topics (including tricky names that used to false-match substrings)
    imported = progress.import_learning_path(
        name="C++ with DSA",
        topics=[
            "Basics & Compilation",
            "Variables & Data Types",
            "Operators & Type Casting",
            "Input / Output",
            "Control Flow",
            "Functions",
            "Scope & Storage Classes",
            "Arrays",
            "Pointers",
            "Classes & Objects",
            "Exception Handling",
            "Multithreading Basics",
        ],
        auto_generate_if_empty=False,
    )
    roadmap_id = imported["roadmap"]["id"]

    # Create a realistic sample practice folder mirroring the user's workspace
    folder = tmp_path / "cpp_practice"
    folder.mkdir()
    (folder / "first_cpp.cpp").write_text(
        '#include <iostream>\nusing namespace std;\nint main() {\n    cout << "Hello C++";\n    return 0;\n}\n',
        encoding="utf-8",
    )
    (folder / "first_cpp.exe").write_bytes(b"MZ_FAKE_EXE")
    (folder / "variables_data_type.cpp").write_text(
        "#include <iostream>\nusing namespace std;\nint main() {\n    int a = 10;\n    double d = 3.14;\n    cout << sizeof(a) << d;\n    return 0;\n}\n",
        encoding="utf-8",
    )
    (folder / "if_else.cpp").write_text(
        "#include <iostream>\nusing namespace std;\nint main() {\n    char ch;\n    cin >> ch;\n    if (ch >= 'a' && ch <= 'z') {\n        cout << \"lower\";\n    } else {\n        cout << \"upper\";\n    }\n    return 0;\n}\n",
        encoding="utf-8",
    )
    # Empty WIP file (just like while_loop.cpp)
    (folder / "while_loop.cpp").write_text("", encoding="utf-8")
    # Empty file for Functions -> must NOT trigger learning or completion suggestion
    (folder / "functions_practice.cpp").write_text("", encoding="utf-8")
    # Boilerplate-only file for Arrays -> must NOT trigger completion suggestion
    (folder / "arrays.cpp").write_text(
        "#include <iostream>\nusing namespace std;\nint main() {\n    return 0;\n}\n",
        encoding="utf-8",
    )
    # Misnamed file: named pointers.cpp, but contains ZERO pointer code -> must NOT match Pointers!
    (folder / "pointers.cpp").write_text(
        '#include <iostream>\nusing namespace std;\nint main() {\n    cout << "just printing text";\n    cout << "no pointers here";\n    return 0;\n}\n',
        encoding="utf-8",
    )

    return {"roadmap_id": roadmap_id, "folder": folder, "db_path": db_path}


def test_folder_sync_suggest_and_confirm_workflow(isolated_learning_env):
    rm_id = isolated_learning_env["roadmap_id"]
    folder = isolated_learning_env["folder"]

    res = code_rag.link_folder_to_roadmap(rm_id, str(folder), sync_now=True)
    sync = res["sync"]
    assert sync["total_files"] == 7
    assert sync["practiced_files"] == 4  # first_cpp, variables, if_else, pointers (has real cout lines)
    assert sync["wip_files"] == 1  # arrays.cpp (boilerplate only!)
    assert sync["empty_files"] == 2  # while_loop.cpp, functions_practice.cpp

    # Check topic statuses:
    # - NEVER auto-marked 'completed'!
    # - Only topics with ACTUAL verified code move to 'learning'.
    # - Empty (Functions), boilerplate-only (Arrays), and unrelated code (Pointers) stay 'not_started'!
    detail = progress.get_roadmap(rm_id)
    status_by_name = {t["name"]: t["status"] for t in detail["topics"]}
    assert status_by_name["Basics & Compilation"] == "learning"
    assert status_by_name["Variables & Data Types"] == "learning"
    assert status_by_name["Control Flow"] == "learning"
    assert status_by_name["Functions"] == "not_started"
    assert status_by_name["Arrays"] == "not_started"
    assert status_by_name["Pointers"] == "not_started"
    # Word-boundary guard: 'while_loop' must not trigger Classes ('oop'), 'basics' must not trigger Multithreading Basics
    assert status_by_name["Classes & Objects"] == "not_started"
    assert status_by_name["Scope & Storage Classes"] == "not_started"
    assert status_by_name["Exception Handling"] == "not_started"
    assert status_by_name["Multithreading Basics"] == "not_started"

    # Pending completion suggestions exist ONLY for topics with verified code inside the file
    suggestions = code_rag.list_code_suggestions(roadmap_id=rm_id, state="pending")
    suggested_names = {s["topic_name"] for s in suggestions}
    assert "Basics & Compilation" in suggested_names
    assert "Variables & Data Types" in suggested_names
    assert "Control Flow" in suggested_names
    assert "Functions" not in suggested_names
    assert "Arrays" not in suggested_names
    assert "Pointers" not in suggested_names

    # Re-sync with NO file changes -> incremental check skips all unchanged files
    noop_sync = code_rag.sync_roadmap_folder(rm_id)
    assert noop_sync["files_reindexed"] == 0
    assert noop_sync["new_suggestions"] == []

    # Now write REAL function code into functions_practice.cpp -> detects ONLY that changed file & asks to confirm!
    (folder / "functions_practice.cpp").write_text(
        "#include <iostream>\nusing namespace std;\nint add(int a, int b) {\n    return a + b;\n}\nint main() {\n    cout << add(2, 3);\n    return 0;\n}\n",
        encoding="utf-8",
    )
    changed_sync = code_rag.sync_roadmap_folder(rm_id)
    assert changed_sync["files_reindexed"] == 1
    assert any(s["topic_name"] == "Functions" for s in changed_sync["new_suggestions"])
    detail_mid = progress.get_roadmap(rm_id)
    # Still NOT auto-completed — stays 'learning' until user confirms!
    assert next(t for t in detail_mid["topics"] if t["name"] == "Functions")["status"] == "learning"

    # Confirm Basics suggestion -> topic becomes completed
    basics_sugg = next(s for s in suggestions if s["topic_name"] == "Basics & Compilation")
    confirmed = code_rag.resolve_code_suggestion(basics_sugg["id"], "confirmed")
    assert confirmed["suggestion_state"] == "confirmed"
    detail_after = progress.get_roadmap(rm_id)
    assert next(t for t in detail_after["topics"] if t["name"] == "Basics & Compilation")["status"] == "completed"

    # Dismiss Variables suggestion -> stays dismissed across re-sync until file changes
    var_sugg = next(s for s in suggestions if s["topic_name"] == "Variables & Data Types")
    code_rag.resolve_code_suggestion(var_sugg["id"], "dismissed")
    code_rag.sync_roadmap_folder(rm_id)
    remaining_names = {s["topic_name"] for s in code_rag.list_code_suggestions(roadmap_id=rm_id, state="pending")}
    assert "Variables & Data Types" not in remaining_names


def test_hybrid_code_rag_search_and_prompt_context(isolated_learning_env):
    rm_id = isolated_learning_env["roadmap_id"]
    folder = isolated_learning_env["folder"]
    code_rag.link_folder_to_roadmap(rm_id, str(folder), sync_now=True)

    # Search for lowercase / if_else code via Hybrid RAG
    hits = code_rag.search_code_rag("lowercase character if else", roadmap_id=rm_id, limit=3)
    assert hits
    assert hits[0]["rel_path"] == "if_else.cpp"
    assert "lower" in hits[0]["snippet"]

    # Search for sizeof / variables
    hits_var = code_rag.search_code_rag("sizeof double variable", roadmap_id=rm_id, limit=3)
    assert hits_var
    assert any(h["rel_path"] == "variables_data_type.cpp" for h in hits_var)

    # RAG prompt context builder includes folder stats, empty files, and retrieved code
    ctx = code_rag.build_rag_prompt_context("check my if else code in C++ with DSA")
    assert "C++ with DSA" in ctx
    assert "while_loop.cpp" in ctx
    assert "if_else.cpp" in ctx


def test_friendly_proactive_coach_uses_folder_insights(isolated_learning_env):
    rm_id = isolated_learning_env["roadmap_id"]
    folder = isolated_learning_env["folder"]
    code_rag.link_folder_to_roadmap(rm_id, str(folder), sync_now=True)

    # Mark all pending suggestions confirmed so we test the empty-file friendly check-in
    for s in code_rag.list_code_suggestions(roadmap_id=rm_id, state="pending"):
        code_rag.resolve_code_suggestion(s["id"], "confirmed")

    checkin = app.build_proactive_checkin(preferred_category="learning", use_llm=False)
    assert checkin is not None
    assert checkin["category"] == "learning"
    assert "while_loop.cpp" in checkin["message"] or "functions_practice.cpp" in checkin["message"]


def test_folder_rag_api_and_chat_commands(isolated_learning_env):
    rm_id = isolated_learning_env["roadmap_id"]
    folder = isolated_learning_env["folder"]
    client = TestClient(app.app)

    # 1. Link folder via API
    r_link = client.put(
        f"/api/learning/roadmaps/{rm_id}/folder",
        json={"folder_path": str(folder), "enabled": True},
    )
    assert r_link.status_code == 200
    body = r_link.json()
    assert body["sync"]["practiced_files"] == 4

    # 2. Fetch code insights via API
    r_ins = client.get(f"/api/learning/roadmaps/{rm_id}/code-insights")
    assert r_ins.status_code == 200
    ins = r_ins.json()
    assert "while_loop.cpp" in ins["empty_files"]
    assert ins["friendly_summary"]

    # 3. Query Hybrid RAG via API
    r_rag = client.post(
        "/api/learning/rag/search",
        json={"query": "Hello C++ cout", "roadmap_id": rm_id, "limit": 3},
    )
    assert r_rag.status_code == 200
    assert any(item["rel_path"] == "first_cpp.cpp" for item in r_rag.json()["results"])

    # 4. Chat commands for syncing and confirming suggestions
    sync_reply = app._learning_command("sync my C++ with DSA learning folder")
    assert sync_reply is not None
    assert "C++ with DSA" in sync_reply[0]

    confirm_reply = app._learning_command("confirm all code suggestions")
    assert confirm_reply is not None
    assert "Marked completed" in confirm_reply[0]


def test_folder_picker_endpoint(isolated_learning_env, monkeypatch):
    folder = isolated_learning_env["folder"]
    client = TestClient(app.app)

    monkeypatch.setattr(code_rag, "pick_local_folder", lambda initial_dir=None: str(folder))
    res = client.post("/api/learning/folders/pick", json={})
    assert res.status_code == 200
    assert res.json() == {"cancelled": False, "folder_path": str(folder)}

    monkeypatch.setattr(code_rag, "pick_local_folder", lambda initial_dir=None: None)
    res_cancel = client.post("/api/learning/folders/pick", json={})
    assert res_cancel.status_code == 200
    assert res_cancel.json() == {"cancelled": True, "folder_path": None}


def test_code_rag_modern_languages_and_stat_skip(temp_db, tmp_path, monkeypatch):
    """Verify React/TS/SQL/Rust concept extraction and zero-disk-read skip on unchanged files."""
    schema.init(temp_db.database_path)
    imported = progress.import_learning_path(
        name="Full-Stack Systems",
        category="technical",
        topics=["React Hooks & Components", "REST APIs & Routing", "SQL Queries", "Rust Ownership"],
        auto_generate_if_empty=False,
    )
    rm = imported["roadmap"]

    folder = tmp_path / "fullstack_practice"
    folder.mkdir()
    tsx_file = folder / "useCounter.tsx"
    tsx_file.write_text(
        "import { useState, useEffect } from 'react';\n"
        "export function CounterWidget() {\n"
        "  const [count, setCount] = useState(0);\n"
        "  useEffect(() => { document.title = String(count); }, [count]);\n"
        "  return <div>{count}</div>;\n"
        "}\n",
        encoding="utf-8",
    )
    rs_file = folder / "borrow_demo.rs"
    rs_file.write_text(
        "struct Buffer { data: Vec<u8> }\n"
        "impl Buffer {\n"
        "    fn push_byte(&mut self, b: u8) { self.data.push(b); }\n"
        "}\n",
        encoding="utf-8",
    )

    tsx_info = code_rag.analyze_source_file(tsx_file, folder)
    assert "react_components_hooks" in tsx_info["code_concepts"]
    assert "CounterWidget" in tsx_info["symbols"]

    rs_info = code_rag.analyze_source_file(rs_file, folder)
    assert "rust_ownership_borrowing" in rs_info["code_concepts"]
    assert "Buffer" in rs_info["symbols"]

    code_rag.link_folder_to_roadmap(rm["id"], str(folder), sync_now=True)

    # On second sync with unchanged mtime+size, read_bytes should NOT be called at all
    read_calls = []
    orig_read_bytes = type(tsx_file).read_bytes

    def _spy_read_bytes(self):
        read_calls.append(self.name)
        return orig_read_bytes(self)

    monkeypatch.setattr(type(tsx_file), "read_bytes", _spy_read_bytes)
    sync2 = code_rag.sync_roadmap_folder(rm["id"])
    assert sync2["files_reindexed"] == 0
    assert read_calls == []
