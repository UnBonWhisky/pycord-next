# The MIT License (MIT)
#
# Copyright (c) 2015-2021 Rapptz
# Copyright (c) 2021-present Pycord Development
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
# OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.

"""Connection state holding the gateway driven models and stores."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from functools import partial
from typing import TYPE_CHECKING, Any, Literal, TypeVar, cast, overload

from aiocache import BaseCache

from .. import utils
from ..abc import GuildChannel as GuildChannelBase
from ..activity import BaseActivity
from ..cache import CacheStore
from ..channel import (
    DMChannel,
    GroupChannel,
    PartialMessageable,
    TextChannel,
    VocalGuildChannel,
    _guild_channel_factory,
    _threaded_channel_factory,
)
from ..emoji import AppEmoji, GuildEmoji
from ..enums import ChannelType, Status
from ..errors import GatewayRateLimited, InvalidData
from ..flags import GatewayCapabilities, Intents, MemberCacheFlags
from ..guild import Guild, PartialGuild
from ..member import Member
from ..mentions import AllowedMentions
from ..message import Message, PartialMessage
from ..partial_emoji import PartialEmoji
from ..poll import Poll
from ..role import Role
from ..scheduled_events import ScheduledEvent
from ..soundboard import SoundboardSound
from ..stage_instance import StageInstance
from ..sticker import GuildSticker
from ..threads import Thread, ThreadMember
from ..ui.modal import BaseModal, ModalStore
from ..ui.view import BaseView, ViewStore
from ..user import ClientUser, User
from .parsers import PARSERS

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Coroutine, Sequence

    from ..abc import MessageableChannel, PartialMessageableChannel, PrivateChannel
    from ..cache import CacheBucket
    from ..client import Client
    from ..flags import ApplicationFlags
    from ..gateway import DiscordWebSocket, GatewayTransport
    from ..guild import GuildChannel
    from ..http import HTTPClient
    from ..interactions import Interaction
    from ..raw_models import ChannelInfo, GatewayRateLimit, RawMessageUpdateEvent
    from ..types.activity import Activity as ActivityPayload
    from ..types.channel import DMChannel as DMChannelPayload, RequestChannelInfoField
    from ..types.emoji import Emoji as EmojiPayload, PartialEmoji as PartialEmojiPayload
    from ..types.guild import Guild as GuildPayload
    from ..types.interactions import Interaction as InteractionPayload
    from ..types.message import Message as MessagePayload
    from ..types.poll import Poll as PollPayload
    from ..types.raw_models import TypingEvent
    from ..types.sticker import GuildSticker as GuildStickerPayload
    from ..types.threads import Thread as ThreadPayload
    from ..types.user import User as UserPayload
    from ..voice import VoiceProtocol

    T = TypeVar("T")
    CS = TypeVar("CS", bound="ConnectionState")
    Channel = GuildChannel | PrivateChannel

PRIVATE_CHANNEL_LIMIT = 128


class ChunkRequest:
    """A pending request for guild member chunks."""

    def __init__(
        self,
        guild_id: int,
        loop: asyncio.AbstractEventLoop,
        resolver: Callable[[int], Awaitable[Guild | None]],
        *,
        cache: bool = True,
    ) -> None:
        self.guild_id: int = guild_id
        self.resolver: Callable[[int], Awaitable[Guild | None]] = resolver
        self.loop: asyncio.AbstractEventLoop = loop
        self.cache: bool = cache
        self.nonce: str = os.urandom(16).hex()
        self.buffer: list[Member] = []
        self.waiters: list[asyncio.Future[list[Member]]] = []

    async def add_members(self, members: list[Member]) -> None:
        """Buffer chunked members and cache them when requested."""
        self.buffer.extend(members)
        if self.cache:
            guild = await self.resolver(self.guild_id)
            if guild is None:
                return

            for member in members:
                existing = await guild.get_member(member.id)
                if existing is None or existing.joined_at is None:
                    await guild._add_member(member)

    async def wait(self) -> list[Member]:
        """Wait for every chunk to be received."""
        future: asyncio.Future[list[Member]] = self.loop.create_future()
        self.waiters.append(future)
        try:
            return await future
        finally:
            self.waiters.remove(future)

    def get_future(self) -> asyncio.Future[list[Member]]:
        """Return a future resolved once every chunk is received."""
        future = self.loop.create_future()
        self.waiters.append(future)
        return future

    def done(self) -> None:
        """Resolve every waiter with the buffered members."""
        for future in self.waiters:
            if not future.done():
                future.set_result(self.buffer)

    def fail(self, exc: BaseException) -> None:
        """Fail every waiter with ``exc``."""
        for future in self.waiters:
            if not future.done():
                future.set_exception(exc)


class ChannelInfoRequest:
    """A pending request for the ephemeral info of the channels of a guild."""

    def __init__(
        self,
        guild_id: int,
        loop: asyncio.AbstractEventLoop,
        resolver: Callable[[int], Awaitable[Guild | None]],
        fields: tuple[RequestChannelInfoField, ...],
        *,
        cache: bool = True,
    ) -> None:
        self.guild_id: int = guild_id
        self.resolver: Callable[[int], Awaitable[Guild | None]] = resolver
        self.loop: asyncio.AbstractEventLoop = loop
        self.fields: tuple[RequestChannelInfoField, ...] = fields
        self.cache: bool = cache
        self.channel_info: list[ChannelInfo] = []
        self.waiters: list[asyncio.Future[list[ChannelInfo]]] = []

    async def parse_response(self, channel_info: list[ChannelInfo]) -> None:
        """Cache the received channel info when requested and resolve the waiters."""
        self.channel_info = channel_info
        if self.cache:
            guild = await self.resolver(self.guild_id)
            if guild is not None:
                for info in channel_info:
                    channel = await guild.get_channel(info.id)
                    if not isinstance(channel, VocalGuildChannel):
                        continue
                    if "status" in self.fields:
                        channel._update_status(status=info.status)
                    if "voice_start_time" in self.fields:
                        channel._update_status(voice_start_time=info.voice_start_time)
                    await guild._add_channel(channel)

        for future in self.waiters:
            if not future.done():
                future.set_result(self.channel_info)

    def get_future(self) -> asyncio.Future[list[ChannelInfo]]:
        """Return a future resolved once the channel info is received."""
        future = self.loop.create_future()
        self.waiters.append(future)
        return future


_logger = logging.getLogger(__name__)

GUILD_SCOPED_KINDS = (
    "channels",
    "threads",
    "members",
    "roles",
    "voice_states",
    "scheduled_events",
    "stage_instances",
    "guild_sounds",
    "guild_emojis",
    "guild_stickers",
)


class ConnectionState:
    """Holds the gateway driven state and dispatches parsed events."""

    if TYPE_CHECKING:
        _get_websocket: Callable[..., GatewayTransport]
        _get_client: Callable[..., Client]
        _parsers: dict[str, Callable[[dict[str, Any]], Coroutine[Any, Any, None]]]
        _ready_state: asyncio.Queue[Guild]
        application_flags: ApplicationFlags

    def __init__(
        self,
        *,
        dispatch: Callable[..., None],
        handlers: dict[str, Callable[..., Any]],
        hooks: dict[str, Callable[..., Awaitable[Any]]],
        http: HTTPClient,
        loop: asyncio.AbstractEventLoop,
        **options: Any,
    ) -> None:
        self.loop: asyncio.AbstractEventLoop = loop
        self.http: HTTPClient = http
        self.max_messages: int | None = options.get("max_messages", 1000)
        if self.max_messages is not None and self.max_messages <= 0:
            self.max_messages = 1000

        self.dispatch: Callable[..., None] = dispatch
        self.handlers: dict[str, Callable[..., Any]] = handlers
        self.hooks: dict[str, Callable[..., Awaitable[Any]]] = hooks
        self.shard_count: int | None = None
        self._ready_task: asyncio.Task[None] | None = None
        self._background_tasks: set[asyncio.Task[Any]] = set()
        self.application_id: int | None = utils._get_as_snowflake(
            options, "application_id"
        )
        self.heartbeat_timeout: float = options.get("heartbeat_timeout", 60.0)
        self.guild_ready_timeout: float = options.get("guild_ready_timeout", 2.0)
        if self.guild_ready_timeout < 0:
            raise ValueError("guild_ready_timeout cannot be negative")

        allowed_mentions = options.get("allowed_mentions")

        if allowed_mentions is not None and not isinstance(
            allowed_mentions, AllowedMentions
        ):
            raise TypeError("allowed_mentions parameter must be AllowedMentions")

        self.allowed_mentions: AllowedMentions | None = allowed_mentions
        self._chunk_requests: dict[int | str, ChunkRequest] = {}
        self.cache_channel_info: bool = options.get("cache_channel_info", False)

        activity = options.get("activity")
        if activity:
            if not isinstance(activity, BaseActivity):
                raise TypeError("activity parameter must derive from BaseActivity.")

            activity = activity.to_dict()

        status = options.get("status")
        if status:
            status = "invisible" if status is Status.offline else str(status)
        intents = options.get("intents")
        if intents is None:
            intents = Intents.default()

        elif not isinstance(intents, Intents):
            raise TypeError(f"intents parameter must be Intent not {type(intents)!r}")
        if not intents.guilds:
            _logger.warning(
                "Guilds intent seems to be disabled. This may cause state related"
                " issues."
            )

        self._chunk_guilds: bool = options.get(
            "chunk_guilds_at_startup", intents.members
        )

        # Ensure these two are set properly
        if not intents.members and self._chunk_guilds:
            raise ValueError(
                "Intents.members must be enabled to chunk guilds at startup."
            )

        cache_flags = options.get("member_cache_flags")
        if cache_flags is None:
            cache_flags = MemberCacheFlags.from_intents(intents)
        elif not isinstance(cache_flags, MemberCacheFlags):
            raise TypeError(
                "member_cache_flags parameter must be MemberCacheFlags not"
                f" {type(cache_flags)!r}"
            )

        else:
            cache_flags._verify_intents(intents)

        self.member_cache_flags: MemberCacheFlags = cache_flags
        self._activity: ActivityPayload | None = activity
        self._status: str | None = status
        self._intents: Intents = intents

        capabilities = options.get("capabilities")
        if capabilities is None:
            capabilities = GatewayCapabilities.none()
        elif isinstance(capabilities, int):
            capabilities = GatewayCapabilities._from_value(capabilities)
        elif not isinstance(capabilities, GatewayCapabilities):
            raise TypeError(
                "capabilities parameter must be GatewayCapabilities or int."
            )

        self.capabilities: GatewayCapabilities = capabilities

        self._cache_users: bool = bool(intents.members and not cache_flags._empty)

        self.cache_app_emojis: bool = options.get("cache_app_emojis", False)
        self.cache_default_sounds: bool = options.get(
            "cache_default_sounds",
            True,  # TODO(Paillat-dev): Don't cache default sounds by default
        )
        self.cache_fetch: bool = options.get("cache_fetch", False)

        cache_backend = options.get("cache_backend")
        if cache_backend is not None and not isinstance(cache_backend, BaseCache):
            raise TypeError(
                "cache_backend parameter must be aiocache.BaseCache not"
                f" {type(cache_backend)!r}"
            )

        self._store: CacheStore = CacheStore(
            cache_backend,
            namespace=options.get("cache_namespace", "pycord"),
            state=self,
        )

        self.parsers: dict[str, Callable[[Any], Coroutine[Any, Any, None]]] = (
            self._build_parsers()
        )

        self.clear()

    def _build_parsers(self) -> dict[str, Callable[[Any], Coroutine[Any, Any, None]]]:
        parsers: dict[str, Callable[[Any], Coroutine[Any, Any, None]]] = {
            event: partial(func, self) for event, func in PARSERS.items()
        }
        for attr in dir(type(self)):
            if attr.startswith("parse_"):
                parsers[attr[6:].upper()] = getattr(self, attr)
        return parsers

    def _create_task(self, coro: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

    @property
    def cache(self) -> CacheStore:
        """The :class:`~discord.cache.CacheStore` backing every cached entity."""
        return self._store

    def clear(self, *, views: bool = True) -> None:
        """Reset the live state and rebind the cache buckets.

        Cached entities are removed with :meth:`_clear_cache`.
        """
        self.user: ClientUser | None = None
        self._channel_info_requests: dict[int, list[ChannelInfoRequest]] = {}
        store = self._store
        self._users: CacheBucket[int, User] = store.bucket("users")
        self._guilds: CacheBucket[int, Guild] = store.bucket("guilds")
        self._emojis: CacheBucket[int, GuildEmoji] = store.bucket("emojis")
        self._app_emojis: CacheBucket[int, AppEmoji] = store.bucket("app_emojis")
        self._stickers: CacheBucket[int, GuildSticker] = store.bucket("stickers")
        self._polls: CacheBucket[int, Poll] = store.bucket("polls")
        self._sounds: CacheBucket[int, SoundboardSound] = store.bucket("sounds")
        self._channel_guild: CacheBucket[int, int] = store.bucket("channel_guild")
        self._private_channels: CacheBucket[int, PrivateChannel] = store.bucket(
            "private_channels", maxlen=PRIVATE_CHANNEL_LIMIT, lru=True
        )
        self._private_channels_by_user: CacheBucket[int, int] = store.bucket(
            "private_channels_by_user"
        )
        self._messages: CacheBucket[int, Message] | None = (
            store.bucket("messages", maxlen=self.max_messages)
            if self.max_messages is not None
            else None
        )
        if views:
            self._view_store: ViewStore = ViewStore(self)
        self._modal_store: ModalStore = ModalStore(self)
        self._voice_clients: dict[int, VoiceProtocol[Any]] = {}

    async def _clear_cache(self) -> None:
        await self._store.clear()

    def _guild_bucket(self, kind: str, guild_id: int) -> CacheBucket[int, Any]:
        return self._store.bucket(kind, scope=guild_id)

    async def process_chunk_requests(
        self, guild_id: int, nonce: str | None, members: list[Member], complete: bool
    ) -> None:
        """Feed a received chunk to the matching chunk requests."""
        removed: list[int | str] = []
        for key, request in list(self._chunk_requests.items()):
            if request.guild_id == guild_id and request.nonce == nonce:
                await request.add_members(members)
                if complete:
                    request.done()
                    removed.append(key)

        for key in removed:
            del self._chunk_requests[key]

    async def process_info_requests(
        self, guild_id: int, channel_info: list[ChannelInfo]
    ) -> None:
        """Feed a received channel info to the oldest matching request."""
        requests = self._channel_info_requests.get(guild_id)
        if not requests:
            return

        request = requests.pop(0)
        if not requests:
            del self._channel_info_requests[guild_id]
        await request.parse_response(channel_info)

    def _discard_info_request(self, request: ChannelInfoRequest) -> None:
        requests = self._channel_info_requests.get(request.guild_id)
        if requests is None or request not in requests:
            return

        requests.remove(request)
        if not requests:
            del self._channel_info_requests[request.guild_id]

    def process_gateway_rate_limit(self, payload: GatewayRateLimit) -> None:
        """Fail the chunk request affected by a gateway rate limit."""
        if payload.opcode != 8 or payload.nonce is None:
            return

        exc = GatewayRateLimited(payload.opcode, payload.retry_after, payload.meta)
        for key, request in list(self._chunk_requests.items()):
            if request.nonce == payload.nonce:
                request.fail(exc)
                del self._chunk_requests[key]

    def call_handlers(self, key: str, *args: Any, **kwargs: Any) -> None:
        """Call the internal handler registered for ``key``, if any."""
        try:
            func = self.handlers[key]
        except KeyError:
            pass
        else:
            func(*args, **kwargs)

    async def call_hooks(self, key: str, *args: Any, **kwargs: Any) -> None:
        """Await the internal hook registered for ``key``, if any."""
        try:
            coro = self.hooks[key]
        except KeyError:
            pass
        else:
            await coro(*args, **kwargs)

    @property
    def self_id(self) -> int | None:
        """Return the ID of the connected user, if any."""
        u = self.user
        return u.id if u else None

    @property
    def intents(self) -> Intents:
        """Return a copy of the intents of this state."""
        ret = Intents.none()
        ret.value = self._intents.value
        return ret

    @property
    def voice_clients(self) -> list[VoiceProtocol[Any]]:
        """Return every registered voice client."""
        return list(self._voice_clients.values())

    def _get_voice_client(self, guild_id: int | None) -> VoiceProtocol[Any] | None:
        if guild_id is None:
            return None
        return self._voice_clients.get(guild_id)

    def _add_voice_client(self, guild_id: int, voice: VoiceProtocol[Any]) -> None:
        self._voice_clients[guild_id] = voice

    def _remove_voice_client(self, guild_id: int) -> None:
        self._voice_clients.pop(guild_id, None)

    def _update_references(self, ws: DiscordWebSocket) -> None:
        for vc in self.voice_clients:
            vc.main_ws = ws  # type: ignore[attr-defined]

    async def store_user(self, data: UserPayload) -> User:
        """Cache a user from its payload and return it."""
        if not self._cache_users:
            return self.create_user(data)
        user_id = int(data["id"])
        user = await self._users.get(user_id)
        if user is None:
            user = User(state=self, data=data)
            if user.discriminator != "0000":
                await self._users.set(user_id, user)
            return user
        # Making sure we don't mutate the cached user
        # because we cannot make sure it's up to date.
        # but still return the updated version of the user.
        # This make sure data like banner, etc are updated.
        copied_user = user._copy(user)
        copied_user._update(data)
        return copied_user

    async def deref_user(self, user_id: int) -> None:
        """Remove a user from the cache."""
        await self._users.pop(user_id)

    async def deref_user_no_intents(self, user_id: int) -> None:
        """Do nothing, kept for subclasses (the sharded state overrides ``deref_user``)."""
        return

    def create_user(self, data: UserPayload) -> User:
        """Build a user from its payload without caching it."""
        return User(state=self, data=data)

    async def get_user(self, id: int | None) -> User | None:
        """Return the cached user with the given ID, if any."""
        if id is None:
            return None
        return await self._users.get(id)

    async def get_users(self) -> list[User]:
        """Return every cached user."""
        return await self._users.values()

    async def store_emoji(
        self, guild: Guild | PartialGuild, data: EmojiPayload
    ) -> GuildEmoji:
        """Build a guild emoji and cache it."""
        # the id will be present here
        emoji = GuildEmoji(guild=guild, state=self, data=data)
        await self._emojis.set(emoji.id, emoji)
        await self._guild_bucket("guild_emojis", guild.id).set(emoji.id, emoji)
        return emoji

    async def maybe_store_app_emoji(
        self, application_id: int, data: EmojiPayload
    ) -> AppEmoji:
        """Build an application emoji and cache it when enabled."""
        # the id will be present here
        emoji = AppEmoji(application_id=application_id, state=self, data=data)
        if self.cache_app_emojis:
            await self._app_emojis.set(emoji.id, emoji)
        return emoji

    async def store_sticker(
        self, guild: Guild | PartialGuild, data: GuildStickerPayload
    ) -> GuildSticker:
        """Build a guild sticker and cache it."""
        sticker = GuildSticker(state=self, data=data)
        await self._stickers.set(sticker.id, sticker)
        await self._guild_bucket("guild_stickers", guild.id).set(sticker.id, sticker)
        return sticker

    def store_view(self, view: BaseView, message_id: int | None = None) -> None:
        """Register a view, optionally bound to a message."""
        self._view_store.add_view(view, message_id)

    def purge_message_view(self, message_id: int) -> None:
        """Remove the view attached to a message."""
        self._view_store.remove_message_view(message_id)

    def get_message_view(self, message_id: int) -> BaseView | None:
        """Return the view tracked for a message, if any."""
        return self._view_store.get_message_view(message_id)

    def store_modal(self, modal: BaseModal, message_id: int) -> None:
        """Register a modal for a message."""
        self._modal_store.add_modal(modal, message_id)

    def prevent_view_updates_for(self, message_id: int) -> BaseView | None:
        """Stop tracking view updates for a message."""
        return self._view_store.remove_message_tracking(message_id)

    @property
    def persistent_views(self) -> Sequence[BaseView]:
        """Return the registered persistent views."""
        return self._view_store.persistent_views

    @property
    def guilds(self) -> list[Guild]:
        """The cached guilds, from the in-process cache (see :meth:`get_guilds`)."""
        return self._guilds.values_nowait()

    @property
    def emojis(self) -> list[GuildEmoji | AppEmoji]:
        """The cached emojis, from the in-process cache (see :meth:`get_emojis`)."""
        return [*self._emojis.values_nowait(), *self._app_emojis.values_nowait()]

    @property
    def stickers(self) -> list[GuildSticker]:
        """The cached stickers, from the in-process cache (see :meth:`get_stickers`)."""
        return self._stickers.values_nowait()

    @property
    def polls(self) -> list[Poll]:
        """The cached polls, from the in-process cache (see :meth:`get_polls`)."""
        return self._polls.values_nowait()

    @property
    def private_channels(self) -> list[PrivateChannel]:
        """The cached private channels, from the in-process cache (see :meth:`get_private_channels`)."""
        return self._private_channels.values_nowait()

    @property
    def sounds(self) -> list[SoundboardSound]:
        """The cached soundboard sounds, from the in-process cache (see :meth:`get_sounds`)."""
        return self._sounds.values_nowait()

    async def get_guilds(self) -> list[Guild]:
        """Return every cached guild."""
        return await self._guilds.values()

    async def _get_guild(self, guild_id: int | None) -> Guild | None:
        if guild_id is None:
            return None
        return await self._guilds.get(guild_id)

    async def _add_guild(self, guild: Guild) -> None:
        await self._guilds.set(guild.id, guild)

    async def _remove_guild(self, guild: Guild) -> None:
        guild_id = guild.id
        await self._guilds.pop(guild_id)
        await self._drop_guild_children(guild_id)

        if self._messages is not None:
            for message_id, message in await self._messages.items():
                if message.guild_id == guild_id:
                    await self._messages.pop(message_id)

    async def _drop_guild_children(self, guild_id: int) -> None:
        for emoji in await self._guild_bucket("guild_emojis", guild_id).values():
            await self._emojis.pop(emoji.id)
        for sticker in await self._guild_bucket("guild_stickers", guild_id).values():
            await self._stickers.pop(sticker.id)
        for sound in await self._guild_bucket("guild_sounds", guild_id).values():
            await self._sounds.pop(sound.id)
        for kind in ("channels", "threads"):
            for channel_id in await self._guild_bucket(kind, guild_id).keys():
                await self._channel_guild.pop(channel_id)
        for thread_id in await self._guild_bucket("threads", guild_id).keys():
            await self._drop_bucket("thread_members", thread_id)
        for kind in GUILD_SCOPED_KINDS:
            await self._drop_bucket(kind, guild_id)

    async def get_emojis(self) -> list[GuildEmoji | AppEmoji]:
        """Return every cached emoji."""
        return [*await self._emojis.values(), *await self._app_emojis.values()]

    async def get_stickers(self) -> list[GuildSticker]:
        """Return every cached sticker."""
        return await self._stickers.values()

    async def get_emoji(self, emoji_id: int | None) -> GuildEmoji | AppEmoji | None:
        """Return the cached emoji with the given ID, if any."""
        if emoji_id is None:
            return None
        return await self._emojis.get(emoji_id) or await self._app_emojis.get(emoji_id)

    async def _remove_emoji(self, emoji: GuildEmoji | AppEmoji) -> None:
        await self._emojis.pop(emoji.id)
        await self._app_emojis.pop(emoji.id)
        guild_id = getattr(emoji, "guild_id", None)
        if guild_id is not None:
            await self._guild_bucket("guild_emojis", guild_id).pop(emoji.id)

    async def get_sticker(self, sticker_id: int | None) -> GuildSticker | None:
        """Return the cached sticker with the given ID, if any."""
        if sticker_id is None:
            return None
        return await self._stickers.get(sticker_id)

    async def get_polls(self) -> list[Poll]:
        """Return every cached poll."""
        return await self._polls.values()

    async def store_raw_poll(
        self, poll: PollPayload, raw: RawMessageUpdateEvent
    ) -> Poll:
        """Build a poll from a raw payload and cache it."""
        channel = await self.get_channel(raw.channel_id) or PartialMessageable(
            state=self, id=raw.channel_id
        )
        message = PartialMessage(
            channel=cast("PartialMessageableChannel", channel),
            id=raw.message_id,
            guild_id=raw.guild_id,
        )
        p = Poll.from_dict(poll, message)
        await self._polls.set(message.id, p)
        return p

    async def store_poll(self, poll: Poll, message_id: int) -> None:
        """Cache a poll for a message."""
        await self._polls.set(message_id, poll)

    async def get_poll(self, message_id: int) -> Poll | None:
        """Return the cached poll of a message, if any."""
        return await self._polls.get(message_id)

    async def get_private_channels(self) -> list[PrivateChannel]:
        """Return every cached private channel."""
        return await self._private_channels.values()

    async def _get_private_channel(
        self, channel_id: int | None
    ) -> PrivateChannel | None:
        if channel_id is None:
            return None
        return await self._private_channels.get(channel_id)

    async def _get_private_channel_by_user(
        self, user_id: int | None
    ) -> DMChannel | None:
        if user_id is None:
            return None
        channel_id = await self._private_channels_by_user.get(user_id)
        if channel_id is None:
            return None
        channel = await self._private_channels.peek(channel_id)
        return channel if isinstance(channel, DMChannel) else None

    async def _add_private_channel(self, channel: PrivateChannel) -> None:
        for evicted_id, evicted in await self._private_channels.set(
            channel.id, channel
        ):
            del evicted_id
            if isinstance(evicted, DMChannel) and evicted.recipient:
                await self._private_channels_by_user.pop(evicted.recipient.id)

        if isinstance(channel, DMChannel) and channel.recipient:
            await self._private_channels_by_user.set(channel.recipient.id, channel.id)

    async def add_dm_channel(self, data: DMChannelPayload) -> DMChannel:
        """Create a DM channel from its payload and cache it."""
        # self.user is *always* cached when this is called
        channel = DMChannel(me=cast("ClientUser", self.user), state=self, data=data)
        await self._add_private_channel(channel)
        return channel

    async def _remove_private_channel(self, channel: PrivateChannel) -> None:
        await self._private_channels.pop(channel.id)
        if isinstance(channel, DMChannel):
            recipient = channel.recipient
            if recipient is not None:
                await self._private_channels_by_user.pop(recipient.id)

    async def _get_message(self, msg_id: int | None) -> Message | None:
        if self._messages is None or msg_id is None:
            return None
        return await self._messages.get(msg_id)

    async def get_cached_messages(self) -> list[Message]:
        """Return every cached message, oldest first."""
        if self._messages is None:
            return []
        return await self._messages.values()

    async def _store_message(self, message: Message) -> None:
        if self._messages is not None:
            await self._messages.set(message.id, message)

    async def _remove_message(self, message_id: int) -> Message | None:
        if self._messages is None:
            return None
        return await self._messages.pop(message_id)

    async def _add_guild_from_data(self, data: GuildPayload) -> Guild:
        guild = Guild(data=data, state=self)
        await self._populate_guild(guild, data)
        await self._add_guild(guild)
        return guild

    async def _populate_guild(self, guild: Guild, data: GuildPayload) -> None:
        guild_id = guild.id
        bucket = self._guild_bucket

        roles = bucket("roles", guild_id)
        await roles.clear()
        await roles.set_many(
            {
                role.id: role
                for role in (
                    Role(guild=guild, data=r, state=self) for r in data.get("roles", [])
                )
            }
        )

        guild_emojis = bucket("guild_emojis", guild_id)
        for emoji in await guild_emojis.values():
            await self._emojis.pop(emoji.id)
        await guild_emojis.clear()
        for emoji_data in data.get("emojis", []):
            await self.store_emoji(guild, emoji_data)

        guild_stickers = bucket("guild_stickers", guild_id)
        for sticker in await guild_stickers.values():
            await self._stickers.pop(sticker.id)
        await guild_stickers.clear()
        for sticker_data in data.get("stickers", []):
            await self.store_sticker(guild, sticker_data)

        stage_instances = bucket("stage_instances", guild_id)
        await stage_instances.clear()
        for stage_data in data.get("stage_instances", []):
            stage_instance = StageInstance(guild=guild, data=stage_data, state=self)
            await stage_instances.set(stage_instance.id, stage_instance)

        members = bucket("members", guild_id)
        cache_joined = self.member_cache_flags.joined
        self_id = self.self_id
        cached_members: dict[int, Member] = {}
        for member_data in data.get("members", []):
            member = Member(data=member_data, guild=guild, state=self)
            if self._cache_users:
                await self.store_user(member_data["user"])
            if cache_joined or member.id == self_id:
                cached_members[member.id] = member
        await members.set_many(cached_members)

        events = bucket("scheduled_events", guild_id)
        await events.clear()
        for event_data in data.get("guild_scheduled_events", []):
            creator_id = utils._get_as_snowflake(event_data, "creator_id")
            creator = (
                None
                if not event_data.get("creator", None) or creator_id is None
                else await members.get(creator_id)
            )
            event = ScheduledEvent(
                state=self, guild=guild, creator=creator, data=event_data
            )
            await events.set(event.id, event)

        empty_tuple = ()
        for presence in data.get("presences", []):
            user_id = int(presence["user"]["id"])
            presence_member = await members.get(user_id)
            if presence_member is not None:
                presence_member._presence_update(presence, empty_tuple)
                await members.set(user_id, presence_member)

        if "channels" in data:
            for channel_data in data["channels"]:
                factory, _ = _guild_channel_factory(channel_data["type"])
                if factory:
                    guild_factory = cast("Callable[..., GuildChannel]", factory)
                    await self._add_channel(
                        guild_id,
                        guild_factory(guild=guild, data=channel_data, state=self),
                    )

        if "threads" in data:
            for thread_data in data["threads"]:
                await self._add_thread(
                    guild_id, Thread(guild=guild, state=self, data=thread_data)
                )

        for voice_data in data.get("voice_states", []):
            await guild._update_voice_state(
                voice_data, utils._get_as_snowflake(voice_data, "channel_id")
            )

        for sound_data in data.get("soundboard_sounds", []):
            await guild._add_sound(
                SoundboardSound(state=self, http=self.http, data=sound_data)
            )

    async def _add_channel(self, guild_id: int, channel: GuildChannelBase) -> None:
        await self._guild_bucket("channels", guild_id).set(channel.id, channel)
        await self._channel_guild.set(channel.id, guild_id)

    async def _remove_channel(self, guild_id: int, channel_id: int) -> None:
        await self._guild_bucket("channels", guild_id).pop(channel_id)
        await self._channel_guild.pop(channel_id)

    async def _add_thread(self, guild_id: int, thread: Thread) -> None:
        await self._guild_bucket("threads", guild_id).set(thread.id, thread)
        await self._channel_guild.set(thread.id, guild_id)

    async def _remove_thread(self, guild_id: int, thread_id: int) -> Thread | None:
        thread = await self._guild_bucket("threads", guild_id).pop(thread_id)
        await self._channel_guild.pop(thread_id)
        await self._drop_bucket("thread_members", thread_id)
        return thread

    async def _drop_bucket(self, kind: str, scope: int) -> None:
        self._store.bucket(kind, scope=scope)
        await self._store.drop(kind, scope=scope)

    async def _guild_needs_chunking(self, guild: Guild) -> bool:
        # If presences are enabled then we get back the old guild.large behaviour
        return (
            self._chunk_guilds
            and not await guild.is_chunked()
            and not (self._intents.presences and not guild.large)
        )

    async def _get_guild_channel(
        self, data: MessagePayload | TypingEvent, guild_id: int | None = None
    ) -> tuple[MessageableChannel, Guild | None]:
        channel_id = int(data["channel_id"])
        resolved_guild_id = guild_id or data.get("guild_id")
        channel: MessageableChannel | GuildChannel | Thread | None
        if resolved_guild_id is None:
            channel = DMChannel._from_message(self, channel_id)
            guild = None
        else:
            guild = await self._get_guild(int(resolved_guild_id))
            channel = await guild._resolve_channel(channel_id) if guild else None

        # a message can only be sent in a messageable channel
        return cast(
            "MessageableChannel",
            channel or PartialMessageable(state=self, id=channel_id),
        ), guild

    async def chunker(
        self,
        guild_id: int,
        query: str = "",
        limit: int = 0,
        presences: bool = False,
        *,
        nonce: str | None = None,
    ) -> None:
        """Send a member chunk request for a guild."""
        ws = self._get_websocket(guild_id)  # This is ignored upstream
        await ws.request_chunks(
            guild_id, query=query, limit=limit, presences=presences, nonce=nonce
        )

    async def query_members(
        self,
        guild: Guild | PartialGuild,
        query: str | None,
        limit: int,
        user_ids: list[int] | None,
        cache: bool,
        presences: bool,
    ) -> list[Member]:
        """Query the members of a guild and wait for the result."""
        guild_id = guild.id
        ws = self._get_websocket(guild_id)

        request = ChunkRequest(guild.id, self.loop, self._get_guild, cache=cache)
        self._chunk_requests[request.nonce] = request

        try:
            # start the query operation
            await ws.request_chunks(
                guild_id,
                query=query,
                limit=limit,
                user_ids=user_ids,
                presences=presences,
                nonce=request.nonce,
            )
            return await asyncio.wait_for(request.wait(), timeout=30.0)
        except asyncio.TimeoutError:
            _logger.warning(
                (
                    "Timed out waiting for chunks with query %r and limit %d for"
                    " guild_id %d"
                ),
                query,
                limit,
                guild_id,
            )
            raise

    async def _get_ready_guild(self) -> Guild | None:
        try:
            return await asyncio.wait_for(
                self._ready_state.get(), timeout=self.guild_ready_timeout
            )
        except asyncio.TimeoutError:
            return None

    async def _delay_ready(self) -> None:
        if self.cache_app_emojis and self.application_id:
            data = await self.http.get_all_application_emojis(self.application_id)
            for e in data.get("items", []):
                await self.maybe_store_app_emoji(self.application_id, e)
        if self.cache_default_sounds:
            await self._add_default_sounds()
        try:
            states: list[
                tuple[
                    Guild,
                    asyncio.Future[list[Member]] | None,
                    asyncio.Future[list[ChannelInfo]] | None,
                ]
            ] = []
            while True:
                # this snippet of code is basically waiting N seconds
                # until the last GUILD_CREATE was sent
                guild = await self._get_ready_guild()
                if guild is None:
                    break

                needs_chunking = await self._guild_needs_chunking(guild)
                if needs_chunking or self.cache_channel_info:
                    future = (
                        await self.chunk_guild(guild, wait=False)
                        if needs_chunking
                        else None
                    )
                    info_task: asyncio.Future[list[ChannelInfo]] | None = (
                        asyncio.ensure_future(self.request_guild_channel_info(guild))
                        if self.cache_channel_info
                        else None
                    )
                    states.append((guild, future, info_task))
                elif guild.unavailable is False:
                    self.dispatch("guild_available", guild)
                else:
                    self.dispatch("guild_join", guild)

            for guild, future, info_task in states:
                if future is not None:
                    await self._wait_for_guild_chunks(guild, future)
                if info_task is not None:
                    await self._wait_for_guild_channel_info(guild, info_task)

                if guild.unavailable is False:
                    self.dispatch("guild_available", guild)
                else:
                    self.dispatch("guild_join", guild)

            # remove the state
            with contextlib.suppress(AttributeError):
                del self._ready_state  # already been deleted somehow

        except asyncio.CancelledError:
            pass
        else:
            # dispatch the event
            self.call_handlers("ready")
            self.dispatch("ready")
        finally:
            self._ready_task = None

    async def _wait_for_guild_chunks(
        self, guild: Guild, future: asyncio.Future[list[Member]]
    ) -> None:
        try:
            await asyncio.wait_for(future, timeout=5.0)
        except asyncio.TimeoutError:
            _logger.warning(
                "Shard ID %s timed out waiting for chunks for guild_id %s.",
                guild.shard_id,
                guild.id,
            )
        except GatewayRateLimited:
            _logger.warning(
                "Chunking of guild ID %s was rate limited.",
                guild.id,
            )

    async def _wait_for_guild_channel_info(
        self, guild: Guild, task: asyncio.Future[list[ChannelInfo]]
    ) -> None:
        try:
            await asyncio.wait_for(task, timeout=5.0)
        except asyncio.TimeoutError:
            _logger.warning(
                "Shard ID %s timed out waiting for channel info for guild_id %s.",
                guild.shard_id,
                guild.id,
            )
        except Exception:
            _logger.exception(
                "Shard ID %s failed to request channel info for guild_id %s.",
                guild.shard_id,
                guild.id,
            )

    async def _get_create_guild(self, data: GuildPayload) -> Guild:
        if data.get("unavailable") is False:
            # GUILD_CREATE with unavailable in the response
            # usually means that the guild has become available
            # and is therefore in the cache
            guild = await self._get_guild(int(data["id"]))
            if guild is not None:
                guild.unavailable = False
                guild._from_data(data)
                await self._populate_guild(guild, data)
                await self._add_guild(guild)
                return guild

        return await self._add_guild_from_data(data)

    async def is_guild_evicted(self, guild: Guild) -> bool:
        """Return whether the guild is no longer cached."""
        return not await self._guilds.contains(guild.id)

    @overload
    async def chunk_guild(
        self, guild: Guild, *, wait: Literal[True] = True, cache: bool | None = None
    ) -> list[Member]: ...

    @overload
    async def chunk_guild(
        self, guild: Guild, *, wait: Literal[False], cache: bool | None = None
    ) -> asyncio.Future[list[Member]]: ...

    @overload
    async def chunk_guild(
        self, guild: Guild, *, wait: bool, cache: bool | None = None
    ) -> list[Member] | asyncio.Future[list[Member]]: ...

    async def chunk_guild(
        self, guild: Guild, *, wait: bool = True, cache: bool | None = None
    ) -> list[Member] | asyncio.Future[list[Member]]:
        """Request the members of a guild and wait for, or return, the chunks."""
        # Note: This method makes an API call without timeout, and should be used in
        #       conjunction with `asyncio.wait_for(..., timeout=...)`.
        cache = cache or self.member_cache_flags.joined
        request = self._chunk_requests.get(guild.id)  # nosec B113
        if request is None:
            self._chunk_requests[guild.id] = request = ChunkRequest(
                guild.id, self.loop, self._get_guild, cache=cache
            )
            await self.chunker(guild.id, nonce=request.nonce)

        if wait:
            return await request.wait()
        return request.get_future()

    async def request_guild_channel_info(
        self,
        guild: Guild,
        *,
        fields: Sequence[RequestChannelInfoField] = ("status", "voice_start_time"),
        cache: bool = True,
    ) -> list[ChannelInfo]:
        """Request the channel info of a guild and wait for the response."""
        fields = tuple(dict.fromkeys(fields))
        requests = self._channel_info_requests.setdefault(guild.id, [])
        request = next((r for r in requests if r.fields == fields), None)
        created = request is None
        if request is None:
            request = ChannelInfoRequest(
                guild.id, self.loop, self._get_guild, fields, cache=cache
            )
            requests.append(request)
        else:
            request.cache = request.cache or cache

        future = request.get_future()
        try:
            if created:
                ws = self._get_websocket(guild.id)
                await ws.request_channel_info(guild.id, fields=fields)
            return await future
        finally:
            request.waiters.remove(future)
            if not request.waiters:
                self._discard_info_request(request)

    async def _chunk_and_dispatch(self, guild: Guild, unavailable: bool | None) -> None:
        try:
            await asyncio.wait_for(self.chunk_guild(guild), timeout=60.0)
        except asyncio.TimeoutError:
            _logger.info("Somehow timed out waiting for chunks.")
        except GatewayRateLimited:
            _logger.info("Chunking of guild ID %s was rate limited.", guild.id)

        if unavailable is False:
            self.dispatch("guild_available", guild)
        else:
            self.dispatch("guild_join", guild)

    async def _get_member(
        self, guild_id: int | None, user_id: int | None
    ) -> Member | None:
        if guild_id is None or user_id is None:
            return None
        return await self._guild_bucket("members", guild_id).get(user_id)

    async def _get_typing_user(
        self, channel: MessageableChannel | None, user_id: int
    ) -> User | Member | None:
        if isinstance(channel, DMChannel):
            return channel.recipient or await self.get_user(user_id)

        if isinstance(channel, (Thread, TextChannel)):
            return await self._get_member(channel.guild_id, user_id)

        if isinstance(channel, GroupChannel):
            return utils.find(lambda x: x.id == user_id, channel.recipients)

        return await self.get_user(user_id)

    async def _get_reaction_user(
        self, channel: MessageableChannel | None, user_id: int
    ) -> User | Member | None:
        if isinstance(channel, TextChannel):
            return await self._get_member(channel.guild_id, user_id)
        return await self.get_user(user_id)

    async def get_reaction_emoji(
        self, data: PartialEmojiPayload
    ) -> GuildEmoji | AppEmoji | PartialEmoji | str | None:
        """Resolve a reaction emoji payload to a cached or partial emoji."""
        emoji_id = utils._get_as_snowflake(data, "id")

        if not emoji_id:
            return data["name"]

        emoji = await self.get_emoji(emoji_id)
        if emoji is not None:
            return emoji
        return PartialEmoji.with_state(
            self,
            animated=data.get("animated", False),
            id=emoji_id,
            name=data["name"],
        )

    async def _upgrade_partial_emoji(
        self, emoji: PartialEmoji
    ) -> GuildEmoji | AppEmoji | PartialEmoji | str:
        emoji_id = emoji.id
        if not emoji_id:
            return emoji.name or emoji
        return await self.get_emoji(emoji_id) or emoji

    async def get_channel(self, id: int | None) -> Channel | Thread | None:
        """Return the cached channel with the given ID, if any."""
        if id is None:
            return None

        pm = await self._get_private_channel(id)
        if pm is not None:
            return pm

        guild_id = await self._channel_guild.get(id)
        if guild_id is None:
            return None
        return await self._resolve_guild_channel(guild_id, id)

    async def _resolve_guild_channel(
        self, guild_id: int, channel_id: int
    ) -> GuildChannel | Thread | None:
        return await self._guild_bucket("channels", guild_id).get(
            channel_id
        ) or await self._guild_bucket("threads", guild_id).get(channel_id)

    def create_message(
        self,
        *,
        channel: MessageableChannel,
        data: MessagePayload,
    ) -> Message:
        """Build a message from its payload without touching the cache."""
        return Message(state=self, channel=channel, data=data)

    async def _create_message(
        self,
        *,
        channel: MessageableChannel,
        data: MessagePayload,
    ) -> Message:
        message = Message(state=self, channel=channel, data=data)
        await self._populate_message(message, data)
        return message

    async def _get_sound(self, sound_id: int | None) -> SoundboardSound | None:
        if sound_id is None:
            return None
        return await self._sounds.get(sound_id)

    async def _update_sound(self, sound: SoundboardSound) -> SoundboardSound | None:
        before = await self._sounds.get(sound.id)
        await self._sounds.set(sound.id, sound)
        guild_id = sound.guild_id
        if guild_id is not None:
            await self._guild_bucket("guild_sounds", guild_id).set(sound.id, sound)
        return before

    async def _add_default_sounds(self) -> None:
        default_sounds = await self.http.get_default_sounds()
        for default_sound in default_sounds:
            sound = SoundboardSound(state=self, http=self.http, data=default_sound)
            await self._add_sound(sound)

    async def _add_sound(self, sound: SoundboardSound) -> None:
        await self._sounds.set(sound.id, sound)
        guild_id = sound.guild_id
        if guild_id is not None:
            await self._guild_bucket("guild_sounds", guild_id).set(sound.id, sound)

    async def _remove_sound(self, sound: SoundboardSound) -> None:
        await self._sounds.pop(sound.id)
        guild_id = sound.guild_id
        if guild_id is not None:
            await self._guild_bucket("guild_sounds", guild_id).pop(sound.id)

    async def get_sounds(self) -> list[SoundboardSound]:
        """Return every cached soundboard sound."""
        return await self._sounds.values()

    async def _cache_fetched(self, obj: T, data: Any = None) -> T:
        if not self.cache_fetch:
            return obj
        await self._store_fetched(obj, data)
        return obj

    async def _cache_fetched_many(self, objs: list[T]) -> list[T]:
        if self.cache_fetch:
            for obj in objs:
                await self._store_fetched(obj, None)
        return objs

    async def _fetch_channel(self, channel_id: int) -> Channel | Thread:
        data = await self.http.get_channel(channel_id)

        factory, ch_type = _threaded_channel_factory(data["type"])
        if factory is None:
            raise InvalidData(
                "Unknown channel type {type} for channel ID {id}.".format_map(data)
            )

        channel: Channel | Thread
        if ch_type in (ChannelType.group, ChannelType.private):
            # the factory will be a DMChannel or GroupChannel here
            private_factory = cast("Callable[..., DMChannel | GroupChannel]", factory)
            channel = private_factory(
                me=cast("ClientUser", self.user), data=data, state=self
            )
        else:
            # the factory can't be a DMChannel or GroupChannel here
            threaded_factory = cast("Callable[..., GuildChannel | Thread]", factory)
            channel = threaded_factory(
                guild=PartialGuild(state=self, id=int(cast("Any", data)["guild_id"])),
                state=self,
                data=data,
            )
        return await self._cache_fetched(channel)

    async def _populate_message(self, message: Message, data: MessagePayload) -> None:
        guild_id = message.guild_id
        if self._cache_users and "author" in data:
            await self.store_user(data["author"])

        if guild_id is not None:
            members = self._guild_bucket("members", guild_id)
            if "author" in data:
                cached = await members.get(message.author.id)
                if cached is not None:
                    if "member" in data:
                        cached._update_from_message(data["member"])
                        await members.set(cached.id, cached)
                    message.author = cached

            if "mentions" in data:
                message.mentions = [
                    await members.get(int(mention["id"])) or built
                    for mention, built in zip(
                        filter(None, data["mentions"]), message.mentions, strict=True
                    )
                ]

            if "mention_roles" in data:
                roles = self._guild_bucket("roles", guild_id)
                message.role_mentions = [
                    role
                    for role_id in map(int, data["mention_roles"])
                    if (role := await roles.get(role_id)) is not None
                ]

        if message.thread is not None:
            thread_guild_id = message.thread.guild_id
            if await self._get_guild(thread_guild_id) is None:
                message.thread = None
            else:
                cached_thread = await self._guild_bucket(
                    "threads", thread_guild_id
                ).get(message.thread.id)
                if cached_thread is not None:
                    message.thread = cached_thread

        for reaction in message.reactions:
            if isinstance(reaction.emoji, PartialEmoji) and reaction.emoji.id:
                reaction.emoji = (
                    await self.get_emoji(reaction.emoji.id) or reaction.emoji
                )

        if message._poll is not None:
            if message._poll.results is None:
                # results is nullable, so grab old results if necessary.
                old_poll = await self.get_poll(message.id)
                if old_poll is not None:
                    message._poll.results = old_poll.results
            await self.store_poll(message._poll, message.id)

        reference = message.reference
        referenced = data.get("referenced_message")
        if (
            reference is not None
            and isinstance(reference.resolved, Message)
            and referenced is not None
        ):
            await self._populate_message(reference.resolved, referenced)

    async def _build_thread(
        self, guild: Guild | PartialGuild, data: ThreadPayload
    ) -> Thread:
        invoke = data.pop("_invoke_flag", False)
        thread = Thread(guild=guild, state=self, data=data)
        if invoke:
            cached = await self._guild_bucket("threads", guild.id).get(thread.id)
            if cached is not None:
                for name in (
                    "owner_id",
                    "last_message_id",
                    "message_count",
                    "total_message_sent",
                    "member_count",
                ):
                    if getattr(thread, name) is None:
                        setattr(thread, name, getattr(cached, name))
        return thread

    async def _populate_interaction(
        self, interaction: Interaction, data: InteractionPayload
    ) -> None:
        guild_id = interaction.guild_id
        if guild_id is not None:
            guild = await self._get_guild(guild_id)
            member = data.get("member")
            if guild is not None and member is not None:
                interaction.user = await guild._get_and_update_member(
                    member,
                    int(member["user"]["id"]),
                    self.member_cache_flags.interaction,
                )
            channel = (
                await self._resolve_guild_channel(guild_id, interaction.channel_id)
                if interaction.channel_id is not None
                else None
            )
            if channel is not None and not getattr(channel, "obfuscated", False):
                interaction.channel = channel

        if interaction.message is not None and interaction._message_data is not None:
            await self._populate_message(interaction.message, interaction._message_data)

    async def _store_fetched(self, obj: Any, data: Any) -> None:
        if isinstance(obj, ClientUser):
            return
        if isinstance(obj, User):
            await self._users.set(obj.id, obj)
        elif isinstance(obj, Guild):
            await self._add_guild(obj)
            if data is not None:
                await self._populate_guild(obj, data)
        elif isinstance(obj, Member):
            if not self.member_cache_flags._empty:
                await self._guild_bucket("members", obj.guild_id).set(obj.id, obj)
        elif isinstance(obj, Thread):
            await self._add_thread(obj.guild_id, obj)
        elif isinstance(obj, (DMChannel, GroupChannel)):
            await self._add_private_channel(obj)
        elif isinstance(obj, GuildChannelBase):
            await self._add_channel(obj.guild_id, obj)
        elif isinstance(obj, Message):
            await self._store_message(obj)
        elif isinstance(obj, ThreadMember):
            await self._store.bucket("thread_members", scope=obj.thread_id).set(
                obj.id, obj
            )
        elif isinstance(obj, Role):
            await self._guild_bucket("roles", obj.guild_id).set(obj.id, obj)
        elif isinstance(obj, GuildEmoji):
            await self._emojis.set(obj.id, obj)
            await self._guild_bucket("guild_emojis", obj.guild_id).set(obj.id, obj)
        elif isinstance(obj, AppEmoji):
            await self._app_emojis.set(obj.id, obj)
        elif isinstance(obj, GuildSticker):
            await self._stickers.set(obj.id, obj)
            await self._guild_bucket("guild_stickers", obj.guild_id).set(obj.id, obj)
        elif isinstance(obj, ScheduledEvent):
            await self._guild_bucket("scheduled_events", obj.guild_id).set(obj.id, obj)
        elif isinstance(obj, StageInstance):
            await self._guild_bucket("stage_instances", obj.guild_id).set(obj.id, obj)
        elif isinstance(obj, SoundboardSound):
            await self._add_sound(obj)
