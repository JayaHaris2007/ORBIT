"""Unit tests for ORBIT Control Center / launcher helpers."""

from pathlib import Path

import orbit_launcher


def test_load_and_save_env_config(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("# header comment\nOLLAMA_MODEL=qwen3.5:4b\nTTS_BACKEND=phonon\n", encoding="utf-8")

    cfg = orbit_launcher.load_env_config(env_file)
    assert cfg["OLLAMA_MODEL"] == "qwen3.5:4b"
    assert cfg["TTS_BACKEND"] == "phonon"

    orbit_launcher.save_env_values(
        {"OLLAMA_MODEL": "llama3.2:3b", "ORBIT_COACH_INTERVAL_MINUTES": "30"},
        env_path=env_file,
    )
    updated = orbit_launcher.load_env_config(env_file)
    assert updated["OLLAMA_MODEL"] == "llama3.2:3b"
    assert updated["TTS_BACKEND"] == "phonon"
    assert updated["ORBIT_COACH_INTERVAL_MINUTES"] == "30"
    assert "# header comment" in env_file.read_text(encoding="utf-8")


def test_build_service_command_backend_and_frontend(tmp_path, monkeypatch):
    venv_py = tmp_path / ".venv" / "Scripts" / "python.exe"
    venv_py.parent.mkdir(parents=True)
    venv_py.write_text("", encoding="utf-8")

    cmd, env, cwd = orbit_launcher.build_service_command(
        "backend",
        env_cfg={"TTS_BACKEND": "sapi", "OLLAMA_MODEL": "qwen3.5:4b"},
        base_dir=tmp_path,
    )
    assert Path(cmd[0]) == venv_py
    assert cmd[1].endswith("app.py")
    assert cmd[2] == "--server"
    assert env["TTS_BACKEND"] == "sapi"
    assert cwd == tmp_path


def test_supervisor_emit_log_handles_all_channels():
    collected = []
    sup = orbit_launcher.ServiceSupervisor(on_log=lambda svc, ln: collected.append((svc, ln)))
    for channel in ("launcher", "ollama", "backend", "frontend", "custom"):
        sup._emit_log(channel, f"hello from {channel}")
    assert len(collected) == 5
    assert "hello from launcher" in sup.services["launcher"].logs

