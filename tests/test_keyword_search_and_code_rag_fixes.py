"""Regression tests for code-to-topic accuracy, grounded learning level context,
improved keyword search (aliases/stemming/typos), and conversational suggestion dismissal.
"""

from datetime import datetime

import app
from agent.loop import _build_initial_messages, _build_ollama_chat_payload
from learning import code_rag, progress


def _setup_cpp_roadmap_with_loops(tmp_path):
    app.init_learning_module("local")
    imported = progress.import_learning_path(
        name="C++ with DSA",
        raw_text=(
            "Basics & Compilation\n"
            "Variables & Data Types\n"
            "Operators & Type Casting\n"
            "Input / Output\n"
            "Control Flow\n"
            "Functions\n"
            "Arrays\n"
            "Strings\n"
            "Linked Lists\n"
            "Polymorphism & Virtual Functions\n"
            "Abstract Classes\n"
            "Trees\n"
            "Graphs\n"
            "Dynamic Programming\n"
        ),
        category="technical",
    )
    rm_id = int(imported["roadmap"]["id"])
    detail = progress.get_roadmap(rm_id)
    topics_by_name = {t["name"]: t for t in detail["topics"]}
    for done_name in (
        "Basics & Compilation",
        "Variables & Data Types",
        "Operators & Type Casting",
        "Input / Output",
        "Control Flow",
    ):
        progress.set_topic_status(int(topics_by_name[done_name]["id"]), "completed")

    folder = tmp_path / "cpp_dsa"
    folder.mkdir()
    (folder / "for_loop.cpp").write_text(
        "#include <iostream>\n"
        "using namespace std;\n"
        "int main() {\n"
        "    int sum = 0;\n"
        "    for (int i = 0; i < 10; i++) {\n"
        "        sum += i;\n"
        "    }\n"
        "    cout << sum << endl;\n"
        "    return 0;\n"
        "}\n",
        encoding="utf-8",
    )
    (folder / "while_loop.cpp").write_text(
        "#include <iostream>\n"
        "using namespace std;\n"
        "int main() {\n"
        "    int count = 0;\n"
        "    while (count < 5) {\n"
        "        cout << count << endl;\n"
        "        count++;\n"
        "    }\n"
        "    return 0;\n"
        "}\n",
        encoding="utf-8",
    )
    code_rag.link_folder_to_roadmap(rm_id, str(folder), sync_now=True, embed=None)
    return rm_id, folder


def test_loop_files_with_int_equals_zero_never_match_polymorphism_or_abstract_classes(tmp_path):
    rm_id, folder = _setup_cpp_roadmap_with_loops(tmp_path)

    for_info = code_rag.analyze_source_file(folder / "for_loop.cpp", folder)
    while_info = code_rag.analyze_source_file(folder / "while_loop.cpp", folder)
    assert "polymorphism_virtual" not in for_info["code_concepts"]
    assert "polymorphism_virtual" not in while_info["code_concepts"]
    assert "control_flow" in for_info["code_concepts"]
    assert "control_flow" in while_info["code_concepts"]

    pending = code_rag.list_code_suggestions(roadmap_id=rm_id, state="pending")
    pending_names = {s["topic_name"] for s in pending}
    assert "Polymorphism & Virtual Functions" not in pending_names
    assert "Abstract Classes" not in pending_names

    # Genuine pure virtual function MUST still match polymorphism_virtual
    (folder / "shape_virtual.cpp").write_text(
        "#include <iostream>\n"
        "class Shape {\n"
        "public:\n"
        "    virtual double area() const = 0;\n"
        "};\n"
        "int main() { return 0; }\n",
        encoding="utf-8",
    )
    virt_info = code_rag.analyze_source_file(folder / "shape_virtual.cpp", folder)
    assert "polymorphism_virtual" in virt_info["code_concepts"]


def test_grounded_learning_context_includes_completed_vs_unlearned_and_follows_up(tmp_path):
    _setup_cpp_roadmap_with_loops(tmp_path)

    # 1. Spoken "C plus plus" + "learnt" + "DSA problem" must trigger grounded progress context
    ctx1 = code_rag.build_rag_prompt_context("give me some DSA problem till I learnt in C plus plus")
    assert "COMPLETED (user HAS learned ONLY these)" in ctx1
    assert "Control Flow" in ctx1
    assert "NOT YET LEARNED" in ctx1
    assert "Functions" in ctx1
    assert "STRICT LEVEL RULE" in ctx1

    # 2. Follow-up turn without tech keywords ("I mean like the interview level") stays grounded via history
    history = [
        {"role": "user", "content": "give me some DSA problem till I learnt in C plus plus"},
        {"role": "assistant", "content": "Here are some loop and control flow problems."},
    ]
    ctx2 = code_rag.build_rag_prompt_context("I mean like the interview level", history=history)
    assert "COMPLETED (user HAS learned ONLY these)" in ctx2
    assert "Control Flow" in ctx2

    # 3. _productivity_context handles "C++" and "C plus plus" properly (fixing broken \bc\+\+\b regex)
    p_cpp = app._productivity_context("give me problems in C++")
    p_spoken = app._productivity_context("give me problems till I learnt in C plus plus")
    assert "Completed in C++ with DSA:" in p_cpp
    assert "Completed in C++ with DSA:" in p_spoken

    # 4. Agent loop injects grounded learning context on follow-up turn + repeat_penalty
    msgs = _build_initial_messages("I mean like the interview level", history, [], app.agent_deps)
    assert "COMPLETED (user HAS learned ONLY these)" in msgs[0]["content"]
    _, payload, _ = _build_ollama_chat_payload(msgs, max_tokens=512)
    assert payload["options"]["repeat_penalty"] >= 1.1


def test_improved_keyword_search_handles_aliases_stems_and_typos(tmp_path):
    _setup_cpp_roadmap_with_loops(tmp_path)

    # Spoken alias "C plus plus" + stemmed "looping" finds while_loop.cpp / for_loop.cpp
    hits_stem = code_rag.search_code_rag("what looping did I write in C plus plus")
    assert any(h["rel_path"] in ("while_loop.cpp", "for_loop.cpp") for h in hits_stem)

    # Typo tolerance ("whlie") still matches while_loop.cpp
    hits_typo = code_rag.search_code_rag("whlie")
    assert any(h["rel_path"] == "while_loop.cpp" for h in hits_typo)

    # Memory keyword search handles "C plus plus" -> "C++", stems ("learnt"), and typos
    app.memory_store.add_memory("I am learning C++ and practicing loops every evening")
    mem_cpp = app.memory_store.search_memories("what did I say about C plus plus")
    assert any("C++" in m["content"] for m in mem_cpp)
    mem_typo = app.memory_store.search_memories("practcing")
    assert any("practicing" in m["content"] for m in mem_typo)


def test_stop_asking_and_short_no_dismiss_pending_code_suggestions(tmp_path):
    rm_id, folder = _setup_cpp_roadmap_with_loops(tmp_path)
    # Create a real Functions file to trigger a legitimate pending suggestion for Functions
    (folder / "functions_demo.cpp").write_text(
        "#include <iostream>\n"
        "int add(int a, int b) {\n"
        "    return a + b;\n"
        "}\n"
        "int main() {\n"
        "    std::cout << add(2, 3);\n"
        "    return 0;\n"
        "}\n",
        encoding="utf-8",
    )
    code_rag.sync_roadmap_folder(rm_id, embed=None)
    pending = code_rag.list_code_suggestions(roadmap_id=rm_id, state="pending")
    assert any(s["topic_name"] == "Functions" for s in pending)

    chat_id = app.memory_store.create_chat()["id"]
    app.memory_store.add_notification(
        chat_id,
        "task-coach-learning-1",
        "Quick check-in — looks like you've been practicing Functions (functions_demo.cpp) in C++ with DSA. Should I tick that one off for you?",
    )

    # Proactive coach must NOT re-ask about Functions when it was already asked recently
    daytime = datetime(2026, 11, 26, 14, 0, tzinfo=app.LOCAL_TIMEZONE)
    checkin = app.build_proactive_checkin(chat_id, preferred_category="learning", now=daytime)
    assert checkin is not None
    assert "tick that one off" not in checkin["message"].lower()

    # Saying "no simply dont ask me again and again" dismisses pending suggestions cleanly
    reply = app._handle_local_command("no simply dont ask me again and again", chat_id)
    assert reply is not None
    text, provider = reply
    assert provider == "local-learning"
    assert "Functions" in text
    assert code_rag.list_code_suggestions(roadmap_id=rm_id, state="pending") == []


def test_planning_advice_and_multidomain_prompts_not_hijacked_by_keyword_lists(tmp_path):
    _setup_cpp_roadmap_with_loops(tmp_path)
    chat_id = app.memory_store.create_chat()["id"]
    app.memory_store.add_memory("My goal is to master C++ and DSA this semester")
    app.memory_store.create_habit("Morning DSA", "Code", 1)
    app.memory_store.create_reminder("Revise loops", "2026-11-27T08:00:00+05:30", None, chat_id)

    # 1. Planning, organizing, analyzing, and multi-domain prompts must reach the LLM (return None locally)
    llm_prompts = [
        "plan my next day and task to complete",
        "plan my habits for tomorrow",
        "organize my pending tasks and habits",
        "show my tasks and habits",
        "check my habits and reminders",
        "show my tasks and reminders",
        "prioritize my open tasks for tomorrow",
        "break down my pending task into steps",
        "make a timetable for my remaining tasks",
        "analyze my habits and learning progress",
        "help me plan my goals",
    ]
    for prompt in llm_prompts:
        res = app._handle_local_command(prompt, chat_id)
        assert res is None, f"Prompt {prompt!r} was wrongly hijacked by local handler: {res}"

    # 2. Explicit single-domain list commands still work deterministically
    assert app._handle_local_command("show my pending tasks", chat_id)[1] == "local-task-manager"
    assert app._handle_local_command("pending tasks", chat_id)[1] == "local-task-manager"
    assert app._handle_local_command("tasks", chat_id)[1] == "local-task-manager"
    assert app._handle_local_command("check my habits to complete", chat_id)[1] == "local-habit-manager"
    assert app._handle_local_command("pending habits", chat_id)[1] == "local-habit-manager"
    assert app._handle_local_command("show reminders", chat_id)[1] == "local-scheduler"
    assert app._handle_local_command("upcoming reminders", chat_id)[1] == "local-scheduler"
    assert app._handle_local_command("show my notes", chat_id)[1] == "local-memory"

    # 3. Planning prompts inject full live workspace snapshot (habits, tasks, reminders, analytics, learning)
    msgs = _build_initial_messages("plan my next day and task to complete", [], [], app.agent_deps)
    sys_prompt = msgs[0]["content"]
    assert "Live workspace snapshot:" in sys_prompt
    assert "Morning DSA" in sys_prompt
    assert "Pending tasks:" in sys_prompt
    assert "Revise loops" in sys_prompt
    assert "Gamification & analytics:" in sys_prompt
    assert "COMPLETED (user HAS learned ONLY these)" in sys_prompt
    assert "NOT YET LEARNED" in sys_prompt
