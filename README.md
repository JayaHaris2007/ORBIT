<p align="center">
  <img src="logo.png" alt="ORBIT Logo" width="84" height="84" />
</p>

# ORBIT — Local AI Assistant

**ORBIT** is a 100% local personal AI assistant and productivity workspace featuring a **full-screen interactive 3D Kinetic Topographic ASCII Wave Field**, a **calm navbar-free chat-first interface**, **hands-free Live Voice Mode (`Ctrl + Space`)**, **real-time token streaming** powered by **Ollama (`qwen3.5:4b`)** (or optional Gemini BYOK), **hybrid memory recall**, **adaptive learning roadmaps with local code-folder tracking**, and **Discord integration**.

---

## Key Highlights

- **Interactive 3D ASCII Wave Field Background:** Pure monospace procedural terrain in Obsidian (`#050505`), Burnt Ember Orange (`#D95D24`–`#FFD4A8`), and Bone Cream (`#F2EFE9`) — zero heavy 3D WebGL overhead.
  - **Mouse:** Smooth magnetic ridge swell under the cursor, subtle 3D parallax, wake trails, and click shockwaves.
  - **QWERTY-Spatial Keyboard Physics:** Each key plucks a harmonic ridge wave at its physical keyboard column and releases rising typed-character ember sparks (`char → * → + → ·`); `Space` triggers a wide central breath, `Backspace` pulls a smooth receding valley, and `Enter` sweeps an ember scanline across the horizon.
  - **Voice Reactivity:** Live mic input and spoken replies radiate acoustic waves across the terrain.
- **Calm, Navbar-Free Chat-First Workspace:** Operate everything through natural language or `/` slash commands, with a discreet slide-over chat history drawer (`≡`) and centered floating pop-up modals for every workspace module.
- **Hands-Free Live Voice Mode (`Ctrl + Space`):**
  - Toggle Live Mode from anywhere with **`Ctrl + Space`** (or click **`● live`** / type `/live`).
  - Features a high-contrast **pure ASCII Symmetric Harmonic Voice Matrix** inside a dedicated obsidian frame, Markdown-rendered live captions, expandable session log, and latency stats.
  - Real-time 16 kHz PCM WebSocket streaming with 500 ms pre-roll VAD, automatic speaker echo gating, barge-in / manual **`Space`** interrupt & send-now, and **`M`** mic mute.
  - Clean natural TTS speech that strips file extensions (e.g., `while_loop.cpp` → *"while loop"*) and angle-bracket placeholders automatically.

---

## Features & How They Work

### End-to-End Request Flow

```text
  [ Browser UI: React 19 + Procedural ASCII Canvas ]
       │
       ├── Chat / Slash Commands (SSE: /api/generate/stream)
       ├── Live Voice Mode (WebSocket: /ws/voice · 16kHz PCM <-> WAV)
       └── Pop-Up Modals (REST: /api/tasks, /api/habits, /api/learning, ...)
       │
       ▼
  [ FastAPI Backend (app.py) ]
       ├── 1. Deterministic Command Router (services/command_router.py)
       │      Instant local execution for tasks, habits, learning, reminders, & navigation
       ├── 2. AI Agent & Tool Loop (agent/loop.py + agent/tools.py)
       │      Local Ollama (qwen3.5:4b) or Gemini BYOK + confirmation guard (agent/confirm.py)
       ├── 3. Voice Pipeline (voice/router.py, stt.py, text_clean.py, phonon_engine.py)
       │      Pre-roll VAD -> STT -> Chat Pipeline -> Speech Summarizer -> Sentence WAV stream
       └── 4. Local Storage & Background Jobs (assistant.db + APScheduler)
              SQLite WAL memory/productivity store, code-folder RAG, reminders & proactive coach
```

### 1. Hybrid AI Chat & Deterministic Routing
- **What it does:** Answers questions, writes/debugs code, manages your workspace data, and streams replies token-by-token in real time.
- **How it works:** Every message first passes through a fast local intent router (`services/command_router.py`) that handles structured actions (creating/completing tasks, logging habits, checking pending learning topics, opening pop-ups) immediately without waiting for an LLM. Open-ended requests stream via Server-Sent Events (`/api/generate/stream`) through local **Ollama** (`qwen3.5:4b`) or an optional browser-stored **Google AI Studio Gemini API key** (`agent/gemini.py`). Multi-step tool calls run inside `agent/loop.py` with explicit user confirmation (`agent/confirm.py`) before any destructive action.

### 2. Full-Screen Procedural 3D ASCII Workspace
- **What it does:** Turns the entire viewport into a calm, living Obsidian + Burnt Ember ASCII mountain wave field that reacts to mouse movement, typing, and voice.
- **How it works:** `SpideyAsciiCanvas.jsx` runs a lightweight software 3D projection engine on a standard 2D HTML5 `<canvas>` with a depth buffer (`zBuf`) and color-bucketed monospace rendering (no WebGL/Three.js bundle). Pointer movement applies 3D camera parallax and a Gaussian ridge swell; typing maps each key's physical QWERTY `(x, z)` coordinate to a traveling column string-pluck and a rising character spark (`char → * → + → ·`); pressing `Enter` sweeps a horizontal ember scanline across the terrain.

### 3. Hands-Free Live Voice Mode (`Ctrl + Space`)
- **What it does:** Lets you hold a continuous back-and-forth spoken conversation with ORBIT — complete with live Markdown captions, voice navigation, mute, and mid-sentence interruption.
- **How it works:**
  1. **Capture:** An `AudioWorklet` (`frontend/public/audio-worklet/pcm-capture.js`) downsamples microphone audio to 16 kHz mono 16-bit PCM and streams 100 ms binary frames over `/ws/voice`.
  2. **VAD & Echo Safety:** The backend (`voice/router.py`) maintains a 500 ms rolling pre-roll ring buffer (so silence never bloats STT input and first syllables aren't clipped), detects utterance boundaries via energy VAD, and enforces a 30 s cap. The browser gates mic frames while TTS speakers are active so ORBIT never hears itself.
  3. **STT → Brain → TTS:** Utterances are transcribed (`voice/stt.py`), executed through the unified chat handler, condensed into natural spoken English with file extensions and placeholders stripped (`voice/text_clean.py`), and synthesized sentence-by-sentence via Gradium Phonon CPU TTS (`voice/phonon_engine.py`, with Windows SAPI fallback) back to the browser's `AudioQueue`.
  4. **Visuals & Controls:** `LiveOverlay.jsx` renders a 100% pure ASCII Symmetric Harmonic Voice Matrix driven directly by real-time mic RMS and TTS analyser levels, with `M` to mute, `Space` to send/interrupt, and `Ctrl + Space` or `Esc` to exit.

### 4. Adaptive Learning Roadmaps & Local Code-Folder Tracking (Code RAG)
- **What it does:** Tracks multi-topic study roadmaps with prerequisite unlocking, automatically notices when you've practiced a topic in your local code folder, and lets you search your own code snippets.
- **How it works:** Roadmaps and topic prerequisite graphs live in SQLite (`learning/roadmaps.py`, `learning/progress.py`). When you link a local folder in a roadmap pop-up, `learning/code_rag.py` indexes your source files locally, maps files (such as `while_loop.cpp` or `if_else.cpp`) to matching roadmap topics, powers hybrid snippet search, and feeds proactive nudges (`learning/nudges.py`) asking if you'd like to mark completed topics done and roll into the next unlocked topic.

### 5. Tasks, Daily Habits, Streaks & Analytics
- **What it does:** Manages prioritized to-dos, recurring daily habits, streaks, XP, and a unified productivity dashboard — controllable either in chat/voice or inside floating pop-up modals.
- **How it works:** All items are stored locally in `assistant.db` (`memory.py`, `routers/productivity.py`). Natural-language parsers (`services/productivity_parsers.py`) let you say *"add high priority task submit report"* or *"mark exercise done"*, instantly updating SQLite and broadcasting `orbit:refresh` UI events so open modals and `/analytics` (Total Productivity %, per-roadmap completion, streaks, and yearly heatmap) stay synced automatically.

### 6. Scheduled Reminders, Hybrid Memory & Proactive Coaching
- **What it does:** Remembers personal facts/notes you share, fires scheduled one-time or recurring reminders, and sends occasional friendly check-ins about pending goals.
- **How it works:** Memories are indexed with built-in hybrid lexical-concept recall in `memory.py` (no PyTorch or external vector database required). `APScheduler` runs scheduled reminder triggers (`services/reminders.py`) and cooldown-guarded proactive check-ins (`services/proactive_coach.py`), delivering notifications into the active chat stream and optionally speaking them aloud when TTS is enabled.

### 7. Live Web Research
- **What it does:** Searches the live web when you ask about current events, documentation, or external topics and returns concise, plain-English summaries with source citations.
- **How it works:** `research/search_engine.py` executes rate-limited web queries (`research/rate_limit.py`, supporting Tavily when `TAVILY_API_KEY` is configured) and passes retrieved snippets through ORBIT's summarizer while treating web content as untrusted data.

### 8. Discord Text & Voice Bot (Optional)
- **What it does:** Brings ORBIT into your Discord server for both text messages and two-way voice channel conversations.
- **How it works:** `discord_bot.py` and `services/discord_voice.py` connect via `AI_DISCORD_TOKEN`, capture guild voice streams with speaker-echo protection, and route every message or spoken turn through the exact same local brain, memory, STT, and TTS pipeline as the web app.

---

## Required Software & Exact Versions

Verified working environment:

| Software | Tested / Exact Version | Minimum Supported | Download |
|----------|------------------------|-------------------|----------|
| **Python** | **Python 3.15.2** | Python 3.11+ (`3.14` / `3.15.2`) | [python.org](https://www.python.org/downloads/) |
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

- **LLM Brain:** Local [Ollama](https://ollama.com) (`qwen3.5:4b`, native tool calling + SSE token streaming) + optional Google AI Studio Gemini BYOK in Settings
- **Voice TTS:** Gradium Phonon (`phonon-31m-en` via `ptts` on CPU) with automatic Windows SAPI fallback
- **Voice STT:** Local Whisper / `SpeechRecognition` over WebSocket (`/ws/voice`) with rolling pre-roll VAD & barge-in
- **Backend:** Python FastAPI, SQLite (WAL mode), APScheduler, built-in hybrid lexical-concept memory (no PyTorch or embedding model required)
- **Frontend:** React 19, Vite, Tailwind CSS v4, Canvas 2D Procedural ASCII Engine, Framer Motion

---

## Step-by-Step Setup (Clone → Install → Run)

### 1. Clone the Repository (`master` branch)

```powershell
git clone https://github.com/JayaHaris2007/ORBIT007.git
cd ORBIT007
```

### 2. Install & Start Ollama (`0.40.16`)

Install [Ollama](https://ollama.com), then pull the default local model and start the service:

```powershell
ollama pull qwen3.5:4b
ollama serve
```

### 3. Create Python Virtual Environment & Install `requirements.txt`

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

Launch the desktop supervisor GUI to start, monitor, and manage Ollama, the backend API, and the frontend dev server in one window:

- **Double-click** `Spidey Control Center.pyw` (or `start.bat`), **or** run:

```powershell
.\.venv\Scripts\pythonw.exe spidey_launcher.py
```

The **Control Center** provides:
1. **Global Controls:** `▶ START ALL`, `■ STOP ALL`, `↻ RESTART`, and `↗ OPEN WEB UI` (`http://localhost:5173`).
2. **Service Cards & Health Checks:** Live status for Ollama (`127.0.0.1:11434`), Backend API (`127.0.0.1:8000`), and Web Frontend (`http://localhost:5173`).
3. **Live Configuration Strip (`.env`):** Edit `OLLAMA_MODEL`, `LLM_BACKEND` (`ollama` / `gemini`), `TTS_BACKEND` (`phonon` / `sapi`), proactive `COACH (MIN)` interval, `Auto-open browser`, and trigger `Run Tests` (`pytest`) directly from the GUI.
4. **Tabbed Live Log Console & Clean Shutdown:** Real-time logs across services and clean process-tree termination on exit.

*(For legacy multi-terminal batch mode, run `.\start.bat --cli`.)*

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

## Workspace Commands & Pop-Up Modules

Everything opens calmly as a floating pop-up modal via chat or slash commands:

| Slash Command | Route | Module | What It Does |
|---------------|-------|--------|--------------|
| `/tasks` | `/todos` | **Tasks** | Priority task management with search, filters, due dates, and AI-driven updates |
| `/habits` | `/habits` | **Habits** | Create, edit, and track daily habits, streaks, and XP |
| `/learning` | `/learning` | **Learning** | Calm roadmap pop-up with step-by-step topics, prerequisites, AI suggestions, and local code-folder tracking |
| `/reminders` | `/reminders` | **Reminders & Memory** | Scheduled reminders (one-time & recurring) + long-term semantic memories |
| `/analytics` | `/analytics` | **Analytics** | Total Productivity %, per-roadmap learning progress, streaks, yearly heatmap, and charts |
| `/settings` | `/settings` | **Settings** | Theme selection, profile, Gemini BYOK key, notifications, and full SQLite database reset |
| `/live` | — | **Live Voice Mode** | Toggle continuous hands-free voice conversation (also **`Ctrl + Space`**) |
| `/orbit` | — | **ORBIT007 Agent** | Open the dedicated ORBIT007 Live Agent pop-up |
| `/new` | `/` | **New Chat** | Start a fresh conversation |
| `/chat` | `/` | **Return to Chat** | Close any open pop-up modal (`Esc` also closes pop-ups) |

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl + Space` | Toggle **Live Voice Mode** from anywhere (including inside the chat box) |
| `M` *(in Live Mode)* | Mute / unmute microphone |
| `Space` *(in Live Mode)* | Send spoken audio immediately while listening, or interrupt ORBIT while speaking/thinking |
| `Esc` | Close active Live Mode, pop-up modal, or chat history drawer |
| `/` | Open slash command suggestions in the composer |

---

## Running Tests & Production Build

**Run the Python test suite:**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

**Lint and build the frontend for production:**

```powershell
Set-Location frontend
npx eslint src
npm run build
```
