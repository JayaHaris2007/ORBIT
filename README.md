<p align="center">
  <img src="logo.png" alt="ORBIT Logo" width="84" height="84" />
</p>

# ORBIT — Personal Local AI Assistant

**ORBIT** is a 100% local personal AI assistant and productivity companion designed to run privately on your own machine. It tracks your daily work, tasks, habits, learning progress, local code practice, reminders, and memories — turning everything you're doing into actionable guidance and real-time assistance via chat, voice, or Discord.

---

## Why "ORBIT"?

Just like a satellite orbits around the Earth — continuously observing, gathering signals, and keeping track of what is happening below — **ORBIT** orbits around *you*.

It stays quietly in motion around your daily life and work, tracking what you are building, studying, completing, and planning:
- The **tasks** you need to finish and the **habits** you're building every day.
- The **learning roadmaps** you follow and the **actual code files** you write in your local folders.
- The **facts, notes, and reminders** you share over time.
- The **patterns and momentum** behind your productivity.

By keeping all of this context in one private local database (`assistant.db`), ORBIT doesn't just answer generic questions — it understands what you're actively working on and helps you stay consistent, focused, and moving forward without sending your personal data to external servers.

---

## Main Purpose

Most productivity apps force you to manually juggle separate tools for to-dos, habit trackers, study plans, reminders, notes, and AI chat — none of which know what the others are doing.

ORBIT unifies them into a single local intelligence layer:
- **Track everything you do automatically:** Log tasks, habits, reminders, memories, and coding progress naturally through conversation or voice.
- **Connect learning to real practice:** Link local code folders so ORBIT sees what you've actually coded and recommends the next topic when you're ready.
- **Act proactively, not just passively:** Surface reminders, streaks, and gentle check-ins when goals stall.
- **Stay 100% private and local-first:** Powered by local Ollama, local SQLite, and local CPU neural TTS/STT, with optional cloud upgrades only when you choose them.

---

## Features & How They Work

### System Overview

```text
  [ User Channels: Web Chat · Live Voice (Ctrl+Space) · Discord Text/Voice ]
                                     │
                                     ▼
  [ FastAPI Core (app.py) ]
     ├── 1. Deterministic Command Router (services/command_router.py)
     │      Instant local execution for tasks, habits, learning, reminders, & navigation
     ├── 2. AI Agent & Native Tool Loop (agent/loop.py + agent/tools.py)
     │      Local Ollama (qwen3.5:4b) or optional Gemini BYOK + confirmation safety
     ├── 3. Real-Time Voice Pipeline (voice/router.py, stt.py, text_clean.py, tts.py)
     │      16kHz PCM WebSocket -> Pre-roll VAD -> STT -> Brain -> Clean Speech -> WAV TTS
     └── 4. Local Data & Background Jobs (assistant.db + APScheduler)
            SQLite WAL storage, Hybrid Memory, Code-Folder RAG, Reminders & Proactive Coach
```

### 1. Hybrid AI Brain & Native Tool Calling
- **What it does:** Answers technical and everyday questions, streams replies in real time, and directly manages your tasks, habits, reminders, memories, and learning roadmaps.
- **How it works:** Incoming prompts first pass through a deterministic command router (`services/command_router.py`) so common actions execute instantly without waiting on an LLM. Complex or open-ended requests stream via Server-Sent Events (`/api/generate/stream`) through local **Ollama** (`qwen3.5:4b`) or an optional **Google AI Studio Gemini API key** (BYOK). Multi-step tool calls execute through `agent/loop.py` and `agent/tools.py`, with a confirmation gate (`agent/confirm.py`) before destructive deletions.

### 2. Hands-Free Live Voice Mode (`Ctrl + Space`)
- **What it does:** Enables continuous two-way spoken conversation with ORBIT, including mic mute, mid-sentence interruption, and spoken command execution.
- **How it works:**
  1. Browser `AudioWorklet` (`pcm-capture.js`) captures 16 kHz mono PCM in 100 ms frames over `/ws/voice`.
  2. The backend (`voice/router.py`) keeps a 500 ms rolling pre-roll buffer (preventing silence bloat and clipped first syllables) and runs energy-based VAD with barge-in support.
  3. Speech is transcribed (`voice/stt.py`), routed through ORBIT's unified brain, summarized and cleaned for natural pronunciation — automatically stripping file extensions (e.g., `while_loop.cpp` → *"while loop"*) and placeholders (`voice/text_clean.py`) — and streamed back sentence-by-sentence via Gradium Phonon CPU TTS (`voice/phonon_engine.py`, with Windows SAPI fallback).

### 3. Adaptive Learning Roadmaps & Local Code-Folder Tracking (Code RAG)
- **What it does:** Tracks structured study roadmaps with prerequisite trees, detects topics you've already practiced in your local codebase, lets you search your own snippets, and tells you what is ready to learn next.
- **How it works:** Roadmaps and topic statuses are stored in SQLite (`learning/roadmaps.py`, `learning/progress.py`). When you link a local folder, `learning/code_rag.py` indexes your source files locally, maps practiced files (like `while_loop.cpp` and `if_else.cpp`) to matching topics (like *Control Flow*), powers snippet retrieval, and generates nudges (`learning/nudges.py`) to mark completed topics done and advance to unlocked topics.

### 4. Tasks, Daily Habits, Streaks & Gamification
- **What it does:** Tracks prioritized to-do items with due dates alongside recurring daily habits, streaks, and XP progression.
- **How it works:** Backed by SQLite (`memory.py`, `routers/productivity.py`) and natural-language parsers (`services/productivity_parsers.py`). You can add, search, update, or complete tasks and habits conversationally via chat or voice, and changes immediately sync across the workspace.

### 5. Scheduled Reminders, Hybrid Memory & Proactive Coaching
- **What it does:** Remembers facts, preferences, and ongoing projects you share, triggers scheduled reminders on time, and sends occasional friendly check-ins about pending goals.
- **How it works:** `memory.py` indexes memories using built-in hybrid lexical-concept recall (no PyTorch or external vector DB required). `APScheduler` powers one-time and recurring reminders (`services/reminders.py`) and cooldown-guarded proactive check-ins (`services/proactive_coach.py`).

### 6. Unified Productivity Analytics
- **What it does:** Gives a clear picture of your consistency and output across all tracked areas.
- **How it works:** Aggregates task completion rates, daily habit streaks, yearly activity history, and per-roadmap learning completion into a unified Productivity % and trend breakdown.

### 7. Live Web Research
- **What it does:** Looks up current information, docs, or external topics and summarizes results with source references.
- **How it works:** `research/search_engine.py` performs rate-limited queries (`research/rate_limit.py`, supporting Tavily via `TAVILY_API_KEY`) and summarizes findings while treating fetched web content as untrusted data.

### 8. Discord Text & Voice Integration (Optional)
- **What it does:** Extends ORBIT into your Discord server for both text chats and two-way voice channel calls.
- **How it works:** `discord_bot.py` and `services/discord_voice.py` connect using `AI_DISCORD_TOKEN` and route every message or spoken turn through the exact same local brain, memory, STT, and TTS pipeline.

---

## Required Software & Exact Versions

Verified working environment:

| Software | Tested / Exact Version | Minimum Supported | Download |
|----------|------------------------|-------------------|----------|
| **Python** | **Python 3.15.2** | Python 3.11+ (`3.13` / `3.14` / `3.15.2`) | [python.org](https://www.python.org/downloads/) |
| **Node.js & npm** | **Node.js v26.13.0** (`npm 11.20.0`) | Node.js 18+ | [nodejs.org](https://nodejs.org/) |
| **Ollama** | **Ollama 0.40.16** (`qwen3.5:4b`) | Latest Ollama | [ollama.com](https://ollama.com/) |

Check your installed versions before starting:

```powershell
python --version
node --version
npm --version
ollama --version
```

---

## Tech Stack

- **LLM Brain:** Local [Ollama](https://ollama.com) (`qwen3.5:4b`, native tool calling + SSE streaming) + optional Gemini BYOK
- **Voice TTS:** Gradium Phonon (`phonon-31m-en` via `ptts` on CPU) with automatic Windows SAPI fallback
- **Voice STT:** Local Whisper / `SpeechRecognition` over WebSocket (`/ws/voice`) with rolling pre-roll VAD & barge-in
- **Backend:** Python FastAPI, SQLite (WAL mode), APScheduler, built-in hybrid lexical-concept memory
- **Web App:** React 19, Vite, Tailwind CSS v4

---

## Step-by-Step Setup (Clone → Install → Run)

### 1. Clone the Repository (`master` branch)

```powershell
git clone https://github.com/JayaHaris2007/ORBIT007.git
cd ORBIT007
```

### 2. Install & Start Ollama

Install [Ollama](https://ollama.com), then pull the default local model and start the service:

```powershell
ollama pull qwen3.5:4b
ollama serve
```

### 3. Create Python Virtual Environment & Install Dependencies

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 4. Install Frontend Dependencies

```powershell
cd frontend
npm i
cd ..
```

### 5. Configure Environment Variables (`.env`)

Copy the example environment file:

```powershell
Copy-Item .env.example .env
```

Key settings in `.env` (all work out of the box locally):

```env
OLLAMA_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3.5:4b
OLLAMA_NUM_CTX=8192
SPIDEY_TIMEZONE=Asia/Kolkata

# Voice TTS (Phonon CPU neural TTS; falls back to Windows SAPI automatically)
TTS_BACKEND=phonon
PHONON_MODEL=hf://gradium/phonon-31m-en
PHONON_QUANT=q8
PHONON_LANG=en
SPIDEY_TTS_VOICE=Easton

# Optional: Tavily key for live web search & research
TAVILY_API_KEY=

# Optional: Discord bot token
AI_DISCORD_TOKEN=
```

*(Optional)* Pre-cache the Phonon TTS weights once while online:

```powershell
$env:SPIDEY_ALLOW_HUB = "1"
.\.venv\Scripts\python.exe -m ptts --lang en --quant q8 --voice Easton "Hello from ORBIT" -o test.wav
```

---

## How to Run the Program

### Option A: Desktop Control Center GUI (Recommended)

Launch the desktop supervisor GUI to start, monitor, and manage Ollama, the backend API, and the web server from one window:

- **Double-click** `Spidey Control Center.pyw` (or `start.bat`), **or** run:

```powershell
.\.venv\Scripts\pythonw.exe spidey_launcher.py
```

The **Control Center** provides:
1. **Global Controls:** `▶ START ALL`, `■ STOP ALL`, `↻ RESTART`, and `↗ OPEN WEB UI` (`http://localhost:5173`).
2. **Service Health Checks:** Live status for Ollama (`127.0.0.1:11434`), Backend API (`127.0.0.1:8000`), and Web Server (`http://localhost:5173`).
3. **Live Configuration (`.env`):** Edit `OLLAMA_MODEL`, `LLM_BACKEND` (`ollama` / `gemini`), `TTS_BACKEND` (`phonon` / `sapi`), proactive `COACH (MIN)` interval, and run `pytest` directly.
4. **Live Logs & Clean Shutdown:** Tabbed stdout/stderr logs and clean process-tree shutdown on exit.

*(For multi-terminal batch mode, run `.\start.bat --cli`.)*

### Option B: Run Manually in Two Terminals

**Terminal 1 — Backend Server (`Port 8000`):**

```powershell
.\.venv\Scripts\activate
python app.py --server
```

**Terminal 2 — Frontend Dev Server (`Port 5173`):**

```powershell
npm --prefix frontend run dev
```

Then open **http://localhost:5173** in your browser.

---

## Commands & Shortcuts

| Command / Shortcut | Action |
|--------------------|--------|
| `/tasks` | Manage prioritized tasks & due dates |
| `/habits` | Track daily habits, streaks, and XP |
| `/learning` | Open learning roadmaps & linked local code folders |
| `/reminders` | Manage scheduled reminders & saved memories |
| `/analytics` | View productivity stats, streaks, and roadmap progress |
| `/settings` | Configure profile, Gemini BYOK key, notifications, or database reset |
| `/live` or `Ctrl + Space` | Toggle hands-free Live Voice Mode |
| `M` *(in Live Mode)* | Mute / unmute microphone |
| `Space` *(in Live Mode)* | Send speech immediately or interrupt ORBIT |
| `/orbit` | Open the ORBIT007 Live Agent |
| `/new` | Start a fresh chat session |

---

## Running Tests & Production Build

**Run lint and the Python test suite (matches CI):**

```powershell
ruff check . --select E9,F63,F7,F82
.\.venv\Scripts\python.exe -m pytest -q
```

**Build the web app for production:**

```powershell
npm --prefix frontend run build
```
