# S.P.I.D.E.Y. (ORBIT007) — Local AI Assistant

S.P.I.D.E.Y. is a 100% local personal AI assistant and productivity workbench featuring a **Three.js 3D Neural Core**, a **Swiss-editorial pen-plotter interface**, **real-time token streaming** powered by **Ollama (`qwen3.5:4b`)**, **continuous hands-free voice discussion**, **semantic memory**, and **Discord integration**.

---

## Prerequisites & Tech Stack

- **Python:** **Python 3.11 – 3.15** (Recommended: **Python 3.14** on Windows for prebuilt wheels of `torch`, `pydantic-core`, `numpy`, and `regex`; Python `3.15` is also supported)
- **Node.js:** **Node.js 18+** (with `npm`)
- **LLM Brain:** Local [Ollama](https://ollama.com) (`qwen3.5:4b`, native tool calling + token streaming)
- **Voice TTS:** Gradium Phonon (`phonon-31m-en` via `ptts` on CPU) with automatic Windows SAPI fallback
- **Voice STT:** Local Whisper / `SpeechRecognition` with continuous VAD & barge-in support
- **Backend:** Python FastAPI, SQLite (WAL mode), APScheduler, `sentence-transformers` semantic memory
- **Frontend:** React 19, Vite, Tailwind CSS v4, Three.js (3D Particle Sphere), Framer Motion

---

## Step-by-Step Setup (Clone → Install → Run)

### 1. Clone the Repository

```powershell
git clone <your-repository-url> Spidey
cd Spidey
```

### 2. Install & Start Ollama

Install [Ollama](https://ollama.com), then pull the default local model:

```powershell
ollama pull qwen3.5:4b
ollama serve
```

### 3. Create Python Virtual Environment & Install `requirements.txt`

Requires **Python 3.11+** (**Python 3.14** recommended on Windows; **Python 3.15** also supported). Check your version first:

```powershell
python --version
```

Create `.venv` and install all dependencies from `requirements.txt`:

```powershell
python -m venv .venv
# Or to target Python 3.14 explicitly on Windows: py -3.14 -m venv .venv

.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 4. Install Frontend Dependencies

```powershell
npm --prefix frontend install
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
.\.venv\Scripts\python.exe -m ptts --lang en --quant q8 --voice Easton "Hello from Spidey" -o test.wav
```

---

## How to Run the Program

### Option A: One-Click Windows Launcher (Recommended)

Run `start.bat` from the project root:

```powershell
.\start.bat
```

`start.bat` automatically:
1. Activates `.venv`
2. Starts `ollama serve` in the background (if not already running)
3. Starts the **FastAPI Backend** on `http://127.0.0.1:8000`
4. Starts the **Vite Frontend** on `http://localhost:5173`

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

## Core Workspace Sections

| # | Route | Section | What It Does |
|---|-------|---------|--------------|
| `01` | `/dashboard` | **Command Center** | 3D Three.js Neural Core + personal telemetry matrix, daily habits, priority tasks, task editor, and Focus Mode |
| `02` | `/habits` | **Habits** | Create, edit, and track daily habits, streaks, and XP |
| `03` | `/todos` | **Tasks** | Priority task management with search, filters, due dates, and AI-driven updates |
| `04` | `/reminders` | **Reminders & Memory** | Scheduled reminders (one-time & recurring) + long-term semantic memories |
| `05` | `/learning` | **Learning** | Structured study roadmaps, topic status tracking, and AI study suggestions |
| `06` | `/analytics` | **Analytics** | Weekly completion rates, streaks, yearly heatmap, and monthly/weekday charts |
| `07` | `/settings` | **Settings** | Theme selection (Dark / Midnight / Light), profile, notifications, and data controls |

---

## Running Tests & Production Build

**Run the Python test suite:**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

**Build the frontend for production:**

```powershell
npm --prefix frontend run build
```
