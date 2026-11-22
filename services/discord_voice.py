"""Discord Server Voice Channel integration for S.P.I.D.E.Y.

Supports full two-way voice conversation inside Discord server voice channels:
- Receives per-user Opus audio via ``discord-ext-voice-recv`` with ``wants_opus()=True``
  and transparent DAVE (End-to-End Encryption via ``davey``) decryption so it works
  reliably on Discord's encrypted voice channels.
- Decodes Opus -> 48 kHz stereo PCM -> 16 kHz mono PCM, runs per-user energy VAD
  with pre-roll buffering and a silence-flush watchdog (handles Discord client DTX).
- Transcribes speech via S.P.I.D.E.Y.'s unified STT, routes through the same
  confirmation -> local command -> agent tool loop pipeline as text/web chat,
  and speaks concise summaries back into the call via Phonon/SAPI TTS + ``discord.PCMAudio``.
"""

from __future__ import annotations

import asyncio
import collections
import io
import logging
import math
import os
import re
import struct
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import discord
import numpy as np
from scipy.signal import resample_poly

import app
from voice.text_clean import clean_text_for_speech, summarize_for_speech

try:
    import davey
except ImportError:  # pragma: no cover - optional in stripped environments
    davey = None  # type: ignore[assignment]

try:
    from discord.ext import voice_recv
    from discord.ext.voice_recv.gateway import hook as _voice_recv_hook
    from discord.gateway import DiscordVoiceWebSocket
    from discord.voice_state import VoiceConnectionState
except ImportError:  # pragma: no cover - optional in stripped environments
    voice_recv = None  # type: ignore[assignment]
    _voice_recv_hook = None  # type: ignore[assignment]
    DiscordVoiceWebSocket = None  # type: ignore[assignment]
    VoiceConnectionState = None  # type: ignore[assignment]

LOGGER = logging.getLogger("spidey.discord.voice")

# Suppress per-second RTCP SenderReportPacket / gateway seq INFO spam from voice_recv
logging.getLogger("discord.ext.voice_recv.reader").setLevel(logging.WARNING)
logging.getLogger("discord.ext.voice_recv.gateway").setLevel(logging.WARNING)

DISCORD_SAMPLE_RATE = 48000
STT_SAMPLE_RATE = 16000
OPUS_SILENCE_FRAME = b"\xf8\xff\xfe"
DISCORD_FRAME_BYTES = 3840  # 20ms @ 48 kHz stereo 16-bit PCM

# Tunable VAD defaults (overridable via environment variables)
VOICE_ENERGY_THRESHOLD = float(os.environ.get("DISCORD_VOICE_ENERGY_THRESHOLD", "260.0") or "260.0")
VOICE_SILENCE_TIMEOUT_S = float(os.environ.get("DISCORD_VOICE_SILENCE_SECONDS", "0.95") or "0.95")
VOICE_MIN_SPEECH_S = float(os.environ.get("DISCORD_VOICE_MIN_SPEECH_SECONDS", "0.35") or "0.35")
VOICE_MAX_UTTERANCE_S = float(os.environ.get("DISCORD_VOICE_MAX_UTTERANCE_SECONDS", "15.0") or "15.0")
VOICE_ECHO_COOLDOWN_S = float(os.environ.get("DISCORD_VOICE_ECHO_COOLDOWN_SECONDS", "0.4") or "0.4")
VOICE_WATCHDOG_INTERVAL_S = 0.2

_LEAVE_CALL_RE = re.compile(
    r"^(?:hey\s+spidey[,\s]+|spidey[,\s]+)?(?:please\s+)?"
    r"(?:leave(?:\s+the)?\s+(?:call|voice(?:\s+channel)?|vc)|"
    r"disconnect(?:\s+from\s+(?:the\s+)?(?:call|voice))?|"
    r"hang\s+up|exit\s+(?:the\s+)?(?:call|voice)|bye\s+spidey|goodbye\s+spidey)$",
    re.IGNORECASE,
)

_STOP_SPEAKING_RE = re.compile(
    r"^(?:hey\s+spidey[,\s]+|spidey[,\s]+)?(?:please\s+)?"
    r"(?:stop\s+(?:talking|speaking)|be\s+quiet|shut\s+up|mute\s+yourself|silence)$",
    re.IGNORECASE,
)

# Common short STT noise artifacts on silent/noisy mic taps
_NOISE_TRANSCRIPTS = {
    "", ".", "..", "...", "you", "yeah", "uh", "um", "hmm", "hm",
    "thank you", "thanks for watching", "thanks for watching.",
    "subtitles by", "bye.",
}


def ensure_opus_loaded() -> bool:
    """Ensure libopus is loaded so Discord voice encode/decode works."""
    if discord.opus.is_loaded():
        return True
    try:
        discord.opus._load_default()
        return discord.opus.is_loaded()
    except Exception as exc:
        LOGGER.warning("Could not load default libopus: %s", exc)
        return False


def pcm48k_stereo_to_16k_mono(pcm48k_stereo: bytes) -> bytes:
    """Convert 48 kHz 16-bit signed stereo PCM to 16 kHz 16-bit signed mono PCM."""
    if not pcm48k_stereo:
        return b""
    # 4 bytes per stereo frame (2 channels x int16)
    usable = (len(pcm48k_stereo) // 4) * 4
    if usable == 0:
        return b""
    samples = np.frombuffer(pcm48k_stereo[:usable], dtype=np.int16).astype(np.float32)
    stereo = samples.reshape(-1, 2)
    mono = stereo.mean(axis=1)
    # 48 kHz -> 16 kHz is an exact 3:1 decimation with box anti-aliasing
    n3 = (len(mono) // 3) * 3
    if n3 == 0:
        return b""
    downsampled = mono[:n3].reshape(-1, 3).mean(axis=1)
    return np.clip(np.rint(downsampled), -32768, 32767).astype(np.int16).tobytes()


def float32_to_pcm48k_stereo(audio: np.ndarray, src_rate: int = 24000) -> bytes:
    """Resample float32 mono/stereo audio to Discord's 48 kHz 16-bit stereo PCM format."""
    arr = np.asarray(audio, dtype=np.float32)
    if arr.size == 0:
        return b""
    if arr.ndim > 1:
        arr = arr.mean(axis=1)
    src_rate = int(src_rate) if src_rate and src_rate > 0 else 24000
    if src_rate != DISCORD_SAMPLE_RATE:
        g = math.gcd(DISCORD_SAMPLE_RATE, src_rate)
        up = DISCORD_SAMPLE_RATE // g
        down = src_rate // g
        arr = resample_poly(arr, up, down).astype(np.float32)
    clipped = np.clip(arr, -1.0, 1.0)
    int16_mono = np.rint(clipped * 32767.0).astype(np.int16)
    stereo = np.repeat(int16_mono[:, np.newaxis], 2, axis=1)
    raw = stereo.tobytes()
    # Pad to an exact multiple of 3840 bytes (20ms Discord Opus frame) + 100ms tail silence
    rem = len(raw) % DISCORD_FRAME_BYTES
    if rem:
        raw += b"\x00" * (DISCORD_FRAME_BYTES - rem)
    raw += b"\x00" * (DISCORD_FRAME_BYTES * 5)
    return raw


def pcm_rms(pcm16k: bytes) -> float:
    """Return root-mean-square amplitude of 16-bit signed PCM bytes."""
    if not pcm16k or len(pcm16k) < 2:
        return 0.0
    usable = (len(pcm16k) // 2) * 2
    samples = np.frombuffer(pcm16k[:usable], dtype=np.int16).astype(np.float32)
    if samples.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(samples * samples)))


def prepare_pcm16k_for_stt(pcm16k: bytes) -> tuple[bytes, float, float]:
    """Auto-gain normalize and pad 16 kHz mono PCM for reliable STT.

    Returns ``(prepared_pcm, raw_rms, raw_peak)``.
    """
    if not pcm16k or len(pcm16k) < 2:
        return b"", 0.0, 0.0
    usable = (len(pcm16k) // 2) * 2
    samples = np.frombuffer(pcm16k[:usable], dtype=np.int16).astype(np.float32)
    if samples.size == 0:
        return b"", 0.0, 0.0
    # Remove any DC offset
    samples = samples - float(np.mean(samples))
    raw_rms = float(np.sqrt(np.mean(samples * samples)))
    raw_peak = float(np.max(np.abs(samples)))
    if raw_peak > 200.0:
        gain = min(8.0, 22000.0 / raw_peak)
        if gain > 1.15:
            samples = np.clip(samples * gain, -32767.0, 32767.0)
    pad = np.zeros(int(STT_SAMPLE_RATE * 0.2), dtype=np.int16)  # 200ms leading & trailing silence
    out = np.concatenate([pad, np.rint(samples).astype(np.int16), pad])
    return out.tobytes(), raw_rms, raw_peak


def synthesize_discord_pcm(text: str) -> bytes | None:
    """Summarize and synthesize text into 48 kHz 16-bit stereo PCM bytes for Discord."""
    spoken = summarize_for_speech(text) or clean_text_for_speech(text) or (text or "").strip()
    if not spoken:
        return None
    try:
        from voice import config as voice_config
        from voice.tts import get_tts_engine

        engine = get_tts_engine()
        engine.load()
        if not engine.available:
            return None
        audio = engine.synthesize(spoken)
        if audio is None or len(audio) == 0:
            return None
        # Phonon outputs 24 kHz; Windows SAPI typically outputs 22.05 kHz
        src_rate = 22050 if getattr(engine, "last_backend", None) == "sapi" else voice_config.SAMPLE_RATE
        return float32_to_pcm48k_stereo(audio, src_rate=src_rate)
    except Exception as exc:
        LOGGER.warning("Discord voice TTS synthesis failed: %s", exc)
        return None


def _decrypt_dave_opus(voice_client: Any, user_id: int, opus_bytes: bytes) -> tuple[bytes | None, str]:
    """Decrypt a Discord DAVE E2EE Opus packet when DAVE is active on the connection.

    Returns ``(opus_bytes_or_None, status_label)``.
    """
    if not opus_bytes:
        return None, "empty"
    if davey is None:
        return opus_bytes, "no-davey"
    conn = getattr(voice_client, "_connection", None)
    dave_session = getattr(conn, "dave_session", None)
    if dave_session is None or not getattr(dave_session, "ready", False):
        return opus_bytes, "dave-inactive"
    try:
        return dave_session.decrypt(user_id, davey.MediaType.audio, opus_bytes), "dave-decrypted"
    except Exception as exc:
        try:
            if dave_session.can_passthrough(user_id):
                return opus_bytes, "dave-passthrough"
        except Exception:
            pass
        LOGGER.debug("DAVE decrypt failed for user %s: %s", user_id, exc)
        return None, f"dave-error:{type(exc).__name__}"


if voice_recv is not None and DiscordVoiceWebSocket is not None and VoiceConnectionState is not None:

    class _SpideyVoiceWebSocket(DiscordVoiceWebSocket):
        """DiscordVoiceWebSocket patched for davey 0.2.x prepare_transition / execute_transition."""

        async def received_message(self, msg: dict[str, Any]) -> None:
            op = msg["op"]
            data = msg.get("d") or {}
            state = self._connection
            if state.dave_session is not None and op == self.DAVE_PREPARE_TRANSITION:
                transition_id = data["transition_id"]
                protocol_version = data["protocol_version"]
                if hasattr(state.dave_session, "prepare_transition"):
                    try:
                        state.dave_session.prepare_transition(transition_id, protocol_version)
                    except Exception as exc:
                        LOGGER.warning("DAVE prepare_transition(%s, %s) failed: %s", transition_id, protocol_version, exc)
            await super().received_message(msg)

        async def received_binary_message(self, msg: bytes) -> None:
            self.seq_ack = struct.unpack_from(">H", msg, 0)[0]
            op = msg[2]
            state = self._connection
            if state.dave_session is None:
                return

            if op == self.MLS_ANNOUNCE_COMMIT_TRANSITION:
                transition_id = struct.unpack_from(">H", msg, 3)[0]
                try:
                    should_prepare = state.dave_session.process_commit(msg[5:])
                    if hasattr(state.dave_session, "prepare_transition") and (should_prepare is None or should_prepare):
                        state.dave_session.prepare_transition(transition_id, state.dave_protocol_version)
                    if transition_id == 0:
                        if hasattr(state.dave_session, "execute_transition"):
                            state.dave_session.execute_transition(0)
                        LOGGER.info(
                            "DAVE commit transition 0 executed (ready=%s, can_encrypt=%s, epoch=%s).",
                            state.dave_session.ready,
                            state.can_encrypt,
                            state.dave_session.epoch,
                        )
                    else:
                        state.dave_pending_transitions[transition_id] = state.dave_protocol_version
                        await self.send_transition_ready(transition_id)
                except Exception as exc:
                    LOGGER.warning("DAVE MLS commit failed for transition %s: %s", transition_id, exc)
                    await state._recover_from_invalid_commit(transition_id)
                return

            if op == self.MLS_WELCOME:
                transition_id = struct.unpack_from(">H", msg, 3)[0]
                try:
                    state.dave_session.process_welcome(msg[5:])
                    if hasattr(state.dave_session, "prepare_transition"):
                        state.dave_session.prepare_transition(transition_id, state.dave_protocol_version)
                    if transition_id == 0:
                        if hasattr(state.dave_session, "execute_transition"):
                            state.dave_session.execute_transition(0)
                        LOGGER.info(
                            "DAVE welcome transition 0 executed (ready=%s, can_encrypt=%s, epoch=%s).",
                            state.dave_session.ready,
                            state.can_encrypt,
                            state.dave_session.epoch,
                        )
                    else:
                        state.dave_pending_transitions[transition_id] = state.dave_protocol_version
                        await self.send_transition_ready(transition_id)
                except Exception as exc:
                    LOGGER.warning("DAVE MLS welcome failed for transition %s: %s", transition_id, exc)
                    await state._recover_from_invalid_commit(transition_id)
                return

            await super().received_binary_message(msg)

    class _SpideyVoiceConnectionState(VoiceConnectionState):
        """VoiceConnectionState that activates davey 0.2.x keys on execute_transition."""

        async def _connect_websocket(self, resume: bool) -> DiscordVoiceWebSocket:
            from discord.utils import MISSING

            seq_ack = -1
            if self.ws is not MISSING:
                seq_ack = self.ws.seq_ack
            ws = await _SpideyVoiceWebSocket.from_connection_state(
                self, resume=resume, hook=self.hook, seq_ack=seq_ack
            )
            from discord.voice_state import ConnectionFlowState

            self.state = ConnectionFlowState.websocket_connected
            return ws

        async def _execute_transition(self, transition_id: int) -> None:
            await super()._execute_transition(transition_id)
            if self.dave_session is not None and hasattr(self.dave_session, "execute_transition"):
                try:
                    executed = self.dave_session.execute_transition(transition_id)
                    LOGGER.info(
                        "DAVE execute_transition(%s) -> %s (ready=%s, can_encrypt=%s, epoch=%s).",
                        transition_id,
                        executed,
                        self.dave_session.ready,
                        self.can_encrypt,
                        self.dave_session.epoch,
                    )
                except Exception as exc:
                    LOGGER.warning("DAVE execute_transition(%s) failed: %s", transition_id, exc)

    class SpideyVoiceRecvClient(voice_recv.VoiceRecvClient):
        """VoiceRecvClient wired with davey 0.2.x transition support."""

        def create_connection_state(self) -> VoiceConnectionState:
            return _SpideyVoiceConnectionState(self, hook=_voice_recv_hook)

else:  # pragma: no cover - fallback when voice_recv is unavailable
    SpideyVoiceRecvClient = None  # type: ignore[assignment]


@dataclass
class _UserAudioState:
    user: Any
    decoder: Any = None
    pre_roll: collections.deque = field(default_factory=lambda: collections.deque(maxlen=15))
    speech_chunks: list[bytes] = field(default_factory=list)
    is_speaking: bool = False
    speech_start_ts: float = 0.0
    last_voice_ts: float = 0.0
    voiced_frames: int = 0
    noise_floor: float = 80.0
    logged_first_packet: bool = False
    dave_errors: int = 0
    opus_errors: int = 0


_SinkBase = voice_recv.AudioSink if voice_recv is not None else object


class SpideyVoiceSink(_SinkBase):  # type: ignore[misc]
    """Opus-level Discord voice sink with DAVE E2EE decryption and per-user VAD."""

    def __init__(
        self,
        session: GuildVoiceSession,
        *,
        energy_threshold: float = VOICE_ENERGY_THRESHOLD,
        silence_timeout_s: float = VOICE_SILENCE_TIMEOUT_S,
        min_speech_s: float = VOICE_MIN_SPEECH_S,
        max_utterance_s: float = VOICE_MAX_UTTERANCE_S,
    ) -> None:
        if voice_recv is not None:
            super().__init__()
        self.session = session
        self.energy_threshold = energy_threshold
        self.silence_timeout_s = silence_timeout_s
        self.min_speech_s = min_speech_s
        self.max_utterance_s = max_utterance_s
        self._lock = threading.Lock()
        self._users: dict[int, _UserAudioState] = {}

    def wants_opus(self) -> bool:
        return True

    def _get_or_create_state(self, user: Any) -> _UserAudioState:
        state = self._users.get(user.id)
        if state is None:
            decoder = discord.opus.Decoder() if discord.opus.is_loaded() else None
            state = _UserAudioState(user=user, decoder=decoder)
            self._users[user.id] = state
        else:
            state.user = user
            if state.decoder is None and discord.opus.is_loaded():
                state.decoder = discord.opus.Decoder()
        return state

    def _finalize_locked(self, state: _UserAudioState) -> tuple[Any, bytes] | None:
        chunks = state.speech_chunks
        voiced_frames = state.voiced_frames
        state.speech_chunks = []
        state.is_speaking = False
        state.speech_start_ts = 0.0
        state.last_voice_ts = 0.0
        state.voiced_frames = 0
        state.pre_roll.clear()

        if not chunks:
            return None
        pcm = b"".join(chunks)
        # 16 kHz mono int16 = 32,000 bytes/second
        duration_s = len(pcm) / (STT_SAMPLE_RATE * 2)
        min_voiced_frames = max(3, int(self.min_speech_s / 0.04))
        if duration_s < self.min_speech_s or voiced_frames < min_voiced_frames:
            return None
        return state.user, pcm

    def feed_pcm16k(self, user: Any, pcm16k: bytes, *, now: float | None = None) -> tuple[Any, bytes] | None:
        """Feed one 16 kHz mono PCM frame through per-user VAD; returns finalized utterance if ready."""
        if not pcm16k or user is None:
            return None
        ts = time.monotonic() if now is None else now
        rms = pcm_rms(pcm16k)

        with self._lock:
            state = self._get_or_create_state(user)
            adaptive_threshold = max(self.energy_threshold, min(1400.0, state.noise_floor * 2.4))
            if rms >= adaptive_threshold:
                if not state.is_speaking:
                    state.is_speaking = True
                    state.speech_start_ts = ts
                    state.speech_chunks = list(state.pre_roll)
                    state.pre_roll.clear()
                state.speech_chunks.append(pcm16k)
                state.last_voice_ts = ts
                state.voiced_frames += 1
                if (ts - state.speech_start_ts) >= self.max_utterance_s:
                    return self._finalize_locked(state)
            else:
                if state.is_speaking:
                    state.speech_chunks.append(pcm16k)
                    if (ts - state.last_voice_ts) >= self.silence_timeout_s:
                        return self._finalize_locked(state)
                else:
                    # Slowly track ambient room noise floor when user is quiet
                    state.noise_floor = state.noise_floor * 0.92 + rms * 0.08
                    state.pre_roll.append(pcm16k)
        return None

    def flush_timed_out_users(self, *, now: float | None = None) -> list[tuple[Any, bytes]]:
        """Flush users who stopped sending RTP packets (Discord DTX) past the silence timeout."""
        ts = time.monotonic() if now is None else now
        ready: list[tuple[Any, bytes]] = []
        with self._lock:
            for state in list(self._users.values()):
                if state.is_speaking and (ts - state.last_voice_ts) >= self.silence_timeout_s:
                    item = self._finalize_locked(state)
                    if item is not None:
                        ready.append(item)
        return ready

    def write(self, user: Any, data: Any) -> None:
        if user is None or getattr(user, "bot", False):
            return
        if not self.session.is_user_allowed(user.id):
            return
        # Prevent speaker-to-mic echo loops while S.P.I.D.E.Y. is talking
        if self.session.should_ignore_incoming_audio():
            return

        opus_bytes = getattr(data, "opus", None)
        if not opus_bytes or opus_bytes == OPUS_SILENCE_FRAME:
            return

        vc = getattr(self, "voice_client", None) or self.session.voice_client
        decrypted_opus, dave_status = _decrypt_dave_opus(vc, user.id, opus_bytes)
        if not decrypted_opus or decrypted_opus == OPUS_SILENCE_FRAME:
            if dave_status.startswith("dave-error"):
                with self._lock:
                    st = self._get_or_create_state(user)
                    st.dave_errors += 1
                    if st.dave_errors in (1, 25, 100):
                        LOGGER.warning(
                            "Discord voice DAVE decrypt error #%d for user %s (%s, opus_len=%d).",
                            st.dave_errors, user.id, dave_status, len(opus_bytes),
                        )
            return

        with self._lock:
            state = self._get_or_create_state(user)
            decoder = state.decoder
        if decoder is None:
            return

        try:
            pcm48k = decoder.decode(decrypted_opus, fec=False)
        except Exception as exc:
            with self._lock:
                state.opus_errors += 1
                if state.opus_errors in (1, 25, 100):
                    LOGGER.warning(
                        "Discord voice Opus decode error #%d for user %s (dave=%s, len=%d): %s",
                        state.opus_errors, user.id, dave_status, len(decrypted_opus), exc,
                    )
            return

        pcm16k = pcm48k_stereo_to_16k_mono(pcm48k)
        if not pcm16k:
            return

        if not state.logged_first_packet:
            state.logged_first_packet = True
            LOGGER.info(
                "Discord voice receiving audio from user=%s (dave=%s, opus=%dB, rms=%.1f).",
                user.id, dave_status, len(decrypted_opus), pcm_rms(pcm16k),
            )

        utterance = self.feed_pcm16k(user, pcm16k)
        if utterance is not None:
            self.session.submit_utterance_from_thread(utterance[0], utterance[1])

    def cleanup(self) -> None:
        with self._lock:
            self._users.clear()


class GuildVoiceSession:
    """Active two-way voice session inside a single Discord server voice channel."""

    def __init__(
        self,
        manager: DiscordVoiceManager,
        guild: discord.Guild,
        voice_client: Any,
        text_channel: Any | None,
        loop: asyncio.AbstractEventLoop,
        *,
        text_mirror: bool = True,
    ) -> None:
        self.manager = manager
        self.guild = guild
        self.voice_client = voice_client
        self.text_channel = text_channel
        self.loop = loop
        self.text_mirror = text_mirror

        self.sink = SpideyVoiceSink(self)
        self.turn_lock = asyncio.Lock()
        self.is_speaking_output = False
        self.ignore_audio_until = 0.0
        self._closed = False
        self._watchdog_task: asyncio.Task | None = None
        self._playback_done_event: asyncio.Event | None = None

    def is_user_allowed(self, user_id: int) -> bool:
        return self.manager.is_user_allowed(user_id, self.guild.id)

    def should_ignore_incoming_audio(self) -> bool:
        if self._closed or self.is_speaking_output:
            return True
        if time.monotonic() < self.ignore_audio_until:
            return True
        try:
            if self.voice_client and self.voice_client.is_playing():
                return True
        except Exception:
            pass
        return False

    def start(self) -> None:
        if hasattr(self.voice_client, "listen") and not self.voice_client.is_listening():
            self.voice_client.listen(self.sink)
        if self._watchdog_task is None or self._watchdog_task.done():
            self._watchdog_task = self.loop.create_task(self._silence_watchdog())

    async def _silence_watchdog(self) -> None:
        try:
            while not self._closed:
                await asyncio.sleep(VOICE_WATCHDOG_INTERVAL_S)
                if self._closed or self.should_ignore_incoming_audio():
                    continue
                ready = self.sink.flush_timed_out_users()
                for user, pcm16k in ready:
                    self.loop.create_task(self.handle_utterance(user, pcm16k))
        except asyncio.CancelledError:
            pass
        except Exception:
            LOGGER.exception("Voice silence watchdog error in guild %s.", self.guild.id)

    def submit_utterance_from_thread(self, user: Any, pcm16k: bytes) -> None:
        if self._closed:
            return
        try:
            asyncio.run_coroutine_threadsafe(self.handle_utterance(user, pcm16k), self.loop)
        except Exception as exc:
            LOGGER.debug("Could not schedule voice utterance: %s", exc)

    def stop_playback(self) -> bool:
        if self.voice_client and self.voice_client.is_playing():
            # IMPORTANT: VoiceRecvClient.stop() also stops listening! Use stop_playing() so the mic stays active.
            if hasattr(self.voice_client, "stop_playing"):
                self.voice_client.stop_playing()
            else:
                self.voice_client.stop()
            self.is_speaking_output = False
            self.ignore_audio_until = time.monotonic() + 0.2
            if self._playback_done_event is not None:
                self._playback_done_event.set()
            return True
        return False

    async def wait_for_voice_ready(self, timeout: float = 2.0) -> None:
        """Wait briefly for DAVE E2EE epoch transition to settle before initial playback."""
        deadline = time.monotonic() + timeout
        conn = getattr(self.voice_client, "_connection", None)
        while time.monotonic() < deadline and not self._closed:
            if conn is not None and getattr(conn, "can_encrypt", False):
                await asyncio.sleep(0.25)
                return
            await asyncio.sleep(0.1)

    async def speak(self, text: str) -> bool:
        """Synthesize text and play it into the Discord voice channel."""
        if self._closed or not self.voice_client or not self.voice_client.is_connected():
            return False
        pcm48k = await asyncio.to_thread(synthesize_discord_pcm, text)
        if not pcm48k or self._closed or not self.voice_client.is_connected():
            return False

        # Stop any prior clip without stopping the voice receiver!
        if self.voice_client.is_playing():
            if hasattr(self.voice_client, "stop_playing"):
                self.voice_client.stop_playing()
            else:
                self.voice_client.stop()
            await asyncio.sleep(0.05)

        done_event = asyncio.Event()
        self._playback_done_event = done_event
        self.is_speaking_output = True

        def _after_play(error: Exception | None) -> None:
            if error:
                LOGGER.warning("Discord voice playback error: %s", error)
            self.is_speaking_output = False
            self.ignore_audio_until = time.monotonic() + VOICE_ECHO_COOLDOWN_S
            try:
                self.loop.call_soon_threadsafe(done_event.set)
            except Exception:
                pass

        try:
            conn = getattr(self.voice_client, "_connection", None)
            dur_s = len(pcm48k) / (DISCORD_SAMPLE_RATE * 4)
            LOGGER.info(
                "Discord voice speaking %.2fs in '%s' (dave_encrypt=%s).",
                dur_s,
                self.guild.name,
                bool(getattr(conn, "can_encrypt", False)),
            )
            source = discord.PCMAudio(io.BytesIO(pcm48k))
            self.voice_client.play(source, after=_after_play)
            await done_event.wait()
            return True
        except Exception as exc:
            LOGGER.warning("Failed to play TTS audio in guild %s: %s", self.guild.id, exc)
            self.is_speaking_output = False
            self.ignore_audio_until = time.monotonic() + 0.2
            return False
        finally:
            self._playback_done_event = None

    async def _send_text_mirror(self, content: str) -> None:
        if not self.text_mirror or self.text_channel is None:
            return
        try:
            for chunk in self.manager.split_response(content):
                await self.text_channel.send(chunk)
        except Exception as exc:
            LOGGER.debug("Could not mirror voice message to text channel: %s", exc)

    async def handle_utterance(self, user: Any, pcm16k: bytes) -> str | None:
        """Transcribe one spoken utterance, generate a reply, and speak it back."""
        if self._closed:
            return None

        async with self.turn_lock:
            if self._closed:
                return None

            duration_s = len(pcm16k) / (STT_SAMPLE_RATE * 2)
            prepared_pcm, raw_rms, raw_peak = prepare_pcm16k_for_stt(pcm16k)
            if not prepared_pcm:
                return None

            try:
                transcript = await asyncio.to_thread(app.transcribe_pcm_bytes, prepared_pcm)
            except Exception as exc:
                LOGGER.warning("Discord voice STT failed: %s", exc)
                return None

            transcript = (transcript or "").strip()
            display_name = getattr(user, "display_name", None) or getattr(user, "name", str(user.id))
            LOGGER.info(
                "Discord voice STT [%s] %s (%.2fs, rms=%.0f, peak=%.0f) -> %r",
                self.guild.name,
                display_name,
                duration_s,
                raw_rms,
                raw_peak,
                transcript,
            )
            norm_low = transcript.lower().strip(" .!?,;:")
            if not transcript or len(norm_low) < 2:
                # Save last unrecognized clip to voice/tmp for easy debugging
                try:
                    import wave
                    from voice import config as voice_config
                    dbg_path = voice_config.TMP_DIR / "last_discord_utterance.wav"
                    with wave.open(str(dbg_path), "wb") as wf:
                        wf.setnchannels(1)
                        wf.setsampwidth(2)
                        wf.setframerate(STT_SAMPLE_RATE)
                        wf.writeframes(prepared_pcm)
                except Exception:
                    pass
                return None
            if norm_low in _NOISE_TRANSCRIPTS and duration_s < 1.2:
                return None

            # Built-in call control phrases
            if _STOP_SPEAKING_RE.match(transcript):
                self.stop_playback()
                return None

            if _LEAVE_CALL_RE.match(transcript):
                bye_msg = "Alright, leaving the voice call. Talk soon!"
                await self._send_text_mirror(f"🎙️ **{display_name}:** {transcript}\n🤖 {bye_msg}")
                await self.speak(bye_msg)
                await self.manager.leave(self.guild.id)
                return bye_msg

            # Route through the unified S.P.I.D.E.Y. prompt pipeline
            reply = await self.manager.generate_voice_reply(
                user_id=user.id,
                prompt=transcript,
                guild_id=self.guild.id,
                text_channel_id=self.text_channel.id if self.text_channel else None,
            )
            if not reply:
                return None

            await self._send_text_mirror(f"🎙️ **{display_name}:** {transcript}\n🤖 {reply}")
            await self.speak(reply)
            return reply

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._watchdog_task is not None and not self._watchdog_task.done():
            self._watchdog_task.cancel()
            try:
                await self._watchdog_task
            except asyncio.CancelledError:
                pass
        try:
            self.stop_playback()
        except Exception:
            pass
        try:
            if hasattr(self.voice_client, "is_listening") and self.voice_client.is_listening():
                self.voice_client.stop_listening()
        except Exception:
            pass
        try:
            self.sink.cleanup()
        except Exception:
            pass
        try:
            if self.voice_client and self.voice_client.is_connected():
                await self.voice_client.disconnect(force=False)
        except Exception as exc:
            LOGGER.debug("Voice disconnect error in guild %s: %s", self.guild.id, exc)


class DiscordVoiceManager:
    """Manages active server voice sessions across guilds for SpideyBot."""

    def __init__(
        self,
        *,
        allowed_user_ids: set[int],
        allowed_guild_ids: set[int],
        split_response: Callable[[str], list[str]],
        clean_reply_text: Callable[[str], str],
        track_chat: Callable[[str, str], None],
        provider_name: str = "discord",
    ) -> None:
        self.allowed_user_ids = allowed_user_ids
        self.allowed_guild_ids = allowed_guild_ids
        self.split_response = split_response
        self.clean_reply_text = clean_reply_text
        self.track_chat = track_chat
        self.provider_name = provider_name
        self.sessions: dict[int, GuildVoiceSession] = {}

    def is_user_allowed(self, user_id: int, guild_id: int | None = None) -> bool:
        if self.allowed_user_ids and user_id not in self.allowed_user_ids:
            return False
        if self.allowed_guild_ids and guild_id is not None and guild_id not in self.allowed_guild_ids:
            return False
        return True

    def get_session(self, guild_id: int) -> GuildVoiceSession | None:
        return self.sessions.get(guild_id)

    async def join(
        self,
        voice_channel: discord.VoiceChannel | discord.StageChannel,
        text_channel: Any | None = None,
        *,
        greet: bool = True,
    ) -> GuildVoiceSession:
        """Connect S.P.I.D.E.Y. to a server voice channel and start two-way listening."""
        if voice_recv is None:
            raise RuntimeError(
                "discord-ext-voice-recv is not installed. Run `pip install discord-ext-voice-recv`."
            )
        if not ensure_opus_loaded():
            raise RuntimeError("Could not load libopus for Discord voice.")

        guild = voice_channel.guild
        existing = self.sessions.get(guild.id)
        if existing is not None:
            if existing.voice_client and existing.voice_client.is_connected():
                if existing.voice_client.channel.id != voice_channel.id:
                    await existing.voice_client.move_to(voice_channel)
                if text_channel is not None:
                    existing.text_channel = text_channel
                existing.start()
                return existing
            await self.leave(guild.id)

        # Clean up any stale guild.voice_client not tracked in self.sessions
        if guild.voice_client is not None:
            try:
                await guild.voice_client.disconnect(force=True)
            except Exception:
                pass

        vc_cls = SpideyVoiceRecvClient or voice_recv.VoiceRecvClient
        vc = await voice_channel.connect(cls=vc_cls, self_deaf=False)
        loop = asyncio.get_running_loop()
        session = GuildVoiceSession(
            manager=self,
            guild=guild,
            voice_client=vc,
            text_channel=text_channel,
            loop=loop,
        )
        self.sessions[guild.id] = session
        session.start()
        LOGGER.info("Joined Discord voice channel '%s' in guild '%s'.", voice_channel.name, guild.name)

        if greet:
            async def _greet_when_ready() -> None:
                await session.wait_for_voice_ready(timeout=2.0)
                await session.speak("Hey! I'm in the call and listening.")
            loop.create_task(_greet_when_ready())
        return session

    async def leave(self, guild_id: int) -> bool:
        session = self.sessions.pop(guild_id, None)
        if session is None:
            return False
        await session.close()
        LOGGER.info("Left Discord voice channel in guild %s.", guild_id)
        return True

    async def disconnect_all(self) -> None:
        for guild_id in list(self.sessions.keys()):
            await self.leave(guild_id)

    def stop_speaking(self, guild_id: int) -> bool:
        session = self.sessions.get(guild_id)
        if session is None:
            return False
        return session.stop_playback()

    async def speak_in_guild(self, guild_id: int, text: str) -> bool:
        """Speak text aloud if S.P.I.D.E.Y. is currently connected to a voice call in guild_id."""
        session = self.sessions.get(guild_id)
        if session is None:
            return False
        async with session.turn_lock:
            return await session.speak(text)

    async def handle_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
        bot_user_id: int | None,
    ) -> None:
        """Auto-leave when everyone else exits the voice channel, or clean up if bot was kicked."""
        guild = member.guild
        session = self.sessions.get(guild.id)
        if session is None:
            return

        # Bot itself disconnected externally (e.g. kicked by an admin)
        if bot_user_id is not None and member.id == bot_user_id and after.channel is None:
            await self.leave(guild.id)
            return

        vc = session.voice_client
        if vc is None or not vc.is_connected() or vc.channel is None:
            await self.leave(guild.id)
            return

        humans = [m for m in vc.channel.members if not getattr(m, "bot", False)]
        if not humans:
            LOGGER.info("No humans left in voice channel '%s'; auto-leaving.", vc.channel.name)
            await self.leave(guild.id)

    async def generate_voice_reply(
        self,
        *,
        user_id: int,
        prompt: str,
        guild_id: int | None = None,
        text_channel_id: int | None = None,
    ) -> str:
        """Run a voice transcript through S.P.I.D.E.Y.'s unified brain (confirmation -> local -> tools)."""
        chat = app.memory_store.get_or_create_external_chat(self.provider_name, str(user_id))
        chat_id = chat["id"]
        self.track_chat(chat_id, str(user_id))

        existing_reminders = {
            r["id"] for r in app.memory_store.list_reminders(active_only=True)
        }

        # 1. Pending destructive confirmation check
        handled, conf_reply, _ = await asyncio.to_thread(
            app.confirmation_mgr.check_and_handle, chat_id, prompt, app.agent_deps
        )
        if handled:
            app.memory_store.add_message(chat_id, "user", prompt)
            app.memory_store.add_message(chat_id, "assistant", conf_reply)
            return conf_reply

        # 2. Rules-first local command handling
        try:
            command = await asyncio.to_thread(app._handle_local_command, prompt, chat_id)
        except ValueError as err:
            return str(err)
        except Exception:
            LOGGER.exception("Discord voice local command failed.")
            return "Something went wrong handling that command."

        if command is not None:
            response, _provider = command
            await self._save_new_reminder_targets(existing_reminders, chat_id, text_channel_id, guild_id, user_id)
            app.memory_store.add_message(chat_id, "user", prompt)
            app.memory_store.add_message(chat_id, "assistant", response)
            return response

        # 3. Native agent tool loop / LLM with concise voice channel budget
        app.memory_store.add_message(chat_id, "user", prompt)
        try:
            await asyncio.to_thread(app.ensure_model_loaded)
            context = app.memory_store.build_context(chat_id, None, prompt)
            history = list(context)
            if history and history[-1].get("role") == "user" and history[-1].get("content") == prompt:
                history.pop()
            memories = app._memories_for_prompt(prompt)
            agent_res = await asyncio.to_thread(
                app.respond_with_tools,
                prompt,
                chat_id,
                history,
                memories,
                "voice",
            )
            response = self.clean_reply_text(agent_res.reply)
        except Exception:
            LOGGER.exception("Discord voice generation failed.")
            return "Sorry, I ran into trouble generating a response right now."

        await self._save_new_reminder_targets(existing_reminders, chat_id, text_channel_id, guild_id, user_id)
        app.memory_store.add_message(chat_id, "assistant", response)
        return response

    async def _save_new_reminder_targets(
        self,
        existing_ids: set[str],
        chat_id: str,
        channel_id: int | None,
        guild_id: int | None,
        user_id: int,
    ) -> None:
        new_reminders = [
            r for r in app.memory_store.list_reminders(active_only=True)
            if r["id"] not in existing_ids and r.get("chat_id") == chat_id
        ]
        for r in new_reminders:
            await asyncio.to_thread(
                app.memory_store.save_reminder_delivery_target,
                r["id"],
                channel_id,
                guild_id,
                user_id,
            )
