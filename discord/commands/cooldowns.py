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

"""Cooldown and concurrency primitives shared by application and prefix commands."""

from __future__ import annotations

import inspect
import time
from collections import deque
from typing import TYPE_CHECKING, Any, TypeVar, cast

import discord.abc
from discord.enums import Enum
from discord.utils import _get_event_loop

from ..abc import PrivateChannel
from ..channel import PartialMessageable
from ..member import Member

if TYPE_CHECKING:
    import asyncio
    from collections.abc import Callable

    from typing_extensions import Self

    from ..abc import Snowflake
    from ..message import Message
    from .context import BaseContext

__all__ = (
    "BucketType",
    "Cooldown",
    "CooldownMapping",
    "DynamicCooldownMapping",
    "MaxConcurrency",
    "resolve_cooldown_settings",
)

C = TypeVar("C", bound="CooldownMapping")


def _is_instance(value: object, cls: type) -> bool:
    return isinstance(value, cls)


def _is_none(value: object) -> bool:
    return value is None


def _channel_id(target: Message | BaseContext) -> int:
    channel = target.channel
    if channel is None:
        raise ValueError("The context has no channel to key the bucket on.")
    return channel.id


class BucketType(Enum):
    """The bucket a cooldown or concurrency limit is keyed on."""

    default = 0
    user = 1
    guild = 2
    channel = 3
    member = 4
    category = 5
    role = 6

    def get_key(self, msg: Message | BaseContext) -> Any:
        """Returns the key identifying the bucket ``msg`` belongs to."""
        if self is BucketType.user:
            return msg.author.id
        if self is BucketType.guild:
            return (msg.guild or msg.author).id
        if self is BucketType.channel:
            return _channel_id(msg)
        if self is BucketType.member:
            return (msg.guild and msg.guild.id), msg.author.id
        if self is BucketType.category:
            return (
                msg.channel.category.id
                if isinstance(msg.channel, discord.abc.GuildChannel)
                and msg.channel.category
                else _channel_id(msg)
            )
        if self is BucketType.role:
            # we return the channel id of a private-channel as there are only roles in guilds
            # and that yields the same result as for a guild with only the @everyone role
            # NOTE: PrivateChannel doesn't actually have an id attribute, but we assume we are
            # receiving a DMChannel or GroupChannel which inherit from PrivateChannel and do
            if isinstance(msg.channel, PrivateChannel):  # pyright: ignore[reportGeneralTypeIssues]
                return cast("Snowflake", msg.channel).id
            return cast("Member", msg.author).top_role.id
        return None

    async def get_key_async(self, msg: Message | BaseContext) -> Any:
        """|coro|

        Returns the key identifying the bucket ``msg`` belongs to, like :meth:`get_key`
        but resolving what it needs through the cache with any backend.

        :attr:`role` uses :meth:`Member.get_top_role` and :attr:`category` uses the
        ``category_id`` of the channel, which is looked up with
        :meth:`Message.get_channel` only when the channel is a partial handle.

        .. versionadded:: 3.0
        """
        if self is BucketType.category:
            channel: Any = msg.channel
            if channel is None or isinstance(channel, PartialMessageable):
                channel = await msg.get_channel() or channel
            if (
                isinstance(channel, discord.abc.GuildChannel)
                and channel.category_id is not None
            ):
                return channel.category_id
            return channel.id
        if self is BucketType.role:
            guild = msg.guild
            if guild is None:
                return _channel_id(msg)
            author = msg.author
            top_role = (
                await author.get_top_role() if isinstance(author, Member) else None
            )
            return guild.id if top_role is None else top_role.id
        return self.get_key(msg)

    def __call__(self, msg: Message | BaseContext) -> Any:
        """Alias of :meth:`get_key`."""
        return self.get_key(msg)


class Cooldown:
    """Represents a cooldown for a command.

    Attributes
    ----------
    rate: :class:`int`
        The total number of tokens available per :attr:`per` seconds.
    per: :class:`float`
        The length of the cooldown period in seconds.
    """

    __slots__ = ("_last", "_tokens", "_window", "per", "rate")

    def __init__(self, rate: float, per: float) -> None:
        self.rate: int = int(rate)
        self.per: float = float(per)
        self._window: float = 0.0
        self._tokens: int = self.rate
        self._last: float = 0.0

    def get_tokens(self, current: float | None = None) -> int:
        """Returns the number of available tokens before rate limiting is applied.

        Parameters
        ----------
        current: Optional[:class:`float`]
            The time in seconds since Unix epoch to calculate tokens at.
            If not supplied then :func:`time.time()` is used.

        Returns
        -------
        :class:`int`
            The number of tokens available before the cooldown is to be applied.
        """
        if not current:
            current = time.time()

        tokens = self._tokens

        if current > self._window + self.per:
            tokens = self.rate
        return tokens

    def get_retry_after(self, current: float | None = None) -> float:
        """Returns the time in seconds until the cooldown will be reset.

        Parameters
        ----------
        current: Optional[:class:`float`]
            The current time in seconds since Unix epoch.
            If not supplied, then :func:`time.time()` is used.

        Returns
        -------
        :class:`float`
            The number of seconds to wait before this cooldown will be reset.
        """
        current = current or time.time()
        tokens = self.get_tokens(current)

        if tokens == 0:
            return self.per - (current - self._window)

        return 0.0

    def update_rate_limit(self, current: float | None = None) -> float | None:
        """Updates the cooldown rate limit.

        Parameters
        ----------
        current: Optional[:class:`float`]
            The time in seconds since Unix epoch to update the rate limit at.
            If not supplied, then :func:`time.time()` is used.

        Returns
        -------
        Optional[:class:`float`]
            The retry-after time in seconds if rate limited.
        """
        current = current or time.time()
        self._last = current

        self._tokens = self.get_tokens(current)

        # first token used means that we start a new rate limit window
        if self._tokens == self.rate:
            self._window = current

        # check if we are rate limited
        if self._tokens == 0:
            return self.per - (current - self._window)

        # we're not so decrement our tokens
        self._tokens -= 1
        return None

    def reset(self) -> None:
        """Reset the cooldown to its initial state."""
        self._tokens = self.rate
        self._last = 0.0

    def copy(self) -> Cooldown:
        """Creates a copy of this cooldown.

        Returns
        -------
        :class:`Cooldown`
            A new instance of this cooldown.
        """
        return Cooldown(self.rate, self.per)

    def __repr__(self) -> str:
        return (
            f"<Cooldown rate: {self.rate} per: {self.per} window:"
            f" {self._window} tokens: {self._tokens}>"
        )


class CooldownMapping:
    """Maps buckets to :class:`Cooldown` instances."""

    def __init__(
        self,
        original: Cooldown | None,
        type: Callable[[Message], Any],
    ) -> None:
        if not callable(type):
            raise TypeError("Cooldown type must be a BucketType or callable")

        self._cache: dict[Any, Cooldown] = {}
        self._cooldown: Cooldown | None = original
        self._type: Callable[[Message], Any] = type

    def copy(self) -> CooldownMapping:
        """Returns a copy of this mapping."""
        ret = CooldownMapping(self._cooldown, self._type)
        ret._cache = self._cache.copy()
        return ret

    @property
    def valid(self) -> bool:
        """Whether a cooldown is configured."""
        return self._cooldown is not None

    @property
    def type(self) -> Callable[[Message], Any]:
        """The bucket type callable."""
        return self._type

    @classmethod
    def from_cooldown(
        cls: type[C], rate: float, per: float, type: Callable[[Message], Any]
    ) -> C:
        """Creates a mapping from a rate, a period and a bucket type."""
        return cls(Cooldown(rate, per), type)

    def _bucket_key(self, msg: Message) -> Any:
        return self._type(msg)

    async def _bucket_key_async(self, msg: Message) -> Any:
        if isinstance(self._type, BucketType):
            return await self._type.get_key_async(msg)
        key = self._type(msg)
        if inspect.isawaitable(key):
            return await key
        return key

    def _verify_cache_integrity(self, current: float | None = None) -> None:
        # we want to delete all cache objects that haven't been used
        # in a cooldown window. e.g. if we have a  command that has a
        # cooldown of 60s, and it has not been used in 60s then that key should be deleted
        current = current or time.time()
        dead_keys = [k for k, v in self._cache.items() if current > v._last + v.per]
        for k in dead_keys:
            del self._cache[k]

    def create_bucket(self, message: Message) -> Cooldown:
        """Creates the cooldown of the bucket ``message`` belongs to."""
        return cast("Cooldown", self._cooldown).copy()

    def get_bucket(self, message: Message, current: float | None = None) -> Cooldown:
        """Returns the cooldown of the bucket ``message`` belongs to."""
        if self._type is BucketType.default:
            return cast("Cooldown", self._cooldown)

        self._verify_cache_integrity(current)
        return self._bucket_for(message, self._bucket_key(message))

    async def get_bucket_async(
        self, message: Message, current: float | None = None
    ) -> Cooldown:
        """|coro|

        Returns the cooldown of the bucket ``message`` belongs to, like :meth:`get_bucket`
        but with a key resolved through :meth:`BucketType.get_key_async`, which works with
        every cache backend. A callable bucket type may return an awaitable.

        .. versionadded:: 3.0
        """
        if self._type is BucketType.default:
            return cast("Cooldown", self._cooldown)

        key = await self._bucket_key_async(message)
        self._verify_cache_integrity(current)
        return self._bucket_for(message, key)

    def _bucket_for(self, message: Message, key: Any) -> Cooldown:
        if key not in self._cache:
            bucket = self.create_bucket(message)
            if not _is_none(bucket):
                self._cache[key] = bucket
        else:
            bucket = self._cache[key]

        return bucket

    def update_rate_limit(
        self, message: Message, current: float | None = None
    ) -> float | None:
        """Updates the bucket of ``message`` and returns the retry-after time if rate limited."""
        bucket = self.get_bucket(message, current)
        return bucket.update_rate_limit(current)

    async def update_rate_limit_async(
        self, message: Message, current: float | None = None
    ) -> float | None:
        """|coro|

        Like :meth:`update_rate_limit` but resolving the bucket with :meth:`get_bucket_async`.

        .. versionadded:: 3.0
        """
        bucket = await self.get_bucket_async(message, current)
        return bucket.update_rate_limit(current)


class DynamicCooldownMapping(CooldownMapping):
    """A :class:`CooldownMapping` whose cooldown is built by a factory."""

    def __init__(
        self, factory: Callable[[Message], Cooldown], type: Callable[[Message], Any]
    ) -> None:
        super().__init__(None, type)
        self._factory: Callable[[Message], Cooldown] = factory

    def copy(self) -> DynamicCooldownMapping:
        """Returns a copy of this mapping."""
        ret = DynamicCooldownMapping(self._factory, self._type)
        ret._cache = self._cache.copy()
        return ret

    @property
    def valid(self) -> bool:
        """Always ``True``."""
        return True

    def create_bucket(self, message: Message) -> Cooldown:
        """Creates the cooldown through the factory."""
        return self._factory(message)


class _Semaphore:
    """A version of a semaphore.

    If you're wondering why asyncio.Semaphore isn't being used,
    it's because it doesn't expose the internal value. This internal
    value is necessary because I need to support both `wait=True` and
    `wait=False`.

    An asyncio.Queue could have been used to do this as well -- but it is
    not as efficient since internally that uses two queues and is a bit
    overkill for what is basically a counter.
    """

    __slots__ = ("_waiters", "loop", "value")

    def __init__(self, number: int) -> None:
        self.value: int = number
        self.loop: asyncio.AbstractEventLoop = _get_event_loop()
        self._waiters: deque[asyncio.Future[None]] = deque()

    def __repr__(self) -> str:
        return f"<_Semaphore value={self.value} waiters={len(self._waiters)}>"

    def locked(self) -> bool:
        return self.value == 0

    def is_active(self) -> bool:
        return len(self._waiters) > 0

    def wake_up(self) -> None:
        while self._waiters:
            future = self._waiters.popleft()
            if not future.done():
                future.set_result(None)
                return

    async def acquire(self, *, wait: bool = False) -> bool:
        if not wait and self.value <= 0:
            # signal that we're not acquiring
            return False

        while self.value <= 0:
            future = self.loop.create_future()
            self._waiters.append(future)
            try:
                await future
            except:
                future.cancel()
                if self.value > 0 and not future.cancelled():
                    self.wake_up()
                raise

        self.value -= 1
        return True

    def release(self) -> None:
        self.value += 1
        self.wake_up()


class MaxConcurrency:
    """Limits how many invocations of a command can run at once per bucket."""

    __slots__ = ("_mapping", "number", "per", "wait")

    def __init__(self, number: int, *, per: BucketType, wait: bool) -> None:
        self._mapping: dict[Any, _Semaphore] = {}
        self.per: BucketType = per
        self.number: int = number
        self.wait: bool = wait

        if number <= 0:
            raise ValueError("max_concurrency 'number' cannot be less than 1")

        if not _is_instance(per, BucketType):
            raise TypeError(
                f"max_concurrency 'per' must be of type BucketType not {type(per)!r}"
            )

    def copy(self) -> Self:
        """Returns a copy of this limit."""
        return self.__class__(self.number, per=self.per, wait=self.wait)

    def __repr__(self) -> str:
        return (
            f"<MaxConcurrency per={self.per!r} number={self.number} wait={self.wait}>"
        )

    def get_key(self, message: Message | BaseContext) -> Any:
        """Returns the key identifying the bucket ``message`` belongs to."""
        return self.per.get_key(message)

    async def acquire(self, message: Message | BaseContext) -> None:
        """Acquires a slot or raises :exc:`.MaxConcurrencyReached`."""
        key = await self.per.get_key_async(message)

        try:
            sem = self._mapping[key]
        except KeyError:
            self._mapping[key] = sem = _Semaphore(self.number)

        acquired = await sem.acquire(wait=self.wait)
        if not acquired:
            from ..ext.commands.errors import (
                MaxConcurrencyReached,
            )

            raise MaxConcurrencyReached(self.number, self.per)

    async def release(self, message: Message | BaseContext) -> None:
        """Releases the slot taken by :meth:`acquire`."""
        # Technically there's no reason for this function to be async
        # But it might be more useful in the future
        key = await self.per.get_key_async(message)

        try:
            sem = self._mapping[key]
        except KeyError:
            # ...? peculiar
            return
        else:
            sem.release()

        if sem.value >= self.number and not sem.is_active():
            del self._mapping[key]


def resolve_cooldown_settings(
    *, cooldown: CooldownMapping | None, max_concurrency: MaxConcurrency | None
) -> tuple[CooldownMapping, MaxConcurrency | None]:
    """Validates and returns the cooldown mapping and concurrency limit of a command."""
    if cooldown is None:
        buckets = CooldownMapping(cooldown, BucketType.default)
    elif _is_instance(cooldown, CooldownMapping):
        buckets = cooldown
    else:
        raise TypeError("Cooldown must be an instance of CooldownMapping or None.")

    if max_concurrency is not None and not _is_instance(
        max_concurrency, MaxConcurrency
    ):
        raise TypeError("max_concurrency must be an instance of MaxConcurrency or None")

    return buckets, max_concurrency
