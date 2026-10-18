"""
The MIT License (MIT)

Copyright (c) 2015-2021 Rapptz
Copyright (c) 2021-present Pycord Development

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.
"""

from __future__ import annotations

import asyncio
import datetime as dt
from collections.abc import AsyncIterator, Awaitable, Callable, Generator, Iterable
from typing import (
    TYPE_CHECKING,
    Any,
    TypeVar,
    Union,
    cast,
)

from typing_extensions import deprecated, override

from .audit_logs import AuditLogEntry
from .errors import ClientException, HTTPException, NoMoreItems
from .message_search import SearchIndexNotReady
from .object import Object
from .utils import maybe_coroutine, snowflake_time, time_snowflake

__all__ = (
    "AuditLogIterator",
    "EntitlementIterator",
    "GuildIterator",
    "HistoryIterator",
    "MemberIterator",
    "MessagePinIterator",
    "MessageSearchIterator",
    "ReactionIterator",
    "ScheduledEventSubscribersIterator",
    "SubscriptionIterator",
)

if TYPE_CHECKING:
    from .abc import Messageable, MessageableChannel, Snowflake, SnowflakeTime
    from .client import Client
    from .enums import AuditLogAction
    from .guild import BanEntry, Guild, PartialGuild
    from .http import HTTPClient
    from .member import Member
    from .message import Message, MessagePin, PartialMessage
    from .monetization import Entitlement, Subscription
    from .poll import PollAnswer
    from .scheduled_events import ScheduledEvent
    from .state import ConnectionState
    from .threads import Thread
    from .types.audit_log import (
        AuditLog as AuditLogPayload,
        AuditLogEntry as AuditLogEntryPayload,
    )
    from .types.guild import Ban as BanPayload, Guild as GuildPayload
    from .types.member import MemberWithUser as MemberWithUserPayload
    from .types.message import (
        Message as MessagePayload,
        MessagePin as MessagePinPayload,
        MessageSearchResults,
    )
    from .types.monetization import (
        Entitlement as EntitlementPayload,
        Subscription as SubscriptionPayload,
    )
    from .types.scheduled_events import (
        ScheduledEventSubscriber as ScheduledEventSubscriberPayload,
    )
    from .types.threads import Thread as ThreadPayload
    from .types.user import User as UserPayload
    from .user import User

T = TypeVar("T")
OT = TypeVar("OT")
_Func = Callable[[T], OT | Awaitable[OT]]

OLDEST_OBJECT = Object(id=0)


def _snowflake_bound(value: SnowflakeTime | None, *, high: bool) -> Snowflake | None:
    if isinstance(value, dt.datetime):
        return Object(id=time_snowflake(value, high=high))
    return value


class _AsyncIterator(AsyncIterator[T]):
    __slots__ = ()

    async def next(self) -> T:
        raise NotImplementedError

    def get(self, **attrs: Any) -> Awaitable[T | None]:
        def predicate(elem: T) -> bool:
            for attr, val in attrs.items():
                nested = attr.split("__")
                obj = elem
                for attribute in nested:
                    obj = getattr(obj, attribute)

                if obj != val:
                    return False
            return True

        return self.find(predicate)

    async def find(self, predicate: _Func[T, bool]) -> T | None:
        while True:
            try:
                elem = await self.next()
            except NoMoreItems:
                return None

            ret = await maybe_coroutine(predicate, elem)
            if ret:
                return elem

    def chunk(self, max_size: int) -> _ChunkedAsyncIterator[T]:
        if max_size <= 0:
            raise ValueError("async iterator chunk sizes must be greater than 0.")
        return _ChunkedAsyncIterator(self, max_size)

    def map(self, func: _Func[T, OT]) -> _MappedAsyncIterator[OT]:
        return _MappedAsyncIterator(self, func)

    def filter(self, predicate: _Func[T, bool]) -> _FilteredAsyncIterator[T]:
        return _FilteredAsyncIterator(self, predicate)

    async def flatten(self) -> list[T]:
        return [element async for element in self]

    async def __anext__(self) -> T:
        try:
            return await self.next()
        except NoMoreItems:
            raise StopAsyncIteration from None


def _identity(x: T) -> T:
    return x


class _ChunkedAsyncIterator(_AsyncIterator[list[T]]):
    def __init__(self, iterator: _AsyncIterator[T], max_size: int) -> None:
        self.iterator: _AsyncIterator[T] = iterator
        self.max_size: int = max_size

    async def next(self) -> list[T]:
        ret: list[T] = []
        try:
            while len(ret) < self.max_size:
                ret.append(await self.iterator.next())
        except NoMoreItems:
            if not ret:
                raise
        return ret


class _MappedAsyncIterator(_AsyncIterator[T]):
    def __init__(self, iterator: _AsyncIterator[Any], func: _Func[Any, T]) -> None:
        self.iterator: _AsyncIterator[Any] = iterator
        self.func: _Func[Any, T] = func

    async def next(self) -> T:
        # this raises NoMoreItems and will propagate appropriately
        item = await self.iterator.next()
        return await maybe_coroutine(self.func, item)


class _FilteredAsyncIterator(_AsyncIterator[T]):
    def __init__(
        self, iterator: _AsyncIterator[T], predicate: _Func[T, object] | None
    ) -> None:
        self.iterator: _AsyncIterator[T] = iterator

        if predicate is None:
            predicate = _identity

        self.predicate: _Func[T, object] = predicate

    async def next(self) -> T:
        getter = self.iterator.next
        pred = self.predicate
        while True:
            # propagate NoMoreItems similar to _MappedAsyncIterator
            item = await getter()
            ret = await maybe_coroutine(pred, item)
            if ret:
                return item


class ReactionIterator(_AsyncIterator[Union["User", "Member"]]):
    """Iterator over the users that reacted to a message."""

    def __init__(
        self,
        message: Message | PartialMessage,
        emoji: str,
        limit: int = 100,
        after: Snowflake | None = None,
        type: int | None = None,
    ) -> None:
        self.message: Message | PartialMessage = message
        self.limit: int = limit
        self.after: Snowflake | None = after
        self.type: int | None = type
        state = message._state
        self.getter = state.http.get_reaction_users
        self.state: ConnectionState = state
        self.emoji: str = emoji
        self.guild_id: int | None = getattr(message.guild, "id", None)
        self.channel_id: int = message.channel.id
        self.users: asyncio.Queue[User | Member] = asyncio.Queue()

    @override
    async def next(self) -> User | Member:
        """Return the next user, fetching a new page when needed."""
        if self.users.empty():
            await self.fill_users()

        try:
            return self.users.get_nowait()
        except asyncio.QueueEmpty:
            raise NoMoreItems from None

    async def fill_users(self) -> None:
        """Fetch the next page of users into the queue."""
        # this is a hack because >circular imports<
        from .user import User

        if self.limit > 0:
            retrieve = min(self.limit, 100)

            after = self.after.id if self.after else None
            data: list[UserPayload] = await self.getter(
                self.channel_id,
                self.message.id,
                self.emoji,
                retrieve,
                after=after,
                type=self.type,
            )

            if data:
                self.limit -= retrieve
                self.after = Object(id=int(data[-1]["id"]))

            for element in reversed(data):
                if self.guild_id is None:
                    await self.users.put(User(state=self.state, data=element))
                else:
                    member = await self.state._get_member(
                        self.guild_id, int(element["id"])
                    )
                    if member is not None:
                        await self.users.put(member)
                    else:
                        await self.users.put(User(state=self.state, data=element))


class VoteIterator(_AsyncIterator[Union["User", "Member"]]):
    """Iterator over the users that voted for a poll answer."""

    def __init__(
        self,
        message: Message | PartialMessage,
        answer: PollAnswer,
        limit: int = 100,
        after: Snowflake | None = None,
    ) -> None:
        self.message: Message | PartialMessage = message
        self.limit: int = limit
        self.after: Snowflake | None = after
        state = message._state
        self.getter = state.http.get_answer_voters
        self.state: ConnectionState = state
        self.answer: PollAnswer = answer
        self.guild_id: int | None = getattr(message.guild, "id", None)
        self.channel_id: int = message.channel.id
        self.users: asyncio.Queue[User | Member] = asyncio.Queue()

    @override
    async def next(self) -> User | Member:
        """Return the next voter, fetching a new page when needed."""
        if self.users.empty():
            await self.fill_users()

        try:
            return self.users.get_nowait()
        except asyncio.QueueEmpty:
            raise NoMoreItems from None

    async def fill_users(self) -> None:
        """Fetch the next page of voters into the queue."""
        # import here to prevent circular imports
        from .user import User

        if self.limit > 0:
            retrieve = min(self.limit, 100)

            after = self.after.id if self.after else None
            req = await self.getter(
                self.channel_id,
                self.message.id,
                cast("int", self.answer.id),
                retrieve,
                after=after,
            )
            data: list[UserPayload] = req.get("users", [])

            if data:
                self.limit -= retrieve
                self.after = Object(id=int(data[-1]["id"]))

            for element in reversed(data):
                if self.guild_id is None:
                    await self.users.put(User(state=self.state, data=element))
                else:
                    member = await self.state._get_member(
                        self.guild_id, int(element["id"])
                    )
                    if member is not None:
                        await self.users.put(member)
                    else:
                        await self.users.put(User(state=self.state, data=element))


class HistoryIterator(_AsyncIterator["Message"]):
    """Iterator for receiving a channel's message history.

    The messages endpoint has two behaviours we care about here:
    If ``before`` is specified, the messages endpoint returns the `limit`
    newest messages before ``before``, sorted with newest first. For filling over
    100 messages, update the ``before`` parameter to the oldest message received.
    Messages will be returned in order by time.
    If ``after`` is specified, it returns the ``limit`` oldest messages after
    ``after``, sorted with newest first. For filling over 100 messages, update the
    ``after`` parameter to the newest message received. If messages are not
    reversed, they will be out of order (99-0, 199-100, so on)

    A note that if both ``before`` and ``after`` are specified, ``before`` is ignored by the
    messages endpoint.

    Parameters
    ----------
    messageable: :class:`abc.Messageable`
        Messageable class to retrieve message history from.
    limit: :class:`int`
        Maximum number of messages to retrieve
    before: Optional[Union[:class:`abc.Snowflake`, :class:`datetime.datetime`]]
        Message before which all messages must be.
    after: Optional[Union[:class:`abc.Snowflake`, :class:`datetime.datetime`]]
        Message after which all messages must be.
    around: Optional[Union[:class:`abc.Snowflake`, :class:`datetime.datetime`]]
        Message around which all messages must be. Limit max 101. Note that if
        limit is an even number, this will return at most limit+1 messages.
    oldest_first: Optional[:class:`bool`]
        If set to ``True``, return messages in oldest->newest order. Defaults to
        ``True`` if `after` is specified, otherwise ``False``.
    """

    channel: MessageableChannel

    def __init__(
        self,
        messageable: Messageable,
        limit: int | None,
        before: SnowflakeTime | None = None,
        after: SnowflakeTime | None = None,
        around: SnowflakeTime | None = None,
        oldest_first: bool | None = None,
    ) -> None:
        before_bound = _snowflake_bound(before, high=False)
        after_bound = _snowflake_bound(after, high=True)
        around_bound = _snowflake_bound(around, high=False)

        self.reverse: bool = after is not None if oldest_first is None else oldest_first
        self.messageable: Messageable = messageable
        self.limit: int | None = limit
        self.before: Snowflake | None = before_bound
        self.after: Snowflake = after_bound or OLDEST_OBJECT
        self.around: Snowflake | None = around_bound
        self.retrieve: int

        self._filter: Callable[[MessagePayload], bool] | None = None

        self.state: ConnectionState = self.messageable._state
        self.logs_from = self.state.http.logs_from
        self.messages: asyncio.Queue[Message] = asyncio.Queue()
        self._retrieve_messages: Callable[[int], Awaitable[list[MessagePayload]]]

        if self.around:
            if self.limit is None:
                raise ValueError("history does not support around with limit=None")
            if self.limit > 101:
                raise ValueError(
                    "history max limit 101 when specifying around parameter"
                )
            if self.limit == 101:
                self.limit = 100  # Thanks discord

            self._retrieve_messages = self._retrieve_messages_around_strategy
            if self.before and self.after:
                before_id, after_id = self.before.id, self.after.id
                self._filter = lambda m: after_id < int(m["id"]) < before_id
            elif self.before:
                before_id = self.before.id
                self._filter = lambda m: int(m["id"]) < before_id
            elif self.after:
                after_id = self.after.id
                self._filter = lambda m: after_id < int(m["id"])
        elif self.reverse:
            self._retrieve_messages = self._retrieve_messages_after_strategy
            if self.before:
                before_id = self.before.id
                self._filter = lambda m: int(m["id"]) < before_id
        else:
            self._retrieve_messages = self._retrieve_messages_before_strategy
            if self.after and self.after != OLDEST_OBJECT:
                after_id = self.after.id
                self._filter = lambda m: int(m["id"]) > after_id

    @override
    async def next(self) -> Message:
        """Return the next message, fetching a new page when needed."""
        if self.messages.empty():
            await self.fill_messages()

        try:
            return self.messages.get_nowait()
        except asyncio.QueueEmpty:
            raise NoMoreItems from None

    def _get_retrieve(self) -> bool:
        limit = self.limit
        r = 100 if limit is None or limit > 100 else limit
        self.retrieve = r
        return r > 0

    async def fill_messages(self) -> None:
        """Fetch the next page of messages into the queue."""
        if not hasattr(self, "channel"):
            # do the required set up
            channel = await self.messageable._get_channel()
            self.channel = channel

        if self._get_retrieve():
            data = await self._retrieve_messages(self.retrieve)
            if len(data) < 100:
                self.limit = 0  # terminate the infinite loop

            items: Iterable[MessagePayload] = reversed(data) if self.reverse else data
            if self._filter:
                items = filter(self._filter, items)

            channel = self.channel
            for element in items:
                await self.messages.put(
                    await self.state._create_message(channel=channel, data=element)
                )

    async def _retrieve_messages_before_strategy(
        self, retrieve: int
    ) -> list[MessagePayload]:
        """Retrieve messages using before parameter."""
        before = self.before.id if self.before else None
        data: list[MessagePayload] = await self.logs_from(
            self.channel.id, retrieve, before=before
        )
        if len(data):
            if self.limit is not None:
                self.limit -= retrieve
            self.before = Object(id=int(data[-1]["id"]))
        return data

    async def _retrieve_messages_after_strategy(
        self, retrieve: int
    ) -> list[MessagePayload]:
        """Retrieve messages using after parameter."""
        after = self.after.id if self.after else None
        data: list[MessagePayload] = await self.logs_from(
            self.channel.id, retrieve, after=after
        )
        if len(data):
            if self.limit is not None:
                self.limit -= retrieve
            self.after = Object(id=int(data[0]["id"]))
        return data

    async def _retrieve_messages_around_strategy(
        self, retrieve: int
    ) -> list[MessagePayload]:
        """Retrieve messages using around parameter."""
        if self.around:
            around = self.around.id if self.around else None
            data: list[MessagePayload] = await self.logs_from(
                self.channel.id, retrieve, around=around
            )
            self.around = None
            return data
        return []


class AuditLogIterator(_AsyncIterator["AuditLogEntry"]):
    """Iterator over the audit log entries of a guild."""

    def __init__(
        self,
        guild: Guild | PartialGuild,
        limit: int | None = None,
        before: SnowflakeTime | None = None,
        after: SnowflakeTime | None = None,
        user_id: int | None = None,
        action_type: AuditLogAction | int | None = None,
    ) -> None:
        self.guild: Guild | PartialGuild = guild
        self.loop = guild._state.loop
        self.request = guild._state.http.get_audit_logs
        self.limit: int | None = limit
        self.before: Snowflake | None = _snowflake_bound(before, high=False)
        self.user_id: int | None = user_id
        self.action_type: AuditLogAction | int | None = action_type
        self.after: Snowflake | None = _snowflake_bound(after, high=True)
        self._users: dict[int, User] = {}
        self._state: ConnectionState = guild._state
        self.entries: asyncio.Queue[AuditLogEntry] = asyncio.Queue()
        self.retrieve: int

    async def _retrieve_entries(
        self, retrieve: int
    ) -> tuple[list[UserPayload], list[AuditLogEntryPayload]]:
        before = self.before.id if self.before else None
        after = self.after.id if self.after else None
        data: AuditLogPayload = await self.request(
            self.guild.id,
            limit=retrieve,
            user_id=self.user_id,
            action_type=self.action_type,
            before=before,
            after=after,
        )

        entries = data.get("audit_log_entries", [])
        # if ONLY after is passed and NOT before, Discord reverses the sort to oldest first.
        if len(data) and entries:
            if self.limit is not None:
                self.limit -= retrieve
            if self.before or not self.after:
                self.before = Object(id=int(entries[-1]["id"]))
            if self.after and not self.before:
                self.after = Object(id=int(entries[-1]["id"]))
        return data.get("users", []), entries

    @override
    async def next(self) -> AuditLogEntry:
        """Return the next audit log entry, fetching a new page when needed."""
        if self.entries.empty():
            await self._fill()

        try:
            return self.entries.get_nowait()
        except asyncio.QueueEmpty:
            raise NoMoreItems from None

    def _get_retrieve(self) -> bool:
        limit = self.limit
        r = 100 if limit is None or limit > 100 else limit
        self.retrieve = r
        return r > 0

    async def _fill(self) -> None:
        from .user import User

        if self._get_retrieve():
            users, data = await self._retrieve_entries(self.retrieve)
            if len(data) < 100:
                self.limit = 0  # terminate the infinite loop

            for user in users:
                u = User(data=user, state=self._state)
                self._users[u.id] = u

            for element in data:
                await self.entries.put(
                    AuditLogEntry(data=element, users=self._users, guild=self.guild)
                )


class GuildIterator(_AsyncIterator["Guild"]):
    """Iterator for receiving the client's guilds.

    The guilds endpoint has the same two behaviours as described
    in :class:`HistoryIterator`:
    If ``before`` is specified, the guilds endpoint returns the ``limit``
    newest guilds before ``before``, sorted with newest first. For filling over
    100 guilds, update the ``before`` parameter to the oldest guild received.
    Guilds will be returned in order by time.
    If `after` is specified, it returns the ``limit`` oldest guilds after ``after``,
    sorted with newest first. For filling over 100 guilds, update the ``after``
    parameter to the newest guild received, If guilds are not reversed, they
    will be out of order (99-0, 199-100, so on)

    Not that if both ``before`` and ``after`` are specified, ``before`` is ignored by the
    guilds endpoint.

    Parameters
    ----------
    bot: :class:`discord.Client`
        The client to retrieve the guilds from.
    limit: :class:`int`
        Maximum number of guilds to retrieve.
    before: Optional[Union[:class:`abc.Snowflake`, :class:`datetime.datetime`]]
        Object before which all guilds must be.
    after: Optional[Union[:class:`abc.Snowflake`, :class:`datetime.datetime`]]
        Object after which all guilds must be.
    with_counts: :class:`bool`
        Whether to include member count information in guilds. This fills the
        :attr:`.Guild.approximate_member_count` and :attr:`.Guild.approximate_presence_count`
        fields.
        Defaults to ``True``.
    shard: Optional[:class:`int`]
        Only retrieve the guilds stored in this shard (``0`` to ``max_concurrency - 1``).
        Required by Discord for apps using large bot sharding. It is not the gateway shard ID.
        When :attr:`.Client.session_start_limit` is known, a value outside of
        ``0`` to ``max_concurrency - 1`` raises :exc:`ValueError`.
    all_shards: :class:`bool`
        Whether to retrieve the guilds of every shard from ``0`` to ``max_concurrency - 1``
        one after the other, ``max_concurrency`` being read from :attr:`.Client.session_start_limit`.
        Mutually exclusive with ``shard``.
    """

    def __init__(
        self,
        bot: Client,
        limit: int | None,
        before: SnowflakeTime | None = None,
        after: SnowflakeTime | None = None,
        with_counts: bool = True,
        *,
        shard: int | None = None,
        all_shards: bool = False,
    ) -> None:
        if shard is not None and all_shards:
            raise ValueError("shard and all_shards are mutually exclusive")
        before_bound = _snowflake_bound(before, high=False)
        after_bound = _snowflake_bound(after, high=True)

        self.bot: Client = bot
        self.limit: int | None = limit
        self.before: Snowflake | None = before_bound
        self.after: Snowflake | None = after_bound
        self.with_counts: bool = with_counts
        self.shard: int | None = shard
        self._all_shards: bool = all_shards
        self._pending_shards: list[int] | None = None
        self._first = (before_bound, after_bound)
        self._total_left: int | None = limit

        self._filter: Callable[[GuildPayload], bool] | None = None

        self.state: ConnectionState = self.bot._connection
        self.guilds: asyncio.Queue[Guild] = asyncio.Queue()
        self.retrieve: int
        self._retrieve_guilds: Callable[[int], Awaitable[list[GuildPayload]]]

        if self.before and self.after:
            self._retrieve_guilds = self._retrieve_guilds_before_strategy
            after_id = self.after.id
            self._filter = lambda m: int(m["id"]) > after_id
        elif self.after:
            self._retrieve_guilds = self._retrieve_guilds_after_strategy
        else:
            self._retrieve_guilds = self._retrieve_guilds_before_strategy

    def _max_concurrency(self) -> int | None:
        session_start_limit = self.bot.session_start_limit
        return session_start_limit.max_concurrency if session_start_limit else None

    def _advance_shard(self) -> bool:
        if not self._all_shards or self._total_left == 0:
            return False
        if self._pending_shards is None:
            max_concurrency = self._max_concurrency()
            if max_concurrency is None:
                raise ClientException(
                    "all_shards needs Client.session_start_limit, log in first"
                )
            self._pending_shards = list(range(max_concurrency))
        if not self._pending_shards:
            return False
        self.shard = self._pending_shards.pop(0)
        self.before, self.after = self._first
        self.limit = self._total_left
        self._retrieve_guilds = (
            self._retrieve_guilds_after_strategy
            if self.after and not self.before
            else self._retrieve_guilds_before_strategy
        )
        return True

    @override
    async def next(self) -> Guild:
        """Return the next guild, fetching a new page when needed."""
        if self._all_shards and self._pending_shards is None:
            self._advance_shard()

        while True:
            if self.guilds.empty():
                await self.fill_guilds()

            try:
                guild = self.guilds.get_nowait()
            except asyncio.QueueEmpty:
                if not self._advance_shard():
                    raise NoMoreItems from None
                continue
            if self._total_left is not None:
                self._total_left -= 1
            return guild

    def _get_retrieve(self) -> bool:
        limit = self.limit
        r = 100 if limit is None or limit > 100 else limit
        self.retrieve = r
        return r > 0

    def create_guild(self, data: GuildPayload) -> Guild:
        """Build a guild from its payload."""
        from .guild import Guild

        return Guild(state=self.state, data=data)

    async def fill_guilds(self) -> None:
        """Fetch the next page of guilds into the queue."""
        if self._get_retrieve():
            data = await self._retrieve_guilds(self.retrieve)
            if self.limit is None or len(data) < 100:
                self.limit = 0

            items: Iterable[GuildPayload] = data
            if self._filter:
                items = filter(self._filter, items)

            for element in items:
                await self.guilds.put(self.create_guild(element))

    async def get_guilds(self, retrieve: int, **kwargs: Any) -> list[GuildPayload]:
        """Request a page of guilds from Discord."""
        if self.shard is not None:
            max_concurrency = self._max_concurrency()
            if max_concurrency is not None and not 0 <= self.shard < max_concurrency:
                raise ValueError(
                    f"shard must be between 0 and {max_concurrency - 1} (max_concurrency - 1)"
                )
            kwargs["shard"] = self.shard
        try:
            return await self.bot.http.get_guilds(retrieve, **kwargs)
        except HTTPException as exc:
            if exc.status != 400 or self.shard is not None:
                raise
            hint = (
                "Get Current User Guilds requires the shard parameter when the app uses"
                " large bot sharding. Pass all_shards=True to Client.fetch_guilds(), or"
                " shard=N for every N from 0 to max_concurrency - 1."
            )
            exc.text = f"{exc.text} {hint}".strip()
            exc.args = (f"{exc.args[0]}: {hint}",)
            raise

    async def _retrieve_guilds_before_strategy(
        self, retrieve: int
    ) -> list[GuildPayload]:
        """Retrieve guilds using before parameter."""
        before = self.before.id if self.before else None
        data: list[GuildPayload] = await self.get_guilds(
            retrieve, before=before, with_counts=self.with_counts
        )
        if len(data):
            if self.limit is not None:
                self.limit -= retrieve
            self.before = Object(id=int(data[-1]["id"]))
        return data

    async def _retrieve_guilds_after_strategy(
        self, retrieve: int
    ) -> list[GuildPayload]:
        """Retrieve guilds using after parameter."""
        after = self.after.id if self.after else None
        data: list[GuildPayload] = await self.get_guilds(
            retrieve, after=after, with_counts=self.with_counts
        )
        if len(data):
            if self.limit is not None:
                self.limit -= retrieve
            self.after = Object(id=int(data[0]["id"]))
        return data


class MemberIterator(_AsyncIterator["Member"]):
    """Iterator over the members of a guild."""

    def __init__(
        self,
        guild: Guild | PartialGuild,
        limit: int | None = 1000,
        after: SnowflakeTime | None = None,
    ) -> None:
        self.guild: Guild | PartialGuild = guild
        self.limit: int | None = limit
        self.after: Snowflake = _snowflake_bound(after, high=True) or OLDEST_OBJECT

        self.state: ConnectionState = self.guild._state
        self.get_members = self.state.http.get_members
        self.members: asyncio.Queue[Member] = asyncio.Queue()
        self.retrieve: int

    @override
    async def next(self) -> Member:
        """Return the next member, fetching a new page when needed."""
        if self.members.empty():
            await self.fill_members()

        try:
            return self.members.get_nowait()
        except asyncio.QueueEmpty:
            raise NoMoreItems from None

    def _get_retrieve(self) -> bool:
        limit = self.limit
        r = 1000 if limit is None or limit > 1000 else limit
        self.retrieve = r
        return r > 0

    async def fill_members(self) -> None:
        """Fetch the next page of members into the queue."""
        if not self._get_retrieve():
            return
        after = self.after.id if self.after else None
        data = await self.get_members(self.guild.id, self.retrieve, after)
        if not data:
            # no data, terminate
            return

        if len(data) < 1000:
            self.limit = 0  # terminate loop

        self.after = Object(id=int(data[-1]["user"]["id"]))

        for element in reversed(data):
            await self.members.put(self.create_member(element))

    def create_member(self, data: MemberWithUserPayload) -> Member:
        """Build a member from its payload."""
        from .member import Member

        return Member(data=data, guild=self.guild, state=self.state)


class BanIterator(_AsyncIterator["BanEntry"]):
    """Iterator over the bans of a guild."""

    def __init__(
        self,
        guild: Guild | PartialGuild,
        limit: int | None = None,
        before: Snowflake | None = None,
        after: Snowflake | None = None,
    ) -> None:
        self.guild: Guild | PartialGuild = guild
        self.limit: int | None = limit
        self.after: Snowflake | None = after
        self.before: Snowflake | None = before

        self.state: ConnectionState = self.guild._state
        self.get_bans = self.state.http.get_bans
        self.bans: asyncio.Queue[BanEntry] = asyncio.Queue()
        self.retrieve: int

    @override
    async def next(self) -> BanEntry:
        """Return the next ban, fetching a new page when needed."""
        if self.bans.empty():
            await self.fill_bans()

        try:
            return self.bans.get_nowait()
        except asyncio.QueueEmpty:
            raise NoMoreItems from None

    def _get_retrieve(self) -> bool:
        limit = self.limit
        r = 1000 if limit is None or limit > 1000 else limit
        self.retrieve = r
        return r > 0

    async def fill_bans(self) -> None:
        """Fetch the next page of bans into the queue."""
        if not self._get_retrieve():
            return
        before = self.before.id if self.before else None
        after = self.after.id if self.after else None
        data = await self.get_bans(self.guild.id, self.retrieve, before, after)
        if not data:
            # no data, terminate
            return
        if self.limit:
            self.limit -= self.retrieve

        if len(data) < 1000:
            self.limit = 0  # terminate loop

        self.after = Object(id=int(data[-1]["user"]["id"]))

        for element in reversed(data):
            await self.bans.put(self.create_ban(element))

    def create_ban(self, data: BanPayload) -> BanEntry:
        """Build a ban entry from its payload."""
        from .guild import BanEntry
        from .user import User

        return BanEntry(
            reason=data["reason"], user=User(state=self.state, data=data["user"])
        )


class ArchivedThreadIterator(_AsyncIterator["Thread"]):
    """Iterator over the archived threads of a channel."""

    def __init__(
        self,
        channel_id: int,
        guild: Guild | PartialGuild,
        limit: int | None,
        joined: bool,
        private: bool,
        before: Snowflake | dt.datetime | None = None,
    ) -> None:
        self.channel_id = channel_id
        self.guild = guild
        self.limit = limit
        self.joined = joined
        self.private = private
        self.http = guild._state.http

        if joined and not private:
            raise ValueError("Cannot iterate over joined public archived threads")

        self.before: str | None
        if before is None:
            self.before = None
        elif isinstance(before, dt.datetime):
            if joined:
                self.before = str(time_snowflake(before, high=False))
            else:
                self.before = before.isoformat()
        elif joined:
            self.before = str(before.id)
        else:
            self.before = snowflake_time(before.id).isoformat()

        self.update_before: Callable[[ThreadPayload], str] = self.get_archive_timestamp

        if joined:
            self.endpoint = self.http.get_joined_private_archived_threads
            self.update_before = self.get_thread_id
        elif private:
            self.endpoint = self.http.get_private_archived_threads
        else:
            self.endpoint = self.http.get_public_archived_threads

        self.queue: asyncio.Queue[Thread] = asyncio.Queue()
        self.has_more: bool = True

    @override
    async def next(self) -> Thread:
        """Return the next thread, fetching a new page when needed."""
        if self.queue.empty():
            await self.fill_queue()

        try:
            return self.queue.get_nowait()
        except asyncio.QueueEmpty:
            raise NoMoreItems from None

    @staticmethod
    def get_archive_timestamp(data: ThreadPayload) -> str:
        """Return the archive timestamp of a thread payload."""
        return data["thread_metadata"]["archive_timestamp"]

    @staticmethod
    def get_thread_id(data: ThreadPayload) -> str:
        """Return the ID of a thread payload as a string."""
        return str(data["id"])

    async def fill_queue(self) -> None:
        """Fetch the next page of threads into the queue."""
        if not self.has_more:
            raise NoMoreItems

        limit = 50 if self.limit is None else min(self.limit, 50)
        data = await self.endpoint(self.channel_id, before=self.before, limit=limit)

        # This stuff is obviously WIP because 'members' is always empty
        threads: list[ThreadPayload] = data.get("threads", [])
        for d in reversed(threads):
            self.queue.put_nowait(self.create_thread(d))

        self.has_more = data.get("has_more", False)
        if self.limit is not None:
            self.limit -= len(threads)
            if self.limit <= 0:
                self.has_more = False

        if self.has_more:
            self.before = self.update_before(threads[-1])

    def create_thread(self, data: ThreadPayload) -> Thread:
        """Build a thread from its payload."""
        from .threads import Thread

        return Thread(guild=self.guild, state=self.guild._state, data=data)


class ScheduledEventSubscribersIterator(_AsyncIterator[Union["User", "Member"]]):
    """Iterator over the users subscribed to a scheduled event."""

    def __init__(
        self,
        event: ScheduledEvent,
        limit: int | None,
        with_member: bool = False,
        before: SnowflakeTime | None = None,
        after: SnowflakeTime | None = None,
        use_cache: bool = False,
    ) -> None:
        self.use_cache: bool = use_cache
        self._cache_limit: int | None = limit
        self.event: ScheduledEvent = event
        self.limit: int | None = limit
        self.with_member: bool = with_member
        self.before: Snowflake | None = _snowflake_bound(before, high=False)
        self.after: Snowflake | None = _snowflake_bound(after, high=True)

        self.subscribers: asyncio.Queue[User | Member] = asyncio.Queue()
        self.get_subscribers = self.event._state.http.get_scheduled_event_users
        self.retrieve: int

    @override
    async def next(self) -> User | Member:
        """Return the next subscriber, fetching a new page when needed."""
        if self.subscribers.empty():
            await self.fill_subs()

        try:
            return self.subscribers.get_nowait()
        except asyncio.QueueEmpty:
            raise NoMoreItems from None

    def _get_retrieve(self) -> bool:
        limit = self.limit
        r = 100 if limit is None or limit > 100 else limit
        self.retrieve = r
        return r > 0

    def member_from_payload(self, data: ScheduledEventSubscriberPayload) -> Member:
        """Build a member from a subscriber payload."""
        from .member import Member

        payload = cast("dict[str, Any]", data)
        user = payload.pop("user")

        member = payload.pop("member")
        member["user"] = user

        return Member(data=member, guild=self.event.guild, state=self.event._state)

    def user_from_payload(self, data: ScheduledEventSubscriberPayload) -> User:
        """Build a user from a subscriber payload."""
        from .user import User

        user = cast("dict[str, Any]", data).pop("user")

        return User(state=self.event._state, data=user)

    async def _fill_from_cache(self) -> None:
        before = self.before.id if self.before else None
        after = self.after.id if self.after else None
        state = self.event._state
        members = state._guild_bucket("members", self.event.guild_id)
        max_items = self._cache_limit
        self._cache_limit = 0
        count = 0
        for user_id in sorted(self.event._subscriber_ids):
            if before is not None and user_id >= before:
                continue
            if after is not None and user_id <= after:
                continue
            member = await members.get(user_id)
            subscriber = (
                member
                if self.with_member
                else await state.get_user(user_id) or getattr(member, "_user", None)
            )
            if subscriber is None:
                continue
            await self.subscribers.put(subscriber)
            count += 1
            if max_items is not None and count >= max_items:
                break

    async def fill_subs(self) -> None:
        """Fetch the next page of subscribers into the queue."""
        if self.use_cache:
            if self._cache_limit != 0:
                await self._fill_from_cache()
            return

        if not self._get_retrieve():
            return

        before = self.before.id if self.before else None
        after = self.after.id if self.after else None
        data = await self.get_subscribers(
            guild_id=self.event.guild.id,
            event_id=self.event.id,
            limit=self.retrieve,
            with_member=self.with_member,
            before=before,
            after=after,
        )

        data_length = len(data)
        if data_length < self.retrieve:
            self.limit = 0
        elif data_length > 0:
            if self.limit:
                self.limit -= self.retrieve
            self.after = Object(id=int(data[-1]["user_id"]))

        for element in reversed(data):
            if "member" in element:
                await self.subscribers.put(self.member_from_payload(element))
            else:
                await self.subscribers.put(self.user_from_payload(element))


class EntitlementIterator(_AsyncIterator["Entitlement"]):
    """Iterator over the entitlements of an application."""

    def __init__(
        self,
        state: ConnectionState,
        user_id: int | None = None,
        sku_ids: list[int] | None = None,
        before: SnowflakeTime | None = None,
        after: SnowflakeTime | None = None,
        limit: int | None = None,
        guild_id: int | None = None,
        exclude_ended: bool | None = None,
    ) -> None:
        self.user_id: int | None = user_id
        self.sku_ids: list[int] | None = sku_ids

        self.before: Snowflake | None = _snowflake_bound(before, high=False)
        self.after: Snowflake | None = _snowflake_bound(after, high=True)
        self.limit: int | None = limit
        self.guild_id: int | None = guild_id
        self.exclude_ended: bool | None = exclude_ended

        self._filter: Callable[[EntitlementPayload], bool] | None = None
        self._retrieve_entitlements: Callable[
            [int], Awaitable[list[EntitlementPayload]]
        ]

        if self.before and self.after:
            self._retrieve_entitlements = self._retrieve_entitlements_before_strategy
            after_id = self.after.id
            self._filter = lambda e: int(e["id"]) > after_id
        elif self.after:
            self._retrieve_entitlements = self._retrieve_entitlements_after_strategy
        else:
            self._retrieve_entitlements = self._retrieve_entitlements_before_strategy

        self.state: ConnectionState = state
        self.get_entitlements = state.http.list_entitlements
        self.entitlements: asyncio.Queue[Entitlement] = asyncio.Queue()
        self.retrieve: int

    @override
    async def next(self) -> Entitlement:
        """Return the next entitlement, fetching a new page when needed."""
        if self.entitlements.empty():
            await self.fill_entitlements()

        try:
            return self.entitlements.get_nowait()
        except asyncio.QueueEmpty:
            raise NoMoreItems from None

    def _get_retrieve(self) -> bool:
        limit = self.limit
        r = 100 if limit is None or limit > 100 else limit
        self.retrieve = r
        return r > 0

    def create_entitlement(self, data: EntitlementPayload) -> Entitlement:
        """Build an entitlement from its payload."""
        from .monetization import Entitlement

        return Entitlement(data=data, state=self.state)

    async def fill_entitlements(self) -> None:
        """Fetch the next page of entitlements into the queue."""
        if not self._get_retrieve():
            return

        data = await self._retrieve_entitlements(self.retrieve)

        if self._filter:
            data = list(filter(self._filter, data))

        if len(data) < 100:
            self.limit = 0  # terminate loop

        for element in data:
            await self.entitlements.put(self.create_entitlement(element))

    async def _retrieve_entitlements_before_strategy(
        self, retrieve: int
    ) -> list[EntitlementPayload]:
        """Retrieve entitlements using before parameter."""
        before = self.before.id if self.before else None
        data = await self.get_entitlements(
            cast("int", self.state.application_id),
            before=before,
            limit=retrieve,
            user_id=self.user_id,
            guild_id=self.guild_id,
            sku_ids=self.sku_ids,
            exclude_ended=self.exclude_ended,
        )
        if data:
            if self.limit is not None:
                self.limit -= retrieve
            self.before = Object(id=int(data[-1]["id"]))
        return data

    async def _retrieve_entitlements_after_strategy(
        self, retrieve: int
    ) -> list[EntitlementPayload]:
        """Retrieve entitlements using after parameter."""
        after = self.after.id if self.after else None
        data = await self.get_entitlements(
            cast("int", self.state.application_id),
            after=after,
            limit=retrieve,
            user_id=self.user_id,
            guild_id=self.guild_id,
            sku_ids=self.sku_ids,
            exclude_ended=self.exclude_ended,
        )
        if data:
            if self.limit is not None:
                self.limit -= retrieve
            self.after = Object(id=int(data[-1]["id"]))
        return data


class SubscriptionIterator(_AsyncIterator["Subscription"]):
    """Iterator over the subscriptions of a SKU."""

    def __init__(
        self,
        state: ConnectionState,
        sku_id: int,
        limit: int | None = None,
        before: SnowflakeTime | None = None,
        after: SnowflakeTime | None = None,
        user_id: int | None = None,
    ) -> None:
        self.state: ConnectionState = state
        self.sku_id: int = sku_id
        self.limit: int | None = limit
        self.before: Snowflake | None = _snowflake_bound(before, high=False)
        self.after: Snowflake | None = _snowflake_bound(after, high=True)
        self.user_id: int | None = user_id

        self._filter: Callable[[SubscriptionPayload], bool] | None = None

        self.get_subscriptions = state.http.list_sku_subscriptions
        self.subscriptions: asyncio.Queue[Subscription] = asyncio.Queue()
        self.retrieve: int
        self._retrieve_subscriptions: Callable[
            [int], Awaitable[list[SubscriptionPayload]]
        ]

        if self.before and self.after:
            self._retrieve_subscriptions = self._retrieve_subscriptions_before_strategy
            after_id = self.after.id
            self._filter = lambda m: int(m["id"]) > after_id
        elif self.after:
            self._retrieve_subscriptions = self._retrieve_subscriptions_after_strategy
        else:
            self._retrieve_subscriptions = self._retrieve_subscriptions_before_strategy

    @override
    async def next(self) -> Subscription:
        """Return the next subscription, fetching a new page when needed."""
        if self.subscriptions.empty():
            await self.fill_subscriptions()

        try:
            return self.subscriptions.get_nowait()
        except asyncio.QueueEmpty:
            raise NoMoreItems from None

    def _get_retrieve(self) -> bool:
        limit = self.limit
        r = 100 if limit is None or limit > 100 else limit
        self.retrieve = r
        return r > 0

    def create_subscription(self, data: SubscriptionPayload) -> Subscription:
        """Build a subscription from its payload."""
        from .monetization import Subscription

        return Subscription(state=self.state, data=data)

    async def fill_subscriptions(self) -> None:
        """Fetch the next page of subscriptions into the queue."""
        if self._get_retrieve():
            data = await self._retrieve_subscriptions(self.retrieve)
            if self.limit is None or len(data) < 100:
                self.limit = 0

            items: Iterable[SubscriptionPayload] = data
            if self._filter:
                items = filter(self._filter, items)

            for element in items:
                await self.subscriptions.put(self.create_subscription(element))

    async def _retrieve_subscriptions_before_strategy(
        self, retrieve: int
    ) -> list[SubscriptionPayload]:
        before = self.before.id if self.before else None
        data: list[SubscriptionPayload] = await self.get_subscriptions(
            self.sku_id,
            limit=retrieve,
            before=before,
            user_id=self.user_id,
        )
        if len(data):
            if self.limit is not None:
                self.limit -= retrieve
            self.before = Object(id=int(data[-1]["id"]))
        return data

    async def _retrieve_subscriptions_after_strategy(
        self, retrieve: int
    ) -> list[SubscriptionPayload]:
        after = self.after.id if self.after else None
        data: list[SubscriptionPayload] = await self.get_subscriptions(
            self.sku_id,
            limit=retrieve,
            after=after,
            user_id=self.user_id,
        )
        if len(data):
            if self.limit is not None:
                self.limit -= retrieve
            self.after = Object(id=int(data[0]["id"]))
        return data


class MessagePinIterator(_AsyncIterator["MessagePin"]):
    """Iterator over the pinned messages of a channel."""

    def __init__(
        self,
        channel: Messageable,
        limit: int | None,
        before: Snowflake | dt.datetime | None = None,
    ) -> None:
        self._channel: Messageable = channel
        self.channel: MessageableChannel | Object | None = None

        self.limit: int | None = limit
        self.http: HTTPClient = channel._state.http

        self.before: str | None
        if before is None:
            self.before = None
        elif isinstance(before, dt.datetime):
            self.before = before.isoformat()
        else:
            self.before = snowflake_time(before.id).isoformat()

        self.update_before: Callable[[MessagePinPayload], str] = self.get_last_pinned

        self.queue: asyncio.Queue[MessagePin] = asyncio.Queue()
        self.has_more: bool = True

    @override
    async def next(self) -> MessagePin:
        """Return the next pin, fetching a new page when needed."""
        if self.queue.empty():
            await self.fill_queue()

        try:
            return self.queue.get_nowait()
        except asyncio.QueueEmpty:
            raise NoMoreItems from None

    @staticmethod
    def get_last_pinned(data: MessagePinPayload) -> str:
        """Return the timestamp at which a pin was created."""
        return data["pinned_at"]

    async def fill_queue(self) -> None:
        """Fetch the next page of pins into the queue."""
        if not self.has_more:
            raise NoMoreItems

        if self.channel is None:
            channel = await self._channel._get_channel()
            self.channel = channel

        limit = 50 if self.limit is None else min(self.limit, 50)
        data = await self.http.pins_from(
            self.channel.id, before=self.before, limit=limit
        )

        pins: list[MessagePinPayload] = data.get("items", [])
        for d in pins:
            self.queue.put_nowait(await self.create_pin(d))

        self.has_more = data.get("has_more", False)
        if self.limit is not None:
            self.limit -= len(pins)
            if self.limit <= 0:
                self.has_more = False

        if self.has_more:
            self.before = self.update_before(pins[-1])

    async def create_pin(self, data: MessagePinPayload) -> MessagePin:
        """Build a pin from its payload."""
        from .message import MessagePin

        channel = self.channel
        if channel is None:
            raise RuntimeError("Channel is None, cannot create pin")

        if not isinstance(channel, Object):
            state = channel._state
            pin = MessagePin(state=state, channel=channel, data=data)
            await state._populate_message(pin.message, data["message"])
            return pin

        raise RuntimeError("Cannot create pin for Object channel")

    async def retrieve_inner(self) -> list[Message]:
        """Return the messages of every pin."""
        pins = await self.flatten()
        return [p.message for p in pins]

    @deprecated(
        "Messageable.pins() returning a list of Message is deprecated since version 2.7 and will be removed in 2.9."
        " See the documentation of Messageable.pins() for more information."
    )
    def __await__(self) -> Generator[Any, Any, list[Message]]:
        return self.retrieve_inner().__await__()


class MessageSearchIterator(_AsyncIterator["Message"]):
    """Iterator for the results of a guild message search.

    Discord caps the pages at 25 messages and the offset at 9975, so no more
    than 10000 results can be reached. Pages that Discord is still indexing are
    retried after the delay it asks for.

    Attributes
    ----------
    total_results: Optional[:class:`int`]
        The number of messages matching the search, ``None`` until the first
        page was received. It may be inaccurate while messages are created or deleted.
    doing_deep_historical_index: Optional[:class:`bool`]
        Whether the guild is undergoing a deep historical indexing operation,
        ``None`` until the first page was received.
    documents_indexed: Optional[:class:`int`]
        The number of documents indexed during the current index operation, if any.
    """

    PAGE_SIZE = 25
    MAX_OFFSET = 9975
    DEFAULT_RETRY_DELAY = 1.0

    def __init__(
        self,
        guild: Guild | PartialGuild,
        *,
        limit: int | None,
        params: dict[str, Any],
        index_retries: int,
    ) -> None:
        self.guild: Guild | PartialGuild = guild
        self.limit: int | None = limit
        self.params: dict[str, Any] = params
        self.index_retries: int = index_retries
        self.state: ConnectionState = guild._state
        self.offset: int = params.pop("offset", 0)
        self.messages: asyncio.Queue[Message] = asyncio.Queue()
        self.seen: set[int] = set()
        self.exhausted: bool = False
        self.total_results: int | None = None
        self.doing_deep_historical_index: bool | None = None
        self.documents_indexed: int | None = None

    @override
    async def next(self) -> Message:
        while self.messages.empty() and not self.exhausted:
            await self._fill_messages()

        try:
            return self.messages.get_nowait()
        except asyncio.QueueEmpty:
            raise NoMoreItems from None

    async def count(self) -> int:
        """Return the number of messages matching the search.

        The first page is requested when it was not received yet.
        """
        if self.total_results is None:
            await self._fill_messages()
        return self.total_results or 0

    async def _retrieve_page(self, size: int) -> MessageSearchResults:
        attempts = 0
        while True:
            page: dict[str, Any] = {"limit": size, **self.params}
            if self.offset:
                page["offset"] = self.offset
            data = await self.state.http.search_guild_messages(self.guild.id, **page)
            if "messages" in data:
                return data

            retry_after = float(data.get("retry_after", 0))
            self.documents_indexed = data.get("documents_indexed")
            if attempts >= self.index_retries:
                raise SearchIndexNotReady(
                    retry_after=retry_after,
                    documents_indexed=data.get("documents_indexed", 0),
                )
            attempts += 1
            await asyncio.sleep(retry_after or self.DEFAULT_RETRY_DELAY)

    async def _fill_messages(self) -> None:
        remaining = self.PAGE_SIZE if self.limit is None else self.limit
        size = min(self.PAGE_SIZE, remaining)
        if size <= 0 or self.offset > self.MAX_OFFSET:
            self.exhausted = True
            return

        data = await self._retrieve_page(size)
        self.total_results = data["total_results"]
        self.doing_deep_historical_index = data["doing_deep_historical_index"]
        self.documents_indexed = data.get("documents_indexed")
        self.offset += size
        if self.offset >= self.total_results:
            self.exhausted = True

        threads = {int(t["id"]): t for t in data.get("threads", [])}
        for group in data["messages"]:
            for payload in group:
                message_id = int(payload["id"])
                if message_id in self.seen:
                    continue
                self.seen.add(message_id)
                payload.setdefault("guild_id", str(self.guild.id))
                channel = await self._resolve_channel(payload, threads)
                await self.messages.put(
                    await self.state._create_message(channel=channel, data=payload)
                )
                if self.limit is not None:
                    self.limit -= 1

    async def _resolve_channel(
        self, payload: MessagePayload, threads: dict[int, ThreadPayload]
    ) -> MessageableChannel:
        channel_id = int(payload["channel_id"])
        thread = threads.get(channel_id)
        if thread is not None:
            cached: Thread | None = await self.state._guild_bucket(
                "threads", self.guild.id
            ).get(channel_id)
            if cached is not None:
                return cached
            built = await self.state._build_thread(self.guild, thread)
            return await self.state._cache_fetched(built)

        channel, _ = await self.state._get_guild_channel(payload, self.guild.id)
        return channel
