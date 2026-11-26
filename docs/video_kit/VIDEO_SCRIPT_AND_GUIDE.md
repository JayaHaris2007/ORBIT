# ORBIT — Full 4:30 Video Script, Storyboard & Recording Guide

> **Format:** Hybrid 3–5 min Full Demo & How-It-Works Walkthrough (1080p @ 60fps — ideal for YouTube, Portfolio, LinkedIn, or College Project Presentation).
> **Included Assets:**
> - Animated 1080p Slides: `docs/video_kit/orbit_slides.html` (open in Chrome → press `F` for fullscreen → press `H` to hide HUD before recording).
> - Safe Demo-Data Seeder: `scripts/seed_demo_data.py` (backs up your real `assistant.db`, seeds polished showcase data, and restores your original DB with one command afterward).

---

## 1. Pre-Recording Setup (5 Minutes)

### Step A — Seed Polished Showcase Data (Safe Backup Included)
Stop the backend server first so SQLite isn't locked, then run:

```powershell
.\.venv\Scripts\python.exe scripts\seed_demo_data.py --seed
```

*(When you finish recording, restore your real data anytime with `.\.venv\Scripts\python.exe scripts\seed_demo_data.py --restore`.)*

### Step B — Start ORBIT & Open Both Browser Tabs
1. Start ORBIT via `ORBIT Control Center.pyw` (`▶ START ALL`) or:
   - Terminal 1: `.\.venv\Scripts\python.exe app.py --server`
   - Terminal 2: `npm --prefix frontend run dev`
2. Open Chrome in a clean profile (hide bookmarks bar with `Ctrl + Shift + B`):
   - **Tab 1:** `http://localhost:5173` — set browser zoom to **110%–125%** so UI labels and chat text look super crisp on mobile & YouTube.
   - **Tab 2:** `docs/video_kit/orbit_slides.html` (double-click the file or drag into Chrome) — press **`F`** for fullscreen, **`H`** to hide the presenter bar, and use **`→` / `←`** to step through Slides 1–6 (press **`R`** to replay a slide's entrance animation).

### Step C — Recommended OBS Studio Settings
- **Canvas & Output Resolution:** `1920 × 1080` at **60 fps** (or 30 fps if CPU-bound during local Ollama).
- **Audio Tracks:** Record **Mic** on Track 1 and **Desktop Audio** (for ORBIT's Live Voice Phonon TTS replies!) on Track 2 so you can balance volumes cleanly in editing.
- **Mic Filters in OBS:** Add **Noise Suppression (RNNoise)** + **Compressor (-18 dB threshold, 3:1 ratio)** for studio-clean voiceover.
- **Tip:** Record the **Live Demos** first as separate short clips (one clip per scene) and record **Slides 1–6** cleanly, then stitch them together in CapCut / DaVinci Resolve while reading or re-recording your voiceover!

---

## 2. Scene-by-Scene Script & Shot List (~4:30 Total)

### Scene 1 — Hook & Title Intro (`0:00 – 0:25`)
- **Visual:** `orbit_slides.html` — **Slide 1 (`01 // INTRO`)** fullscreen. Let the 3D ASCII waves move for 2 seconds before speaking.
- **Spoken Script:**
  > "Most AI assistants live in the cloud, forget what you're actually working on, and sit completely disconnected from your tasks, habits, and code.
  > *[PAUSE 0.5s]*
  > Meet **ORBIT** — a 100% local personal AI assistant, developer co-pilot, and productivity workspace that runs entirely on your own machine."

---

### Scene 2 — Why "ORBIT"? (`0:25 – 0:50`)
- **Visual:** Press `→` to **Slide 2 (`01 // THE PROBLEM & PHILOSOPHY`)**.
- **Spoken Script:**
  > "Just like a satellite orbits the Earth continuously observing what's happening below, ORBIT orbits around your daily workflow.
  > Instead of juggling six disconnected cloud apps, ORBIT unifies your tasks, daily habits, learning roadmaps, local code folders, reminders, and long-term memory inside one private SQLite database — with zero cloud lock-in."

---

### Scene 3 — Live Workspace & Reactive ASCII UI (`0:50 – 1:35`)
- **Visual:** Switch to **Tab 1 (`http://localhost:5173`)**.
  1. Slowly glide your cursor across the empty Hero canvas so viewers see the **3D ASCII topographic mountains warp** in real time.
  2. Type slowly in the bottom composer bar so viewers see the **QWERTY-spatial mountain plucks & rising ember sparks**:
     - Prompt 1: **`add high priority task ship ORBIT v2 release notes tomorrow`** → Press `Enter` (show the ember scanline sweep + instant `<2 ms` deterministic reply!).
     - Prompt 2: **`what's pending today?`** → Show instant list + click **`Tasks`** in the Top Navbar to prove it synced live into SQLite!
  3. Quickly click **`Habits` → `Analytics`** in the Top Navbar (show the 7-day ASCII streak strips, yearly heatmap, and unified productivity score without even having to close modals first!).
- **Spoken Script:**
  > "Let's see it running live. Everything sits inside one calm Obsidian-and-Ember ASCII workspace — built on a pure 2D HTML5 canvas with zero heavy WebGL bloat. Every keystroke physically plucks the matching column of the 3D terrain.
  > *[TYPE PROMPT 1 & HIT ENTER]*
  > Watch how fast that responded. Common actions like adding tasks, completing habits, or setting reminders hit ORBIT's deterministic command router in under two milliseconds — without even waking up the LLM.
  > *[CLICK TASKS → HABITS → ANALYTICS IN TOP NAVBAR]*
  > And because every module is mounted right in the top bar and synced to the same database, switching from Tasks to daily Habit streaks to unified Productivity Analytics is instant."

---

### Scene 4 — Live Code-Folder RAG & Learning Roadmaps (`1:35 – 2:15`)
- **Visual:** Click **`Learning`** in the Top Navbar → click into the **`C++ with DSA`** roadmap.
  1. Point out the linked local folder (`scratch/demo_code_folder`) and the **Suggest & Confirm** card showing `Control Flow` verified from `while_loop.cpp`!
  2. Click **Confirm** (or switch back to **`Chat`** and type: **`what's ready to learn next?`**) so ORBIT recommends the next unlocked topic.
- **Spoken Script:**
  > "My favorite feature for developers is **Adaptive Learning with Local Code RAG**.
  > You link your actual local practice folder to a study roadmap. ORBIT scans your files using fast modification-time delta checks across C++, Python, React, TypeScript, SQL, Rust, and Go, indexes code chunks into SQLite FTS5, and detects which concepts you've genuinely practiced — ignoring empty or boilerplate files.
  > Here it spotted real loop logic in `while_loop.cpp`, moved Control Flow to in-progress, and surfaced a Suggest-and-Confirm prompt instead of blindly guessing."

---

### Scene 5 — Hands-Free Live Voice Mode (`2:15 – 2:55`)
- **Visual:** Return to **`Chat`**, press **`Ctrl + Space`** (or click **`● live`** in the Top Navbar).
  1. Show the dedicated obsidian **ASCII Harmonic Voice Matrix** reacting live to your voice.
  2. Speak aloud: **"Give me a quick check-in on my habits today."**
  3. Let ORBIT transcribe, stream live captions, and speak back using local **Phonon CPU TTS** (let Desktop Audio be heard clearly!).
  4. Demonstrate pressing **`M`** (mic mute) or clicking the **Mute** button, then press **`Esc`** to exit cleanly.
- **Spoken Script:**
  > "Now let's hit `Control + Space` for hands-free **Live Voice Mode**.
  > *[PAUSE — SPEAK YOUR DEMO QUESTION TO ORBIT & LET ORBIT REPLY OUT LOUD]*
  > Notice two things: first, ORBIT starts speaking almost immediately instead of waiting for the entire paragraph to finish — and second, its speech cleaner strips Markdown and raw file extensions so it sounds like a real partner, not a screen reader. You can mute anytime with `M`, interrupt mid-sentence with `Space`, or exit with `Escape`."

---

### Scene 6 — Universal Ollama Models + Settings Hot-Swap (`2:55 – 3:20`)
- **Visual:** Click **`Settings`** in the Top Navbar → scroll to **`02 // Local Ollama Models`**.
  1. Open the **Active Installed Model** dropdown showing your installed Ollama models + VRAM `[LOADED]` badge.
  2. Point to the **Pull or Switch to Any Ollama Library Tag** box (`llama3.2:3b`, `gemma3:4b`, `deepseek-r1:8b`, `qwen2.5-coder:7b`, `mistral:7b`) and the optional **Gemini BYOK** section right below it.
- **Spoken Script:**
  > "ORBIT works with **every model in Ollama** — Qwen, Llama, Gemma, DeepSeek-R1, Mistral, Phi, or custom GGUFs. You can hot-swap or pull new models right here in Settings with zero server restart. Even if a model doesn't support native tool calling or thinking flags, ORBIT automatically adapts on the fly and injects live workspace context so streaming never breaks. And if you ever want cloud reasoning, you can drop in your own Gemini API key."

---

### Scene 7 — How It Works Under the Hood (`3:20 – 4:10`)
- **Visual:** Switch to **Tab 2 (`orbit_slides.html`)**:
  - **Slide 3 (`02 // ARCHITECTURE` — 20s):** Walk through the 4 stages as the ember highlight pulses across Confirmation Gate → 0ms Router → Memory + Code RAG → Streaming Tool Loop.
  - **Slide 4 (`03 // LIVE VOICE PIPELINE` — 18s):** Point out the latency comparison bar chart (`~40–60% faster first audio`) and the 500 ms pre-roll VAD.
  - **Slide 5 (`04 // CODE RAG & MODELS` — 12s):** Briefly recap zero-read delta scanning + universal model adaptation.
- **Spoken Script:**
  > "Under the hood, every channel — Web Chat, Live Voice, and even the built-in Discord text and voice bot — routes through one unified FastAPI turn orchestrator.
  > *[SLIDE 3]*
  > First comes a confirmation safety gate before any deletion. Second, a sub-2-millisecond deterministic router handles structured commands locally. Third, ORBIT builds bounded context with lexical-concept memory and FTS5 code snippets. Fourth, a streaming native tool loop talks to Ollama over a shared `aiohttp` pool, backed by thread-local SQLite WAL connections.
  > *[SLIDE 4]*
  > In Live Voice Mode, 16-kilohertz PCM streams over WebSockets with a 500-millisecond pre-roll buffer. As tokens arrive from the LLM, an incremental sentence buffer feeds Gradium Phonon CPU TTS concurrently — cutting time-to-first-audio by 40 to 60 percent, while automatically pausing the background ASCII canvas to free CPU cores.
  > *[SLIDE 5]*
  > And on the frontend, lazy-loaded modals and explicit tree-shaken icons keep the whole bundle fast and lightweight."

---

### Scene 8 — *(Optional 15s Bonus Cut)* Desktop Control Center & Discord (`4:10 – 4:25`)
- **Visual:** Show a quick 5-second shot of `ORBIT Control Center.pyw` running (`▶ START ALL` green health pills) — and if you have Discord set up, a 10-second clip typing `!join` and speaking to ORBIT in a server voice channel.
- **Spoken Script:**
  > "Everything launches from one dark Desktop Control Center supervisor — and if you add a Discord token in `.env`, the exact same local brain and voice engine joins your Discord server for text chats and two-way encrypted voice calls."

---

### Scene 9 — Outro & Call to Action (`4:25 – 4:40`)
- **Visual:** **Slide 6 (`05 // OUTRO`)** fullscreen. Hold 3 seconds at the end for fade-out.
- **Spoken Script:**
  > "ORBIT is 100% local, privacy-first, and open source. Clone the repo, pull any Ollama model, and start building with a calmer AI workspace. Link is in the description — thanks for watching!"

---

## 3. Quick Editing Assembly Tips (CapCut / DaVinci Resolve)
- **Background Music:** Subtle dark ambient / lo-fi synth track at **-24 dB to -28 dB** (duck down to `-34 dB` whenever ORBIT speaks in Scene 5).
- **Zoom-Ins:** Add a subtle `110%` slow zoom or punch-in during Scene 3 (typing a prompt) and Scene 4 (the `while_loop.cpp` Suggest & Confirm card) so viewers on phones can read every detail.
- **After Filming — Restore Your Real Data:**
  ```powershell
  .\.venv\Scripts\python.exe scripts\seed_demo_data.py --restore
  ```
