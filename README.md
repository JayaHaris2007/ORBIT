<p align="center">
  <img src="logo.png" alt="ORBIT Logo" width="84" height="84" />
</p>

# ORBIT — Personal Local AI Assistant

**ORBIT** is a 100% local personal AI assistant and calm productivity workspace designed to run privately on your own machine. It tracks your daily work, tasks, habits, learning roadmaps, local code practice, reminders, and long-term memories — turning everything you're doing into actionable guidance and real-time assistance via Web Chat, hands-free Live Voice, or Discord Text & Voice Channels.

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

## Key Improvements in the Latest Architecture

| Area | Improvement |
|------|-------------|
| **Sentence-Streamed Live Voice (`/ws/voice`)** | LLM tokens now stream into an incremental sentence buffer while a concurrent worker synthesizes **Sentence 1** via Phonon CPU TTS as **Sentence 2** is still generating — cutting time-to-first-audio by **~40–60%**, paired with live streaming `reply_partial` captions. |
| **Unified Turn Orchestrator** | Web Chat, SSE streaming, `/ws` Live Agent, and `/ws/voice` all run through one shared 4-stage pipeline (`services/turn_orchestrator.py`): confirmation gate → 0 ms deterministic router → context & short follow-up resolution → native tool loop. |
| **Zero-Churn SQLite WAL & HTTP Pooling** | `memory.py` and `learning/schema.py` reuse thread-local persistent SQLite WAL connections (instead of reopening + re-running PRAGMAs per query), and `agent/loop.py` reuses a shared `aiohttp.ClientSession` across streaming rounds. |
| **Instant Delta Code RAG + Multi-Language Rules** | `learning/code_rag.py` skips unchanged files with zero disk reads via `mtime + size` checks and detects concepts/symbols across **C++, C, Python, Java, React Hooks/JSX, TypeScript Interfaces, Async/Promises, REST APIs, SQL, Rust Ownership, and Go**. |
| **Modular Workspace, Top Navbar & Auto-Paused ASCII Physics** | `SpideyWorkspace.jsx` includes a full-section `TopNavbar` (`Chat`, `Tasks`, `Habits`, `Reminders`, `Learning`, `Analytics`, `Settings`) + dedicated `MuteButton` (speaker & mic mute) alongside memoized `ConversationStream`, `ComposerBar`, and `ChatHistoryDrawer`; `SpideyAsciiCanvas.jsx` auto-pauses behind `LiveOverlay` or off-screen. |
| **98.8% Smaller Icon Bundle (`-580 KB`)** | Replaced wildcard icon barrel imports with explicit tree-shaken imports and lazy-loaded modals/overlays, shrinking `icons-vendor.js` from **586.79 KB** down to **8.61 KB** (`3.47 KB` gzip). |
| **Universal Multi-Model Ollama Support** | Works with **every chat/coder/reasoning model in Ollama** (`qwen3.5`, `llama3.2`, `gemma3`, `deepseek-r1`, `mistral`, `phi4`, `qwen2.5-coder`, custom GGUFs). Models without native `tools` or `think` automatically adapt on the fly with live workspace context injection, and you can hot-swap or pull any model directly from **Settings (`/settings`)** or the Control Center GUI with zero server restart. |
| **Hardened Auth & Portable Identity** | `/tts/*` audio replies are protected under `ORBIT_API_TOKEN`, WebSockets authenticate via `Sec-WebSocket-Protocol` (`orbit-token.*`) so tokens never leak into URL logs, and user identity resolves dynamically from saved memories or `ORBIT_USER_NAME`. |

---

## Features & How They Work

### System Overview

```text
  [ User Channels: Web Chat · Live Voice (Ctrl+Space) · Discord Text & Voice ]
                                      │
                                      ▼
  [ FastAPI Core (app.py) + Unified Turn Orchestrator (services/turn_orchestrator.py) ]
     ├── 1. Confirmation Gate (agent/confirm.py)
     │      Explicit yes/no verification before any destructive deletion
     ├── 2. 0ms Deterministic Router (services/command_router.py)
     │      Instant local execution for tasks, habits, learning, reminders, & navigation
     ├── 3. Streaming Native Tool Loop (agent/loop.py + agent/tools.py)
     │      Local Ollama (qwen3.5:4b) or optional Gemini BYOK over shared aiohttp session
     ├── 4. Concurrent Streaming Voice Pipeline (voice/router.py, stt.py, text_clean.py, tts.py)
     │      16kHz PCM WS -> 500ms Pre-roll VAD -> STT -> Sentence-Streamed Phonon TTS
     └── 5. Local Data & Background Jobs (assistant.db + APScheduler)
            Thread-local SQLite WAL, FTS5 Code RAG, Hybrid Memory & Proactive Coach
```

### 1. Hybrid AI Brain & Native Tool Calling
- **What it does:** Answers technical and everyday questions, streams replies token-by-token, and directly manages your tasks, habits, reminders, memories, and learning roadmaps.
- **How it works:** Prompts pass through `services/turn_orchestrator.py`: deterministic commands execute in `<2 ms` via `services/command_router.py`, while open-ended or multi-step requests stream over SSE (`/api/generate/stream`) via local **Ollama** (`qwen3.5:4b`) or an optional **Google AI Studio Gemini API key** (BYOK) with confirmation safety (`agent/confirm.py`).

### 2. Hands-Free Live Voice Mode (`Ctrl + Space`)
- **What it does:** Enables continuous two-way spoken conversation with ORBIT, including mic mute (`M`), mid-sentence barge-in (`Space`), live streaming captions, and spoken command execution.
- **How it works:**
  1. Browser `AudioWorklet` (`pcm-capture.js`) streams 16 kHz mono PCM in 100 ms frames over `/ws/voice`.
  2. `voice/router.py` maintains a 500 ms rolling pre-roll buffer and energy VAD with echo gating.
  3. Transcribed speech (`voice/stt.py`) streams through the unified brain into an incremental sentence splitter, cleaning code/file extensions (`while_loop.cpp` → *"while loop"*) via `voice/text_clean.py` and synthesizing each sentence concurrently with **Gradium Phonon CPU neural TTS** (`voice/phonon_engine.py`, with Windows SAPI fallback).

### 3. Adaptive Learning Roadmaps & Local Code-Folder Tracking (Hybrid Code RAG)
- **What it does:** Tracks study roadmaps with prerequisite trees, detects topics you've practiced in your local folders, indexes chunks into SQLite FTS5 for snippet search, and suggests ready-to-learn topics.
- **How it works:** `learning/code_rag.py` performs fast `mtime + size` delta scans on linked folders, verifies substantive non-boilerplate logic across C++/Python/Java/React/TypeScript/SQL/Rust/Go, auto-starts practiced topics, and uses a Suggest & Confirm workflow before marking topics completed.

### 4. Tasks, Daily Habits, Streaks & Gamification
- **What it does:** Tracks prioritized to-dos with due dates alongside daily recurring habits, 7-day ASCII streak strips, and XP levels.
- **How it works:** Backed by thread-local SQLite WAL (`memory.py`) and natural-language parsers (`services/productivity_parsers.py`), syncing changes live across modals via `orbit:refresh`.

### 5. Scheduled Reminders, Hybrid Memory & Proactive Coaching
- **What it does:** Recalls personal facts, projects, and preferences without external vector DBs, fires one-time or recurring reminders, and sends cooldown-guarded check-ins.
- **How it works:** Powered by `memory.py` hybrid lexical-concept retrieval, `APScheduler` (`services/reminders.py`), and `services/proactive_coach.py`.

### 6. Unified Productivity Analytics & Live Web Research
- **Analytics (`/analytics`):** Combines task completion, habit streaks, per-roadmap progress, and a 365-day contribution heatmap.
- **Web Research:** Rate-limited live web search (`research/search_engine.py` via `TAVILY_API_KEY`) that treats external web pages as untrusted data.

---

## Required Software & Exact Versions

| Software | Tested / Exact Version | Minimum Supported | Download |
|----------|------------------------|-------------------|----------|
| **Python** | **Python 3.15.2** | Python 3.11+ (`3.13` / `3.14` / `3.15.2`) | [python.org](https://www.python.org/downloads/) |
| **Node.js & npm** | **Node.js v26.13.0** (`npm 11.20.0`) | Node.js 18+ | [nodejs.org](https://nodejs.org/) |
| **Ollama** | **Ollama 0.40.16** (`qwen3.5:4b`) | Latest Ollama | [ollama.com](https://ollama.com/) |

```powershell
python --version
node --version
npm --version
ollama --version
```

---

## Step-by-Step Setup (Clone → Install → Run)

### 1. Clone the Repository

```powershell
git clone https://github.com/JayaHaris2007/ORBIT007.git
cd ORBIT007
```

### 2. Install & Start Ollama

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

```powershell
Copy-Item .env.example .env
```

Key `.env` settings (works locally out of the box):

```env
OLLAMA_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3.5:4b
OLLAMA_NUM_CTX=8192
SPIDEY_TIMEZONE=Asia/Kolkata
ORBIT_USER_NAME=

# Voice TTS (Phonon CPU neural TTS; falls back to Windows SAPI automatically)
TTS_BACKEND=phonon
PHONON_MODEL=hf://gradium/phonon-31m-en
PHONON_QUANT=q8
PHONON_LANG=en
SPIDEY_TTS_VOICE=Easton

# Optional security token when exposing beyond 127.0.0.1
ORBIT_API_TOKEN=

# Optional: Tavily key for live web research
TAVILY_API_KEY=

# Optional: Discord Bot Token & allowlists (see full Discord guide below)
AI_DISCORD_TOKEN=
AI_DISCORD_ALLOWED_USER_IDS=
AI_DISCORD_ALLOWED_GUILD_IDS=
```

*(Optional)* Pre-cache the Phonon TTS weights once while online:

```powershell
$env:SPIDEY_ALLOW_HUB = "1"
.\.venv\Scripts\python.exe -m ptts --lang en --quant q8 --voice Easton "Hello from ORBIT" -o test.wav
```

---

## How to Run the Program

### Option A: Desktop Control Center GUI (Recommended)

Double-click **`Spidey Control Center.pyw`** (or `start.bat`), or run:

```powershell
.\.venv\Scripts\pythonw.exe spidey_launcher.py
```

The Control Center lets you `▶ START ALL`, `■ STOP ALL`, `↻ RESTART`, monitor live health for Ollama (`11434`), FastAPI (`8000`), and Vite (`5173`), edit `.env`, view tabbed logs, and run `pytest`.

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

Open **http://localhost:5173** in your browser to launch the ORBIT workspace.

---

## Discord Setup Guide (Text Messages & Two-Way Voice Channels)

ORBIT includes a full Discord bot (`discord_bot.py` + `services/discord_voice.py`) that connects **both text channels/DMs and live two-way Discord voice channels** directly to your local ORBIT brain, tasks, habits, reminders, STT, and Phonon TTS.

All required Discord voice packages (`discord.py`, `PyNaCl`, `davey` for Discord DAVE end-to-end voice encryption, and `discord-ext-voice-recv`) are **already installed by `requirements.txt`** — no external FFmpeg installation is required.

### Step 1: Create Your Discord Bot & Enable Intents
1. Open the [Discord Developer Portal](https://discord.com/developers/applications) and click **New Application** (e.g., `ORBIT`).
2. Go to the **Bot** tab on the left sidebar:
   - Click **Reset Token** and copy your Bot Token.
   - Scroll down to **Privileged Gateway Intents** and toggle **ON**:
     - **Message Content Intent** *(required so ORBIT can read messages and commands)*
     - *(Optional)* **Server Members Intent**
   - Click **Save Changes**.

### Step 2: Invite the Bot with Text + Voice Permissions
1. In the Developer Portal, open **OAuth2 → URL Generator**.
2. Under **Scopes**, check **`bot`**.
3. Under **Bot Permissions**, check:
   - **Text Permissions:** `View Channels`, `Send Messages`, `Read Message History`, `Send Messages in Threads`
   - **Voice Permissions:** `Connect`, `Speak`, `Use Voice Activity`
4. Copy the generated URL at the bottom, open it in your browser, and authorize the bot into your Discord server.

### Step 3: Add Token & Security Allowlists in `.env`
1. *(Recommended)* In Discord, open **User Settings → Advanced → Developer Mode** (turn ON):
   - Right-click your profile picture → **Copy User ID**.
   - Right-click your server icon → **Copy Server ID**.
2. Add them to your root `.env` file:

```env
AI_DISCORD_TOKEN=your_bot_token_here
AI_DISCORD_PREFIX=!

# Strongly recommended: lock the bot to only your Discord account & server
AI_DISCORD_ALLOWED_USER_IDS=123456789012345678
AI_DISCORD_ALLOWED_GUILD_IDS=987654321098765432

# Optional: pin proactive coaching check-ins to a specific channel ID
AI_DISCORD_NOTIFY_CHANNEL_ID=

# Auto-clear Discord chat context window every N days (default: 3; set 0 to disable)
AI_DISCORD_CONTEXT_RESET_DAYS=3

# Optional: fine-tune Discord voice VAD sensitivity
DISCORD_VOICE_ENERGY_THRESHOLD=260.0
DISCORD_VOICE_SILENCE_SECONDS=0.95
```

### Step 4: Start ORBIT (Runs In-Process Automatically)
- Whenever `AI_DISCORD_TOKEN` is set in `.env`, starting `python app.py --server` (or clicking `▶ START ALL` in `Spidey Control Center.pyw`) **automatically launches the Discord bot inside the FastAPI process**, sharing the loaded LLM, TTS engine, and SQLite database with zero extra VRAM/RAM overhead.
- *(Standalone mode)* If you want to run *only* the Discord bot without the web server, run:
  ```powershell
  .\.venv\Scripts\python.exe discord_bot.py
  ```

### Step 5: Using Discord Text Messages & DMs
- **Chat naturally (no prefix needed):** Send any message in an allowed server channel or DM (e.g., *"what's pending today?"*, *"add a high priority task to review PRs"*, *"remind me in 20 minutes to stretch"*).
- **Mention or prefix commands:**
  - `@ORBIT <question>` or `!ask <question>` / `!input <question>`
  - `!ping` — Instant gateway latency health check
  - `!reset` / `!clear` / `!new` — Clear your Discord chat context immediately (tasks, habits, reminders & memories stay untouched; also auto-clears every 3 days via `AI_DISCORD_CONTEXT_RESET_DAYS=3`)
  - `!notify here` — Pin scheduled check-ins and proactive recommendations to the current server text channel (falls back to DM if forbidden)

### Step 6: Using Discord Two-Way Voice Channels
1. **Hop into any Voice Channel** in your Discord server.
2. In any text channel of that server, send **`!join`** (or `!vc`, `!call`, or simply type `join voice` / `@ORBIT join my vc`).
3. ORBIT joins your voice channel, greets you aloud, and listens continuously using per-user Opus decoding + DAVE E2EE decryption + energy VAD:
   - Just **speak naturally** — ORBIT transcribes your speech locally, executes task/habit/learning/reminder tools, speaks a clean natural reply back into the call, and optionally mirrors the transcript + reply in the text channel.
   - If a scheduled reminder fires while you're in a call, ORBIT speaks the alert aloud in the voice channel too.
4. **Voice Call Controls (Type or Speak Aloud):**

| Action | Text Command | Spoken Voice Phrase |
|--------|--------------|---------------------|
| **Join your current voice channel** | `!join` · `!vc` · `!call` · `join voice` | — |
| **Interrupt ORBIT mid-sentence** | `!stop` · `!quiet` | *"stop talking"* / *"be quiet"* |
| **Make ORBIT speak custom text** | `!say <message>` | — |
| **Check call status** | `!voice status` | — |
| **Toggle live text transcript mirror** | `!voice text on` / `!voice text off` | — |
| **Leave the voice channel** | `!leave` · `!disconnect` · `!hangup` | *"leave the call"* / *"bye"* |

---

## Web Workspace Commands & Shortcuts

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
| `/new` | Start a fresh chat session |

---

## Running Tests & Production Build

```powershell
ruff check . --select E9,F63,F7,F82
.\.venv\Scripts\python.exe -m pytest -q
npm --prefix frontend run lint
npm --prefix frontend run build
```
