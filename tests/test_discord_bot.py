"""Tests for Discord bot text commands and reminder delivery."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest


def test_reminder_delivery_target_storage_in_memory_store(tmp_path):
    from memory import MemoryStore
    db_file = tmp_path / "test_reminders.db"
    store = MemoryStore(db_file)

    # Test initial retrieval
    assert store.get_reminder_delivery_target("rem-1") is None

    # Test save
    store.save_reminder_delivery_target("rem-1", channel_id=123, guild_id=456, user_id=789)
    target = store.get_reminder_delivery_target("rem-1")
    assert target is not None
    assert target["channel_id"] == 123
    assert target["guild_id"] == 456
    assert target["user_id"] == 789

    # Test upsert
    store.save_reminder_delivery_target("rem-1", channel_id=999, guild_id=456, user_id=789)
    target2 = store.get_reminder_delivery_target("rem-1")
    assert target2["channel_id"] == 999


def test_server_channel_reminder_delivery_routes_to_channel():
    async def _test():
        import discord
        import discord_bot

        mock_channel = AsyncMock(spec=discord.TextChannel)
        mock_channel.send = AsyncMock()

        bot = discord_bot.bot
        bot.send_dm = AsyncMock()

        mock_notification = {
            "id": 10,
            "chat_id": "test-chat-1",
            "reminder_id": "rem-server-1",
            "content": "Just a nudge: sleep. It's 10:08 PM right now.",
        }

        mock_target = {
            "reminder_id": "rem-server-1",
            "channel_id": 555,
            "guild_id": 777,
            "user_id": 9999,
        }

        with patch.object(bot, "get_channel", return_value=mock_channel):
            with patch("app.memory_store.get_reminder_delivery_target", return_value=mock_target):
                with patch("app.memory_store.list_notifications", return_value=[mock_notification]):
                    with patch("app.memory_store.add_message"):
                        saved_chats = dict(bot.discord_chats)
                        saved_ids = dict(bot.last_notification_id)
                        try:
                            bot.discord_chats.clear()
                            bot.last_notification_id.clear()
                            bot.discord_chats["test-chat-1"] = "9999"
                            bot.last_notification_id["test-chat-1"] = 0

                            # Run deliver_notifications for one iteration
                            with patch("asyncio.sleep", side_effect=[None, asyncio.CancelledError]):
                                with patch.object(bot, "wait_until_ready", new_callable=AsyncMock):
                                    try:
                                        await bot.deliver_notifications()
                                    except asyncio.CancelledError:
                                        pass
                        finally:
                            bot.discord_chats = saved_chats
                            bot.last_notification_id = saved_ids

                        # Server channel MUST receive the message mentioning the user
                        mock_channel.send.assert_called_once_with("<@9999> Just a nudge: sleep. It's 10:08 PM right now.")
                        # send_dm MUST NOT have been called
                        bot.send_dm.assert_not_called()

    asyncio.run(_test())


def test_dm_reminder_delivery_routes_to_dm():
    async def _test():
        import discord_bot

        bot = discord_bot.bot
        bot.send_dm = AsyncMock()

        mock_notification = {
            "id": 11,
            "chat_id": "test-chat-2",
            "reminder_id": "rem-dm-1",
            "content": "Just a nudge: dinner. It's 9:36 PM right now.",
        }

        # Target has no guild/channel (DM reminder)
        mock_target = {
            "reminder_id": "rem-dm-1",
            "channel_id": None,
            "guild_id": None,
            "user_id": 8888,
        }

        with patch("app.memory_store.get_reminder_delivery_target", return_value=mock_target):
            with patch("app.memory_store.list_notifications", return_value=[mock_notification]):
                with patch("app.memory_store.add_message"):
                    saved_chats = dict(bot.discord_chats)
                    saved_ids = dict(bot.last_notification_id)
                    try:
                        bot.discord_chats.clear()
                        bot.last_notification_id.clear()
                        bot.discord_chats["test-chat-2"] = "8888"
                        bot.last_notification_id["test-chat-2"] = 0

                        with patch("asyncio.sleep", side_effect=[None, asyncio.CancelledError]):
                            with patch.object(bot, "wait_until_ready", new_callable=AsyncMock):
                                try:
                                    await bot.deliver_notifications()
                                except asyncio.CancelledError:
                                    pass
                    finally:
                        bot.discord_chats = saved_chats
                        bot.last_notification_id = saved_ids

                    # send_dm MUST be called for DM reminder
                    bot.send_dm.assert_called_once_with(8888, "Just a nudge: dinner. It's 9:36 PM right now.")

    asyncio.run(_test())


def test_discord_server_text_message_works():
    """Verify that messages in server text channels work normally as text prompts."""
    async def _test():
        import discord_bot

        mock_msg = MagicMock()
        mock_msg.author.bot = False
        mock_msg.content = "set reminder at 22:08 for sleep"
        mock_msg.guild.id = 777
        mock_msg.channel.id = 555
        mock_msg.mentions = []

        with patch.object(discord_bot.bot, "respond_to_prompt", new_callable=AsyncMock) as mock_respond:
            await discord_bot.on_message(mock_msg)
            mock_respond.assert_called_once_with(mock_msg, "set reminder at 22:08 for sleep")

    asyncio.run(_test())


def test_respond_to_prompt_sends_text_reply():
    """Verify that a prompt reply delivers text reply directly without voice."""
    async def _test():
        import discord
        import discord_bot

        mock_author = MagicMock(spec=discord.Member)
        mock_author.id = 12345
        mock_author.bot = False

        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 777
        mock_author.guild = mock_guild

        mock_msg = MagicMock(spec=discord.Message)
        mock_msg.author = mock_author
        mock_msg.guild = mock_guild
        mock_msg.reply = AsyncMock()

        assert not hasattr(discord_bot.bot, "voice")

        with patch.object(discord_bot.bot, "is_allowed", return_value=True):
            with patch("app.memory_store.get_or_create_external_chat", return_value={"id": "chat-text-1"}):
                with patch("app.memory_store.list_reminders", return_value=[]):
                    with patch("app.confirmation_mgr.check_and_handle", return_value=(False, None, None)):
                        with patch("app._handle_local_command", return_value=("I am S.P.I.D.E.Y., standing by.", "local")):
                            with patch("app.memory_store.add_message"):
                                reply = await discord_bot.bot.respond_to_prompt(mock_msg, "who are you")

                                assert reply == "I am S.P.I.D.E.Y., standing by."
                                mock_msg.reply.assert_called_once_with("I am S.P.I.D.E.Y., standing by.")

    asyncio.run(_test())


def test_proactive_recommendation_routes_to_server_channel_and_speaks_in_voice_call():
    """Proactive check-ins (target=None) route to the server channel and speak aloud if in a voice call."""
    async def _test():
        import discord
        import discord_bot

        mock_channel = AsyncMock(spec=discord.TextChannel)
        mock_channel.id = 444
        mock_channel.send = AsyncMock()

        bot = discord_bot.bot
        bot.send_dm = AsyncMock()

        mock_notification = {
            "id": 25,
            "chat_id": "test-chat-coach",
            "reminder_id": "task-coach-learning-discord-abc",
            "content": "Study push: Control Flow in C++ with DSA is queued up next.",
        }

        mock_vc = MagicMock()
        mock_vc.is_connected.return_value = True
        mock_vc.channel = MagicMock(members=[MagicMock(id=9999)])
        mock_session = MagicMock()
        mock_session.guild = MagicMock(id=777)
        mock_session.text_channel = mock_channel
        mock_session.voice_client = mock_vc

        bot.voice_manager.sessions[777] = mock_session
        orig_speak = bot.voice_manager.speak_in_guild
        bot.voice_manager.speak_in_guild = AsyncMock(return_value=True)

        try:
            with patch.object(bot, "get_channel", return_value=mock_channel):
                with patch("app.memory_store.get_reminder_delivery_target", return_value=None):
                    with patch("app.memory_store.list_notifications", return_value=[mock_notification]):
                        with patch("app.memory_store.add_message"):
                            with patch("app.memory_store.set_external_last_notification_id"):
                                saved_chats = dict(bot.discord_chats)
                                saved_ids = dict(bot.last_notification_id)
                                try:
                                    bot.discord_chats.clear()
                                    bot.last_notification_id.clear()
                                    bot.discord_chats["test-chat-coach"] = "9999"
                                    bot.last_notification_id["test-chat-coach"] = 0

                                    with patch("asyncio.sleep", side_effect=[None, asyncio.CancelledError]):
                                        with patch.object(bot, "wait_until_ready", new_callable=AsyncMock):
                                            try:
                                                await bot.deliver_notifications()
                                            except asyncio.CancelledError:
                                                pass
                                    await asyncio.sleep(0)
                                finally:
                                    bot.discord_chats = saved_chats
                                    bot.last_notification_id = saved_ids

            mock_channel.send.assert_called_once_with(
                "<@9999> Study push: Control Flow in C++ with DSA is queued up next."
            )
            bot.send_dm.assert_not_called()
            bot.voice_manager.speak_in_guild.assert_awaited_once_with(
                777, "Study push: Control Flow in C++ with DSA is queued up next."
            )
        finally:
            bot.voice_manager.sessions.pop(777, None)
            bot.voice_manager.speak_in_guild = orig_speak

    asyncio.run(_test())


def test_discord_context_auto_resets_every_3_days_and_preserves_data(temp_db, monkeypatch):
    """Discord chat messages auto-clear once >= 3 days old while keeping memories, tasks & session link."""
    from datetime import datetime, timedelta, timezone
    import discord_bot

    monkeypatch.setenv("AI_DISCORD_CONTEXT_RESET_DAYS", "3")

    chat = temp_db.get_or_create_external_chat("discord", "55555")
    cid = chat["id"]
    temp_db.add_memory("My favorite language is Python.")
    temp_db.create_task("Keep this task safe", priority="high")
    temp_db.add_message(cid, "user", "Old topic from 2 days ago")
    temp_db.add_message(cid, "assistant", "Recent reply")

    # 2 days old -> should NOT clear yet
    two_days_ago = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    with temp_db.connect() as conn:
        conn.execute("UPDATE messages SET created_at = ? WHERE conversation_id = ?", (two_days_ago, cid))

    assert discord_bot._reset_stale_discord_contexts() == {}
    assert len(temp_db.get_messages(cid)) == 2

    # 3.1 days old -> MUST clear Discord chat context automatically
    over_three_days = (datetime.now(timezone.utc) - timedelta(days=3, hours=2)).isoformat()
    with temp_db.connect() as conn:
        conn.execute(
            "UPDATE messages SET created_at = ? WHERE conversation_id = ? AND role = 'user'",
            (over_three_days, cid),
        )

    cleared = discord_bot._reset_stale_discord_contexts()
    assert cleared == {cid: 2}
    assert temp_db.get_messages(cid) == []
    # Session link, memories, and tasks remain intact
    assert temp_db.get_or_create_external_chat("discord", "55555")["id"] == cid
    assert len(temp_db.list_memories()) == 1
    assert len(temp_db.list_tasks()) == 1


def test_discord_manual_reset_command_clears_chat_context(temp_db, monkeypatch):
    """!reset immediately clears the caller's Discord chat messages while preserving saved data."""
    import discord_bot

    monkeypatch.setattr(discord_bot.bot, "allowed_user_ids", set())
    monkeypatch.setattr(discord_bot.bot, "allowed_guild_ids", set())

    chat = temp_db.get_or_create_external_chat("discord", "77777")
    cid = chat["id"]
    temp_db.add_message(cid, "user", "Hello")
    temp_db.add_message(cid, "assistant", "Hi there")
    assert len(temp_db.get_messages(cid)) == 2

    ctx = MagicMock()
    ctx.author = MagicMock(id=77777)
    ctx.message = MagicMock(author=ctx.author, guild=None)
    ctx.reply = AsyncMock()

    asyncio.run(discord_bot.reset_context_command.callback(ctx))

    assert temp_db.get_messages(cid) == []
    ctx.reply.assert_awaited_once()
    assert "Cleared your Discord chat context (2 message(s) removed)" in ctx.reply.call_args[0][0]


