"""Unit tests for Discord server voice call integration (audio resampling, VAD, DAVE decrypt, session flow)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np

from services.discord_voice import (
    DISCORD_SAMPLE_RATE,
    STT_SAMPLE_RATE,
    DiscordVoiceManager,
    GuildVoiceSession,
    SpideyVoiceSink,
    _decrypt_dave_opus,
    float32_to_pcm48k_stereo,
    pcm48k_stereo_to_16k_mono,
    pcm_rms,
)


def test_pcm48k_stereo_to_16k_mono_downsampling_ratio_and_rms():
    # Generate 20ms of 48 kHz stereo sine wave (960 samples/channel)
    t = np.arange(960, dtype=np.float32) / DISCORD_SAMPLE_RATE
    wave = (np.sin(2 * np.pi * 440.0 * t) * 12000.0).astype(np.int16)
    stereo = np.stack([wave, wave], axis=1).tobytes()
    assert len(stereo) == 3840

    mono16k = pcm48k_stereo_to_16k_mono(stereo)
    # 960 / 3 = 320 mono int16 samples = 640 bytes
    assert len(mono16k) == 640
    assert pcm_rms(mono16k) > 5000.0


def test_float32_to_pcm48k_stereo_upsamples_24k_to_48k():
    # 0.1s of 24 kHz mono float32 audio = 2400 samples -> 4800 stereo frames (19200 bytes) + 5 frames tail silence
    audio24k = np.linspace(-0.5, 0.5, 2400, dtype=np.float32)
    pcm48k = float32_to_pcm48k_stereo(audio24k, src_rate=24000)
    assert len(pcm48k) % 3840 == 0
    assert len(pcm48k) == 4800 * 4 + 3840 * 5


def test_dave_decrypt_passes_through_when_inactive_and_decrypts_when_ready():
    # 1. No DAVE session -> returns raw opus untouched
    vc_plain = SimpleNamespace(_connection=SimpleNamespace(dave_session=None))
    data, status = _decrypt_dave_opus(vc_plain, 123, b"raw-opus")
    assert data == b"raw-opus"
    assert status == "dave-inactive"

    # 2. Active DAVE session -> calls dave_session.decrypt(user_id, MediaType.audio, opus)
    dave_mock = MagicMock()
    dave_mock.ready = True
    dave_mock.decrypt.return_value = b"decrypted-opus"
    vc_dave = SimpleNamespace(_connection=SimpleNamespace(dave_session=dave_mock))
    data2, status2 = _decrypt_dave_opus(vc_dave, 999, b"encrypted-opus")
    assert data2 == b"decrypted-opus"
    assert status2 == "dave-decrypted"
    dave_mock.decrypt.assert_called_once()


def test_voice_sink_vad_captures_utterance_and_flushes_on_silence():
    dummy_session = MagicMock()
    sink = SpideyVoiceSink(
        dummy_session,
        energy_threshold=300.0,
        silence_timeout_s=0.6,
        min_speech_s=0.2,
    )
    assert sink.wants_opus() is True

    user = SimpleNamespace(id=42, bot=False, display_name="Jaya")
    # 20ms @ 16kHz mono = 320 samples = 640 bytes
    loud_frame = (np.ones(320, dtype=np.int16) * 2500).tobytes()
    quiet_frame = np.zeros(320, dtype=np.int16).tobytes()

    # Pre-roll silence
    assert sink.feed_pcm16k(user, quiet_frame, now=0.0) is None
    # 12 frames (240ms) of speech
    for i in range(12):
        assert sink.feed_pcm16k(user, loud_frame, now=0.1 + i * 0.02) is None

    # Watchdog flush before timeout -> nothing yet
    assert sink.flush_timed_out_users(now=0.5) == []
    # Watchdog flush past 0.6s silence timeout (handles Discord DTX!)
    flushed = sink.flush_timed_out_users(now=1.1)
    assert len(flushed) == 1
    flushed_user, pcm = flushed[0]
    assert flushed_user.id == 42
    assert len(pcm) >= int(STT_SAMPLE_RATE * 2 * 0.2)


def test_voice_session_handles_utterance_and_speaks_reply(temp_db):
    async def _run():
        manager = DiscordVoiceManager(
            allowed_user_ids={101},
            allowed_guild_ids=set(),
            split_response=lambda s: [s],
            clean_reply_text=lambda s: s,
            track_chat=lambda cid, uid: None,
        )
        temp_db.create_task("learning C++ basics", priority="medium")

        guild = SimpleNamespace(id=555, name="Test Server")
        vc = MagicMock()
        vc.is_connected.return_value = True
        vc.is_playing.return_value = False
        vc.is_listening.return_value = False
        text_channel = AsyncMock()
        loop = asyncio.get_running_loop()

        session = GuildVoiceSession(manager, guild, vc, text_channel, loop, text_mirror=True)
        session.speak = AsyncMock(return_value=True)

        user = SimpleNamespace(id=101, bot=False, display_name="Jaya")
        fake_pcm = (np.ones(STT_SAMPLE_RATE, dtype=np.int16) * 2000).tobytes()

        with patch("app.transcribe_pcm_bytes", return_value="list my tasks"):
            reply = await session.handle_utterance(user, fake_pcm)

        assert reply is not None
        assert "learning C++ basics" in reply
        session.speak.assert_awaited_once_with(reply)
        text_channel.send.assert_awaited()

    asyncio.run(_run())


def test_voice_auto_leave_when_channel_empty():
    async def _run():
        manager = DiscordVoiceManager(
            allowed_user_ids=set(),
            allowed_guild_ids=set(),
            split_response=lambda s: [s],
            clean_reply_text=lambda s: s,
            track_chat=lambda cid, uid: None,
        )
        bot_member = SimpleNamespace(id=1, bot=True)
        human_member = SimpleNamespace(id=2, bot=False, guild=SimpleNamespace(id=777, name="Guild"))
        vc = AsyncMock()
        vc.is_connected = MagicMock(return_value=True)
        vc.is_playing = MagicMock(return_value=False)
        vc.is_listening = MagicMock(return_value=False)
        vc.channel = SimpleNamespace(name="General", members=[bot_member])

        session = GuildVoiceSession(
            manager, human_member.guild, vc, None, asyncio.get_running_loop()
        )
        manager.sessions[777] = session

        await manager.handle_voice_state_update(
            human_member,
            SimpleNamespace(channel=vc.channel),
            SimpleNamespace(channel=None),
            bot_user_id=1,
        )
        assert 777 not in manager.sessions
        vc.disconnect.assert_awaited_once()

    asyncio.run(_run())


def test_davey_02_welcome_and_execute_transition_hooks():
    """Verify _SpideyVoiceWebSocket calls prepare_transition + execute_transition for davey 0.2.x."""
    import struct
    from services.discord_voice import _SpideyVoiceWebSocket, _SpideyVoiceConnectionState

    async def _run():
        dave_mock = MagicMock()
        dave_mock.ready = True
        dave_mock.epoch = 1
        dave_mock.process_commit.return_value = True
        dave_mock.execute_transition.return_value = True

        state = SimpleNamespace(
            dave_session=dave_mock,
            dave_protocol_version=1,
            dave_pending_transitions={},
            can_encrypt=True,
            _recover_from_invalid_commit=AsyncMock(),
        )

        ws = object.__new__(_SpideyVoiceWebSocket)
        ws._connection = state
        ws.seq_ack = 0
        ws.send_transition_ready = AsyncMock()

        # 1. MLS_WELCOME with transition_id = 0 -> must prepare_transition(0, 1) and execute_transition(0)
        welcome_msg = struct.pack(">HBH", 1, _SpideyVoiceWebSocket.MLS_WELCOME, 0) + b"welcome-bytes"
        await ws.received_binary_message(welcome_msg)
        dave_mock.process_welcome.assert_called_once_with(b"welcome-bytes")
        dave_mock.prepare_transition.assert_called_once_with(0, 1)
        dave_mock.execute_transition.assert_called_once_with(0)

        # 2. MLS_ANNOUNCE_COMMIT_TRANSITION with transition_id = 7 -> prepares & sends transition_ready
        dave_mock.reset_mock()
        dave_mock.process_commit.return_value = True
        commit_msg = struct.pack(">HBH", 2, _SpideyVoiceWebSocket.MLS_ANNOUNCE_COMMIT_TRANSITION, 7) + b"commit-bytes"
        await ws.received_binary_message(commit_msg)
        dave_mock.process_commit.assert_called_once_with(b"commit-bytes")
        dave_mock.prepare_transition.assert_called_once_with(7, 1)
        assert state.dave_pending_transitions[7] == 1
        ws.send_transition_ready.assert_awaited_once_with(7)

    asyncio.run(_run())
