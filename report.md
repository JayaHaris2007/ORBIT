# ORBIT — Brand, Design System, Agent Architecture & Landing Page Blueprint

> A complete reference covering ORBIT's visual identity, Obsidian + Burnt Ember ASCII design system, interactive procedural motion, local-first AI agent capabilities, and a ready-to-build landing page specification.

---

## 1. Brand Identity

| Attribute | Specification |
|-----------|---------------|
| **Product Name** | **ORBIT** |
| **Tagline / Descriptor** | `ORBIT // Neural OS` — *Your 100% local personal AI assistant, developer co-pilot, and calm productivity workspace.* |
| **Voice & Tone** | Calm, direct, practical, warm, slightly witty — talks like a sharp close friend and engineering partner. Never robotic, never cluttered, never spammy. |
| **Core Philosophy** | **Calm power over visual noise.** Zero heavy navbars, zero generic SaaS glass-blobs, zero cloud lock-in. Everything lives inside one serene chat-first canvas framed by procedural ASCII physics. |
| **Logo Assets** | Circular obsidian core (`#000000`) with 7 white orbital rings (`#FFFFFF`) and a radiant burnt-orange sun + 7 orbiting planets (`#FF6F00`). Available in `logo.svg`, `logo.png` (circular alpha mask), `frontend/public/logo.svg`, `frontend/public/logo.png`, `frontend/public/favicon.ico`, and `orbit.ico`. |
| **Logo Usage Rule** | Render **clean and crisp without artificial outer glow shadows or extra border rings** — let the circular obsidian-and-orange orbital mark stand cleanly on dark surfaces. |

---

## 2. Theme & Design System (Obsidian + Burnt Ember ASCII)

### 2.1 Color Palette & Tokens

| Token / Role | Hex / RGBA | Usage |
|--------------|------------|-------|
| `--color-background` (Deep Obsidian) | `#050505` / `#060606` | Full-bleed viewport canvas, code blocks, dark input fields |
| `--color-surface` (Warm Charcoal) | `#0A0908` / `#0D0C0B` | Floating modals, `.ascii-frame` panels, drawers, Live Mode header/footer |
| `--color-surfaceHighlight` (Elevated Ash) | `#120B07` / `#161412` | User chat bubbles, hover states, active cards |
| `--color-primary` (Burnt Ember) | `#D95D24` | Primary CTAs, active pills, `.ascii-frame` corner brackets, list markers, active accents |
| `--color-secondary` (Ember Glow) | `#E87D42` / `#FF944D` | Active labels, live transcripts, interactive wave crests, telemetry numbers |
| Incandescent Highlight | `#FFD4A8` | Peak ASCII terrain ridges, active voice energy crests, alert highlights |
| `--color-text` (Bone Cream) | `#F2EFE9` | Primary headings, chat responses, high-contrast UI labels |
| Secondary Cream | `#CFC9BF` / `#A8A096` | Body copy, quick hints, secondary buttons |
| `--color-textMuted` (Warm Stone) | `#8E867D` / `#6E675F` | Captions, timestamps, metadata, subtle placeholders |
| Hairline Borders | `rgba(242, 239, 233, 0.12)` – `0.16` | Crisp 1px architectural card & input borders |
| Active Ember Border | `rgba(217, 93, 36, 0.45)` – `1.0` | Focused composer, user messages, hover highlights |

#### ASCII Terrain Luminance Ramp (`SpideyAsciiCanvas.jsx`)
- **Valleys & Slopes (Deep Ash → Bone Cream):**
  `#171513`, `#23201d`, `#332f2a`, `#48423c`, `#635b53`, `#857c72`, `#b0a79d`, `#e5dfd6`
- **Crests & Active Energy (Deep Ember → Incandescent Highlight):**
  `#4d1f0b`, `#752d0f`, `#9e3e15`, `#c44f1c`, `#d95d24`, `#f27029`, `#ff944d`, `#ffd4a8`
- **Sky Coordinate Markers (`+` / `·`):**
  `#141210`, `#1f1c19`, `#4a210f`

### 2.2 Typography

| Role | Font Family | Weights | Styling Rules |
|------|-------------|---------|---------------|
| **UI & Prose (`--font-sans`)** | `'Space Grotesk', system-ui, sans-serif` | 400, 500, 600, 700 | Clean modern geometric sans for chat replies, descriptions, and modal content (`14px`–`15px`, line-height `1.65`–`1.7`). |
| **Technical, HUD & ASCII (`--font-mono`)** | `'JetBrains Mono', 'Cascadia Code', Consolas, monospace` | 400, 500, 600, 700 | Wide-tracked uppercase labels (`tracking-[0.14em]` to `tracking-[0.42em]`), slash commands, buttons (`[tts:on]`, `[● live]`, `[end live · ctrl+space]`), section indices (`01 //`), and all canvas ASCII grids. |

### 2.3 Architectural Surface Language

- **Sharp 0px Geometry (`border-radius: 0px`):** Deliberate terminal-editorial precision — crisp rectangular cards, inputs, and buttons (only the ORBIT logo mark and live indicator dots are circular).
- **Signature `.ascii-frame` Corner Crosshairs:** Every major card and modal uses a hairline `1px` bone border (`rgba(242, 239, 233, 0.12)`) accented by `7px × 7px` burnt-ember (`#D95D24`) corner brackets at top-left and bottom-right.
- **Crisp Top Navbar + Calm Canvas Layout (`TopNavbar.jsx`):**
  - Top bar (`h-12`, `#070606/92`): chat drawer toggle (`≡`) + ORBIT brand on the left; direct one-click tabs for **every core section** (`Chat`, `Tasks`, `Habits`, `Reminders`, `Learning`, `Analytics`, `Settings`) in the center; and dedicated **Mute** (`MuteButton` for speaker TTS + microphone mute during Live Mode) + **`● Live`** controls on the right.
  - Center: floating hero stage or calm scrollable conversation stream.
  - Bottom: single floating composer bar (`Ask ORBIT anything… or type /`) with `Mute`, `Mic Mute` (in Live Mode), `● Live`, and `Send`.
  - Secondary modules open as **centered floating pop-up modals** directly below the Top Navbar so users can switch between any section in a single click or dismiss with `Esc`.
- **Editorial Markdown Rendering (`.assistant-message`):** Square burnt-orange (`#D95D24`) bullet markers, dark inline code pills (`#171310` with subtle ember border and `#F2B58F` text), and clean obsidian code blocks (`#060606`).

### 2.4 Procedural ASCII Visuals & Motion Signature

- **3D Kinetic Topographic ASCII Wave Field (Background):**
  - Pure 2D HTML5 `<canvas>` with depth-buffer (`zBuf`) projection and color-bucketed character rendering — **zero Three.js / WebGL bloat**.
  - Elevation glyph ramp: `.` → `:` → `-` → `=` → `/` → `^`.
  - **Mouse interaction:** Silky 3D camera parallax, Gaussian magnetic ridge swell under cursor, wake trails, and click shockwaves.
  - **Keyboard physics:** Physical QWERTY `(x, z)` mapping plucks directional harmonic waves along the matching mountain column and releases rising character ember sparks (`char → * → + → ·`); `Space` sends a calm central ridge breath; `Backspace` pulls a receding valley; `Enter` sweeps an ember transmission scanline front-to-back across the horizon.
  - **Voice reactivity:** Mic RMS and TTS audio levels radiate soft concentric acoustic waves across the terrain.
  - **Zero-Idle CPU Gating:** Automatically pauses `requestAnimationFrame` via `IntersectionObserver`, `document.hidden`, and overlay state (`paused` prop when occluded by `LiveOverlay`) so background physics never compete with CPU-bound local LLM/TTS inference.
- **Live Voice Mode ASCII Matrix (`LiveOverlay.jsx`):**
  - Dedicated solid `#060606` `.ascii-frame` stage over a darkened scrim (`bg-[#050505]/86 backdrop-blur-[5px]`) so visuals never blend into the background.
  - Exports reusable `LiveVoiceWave` rendering a dense symmetric harmonic wave matrix (` .:-=+*#%@`) in warm ash/cream and burnt ember across `CONNECTING`, `LISTENING`, `MUTED`, `TRANSCRIBING`, `THINKING`, and `SPEAKING`.
- **UI Motion Curve:** Crisp, restrained Framer Motion transitions (`duration: 0.18–0.22s`, cubic-bezier `[0.22, 1, 0.36, 1]`). Respects `prefers-reduced-motion`.

---

## 3. All About the ORBIT Agent

### 3.1 Core Architecture

- **100% Local-First Execution & Universal Ollama Support:** Runs completely on the user's machine with **any Ollama model** (default `qwen3.5:4b`, plus `llama3.2`, `gemma3`, `deepseek-r1`, `mistral`, `phi4`, `qwen2.5-coder`, and custom GGUFs — auto-adapting `tools` and `think` capabilities per model and supporting zero-restart hot-swapping/pulling via `/api/ollama/select` & `/api/ollama/pull`), thread-local persistent **SQLite WAL + FTS5** (`assistant.db`), **Gradium Phonon CPU neural TTS** (`phonon-31m-en`, with Windows SAPI fallback), and local **Whisper / SpeechRecognition STT**.
- **Optional Cloud Upgrade (BYOK) & Portable Identity:** Users can optionally drop a **Google AI Studio Gemini API key** in Settings (stored only in browser `localStorage`), connect **Tavily** for live web search, or attach a **Discord Bot Token** (`AI_DISCORD_TOKEN`) for text and DAVE-encrypted two-way server voice channels. User identity resolves dynamically from `ORBIT_USER_NAME` or saved profile memories (zero hardcoded names).
- **Unified Four-Stage Turn Orchestrator (`services/turn_orchestrator.py`):**
  Shared across HTTP `/api/generate`, SSE `/api/generate/stream`, `/ws` Live Agent, and `/ws/voice`:
  1. **Confirmation Gate (`agent/confirm.py`):** Intercepts pending yes/no confirmations before any destructive delete executes.
  2. **0 ms Deterministic Command Router (`services/command_router.py`):** Executes tasks, habits, learning queries, reminders, greetings, and UI navigation instantaneously with cross-domain intent guards.
  3. **Context & Follow-Up Resolution (`memory.py` + `services/llm.py`):** Builds bounded conversation history, resolves short follow-ups (*"why?"*, *"name one"*), and injects lexical-concept memories + Code RAG snippets.
  4. **Streaming Native Tool-Calling Loop (`agent/loop.py` + `agent/tools.py`):** Streams tokens over a shared `aiohttp.ClientSession` pool and validates every tool call with RapidFuzz entity resolution.
- **Hardened Local & LAN Security:** `/tts/*` audio artifacts are guarded by `ORBIT_API_TOKEN`, and WebSockets authenticate via `Sec-WebSocket-Protocol` (`orbit-token.*`) so tokens never leak into server URL access logs.

### 3.2 Feature Matrix

| Pillar | Capabilities | How Users Trigger It |
|--------|--------------|----------------------|
| **Live Voice Mode** | Continuous 16 kHz PCM WebSocket conversation (`/ws/voice`), 500 ms pre-roll VAD, echo gating, **concurrent sentence-by-sentence streaming Phonon TTS** (~40–60% faster first audio), live `reply_partial` captions, barge-in (`Space`), and mic mute (`M`). | Press **`Ctrl + Space`**, click **`● live`**, or type `/live` |
| **Adaptive Learning & Code RAG** | Structured study roadmaps with prerequisite trees, fast `mtime + size` zero-read delta scans (`learning/code_rag.py`) across **C++, Python, Java, React/JSX, TypeScript, REST APIs, SQL, Rust, and Go**, FTS5 snippet search, and Suggest & Confirm completion nudges. | Chat (*"what's pending to learn next?"*), `/learning` |
| **Tasks & Daily Habits** | Prioritized to-dos, due dates, daily recurring habits, 7-day ASCII streak strips, XP gamification, and real-time `orbit:refresh` modal synchronization. | Chat (*"add high priority task…"*), `/tasks`, `/habits` |
| **Reminders & Hybrid Memory** | One-time & recurring `APScheduler` reminders, built-in lexical-concept long-term memory recall (zero PyTorch or external vector DB required), and cooldown-guarded proactive coaching check-ins. | Chat (*"remind me at 7pm…"*), `/reminders` |
| **Analytics & Telemetry** | Unified Total Productivity %, per-roadmap learning progress, habit streaks, yearly heatmap, and visual charts. | Chat (*"open analytics"*), `/analytics` |
| **Live Web Research** | Rate-limited live web search with plain-English cited summaries (`research/search_engine.py`). | Ask any live/web question in chat or voice |
| **ORBIT Live Agent & Discord** | Dedicated `/orbit` live agent modal + in-process Discord text, DM, and DAVE-encrypted two-way server voice channel bot (`!join`, `!stop`, `!leave`, `!notify here`). | `/orbit` or configure `AI_DISCORD_TOKEN` |
| **Desktop Control Center** | One-window dark supervisor GUI (`Spidey Control Center.pyw`) to start/stop/restart Ollama, FastAPI, and Vite, monitor health, edit `.env`, stream logs, run `pytest`, and cleanly shut down process trees. | Double-click `Spidey Control Center.pyw` |

---

## 4. Landing Page Blueprint (Ready to Build)

Use this blueprint to build a high-impact **ORBIT** landing page (`LandingPage.jsx` or standalone marketing site) that feels like stepping directly into ORBIT itself.

### 4.1 Design Direction & Non-Negotiables
- **Same Obsidian + Burnt Ember ASCII DNA:** Background `#050505` with the live **3D Kinetic Topographic ASCII Wave Field** running behind the Hero (interactive with visitor's mouse immediately on page load!).
- **Zero Generic AI Tropes:** No purple/blue gradient blobs, no rounded bubbly SaaS cards, no stock 3D robots. Use crisp `0px` `.ascii-frame` cards, `Space Grotesk` display headlines, `JetBrains Mono` technical eyebrows (`01 // LOCAL_FIRST`), and burnt-ember `#D95D24` highlights.
- **Clean Logo Presentation:** Circular ORBIT logo mark (`logo.svg` / `logo.png`) rendered crisp with **no outer glow shadow**.

### 4.2 Section-by-Section Layout & Copy Deck

#### Section 0 — Minimal Floating Header
- **Left:** Circular ORBIT logo (`28px`, no glow) + `ORBIT` (`JetBrains Mono`, `tracking-[0.26em]`, `#F2EFE9`).
- **Center (Desktop only, ultra-quiet monospace links):** `Features` · `Live Voice` · `Architecture` · `Local First`
- **Right:** Two crisp sharp buttons:
  - Secondary: `[github]` (ghost hairline border)
  - Primary: `Launch Workspace →` (solid `#D95D24`, text `#060606`)

#### Section 1 — Full-Viewport Interactive ASCII Hero (`min-h-[92dvh]`)
- **Background:** Full-bleed interactive **3D Topographic ASCII Wave Field** (`SpideyAsciiCanvas`) with subtle radial dark vignette so hero copy stays razor-sharp. Visitors moving their mouse immediately warp the ASCII mountains.
- **Eyebrow Badge:** `● 100% LOCAL · OLLAMA + PHONON TTS · ZERO CLOUD LOCK-IN`
- **Headline (`Space Grotesk`, 56px–76px, tight tracking):**
  > **A calmer local AI**
  > **built for how you actually work.**
- **Subheadline (`18px`, `#A8A096`, max-w-2xl):**
  > ORBIT unites a private local LLM, hands-free Live Voice Mode, adaptive coding roadmaps, tasks, habits, and long-term memory inside one serene, keyboard-driven ASCII workspace.
- **CTA Row:**
  - Primary (`#D95D24`): `Open ORBIT →`
  - Secondary (`border-[#F2EFE9]/20`): `Try Live Demo` (or `View Setup Guide`)
- **Interactive Micro-Prompt Strip (below CTAs):**
  - A live mock composer bar (`Ask ORBIT anything… or type /`) where typing actually triggers the **QWERTY-spatial terrain plucks & rising ember sparks** right on the landing page!

#### Section 2 — Value Strip (4-Column Monospace Telemetry Bar)
Four crisp hairline-divided cells inside a single `.ascii-frame` strip:
- `01 // PRIVACY` — **100% Local SQLite + Ollama** *(optional Gemini BYOK)*
- `02 // VOICE` — **`Ctrl + Space` Live Mode** *(16 kHz PCM · VAD · Barge-in)*
- `03 // LEARNING` — **Code-Folder RAG** *(tracks real files to roadmap topics)*
- `04 // INTERFACE` — **Zero-Navbar ASCII OS** *(operate everything via chat or `/`)*

#### Section 3 — Interactive Live Voice Mode Showcase (`02 // HANDS_FREE_VOICE`)
- **2-Column Asymmetric Split:**
  - **Left (Story & Controls):**
    - Eyebrow: `02 // LIVE_VOICE_MODE`
    - Headline: **Press `Ctrl + Space`. Just talk.**
    - Body: Continuous two-way voice over local WebSockets with 500 ms pre-roll VAD, automatic speaker echo gating, natural speech cleanup (no awkward `.cpp` file extensions read aloud), and instant `Space` barge-in.
    - Keycap Legend Pills: `[ctrl+space] toggle` · `[m] mute` · `[space] interrupt` · `[esc] exit`
  - **Right (Live Animated Preview):**
    - Embedded solid `#060606` `.ascii-frame` card running an **interactive preview of the pure ASCII Symmetric Harmonic Voice Matrix** (` .:-=+*#%@`) paired with a clean Markdown caption bubble showing a realistic ORBIT exchange (*"What's ready to learn next?"* → formatted Control Flow / Functions bullet list).

#### Section 4 — Core Capabilities Bento Grid (`03 // WORKSPACE_MODULES`)
Six crisp `.ascii-frame` cards (`bg-[#0A0908]`, hover border `#D95D24/60`, 2×3 grid on desktop):
1. **`/learning` — Adaptive Roadmaps & Code RAG:** Link your local practice folder; ORBIT matches files like `while_loop.cpp` to roadmap topics, searches your snippets, and nudges you into the next unlocked module.
2. **`/tasks` & `/habits` — Frictionless Execution:** Manage priorities, due dates, daily streaks, and XP by typing naturally, speaking in Live Mode, or popping open calm modals.
3. **`/reminders` — Hybrid Memory & Proactive Coach:** Built-in lexical-concept recall with zero heavy vector DBs, paired with scheduled reminders and subtle, non-robotic check-ins.
4. **`/analytics` — Unified Productivity Telemetry:** Real-time Total Productivity %, per-roadmap completion rings, streaks, and a yearly contribution heatmap.
5. **Hybrid Local + BYOK Intelligence:** Instant deterministic routing for workspace commands, SSE token streaming via local Ollama (`qwen3.5:4b`), and optional Gemini BYOK in Settings.
6. **Desktop Control Center & Discord:** Manage Ollama, FastAPI, and Vite from one dark GUI supervisor — or bring ORBIT into Discord text & voice channels.

#### Section 5 — "Chat-First, Zero-Clutter" Command Showcase (`04 // SLASH_WORKFLOW`)
- **Visual:** Interactive split terminal card where clicking `/tasks`, `/learning`, `/live`, `/analytics`, or `/reminders` previews the corresponding calm Obsidian pop-up mockup and shows how ORBIT routes natural language vs slash commands instantaneously.
- **Copy:** *"No 14-tab sidebars. No notification chaos. Stay in flow over a living ASCII canvas — summon any module only when you need it, dismiss it with `Esc`."*

#### Section 6 — Local-First Architecture & Tech Stack (`05 // UNDER_THE_HOOD`)
- Include the clean **ASCII End-to-End Architecture Diagram** (`Browser ASCII Canvas` → `FastAPI Router + Agent Loop + Voice WS` → `Ollama / SQLite WAL / Phonon TTS`).
- Compact stack badges in monospace: `React 19` · `Vite` · `Tailwind v4` · `FastAPI` · `SQLite WAL` · `Ollama qwen3.5:4b` · `Phonon CPU TTS` · `APScheduler`.

#### Section 7 — Quick-Start Terminal Block & Final CTA (`06 // RUN_LOCALLY`)
- Copyable 3-step terminal card (`.ascii-frame`):
  ```bash
  git clone https://github.com/JayaHaris2007/ORBIT007.git
  ollama pull qwen3.5:4b
  python app.py --server  # or launch the Control Center GUI
  ```
- **Final CTA Headline:** *Own your assistant. Keep your calm.*
- **Buttons:** `Open Workspace →` + `Read README`

#### Section 8 — Minimal Footer
- Hairline top border (`border-[#F2EFE9]/10`), circular ORBIT logo + `ORBIT // Neural OS`, version/status indicator (`● 100% local runtime`), and copyright line (`© 2026 ORBIT`).

---

## 5. Implementation Status & Architecture Upgrades

- **Modular Workspace & Bundle Optimization:**
  - `SpideyWorkspace.jsx` is decomposed into `TopNavbar.jsx`, `ChatHistoryDrawer.jsx`, `ConversationStream.jsx`, and `ComposerBar.jsx`, preventing Markdown stream re-renders while typing, with `React.lazy` code-splitting across all section modals and `LiveOverlay`.
  - Removed legacy `LandingPage`, `OrbitAgentView`, and `Overview` in-app routes so the web app stays a pure, focused workspace (`Chat`, `Tasks`, `Habits`, `Reminders`, `Learning`, `Analytics`, `Settings`), while keeping Section 4 above as a standalone external marketing site specification if ever needed separately.
  - Replaced wildcard Lucide barrel imports in `HabitCard.jsx` with explicit icon imports, shrinking `icons-vendor.js` by **98.5% (`586.79 KB` → `8.61 KB`, `3.47 KB` gzip)** and removing ~240 KB of dead/duplicate components.

---

## 6. Before vs. After Engineering Comparison

| Dimension | Previous Architecture | Current Architecture | Impact |
|-----------|-----------------------|----------------------|--------|
| **Live Voice First-Audio Latency** | Waited for full LLM response before TTS synthesis | Concurrent sentence-by-sentence streaming into Phonon TTS + `reply_partial` captions | **~40–60% faster** spoken response onset |
| **Canvas CPU Scheduling** | Background & overlay ASCII canvases ran 60 FPS simultaneously | `SpideyAsciiCanvas` auto-pauses behind `LiveOverlay`, hidden tabs, & off-screen scroll | Frees CPU cores during local Ollama + Phonon inference |
| **Frontend Icon Bundle** | `586.79 KB` (`155.77 KB` gzip) wildcard `lucide-react` chunk | `6.70 KB` (`2.85 KB` gzip) explicit icon map + lazy-loaded overlays | **-98.8% (`-580 KB`)** smaller icon bundle, zero build warnings |
| **Workspace Render Isolation** | 1,283-line monolith re-rendered chat stream per keystroke | Memoized `ConversationStream`, `ComposerBar`, & `ChatHistoryDrawer` | Zero input lag in long Markdown conversations |
| **SQLite & HTTP Transport** | Opened/PRAGMA'd/closed SQLite per query; new `ClientSession` per round | Thread-local persistent WAL connections + shared `aiohttp.ClientSession` | Lower I/O & socket overhead across multi-tool turns |
| **Turn Pipeline Consistency** | 3 duplicated turn flows across HTTP, `/ws`, and `/ws/voice` | Single `services/turn_orchestrator.py` across all channels | Identical short follow-ups, memory recall, & confirmations |
| **Code RAG Indexing** | Full byte-read + SHA-256 on every file; C++/Python/Java focus | Zero-read `mtime + size` skip + React, TS, REST, SQL, Rust, Go, & Python rules | Near-instant background syncs across full-stack & systems repos |
| **Auth & Repo Portability** | Unprotected `/tts/*`, `?token=` in WS URL logs, hardcoded `"Jaya's"` prompt | Protected `/tts/*`, `Sec-WebSocket-Protocol` WS auth, dynamic user name | Safe LAN token auth & clean multi-user open-source portability |
