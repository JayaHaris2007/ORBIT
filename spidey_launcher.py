"""S.P.I.D.E.Y. Desktop Control Center — GUI front end to start, monitor, and manage all services."""

from __future__ import annotations

import json
import os
import queue
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"
ENV_EXAMPLE_PATH = BASE_DIR / ".env.example"
LOGS_DIR = BASE_DIR / "logs"

OLLAMA_HOST = "127.0.0.1"
OLLAMA_PORT = 11434
BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8000
FRONTEND_HOST = "127.0.0.1"
FRONTEND_PORT = 5173
FRONTEND_URL = f"http://localhost:{FRONTEND_PORT}"

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


def resolve_python_executable(base_dir: Path = BASE_DIR) -> str:
    """Return the project's virtual environment Python executable, or sys.executable."""
    candidates = [
        base_dir / ".venv" / "Scripts" / "python.exe",
        base_dir / "venv" / "Scripts" / "python.exe",
        base_dir / ".venv" / "bin" / "python",
        base_dir / "venv" / "bin" / "python",
    ]
    for path in candidates:
        if path.is_file():
            return str(path)
    return sys.executable


def resolve_npm_executable() -> str | None:
    """Locate npm executable on Windows/POSIX."""
    if os.name == "nt":
        return shutil.which("npm.cmd") or shutil.which("npm")
    return shutil.which("npm")


def load_env_config(env_path: Path = ENV_PATH) -> dict[str, str]:
    """Read key=value pairs from .env (falling back to .env.example defaults)."""
    config: dict[str, str] = {
        "OLLAMA_URL": f"http://{OLLAMA_HOST}:{OLLAMA_PORT}",
        "OLLAMA_MODEL": "qwen3.5:4b",
        "TTS_BACKEND": "phonon",
        "LLM_BACKEND": "ollama",
        "SPIDEY_ALLOW_HUB": "1",
        "ORBIT_COACH_INTERVAL_MINUTES": "45",
    }
    source = env_path if env_path.is_file() else (ENV_EXAMPLE_PATH if ENV_EXAMPLE_PATH.is_file() else None)
    if source is None:
        return config
    for line in source.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            config[key] = value
    return config


def save_env_values(updates: dict[str, str], env_path: Path = ENV_PATH) -> None:
    """Persist updated key=value pairs into .env while preserving existing comments and keys."""
    if not env_path.exists() and ENV_EXAMPLE_PATH.is_file():
        env_path.write_text(ENV_EXAMPLE_PATH.read_text(encoding="utf-8"), encoding="utf-8")

    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.is_file() else []
    remaining = dict(updates)
    new_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            new_lines.append(line)
            continue
        key, _ = stripped.split("=", 1)
        key = key.strip()
        if key in remaining:
            new_lines.append(f"{key}={remaining.pop(key)}")
        else:
            new_lines.append(line)

    for key, val in remaining.items():
        new_lines.append(f"{key}={val}")

    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def is_port_open(host: str, port: int, timeout: float = 0.6) -> bool:
    """Return True if a TCP port is accepting connections."""
    for target_host in (host, "127.0.0.1", "localhost"):
        try:
            with socket.create_connection((target_host, port), timeout=timeout):
                return True
        except OSError:
            continue
    return False


def find_port_owner_pid(port: int) -> int | None:
    """Return the PID listening on ``port`` (Windows netstat lookup), or None."""
    try:
        from runtime.guard import get_port_owner_pid

        pid = get_port_owner_pid(port)
        if pid:
            return pid
    except Exception:
        pass
    if os.name == "nt":
        try:
            res = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True,
                text=True,
                timeout=3,
                creationflags=CREATE_NO_WINDOW,
            )
            for line in res.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 5 and "LISTENING" in parts[3].upper():
                    if parts[1].endswith(f":{port}"):
                        pid_val = int(parts[4])
                        if pid_val > 0:
                            return pid_val
        except Exception:
            pass
    return None


def check_ollama_health(ollama_url: str = f"http://{OLLAMA_HOST}:{OLLAMA_PORT}") -> dict[str, Any]:
    """Query Ollama /api/tags and return status + installed model names."""
    url = f"{ollama_url.rstrip('/')}/api/tags"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        models = [m.get("name") or m.get("model") or "" for m in (data.get("models") or [])]
        return {"running": True, "models": [m for m in models if m]}
    except Exception:
        return {"running": False, "models": []}


def check_backend_health(backend_url: str = f"http://{BACKEND_HOST}:{BACKEND_PORT}") -> dict[str, Any]:
    """Query FastAPI /api/health and return status details."""
    url = f"{backend_url.rstrip('/')}/api/health"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return {"running": True, "health": data}
    except Exception:
        return {"running": False, "health": {}}


def build_service_command(
    service_name: str,
    env_cfg: dict[str, str] | None = None,
    base_dir: Path = BASE_DIR,
) -> tuple[list[str], dict[str, str], Path]:
    """Return (cmd, env, cwd) for 'ollama', 'backend', or 'frontend'."""
    cfg = env_cfg if env_cfg is not None else load_env_config()
    env = os.environ.copy()
    for k, v in cfg.items():
        if v != "":
            env[k] = v

    if service_name == "ollama":
        ollama_exe = shutil.which("ollama")
        if not ollama_exe:
            raise FileNotFoundError("Ollama executable not found in PATH.")
        return ([ollama_exe, "serve"], env, base_dir)

    if service_name == "backend":
        py_exe = resolve_python_executable(base_dir)
        env.setdefault("TTS_BACKEND", cfg.get("TTS_BACKEND") or "phonon")
        env.setdefault("SPIDEY_ALLOW_HUB", cfg.get("SPIDEY_ALLOW_HUB") or "1")
        env["PYTHONUNBUFFERED"] = "1"
        return ([py_exe, str(base_dir / "app.py"), "--server"], env, base_dir)

    if service_name == "frontend":
        npm_exe = resolve_npm_executable()
        if not npm_exe:
            raise FileNotFoundError("npm executable not found in PATH.")
        return ([npm_exe, "--prefix", "frontend", "run", "dev"], env, base_dir)

    raise ValueError(f"Unknown service: {service_name}")


@dataclass
class ManagedProcess:
    name: str
    process: subprocess.Popen[str] | None = None
    status: str = "stopped"  # stopped | starting | running | external | error
    pid: int | None = None
    external: bool = False
    logs: list[str] = field(default_factory=list)


class ServiceSupervisor:
    """Manages lifecycle, health polling, and logs for Ollama, Backend, and Frontend."""

    def __init__(
        self,
        base_dir: Path = BASE_DIR,
        on_log: Callable[[str, str], None] | None = None,
    ) -> None:
        self.base_dir = base_dir
        self.on_log = on_log
        self._lock = threading.RLock()
        self.services: dict[str, ManagedProcess] = {
            "ollama": ManagedProcess("ollama"),
            "backend": ManagedProcess("backend"),
            "frontend": ManagedProcess("frontend"),
            "launcher": ManagedProcess("launcher"),
        }

    def _emit_log(self, service: str, line: str) -> None:
        clean = line.rstrip("\r\n")
        if not clean:
            return
        with self._lock:
            target = self.services.get(service) or self.services["launcher"]
            buf = target.logs
            buf.append(clean)
            if len(buf) > 500:
                del buf[: len(buf) - 500]
        if self.on_log:
            self.on_log(service, clean)

    def _stream_output(self, service: str, proc: subprocess.Popen[str]) -> None:
        assert proc.stdout is not None
        try:
            for line in iter(proc.stdout.readline, ""):
                if not line:
                    break
                self._emit_log(service, line)
        except Exception:
            pass
        finally:
            code = proc.poll()
            with self._lock:
                mp = self.services[service]
                if mp.process is proc:
                    mp.process = None
                    mp.pid = None
                    if mp.status != "stopped":
                        mp.status = "stopped" if code in (0, None, -15, 1) else "error"
            self._emit_log("launcher", f"[{service}] process exited (code={code})")

    def start_service(self, service: str, env_cfg: dict[str, str] | None = None) -> bool:
        with self._lock:
            mp = self.services[service]
            if mp.process and mp.process.poll() is None:
                self._emit_log("launcher", f"[{service}] already running (PID {mp.pid})")
                return True

        # Check if already running externally before spawning
        if service == "ollama" and is_port_open(OLLAMA_HOST, OLLAMA_PORT):
            with self._lock:
                mp.status = "external"
                mp.external = True
            self._emit_log("launcher", "[ollama] detected existing Ollama instance on :11434")
            return True
        if service == "backend" and is_port_open(BACKEND_HOST, BACKEND_PORT):
            with self._lock:
                mp.status = "external"
                mp.external = True
            self._emit_log("launcher", "[backend] detected existing backend instance on :8000")
            return True
        if service == "frontend" and is_port_open(FRONTEND_HOST, FRONTEND_PORT):
            with self._lock:
                mp.status = "external"
                mp.external = True
            self._emit_log("launcher", "[frontend] detected existing frontend instance on :5173")
            return True

        try:
            cmd, env, cwd = build_service_command(service, env_cfg=env_cfg, base_dir=self.base_dir)
        except FileNotFoundError as exc:
            with self._lock:
                mp.status = "error"
            self._emit_log(service, f"ERROR: {exc}")
            self._emit_log("launcher", f"[{service}] failed to start: {exc}")
            return False

        kwargs: dict[str, Any] = {
            "cwd": str(cwd),
            "env": env,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            # Keep stdin PIPE open so tools like Vite do not exit immediately on stdin EOF
            "stdin": subprocess.PIPE,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
            "bufsize": 1,
        }
        if os.name == "nt":
            kwargs["creationflags"] = CREATE_NO_WINDOW

        try:
            proc = subprocess.Popen(cmd, **kwargs)
        except Exception as exc:
            with self._lock:
                mp.status = "error"
            self._emit_log(service, f"ERROR launching {cmd[0]}: {exc}")
            return False

        with self._lock:
            mp.process = proc
            mp.pid = proc.pid
            mp.external = False
            mp.status = "starting"

        threading.Thread(
            target=self._stream_output, args=(service, proc), daemon=True
        ).start()
        self._emit_log("launcher", f"[{service}] started (PID {proc.pid})")
        return True

    def stop_service(self, service: str, allow_external_kill: bool = True) -> None:
        with self._lock:
            mp = self.services[service]
            proc = mp.process
            pid = mp.pid
            mp.status = "stopped"
            mp.external = False
            mp.process = None
            mp.pid = None

        if pid is None and allow_external_kill and service in ("backend", "frontend"):
            port = BACKEND_PORT if service == "backend" else FRONTEND_PORT
            pid = find_port_owner_pid(port)
            if pid is None and service == "backend":
                pid = find_port_owner_pid(47654)

        if proc is None and pid is None:
            self._emit_log("launcher", f"[{service}] is already stopped")
            return

        self._emit_log("launcher", f"[{service}] stopping PID {pid}...")
        if os.name == "nt" and pid is not None:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW,
            )
        elif proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

    def restart_service(self, service: str, env_cfg: dict[str, str] | None = None) -> None:
        self.stop_service(service, allow_external_kill=True)
        time.sleep(0.6)
        self.start_service(service, env_cfg=env_cfg)

    def stop_all(self) -> None:
        for svc in ("frontend", "backend"):
            self.stop_service(svc, allow_external_kill=True)
        if self.services["ollama"].process is not None:
            self.stop_service("ollama", allow_external_kill=False)

    def refresh_statuses(self, ollama_url: str) -> dict[str, dict[str, Any]]:
        """Probe TCP ports & health endpoints and return current snapshot for all 3 services."""
        ollama_info = check_ollama_health(ollama_url)
        backend_info = check_backend_health(f"http://{BACKEND_HOST}:{BACKEND_PORT}")
        frontend_up = is_port_open(FRONTEND_HOST, FRONTEND_PORT)

        with self._lock:
            for name, is_up in (
                ("ollama", ollama_info["running"]),
                ("backend", backend_info["running"]),
                ("frontend", frontend_up),
            ):
                mp = self.services[name]
                alive = mp.process is not None and mp.process.poll() is None
                if is_up:
                    mp.status = "running" if alive else "external"
                    mp.external = not alive
                elif alive:
                    mp.status = "starting"
                elif mp.status != "error":
                    mp.status = "stopped"
                    mp.external = False

            return {
                "ollama": {
                    "status": self.services["ollama"].status,
                    "pid": self.services["ollama"].pid,
                    "external": self.services["ollama"].external,
                    "models": ollama_info["models"],
                },
                "backend": {
                    "status": self.services["backend"].status,
                    "pid": self.services["backend"].pid,
                    "external": self.services["backend"].external,
                    "health": backend_info["health"],
                },
                "frontend": {
                    "status": self.services["frontend"].status,
                    "pid": self.services["frontend"].pid,
                    "external": self.services["frontend"].external,
                },
            }


def launch_gui() -> None:
    """Start the Tkinter Swiss-editorial S.P.I.D.E.Y. Control Center."""
    import tkinter as tk
    from tkinter import messagebox, scrolledtext, ttk

    # Palette matching S.P.I.D.E.Y.'s Swiss-editorial dark theme
    BG = "#0F0F0F"
    CARD = "#171717"
    CARD_BORDER = "#2A2A2A"
    TEXT = "#F2EFE9"
    MUTED = "#9C968E"
    ACCENT = "#D95D24"
    ACCENT_HOVER = "#C44E19"
    GREEN = "#22C55E"
    AMBER = "#F59E0B"
    RED = "#EF4444"
    CYAN = "#38BDF8"

    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "spidey.orbit007.control.center.v2"
            )
        except Exception:
            pass

    root = tk.Tk()
    root.title("S.P.I.D.E.Y. // Control Center")
    root.geometry("1040x720")
    root.minsize(900, 620)
    root.configure(bg=BG)

    ico_path = BASE_DIR / "spidey.ico"
    if ico_path.is_file():
        try:
            root.iconbitmap(default=str(ico_path))
        except Exception:
            pass

    for candidate_png in (BASE_DIR / "Logo.png", BASE_DIR / "frontend" / "public" / "logo.png", BASE_DIR / "dist" / "icon.png"):
        if candidate_png.is_file():
            try:
                icon_img = tk.PhotoImage(file=str(candidate_png))
                root._icon_img = icon_img  # Keep reference so GC doesn't collect the taskbar icon
                root.iconphoto(True, icon_img)
                break
            except Exception:
                continue

    if os.name == "nt" and ico_path.is_file():
        def _apply_win32_taskbar_icon() -> None:
            try:
                import ctypes

                user32 = ctypes.windll.user32
                IMAGE_ICON = 1
                LR_LOADFROMFILE = 0x00000010
                WM_SETICON = 0x0080
                ICON_SMALL = 0
                ICON_BIG = 1
                GCLP_HICON = -14
                GCLP_HICONSM = -34
                GA_ROOT = 2

                hicon_big = user32.LoadImageW(0, str(ico_path), IMAGE_ICON, 48, 48, LR_LOADFROMFILE)
                hicon_sm = user32.LoadImageW(0, str(ico_path), IMAGE_ICON, 16, 16, LR_LOADFROMFILE)
                hwnd_child = root.winfo_id()
                hwnds = {
                    hwnd_child,
                    user32.GetParent(hwnd_child),
                    user32.GetAncestor(hwnd_child, GA_ROOT),
                }
                set_class_long = getattr(user32, "SetClassLongPtrW", getattr(user32, "SetClassLongW", None))
                for hwnd in hwnds:
                    if not hwnd:
                        continue
                    if hicon_big:
                        user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, hicon_big)
                        if set_class_long:
                            set_class_long(hwnd, GCLP_HICON, hicon_big)
                    if hicon_sm:
                        user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, hicon_sm)
                        if set_class_long:
                            set_class_long(hwnd, GCLP_HICONSM, hicon_sm)
            except Exception:
                pass

        root.update_idletasks()
        _apply_win32_taskbar_icon()
        root.after(150, _apply_win32_taskbar_icon)

    log_queue: queue.Queue[tuple[str, str]] = queue.Queue()
    cfg = load_env_config()

    def on_log_cb(service: str, line: str) -> None:
        log_queue.put((service, line))

    supervisor = ServiceSupervisor(BASE_DIR, on_log=on_log_cb)

    # --- State variables ---
    model_var = tk.StringVar(value=cfg.get("OLLAMA_MODEL", "qwen3.5:4b"))
    tts_var = tk.StringVar(value=cfg.get("TTS_BACKEND", "phonon"))
    llm_var = tk.StringVar(value=cfg.get("LLM_BACKEND", "ollama"))
    coach_min_var = tk.StringVar(value=cfg.get("ORBIT_COACH_INTERVAL_MINUTES", "45"))
    auto_open_var = tk.BooleanVar(value=True)
    active_tab = tk.StringVar(value="all")
    auto_scroll_var = tk.BooleanVar(value=True)

    all_logs: list[tuple[str, str]] = []

    def current_env_overrides() -> dict[str, str]:
        return {
            "OLLAMA_MODEL": model_var.get().strip() or "qwen3.5:4b",
            "TTS_BACKEND": tts_var.get().strip() or "phonon",
            "LLM_BACKEND": llm_var.get().strip() or "ollama",
            "ORBIT_COACH_INTERVAL_MINUTES": coach_min_var.get().strip() or "45",
        }

    def save_config() -> None:
        updates = current_env_overrides()
        save_env_values(updates)
        log_queue.put(("launcher", f"[config] saved settings to .env: {updates}"))

    # --- Header ---
    header = tk.Frame(root, bg=BG, padx=20, pady=14)
    header.pack(fill="x")

    title_box = tk.Frame(header, bg=BG)
    title_box.pack(side="left")
    tk.Label(
        title_box,
        text="S.P.I.D.E.Y.  //  CONTROL CENTER",
        bg=BG,
        fg=TEXT,
        font=("Consolas", 15, "bold"),
    ).pack(anchor="w")
    tk.Label(
        title_box,
        text="Local AI Assistant Supervisor · Ollama + FastAPI + React",
        bg=BG,
        fg=MUTED,
        font=("Segoe UI", 9),
    ).pack(anchor="w")

    btn_bar = tk.Frame(header, bg=BG)
    btn_bar.pack(side="right")

    def make_btn(parent, text, command, bg_color=CARD, fg_color=TEXT, padx=12):
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=bg_color,
            fg=fg_color,
            activebackground=ACCENT_HOVER if bg_color == ACCENT else "#262626",
            activeforeground=TEXT,
            relief="flat",
            bd=0,
            padx=padx,
            pady=7,
            cursor="hand2",
            font=("Consolas", 9, "bold"),
        )

    def start_all_async() -> None:
        save_config()
        overrides = current_env_overrides()

        def _worker() -> None:
            log_queue.put(("launcher", "Starting S.P.I.D.E.Y. stack..."))
            supervisor.start_service("ollama", env_cfg=overrides)
            for _ in range(15):
                if is_port_open(OLLAMA_HOST, OLLAMA_PORT):
                    break
                time.sleep(0.4)

            supervisor.start_service("backend", env_cfg=overrides)
            supervisor.start_service("frontend", env_cfg=overrides)

            if auto_open_var.get():
                for _ in range(45):
                    if is_port_open(FRONTEND_HOST, FRONTEND_PORT) and is_port_open(BACKEND_HOST, BACKEND_PORT):
                        break
                    time.sleep(0.5)
                if is_port_open(FRONTEND_HOST, FRONTEND_PORT):
                    webbrowser.open(FRONTEND_URL)
                    log_queue.put(("launcher", f"Opened Web UI at {FRONTEND_URL}"))

        threading.Thread(target=_worker, daemon=True).start()

    def stop_all_async() -> None:
        threading.Thread(target=supervisor.stop_all, daemon=True).start()

    def restart_all_async() -> None:
        save_config()
        overrides = current_env_overrides()

        def _worker() -> None:
            supervisor.stop_all()
            time.sleep(0.8)
            supervisor.start_service("ollama", env_cfg=overrides)
            supervisor.start_service("backend", env_cfg=overrides)
            supervisor.start_service("frontend", env_cfg=overrides)

        threading.Thread(target=_worker, daemon=True).start()

    make_btn(btn_bar, "▶ START ALL", start_all_async, bg_color=ACCENT, fg_color="#111111").pack(side="left", padx=4)
    make_btn(btn_bar, "■ STOP ALL", stop_all_async, bg_color="#2A1717", fg_color=RED).pack(side="left", padx=4)
    make_btn(btn_bar, "↻ RESTART", restart_all_async).pack(side="left", padx=4)
    make_btn(btn_bar, "↗ OPEN WEB UI", lambda: webbrowser.open(FRONTEND_URL), bg_color="#1B2A1E", fg_color=GREEN).pack(side="left", padx=4)

    tk.Frame(root, bg=CARD_BORDER, height=1).pack(fill="x", padx=20)

    # --- Service Cards ---
    cards_frame = tk.Frame(root, bg=BG, padx=20, pady=14)
    cards_frame.pack(fill="x")
    for col in range(3):
        cards_frame.grid_columnconfigure(col, weight=1, uniform="svc")

    card_widgets: dict[str, dict[str, Any]] = {}

    def create_card(col: int, key: str, title: str, endpoint: str, extra_action: tuple[str, Callable[[], None]] | None = None):
        outer = tk.Frame(cards_frame, bg=CARD, highlightbackground=CARD_BORDER, highlightthickness=1, padx=14, pady=12)
        outer.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 8, 0))

        top = tk.Frame(outer, bg=CARD)
        top.pack(fill="x")
        tk.Label(top, text=title, bg=CARD, fg=TEXT, font=("Consolas", 11, "bold")).pack(side="left")
        pill = tk.Label(top, text="CHECKING", bg="#262626", fg=MUTED, font=("Consolas", 8, "bold"), padx=7, pady=2)
        pill.pack(side="right")

        sub = tk.Label(outer, text=endpoint, bg=CARD, fg=MUTED, font=("Consolas", 9))
        sub.pack(anchor="w", pady=(4, 2))
        meta = tk.Label(outer, text="PID: —", bg=CARD, fg=MUTED, font=("Segoe UI", 9))
        meta.pack(anchor="w", pady=(0, 10))

        actions = tk.Frame(outer, bg=CARD)
        actions.pack(fill="x")

        make_btn(
            actions,
            "Start",
            lambda s=key: threading.Thread(target=supervisor.start_service, args=(s, current_env_overrides()), daemon=True).start(),
            bg_color="#1F2937",
            padx=9,
        ).pack(side="left", padx=(0, 5))
        make_btn(
            actions,
            "Stop",
            lambda s=key: threading.Thread(target=supervisor.stop_service, args=(s,), daemon=True).start(),
            bg_color="#2A1717",
            fg_color=RED,
            padx=9,
        ).pack(side="left", padx=(0, 5))
        make_btn(
            actions,
            "Restart",
            lambda s=key: threading.Thread(target=supervisor.restart_service, args=(s, current_env_overrides()), daemon=True).start(),
            padx=9,
        ).pack(side="left", padx=(0, 5))
        if extra_action:
            make_btn(actions, extra_action[0], extra_action[1], padx=9).pack(side="right")

        card_widgets[key] = {"pill": pill, "meta": meta}

    def pull_ollama_model() -> None:
        model = model_var.get().strip() or "qwen3.5:4b"
        ollama_exe = shutil.which("ollama")
        if not ollama_exe:
            messagebox.showerror("Ollama Missing", "Ollama was not found in PATH.")
            return

        def _pull() -> None:
            log_queue.put(("ollama", f"Pulling model {model}..."))
            kwargs: dict[str, Any] = {
                "stdout": subprocess.PIPE,
                "stderr": subprocess.STDOUT,
                "text": True,
                "encoding": "utf-8",
                "errors": "replace",
            }
            if os.name == "nt":
                kwargs["creationflags"] = CREATE_NO_WINDOW
            proc = subprocess.Popen([ollama_exe, "pull", model], **kwargs)
            assert proc.stdout is not None
            for ln in iter(proc.stdout.readline, ""):
                if ln.strip():
                    log_queue.put(("ollama", ln.strip()))
            rc = proc.wait()
            log_queue.put(("launcher", f"[ollama] pull {model} finished (code={rc})"))

        threading.Thread(target=_pull, daemon=True).start()

    create_card(0, "ollama", "1. OLLAMA LLM", f"{OLLAMA_HOST}:{OLLAMA_PORT}", ("Pull Model", pull_ollama_model))
    create_card(1, "backend", "2. BACKEND API", f"{BACKEND_HOST}:{BACKEND_PORT}")
    create_card(2, "frontend", "3. WEB FRONTEND", FRONTEND_URL, ("Open", lambda: webbrowser.open(FRONTEND_URL)))

    # --- Settings Strip ---
    cfg_frame = tk.Frame(root, bg=CARD, highlightbackground=CARD_BORDER, highlightthickness=1, padx=14, pady=10)
    cfg_frame.pack(fill="x", padx=20)

    def add_field(parent, label, var, values=None, width=14):
        box = tk.Frame(parent, bg=CARD)
        box.pack(side="left", padx=(0, 14))
        tk.Label(box, text=label, bg=CARD, fg=MUTED, font=("Consolas", 8, "bold")).pack(anchor="w")
        if values:
            widget = ttk.Combobox(box, textvariable=var, values=values, width=width, state="normal")
        else:
            widget = tk.Entry(box, textvariable=var, width=width, bg="#0F0F0F", fg=TEXT, insertbackground=TEXT, relief="flat")
        widget.pack(pady=(2, 0))

    add_field(cfg_frame, "OLLAMA MODEL", model_var, ["qwen3.5:4b", "qwen2.5:7b", "llama3.2:3b"], width=16)
    add_field(cfg_frame, "LLM BACKEND", llm_var, ["ollama", "gemini"], width=10)
    add_field(cfg_frame, "TTS ENGINE", tts_var, ["phonon", "sapi"], width=10)
    add_field(cfg_frame, "COACH (MIN)", coach_min_var, width=6)

    tk.Checkbutton(
        cfg_frame,
        text="Auto-open browser",
        variable=auto_open_var,
        bg=CARD,
        fg=TEXT,
        selectcolor="#0F0F0F",
        activebackground=CARD,
        activeforeground=TEXT,
        font=("Segoe UI", 9),
    ).pack(side="left", padx=(4, 10))

    make_btn(cfg_frame, "Save .env", save_config, bg_color="#262626", padx=10).pack(side="right", padx=4)
    make_btn(
        cfg_frame,
        "Run Tests",
        lambda: threading.Thread(
            target=lambda: _run_pytest_into_logs(),
            daemon=True,
        ).start(),
        bg_color="#1B2230",
        fg_color=CYAN,
        padx=10,
    ).pack(side="right", padx=4)

    def _run_pytest_into_logs() -> None:
        py = resolve_python_executable(BASE_DIR)
        log_queue.put(("launcher", "Running pytest suite..."))
        kwargs: dict[str, Any] = {
            "cwd": str(BASE_DIR),
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
        }
        if os.name == "nt":
            kwargs["creationflags"] = CREATE_NO_WINDOW
        proc = subprocess.Popen([py, "-m", "pytest", "-q", "-p", "no:cacheprovider"], **kwargs)
        assert proc.stdout is not None
        for ln in iter(proc.stdout.readline, ""):
            if ln.strip():
                log_queue.put(("launcher", ln.rstrip()))
        rc = proc.wait()
        log_queue.put(("launcher", f"pytest finished (exit={rc})"))

    # --- Logs Panel ---
    logs_header = tk.Frame(root, bg=BG, padx=20, pady=8)
    logs_header.pack(fill="x")

    tab_buttons: dict[str, tk.Button] = {}

    def select_tab(tab_name: str) -> None:
        active_tab.set(tab_name)
        for name, b in tab_buttons.items():
            b.configure(
                bg=ACCENT if name == tab_name else CARD,
                fg="#111111" if name == tab_name else TEXT,
            )
        render_logs()

    for tab_key, label in (
        ("all", "ALL LOGS"),
        ("backend", "BACKEND"),
        ("frontend", "FRONTEND"),
        ("ollama", "OLLAMA"),
        ("launcher", "LAUNCHER"),
    ):
        b = make_btn(logs_header, label, lambda k=tab_key: select_tab(k), padx=10)
        b.pack(side="left", padx=(0, 6))
        tab_buttons[tab_key] = b

    make_btn(
        logs_header,
        "Clear",
        lambda: (all_logs.clear(), log_text.configure(state="normal"), log_text.delete("1.0", "end"), log_text.configure(state="disabled")),
        padx=10,
    ).pack(side="right")

    tk.Checkbutton(
        logs_header,
        text="Auto-scroll",
        variable=auto_scroll_var,
        bg=BG,
        fg=MUTED,
        selectcolor=BG,
        activebackground=BG,
        activeforeground=TEXT,
        font=("Segoe UI", 9),
    ).pack(side="right", padx=10)

    log_frame = tk.Frame(root, bg=BG, padx=20)
    log_frame.pack(fill="both", expand=True, pady=(0, 16))

    log_text = scrolledtext.ScrolledText(
        log_frame,
        bg="#0A0A0A",
        fg=TEXT,
        insertbackground=TEXT,
        font=("Consolas", 9),
        relief="flat",
        highlightbackground=CARD_BORDER,
        highlightthickness=1,
        state="disabled",
        wrap="word",
    )
    log_text.pack(fill="both", expand=True)
    log_text.tag_config("backend", foreground=CYAN)
    log_text.tag_config("frontend", foreground=GREEN)
    log_text.tag_config("ollama", foreground=AMBER)
    log_text.tag_config("launcher", foreground="#E879F9")

    def append_log_line(svc: str, line: str) -> None:
        cur = active_tab.get()
        if cur != "all" and cur != svc:
            return
        log_text.configure(state="normal")
        log_text.insert("end", f"[{svc.upper()}] {line}\n", svc if svc in ("backend", "frontend", "ollama", "launcher") else "")
        if auto_scroll_var.get():
            log_text.see("end")
        log_text.configure(state="disabled")

    def render_logs() -> None:
        cur = active_tab.get()
        log_text.configure(state="normal")
        log_text.delete("1.0", "end")
        for svc, line in all_logs[-500:]:
            if cur == "all" or cur == svc:
                log_text.insert("end", f"[{svc.upper()}] {line}\n", svc if svc in ("backend", "frontend", "ollama", "launcher") else "")
        if auto_scroll_var.get():
            log_text.see("end")
        log_text.configure(state="disabled")

    select_tab("all")

    def drain_log_queue() -> None:
        drained = 0
        while drained < 100:
            try:
                svc, line = log_queue.get_nowait()
            except queue.Empty:
                break
            all_logs.append((svc, line))
            if len(all_logs) > 1200:
                del all_logs[: len(all_logs) - 1200]
            append_log_line(svc, line)
            drained += 1
        root.after(120, drain_log_queue)

    def poll_health_loop() -> None:
        def _probe() -> None:
            snap = supervisor.refresh_statuses(cfg.get("OLLAMA_URL", f"http://{OLLAMA_HOST}:{OLLAMA_PORT}"))

            def _apply() -> None:
                pill_style = {
                    "running": ("RUNNING", "#14532D", GREEN),
                    "external": ("EXTERNAL", "#1E3A8A", CYAN),
                    "starting": ("STARTING", "#78350F", AMBER),
                    "error": ("ERROR", "#7F1D1D", RED),
                    "stopped": ("STOPPED", "#262626", MUTED),
                }
                for key, info in snap.items():
                    st = info["status"]
                    label, bg_c, fg_c = pill_style.get(st, ("STOPPED", "#262626", MUTED))
                    card_widgets[key]["pill"].configure(text=label, bg=bg_c, fg=fg_c)

                    if key == "ollama":
                        models = info.get("models") or []
                        target = model_var.get().strip()
                        has_model = any(m == target or m.startswith(f"{target}:") for m in models)
                        meta_txt = (
                            f"Models: {len(models)} ({'model ready' if has_model else f'missing {target}'})"
                            if st in ("running", "external")
                            else "PID: —"
                        )
                    elif key == "backend":
                        pid = info.get("pid") or (find_port_owner_pid(BACKEND_PORT) if st in ("running", "external") else None)
                        h = info.get("health") or {}
                        meta_txt = f"PID: {pid or 'external'} · DB {'OK' if h.get('db_connected') else '—'}" if st in ("running", "external") else f"PID: {pid or '—'}"
                    else:
                        pid = info.get("pid") or (find_port_owner_pid(FRONTEND_PORT) if st in ("running", "external") else None)
                        meta_txt = f"PID: {pid or 'external'} · Vite Ready" if st in ("running", "external") else f"PID: {pid or '—'}"
                    card_widgets[key]["meta"].configure(text=meta_txt)

            try:
                root.after(0, _apply)
            except Exception:
                pass

        threading.Thread(target=_probe, daemon=True).start()
        root.after(2000, poll_health_loop)

    def on_close() -> None:
        running_managed = [
            name for name, mp in supervisor.services.items()
            if mp.process is not None and mp.process.poll() is None
        ]
        if running_managed:
            if messagebox.askyesno(
                "Stop Managed Services?",
                f"Stop running S.P.I.D.E.Y. services ({', '.join(running_managed)}) before closing?",
            ):
                supervisor.stop_all()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    log_queue.put(("launcher", "S.P.I.D.E.Y. Control Center ready. Click '▶ START ALL' to launch."))
    drain_log_queue()
    poll_health_loop()
    root.mainloop()


if __name__ == "__main__":
    launch_gui()
