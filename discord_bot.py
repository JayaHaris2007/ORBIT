"""Discord gateway for the local assistant.

The bot shares the same task, habit, and reminder commands as the web chat,
falling back to conversation generation for everything else. Tokens and access
controls are read from the process environment.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import socket
import time
from typing import Any

import discord
from discord.ext import commands

import app
from services.discord_voice import DiscordVoiceManager

LOGGER = logging.getLogger("spidey.discord")
DISCORD_PROVIDER = "discord"
DISCORD_MAX_MESSAGE_LENGTH = 2_000
DISCORD_NOTIFICATION_POLL_SECONDS = 5
DISCORD_LOCK_PORT = 47653


_single_instance_guard: socket.socket | None = None


def _acquire_single_instance() -> socket.socket:
    """Refuse to start when another bot process already owns the lock port."""
    global _single_instance_guard
    if _single_instance_guard is not None:
        return _single_instance_guard
    guard = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    guard.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        guard.bind(("127.0.0.1", DISCORD_LOCK_PORT))
        guard.listen(1)
        _single_instance_guard = guard
    except OSError as error:
        guard.close()
        raise SystemExit(
            "Another discord_bot.py instance is already running. Stop it before "
            "starting a new one."
        ) from error
    return guard


def _release_single_instance() -> None:
    global _single_instance_guard
    if _single_instance_guard is not None:
        try:
            _single_instance_guard.close()
        except Exception as e:
            LOGGER.warning("Error closing single-instance guard socket: %s", e)
        _single_instance_guard = None


def _parse_id_allowlist(name: str) -> set[int]:
    raw_value = os.environ.get(name, "")
    values: set[int] = set()
    for item in raw_value.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            values.add(int(item))
        except ValueError as error:
            raise RuntimeError(f"{name} contains an invalid Discord ID.") from error
    return values


def _split_response(response: str) -> list[str]:
    response = response.strip()
    if not response:
        return ["I generated an empty response."]
    if len(response) <= DISCORD_MAX_MESSAGE_LENGTH:
        return [response]

    chunks: list[str] = []
    max_len = 1900
    remaining = response

    while remaining:
        if len(remaining) <= max_len:
            chunks.append(remaining)
            break

        window = remaining[:max_len]
        para_pos = window.rfind("\n\n")
        if para_pos > max_len // 3:
            split_pos = para_pos + 2
        else:
            newline_pos = window.rfind("\n")
            if newline_pos > max_len // 3:
                split_pos = newline_pos + 1
            else:
                sent_pos = window.rfind(". ")
                if sent_pos > max_len // 3:
                    split_pos = sent_pos + 2
                else:
                    space_pos = window.rfind(" ")
                    if space_pos > max_len // 3:
                        split_pos = space_pos + 1
                    else:
                        split_pos = max_len

        chunk = remaining[:split_pos].strip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[split_pos:].strip()

    return chunks or ["I generated an empty response."]


# The local model sometimes writes keycap numbers with stray combining marks,
# dingbats or braille (1️⃣, 2️⃝, 4️⠁), which Discord shows as broken glyphs.
# The web panel cleans these at render time; Discord has no such layer.
_BROKEN_LIST_MARKER = re.compile(
    r"(?m)^[ \t]*(\d{1,2})"
    r"[\ufe0f\u20d0-\u20ff\u2460-\u24ff\u2700-\u27bf\u2800-\u28ff]+"
    r"[ \t]*(?=\S)"
)
_INVISIBLE_MARKS = re.compile(
    r"[\ufe00-\ufe0f\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufffd]"
)


def _clean_reply_text(text: str) -> str:
    text = _BROKEN_LIST_MARKER.sub(r"\1. ", text)
    text = _INVISIBLE_MARKS.sub("", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


class SpideyBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.voice_states = True
        super().__init__(
            command_prefix=os.environ.get("AI_DISCORD_PREFIX", "!"),
            intents=intents,
            help_command=None,
        )
        self.allowed_user_ids = _parse_id_allowlist("AI_DISCORD_ALLOWED_USER_IDS")
        self.allowed_guild_ids = _parse_id_allowlist("AI_DISCORD_ALLOWED_GUILD_IDS")
        self.discord_chats: dict[str, str] = {}
        self.last_notification_id: dict[str, int] = {}
        self.voice_manager = DiscordVoiceManager(
            allowed_user_ids=self.allowed_user_ids,
            allowed_guild_ids=self.allowed_guild_ids,
            split_response=_split_response,
            clean_reply_text=_clean_reply_text,
            track_chat=self.track_chat,
            provider_name=DISCORD_PROVIDER,
        )

    async def setup_hook(self) -> None:
        for chat in app.memory_store.list_external_chats(DISCORD_PROVIDER):
            self.track_chat(chat["id"], str(chat["external_user_id"]))
        # Ensure allowed Discord user IDs are tracked even after a fresh DB reset
        for uid in self.allowed_user_ids:
            try:
                ext_chat = app.memory_store.get_or_create_external_chat(DISCORD_PROVIDER, str(uid))
                self.track_chat(ext_chat["id"], str(uid))
            except Exception as err:
                LOGGER.warning("Could not pre-register Discord user %s: %s", uid, err)
        app._restore_reminders(provider=DISCORD_PROVIDER)
        ready = app.init_learning_module(DISCORD_PROVIDER)
        app.schedule_proactive_coach(DISCORD_PROVIDER)
        LOGGER.info(
            "Learning module %s; Discord weekly nudge %s; proactive coach scheduled.",
            "initialized" if ready else "NOT available",
            "scheduled" if ready else "not scheduled",
        )
        asyncio.create_task(self.deliver_notifications())
        LOGGER.info(
            "Discord command registry initialized; tracking %d chat(s).",
            len(self.discord_chats),
        )

    def track_chat(self, chat_id: str, external_user_id: str) -> None:
        if chat_id in self.discord_chats:
            return
        self.discord_chats[chat_id] = external_user_id
        stored_last_id = app.memory_store.get_external_last_notification_id(chat_id)
        self.last_notification_id[chat_id] = stored_last_id

    async def remember_server_channel(
        self, user_id: int, guild_id: int | None, channel_id: int | None
    ) -> None:
        """Persist the user's most recent server text channel for proactive server notifications."""
        if not guild_id or not channel_id:
            return
        try:
            await asyncio.to_thread(
                app.memory_store.save_reminder_delivery_target,
                f"discord-default-channel:{user_id}",
                channel_id,
                guild_id,
                user_id,
            )
        except Exception as exc:
            LOGGER.debug("Could not remember default server channel for user %s: %s", user_id, exc)

    async def _resolve_server_notification_target(self, user_id: int) -> dict[str, Any] | None:
        """Pick a Discord server text channel for proactive recommendations/check-ins."""
        # 1. If S.P.I.D.E.Y. is currently in a voice call with this user, use that call's text channel
        for session in list(self.voice_manager.sessions.values()):
            vc = session.voice_client
            if not vc or not vc.is_connected() or session.text_channel is None:
                continue
            members = getattr(getattr(vc, "channel", None), "members", []) or []
            if any(getattr(m, "id", None) == user_id for m in members) or len(self.voice_manager.sessions) == 1:
                return {
                    "guild_id": session.guild.id,
                    "channel_id": session.text_channel.id,
                    "user_id": user_id,
                }

        # 2. Optional explicit channel override via environment variable
        env_ch = os.environ.get("AI_DISCORD_NOTIFY_CHANNEL_ID", "").strip()
        if env_ch.isdigit():
            ch_obj = self.get_channel(int(env_ch))
            if ch_obj is None:
                try:
                    ch_obj = await self.fetch_channel(int(env_ch))
                except Exception:
                    ch_obj = None
            if ch_obj is not None and getattr(ch_obj, "guild", None) is not None:
                return {
                    "guild_id": ch_obj.guild.id,
                    "channel_id": ch_obj.id,
                    "user_id": user_id,
                }

        # 3. Last server text channel the user interacted in (persisted in SQLite)
        try:
            saved = await asyncio.to_thread(
                app.memory_store.get_reminder_delivery_target,
                f"discord-default-channel:{user_id}",
            )
            if saved and saved.get("guild_id") and saved.get("channel_id"):
                return {
                    "guild_id": saved["guild_id"],
                    "channel_id": saved["channel_id"],
                    "user_id": user_id,
                }
        except Exception as exc:
            LOGGER.debug("Could not read default server channel for user %s: %s", user_id, exc)

        # 4. Fallback: pick a writable text channel in a server S.P.I.D.E.Y. is connected to
        guilds = list(self.guilds or [])
        if self.allowed_guild_ids:
            allowed_first = [g for g in guilds if g.id in self.allowed_guild_ids]
            if allowed_first:
                guilds = allowed_first
        for guild in guilds:
            me = getattr(guild, "me", None)
            candidates: list[discord.TextChannel] = []
            sys_ch = getattr(guild, "system_channel", None)
            if isinstance(sys_ch, discord.TextChannel):
                candidates.append(sys_ch)
            text_channels = list(getattr(guild, "text_channels", []) or [])
            # Prefer channels named spidey or general
            preferred = [
                ch for ch in text_channels
                if any(k in ch.name.lower() for k in ("spidey", "general", "bot", "chat"))
            ]
            for ch in (*preferred, *text_channels):
                if ch not in candidates:
                    candidates.append(ch)
            for ch in candidates:
                try:
                    if me is None or ch.permissions_for(me).send_messages:
                        return {
                            "guild_id": guild.id,
                            "channel_id": ch.id,
                            "user_id": user_id,
                        }
                except Exception:
                    continue
        return None

    def _announce_in_active_voice_call(
        self, user_id: int, content: str, preferred_guild_id: int | None = None
    ) -> bool:
        """If S.P.I.D.E.Y. is in a voice call in the user's server, speak the notification aloud."""
        if preferred_guild_id is not None and self.voice_manager.get_session(preferred_guild_id) is not None:
            asyncio.create_task(self.voice_manager.speak_in_guild(preferred_guild_id, content))
            return True
        for guild_id, session in list(self.voice_manager.sessions.items()):
            vc = session.voice_client
            if not vc or not vc.is_connected():
                continue
            members = getattr(getattr(vc, "channel", None), "members", []) or []
            if any(getattr(m, "id", None) == user_id for m in members) or (
                not self.allowed_guild_ids or guild_id in self.allowed_guild_ids
            ):
                asyncio.create_task(self.voice_manager.speak_in_guild(guild_id, content))
                return True
        return False

    async def deliver_notifications(self) -> None:
        """Poll the shared database and deliver reminders to server channels or DMs."""
        await self.wait_until_ready()
        while not self.is_closed():
            try:
                await asyncio.sleep(DISCORD_NOTIFICATION_POLL_SECONDS)
                for chat_id, external_user_id in list(self.discord_chats.items()):
                    last_id = self.last_notification_id.get(chat_id, 0)
                    try:
                        notifications = await asyncio.to_thread(
                            app.memory_store.list_notifications, chat_id, last_id
                        )
                    except Exception:
                        LOGGER.exception(
                            "Could not read notifications for chat %s.", chat_id
                        )
                        continue
                    for notification in notifications:
                        content = notification["content"].strip()
                        if not content:
                            self.last_notification_id[chat_id] = notification["id"]
                            app.memory_store.set_external_last_notification_id(chat_id, notification["id"])
                            continue

                        reminder_id = notification.get("reminder_id")
                        target = None
                        if reminder_id:
                            try:
                                target = await asyncio.to_thread(
                                    app.memory_store.get_reminder_delivery_target,
                                    reminder_id,
                                )
                            except Exception as e:
                                LOGGER.warning("Could not fetch reminder target for %s: %s", reminder_id, e)

                        # Proactive recommendations / check-ins / nudges have no explicit delivery target row;
                        # route them to the Discord server channel when the bot is in a server!
                        if target is None:
                            try:
                                target = await self._resolve_server_notification_target(int(external_user_id))
                            except Exception as e:
                                LOGGER.debug("Server notification target resolution failed: %s", e)

                        delivered = False  # noqa: must be before all branches
                        if target and target.get("channel_id") and target.get("guild_id"):
                            guild_id = target["guild_id"]
                            channel_id = target["channel_id"]
                            user_id = target["user_id"]

                            channel = self.get_channel(channel_id)
                            if channel is None:
                                try:
                                    channel = await self.fetch_channel(channel_id)
                                except Exception as err:
                                    LOGGER.warning("Could not fetch channel %s: %s", channel_id, err)
                                    channel = None

                            guild = self.get_guild(guild_id)
                            if guild is None:
                                try:
                                    guild = await self.fetch_guild(guild_id)
                                except Exception as err:
                                    LOGGER.warning("Could not fetch guild %s: %s", guild_id, err)
                                    guild = None

                            member = None
                            if guild is not None:
                                member = guild.get_member(user_id)
                                if member is None:
                                    try:
                                        member = await guild.fetch_member(user_id)
                                    except Exception as err:
                                        LOGGER.warning("Could not fetch member %s in guild %s: %s", user_id, guild_id, err)
                                        member = None

                            if channel is not None and isinstance(
                                channel, (discord.TextChannel, discord.Thread)
                            ):
                                try:
                                    user_mention = f"<@{user_id}>"
                                    server_msg = f"{user_mention} {content}"
                                    for chunk in _split_response(server_msg):
                                        await channel.send(chunk)

                                    self.last_notification_id[chat_id] = notification["id"]
                                    app.memory_store.set_external_last_notification_id(chat_id, notification["id"])
                                    LOGGER.info(
                                        "Delivered notification %s to server channel %s for user %s.",
                                        notification["id"],
                                        channel_id,
                                        user_id,
                                    )
                                    delivered = True
                                    # If S.P.I.D.E.Y. is currently in a voice call, also speak the recommendation/reminder aloud
                                    self._announce_in_active_voice_call(int(user_id), content, preferred_guild_id=guild_id)
                                    try:
                                        await asyncio.to_thread(
                                            app.memory_store.add_message,
                                            chat_id,
                                            "assistant",
                                            content,
                                        )
                                    except Exception as e:
                                        LOGGER.warning("Could not record assistant reminder message for chat %s: %s", chat_id, e)
                                except discord.Forbidden:
                                    LOGGER.warning(
                                        "Cannot send notification %s to channel %s (forbidden); falling back to DM.",
                                        notification["id"],
                                        channel_id,
                                    )
                                except Exception:
                                    LOGGER.exception(
                                        "Could not deliver notification %s to channel %s; falling back to DM.",
                                        notification["id"],
                                        channel_id,
                                    )
    
                        if not delivered:
                            try:
                                await self.send_dm(int(external_user_id), content)
                                self.last_notification_id[chat_id] = notification["id"]
                                app.memory_store.set_external_last_notification_id(chat_id, notification["id"])
                                LOGGER.info(
                                    "Delivered notification %s to user %s via DM.",
                                    notification["id"],
                                    external_user_id,
                                )
                                self._announce_in_active_voice_call(int(external_user_id), content)
                                try:
                                    await asyncio.to_thread(
                                        app.memory_store.add_message,
                                        chat_id,
                                        "assistant",
                                        content,
                                    )
                                except Exception as e:
                                    LOGGER.warning("Could not record assistant reminder message for chat %s: %s", chat_id, e)
                            except discord.Forbidden:
                                self.last_notification_id[chat_id] = notification["id"]
                                app.memory_store.set_external_last_notification_id(chat_id, notification["id"])
                                LOGGER.warning(
                                    "Cannot DM notification %s to user %s; DMs are closed.",
                                    notification["id"],
                                    external_user_id,
                                )
                            except Exception:
                                LOGGER.exception(
                                    "Could not deliver notification %s.",
                                    notification["id"],
                                )
            except asyncio.CancelledError:
                break
            except Exception:
                LOGGER.exception("Unexpected error in deliver_notifications loop.")

    async def send_dm(self, user_id: int, content: str) -> None:
        user = self.get_user(user_id)
        if user is None:
            user = await self.fetch_user(user_id)
        for chunk in _split_response(content):
            await user.send(chunk)

    async def on_ready(self) -> None:
        if self.user is not None:
            LOGGER.info("Discord bot connected as %s (%s).", self.user, self.user.id)

    def is_allowed(self, message: discord.Message) -> bool:
        if self.allowed_user_ids and message.author.id not in self.allowed_user_ids:
            return False
        if (
            self.allowed_guild_ids
            and message.guild is not None
            and message.guild.id not in self.allowed_guild_ids
        ):
            return False
        return True

    async def respond_to_prompt(
        self, message: discord.Message, prompt: str
    ) -> None:
        prompt = prompt.strip()
        if not prompt:
            await message.reply("Use `!ask <message>` or `!input <message>` or mention me with a question.")
            return
        if len(prompt) > app.MAX_PROMPT_CHARS:
            await message.reply(
                f"That message is too long. Keep it under {app.MAX_PROMPT_CHARS} characters."
            )
            return
        if not self.is_allowed(message):
            LOGGER.warning(
                "Rejected Discord request from user=%s guild=%s.",
                message.author.id,
                message.guild.id if message.guild else "dm",
            )
            await message.reply("You are not authorized to use this assistant.")
            return

        LOGGER.info(
            "Discord prompt from user=%s guild=%s chars=%d",
            message.author.id,
            message.guild.id if message.guild else "dm",
            len(prompt),
        )

        chat = app.memory_store.get_or_create_external_chat(
            DISCORD_PROVIDER, str(message.author.id)
        )
        chat_id = chat["id"]
        self.track_chat(chat_id, str(message.author.id))
        if message.guild is not None:
            await self.remember_server_channel(message.author.id, message.guild.id, message.channel.id)

        existing_reminders = {
            r["id"] for r in app.memory_store.list_reminders(active_only=True)
        }

        handled, conf_reply, _ = await asyncio.to_thread(
            app.confirmation_mgr.check_and_handle, chat_id, prompt, app.agent_deps
        )
        if handled:
            app.memory_store.add_message(chat_id, "user", prompt)
            app.memory_store.add_message(chat_id, "assistant", conf_reply)
            for chunk in _split_response(conf_reply):
                await message.reply(chunk)
            return conf_reply

        try:
            command = await asyncio.to_thread(
                app._handle_local_command, prompt, chat_id
            )
        except ValueError as error:
            await message.reply(str(error))
            return
        except Exception:
            LOGGER.exception("Discord command handling failed.")
            await message.reply("Something went wrong handling that command.")
            return

        if command is not None:
            response, provider = command
            LOGGER.info("Answered locally with %s.", provider)
            new_reminders = [
                r for r in app.memory_store.list_reminders(active_only=True)
                if r["id"] not in existing_reminders and r.get("chat_id") == chat_id
            ]
            for r in new_reminders:
                channel_id = message.channel.id if message.guild is not None else None
                guild_id = message.guild.id if message.guild is not None else None
                await asyncio.to_thread(
                    app.memory_store.save_reminder_delivery_target,
                    r["id"],
                    channel_id,
                    guild_id,
                    message.author.id,
                )
            app.memory_store.add_message(chat_id, "user", prompt)
            app.memory_store.add_message(chat_id, "assistant", response)
            for chunk in _split_response(response):
                await message.reply(chunk)
            return response

        app.memory_store.add_message(chat_id, "user", prompt)
        try:
            async with message.channel.typing():
                await asyncio.to_thread(app.ensure_model_loaded)
                context = app.memory_store.build_context(
                    chat_id, None, prompt
                )
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
                    "discord",
                )
                response = agent_res.reply
        except ValueError as error:
            await message.reply(str(error))
            return
        except Exception:
            LOGGER.exception("Discord generation failed.")
            await message.reply("I could not generate a response right now.")
            return

        new_reminders = [
            r for r in app.memory_store.list_reminders(active_only=True)
            if r["id"] not in existing_reminders and r.get("chat_id") == chat_id
        ]
        for r in new_reminders:
            channel_id = message.channel.id if message.guild is not None else None
            guild_id = message.guild.id if message.guild is not None else None
            await asyncio.to_thread(
                app.memory_store.save_reminder_delivery_target,
                r["id"],
                channel_id,
                guild_id,
                message.author.id,
            )

        response = _clean_reply_text(response)
        app.memory_store.add_message(chat_id, "assistant", response)
        for chunk in _split_response(response):
            await message.reply(chunk)
        return response

bot = SpideyBot()


@bot.command(name="ask")
async def ask_command(ctx: commands.Context[Any], *, prompt: str = "") -> None:
    await bot.respond_to_prompt(ctx.message, prompt)


@bot.command(name="input")
async def input_command(ctx: commands.Context[Any], *, prompt: str = "") -> None:
    await bot.respond_to_prompt(ctx.message, prompt)


@bot.command(name="ping")
async def ping_command(ctx: commands.Context[Any]) -> None:
    """Instant health check that never loads the model."""
    latency = bot.latency * 1000
    detail = f"{round(latency)} ms" if latency > 0 else "unavailable"
    await ctx.reply(f"Online. Gateway latency {detail}.")


_NATURAL_JOIN_VOICE_RE = re.compile(
    r"^(?:hey\s+spidey[,\s]+|spidey[,\s]+)?(?:please\s+)?"
    r"(?:join(?:\s+me\s+in)?|hop\s+in(?:to)?|come\s+(?:to|into|in))\s+"
    r"(?:my\s+|the\s+)?(?:voice(?:\s+channel|\s+call)?|vc|call)$",
    re.IGNORECASE,
)

_NATURAL_LEAVE_VOICE_RE = re.compile(
    r"^(?:hey\s+spidey[,\s]+|spidey[,\s]+)?(?:please\s+)?"
    r"(?:leave|disconnect(?:\s+from)?|exit)\s+"
    r"(?:my\s+|the\s+)?(?:voice(?:\s+channel|\s+call)?|vc|call)$",
    re.IGNORECASE,
)


async def _join_author_voice(message: discord.Message) -> None:
    if not bot.is_allowed(message):
        await message.reply("You are not authorized to use this assistant.")
        return
    if message.guild is None:
        await message.reply("Voice calls only work inside a Discord server voice channel — join a server voice channel and run `!join`.")
        return
    voice_state = getattr(message.author, "voice", None)
    if voice_state is None or voice_state.channel is None:
        await message.reply("Join a server voice channel first, then send `!join` (or say `join voice`).")
        return
    try:
        await bot.remember_server_channel(message.author.id, message.guild.id, message.channel.id)
        await bot.voice_manager.join(voice_state.channel, text_channel=message.channel, greet=True)
        await message.reply(
            f"Joined **{voice_state.channel.name}** — I'm listening! Speak naturally, or use `!stop` / `!leave` anytime."
        )
    except Exception as exc:
        LOGGER.exception("Failed to join voice channel.")
        await message.reply(f"Couldn't join voice channel: {exc}")


async def _leave_guild_voice(message: discord.Message) -> None:
    if not bot.is_allowed(message):
        await message.reply("You are not authorized to use this assistant.")
        return
    if message.guild is None:
        await message.reply("I'm not in a server voice channel.")
        return
    left = await bot.voice_manager.leave(message.guild.id)
    if left:
        await message.reply("Left the voice channel.")
    else:
        await message.reply("I'm not currently in a voice channel in this server.")


@bot.command(name="join", aliases=["call", "vc"])
async def join_command(ctx: commands.Context[Any]) -> None:
    """Join the caller's current Discord server voice channel."""
    await _join_author_voice(ctx.message)


@bot.command(name="leave", aliases=["disconnect", "hangup"])
async def leave_command(ctx: commands.Context[Any]) -> None:
    """Leave the server voice channel."""
    await _leave_guild_voice(ctx.message)


@bot.command(name="stop", aliases=["shutup", "quiet"])
async def stop_command(ctx: commands.Context[Any]) -> None:
    """Stop S.P.I.D.E.Y. from speaking in the current voice call."""
    if not bot.is_allowed(ctx.message):
        await ctx.reply("You are not authorized to use this assistant.")
        return
    if ctx.guild and bot.voice_manager.stop_speaking(ctx.guild.id):
        await ctx.reply("Stopped speaking.")
    else:
        await ctx.reply("Nothing is playing right now.")


@bot.command(name="say", aliases=["speak"])
async def say_command(ctx: commands.Context[Any], *, text: str = "") -> None:
    """Speak custom text in the active voice channel."""
    if not bot.is_allowed(ctx.message):
        await ctx.reply("You are not authorized to use this assistant.")
        return
    if ctx.guild is None:
        await ctx.reply("Use `!say` inside a server where I'm in a voice channel.")
        return
    if not text.strip():
        await ctx.reply("Usage: `!say <message>`")
        return
    if bot.voice_manager.get_session(ctx.guild.id) is None:
        await _join_author_voice(ctx.message)
    spoke = await bot.voice_manager.speak_in_guild(ctx.guild.id, text.strip())
    if not spoke:
        await ctx.reply("Couldn't play audio in the voice channel.")


@bot.command(name="notify")
async def notify_command(ctx: commands.Context[Any], *, arg: str = "") -> None:
    """Pin proactive recommendations and check-ins to this server text channel (`!notify here`)."""
    if not bot.is_allowed(ctx.message):
        await ctx.reply("You are not authorized to use this assistant.")
        return
    if ctx.guild is None:
        await ctx.reply("Run `!notify here` inside a Discord server text channel to pin recommendations there.")
        return
    await bot.remember_server_channel(ctx.author.id, ctx.guild.id, ctx.channel.id)
    await ctx.reply(f"Got it — I'll send your recommendations and check-ins to **#{ctx.channel.name}** (and speak them aloud whenever I'm in a voice call with you).")


@bot.command(name="voice")
async def voice_command(ctx: commands.Context[Any], *, arg: str = "") -> None:
    """Manage server voice calls: `!voice` (join), `!voice status`, `!voice leave`, `!voice text on|off`."""
    if not bot.is_allowed(ctx.message):
        await ctx.reply("You are not authorized to use this assistant.")
        return
    sub = arg.strip().lower()
    if not sub or sub in {"join", "start", "on"}:
        await _join_author_voice(ctx.message)
        return
    if sub in {"leave", "stop", "off", "disconnect"}:
        await _leave_guild_voice(ctx.message)
        return
    if ctx.guild is None:
        await ctx.reply("Voice calls only work in server channels.")
        return
    session = bot.voice_manager.get_session(ctx.guild.id)
    if sub == "status":
        if session and session.voice_client and session.voice_client.is_connected():
            ch_name = session.voice_client.channel.name
            mirror = "on" if session.text_mirror else "off"
            await ctx.reply(f"Connected to **{ch_name}** (listening, text transcript mirror: **{mirror}**).")
        else:
            await ctx.reply("Not currently in a voice channel. Join one and type `!join`.")
        return
    if sub in {"text on", "mirror on"}:
        if session:
            session.text_mirror = True
            await ctx.reply("Voice transcript mirroring to this text channel is now **on**.")
        else:
            await ctx.reply("I'm not in a voice call right now.")
        return
    if sub in {"text off", "mirror off"}:
        if session:
            session.text_mirror = False
            await ctx.reply("Voice transcript mirroring to this text channel is now **off**.")
        else:
            await ctx.reply("I'm not in a voice call right now.")
        return
    await ctx.reply("Voice commands: `!join`, `!leave`, `!stop`, `!say <text>`, `!voice status`, `!voice text on|off`.")


@bot.event
async def on_voice_state_update(
    member: discord.Member,
    before: discord.VoiceState,
    after: discord.VoiceState,
) -> None:
    await bot.voice_manager.handle_voice_state_update(
        member, before, after, bot.user.id if bot.user else None
    )


@bot.event
async def on_message(message: discord.Message) -> None:
    if message.author.bot:
        return
    raw_content = message.content.strip()
    if bot.user is not None and bot.user in message.mentions:
        prompt = message.content.replace(f"<@{bot.user.id}>", "")
        prompt = prompt.replace(f"<@!{bot.user.id}>", "").strip()
        if _NATURAL_JOIN_VOICE_RE.match(prompt):
            await _join_author_voice(message)
            return
        if _NATURAL_LEAVE_VOICE_RE.match(prompt):
            await _leave_guild_voice(message)
            return
        reply_text = await bot.respond_to_prompt(message, prompt)
        return
    if not message.content.startswith(bot.command_prefix):
        if _NATURAL_JOIN_VOICE_RE.match(raw_content):
            await _join_author_voice(message)
            return
        if _NATURAL_LEAVE_VOICE_RE.match(raw_content):
            await _leave_guild_voice(message)
            return
        reply_text = await bot.respond_to_prompt(message, message.content)
        return
    await bot.process_commands(message)


@bot.event
async def on_command_error(
    ctx: commands.Context[Any], error: commands.CommandError
) -> None:
    """Treat an unregistered `!something` as a prompt, like the web chat."""
    if isinstance(error, commands.CommandNotFound):
        prefix = ctx.prefix or ""
        await bot.respond_to_prompt(ctx.message, ctx.message.content[len(prefix) :])
        return
    LOGGER.error("Discord command failed: %s", error)


_discord_task: asyncio.Task | None = None


async def start_discord_bot_in_process(token: str) -> None:
    """Start the Discord bot inside the existing FastAPI server event loop."""
    global _discord_task
    if _discord_task is not None and not _discord_task.done():
        LOGGER.info("Discord bot is already running in-process.")
        return
    try:
        _acquire_single_instance()
    except Exception as err:
        LOGGER.warning("Could not acquire Discord single instance lock: %s", err)
    LOGGER.info("Starting Discord bot in-process with FastAPI server...")
    _discord_task = asyncio.create_task(bot.start(token))


async def stop_discord_bot_in_process() -> None:
    """Stop the in-process Discord bot gracefully."""
    global _discord_task
    try:
        await bot.voice_manager.disconnect_all()
    except Exception as e:
        LOGGER.warning("Error disconnecting Discord voice sessions: %s", e)
    if bot.is_ready():
        LOGGER.info("Closing in-process Discord bot connection...")
        try:
            await bot.close()
        except Exception as e:
            LOGGER.warning("Error closing Discord bot: %s", e)
    if _discord_task is not None:
        try:
            await _discord_task
        except asyncio.CancelledError:
            pass
        except Exception as e:
            LOGGER.warning("Error waiting for Discord bot task completion: %s", e)
        _discord_task = None
    _release_single_instance()


def main() -> None:
    token = os.environ.get("AI_DISCORD_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "AI_DISCORD_TOKEN is required. Add it to the .env file in the project "
            "root (Discord Developer Portal -> Bot -> Reset Token); never put it "
            "in the frontend."
        )
    logging.basicConfig(
        level=os.environ.get("AI_DISCORD_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # Check if the S.P.I.D.E.Y server is already running with the in-process bot
    try:
        import urllib.request
        req = urllib.request.urlopen("http://127.0.0.1:8000/api/health", timeout=1.5)
        if req.status == 200:
            LOGGER.info(
                "S.P.I.D.E.Y server is already running on port 8000 with the in-process Discord bot. "
                "To avoid duplicate model loading in VRAM, the bot runs inside the server process. "
                "No separate discord_bot.py process is needed. Exiting."
            )
            return
    except Exception as err:
        LOGGER.debug("Server health check bypassed: %s", err)

    from runtime.guard import acquire_model_process_lock
    _model_guard = acquire_model_process_lock()  # noqa: F841
    guard = _acquire_single_instance()  # noqa: F841 - held for the process lifetime
    try:
        bot.run(token)
    finally:
        _release_single_instance()


if __name__ == "__main__":
    main()
